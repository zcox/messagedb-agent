"""FastAPI service for rendering agent events to HTML.

This module provides the main FastAPI application with the /render endpoint
that processes user messages and renders event streams as HTML.
"""

import os
from collections.abc import AsyncIterator
from datetime import UTC
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.display.agent_runner import run_agent_step
from messagedb_agent.display.models import RenderRequest, RenderResponse
from messagedb_agent.display.progress import ProgressEvent, ProgressStage
from messagedb_agent.display.renderer import render_html
from messagedb_agent.projections.display_prefs import project_display_prefs
from messagedb_agent.store import MessageDBClient, MessageDBConfig, read_stream, write_message

# Load environment variables from .env file
load_dotenv()

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI app instance
    """
    app = FastAPI(
        title="MessageDB Agent Display Service",
        description="Renders agent event streams as HTML with LLM-powered generation",
        version="0.1.0",
    )

    # Get the directory where this module is located
    module_dir = Path(__file__).parent

    # Mount static files (JavaScript, CSS)
    app.mount("/static", StaticFiles(directory=str(module_dir / "static")), name="static")

    # Set up Jinja2 templates
    templates = Jinja2Templates(directory=str(module_dir / "templates"))

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, thread_id: str) -> HTMLResponse:  # type: ignore[reportUnusedFunction]  # noqa: E501
        """Serve the main agent interface.

        Args:
            request: FastAPI request object
            thread_id: Thread ID to display

        Returns:
            HTML response with the chat interface
        """
        return templates.TemplateResponse(
            "index.html", {"request": request, "thread_id": thread_id}
        )

    @app.get("/health")
    async def health() -> dict[str, str]:  # type: ignore[reportUnusedFunction]
        """Health check endpoint.

        Returns:
            Status message
        """
        return {"status": "healthy"}

    @app.post("/render-stream")
    async def render_stream(request: RenderRequest) -> StreamingResponse:  # type: ignore[reportUnusedFunction]  # noqa: E501
        """Render agent events to HTML with streaming progress updates.

        This endpoint streams Server-Sent Events (SSE) to provide real-time progress
        updates during the rendering process, then sends the final HTML result.

        Args:
            request: Render request with thread_id, optional user_message, and previous_html

        Returns:
            StreamingResponse with SSE progress events followed by final result

        Raises:
            HTTPException: If rendering fails
        """

        async def event_stream() -> AsyncIterator[str]:
            """Generate SSE progress events and final result."""
            try:
                # Load configuration from environment
                db_config = MessageDBConfig(
                    host=os.getenv("DB_HOST", "localhost"),
                    port=int(os.getenv("DB_PORT", "5432")),
                    database=os.getenv("DB_NAME", "message_store"),
                    user=os.getenv("DB_USER", "message_store_user"),
                    password=os.getenv("DB_PASSWORD", "message_store_password"),
                )

                # LLM config for agent processing (if needed)
                agent_llm_config = VertexAIConfig(
                    project=os.getenv("GCP_PROJECT", ""),
                    location=os.getenv("GCP_LOCATION", "us-central1"),
                    model_name=os.getenv(
                        "AGENT_MODEL", os.getenv("MODEL_NAME", "gemini-2.5-flash")
                    ),
                )

                # LLM config for HTML rendering (use fast/cheap model)
                render_llm_config = VertexAIConfig(
                    project=os.getenv("GCP_PROJECT", ""),
                    location=os.getenv("GCP_LOCATION", "us-central1"),
                    model_name=os.getenv(
                        "RENDER_MODEL", os.getenv("MODEL_NAME", "gemini-2.5-flash")
                    ),
                )

                stream_name = f"agent:v0-{request.thread_id}"
                display_prefs_stream = f"display-prefs:{request.thread_id}"

                # Step 1: Handle user message (if provided)
                if request.user_message:
                    yield ProgressEvent(
                        stage=ProgressStage.WRITING_USER_MESSAGE,
                        message="Writing user message to event stream",
                    ).to_sse()

                    with MessageDBClient(db_config) as store_client:
                        from datetime import datetime

                        event_data: dict[str, Any] = {
                            "message": request.user_message,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }

                        write_message(
                            client=store_client,
                            stream_name=stream_name,
                            message_type="UserMessageAdded",
                            data=event_data,
                            metadata={},
                        )

                    yield ProgressEvent(
                        stage=ProgressStage.AGENT_PROCESSING,
                        message="Processing message with agent (this may take a while)",
                    ).to_sse()

                    # Run agent processing loop
                    await run_agent_step(
                        thread_id=request.thread_id,
                        db_config=db_config,
                        llm_config=agent_llm_config,
                        auto_approve_tools=True,
                    )

                # Step 2: Read all events from stream
                yield ProgressEvent(
                    stage=ProgressStage.READING_EVENTS,
                    message="Reading events from stream",
                ).to_sse()

                with MessageDBClient(db_config) as store_client:
                    events = read_stream(store_client, stream_name)

                    yield ProgressEvent(
                        stage=ProgressStage.READING_EVENTS,
                        message=f"Read {len(events)} events from stream",
                        details={"event_count": len(events)},
                    ).to_sse()

                    # Step 3: Read and project display preferences
                    yield ProgressEvent(
                        stage=ProgressStage.READING_PREFERENCES,
                        message="Reading display preferences",
                    ).to_sse()

                    display_prefs_events = read_stream(store_client, display_prefs_stream)

                # Convert events to dicts for projection
                display_prefs_dicts = [
                    {
                        "type": event.type,
                        "data": event.data,
                    }
                    for event in display_prefs_events
                ]

                current_prefs = project_display_prefs(display_prefs_dicts)

                # Step 4: Render HTML
                yield ProgressEvent(
                    stage=ProgressStage.RENDERING_HTML,
                    message="Generating HTML with LLM (this may take a while)",
                ).to_sse()

                html = await render_html(
                    events=events,
                    display_prefs=current_prefs,
                    llm_config=render_llm_config,
                    previous_html=request.previous_html,
                )

                # Send completion event with final result
                import json

                result = RenderResponse(html=html, display_prefs=current_prefs)
                yield ProgressEvent(
                    stage=ProgressStage.COMPLETE,
                    message="Rendering complete",
                    details={"html_length": len(html)},
                ).to_sse()

                # Send final result as JSON in a special event
                yield f"event: result\ndata: {json.dumps(result.model_dump())}\n\n"

            except Exception as e:
                import json

                logger.error("Render stream failed", error=str(e), error_type=type(e).__name__)
                # Send error event
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    @app.post("/render")
    async def render(request: RenderRequest) -> RenderResponse:  # type: ignore[reportUnusedFunction]  # noqa: E501
        """Render agent events to HTML (legacy non-streaming endpoint).

        This endpoint:
        1. Optionally processes a user message through the agent
        2. Reads all events from the agent stream
        3. Reads and projects display preferences
        4. Renders events as HTML using an LLM
        5. Sanitizes and returns the HTML

        Args:
            request: Render request with thread_id, optional user_message, and previous_html

        Returns:
            RenderResponse with sanitized HTML and display preferences

        Raises:
            HTTPException: If rendering fails
        """
        log = logger.bind(
            thread_id=request.thread_id,
            has_user_message=request.user_message is not None,
            has_previous_html=request.previous_html is not None,
        )
        log.info("Processing render request")

        try:
            # Load configuration from environment
            db_config = MessageDBConfig(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                database=os.getenv("DB_NAME", "message_store"),
                user=os.getenv("DB_USER", "message_store_user"),
                password=os.getenv("DB_PASSWORD", "message_store_password"),
            )

            # LLM config for agent processing (if needed)
            # Falls back to MODEL_NAME from .env if AGENT_MODEL not set
            agent_llm_config = VertexAIConfig(
                project=os.getenv("GCP_PROJECT", ""),
                location=os.getenv("GCP_LOCATION", "us-central1"),
                model_name=os.getenv("AGENT_MODEL", os.getenv("MODEL_NAME", "gemini-2.5-flash")),
            )

            # LLM config for HTML rendering (use fast/cheap model)
            # Falls back to MODEL_NAME from .env if RENDER_MODEL not set
            render_llm_config = VertexAIConfig(
                project=os.getenv("GCP_PROJECT", ""),
                location=os.getenv("GCP_LOCATION", "us-central1"),
                model_name=os.getenv("RENDER_MODEL", os.getenv("MODEL_NAME", "gemini-2.5-flash")),
            )

            stream_name = f"agent:v0-{request.thread_id}"
            display_prefs_stream = f"display-prefs:{request.thread_id}"

            # Step 1: Handle user message (if provided)
            if request.user_message:
                log.info("Processing user message")

                # Write UserMessageAdded event
                with MessageDBClient(db_config) as store_client:
                    from datetime import datetime

                    event_data: dict[str, Any] = {
                        "message": request.user_message,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

                    write_message(
                        client=store_client,
                        stream_name=stream_name,
                        message_type="UserMessageAdded",
                        data=event_data,
                        metadata={},
                    )

                log.info("User message written, starting agent processing")

                # Run agent processing loop
                await run_agent_step(
                    thread_id=request.thread_id,
                    db_config=db_config,
                    llm_config=agent_llm_config,
                    auto_approve_tools=True,
                )

                log.info("Agent processing complete")

            # Step 2: Read all events from stream
            with MessageDBClient(db_config) as store_client:
                events = read_stream(store_client, stream_name)
                log.info("Read events from stream", event_count=len(events))

                # Step 3: Read and project display preferences
                display_prefs_events = read_stream(store_client, display_prefs_stream)
                log.info(
                    "Read display preferences",
                    display_prefs_event_count=len(display_prefs_events),
                )

            # Convert events to dicts for projection
            display_prefs_dicts = [
                {
                    "type": event.type,
                    "data": event.data,
                }
                for event in display_prefs_events
            ]

            current_prefs = project_display_prefs(display_prefs_dicts)
            log.info("Projected display preferences", preferences=current_prefs)

            # Step 4: Render HTML
            html = await render_html(
                events=events,
                display_prefs=current_prefs,
                llm_config=render_llm_config,
                previous_html=request.previous_html,
            )

            log.info("Render complete", html_length=len(html))

            return RenderResponse(html=html, display_prefs=current_prefs)

        except Exception as e:
            log.error("Render request failed", error=str(e), error_type=type(e).__name__)
            raise HTTPException(status_code=500, detail=f"Rendering failed: {str(e)}") from e

    return app


def main() -> None:
    """Run the display service with uvicorn.

    This is the entry point for running the service directly.
    For production, use uvicorn directly:
        uvicorn messagedb_agent.display.service:app --host 0.0.0.0 --port 8000
    """
    import uvicorn

    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()

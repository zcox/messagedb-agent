"""FastAPI service for rendering agent events to HTML.

This module provides the main FastAPI application with the /render endpoint
that processes user messages and renders event streams as HTML.
"""

import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.display.agent_runner import run_agent_step, run_agent_step_streaming
from messagedb_agent.display.models import RenderRequest, RenderResponse
from messagedb_agent.display.renderer import render_html, render_html_stream, sanitize_html
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

    @app.get("/", response_model=None)
    async def index(request: Request, thread_id: str | None = None) -> HTMLResponse | RedirectResponse:  # type: ignore[reportUnusedFunction]  # noqa: E501
        """Serve the main agent interface.

        If no thread_id is provided, generates a new UUID and redirects to the URL with
        the thread_id query parameter.

        Args:
            request: FastAPI request object
            thread_id: Thread ID to display (optional - generates new UUID if not provided)

        Returns:
            HTML response with the chat interface, or redirect if thread_id not provided
        """
        if thread_id is None:
            # Generate new thread ID and redirect
            new_thread_id = str(uuid.uuid4())
            return RedirectResponse(url=f"/?thread_id={new_thread_id}", status_code=302)

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
        """Render agent events to HTML with real-time event streaming.

        This endpoint streams Server-Sent Events (SSE) to provide real-time visibility
        into agent processing by polling the stream and forwarding new events as they appear,
        then sends the final HTML result.

        The implementation:
        1. Reads current stream length
        2. Optionally writes user message
        3. Starts agent processing in background task
        4. Polls stream periodically, streaming new events via SSE
        5. Renders final HTML and sends result

        Args:
            request: Render request with thread_id, optional user_message, and previous_html

        Returns:
            StreamingResponse with SSE events followed by final result

        Raises:
            HTTPException: If rendering fails
        """

        async def event_stream() -> AsyncIterator[str]:
            """Generate SSE events with dual streaming (agent LLM + HTML rendering)."""
            store_client: MessageDBClient | None = None

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

                # Step 1: Initialize store client
                store_client = MessageDBClient(db_config)
                store_client.__enter__()

                logger.info("Starting dual streaming event stream", stream_name=stream_name)

                # Step 2: Handle user message (if provided)
                if request.user_message:
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

                # Phase 1: Agent streaming (if user message provided)
                if request.user_message:
                    logger.info("Starting agent streaming phase")
                    yield "event: agent_start\ndata: {}\n\n"

                    # Stream agent LLM deltas
                    async for delta in run_agent_step_streaming(
                        thread_id=request.thread_id,
                        store_client=store_client,
                        llm_config=agent_llm_config,
                        auto_approve_tools=True,
                    ):
                        yield f"event: agent_delta\ndata: {json.dumps(delta)}\n\n"

                    yield "event: agent_complete\ndata: {}\n\n"
                    logger.info("Agent streaming phase complete")

                # Step 3: Read all events for HTML rendering
                events = read_stream(store_client, stream_name)

                # Step 4: Read and project display preferences
                display_prefs_events = read_stream(store_client, display_prefs_stream)

                # Convert events to dicts for projection
                display_prefs_dicts = [
                    {"type": event.type, "data": event.data} for event in display_prefs_events
                ]

                current_prefs = project_display_prefs(display_prefs_dicts)

                # Phase 2: HTML rendering streaming
                logger.info("Starting HTML rendering streaming phase")
                yield "event: html_start\ndata: {}\n\n"

                # Buffer HTML chunks for final sanitization
                html_chunks: list[str] = []

                async for chunk in render_html_stream(
                    events=events,
                    display_prefs=current_prefs,
                    llm_config=render_llm_config,
                    previous_html=request.previous_html,
                ):
                    html_chunks.append(chunk)
                    yield f'event: html_chunk\ndata: {json.dumps({"chunk": chunk})}\n\n'

                logger.info("HTML streaming complete, processing final HTML")

                # Process complete HTML (extract from markdown if needed and sanitize)
                raw_html = "".join(html_chunks)

                # Extract HTML if LLM wrapped it in markdown code blocks
                if "```html" in raw_html:
                    start = raw_html.find("```html") + 7
                    end = raw_html.find("```", start)
                    if end > start:
                        raw_html = raw_html[start:end].strip()
                elif "```" in raw_html:
                    start = raw_html.find("```") + 3
                    end = raw_html.find("```", start)
                    if end > start:
                        raw_html = raw_html[start:end].strip()

                # Sanitize HTML
                final_html = sanitize_html(raw_html)

                logger.info(
                    "Final HTML processed",
                    raw_length=len(raw_html),
                    sanitized_length=len(final_html),
                )

                # Phase 3: Send final result
                result = RenderResponse(html=final_html, display_prefs=current_prefs)
                yield f"event: result\ndata: {json.dumps(result.model_dump())}\n\n"

                logger.info("Dual streaming complete")

            except Exception as e:
                logger.error("Render stream failed", error=str(e), error_type=type(e).__name__)
                # Send error event in SSE format
                yield f'event: error\ndata: {json.dumps({"error": str(e)})}\n\n'

            finally:
                # Cleanup: close store client
                if store_client:
                    try:
                        store_client.__exit__(None, None, None)  # type: ignore[reportUnknownMemberType]  # noqa: E501
                    except Exception:
                        pass  # Ignore cleanup errors

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

            # Create store client for entire operation
            with MessageDBClient(db_config) as store_client:
                # Step 1: Handle user message (if provided)
                if request.user_message:
                    log.info("Processing user message")

                    # Write UserMessageAdded event
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
                        store_client=store_client,
                        llm_config=agent_llm_config,
                        auto_approve_tools=True,
                    )

                    log.info("Agent processing complete")

                # Step 2: Read all events from stream
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

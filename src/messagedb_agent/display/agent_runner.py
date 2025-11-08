"""Agent invocation logic for the display service.

This module handles running the agent processing loop in response to user messages.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import structlog

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.engine.loop import (
    _message_to_event,  # pyright: ignore[reportPrivateUsage]
    process_thread,
)
from messagedb_agent.events.agent import (
    LLM_CALL_FAILED,
    LLM_CALL_STARTED,
    LLM_RESPONSE_RECEIVED,
)
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_COMPLETED,
    TOOL_EXECUTION_FAILED,
    TOOL_EXECUTION_REQUESTED,
    TOOL_EXECUTION_STARTED,
)
from messagedb_agent.llm import (
    DEFAULT_SYSTEM_PROMPT,
    LLMError,
    create_llm_client,
)
from messagedb_agent.projections import (
    project_to_llm_context,
    project_to_next_step,
    project_to_tool_arguments,
)
from messagedb_agent.projections.next_step import StepType
from messagedb_agent.store import MessageDBClient, read_stream, write_message
from messagedb_agent.tools import (
    ToolRegistry,
    execute_tool,
    register_builtin_tools,
    registry_to_function_declarations,
)
from messagedb_agent.tools.display_tools import register_display_tools

logger = structlog.get_logger(__name__)


async def run_agent_step(
    thread_id: str,
    store_client: MessageDBClient,
    llm_config: VertexAIConfig,
    auto_approve_tools: bool = True,
) -> None:
    """Run one or more agent steps to process the latest user message.

    This runs the standard agent loop:
    1. Read events from stream
    2. Project to agent state/context
    3. Determine next step (LLM, tool, or done)
    4. Execute step and write result events
    5. Repeat until agent is done

    Args:
        thread_id: Unique identifier for the conversation thread
        store_client: Message DB client to use (shared with display service for
            real-time visibility)
        llm_config: LLM configuration for agent
        auto_approve_tools: Whether to automatically approve tool executions
            (default: True for API service)

    Raises:
        ProcessingError: If agent processing fails
    """
    log = logger.bind(thread_id=thread_id, auto_approve_tools=auto_approve_tools)
    log.info("Starting agent processing")

    stream_name = f"agent:v0-{thread_id}"

    # Create LLM client and tool registry (reuse provided store_client)
    llm_client = create_llm_client(llm_config)
    tool_registry = ToolRegistry()
    register_builtin_tools(tool_registry)
    register_display_tools(tool_registry, store_client, thread_id)

    # Run agent processing loop in thread pool to avoid blocking async event loop
    # This allows the polling loop to run concurrently and see events in real-time
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as executor:
        final_state = await loop.run_in_executor(
            executor,
            process_thread,
            thread_id,
            stream_name,
            store_client,
            llm_client,
            tool_registry,
            100,  # max_iterations
            auto_approve_tools,
        )

    log.info(
        "Agent processing complete",
        final_status=final_state.status.value,
        message_count=final_state.message_count,
        llm_call_count=final_state.llm_call_count,
        tool_call_count=final_state.tool_call_count,
    )


async def run_agent_step_streaming(
    thread_id: str,
    store_client: MessageDBClient,
    llm_config: VertexAIConfig,
    auto_approve_tools: bool = True,
) -> AsyncIterator[dict[str, Any]]:
    """Run agent steps with streaming LLM responses, yielding deltas in real-time.

    This implements the same agent loop as run_agent_step(), but streams LLM deltas
    as they arrive while buffering the complete response for MessageDB event storage.

    The function yields dictionaries representing different types of streaming updates:
    - LLM text deltas: {"type": "llm_text", "text": "..."}
    - LLM tool calls: {"type": "llm_tool_call", "name": "...", "id": "...", "index": N}
    - LLM tool input: {"type": "llm_tool_input", "index": N, "input": "..."}
    - LLM completion: {"type": "llm_done", "token_usage": {...}}
    - Tool progress: {"type": "tool_started", "name": "...", "id": "..."}
    - Tool results: {"type": "tool_completed", "name": "...", "id": "...", "result": ...}
    - Tool failures: {"type": "tool_failed", "name": "...", "id": "...", "error": "..."}

    Args:
        thread_id: Unique identifier for the conversation thread
        store_client: Message DB client to use
        llm_config: LLM configuration for agent
        auto_approve_tools: Whether to automatically approve tool executions

    Yields:
        Dictionary deltas representing streaming updates

    Example:
        async for delta in run_agent_step_streaming(thread_id, store, config):
            if delta["type"] == "llm_text":
                print(delta["text"], end="", flush=True)
            elif delta["type"] == "llm_tool_call":
                print(f"\\nCalling {delta['name']}...")
    """
    log = logger.bind(thread_id=thread_id, auto_approve_tools=auto_approve_tools)
    log.info("Starting streaming agent processing")

    stream_name = f"agent:v0-{thread_id}"

    # Create LLM client and tool registry
    llm_client = create_llm_client(llm_config)
    tool_registry = ToolRegistry()
    register_builtin_tools(tool_registry)
    register_display_tools(tool_registry, store_client, thread_id)

    # Process loop: continue until session terminates
    max_iterations = 100
    iteration = 0
    last_position = -1
    accumulated_events: list[BaseEvent] = []

    while iteration < max_iterations:
        iteration += 1
        log_iter = log.bind(iteration=iteration)
        log_iter.debug("Streaming loop iteration")

        # Step 1: Read events from stream
        messages = read_stream(store_client, stream_name, position=last_position + 1)
        new_events = [_message_to_event(msg) for msg in messages]
        accumulated_events.extend(new_events)

        if messages:
            last_position = max(msg.position for msg in messages)

        if not accumulated_events:
            log_iter.warning("No events in stream")
            break

        # Step 2: Determine next step
        step_type, step_metadata = project_to_next_step(accumulated_events)

        log_iter.info("Determined next step", step_type=step_type.value)

        # Step 3: Check for termination
        if step_type == StepType.TERMINATION:
            log_iter.info("Session terminated", reason=step_metadata.get("reason"))
            break

        # Step 4: Execute LLM step with streaming
        if step_type == StepType.LLM_CALL:
            log_iter.info("Executing streaming LLM step")

            # Project to LLM context
            context_messages = project_to_llm_context(accumulated_events)
            tools = registry_to_function_declarations(tool_registry)
            system_prompt = DEFAULT_SYSTEM_PROMPT

            # Write LLMCallStarted event
            try:
                write_message(
                    client=store_client,
                    stream_name=stream_name,
                    message_type=LLM_CALL_STARTED,
                    data={
                        "message_count": len(context_messages),
                        "tool_count": len(tools),
                        "system_prompt_length": len(system_prompt),
                    },
                    metadata={},
                )
                conn = store_client.get_connection()
                if not conn.autocommit:
                    conn.commit()
            except Exception as e:
                log_iter.error("Failed to write LLMCallStarted", error=str(e))
                break

            # Stream LLM call and buffer response
            try:
                # Buffer complete response
                buffered_text_chunks: list[str] = []
                buffered_tool_calls: dict[int, dict[str, Any]] = {}

                # Stream from LLM
                loop = asyncio.get_running_loop()
                with ThreadPoolExecutor() as executor:
                    stream_iter = await loop.run_in_executor(
                        executor,
                        llm_client.call_stream,
                        context_messages,
                        tools if tools else None,
                        system_prompt,
                    )

                    # Process deltas
                    for delta in stream_iter:
                        if delta.delta_type == "text":
                            # Yield text delta
                            yield {"type": "llm_text", "text": delta.text}
                            buffered_text_chunks.append(delta.text or "")

                        elif delta.delta_type == "tool_call":
                            # Yield tool call delta
                            yield {
                                "type": "llm_tool_call",
                                "name": delta.tool_name,
                                "id": delta.tool_call_id,
                                "index": delta.tool_call_index,
                            }
                            # Buffer tool call
                            buffered_tool_calls[delta.tool_call_index or 0] = {
                                "id": delta.tool_call_id,
                                "name": delta.tool_name,
                                "input_chunks": [],
                            }

                        elif delta.delta_type == "tool_input":
                            # Yield tool input delta
                            yield {
                                "type": "llm_tool_input",
                                "index": delta.tool_call_index,
                                "input": delta.tool_input_delta,
                            }
                            # Buffer tool input
                            idx = delta.tool_call_index or 0
                            if idx in buffered_tool_calls:
                                buffered_tool_calls[idx]["input_chunks"].append(
                                    delta.tool_input_delta or ""
                                )

                        elif delta.delta_type in ("usage", "done"):
                            # Yield final usage
                            yield {"type": "llm_done", "token_usage": delta.token_usage}

                # Parse buffered tool calls
                parsed_tool_calls: list[dict[str, Any]] = []
                for idx in sorted(buffered_tool_calls.keys()):
                    tc = buffered_tool_calls[idx]
                    input_json = "".join(tc["input_chunks"])
                    try:
                        arguments: dict[str, Any] = json.loads(input_json) if input_json else {}
                    except json.JSONDecodeError:
                        log_iter.warning(
                            "Failed to parse tool input JSON",
                            tool_name=tc["name"],
                            input_json=input_json,
                        )
                        arguments = {}

                    parsed_tool_calls.append(
                        {"id": tc["id"], "name": tc["name"], "arguments": arguments}
                    )

                # Write LLMResponseReceived event
                buffered_text = "".join(buffered_text_chunks)
                event_data: dict[str, Any] = {
                    "response_text": buffered_text,
                    "tool_calls": parsed_tool_calls,
                    "model_name": llm_client.model_name,
                    "token_usage": {},  # Token usage from last delta
                }

                write_message(
                    client=store_client,
                    stream_name=stream_name,
                    message_type=LLM_RESPONSE_RECEIVED,
                    data=event_data,
                    metadata={},
                )
                conn = store_client.get_connection()
                if not conn.autocommit:
                    conn.commit()

                log_iter.info("LLM response buffered and written to stream")

            except LLMError as e:
                log_iter.error("LLM call failed", error=str(e))
                # Write failure event
                write_message(
                    client=store_client,
                    stream_name=stream_name,
                    message_type=LLM_CALL_FAILED,
                    data={"error_message": str(e), "retry_count": 0},
                    metadata={},
                )
                break

        # Step 5: Execute tool step with progress updates
        elif step_type == StepType.TOOL_EXECUTION:
            log_iter.info("Executing tool step with progress")

            # Get tool calls from events
            tool_calls = project_to_tool_arguments(accumulated_events)

            for i, tool_call in enumerate(tool_calls):
                tool_name = tool_call.get("name", "unknown")
                tool_id = tool_call.get("id", f"call_{i}")
                arguments = tool_call.get("arguments", {})

                # Write ToolExecutionRequested event
                write_message(
                    client=store_client,
                    stream_name=stream_name,
                    message_type=TOOL_EXECUTION_REQUESTED,
                    data={"tool_name": tool_name, "arguments": arguments},
                    metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                )

                # Check approval (simplified for auto_approve_tools mode)
                if auto_approve_tools or not tool_registry.has(tool_name):
                    # Write ToolExecutionStarted event
                    write_message(
                        client=store_client,
                        stream_name=stream_name,
                        message_type=TOOL_EXECUTION_STARTED,
                        data={"tool_name": tool_name, "arguments": arguments},
                        metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                    )
                    conn = store_client.get_connection()
                    if not conn.autocommit:
                        conn.commit()

                    # Yield tool started
                    yield {"type": "tool_started", "name": tool_name, "id": tool_id}

                    # Execute tool
                    loop = asyncio.get_running_loop()
                    with ThreadPoolExecutor() as executor:
                        result = await loop.run_in_executor(
                            executor, execute_tool, tool_name, arguments, tool_registry
                        )

                    # Write result and yield
                    if result.success:
                        write_message(
                            client=store_client,
                            stream_name=stream_name,
                            message_type=TOOL_EXECUTION_COMPLETED,
                            data={
                                "tool_name": tool_name,
                                "result": result.result,
                                "execution_time_ms": result.execution_time_ms,
                            },
                            metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                        )
                        yield {
                            "type": "tool_completed",
                            "name": tool_name,
                            "id": tool_id,
                            "result": result.result,
                        }
                    else:
                        write_message(
                            client=store_client,
                            stream_name=stream_name,
                            message_type=TOOL_EXECUTION_FAILED,
                            data={
                                "tool_name": tool_name,
                                "error_message": result.error or "Unknown error",
                                "retry_count": 0,
                            },
                            metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                        )
                        yield {
                            "type": "tool_failed",
                            "name": tool_name,
                            "id": tool_id,
                            "error": result.error or "Unknown error",
                        }

    log.info("Streaming agent processing complete", iterations=iteration)

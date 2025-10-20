"""LLM step execution for the processing engine.

This module implements the LLM step, which:
1. Projects events to LLM context (conversation history)
2. Retrieves tool declarations from the registry
3. Calls the LLM with context and tools
4. Writes success (LLMResponseReceived) or failure (LLMCallFailed) events

The LLM step is one of the three core step types in the processing loop.
"""

from typing import Any

import structlog

from messagedb_agent.events.agent import LLM_CALL_FAILED, LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.llm import (
    DEFAULT_SYSTEM_PROMPT,
    BaseLLMClient,
    LLMError,
)
from messagedb_agent.projections import project_to_llm_context
from messagedb_agent.store import MessageDBClient, write_message
from messagedb_agent.tools import ToolRegistry, registry_to_function_declarations

logger = structlog.get_logger(__name__)


class LLMStepError(Exception):
    """Raised when LLM step execution encounters an error."""

    pass


def execute_llm_step(
    events: list[BaseEvent],
    llm_client: BaseLLMClient,
    tool_registry: ToolRegistry,
    stream_name: str,
    store_client: MessageDBClient,
    system_prompt: str | None = None,
    max_retries: int = 2,
) -> bool:
    """Execute an LLM step in the processing loop.

    This function:
    1. Projects events to LLM context messages
    2. Gets tool declarations from the registry
    3. Calls the LLM with context, tools, and system prompt
    4. Writes LLMResponseReceived event on success
    5. Writes LLMCallFailed event on failure (with retries)

    Args:
        events: List of events from the stream (for projection)
        llm_client: LLM client to use for the call
        tool_registry: Registry of available tools
        stream_name: Stream name to write result events to
        store_client: MessageDB client for writing events
        system_prompt: System prompt to use (defaults to DEFAULT_SYSTEM_PROMPT)
        max_retries: Maximum number of retry attempts on failure (default: 2)

    Returns:
        True if LLM call succeeded and event written, False if failed after retries

    Raises:
        LLMStepError: If event writing fails or other critical error occurs

    Example:
        ```python
        from messagedb_agent.engine.steps.llm import execute_llm_step
        from messagedb_agent.store import read_stream
        from messagedb_agent.engine.loop import _message_to_event

        # Read events and convert to BaseEvent
        messages = read_stream(store_client, stream_name)
        events = [_message_to_event(msg) for msg in messages]

        # Execute LLM step
        success = execute_llm_step(
            events=events,
            llm_client=llm_client,
            tool_registry=tool_registry,
            stream_name=stream_name,
            store_client=store_client
        )

        if success:
            print("LLM response written to stream")
        else:
            print("LLM call failed after retries")
        ```
    """
    log = logger.bind(
        stream_name=stream_name,
        event_count=len(events),
        max_retries=max_retries,
    )

    log.info("Executing LLM step")

    # Step 1: Project events to LLM context
    messages = project_to_llm_context(events)
    log.debug("Projected events to LLM context", message_count=len(messages))

    # Step 2: Get tool declarations from registry
    tools = registry_to_function_declarations(tool_registry)
    log.debug("Retrieved tool declarations", tool_count=len(tools))

    # Step 3: Use provided system prompt or default
    prompt = system_prompt if system_prompt is not None else DEFAULT_SYSTEM_PROMPT

    # Step 4: Call LLM with retries
    retry_count = 0
    last_error: Exception | None = None

    while retry_count <= max_retries:
        try:
            log_retry = log.bind(retry_count=retry_count)
            log_retry.debug("Calling LLM")

            # Call the LLM
            response = llm_client.call(
                messages=messages,
                tools=tools if tools else None,  # Only pass tools if registry has any
                system_prompt=prompt,
            )

            log_retry.info(
                "LLM call succeeded",
                response_text_length=len(response.text or ""),
                tool_call_count=len(response.tool_calls or []),
                model=response.model_name,
            )

            # Step 5: Write LLMResponseReceived event
            event_data: dict[str, Any] = {
                "response_text": response.text or "",
                "tool_calls": [
                    {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                    for tc in (response.tool_calls or [])
                ],
                "model_name": response.model_name,
                "token_usage": response.token_usage or {},
            }

            try:
                position = write_message(
                    client=store_client,
                    stream_name=stream_name,
                    message_type=LLM_RESPONSE_RECEIVED,
                    data=event_data,
                    metadata={"retry_count": retry_count},
                )
                log_retry.info("LLMResponseReceived event written", position=position)
                return True

            except Exception as e:
                log_retry.error("Failed to write LLMResponseReceived event", error=str(e))
                raise LLMStepError(f"Failed to write success event: {e}") from e

        except LLMError as e:
            # LLM-specific error (API error, response parsing error, etc.)
            last_error = e
            retry_count += 1

            log_retry = log.bind(retry_count=retry_count, error_type=type(e).__name__)
            log_retry.warning("LLM call failed", error=str(e))

            # If we've exhausted retries, write failure event
            if retry_count > max_retries:
                log_retry.error("LLM call failed after all retries", total_attempts=retry_count)

                # Write LLMCallFailed event
                # retry_count - 1 because first attempt doesn't count as a retry
                failure_data = {
                    "error_message": str(e),
                    "retry_count": retry_count - 1,
                }

                try:
                    position = write_message(
                        client=store_client,
                        stream_name=stream_name,
                        message_type=LLM_CALL_FAILED,
                        data=failure_data,
                        metadata={"error_type": type(e).__name__},
                    )
                    log_retry.info("LLMCallFailed event written", position=position)
                    return False

                except Exception as write_error:
                    log_retry.error("Failed to write LLMCallFailed event", error=str(write_error))
                    raise LLMStepError(
                        f"Failed to write failure event: {write_error}"
                    ) from write_error

            # Otherwise, continue to next retry
            log_retry.debug("Retrying LLM call")

    # Should never reach here, but just in case
    assert last_error is not None
    raise LLMStepError(f"LLM call failed after {retry_count} retries: {last_error}")

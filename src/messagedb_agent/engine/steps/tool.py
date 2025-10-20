"""Tool step execution for the processing engine.

This module implements the tool step, which:
1. Projects events to extract tool calls from the last LLM response
2. For each tool call:
   - Writes ToolExecutionRequested event
   - Executes the tool
   - Writes ToolExecutionCompleted or ToolExecutionFailed event
3. Returns overall success status

The tool step is one of the three core step types in the processing loop.
"""

import structlog

from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_COMPLETED,
    TOOL_EXECUTION_FAILED,
    TOOL_EXECUTION_REQUESTED,
)
from messagedb_agent.projections import project_to_tool_arguments
from messagedb_agent.store import MessageDBClient, write_message
from messagedb_agent.tools import ToolRegistry, execute_tool

logger = structlog.get_logger(__name__)


class ToolStepError(Exception):
    """Raised when tool step execution encounters an error."""

    pass


def execute_tool_step(
    events: list[BaseEvent],
    tool_registry: ToolRegistry,
    stream_name: str,
    store_client: MessageDBClient,
) -> bool:
    """Execute a tool step in the processing loop.

    This function:
    1. Projects events to extract tool calls from the last LLM response
    2. For each tool call:
       - Writes ToolExecutionRequested event
       - Executes the tool using the registry
       - Writes ToolExecutionCompleted (success) or ToolExecutionFailed (failure) event
    3. Returns True if all tools executed successfully, False if any failed

    Args:
        events: List of events from the stream (for projection)
        tool_registry: Registry of available tools
        stream_name: Stream name to write result events to
        store_client: MessageDB client for writing events

    Returns:
        True if all tool executions succeeded, False if any failed

    Raises:
        ToolStepError: If event writing fails or other critical error occurs

    Example:
        ```python
        from messagedb_agent.engine.steps.tool import execute_tool_step
        from messagedb_agent.store import read_stream
        from messagedb_agent.engine.loop import _message_to_event

        # Read events and convert to BaseEvent
        messages = read_stream(store_client, stream_name)
        events = [_message_to_event(msg) for msg in messages]

        # Execute tool step
        success = execute_tool_step(
            events=events,
            tool_registry=tool_registry,
            stream_name=stream_name,
            store_client=store_client
        )

        if success:
            print("All tools executed successfully")
        else:
            print("Some tools failed")
        ```
    """
    log = logger.bind(
        stream_name=stream_name,
        event_count=len(events),
    )

    log.info("Executing tool step")

    # Step 1: Project events to get tool calls
    tool_calls = project_to_tool_arguments(events)
    log.debug("Projected tool calls from events", tool_call_count=len(tool_calls))

    if not tool_calls:
        log.warning("No tool calls found in events")
        return True  # No tools to execute is considered success

    # Step 2: Execute each tool call
    all_successful = True

    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call.get("name", "unknown")
        tool_id = tool_call.get("id", f"call_{i}")
        arguments = tool_call.get("arguments", {})

        log_tool = log.bind(
            tool_name=tool_name,
            tool_id=tool_id,
            tool_index=i,
        )

        log_tool.info("Processing tool call")

        # Step 2a: Write ToolExecutionRequested event
        try:
            requested_position = write_message(
                client=store_client,
                stream_name=stream_name,
                message_type=TOOL_EXECUTION_REQUESTED,
                data={
                    "tool_name": tool_name,
                    "arguments": arguments,
                },
                metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
            )
            log_tool.debug(
                "ToolExecutionRequested event written",
                position=requested_position,
            )
        except Exception as e:
            log_tool.error("Failed to write ToolExecutionRequested event", error=str(e))
            raise ToolStepError(f"Failed to write requested event for {tool_name}: {e}") from e

        # Step 2b: Execute the tool
        log_tool.debug("Executing tool", arguments=arguments)
        result = execute_tool(tool_name, arguments, tool_registry)

        # Step 2c: Write success or failure event based on result
        if result.success:
            log_tool.info(
                "Tool execution succeeded",
                execution_time_ms=result.execution_time_ms,
            )

            # Write ToolExecutionCompleted event
            try:
                completed_position = write_message(
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
                log_tool.info(
                    "ToolExecutionCompleted event written",
                    position=completed_position,
                )
            except Exception as e:
                log_tool.error("Failed to write ToolExecutionCompleted event", error=str(e))
                raise ToolStepError(f"Failed to write completed event for {tool_name}: {e}") from e

        else:
            # Tool execution failed
            all_successful = False
            log_tool.warning(
                "Tool execution failed",
                error=result.error,
                execution_time_ms=result.execution_time_ms,
            )

            # Write ToolExecutionFailed event
            try:
                failed_position = write_message(
                    client=store_client,
                    stream_name=stream_name,
                    message_type=TOOL_EXECUTION_FAILED,
                    data={
                        "tool_name": tool_name,
                        "error_message": result.error or "Unknown error",
                        "retry_count": 0,  # No retries in basic implementation
                    },
                    metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                )
                log_tool.info(
                    "ToolExecutionFailed event written",
                    position=failed_position,
                )
            except Exception as e:
                log_tool.error("Failed to write ToolExecutionFailed event", error=str(e))
                raise ToolStepError(f"Failed to write failed event for {tool_name}: {e}") from e

    # Return overall success status
    log.info(
        "Tool step complete",
        total_tools=len(tool_calls),
        all_successful=all_successful,
    )
    return all_successful

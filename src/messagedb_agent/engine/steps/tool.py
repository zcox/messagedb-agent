"""Tool step execution for the processing engine.

This module implements the tool step, which:
1. Projects events to extract tool calls from the last LLM response
2. For each tool call:
   - Writes ToolExecutionRequested event
   - Checks if tool requires approval based on permission level
   - If approval required and not auto-approve mode:
     - Writes approval/rejection event (based on config for now)
   - Executes the tool if approved
   - Writes ToolExecutionCompleted or ToolExecutionFailed event
3. Returns overall success status

The tool step is one of the three core step types in the processing loop.
"""

import time

import structlog

from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_APPROVED,
    TOOL_EXECUTION_COMPLETED,
    TOOL_EXECUTION_FAILED,
    TOOL_EXECUTION_REJECTED,
    TOOL_EXECUTION_REQUESTED,
    TOOL_EXECUTION_STARTED,
)
from messagedb_agent.output import print_tool_result
from messagedb_agent.projections import project_to_tool_arguments
from messagedb_agent.store import MessageDBClient, read_stream, write_message
from messagedb_agent.tools import PermissionLevel, ToolRegistry, execute_tool

logger = structlog.get_logger(__name__)


class ToolStepError(Exception):
    """Raised when tool step execution encounters an error."""

    pass


def execute_tool_step(
    events: list[BaseEvent],
    tool_registry: ToolRegistry,
    stream_name: str,
    store_client: MessageDBClient,
    auto_approve_tools: bool = False,
) -> bool:
    """Execute a tool step in the processing loop.

    This function:
    1. Projects events to extract tool calls from the last LLM response
    2. For each tool call:
       - Writes ToolExecutionRequested event
       - Checks if tool requires approval based on permission level
       - Handles approval (auto-approve or reject based on config)
       - Executes the tool if approved using the registry
       - Writes ToolExecutionCompleted (success) or ToolExecutionFailed (failure) event
    3. Returns True if all tools executed successfully, False if any failed

    Args:
        events: List of events from the stream (for projection)
        tool_registry: Registry of available tools
        stream_name: Stream name to write result events to
        store_client: MessageDB client for writing events
        auto_approve_tools: Whether to automatically approve all tool executions
            (default: False)

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
            store_client=store_client,
            auto_approve_tools=True
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
        auto_approve_tools=auto_approve_tools,
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

        # Step 2b: Check if tool requires approval (if tool exists)
        # If tool doesn't exist, it will fail during execution anyway
        requires_approval = False
        if tool_registry.has(tool_name):
            tool_obj = tool_registry.get(tool_name)
            permission_level = tool_obj.permission_level
            requires_approval = permission_level in (
                PermissionLevel.REQUIRES_APPROVAL,
                PermissionLevel.DANGEROUS,
            )

            log_tool.debug(
                "Checking tool permission level",
                permission_level=permission_level.value,
                requires_approval=requires_approval,
            )
        else:
            log_tool.warning("Tool not found in registry, will fail during execution")

        # Step 2c: Handle approval
        approved = True  # Default to approved for SAFE tools
        if requires_approval:
            if auto_approve_tools:
                # Auto-approve mode: approve all tools
                log_tool.info("Auto-approving tool execution (auto_approve_tools=True)")
                try:
                    write_message(
                        client=store_client,
                        stream_name=stream_name,
                        message_type=TOOL_EXECUTION_APPROVED,
                        data={
                            "tool_name": tool_name,
                            "approved_by": "auto",
                        },
                        metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                    )
                except Exception as e:
                    log_tool.error("Failed to write ToolExecutionApproved event", error=str(e))
                    raise ToolStepError(
                        f"Failed to write approved event for {tool_name}: {e}"
                    ) from e
            else:
                # Manual approval required - wait for user to approve/reject via TUI
                log_tool.info("Waiting for user approval via TUI")

                # Poll for approval or rejection event
                # We'll check the stream every 500ms for up to 5 minutes (600 iterations)
                max_poll_iterations = 600
                poll_interval_seconds = 0.5
                approval_received = False

                for _poll_iteration in range(max_poll_iterations):
                    # Read stream to check for new approval/rejection events
                    messages = read_stream(store_client, stream_name)

                    # Look for approval or rejection events that match this tool
                    for msg in messages:
                        # Check if this is an approval event for our tool
                        if msg.type == TOOL_EXECUTION_APPROVED:
                            msg_tool_name = msg.data.get("tool_name", "")
                            # Match by tool_id in metadata or tool_name
                            msg_tool_id = msg.metadata.get("tool_id") if msg.metadata else None
                            if msg_tool_name == tool_name or msg_tool_id == tool_id:
                                log_tool.info("User approved tool execution")
                                approved = True
                                approval_received = True
                                break

                        # Check if this is a rejection event for our tool
                        elif msg.type == TOOL_EXECUTION_REJECTED:
                            msg_tool_name = msg.data.get("tool_name", "")
                            msg_tool_id = msg.metadata.get("tool_id") if msg.metadata else None
                            if msg_tool_name == tool_name or msg_tool_id == tool_id:
                                log_tool.info("User rejected tool execution")
                                approved = False
                                approval_received = True
                                break

                    if approval_received:
                        break

                    # Sleep before next poll
                    time.sleep(poll_interval_seconds)

                # If no approval received after timeout, reject
                if not approval_received:
                    log_tool.warning("Approval timeout - rejecting tool execution")
                    approved = False
                    try:
                        write_message(
                            client=store_client,
                            stream_name=stream_name,
                            message_type=TOOL_EXECUTION_REJECTED,
                            data={
                                "tool_name": tool_name,
                                "rejected_by": "system",
                                "reason": "Approval timeout",
                            },
                            metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                        )
                    except Exception as e:
                        log_tool.error("Failed to write timeout rejection event", error=str(e))
                        raise ToolStepError(
                            f"Failed to write timeout rejection for {tool_name}: {e}"
                        ) from e

        # Step 2d: Execute tool if approved, otherwise write failure
        if not approved:
            # Tool was rejected, write failure event
            all_successful = False
            log_tool.warning("Tool execution rejected by permission system")

            # Print rejection to user
            print_tool_result(
                tool_name=tool_name,
                success=False,
                error="Tool execution rejected by user or permission system",
                execution_time_ms=0,
            )

            # Write ToolExecutionFailed event
            try:
                write_message(
                    client=store_client,
                    stream_name=stream_name,
                    message_type=TOOL_EXECUTION_FAILED,
                    data={
                        "tool_name": tool_name,
                        "error_message": "Tool execution rejected by permission system",
                        "retry_count": 0,
                    },
                    metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
                )
            except Exception as e:
                log_tool.error("Failed to write ToolExecutionFailed event", error=str(e))
                raise ToolStepError(f"Failed to write failed event for {tool_name}: {e}") from e
            continue  # Skip to next tool

        # Tool is approved, write ToolExecutionStarted event and then execute it
        try:
            write_message(
                client=store_client,
                stream_name=stream_name,
                message_type=TOOL_EXECUTION_STARTED,
                data={
                    "tool_name": tool_name,
                    "arguments": arguments,
                },
                metadata={"tool_id": tool_id, "tool_call_id": tool_id, "tool_index": i},
            )
            # Explicitly commit to ensure event is visible to other connections immediately
            conn = store_client.get_connection()
            if not conn.autocommit:
                conn.commit()
            log_tool.info("ToolExecutionStarted event written and committed")
        except Exception as e:
            log_tool.error("Failed to write ToolExecutionStarted event", error=str(e))
            raise ToolStepError(f"Failed to write started event for {tool_name}: {e}") from e

        log_tool.debug("Executing tool", arguments=arguments)
        result = execute_tool(tool_name, arguments, tool_registry)

        # Step 2c: Print and write success or failure event based on result
        if result.success:
            log_tool.info(
                "Tool execution succeeded",
                execution_time_ms=result.execution_time_ms,
            )

            # Print tool result to user
            print_tool_result(
                tool_name=tool_name,
                success=True,
                result=result.result,
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

            # Print tool failure to user
            print_tool_result(
                tool_name=tool_name,
                success=False,
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

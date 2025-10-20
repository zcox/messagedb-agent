"""Next Step projection for determining the next processing step.

This module provides projection functions that analyze event streams to determine
what the processing engine should do next. The projection implements the core
decision logic for the event-driven processing loop.

The projection follows the Last Event Pattern from the specification:
- The most recent event typically determines the next action
- Specific event types trigger specific step types
- This enables simple, deterministic state transitions

Step Types:
- LLM_CALL: Call the LLM with current context
- TOOL_EXECUTION: Execute tool calls from LLM response
- TERMINATION: End the session

Example:
    >>> from messagedb_agent.store import read_stream
    >>> from messagedb_agent.projections import project_to_next_step
    >>>
    >>> # Read events from a stream
    >>> events = read_stream(client, "agent:v0-thread123")
    >>>
    >>> # Determine next step
    >>> step_type, metadata = project_to_next_step(events)
    >>>
    >>> if step_type == StepType.LLM_CALL:
    ...     # Call LLM with projected context
    ...     pass
    >>> elif step_type == StepType.TOOL_EXECUTION:
    ...     # Execute tools from metadata
    ...     pass
    >>> elif step_type == StepType.TERMINATION:
    ...     # End session
    ...     pass
"""

from enum import Enum
from typing import Any

from messagedb_agent.events.agent import LLM_CALL_FAILED, LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.system import SESSION_COMPLETED
from messagedb_agent.events.tool import TOOL_EXECUTION_COMPLETED, TOOL_EXECUTION_FAILED
from messagedb_agent.events.user import SESSION_TERMINATION_REQUESTED, USER_MESSAGE_ADDED


class StepType(Enum):
    """Types of processing steps in the agent loop.

    Attributes:
        LLM_CALL: Call the LLM to generate a response
        TOOL_EXECUTION: Execute one or more tool calls
        TERMINATION: End the session
    """

    LLM_CALL = "llm_call"
    TOOL_EXECUTION = "tool_execution"
    TERMINATION = "termination"


def project_to_next_step(events: list[BaseEvent]) -> tuple[StepType, dict[str, Any]]:
    """Project event stream to determine the next processing step.

    This function implements the Last Event Pattern: the most recent event
    determines what action the processing engine should take next.

    Decision Logic (from most recent event):
    - UserMessageAdded -> LLM_CALL (process user's message)
    - LLMResponseReceived with tool_calls -> TOOL_EXECUTION (execute tools)
    - LLMResponseReceived without tool_calls -> TERMINATION (response complete)
    - LLMCallFailed -> TERMINATION (LLM call failed after retries)
    - ToolExecutionCompleted -> LLM_CALL (process tool results)
    - ToolExecutionFailed -> TERMINATION (tool execution failed)
    - SessionTerminationRequested -> TERMINATION (end session)
    - SessionCompleted -> TERMINATION (already ended)

    Args:
        events: List of events from the event stream in chronological order

    Returns:
        Tuple of (StepType, metadata dict) where metadata contains:
        - For LLM_CALL: {"reason": str} explaining why LLM call is needed
        - For TOOL_EXECUTION: {"tool_calls": list} with tool calls to execute
        - For TERMINATION: {"reason": str} explaining termination reason

    Raises:
        ValueError: If event list is empty (no events to process)

    Example:
        >>> events = [
        ...     BaseEvent(type="UserMessageAdded", data={"message": "Hello"}, ...),
        ... ]
        >>> step_type, metadata = project_to_next_step(events)
        >>> step_type == StepType.LLM_CALL
        True
        >>> metadata["reason"]
        'user_message_added'
    """
    if not events:
        raise ValueError("Cannot determine next step from empty event list")

    # Get the last event
    last_event = events[-1]

    # Check event type and determine next step
    if last_event.type == USER_MESSAGE_ADDED:
        # User sent a message, need to call LLM to generate response
        return (StepType.LLM_CALL, {"reason": "user_message_added"})

    elif last_event.type == LLM_RESPONSE_RECEIVED:
        # LLM generated a response, check if it contains tool calls
        data: dict[str, Any] = last_event.data
        tool_calls = data.get("tool_calls", [])

        if tool_calls and len(tool_calls) > 0:
            # LLM requested tool calls, execute them
            return (
                StepType.TOOL_EXECUTION,
                {"tool_calls": tool_calls, "reason": "llm_requested_tools"},
            )
        else:
            # LLM generated final text response, session complete
            return (
                StepType.TERMINATION,
                {"reason": "llm_response_complete"},
            )

    elif last_event.type == LLM_CALL_FAILED:
        # LLM call failed after all retries, terminate session
        data = last_event.data
        error_message = data.get("error_message", "Unknown error")
        return (StepType.TERMINATION, {"reason": f"llm_call_failed: {error_message}"})

    elif last_event.type == TOOL_EXECUTION_COMPLETED:
        # Tool execution finished, call LLM to process results
        return (StepType.LLM_CALL, {"reason": "tool_execution_completed"})

    elif last_event.type == TOOL_EXECUTION_FAILED:
        # Tool execution failed, terminate session
        data = last_event.data
        error_message = data.get("error_message", "Unknown error")
        tool_name = data.get("tool_name", "unknown_tool")
        return (
            StepType.TERMINATION,
            {"reason": f"tool_execution_failed: {tool_name} - {error_message}"},
        )

    elif last_event.type == SESSION_TERMINATION_REQUESTED:
        # User requested termination
        data = last_event.data
        reason = data.get("reason", "user_requested")
        return (StepType.TERMINATION, {"reason": reason})

    elif last_event.type == SESSION_COMPLETED:
        # Session already completed
        data = last_event.data
        reason = data.get("completion_reason", "session_already_completed")
        return (StepType.TERMINATION, {"reason": reason})

    else:
        # Unknown event type or no specific action needed
        # Default to LLM_CALL to continue processing
        return (
            StepType.LLM_CALL,
            {"reason": "unknown_event_type", "event_type": last_event.type},
        )


def should_terminate(events: list[BaseEvent]) -> bool:
    """Check if the session should terminate based on events.

    This is a convenience function that checks if the next step is TERMINATION.

    Args:
        events: List of events from the event stream

    Returns:
        True if session should terminate, False otherwise

    Example:
        >>> events = [...]
        >>> if should_terminate(events):
        ...     # Clean up and exit
        ...     pass
    """
    if not events:
        return False

    try:
        step_type, _ = project_to_next_step(events)
        return step_type == StepType.TERMINATION
    except ValueError:
        return False


def get_pending_tool_calls(events: list[BaseEvent]) -> list[dict[str, Any]]:
    """Extract pending tool calls from the most recent LLM response.

    This is a convenience function for getting tool calls that need to be executed.
    It only returns tool calls if the next step is TOOL_EXECUTION.

    Args:
        events: List of events from the event stream

    Returns:
        List of tool call dicts if TOOL_EXECUTION is next, empty list otherwise

    Example:
        >>> events = [...]
        >>> tool_calls = get_pending_tool_calls(events)
        >>> for tc in tool_calls:
        ...     execute_tool(tc["name"], tc["arguments"])
    """
    if not events:
        return []

    try:
        step_type, metadata = project_to_next_step(events)
        if step_type == StepType.TOOL_EXECUTION:
            return metadata.get("tool_calls", [])
        return []
    except ValueError:
        return []


def count_steps_taken(events: list[BaseEvent]) -> dict[str, int]:
    """Count how many times each step type has been executed.

    This analyzes the event stream to count LLM calls and tool executions,
    useful for monitoring and debugging.

    Args:
        events: List of events from the event stream

    Returns:
        Dict with counts: {"llm_calls": int, "tool_executions": int}

    Example:
        >>> events = [...]
        >>> counts = count_steps_taken(events)
        >>> print(f"LLM called {counts['llm_calls']} times")
    """
    llm_calls = sum(1 for e in events if e.type == LLM_RESPONSE_RECEIVED)
    tool_executions = sum(1 for e in events if e.type == TOOL_EXECUTION_COMPLETED)

    return {"llm_calls": llm_calls, "tool_executions": tool_executions}

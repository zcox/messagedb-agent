"""LLM Context projection for converting events to conversation messages.

This module provides projection functions that transform event streams into
conversation messages suitable for LLM APIs. The projection converts domain
events (UserMessageAdded, LLMResponseReceived, ToolExecutionCompleted) into
the Message format expected by LLM clients.

The projection is a pure function that:
- Filters out system/metadata events not relevant to LLM context
- Converts events to chronologically ordered messages
- Preserves conversation flow and tool calling sequences
- Returns messages in the format expected by BaseLLMClient.call()

Example:
    >>> from messagedb_agent.store import read_stream
    >>> from messagedb_agent.projections import project_to_llm_context
    >>>
    >>> # Read events from a stream
    >>> events = read_stream(client, "agent:v0-thread123")
    >>>
    >>> # Project to LLM context
    >>> messages = project_to_llm_context(events)
    >>>
    >>> # Use with LLM client
    >>> response = llm_client.call(messages, tools, system_prompt)
"""

import json
from typing import Any, cast

from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.tool import TOOL_EXECUTION_COMPLETED
from messagedb_agent.events.user import USER_MESSAGE_ADDED
from messagedb_agent.llm.base import Message, ToolCall


def project_to_llm_context(events: list[BaseEvent]) -> list[Message]:
    """Project event stream to LLM conversation context.

    This function converts domain events into the Message format expected by
    LLM clients. It filters and transforms events in chronological order:

    - UserMessageAdded -> user message with text
    - LLMResponseReceived -> assistant message with text and/or tool calls
    - ToolExecutionCompleted -> tool result message

    System events (SessionStarted, SessionCompleted, etc.) are filtered out
    as they are not relevant to the LLM conversation context.

    Args:
        events: List of events from the event stream in chronological order

    Returns:
        List of Message objects suitable for LLM client.call()

    Example:
        >>> events = [
        ...     BaseEvent(type="UserMessageAdded", data={"message": "Hello", ...}, ...),
        ...     BaseEvent(type="LLMResponseReceived", data={"response_text": "Hi!", ...}, ...),
        ... ]
        >>> messages = project_to_llm_context(events)
        >>> len(messages)
        2
        >>> messages[0].role
        'user'
        >>> messages[1].role
        'assistant'
    """
    messages: list[Message] = []

    for event in events:
        if event.type == USER_MESSAGE_ADDED:
            # Convert user message event to user message
            message = _convert_user_message(event)
            if message:
                messages.append(message)

        elif event.type == LLM_RESPONSE_RECEIVED:
            # Convert LLM response event to assistant message
            message = _convert_llm_response(event)
            if message:
                messages.append(message)

        elif event.type == TOOL_EXECUTION_COMPLETED:
            # Convert tool execution event to tool result message
            message = _convert_tool_result(event)
            if message:
                messages.append(message)

        # Skip all other event types (SessionStarted, SessionCompleted, etc.)

    return messages


def _convert_user_message(event: BaseEvent) -> Message | None:
    """Convert UserMessageAdded event to user Message.

    Args:
        event: UserMessageAdded event

    Returns:
        Message with role="user" and text from event data, or None if invalid
    """
    try:
        message_text = event.data.get("message")
        if not message_text:
            return None

        return Message(role="user", text=str(message_text))
    except (KeyError, AttributeError, ValueError):
        # If event data is malformed, skip it
        return None


def _convert_llm_response(event: BaseEvent) -> Message | None:
    """Convert LLMResponseReceived event to assistant Message.

    Args:
        event: LLMResponseReceived event

    Returns:
        Message with role="assistant", text, and/or tool_calls, or None if invalid
    """
    try:
        data: dict[str, Any] = event.data
        response_text: str = str(data.get("response_text", ""))
        tool_calls_data = data.get("tool_calls", [])

        # Convert tool call data to ToolCall objects
        tool_calls: list[ToolCall] = []
        for tc_data in tool_calls_data:
            if isinstance(tc_data, dict):
                tc_data_typed = cast(dict[str, Any], tc_data)
                tc_id: str = str(tc_data_typed.get("id", ""))
                tc_name: str = str(tc_data_typed.get("name", ""))
                tc_args: dict[str, Any] = cast(dict[str, Any], tc_data_typed.get("arguments", {}))
                tool_call = ToolCall(
                    id=tc_id,
                    name=tc_name,
                    arguments=tc_args,
                )
                tool_calls.append(tool_call)

        # Create message with text and/or tool calls
        # Text might be empty if only tool calls
        text = response_text if response_text and response_text.strip() else None

        # Must have either text or tool calls
        if not text and not tool_calls:
            return None

        return Message(role="assistant", text=text, tool_calls=tool_calls or None)
    except (KeyError, AttributeError, ValueError):
        # If event data is malformed, skip it
        return None


def _convert_tool_result(event: BaseEvent) -> Message | None:
    """Convert ToolExecutionCompleted event to tool result Message.

    Args:
        event: ToolExecutionCompleted event

    Returns:
        Message with role="tool", tool result data, or None if invalid
    """
    try:
        tool_name = event.data.get("tool_name")
        result = event.data.get("result")

        if not tool_name:
            return None

        # Find the corresponding tool call ID from metadata or generate one
        # The tool_call_id should match the ID from the LLM's tool call
        # For now, we'll look in metadata or use tool_name as fallback
        tool_call_id = event.metadata.get("tool_call_id", tool_name)

        # Convert result to string format
        # If result is already a string, use it; otherwise JSON serialize it
        if isinstance(result, str):
            result_text = result
        else:
            result_text = json.dumps(result)

        return Message(
            role="tool",
            text=result_text,
            tool_call_id=str(tool_call_id),
            tool_name=str(tool_name),
        )
    except (KeyError, AttributeError, ValueError, TypeError):
        # If event data is malformed, skip it
        return None


def get_last_user_message(events: list[BaseEvent]) -> str | None:
    """Extract the most recent user message from events.

    This is a convenience function for getting just the last user message,
    useful for displaying current user input or detecting conversation state.

    Args:
        events: List of events from the event stream

    Returns:
        Text of the last user message, or None if no user messages found

    Example:
        >>> events = [...]
        >>> last_msg = get_last_user_message(events)
        >>> print(f"User asked: {last_msg}")
    """
    for event in reversed(events):
        if event.type == USER_MESSAGE_ADDED:
            return event.data.get("message")
    return None


def count_conversation_turns(events: list[BaseEvent]) -> int:
    """Count the number of conversation turns (user message + LLM response pairs).

    Args:
        events: List of events from the event stream

    Returns:
        Number of complete conversation turns

    Example:
        >>> events = [...]
        >>> turns = count_conversation_turns(events)
        >>> print(f"Conversation has {turns} turns")
    """
    user_messages = sum(1 for e in events if e.type == USER_MESSAGE_ADDED)
    llm_responses = sum(1 for e in events if e.type == LLM_RESPONSE_RECEIVED)
    # A turn requires both user message and LLM response
    return min(user_messages, llm_responses)

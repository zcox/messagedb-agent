"""Tool Arguments projection for extracting tool call parameters from events.

This module provides projection functions that analyze event streams to extract
tool calls and their arguments from LLM responses. This enables the processing
engine to execute tools with the correct parameters.

The projection focuses on finding pending tool calls that need to be executed,
typically from the most recent LLM response event.

Example:
    >>> from messagedb_agent.store import read_stream
    >>> from messagedb_agent.projections import project_to_tool_arguments
    >>>
    >>> # Read events from a stream
    >>> events = read_stream(client, "agent:v0-thread123")
    >>>
    >>> # Get pending tool calls
    >>> tool_args = project_to_tool_arguments(events)
    >>>
    >>> # Execute each tool
    >>> for tool_call in tool_args:
    ...     result = execute_tool(tool_call["name"], tool_call["arguments"])
"""

from typing import Any, cast

from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent


def project_to_tool_arguments(events: list[BaseEvent]) -> list[dict[str, Any]]:
    """Project event stream to extract pending tool calls and their arguments.

    This function examines the event stream to find tool calls that need to be
    executed. It looks for the most recent LLMResponseReceived event and extracts
    any tool calls from it.

    The function returns tool calls in a format suitable for tool execution,
    with each tool call as a dictionary containing id, name, and arguments.

    Args:
        events: List of events from the event stream in chronological order

    Returns:
        List of tool call dictionaries, each with:
        - id: Unique identifier for the tool call
        - name: Name of the tool to execute
        - arguments: Dictionary of arguments for the tool

        Returns empty list if:
        - Event list is empty
        - No LLMResponseReceived events found
        - Most recent LLM response has no tool calls

    Example:
        >>> events = [
        ...     BaseEvent(
        ...         type="LLMResponseReceived",
        ...         data={
        ...             "response_text": None,
        ...             "tool_calls": [
        ...                 {"id": "1", "name": "get_weather", "arguments": {"city": "NYC"}},
        ...                 {"id": "2", "name": "get_time", "arguments": {"timezone": "EST"}}
        ...             ],
        ...             "model_name": "gemini-2.5-flash",
        ...             "token_usage": {}
        ...         },
        ...         ...
        ...     ),
        ... ]
        >>> tool_args = project_to_tool_arguments(events)
        >>> len(tool_args)
        2
        >>> tool_args[0]["name"]
        'get_weather'
        >>> tool_args[0]["arguments"]
        {'city': 'NYC'}
    """
    if not events:
        return []

    # Find the most recent LLMResponseReceived event
    last_llm_response = _find_last_llm_response(events)
    if last_llm_response is None:
        return []

    # Extract tool calls from the event data
    data: dict[str, Any] = last_llm_response.data
    tool_calls = data.get("tool_calls", [])

    # Convert to list of dicts if needed
    # The tool_calls might be ToolCall dataclass instances or dicts
    result: list[dict[str, Any]] = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            # Already a dict, cast to proper type for type checker
            result.append(cast(dict[str, Any], tc))
        else:
            # Assume it's a ToolCall dataclass, convert to dict
            result.append({"id": tc.id, "name": tc.name, "arguments": tc.arguments})

    return result


def get_tool_call_by_name(events: list[BaseEvent], tool_name: str) -> dict[str, Any] | None:
    """Get the most recent tool call for a specific tool by name.

    This is a convenience function that extracts tool calls and filters
    for a specific tool name.

    Args:
        events: List of events from the event stream
        tool_name: Name of the tool to search for

    Returns:
        Tool call dict if found, None otherwise

    Example:
        >>> events = [...]
        >>> weather_call = get_tool_call_by_name(events, "get_weather")
        >>> if weather_call:
        ...     city = weather_call["arguments"]["city"]
    """
    tool_calls = project_to_tool_arguments(events)
    for tc in tool_calls:
        if tc.get("name") == tool_name:
            return tc
    return None


def get_all_tool_names(events: list[BaseEvent]) -> list[str]:
    """Get list of all tool names from pending tool calls.

    Args:
        events: List of events from the event stream

    Returns:
        List of tool names in order they were requested

    Example:
        >>> events = [...]
        >>> tool_names = get_all_tool_names(events)
        >>> print(tool_names)
        ['get_weather', 'get_time', 'calculate']
    """
    tool_calls = project_to_tool_arguments(events)
    return [tc.get("name", "") for tc in tool_calls if tc.get("name")]


def has_pending_tool_calls(events: list[BaseEvent]) -> bool:
    """Check if there are any pending tool calls in the event stream.

    This is a convenience function to quickly check if tools need to be executed.

    Args:
        events: List of events from the event stream

    Returns:
        True if there are pending tool calls, False otherwise

    Example:
        >>> events = [...]
        >>> if has_pending_tool_calls(events):
        ...     tool_calls = project_to_tool_arguments(events)
        ...     for tc in tool_calls:
        ...         execute_tool(tc["name"], tc["arguments"])
    """
    tool_calls = project_to_tool_arguments(events)
    return len(tool_calls) > 0


def count_tool_calls(events: list[BaseEvent]) -> int:
    """Count the number of pending tool calls.

    Args:
        events: List of events from the event stream

    Returns:
        Number of pending tool calls

    Example:
        >>> events = [...]
        >>> count = count_tool_calls(events)
        >>> print(f"Need to execute {count} tools")
    """
    tool_calls = project_to_tool_arguments(events)
    return len(tool_calls)


def _find_last_llm_response(events: list[BaseEvent]) -> BaseEvent | None:
    """Find the most recent LLMResponseReceived event.

    Args:
        events: List of events to search

    Returns:
        Most recent LLMResponseReceived event, or None if not found
    """
    # Iterate backwards to find last LLM response
    for event in reversed(events):
        if event.type == LLM_RESPONSE_RECEIVED:
            return event
    return None

"""Tests for tool arguments projection functions."""

from datetime import datetime
from uuid import uuid4

from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED, ToolCall
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.user import USER_MESSAGE_ADDED
from messagedb_agent.projections.tool_args import (
    count_tool_calls,
    get_all_tool_names,
    get_tool_call_by_name,
    has_pending_tool_calls,
    project_to_tool_arguments,
)


def create_test_event(
    event_type: str,
    data: dict,
    stream_name: str = "agent:v0-test123",
    position: int = 0,
    time: datetime | None = None,
) -> BaseEvent:
    """Helper to create test events."""
    return BaseEvent(
        id=str(uuid4()),
        type=event_type,
        data=data,
        metadata={},
        position=position,
        global_position=position,
        time=time or datetime.now(),
        stream_name=stream_name,
    )


class TestProjectToToolArguments:
    """Test project_to_tool_arguments function."""

    def test_empty_events_returns_empty_list(self):
        """Test that empty event list returns empty list."""
        result = project_to_tool_arguments([])
        assert result == []

    def test_no_llm_response_returns_empty_list(self):
        """Test that events without LLM response return empty list."""
        events = [
            create_test_event(USER_MESSAGE_ADDED, {"message": "Hello"}),
        ]
        result = project_to_tool_arguments(events)
        assert result == []

    def test_llm_response_without_tool_calls_returns_empty_list(self):
        """Test that LLM response with no tool calls returns empty list."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hello!",
                    "tool_calls": [],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = project_to_tool_arguments(events)
        assert result == []

    def test_single_tool_call_as_dict(self):
        """Test extracting a single tool call stored as dict."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "get_weather",
                            "arguments": {"city": "New York"},
                        }
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 1
        assert result[0]["id"] == "call_1"
        assert result[0]["name"] == "get_weather"
        assert result[0]["arguments"] == {"city": "New York"}

    def test_single_tool_call_as_dataclass(self):
        """Test extracting a single tool call stored as ToolCall dataclass."""
        tool_call = ToolCall(id="call_1", name="get_weather", arguments={"city": "New York"})
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [tool_call],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 1
        assert result[0]["id"] == "call_1"
        assert result[0]["name"] == "get_weather"
        assert result[0]["arguments"] == {"city": "New York"}

    def test_multiple_tool_calls(self):
        """Test extracting multiple tool calls."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}},
                        {"id": "call_2", "name": "get_time", "arguments": {"timezone": "EST"}},
                        {
                            "id": "call_3",
                            "name": "calculate",
                            "arguments": {"expression": "2+2"},
                        },
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 3
        assert result[0]["name"] == "get_weather"
        assert result[1]["name"] == "get_time"
        assert result[2]["name"] == "calculate"

    def test_uses_most_recent_llm_response(self):
        """Test that function uses the most recent LLM response."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "old_1", "name": "old_tool", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
                position=0,
            ),
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "new_1", "name": "new_tool", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
                position=1,
            ),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 1
        assert result[0]["id"] == "new_1"
        assert result[0]["name"] == "new_tool"

    def test_complex_tool_arguments(self):
        """Test tool calls with complex nested arguments."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "search",
                            "arguments": {
                                "query": "weather forecast",
                                "filters": {"location": "NYC", "date": "2025-01-15"},
                                "options": ["temperature", "humidity"],
                            },
                        }
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 1
        assert result[0]["arguments"]["query"] == "weather forecast"
        assert result[0]["arguments"]["filters"]["location"] == "NYC"
        assert result[0]["arguments"]["options"] == ["temperature", "humidity"]

    def test_tool_calls_with_empty_arguments(self):
        """Test tool calls with empty argument dictionaries."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "call_1", "name": "get_current_time", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 1
        assert result[0]["name"] == "get_current_time"
        assert result[0]["arguments"] == {}

    def test_mixed_events_returns_only_tool_calls(self):
        """Test that only tool calls from LLM response are returned."""
        events = [
            create_test_event(USER_MESSAGE_ADDED, {"message": "What's the weather?"}),
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
            create_test_event(USER_MESSAGE_ADDED, {"message": "Thanks!"}),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 1
        assert result[0]["name"] == "get_weather"

    def test_llm_response_with_text_and_tool_calls(self):
        """Test LLM response that has both text and tool calls."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Let me check that for you.",
                    "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = project_to_tool_arguments(events)

        assert len(result) == 1
        assert result[0]["name"] == "get_weather"


class TestGetToolCallByName:
    """Test get_tool_call_by_name helper function."""

    def test_empty_events_returns_none(self):
        """Test that empty events return None."""
        result = get_tool_call_by_name([], "any_tool")
        assert result is None

    def test_no_matching_tool_returns_none(self):
        """Test that non-matching tool name returns None."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = get_tool_call_by_name(events, "get_time")
        assert result is None

    def test_finds_matching_tool(self):
        """Test finding a tool call by name."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}},
                        {"id": "call_2", "name": "get_time", "arguments": {}},
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = get_tool_call_by_name(events, "get_weather")

        assert result is not None
        assert result["id"] == "call_1"
        assert result["name"] == "get_weather"
        assert result["arguments"] == {"city": "NYC"}

    def test_returns_first_matching_tool_if_duplicates(self):
        """Test that first matching tool is returned if there are duplicates."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}},
                        {"id": "call_2", "name": "get_weather", "arguments": {"city": "LA"}},
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = get_tool_call_by_name(events, "get_weather")

        assert result is not None
        assert result["id"] == "call_1"
        assert result["arguments"]["city"] == "NYC"


class TestGetAllToolNames:
    """Test get_all_tool_names helper function."""

    def test_empty_events_returns_empty_list(self):
        """Test that empty events return empty list."""
        result = get_all_tool_names([])
        assert result == []

    def test_no_tool_calls_returns_empty_list(self):
        """Test that events with no tool calls return empty list."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hello!",
                    "tool_calls": [],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = get_all_tool_names(events)
        assert result == []

    def test_returns_all_tool_names_in_order(self):
        """Test that all tool names are returned in order."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {}},
                        {"id": "call_2", "name": "get_time", "arguments": {}},
                        {"id": "call_3", "name": "calculate", "arguments": {}},
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = get_all_tool_names(events)

        assert result == ["get_weather", "get_time", "calculate"]

    def test_handles_duplicate_tool_names(self):
        """Test that duplicate tool names are included."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {}},
                        {"id": "call_2", "name": "get_weather", "arguments": {}},
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = get_all_tool_names(events)

        assert result == ["get_weather", "get_weather"]


class TestHasPendingToolCalls:
    """Test has_pending_tool_calls helper function."""

    def test_empty_events_returns_false(self):
        """Test that empty events return False."""
        result = has_pending_tool_calls([])
        assert result is False

    def test_no_tool_calls_returns_false(self):
        """Test that events with no tool calls return False."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hello!",
                    "tool_calls": [],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = has_pending_tool_calls(events)
        assert result is False

    def test_with_tool_calls_returns_true(self):
        """Test that events with tool calls return True."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = has_pending_tool_calls(events)
        assert result is True


class TestCountToolCalls:
    """Test count_tool_calls helper function."""

    def test_empty_events_returns_zero(self):
        """Test that empty events return 0."""
        result = count_tool_calls([])
        assert result == 0

    def test_no_tool_calls_returns_zero(self):
        """Test that events with no tool calls return 0."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hello!",
                    "tool_calls": [],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = count_tool_calls(events)
        assert result == 0

    def test_single_tool_call_returns_one(self):
        """Test that single tool call returns 1."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "call_1", "name": "get_weather", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = count_tool_calls(events)
        assert result == 1

    def test_multiple_tool_calls_returns_correct_count(self):
        """Test that multiple tool calls return correct count."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {}},
                        {"id": "call_2", "name": "get_time", "arguments": {}},
                        {"id": "call_3", "name": "calculate", "arguments": {}},
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        result = count_tool_calls(events)
        assert result == 3


class TestProjectionPurity:
    """Test that projection functions are pure (same input = same output)."""

    def test_project_to_tool_arguments_is_pure(self):
        """Test that calling projection multiple times gives same result."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}}
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]

        result1 = project_to_tool_arguments(events)
        result2 = project_to_tool_arguments(events)
        result3 = project_to_tool_arguments(events)

        assert result1 == result2 == result3
        assert len(result1) == 1
        assert result1[0]["name"] == "get_weather"

    def test_helper_functions_are_pure(self):
        """Test that all helper functions are pure."""
        events = [
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {}},
                        {"id": "call_2", "name": "get_time", "arguments": {}},
                    ],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]

        # Call each function multiple times
        assert count_tool_calls(events) == count_tool_calls(events) == 2
        assert has_pending_tool_calls(events) == has_pending_tool_calls(events) is True
        assert get_all_tool_names(events) == get_all_tool_names(events)
        assert get_tool_call_by_name(events, "get_weather") == get_tool_call_by_name(
            events, "get_weather"
        )

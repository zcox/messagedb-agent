"""Tests for LLM context projection."""

from datetime import UTC, datetime
from typing import Any

from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.system import SESSION_COMPLETED, SESSION_STARTED
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_COMPLETED,
)
from messagedb_agent.events.user import (
    USER_MESSAGE_ADDED,
)
from messagedb_agent.projections.llm_context import (
    count_conversation_turns,
    get_last_user_message,
    project_to_llm_context,
)


# Helper function to create test events
def create_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    position: int = 0,
) -> BaseEvent:
    """Create a test event for projection testing."""
    return BaseEvent(
        id=f"event-{position}",
        type=event_type,
        data=data or {},
        metadata=metadata or {},
        position=position,
        global_position=position,
        time=datetime.now(UTC),
        stream_name="agent:v0-test123",
    )


class TestProjectToLLMContext:
    """Tests for the main LLM context projection function."""

    def test_empty_events_returns_empty_messages(self):
        """Test projecting empty event list returns empty message list."""
        events: list[BaseEvent] = []
        messages = project_to_llm_context(events)
        assert messages == []

    def test_single_user_message(self):
        """Test converting single user message event."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello, how are you?", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            )
        ]

        messages = project_to_llm_context(events)

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].text == "Hello, how are you?"
        assert messages[0].tool_calls is None

    def test_single_llm_response_with_text(self):
        """Test converting LLM response with text only."""
        events = [
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "I'm doing well, thank you!",
                    "tool_calls": [],
                    "model_name": "claude-sonnet-4-5@20250929",
                    "token_usage": {"input_tokens": 10, "output_tokens": 8},
                },
                position=0,
            )
        ]

        messages = project_to_llm_context(events)

        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].text == "I'm doing well, thank you!"
        assert messages[0].tool_calls is None

    def test_llm_response_with_tool_calls(self):
        """Test converting LLM response with tool calls."""
        events = [
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Let me check the weather.",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "name": "get_weather",
                            "arguments": {"city": "San Francisco"},
                        }
                    ],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 20, "output_tokens": 15},
                },
                position=0,
            )
        ]

        messages = project_to_llm_context(events)

        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].text == "Let me check the weather."
        assert messages[0].tool_calls is not None
        assert len(messages[0].tool_calls) == 1
        assert messages[0].tool_calls[0].id == "call_123"
        assert messages[0].tool_calls[0].name == "get_weather"
        assert messages[0].tool_calls[0].arguments == {"city": "San Francisco"}

    def test_tool_execution_completed(self):
        """Test converting tool execution completed event."""
        events = [
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {
                    "tool_name": "get_weather",
                    "result": {"temperature": 72, "conditions": "sunny"},
                    "execution_time_ms": 150,
                },
                metadata={"tool_call_id": "call_123"},
                position=0,
            )
        ]

        messages = project_to_llm_context(events)

        assert len(messages) == 1
        assert messages[0].role == "tool"
        assert messages[0].tool_call_id == "call_123"
        assert messages[0].tool_name == "get_weather"
        assert '"temperature": 72' in messages[0].text

    def test_complete_conversation_flow(self):
        """Test a complete conversation with user, assistant, tool calls, and results."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "What's the weather in SF?", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Let me check that for you.",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "SF"}}
                    ],
                    "model_name": "claude-sonnet-4-5@20250929",
                    "token_usage": {"input_tokens": 15, "output_tokens": 10},
                },
                position=1,
            ),
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "get_weather", "result": "Sunny, 72F", "execution_time_ms": 100},
                metadata={"tool_call_id": "call_1"},
                position=2,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "It's sunny and 72F in San Francisco!",
                    "tool_calls": [],
                    "model_name": "claude-sonnet-4-5@20250929",
                    "token_usage": {"input_tokens": 25, "output_tokens": 12},
                },
                position=3,
            ),
        ]

        messages = project_to_llm_context(events)

        assert len(messages) == 4
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[1].tool_calls is not None
        assert messages[2].role == "tool"
        assert messages[3].role == "assistant"

    def test_filters_out_system_events(self):
        """Test that system events are filtered out of LLM context."""
        events = [
            create_event(SESSION_STARTED, {"thread_id": "test123"}, position=0),
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
                position=1,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hi!",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 5, "output_tokens": 2},
                },
                position=2,
            ),
            create_event(SESSION_COMPLETED, {"completion_reason": "success"}, position=3),
        ]

        messages = project_to_llm_context(events)

        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"


class TestGetLastUserMessage:
    """Tests for the get_last_user_message convenience function."""

    def test_empty_events_returns_none(self):
        """Test that empty events returns None."""
        events: list[BaseEvent] = []
        result = get_last_user_message(events)
        assert result is None

    def test_single_user_message(self):
        """Test getting last message from single user message."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello, world!", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            )
        ]
        result = get_last_user_message(events)
        assert result == "Hello, world!"

    def test_multiple_user_messages_returns_last(self):
        """Test that with multiple messages, returns the last one."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "First", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            ),
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Third", "timestamp": "2024-01-01T12:02:00Z"},
                position=2,
            ),
        ]
        result = get_last_user_message(events)
        assert result == "Third"


class TestCountConversationTurns:
    """Tests for the count_conversation_turns function."""

    def test_empty_events_returns_zero(self):
        """Test that empty events returns 0 turns."""
        events: list[BaseEvent] = []
        result = count_conversation_turns(events)
        assert result == 0

    def test_single_complete_turn(self):
        """Test counting a single complete turn (user + LLM response)."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hi!",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 5, "output_tokens": 2},
                },
                position=1,
            ),
        ]
        result = count_conversation_turns(events)
        assert result == 1

    def test_multiple_complete_turns(self):
        """Test counting multiple complete turns."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hi!",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 5, "output_tokens": 2},
                },
                position=1,
            ),
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "How are you?", "timestamp": "2024-01-01T12:01:00Z"},
                position=2,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "I'm good!",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 8, "output_tokens": 3},
                },
                position=3,
            ),
        ]
        result = count_conversation_turns(events)
        assert result == 2

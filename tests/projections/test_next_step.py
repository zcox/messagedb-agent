"""Tests for Next Step projection."""

from datetime import UTC, datetime
from typing import Any

import pytest

from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.system import SESSION_COMPLETED
from messagedb_agent.events.tool import TOOL_EXECUTION_COMPLETED
from messagedb_agent.events.user import (
    SESSION_TERMINATION_REQUESTED,
    USER_MESSAGE_ADDED,
)
from messagedb_agent.projections.next_step import (
    StepType,
    count_steps_taken,
    get_pending_tool_calls,
    project_to_next_step,
    should_terminate,
)


# Helper function to create test events
def create_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    position: int = 0,
) -> BaseEvent:
    """Create a test event for projection testing."""
    return BaseEvent(
        id=f"event-{position}",
        type=event_type,
        data=data or {},
        metadata={},
        position=position,
        global_position=position,
        time=datetime.now(UTC),
        stream_name="agent:v0-test123",
    )


class TestProjectToNextStep:
    """Tests for the main next step projection function."""

    def test_empty_events_raises_error(self):
        """Test that empty event list raises ValueError."""
        events: list[BaseEvent] = []
        with pytest.raises(ValueError, match="Cannot determine next step from empty"):
            project_to_next_step(events)

    def test_user_message_added_returns_llm_call(self):
        """Test that UserMessageAdded triggers LLM_CALL."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            )
        ]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.LLM_CALL
        assert metadata["reason"] == "user_message_added"

    def test_llm_response_with_tool_calls_returns_tool_execution(self):
        """Test that LLM response with tool calls triggers TOOL_EXECUTION."""
        events = [
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Let me check that.",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}}
                    ],
                    "model_name": "claude-sonnet-4-5@20250929",
                    "token_usage": {"input_tokens": 10, "output_tokens": 5},
                },
                position=0,
            )
        ]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.TOOL_EXECUTION
        assert metadata["reason"] == "llm_requested_tools"
        assert len(metadata["tool_calls"]) == 1
        assert metadata["tool_calls"][0]["name"] == "get_weather"

    def test_llm_response_without_tool_calls_returns_termination(self):
        """Test that LLM response without tool calls triggers TERMINATION."""
        events = [
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hello there!",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 5, "output_tokens": 3},
                },
                position=0,
            )
        ]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.TERMINATION
        assert metadata["reason"] == "llm_response_complete"

    def test_tool_execution_completed_returns_llm_call(self):
        """Test that ToolExecutionCompleted triggers LLM_CALL."""
        events = [
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {
                    "tool_name": "get_weather",
                    "result": {"temp": 72},
                    "execution_time_ms": 100,
                },
                position=0,
            )
        ]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.LLM_CALL
        assert metadata["reason"] == "tool_execution_completed"

    def test_session_termination_requested_returns_termination(self):
        """Test that SessionTerminationRequested triggers TERMINATION."""
        events = [
            create_event(
                SESSION_TERMINATION_REQUESTED,
                {"reason": "User requested stop"},
                position=0,
            )
        ]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.TERMINATION
        assert metadata["reason"] == "User requested stop"

    def test_session_completed_returns_termination(self):
        """Test that SessionCompleted triggers TERMINATION."""
        events = [
            create_event(
                SESSION_COMPLETED,
                {"completion_reason": "success"},
                position=0,
            )
        ]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.TERMINATION
        assert metadata["reason"] == "success"

    def test_uses_last_event_for_decision(self):
        """Test that only the last event determines the next step."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "First", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Response",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 10, "output_tokens": 5},
                },
                position=1,
            ),
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Second", "timestamp": "2024-01-01T12:01:00Z"},
                position=2,
            ),
        ]

        step_type, metadata = project_to_next_step(events)

        # Should be based on last event (UserMessageAdded)
        assert step_type == StepType.LLM_CALL
        assert metadata["reason"] == "user_message_added"

    def test_complete_flow_sequence(self):
        """Test a complete conversation flow through different steps."""
        # Step 1: User message
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "What's the weather?", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            )
        ]
        step_type, _ = project_to_next_step(events)
        assert step_type == StepType.LLM_CALL

        # Step 2: LLM responds with tool call
        events.append(
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Checking...",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "SF"}}
                    ],
                    "model_name": "claude-sonnet-4-5@20250929",
                    "token_usage": {"input_tokens": 15, "output_tokens": 8},
                },
                position=1,
            )
        )
        step_type, _ = project_to_next_step(events)
        assert step_type == StepType.TOOL_EXECUTION

        # Step 3: Tool executes
        events.append(
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "get_weather", "result": "72F", "execution_time_ms": 50},
                position=2,
            )
        )
        step_type, _ = project_to_next_step(events)
        assert step_type == StepType.LLM_CALL

        # Step 4: LLM responds with final answer
        events.append(
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "It's 72F!",
                    "tool_calls": [],
                    "model_name": "claude-sonnet-4-5@20250929",
                    "token_usage": {"input_tokens": 20, "output_tokens": 5},
                },
                position=3,
            )
        )
        step_type, _ = project_to_next_step(events)
        assert step_type == StepType.TERMINATION

    def test_unknown_event_type_defaults_to_llm_call(self):
        """Test that unknown event types default to LLM_CALL."""
        events = [create_event("UnknownEventType", {}, position=0)]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.LLM_CALL
        assert metadata["reason"] == "unknown_event_type"
        assert metadata["event_type"] == "UnknownEventType"

    def test_llm_response_with_multiple_tool_calls(self):
        """Test LLM response with multiple tool calls."""
        events = [
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Checking both",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}},
                        {"id": "call_2", "name": "get_weather", "arguments": {"city": "SF"}},
                    ],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 20, "output_tokens": 10},
                },
                position=0,
            )
        ]

        step_type, metadata = project_to_next_step(events)

        assert step_type == StepType.TOOL_EXECUTION
        assert len(metadata["tool_calls"]) == 2


class TestShouldTerminate:
    """Tests for the should_terminate convenience function."""

    def test_empty_events_returns_false(self):
        """Test that empty events returns False."""
        events: list[BaseEvent] = []
        assert should_terminate(events) is False

    def test_termination_event_returns_true(self):
        """Test that termination events return True."""
        events = [create_event(SESSION_TERMINATION_REQUESTED, {"reason": "stop"}, position=0)]
        assert should_terminate(events) is True

    def test_session_completed_returns_true(self):
        """Test that SessionCompleted returns True."""
        events = [create_event(SESSION_COMPLETED, {"completion_reason": "success"}, position=0)]
        assert should_terminate(events) is True

    def test_non_termination_event_returns_false(self):
        """Test that non-termination events return False."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            )
        ]
        assert should_terminate(events) is False


class TestGetPendingToolCalls:
    """Tests for the get_pending_tool_calls convenience function."""

    def test_empty_events_returns_empty_list(self):
        """Test that empty events returns empty list."""
        events: list[BaseEvent] = []
        tool_calls = get_pending_tool_calls(events)
        assert tool_calls == []

    def test_tool_execution_step_returns_tool_calls(self):
        """Test that TOOL_EXECUTION step returns tool calls."""
        events = [
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Checking",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}}
                    ],
                    "model_name": "claude-sonnet-4-5@20250929",
                    "token_usage": {"input_tokens": 10, "output_tokens": 5},
                },
                position=0,
            )
        ]

        tool_calls = get_pending_tool_calls(events)

        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "get_weather"

    def test_non_tool_execution_step_returns_empty_list(self):
        """Test that non-TOOL_EXECUTION steps return empty list."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            )
        ]

        tool_calls = get_pending_tool_calls(events)
        assert tool_calls == []


class TestCountStepsTaken:
    """Tests for the count_steps_taken function."""

    def test_empty_events_returns_zero_counts(self):
        """Test that empty events returns zero for all counts."""
        events: list[BaseEvent] = []
        counts = count_steps_taken(events)

        assert counts["llm_calls"] == 0
        assert counts["tool_executions"] == 0

    def test_counts_llm_calls(self):
        """Test counting LLM calls."""
        events = [
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Response 1",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 5, "output_tokens": 3},
                },
                position=0,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Response 2",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 5, "output_tokens": 3},
                },
                position=1,
            ),
        ]

        counts = count_steps_taken(events)
        assert counts["llm_calls"] == 2
        assert counts["tool_executions"] == 0

    def test_counts_tool_executions(self):
        """Test counting tool executions."""
        events = [
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "tool1", "result": "result1", "execution_time_ms": 10},
                position=0,
            ),
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "tool2", "result": "result2", "execution_time_ms": 20},
                position=1,
            ),
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "tool3", "result": "result3", "execution_time_ms": 30},
                position=2,
            ),
        ]

        counts = count_steps_taken(events)
        assert counts["llm_calls"] == 0
        assert counts["tool_executions"] == 3

    def test_counts_mixed_events(self):
        """Test counting with mixed event types."""
        events = [
            create_event(
                USER_MESSAGE_ADDED,
                {"message": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
                position=0,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Response",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 5, "output_tokens": 3},
                },
                position=1,
            ),
            create_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "tool1", "result": "result", "execution_time_ms": 10},
                position=2,
            ),
            create_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Final",
                    "tool_calls": [],
                    "model_name": "gemini-2.0-flash",
                    "token_usage": {"input_tokens": 8, "output_tokens": 4},
                },
                position=3,
            ),
        ]

        counts = count_steps_taken(events)
        assert counts["llm_calls"] == 2
        assert counts["tool_executions"] == 1


class TestStepTypeEnum:
    """Tests for the StepType enum."""

    def test_enum_values(self):
        """Test that enum has correct values."""
        assert StepType.LLM_CALL.value == "llm_call"
        assert StepType.TOOL_EXECUTION.value == "tool_execution"
        assert StepType.TERMINATION.value == "termination"

    def test_enum_comparison(self):
        """Test enum comparison."""
        assert StepType.LLM_CALL == StepType.LLM_CALL
        assert StepType.LLM_CALL != StepType.TOOL_EXECUTION
        assert StepType.TOOL_EXECUTION != StepType.TERMINATION

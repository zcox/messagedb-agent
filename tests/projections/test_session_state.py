"""Tests for session state projection functions."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from messagedb_agent.events.agent import LLM_CALL_FAILED, LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.system import SESSION_COMPLETED, SESSION_STARTED
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_COMPLETED,
    TOOL_EXECUTION_FAILED,
)
from messagedb_agent.events.user import SESSION_TERMINATION_REQUESTED, USER_MESSAGE_ADDED
from messagedb_agent.projections.session_state import (
    SessionState,
    SessionStatus,
    get_session_duration,
    is_session_active,
    project_to_session_state,
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


class TestSessionStateDataclass:
    """Test SessionState dataclass validation."""

    def test_valid_session_state(self):
        """Test creating a valid SessionState."""
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.ACTIVE,
            message_count=5,
            tool_call_count=3,
            llm_call_count=7,
            error_count=0,
            last_activity_time=datetime.now(),
            session_start_time=datetime.now(),
            session_end_time=None,
        )
        assert state.thread_id == "test123"
        assert state.status == SessionStatus.ACTIVE
        assert state.message_count == 5

    def test_empty_thread_id_raises_error(self):
        """Test that empty thread_id raises ValueError."""
        with pytest.raises(ValueError, match="Thread ID cannot be empty"):
            SessionState(
                thread_id="",
                status=SessionStatus.ACTIVE,
                message_count=0,
                tool_call_count=0,
                llm_call_count=0,
                error_count=0,
                last_activity_time=None,
                session_start_time=None,
                session_end_time=None,
            )

    def test_whitespace_thread_id_raises_error(self):
        """Test that whitespace-only thread_id raises ValueError."""
        with pytest.raises(ValueError, match="Thread ID cannot be empty"):
            SessionState(
                thread_id="   ",
                status=SessionStatus.ACTIVE,
                message_count=0,
                tool_call_count=0,
                llm_call_count=0,
                error_count=0,
                last_activity_time=None,
                session_start_time=None,
                session_end_time=None,
            )

    def test_negative_message_count_raises_error(self):
        """Test that negative message_count raises ValueError."""
        with pytest.raises(ValueError, match="Message count cannot be negative"):
            SessionState(
                thread_id="test123",
                status=SessionStatus.ACTIVE,
                message_count=-1,
                tool_call_count=0,
                llm_call_count=0,
                error_count=0,
                last_activity_time=None,
                session_start_time=None,
                session_end_time=None,
            )

    def test_negative_tool_call_count_raises_error(self):
        """Test that negative tool_call_count raises ValueError."""
        with pytest.raises(ValueError, match="Tool call count cannot be negative"):
            SessionState(
                thread_id="test123",
                status=SessionStatus.ACTIVE,
                message_count=0,
                tool_call_count=-1,
                llm_call_count=0,
                error_count=0,
                last_activity_time=None,
                session_start_time=None,
                session_end_time=None,
            )

    def test_negative_llm_call_count_raises_error(self):
        """Test that negative llm_call_count raises ValueError."""
        with pytest.raises(ValueError, match="LLM call count cannot be negative"):
            SessionState(
                thread_id="test123",
                status=SessionStatus.ACTIVE,
                message_count=0,
                tool_call_count=0,
                llm_call_count=-1,
                error_count=0,
                last_activity_time=None,
                session_start_time=None,
                session_end_time=None,
            )

    def test_negative_error_count_raises_error(self):
        """Test that negative error_count raises ValueError."""
        with pytest.raises(ValueError, match="Error count cannot be negative"):
            SessionState(
                thread_id="test123",
                status=SessionStatus.ACTIVE,
                message_count=0,
                tool_call_count=0,
                llm_call_count=0,
                error_count=-1,
                last_activity_time=None,
                session_start_time=None,
                session_end_time=None,
            )


class TestProjectToSessionState:
    """Test project_to_session_state function."""

    def test_empty_events_raises_error(self):
        """Test that empty event list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot compute session state from empty event list"):
            project_to_session_state([])

    def test_single_session_started_event(self):
        """Test projection with only a SessionStarted event."""
        start_time = datetime(2025, 1, 15, 10, 0, 0)
        events = [
            create_test_event(
                SESSION_STARTED,
                {"thread_id": "test123"},
                time=start_time,
            )
        ]
        state = project_to_session_state(events)

        assert state.thread_id == "test123"
        assert state.status == SessionStatus.ACTIVE
        assert state.message_count == 0
        assert state.tool_call_count == 0
        assert state.llm_call_count == 0
        assert state.error_count == 0
        assert state.session_start_time == start_time
        assert state.last_activity_time == start_time
        assert state.session_end_time is None

    def test_counts_user_messages(self):
        """Test that user messages are counted correctly."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(USER_MESSAGE_ADDED, {"message": "Hello"}),
            create_test_event(USER_MESSAGE_ADDED, {"message": "How are you?"}),
            create_test_event(USER_MESSAGE_ADDED, {"message": "Goodbye"}),
        ]
        state = project_to_session_state(events)
        assert state.message_count == 3

    def test_counts_llm_calls(self):
        """Test that LLM calls are counted correctly."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "Hello!",
                    "tool_calls": [],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "I'm well!",
                    "tool_calls": [],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
            ),
        ]
        state = project_to_session_state(events)
        assert state.llm_call_count == 2

    def test_counts_tool_executions(self):
        """Test that tool executions are counted correctly."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "get_weather", "result": "sunny", "execution_time_ms": 100},
            ),
            create_test_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "get_time", "result": "10:00", "execution_time_ms": 50},
            ),
        ]
        state = project_to_session_state(events)
        assert state.tool_call_count == 2

    def test_counts_errors(self):
        """Test that errors are counted correctly."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(
                LLM_CALL_FAILED,
                {"error_message": "API error", "retry_count": 0},
            ),
            create_test_event(
                TOOL_EXECUTION_FAILED,
                {"tool_name": "get_weather", "error_message": "Network error", "retry_count": 0},
            ),
            create_test_event(
                LLM_CALL_FAILED,
                {"error_message": "Timeout", "retry_count": 1},
            ),
        ]
        state = project_to_session_state(events)
        assert state.error_count == 3

    def test_active_status_by_default(self):
        """Test that status is ACTIVE when no completion event present."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(USER_MESSAGE_ADDED, {"message": "Hello"}),
        ]
        state = project_to_session_state(events)
        assert state.status == SessionStatus.ACTIVE

    def test_completed_status_on_success(self):
        """Test that status is COMPLETED on successful completion."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(SESSION_COMPLETED, {"completion_reason": "success"}),
        ]
        state = project_to_session_state(events)
        assert state.status == SessionStatus.COMPLETED

    def test_completed_status_on_completed_reason(self):
        """Test that status is COMPLETED with 'completed' reason."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(SESSION_COMPLETED, {"completion_reason": "completed"}),
        ]
        state = project_to_session_state(events)
        assert state.status == SessionStatus.COMPLETED

    def test_failed_status_on_failure(self):
        """Test that status is FAILED on failed completion."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(SESSION_COMPLETED, {"completion_reason": "failure"}),
        ]
        state = project_to_session_state(events)
        assert state.status == SessionStatus.FAILED

    def test_failed_status_on_timeout(self):
        """Test that status is FAILED on timeout."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(SESSION_COMPLETED, {"completion_reason": "timeout"}),
        ]
        state = project_to_session_state(events)
        assert state.status == SessionStatus.FAILED

    def test_terminated_status_on_user_request(self):
        """Test that status is TERMINATED when user requests termination."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(
                SESSION_TERMINATION_REQUESTED,
                {"reason": "user_request"},
            ),
        ]
        state = project_to_session_state(events)
        assert state.status == SessionStatus.TERMINATED

    def test_session_end_time_on_completion(self):
        """Test that session_end_time is set on completion."""
        start_time = datetime(2025, 1, 15, 10, 0, 0)
        end_time = datetime(2025, 1, 15, 10, 5, 0)
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}, time=start_time),
            create_test_event(SESSION_COMPLETED, {"completion_reason": "success"}, time=end_time),
        ]
        state = project_to_session_state(events)
        assert state.session_start_time == start_time
        assert state.session_end_time == end_time

    def test_last_activity_time_is_last_event(self):
        """Test that last_activity_time is timestamp of last event."""
        time1 = datetime(2025, 1, 15, 10, 0, 0)
        time2 = datetime(2025, 1, 15, 10, 1, 0)
        time3 = datetime(2025, 1, 15, 10, 2, 0)
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}, time=time1),
            create_test_event(USER_MESSAGE_ADDED, {"message": "Hello"}, time=time2),
            create_test_event(USER_MESSAGE_ADDED, {"message": "Goodbye"}, time=time3),
        ]
        state = project_to_session_state(events)
        assert state.last_activity_time == time3

    def test_thread_id_extraction_from_stream_name(self):
        """Test that thread_id is extracted from stream_name correctly."""
        events = [
            create_test_event(
                SESSION_STARTED,
                {"thread_id": "different_id"},  # This should be ignored
                stream_name="agent:v0-abc123",
            ),
        ]
        state = project_to_session_state(events)
        assert state.thread_id == "abc123"

    def test_complex_event_sequence(self):
        """Test projection with a complex realistic event sequence."""
        start_time = datetime(2025, 1, 15, 10, 0, 0)
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}, time=start_time),
            create_test_event(
                USER_MESSAGE_ADDED,
                {"message": "What's the weather?"},
                time=start_time + timedelta(seconds=1),
            ),
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": None,
                    "tool_calls": [{"id": "1", "name": "get_weather", "arguments": {}}],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
                time=start_time + timedelta(seconds=2),
            ),
            create_test_event(
                TOOL_EXECUTION_COMPLETED,
                {"tool_name": "get_weather", "result": "sunny", "execution_time_ms": 100},
                time=start_time + timedelta(seconds=3),
            ),
            create_test_event(
                LLM_RESPONSE_RECEIVED,
                {
                    "response_text": "It's sunny!",
                    "tool_calls": [],
                    "model_name": "gemini-2.5-flash",
                    "token_usage": {},
                },
                time=start_time + timedelta(seconds=4),
            ),
            create_test_event(
                USER_MESSAGE_ADDED,
                {"message": "Thanks!"},
                time=start_time + timedelta(seconds=5),
            ),
        ]
        state = project_to_session_state(events)

        assert state.thread_id == "test123"
        assert state.status == SessionStatus.ACTIVE
        assert state.message_count == 2
        assert state.llm_call_count == 2
        assert state.tool_call_count == 1
        assert state.error_count == 0
        assert state.session_start_time == start_time
        assert state.last_activity_time == start_time + timedelta(seconds=5)

    def test_errors_dont_change_status_if_not_completed(self):
        """Test that errors don't change status to FAILED unless session completed."""
        events = [
            create_test_event(SESSION_STARTED, {"thread_id": "test123"}),
            create_test_event(LLM_CALL_FAILED, {"error_message": "Error", "retry_count": 0}),
        ]
        state = project_to_session_state(events)
        # Should remain ACTIVE even with errors, until session officially completes
        assert state.status == SessionStatus.ACTIVE
        assert state.error_count == 1


class TestIsSessionActive:
    """Test is_session_active helper function."""

    def test_returns_true_for_active_status(self):
        """Test that function returns True for ACTIVE status."""
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.ACTIVE,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=None,
            session_start_time=None,
            session_end_time=None,
        )
        assert is_session_active(state) is True

    def test_returns_false_for_completed_status(self):
        """Test that function returns False for COMPLETED status."""
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.COMPLETED,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=None,
            session_start_time=None,
            session_end_time=None,
        )
        assert is_session_active(state) is False

    def test_returns_false_for_failed_status(self):
        """Test that function returns False for FAILED status."""
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.FAILED,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=None,
            session_start_time=None,
            session_end_time=None,
        )
        assert is_session_active(state) is False

    def test_returns_false_for_terminated_status(self):
        """Test that function returns False for TERMINATED status."""
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.TERMINATED,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=None,
            session_start_time=None,
            session_end_time=None,
        )
        assert is_session_active(state) is False


class TestGetSessionDuration:
    """Test get_session_duration helper function."""

    def test_returns_none_when_no_start_time(self):
        """Test that function returns None when session_start_time is None."""
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.ACTIVE,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=datetime.now(),
            session_start_time=None,
            session_end_time=None,
        )
        assert get_session_duration(state) is None

    def test_returns_none_when_no_end_or_activity_time(self):
        """Test that function returns None when no end or activity time available."""
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.ACTIVE,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=None,
            session_start_time=datetime.now(),
            session_end_time=None,
        )
        assert get_session_duration(state) is None

    def test_calculates_duration_with_end_time(self):
        """Test duration calculation when session_end_time is available."""
        start = datetime(2025, 1, 15, 10, 0, 0)
        end = datetime(2025, 1, 15, 10, 5, 0)  # 5 minutes later
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.COMPLETED,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=end,
            session_start_time=start,
            session_end_time=end,
        )
        duration = get_session_duration(state)
        assert duration == 300.0  # 5 minutes = 300 seconds

    def test_calculates_duration_with_activity_time(self):
        """Test duration calculation using last_activity_time when no end_time."""
        start = datetime(2025, 1, 15, 10, 0, 0)
        activity = datetime(2025, 1, 15, 10, 3, 0)  # 3 minutes later
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.ACTIVE,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=activity,
            session_start_time=start,
            session_end_time=None,
        )
        duration = get_session_duration(state)
        assert duration == 180.0  # 3 minutes = 180 seconds

    def test_prefers_end_time_over_activity_time(self):
        """Test that end_time is used instead of activity_time when both present."""
        start = datetime(2025, 1, 15, 10, 0, 0)
        end = datetime(2025, 1, 15, 10, 5, 0)
        activity = datetime(2025, 1, 15, 10, 3, 0)
        state = SessionState(
            thread_id="test123",
            status=SessionStatus.COMPLETED,
            message_count=0,
            tool_call_count=0,
            llm_call_count=0,
            error_count=0,
            last_activity_time=activity,
            session_start_time=start,
            session_end_time=end,
        )
        duration = get_session_duration(state)
        assert duration == 300.0  # Uses end_time (5 min), not activity_time (3 min)

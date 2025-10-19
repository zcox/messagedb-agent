"""Tests for system event types."""

import pytest

from messagedb_agent.events.system import (
    SESSION_COMPLETED,
    SESSION_STARTED,
    SessionCompletedData,
    SessionStartedData,
)


class TestSessionStartedData:
    """Tests for SessionStartedData event payload."""

    def test_create_session_started_data_minimal(self):
        """SessionStartedData can be created with just thread_id."""
        data = SessionStartedData(thread_id="abc123-def456")

        assert data.thread_id == "abc123-def456"
        assert data.initial_context is None

    def test_create_session_started_data_with_context(self):
        """SessionStartedData can be created with initial_context."""
        initial_context = {"user_id": "user_789", "language": "en", "model": "claude"}
        data = SessionStartedData(thread_id="abc123-def456", initial_context=initial_context)

        assert data.thread_id == "abc123-def456"
        assert data.initial_context == initial_context

    def test_session_started_data_is_immutable(self):
        """SessionStartedData instances are immutable (frozen)."""
        data = SessionStartedData(thread_id="abc123")

        with pytest.raises(AttributeError):
            data.thread_id = "modified"  # type: ignore

    def test_session_started_validates_empty_thread_id(self):
        """SessionStartedData raises ValueError for empty thread_id."""
        with pytest.raises(ValueError, match="Thread ID cannot be empty"):
            SessionStartedData(thread_id="")

    def test_session_started_validates_whitespace_only_thread_id(self):
        """SessionStartedData raises ValueError for whitespace-only thread_id."""
        with pytest.raises(ValueError, match="Thread ID cannot be empty"):
            SessionStartedData(thread_id="   ")

    def test_session_started_with_empty_initial_context(self):
        """SessionStartedData can be created with empty initial_context dict."""
        data = SessionStartedData(thread_id="abc123", initial_context={})

        assert data.thread_id == "abc123"
        assert data.initial_context == {}

    def test_session_started_with_complex_initial_context(self):
        """SessionStartedData handles complex nested initial_context."""
        initial_context = {
            "user": {"id": "user_123", "name": "Alice"},
            "settings": {"model": "claude-sonnet-4-5", "temperature": 0.7},
            "metadata": {"source": "web", "timestamp": "2024-01-01T00:00:00Z"},
        }
        data = SessionStartedData(thread_id="abc123", initial_context=initial_context)

        assert data.initial_context == initial_context
        assert data.initial_context["user"]["name"] == "Alice"  # type: ignore

    def test_session_started_with_uuid_thread_id(self):
        """SessionStartedData works with UUID-formatted thread_id."""
        thread_id = "550e8400-e29b-41d4-a716-446655440000"
        data = SessionStartedData(thread_id=thread_id)

        assert data.thread_id == thread_id

    def test_session_started_with_various_thread_id_formats(self):
        """SessionStartedData accepts various thread_id formats."""
        thread_ids = [
            "simple-123",
            "abc123def456",
            "thread:session:v1",
            "550e8400-e29b-41d4-a716-446655440000",
        ]

        for thread_id in thread_ids:
            data = SessionStartedData(thread_id=thread_id)
            assert data.thread_id == thread_id


class TestSessionCompletedData:
    """Tests for SessionCompletedData event payload."""

    def test_create_session_completed_data_success(self):
        """SessionCompletedData can be created with success reason."""
        data = SessionCompletedData(completion_reason="success")

        assert data.completion_reason == "success"

    def test_create_session_completed_data_failure(self):
        """SessionCompletedData can be created with failure reason."""
        data = SessionCompletedData(completion_reason="failure")

        assert data.completion_reason == "failure"

    def test_create_session_completed_data_timeout(self):
        """SessionCompletedData can be created with timeout reason."""
        data = SessionCompletedData(completion_reason="timeout")

        assert data.completion_reason == "timeout"

    def test_session_completed_data_is_immutable(self):
        """SessionCompletedData instances are immutable (frozen)."""
        data = SessionCompletedData(completion_reason="success")

        with pytest.raises(AttributeError):
            data.completion_reason = "modified"  # type: ignore

    def test_session_completed_validates_empty_completion_reason(self):
        """SessionCompletedData raises ValueError for empty completion_reason."""
        with pytest.raises(ValueError, match="Completion reason cannot be empty"):
            SessionCompletedData(completion_reason="")

    def test_session_completed_validates_whitespace_only_completion_reason(self):
        """SessionCompletedData raises ValueError for whitespace-only completion_reason."""
        with pytest.raises(ValueError, match="Completion reason cannot be empty"):
            SessionCompletedData(completion_reason="   ")

    def test_session_completed_with_various_reasons(self):
        """SessionCompletedData accepts various completion reasons."""
        reasons = [
            "success",
            "failure",
            "timeout",
            "user_request",
            "max_iterations_reached",
            "error",
            "cancelled",
        ]

        for reason in reasons:
            data = SessionCompletedData(completion_reason=reason)
            assert data.completion_reason == reason

    def test_session_completed_with_custom_reason(self):
        """SessionCompletedData accepts custom completion reasons."""
        custom_reasons = [
            "llm_error_unrecoverable",
            "rate_limit_exceeded_permanently",
            "user_cancelled_via_api",
        ]

        for reason in custom_reasons:
            data = SessionCompletedData(completion_reason=reason)
            assert data.completion_reason == reason


class TestEventTypeConstants:
    """Tests for event type constants."""

    def test_session_started_constant(self):
        """SESSION_STARTED constant has correct value."""
        assert SESSION_STARTED == "SessionStarted"

    def test_session_completed_constant(self):
        """SESSION_COMPLETED constant has correct value."""
        assert SESSION_COMPLETED == "SessionCompleted"

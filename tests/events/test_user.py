"""Tests for user event types."""

from datetime import UTC, datetime

import pytest

from messagedb_agent.events.user import (
    SESSION_TERMINATION_REQUESTED,
    USER_MESSAGE_ADDED,
    SessionTerminationRequestedData,
    UserMessageData,
)


class TestUserMessageData:
    """Tests for UserMessageData event payload."""

    def test_create_user_message_data(self):
        """UserMessageData can be created with valid message and timestamp."""
        timestamp = "2024-01-01T12:00:00Z"
        data = UserMessageData(message="Hello, world!", timestamp=timestamp)

        assert data.message == "Hello, world!"
        assert data.timestamp == timestamp

    def test_user_message_data_is_immutable(self):
        """UserMessageData instances are immutable (frozen)."""
        data = UserMessageData(message="Test", timestamp="2024-01-01T12:00:00Z")

        with pytest.raises(AttributeError):
            data.message = "Modified"  # type: ignore

    def test_user_message_data_validates_empty_message(self):
        """UserMessageData raises ValueError for empty message."""
        with pytest.raises(ValueError, match="User message cannot be empty"):
            UserMessageData(message="", timestamp="2024-01-01T12:00:00Z")

    def test_user_message_data_validates_whitespace_only_message(self):
        """UserMessageData raises ValueError for whitespace-only message."""
        with pytest.raises(ValueError, match="User message cannot be empty"):
            UserMessageData(message="   ", timestamp="2024-01-01T12:00:00Z")

    def test_user_message_data_validates_timestamp_format(self):
        """UserMessageData validates ISO 8601 timestamp format."""
        # Valid formats should work
        UserMessageData(message="Test", timestamp="2024-01-01T12:00:00Z")
        UserMessageData(message="Test", timestamp="2024-01-01T12:00:00+00:00")
        UserMessageData(message="Test", timestamp="2024-01-01T12:00:00.123456Z")

    def test_user_message_data_rejects_invalid_timestamp(self):
        """UserMessageData raises ValueError for invalid timestamp format."""
        with pytest.raises(ValueError, match="Timestamp must be valid ISO 8601 format"):
            UserMessageData(message="Test", timestamp="not-a-timestamp")

    def test_user_message_data_rejects_empty_timestamp(self):
        """UserMessageData raises ValueError for empty timestamp."""
        with pytest.raises(ValueError, match="Timestamp must be valid ISO 8601 format"):
            UserMessageData(message="Test", timestamp="")

    def test_user_message_data_with_multiline_message(self):
        """UserMessageData handles multiline messages."""
        message = """This is a
        multiline
        message"""
        data = UserMessageData(message=message, timestamp="2024-01-01T12:00:00Z")

        assert data.message == message

    def test_user_message_data_with_special_characters(self):
        """UserMessageData handles special characters in message."""
        message = "Hello! @#$%^&*() 你好 🌟"
        data = UserMessageData(message=message, timestamp="2024-01-01T12:00:00Z")

        assert data.message == message

    def test_user_message_data_with_current_timestamp(self):
        """UserMessageData works with current timestamp."""
        now = datetime.now(UTC)
        timestamp = now.isoformat()
        data = UserMessageData(message="Test", timestamp=timestamp)

        assert data.timestamp == timestamp


class TestSessionTerminationRequestedData:
    """Tests for SessionTerminationRequestedData event payload."""

    def test_create_session_termination_data_with_default_reason(self):
        """SessionTerminationRequestedData has default reason 'user_request'."""
        data = SessionTerminationRequestedData()

        assert data.reason == "user_request"

    def test_create_session_termination_data_with_custom_reason(self):
        """SessionTerminationRequestedData can be created with custom reason."""
        data = SessionTerminationRequestedData(reason="timeout")

        assert data.reason == "timeout"

    def test_session_termination_data_is_immutable(self):
        """SessionTerminationRequestedData instances are immutable (frozen)."""
        data = SessionTerminationRequestedData(reason="test")

        with pytest.raises(AttributeError):
            data.reason = "modified"  # type: ignore

    def test_session_termination_data_validates_empty_reason(self):
        """SessionTerminationRequestedData raises ValueError for empty reason."""
        with pytest.raises(ValueError, match="Termination reason cannot be empty"):
            SessionTerminationRequestedData(reason="")

    def test_session_termination_data_validates_whitespace_only_reason(self):
        """SessionTerminationRequestedData raises ValueError for whitespace-only reason."""
        with pytest.raises(ValueError, match="Termination reason cannot be empty"):
            SessionTerminationRequestedData(reason="   ")

    def test_session_termination_data_with_various_reasons(self):
        """SessionTerminationRequestedData accepts various termination reasons."""
        reasons = [
            "user_request",
            "timeout",
            "error",
            "max_iterations_reached",
            "task_completed",
        ]

        for reason in reasons:
            data = SessionTerminationRequestedData(reason=reason)
            assert data.reason == reason


class TestEventTypeConstants:
    """Tests for event type constants."""

    def test_user_message_added_constant(self):
        """USER_MESSAGE_ADDED constant has correct value."""
        assert USER_MESSAGE_ADDED == "UserMessageAdded"

    def test_session_termination_requested_constant(self):
        """SESSION_TERMINATION_REQUESTED constant has correct value."""
        assert SESSION_TERMINATION_REQUESTED == "SessionTerminationRequested"

"""Tests for session lifecycle management."""

from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from messagedb_agent.engine.session import (
    SessionError,
    add_user_message,
    start_session,
    terminate_session,
)
from messagedb_agent.events.system import SESSION_COMPLETED, SESSION_STARTED
from messagedb_agent.events.user import USER_MESSAGE_ADDED


class TestStartSession:
    """Tests for the start_session function."""

    @pytest.fixture
    def mock_store_client(self):
        """Create a mock MessageDB store client."""
        return MagicMock()

    def test_successful_session_start(self, mock_store_client):
        """Test that start_session successfully creates a new session."""
        initial_message = "Hello, I need help with my code"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            with patch("messagedb_agent.engine.session.generate_thread_id") as mock_gen_id:
                # Mock thread_id generation
                test_thread_id = "test-thread-123"
                mock_gen_id.return_value = test_thread_id

                # Start session
                thread_id = start_session(
                    initial_message=initial_message, store_client=mock_store_client
                )

        # Verify thread_id returned
        assert thread_id == test_thread_id

        # Verify write_message was called twice (SessionStarted + UserMessageAdded)
        assert mock_write.call_count == 2

        # Verify first write is SessionStarted
        first_call = mock_write.call_args_list[0][1]
        assert first_call["stream_name"] == f"agent:v0-{test_thread_id}"
        assert first_call["message_type"] == SESSION_STARTED
        assert first_call["data"]["thread_id"] == test_thread_id

        # Verify second write is UserMessageAdded
        second_call = mock_write.call_args_list[1][1]
        assert second_call["stream_name"] == f"agent:v0-{test_thread_id}"
        assert second_call["message_type"] == USER_MESSAGE_ADDED
        assert second_call["data"]["message"] == initial_message
        assert "timestamp" in second_call["data"]

    def test_returns_valid_thread_id(self, mock_store_client):
        """Test that start_session returns a valid UUID thread_id."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0):
            thread_id = start_session(
                initial_message="Test message", store_client=mock_store_client
            )

        # Verify it's a valid UUID string
        assert isinstance(thread_id, str)
        # Should be able to parse as UUID
        uuid_obj = UUID(thread_id)
        assert str(uuid_obj) == thread_id

    def test_generates_unique_thread_ids(self, mock_store_client):
        """Test that multiple sessions get unique thread IDs."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0):
            thread_id1 = start_session(
                initial_message="First message", store_client=mock_store_client
            )
            thread_id2 = start_session(
                initial_message="Second message", store_client=mock_store_client
            )

        # Thread IDs should be different
        assert thread_id1 != thread_id2

    def test_uses_default_category_and_version(self, mock_store_client):
        """Test that default category and version are used."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            with patch("messagedb_agent.engine.session.generate_thread_id") as mock_gen_id:
                test_thread_id = "test-123"
                mock_gen_id.return_value = test_thread_id

                start_session(initial_message="Test", store_client=mock_store_client)

        # Verify default stream name format: agent:v0-{threadId}
        stream_name = mock_write.call_args_list[0][1]["stream_name"]
        assert stream_name == f"agent:v0-{test_thread_id}"

    def test_uses_custom_category_and_version(self, mock_store_client):
        """Test that custom category and version can be specified."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            with patch("messagedb_agent.engine.session.generate_thread_id") as mock_gen_id:
                test_thread_id = "test-123"
                mock_gen_id.return_value = test_thread_id

                start_session(
                    initial_message="Test",
                    store_client=mock_store_client,
                    category="custom",
                    version="v1",
                )

        # Verify custom stream name format
        stream_name = mock_write.call_args_list[0][1]["stream_name"]
        assert stream_name == f"custom:v1-{test_thread_id}"

    def test_timestamp_is_iso8601_format(self, mock_store_client):
        """Test that UserMessageAdded event has ISO 8601 timestamp."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            start_session(initial_message="Test", store_client=mock_store_client)

        # Get timestamp from UserMessageAdded event
        user_message_call = mock_write.call_args_list[1][1]
        timestamp = user_message_call["data"]["timestamp"]

        # Verify it's a valid ISO 8601 timestamp
        parsed = datetime.fromisoformat(timestamp)
        assert parsed.tzinfo is not None  # Should have timezone info
        assert isinstance(parsed, datetime)

    def test_validates_empty_message(self, mock_store_client):
        """Test that empty initial_message raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            start_session(initial_message="", store_client=mock_store_client)

    def test_validates_whitespace_only_message(self, mock_store_client):
        """Test that whitespace-only initial_message raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            start_session(initial_message="   \n\t  ", store_client=mock_store_client)

    def test_raises_error_if_session_started_write_fails(self, mock_store_client):
        """Test that SessionError is raised if SessionStarted event write fails."""
        with patch(
            "messagedb_agent.engine.session.write_message",
            side_effect=Exception("Database error"),
        ):
            with pytest.raises(SessionError, match="Failed to write SessionStarted event"):
                start_session(initial_message="Test", store_client=mock_store_client)

    def test_raises_error_if_user_message_write_fails(self, mock_store_client):
        """Test that SessionError is raised if UserMessageAdded event write fails."""
        # First write succeeds (SessionStarted), second fails (UserMessageAdded)
        with patch(
            "messagedb_agent.engine.session.write_message",
            side_effect=[0, Exception("Database error")],
        ):
            with pytest.raises(SessionError, match="Failed to write UserMessageAdded event"):
                start_session(initial_message="Test", store_client=mock_store_client)

    def test_preserves_multiline_message(self, mock_store_client):
        """Test that multiline messages are preserved correctly."""
        multiline_message = "Line 1\nLine 2\nLine 3"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            start_session(initial_message=multiline_message, store_client=mock_store_client)

        # Verify message preserved
        user_message_call = mock_write.call_args_list[1][1]
        assert user_message_call["data"]["message"] == multiline_message

    def test_preserves_special_characters(self, mock_store_client):
        """Test that messages with special characters are preserved."""
        special_message = 'Hello "world" with <tags> & symbols!'

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            start_session(initial_message=special_message, store_client=mock_store_client)

        # Verify message preserved
        user_message_call = mock_write.call_args_list[1][1]
        assert user_message_call["data"]["message"] == special_message

    def test_events_written_in_correct_order(self, mock_store_client):
        """Test that SessionStarted is written before UserMessageAdded."""
        write_order = []

        def track_writes(**kwargs):
            write_order.append(kwargs["message_type"])
            return len(write_order) - 1

        with patch("messagedb_agent.engine.session.write_message", side_effect=track_writes):
            start_session(initial_message="Test", store_client=mock_store_client)

        # Verify order
        assert write_order == [SESSION_STARTED, USER_MESSAGE_ADDED]

    def test_session_started_event_structure(self, mock_store_client):
        """Test that SessionStarted event has correct structure."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            with patch("messagedb_agent.engine.session.generate_thread_id") as mock_gen_id:
                test_thread_id = "test-123"
                mock_gen_id.return_value = test_thread_id

                start_session(initial_message="Test", store_client=mock_store_client)

        # Verify SessionStarted event structure
        session_started_call = mock_write.call_args_list[0][1]
        assert session_started_call["client"] == mock_store_client
        assert session_started_call["stream_name"] == f"agent:v0-{test_thread_id}"
        assert session_started_call["message_type"] == SESSION_STARTED
        assert session_started_call["data"] == {"thread_id": test_thread_id}
        assert session_started_call["metadata"] == {}

    def test_user_message_event_structure(self, mock_store_client):
        """Test that UserMessageAdded event has correct structure."""
        test_message = "Hello, world!"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            start_session(initial_message=test_message, store_client=mock_store_client)

        # Verify UserMessageAdded event structure
        user_message_call = mock_write.call_args_list[1][1]
        assert user_message_call["client"] == mock_store_client
        assert user_message_call["message_type"] == USER_MESSAGE_ADDED
        assert user_message_call["data"]["message"] == test_message
        assert "timestamp" in user_message_call["data"]
        assert user_message_call["metadata"] == {}

    def test_long_message_handling(self, mock_store_client):
        """Test that very long messages are handled correctly."""
        long_message = "A" * 10000  # 10k character message

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            start_session(initial_message=long_message, store_client=mock_store_client)

        # Verify long message preserved
        user_message_call = mock_write.call_args_list[1][1]
        assert user_message_call["data"]["message"] == long_message
        assert len(user_message_call["data"]["message"]) == 10000


class TestTerminateSession:
    """Tests for the terminate_session function."""

    @pytest.fixture
    def mock_store_client(self):
        """Create a mock MessageDB store client."""
        return MagicMock()

    def test_successful_session_termination(self, mock_store_client):
        """Test that terminate_session successfully terminates a session."""
        thread_id = "test-thread-123"
        reason = "success"

        with patch("messagedb_agent.engine.session.write_message", return_value=5) as mock_write:
            position = terminate_session(
                thread_id=thread_id, reason=reason, store_client=mock_store_client
            )

        # Verify position returned
        assert position == 5

        # Verify write_message was called once
        assert mock_write.call_count == 1

        # Verify SessionCompleted event written
        call_args = mock_write.call_args[1]
        assert call_args["stream_name"] == f"agent:v0-{thread_id}"
        assert call_args["message_type"] == SESSION_COMPLETED
        assert call_args["data"]["completion_reason"] == reason

    def test_uses_default_category_and_version(self, mock_store_client):
        """Test that default category and version are used."""
        thread_id = "test-123"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            terminate_session(thread_id=thread_id, reason="success", store_client=mock_store_client)

        # Verify default stream name format
        stream_name = mock_write.call_args[1]["stream_name"]
        assert stream_name == f"agent:v0-{thread_id}"

    def test_uses_custom_category_and_version(self, mock_store_client):
        """Test that custom category and version can be specified."""
        thread_id = "test-123"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            terminate_session(
                thread_id=thread_id,
                reason="success",
                store_client=mock_store_client,
                category="custom",
                version="v1",
            )

        # Verify custom stream name format
        stream_name = mock_write.call_args[1]["stream_name"]
        assert stream_name == f"custom:v1-{thread_id}"

    def test_validates_empty_thread_id(self, mock_store_client):
        """Test that empty thread_id raises ValueError."""
        with pytest.raises(ValueError, match="thread_id cannot be empty"):
            terminate_session(thread_id="", reason="success", store_client=mock_store_client)

    def test_validates_whitespace_only_thread_id(self, mock_store_client):
        """Test that whitespace-only thread_id raises ValueError."""
        with pytest.raises(ValueError, match="thread_id cannot be empty"):
            terminate_session(
                thread_id="   \n\t  ", reason="success", store_client=mock_store_client
            )

    def test_validates_empty_reason(self, mock_store_client):
        """Test that empty reason raises ValueError."""
        with pytest.raises(ValueError, match="reason cannot be empty"):
            terminate_session(thread_id="test-123", reason="", store_client=mock_store_client)

    def test_validates_whitespace_only_reason(self, mock_store_client):
        """Test that whitespace-only reason raises ValueError."""
        with pytest.raises(ValueError, match="reason cannot be empty"):
            terminate_session(
                thread_id="test-123", reason="   \n\t  ", store_client=mock_store_client
            )

    def test_raises_error_if_event_write_fails(self, mock_store_client):
        """Test that SessionError is raised if SessionCompleted event write fails."""
        with patch(
            "messagedb_agent.engine.session.write_message",
            side_effect=Exception("Database error"),
        ):
            with pytest.raises(SessionError, match="Failed to write SessionCompleted event"):
                terminate_session(
                    thread_id="test-123", reason="success", store_client=mock_store_client
                )

    def test_various_termination_reasons(self, mock_store_client):
        """Test that various termination reasons are handled correctly."""
        reasons = ["success", "failure", "timeout", "user_request", "error", "custom_reason"]

        for reason in reasons:
            with patch(
                "messagedb_agent.engine.session.write_message", return_value=0
            ) as mock_write:
                terminate_session(
                    thread_id="test-123", reason=reason, store_client=mock_store_client
                )

                # Verify reason preserved
                call_args = mock_write.call_args[1]
                assert call_args["data"]["completion_reason"] == reason

    def test_event_structure(self, mock_store_client):
        """Test that SessionCompleted event has correct structure."""
        thread_id = "test-123"
        reason = "success"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            terminate_session(thread_id=thread_id, reason=reason, store_client=mock_store_client)

        # Verify event structure
        call_args = mock_write.call_args[1]
        assert call_args["client"] == mock_store_client
        assert call_args["stream_name"] == f"agent:v0-{thread_id}"
        assert call_args["message_type"] == SESSION_COMPLETED
        assert call_args["data"] == {"completion_reason": reason}
        assert call_args["metadata"] == {}

    def test_returns_correct_position(self, mock_store_client):
        """Test that terminate_session returns the correct event position."""
        expected_positions = [0, 5, 10, 100]

        for expected_pos in expected_positions:
            with patch("messagedb_agent.engine.session.write_message", return_value=expected_pos):
                actual_pos = terminate_session(
                    thread_id="test-123", reason="success", store_client=mock_store_client
                )
                assert actual_pos == expected_pos

    def test_long_reason_handling(self, mock_store_client):
        """Test that very long reasons are handled correctly."""
        long_reason = "A" * 1000  # 1k character reason

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            terminate_session(
                thread_id="test-123", reason=long_reason, store_client=mock_store_client
            )

        # Verify long reason preserved
        call_args = mock_write.call_args[1]
        assert call_args["data"]["completion_reason"] == long_reason
        assert len(call_args["data"]["completion_reason"]) == 1000

    def test_special_characters_in_reason(self, mock_store_client):
        """Test that reasons with special characters are preserved."""
        special_reason = 'Error: "Connection failed" <timeout> & retry failed!'

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            terminate_session(
                thread_id="test-123", reason=special_reason, store_client=mock_store_client
            )

        # Verify special characters preserved
        call_args = mock_write.call_args[1]
        assert call_args["data"]["completion_reason"] == special_reason

    def test_multiline_reason(self, mock_store_client):
        """Test that multiline reasons are preserved correctly."""
        multiline_reason = "Line 1\nLine 2\nLine 3"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            terminate_session(
                thread_id="test-123", reason=multiline_reason, store_client=mock_store_client
            )

        # Verify multiline reason preserved
        call_args = mock_write.call_args[1]
        assert call_args["data"]["completion_reason"] == multiline_reason


class TestAddUserMessage:
    """Tests for the add_user_message function."""

    @pytest.fixture
    def mock_store_client(self):
        """Create a mock MessageDB store client."""
        return MagicMock()

    def test_successful_message_addition(self, mock_store_client):
        """Test successful addition of a user message to existing thread."""
        with patch("messagedb_agent.engine.session.write_message", return_value=5) as mock_write:
            position = add_user_message(
                thread_id="abc-123", message="Hello again!", store_client=mock_store_client
            )

        # Verify write_message was called
        assert mock_write.call_count == 1
        assert position == 5

    def test_returns_valid_position(self, mock_store_client):
        """Test that the function returns the position from write_message."""
        with patch("messagedb_agent.engine.session.write_message", return_value=42):
            position = add_user_message(
                thread_id="test-id", message="Test message", store_client=mock_store_client
            )

        assert position == 42

    def test_uses_default_category_and_version(self, mock_store_client):
        """Test default category and version are used."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            add_user_message(
                thread_id="test-123", message="Test message", store_client=mock_store_client
            )

        # Verify stream name uses defaults
        call_args = mock_write.call_args[1]
        assert call_args["stream_name"] == "agent:v0-test-123"

    def test_uses_custom_category_and_version(self, mock_store_client):
        """Test custom category and version are used."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            add_user_message(
                thread_id="test-123",
                message="Test message",
                store_client=mock_store_client,
                category="custom",
                version="v2",
            )

        # Verify stream name uses custom values
        call_args = mock_write.call_args[1]
        assert call_args["stream_name"] == "custom:v2-test-123"

    def test_timestamp_is_iso8601_format(self, mock_store_client):
        """Test that timestamp is in ISO 8601 format."""
        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            add_user_message(
                thread_id="test-123", message="Test message", store_client=mock_store_client
            )

        # Verify timestamp format
        call_args = mock_write.call_args[1]
        timestamp = call_args["data"]["timestamp"]
        # Should be able to parse as ISO 8601
        datetime.fromisoformat(timestamp)

    def test_validates_empty_thread_id(self, mock_store_client):
        """Test that empty thread_id raises ValueError."""
        with pytest.raises(ValueError, match="thread_id cannot be empty"):
            add_user_message(thread_id="", message="Test message", store_client=mock_store_client)

    def test_validates_whitespace_only_thread_id(self, mock_store_client):
        """Test that whitespace-only thread_id raises ValueError."""
        with pytest.raises(ValueError, match="thread_id cannot be empty"):
            add_user_message(
                thread_id="   ", message="Test message", store_client=mock_store_client
            )

    def test_validates_empty_message(self, mock_store_client):
        """Test that empty message raises ValueError."""
        with pytest.raises(ValueError, match="message cannot be empty"):
            add_user_message(thread_id="test-123", message="", store_client=mock_store_client)

    def test_validates_whitespace_only_message(self, mock_store_client):
        """Test that whitespace-only message raises ValueError."""
        with pytest.raises(ValueError, match="message cannot be empty"):
            add_user_message(
                thread_id="test-123", message="   \n\t  ", store_client=mock_store_client
            )

    def test_raises_error_if_write_fails(self, mock_store_client):
        """Test that SessionError is raised if write_message fails."""
        with patch(
            "messagedb_agent.engine.session.write_message", side_effect=Exception("Database error")
        ):
            with pytest.raises(SessionError, match="Failed to write UserMessageAdded"):
                add_user_message(
                    thread_id="test-123", message="Test message", store_client=mock_store_client
                )

    def test_preserves_multiline_message(self, mock_store_client):
        """Test that multiline messages are preserved correctly."""
        multiline_message = "Line 1\nLine 2\nLine 3"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            add_user_message(
                thread_id="test-123", message=multiline_message, store_client=mock_store_client
            )

        # Verify multiline message preserved
        call_args = mock_write.call_args[1]
        assert call_args["data"]["message"] == multiline_message

    def test_preserves_special_characters(self, mock_store_client):
        """Test that special characters in messages are preserved."""
        special_message = "Test with émojis 🎉 and symbols: @#$%^&*()"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            add_user_message(
                thread_id="test-123", message=special_message, store_client=mock_store_client
            )

        # Verify special characters preserved
        call_args = mock_write.call_args[1]
        assert call_args["data"]["message"] == special_message

    def test_user_message_event_structure(self, mock_store_client):
        """Test that UserMessageAdded event has correct structure."""
        test_message = "Test message content"

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            add_user_message(
                thread_id="test-123", message=test_message, store_client=mock_store_client
            )

        # Verify event structure
        call_args = mock_write.call_args[1]
        assert call_args["message_type"] == USER_MESSAGE_ADDED
        assert call_args["data"]["message"] == test_message
        assert "timestamp" in call_args["data"]
        assert call_args["metadata"] == {}

    def test_long_message_handling(self, mock_store_client):
        """Test that very long messages are handled correctly."""
        long_message = "x" * 10000  # 10K character message

        with patch("messagedb_agent.engine.session.write_message", return_value=0) as mock_write:
            add_user_message(
                thread_id="test-123", message=long_message, store_client=mock_store_client
            )

        # Verify long message preserved
        call_args = mock_write.call_args[1]
        assert call_args["data"]["message"] == long_message
        assert len(call_args["data"]["message"]) == 10000

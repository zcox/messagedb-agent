"""Tests for Message DB operations (write_message and read_stream).

These tests use a real Message DB container managed by pytest-docker
and verify the complete read/write lifecycle of messages.
"""

import uuid
from datetime import datetime

import pytest

from messagedb_agent.store import (
    MessageDBClient,
    OptimisticConcurrencyError,
    get_last_stream_message,
    read_stream,
    write_message,
)


@pytest.fixture
def test_stream_name() -> str:
    """Generate a unique stream name for each test."""
    thread_id = str(uuid.uuid4())
    return f"agent:v0-{thread_id}"


class TestWriteMessage:
    """Tests for write_message function."""

    def test_write_single_message(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing a single message to a stream."""
        with messagedb_client:
            position = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "Hello, world!", "timestamp": "2025-10-19T10:00:00Z"},
                metadata={"user_id": "user123"},
            )

            assert position == 0  # First message is at position 0

    def test_write_multiple_messages(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing multiple messages to the same stream."""
        with messagedb_client:
            pos1 = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            pos2 = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "First message"},
            )

            pos3 = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "Second message"},
            )

            assert pos1 == 0
            assert pos2 == 1
            assert pos3 == 2

    def test_write_message_without_metadata(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing a message without metadata."""
        with messagedb_client:
            position = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
                metadata=None,
            )

            assert position == 0

    def test_write_message_with_complex_data(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing a message with complex nested data."""
        with messagedb_client:
            complex_data = {
                "user_message": "What's the weather?",
                "tool_calls": [
                    {"id": "call1", "name": "get_weather", "args": {"location": "NYC"}},
                    {
                        "id": "call2",
                        "name": "get_forecast",
                        "args": {"location": "NYC", "days": 5},
                    },
                ],
                "token_usage": {"prompt": 100, "completion": 50, "total": 150},
            }

            position = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="LLMResponseReceived",
                data=complex_data,
            )

            assert position == 0

    def test_optimistic_concurrency_success(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test successful optimistic concurrency control."""
        with messagedb_client:
            # Write first message without OCC
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            # Write second message with correct expected_version
            position = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "Hello"},
                expected_version=0,  # Stream is at version 0 after first write
            )

            assert position == 1

    def test_optimistic_concurrency_failure(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test optimistic concurrency control failure."""
        with messagedb_client:
            # Write first message
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            # Try to write with wrong expected_version
            with pytest.raises(OptimisticConcurrencyError) as exc_info:
                write_message(
                    client=messagedb_client,
                    stream_name=test_stream_name,
                    message_type="UserMessageAdded",
                    data={"message": "Hello"},
                    expected_version=5,  # Wrong version
                )

            error = exc_info.value
            assert error.stream_name == test_stream_name
            assert error.expected_version == 5
            # actual_version should be 0 (position of last message)
            assert error.actual_version == 0

    def test_optimistic_concurrency_empty_stream_success(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing to empty stream with expected_version=-1 succeeds."""
        with messagedb_client:
            # Write first message with expected_version=-1 (stream must be empty)
            position = write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
                expected_version=-1,  # Stream must be empty
            )

            assert position == 0

    def test_optimistic_concurrency_empty_stream_failure(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing to non-empty stream with expected_version=-1 fails."""
        with messagedb_client:
            # Write first message without OCC
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            # Try to write with expected_version=-1 (but stream is not empty)
            with pytest.raises(OptimisticConcurrencyError) as exc_info:
                write_message(
                    client=messagedb_client,
                    stream_name=test_stream_name,
                    message_type="UserMessageAdded",
                    data={"message": "Hello"},
                    expected_version=-1,  # Stream must be empty, but it's not
                )

            error = exc_info.value
            assert error.stream_name == test_stream_name
            assert error.expected_version == -1
            # actual_version should be 0 (position of last message)
            assert error.actual_version == 0


class TestReadStream:
    """Tests for read_stream function."""

    def test_read_empty_stream(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading from an empty stream."""
        with messagedb_client:
            messages = read_stream(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert messages == []

    def test_read_single_message(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading a single message from a stream."""
        with messagedb_client:
            # Write a message
            message_data = {
                "message": "Hello, world!",
                "timestamp": "2025-10-19T10:00:00Z",
            }
            message_metadata = {"user_id": "user123"}

            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data=message_data,
                metadata=message_metadata,
            )

            # Read the message
            messages = read_stream(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert len(messages) == 1
            message = messages[0]

            assert message.stream_name == test_stream_name
            assert message.type == "UserMessageAdded"
            assert message.position == 0
            assert message.data == message_data
            assert message.metadata == message_metadata
            assert isinstance(message.time, datetime)
            assert isinstance(message.id, str)
            assert isinstance(message.global_position, int)

    def test_read_multiple_messages(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading multiple messages from a stream."""
        with messagedb_client:
            # Write multiple messages
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "First message"},
            )

            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "Second message"},
            )

            # Read all messages
            messages = read_stream(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert len(messages) == 3
            assert messages[0].type == "SessionStarted"
            assert messages[0].position == 0
            assert messages[1].type == "UserMessageAdded"
            assert messages[1].position == 1
            assert messages[1].data == {"message": "First message"}
            assert messages[2].type == "UserMessageAdded"
            assert messages[2].position == 2
            assert messages[2].data == {"message": "Second message"}

    def test_read_from_position(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading from a specific position."""
        with messagedb_client:
            # Write multiple messages
            for i in range(5):
                write_message(
                    client=messagedb_client,
                    stream_name=test_stream_name,
                    message_type="UserMessageAdded",
                    data={"message": f"Message {i}"},
                )

            # Read from position 2
            messages = read_stream(
                client=messagedb_client, stream_name=test_stream_name, position=2
            )

            assert len(messages) == 3  # Positions 2, 3, 4
            assert messages[0].position == 2
            assert messages[0].data == {"message": "Message 2"}
            assert messages[1].position == 3
            assert messages[2].position == 4

    def test_read_with_batch_size(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading with a batch size limit."""
        with messagedb_client:
            # Write 10 messages
            for i in range(10):
                write_message(
                    client=messagedb_client,
                    stream_name=test_stream_name,
                    message_type="UserMessageAdded",
                    data={"message": f"Message {i}"},
                )

            # Read with batch size of 5
            messages = read_stream(
                client=messagedb_client, stream_name=test_stream_name, batch_size=5
            )

            assert len(messages) == 5
            assert messages[0].position == 0
            assert messages[4].position == 4

    def test_read_message_without_metadata(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading a message that has no metadata."""
        with messagedb_client:
            # Write message without metadata
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
                metadata=None,
            )

            # Read the message
            messages = read_stream(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert len(messages) == 1
            assert messages[0].metadata is None

    def test_read_message_with_complex_data(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading a message with complex nested data."""
        with messagedb_client:
            complex_data = {
                "user_message": "What's the weather?",
                "tool_calls": [
                    {"id": "call1", "name": "get_weather", "args": {"location": "NYC"}},
                    {
                        "id": "call2",
                        "name": "get_forecast",
                        "args": {"location": "NYC", "days": 5},
                    },
                ],
                "token_usage": {"prompt": 100, "completion": 50, "total": 150},
            }

            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="LLMResponseReceived",
                data=complex_data,
            )

            # Read the message
            messages = read_stream(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert len(messages) == 1
            assert messages[0].data == complex_data


class TestWriteReadIntegration:
    """Integration tests for write_message and read_stream together."""

    def test_write_and_read_lifecycle(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test complete write and read lifecycle."""
        with messagedb_client:
            # Simulate a simple agent session
            # 1. Start session
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": test_stream_name.split("-")[1]},
            )

            # 2. User sends message
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "What's 2+2?"},
            )

            # 3. LLM responds
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="LLMResponseReceived",
                data={"response": "2+2 equals 4", "tool_calls": []},
            )

            # 4. Session completes
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionCompleted",
                data={"reason": "success"},
            )

            # Read all messages and verify
            messages = read_stream(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert len(messages) == 4
            assert messages[0].type == "SessionStarted"
            assert messages[1].type == "UserMessageAdded"
            assert messages[2].type == "LLMResponseReceived"
            assert messages[3].type == "SessionCompleted"

            # Verify ordering
            for i, message in enumerate(messages):
                assert message.position == i

            # Verify global_position is increasing
            for i in range(1, len(messages)):
                assert messages[i].global_position > messages[i - 1].global_position


class TestGetLastStreamMessage:
    """Tests for get_last_stream_message function."""

    def test_get_last_message_from_empty_stream(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test getting last message from an empty stream returns None."""
        with messagedb_client:
            message = get_last_stream_message(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert message is None

    def test_get_last_message_single_message(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test getting last message when stream has one message."""
        with messagedb_client:
            # Write a message
            message_data = {
                "message": "Hello, world!",
                "timestamp": "2025-10-19T10:00:00Z",
            }
            message_metadata = {"user_id": "user123"}

            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data=message_data,
                metadata=message_metadata,
            )

            # Get the last message
            message = get_last_stream_message(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert message is not None
            assert message.stream_name == test_stream_name
            assert message.type == "UserMessageAdded"
            assert message.position == 0
            assert message.data == message_data
            assert message.metadata == message_metadata
            assert isinstance(message.time, datetime)
            assert isinstance(message.id, str)
            assert isinstance(message.global_position, int)

    def test_get_last_message_multiple_messages(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test getting last message when stream has multiple messages."""
        with messagedb_client:
            # Write multiple messages
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data={"message": "First message"},
            )

            last_message_data = {"message": "Last message"}
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="UserMessageAdded",
                data=last_message_data,
            )

            # Get the last message
            message = get_last_stream_message(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert message is not None
            assert message.type == "UserMessageAdded"
            assert message.position == 2
            assert message.data == last_message_data

    def test_get_last_message_without_metadata(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test getting last message that has no metadata."""
        with messagedb_client:
            # Write message without metadata
            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="SessionStarted",
                data={"thread_id": "thread123"},
                metadata=None,
            )

            # Get the last message
            message = get_last_stream_message(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert message is not None
            assert message.metadata is None

    def test_get_last_message_with_complex_data(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test getting last message with complex nested data."""
        with messagedb_client:
            complex_data = {
                "user_message": "What's the weather?",
                "tool_calls": [
                    {"id": "call1", "name": "get_weather", "args": {"location": "NYC"}},
                    {
                        "id": "call2",
                        "name": "get_forecast",
                        "args": {"location": "NYC", "days": 5},
                    },
                ],
                "token_usage": {"prompt": 100, "completion": 50, "total": 150},
            }

            write_message(
                client=messagedb_client,
                stream_name=test_stream_name,
                message_type="LLMResponseReceived",
                data=complex_data,
            )

            # Get the last message
            message = get_last_stream_message(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            assert message is not None
            assert message.data == complex_data

    def test_get_last_message_efficiency(
        self, messagedb_client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test that get_last_stream_message is more efficient than read_stream."""
        with messagedb_client:
            # Write many messages
            for i in range(100):
                write_message(
                    client=messagedb_client,
                    stream_name=test_stream_name,
                    message_type="UserMessageAdded",
                    data={"message": f"Message {i}"},
                )

            # Get last message using get_last_stream_message
            last_message = get_last_stream_message(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            # Also read entire stream for comparison
            all_messages = read_stream(
                client=messagedb_client,
                stream_name=test_stream_name,
            )

            # They should return the same last message
            assert last_message is not None
            assert last_message.position == 99
            assert last_message.data == {"message": "Message 99"}
            assert last_message.position == all_messages[-1].position
            assert last_message.data == all_messages[-1].data
            assert last_message.type == all_messages[-1].type

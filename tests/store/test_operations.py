"""Tests for Message DB operations (write_event and read_stream).

These tests use a real Message DB container and verify the complete
read/write lifecycle of events.
"""

import uuid
from datetime import datetime

import pytest

from messagedb_agent.store import (
    MessageDBClient,
    MessageDBConfig,
    OptimisticConcurrencyError,
    read_stream,
    write_event,
)


@pytest.fixture
def config() -> MessageDBConfig:
    """Create a MessageDBConfig for testing.

    Note: This assumes Message DB is running locally on default port.
    In a real test setup, this would use a docker-compose container.
    """
    return MessageDBConfig()


@pytest.fixture
def client(config: MessageDBConfig) -> MessageDBClient:
    """Create a MessageDBClient for testing."""
    return MessageDBClient(config)


@pytest.fixture
def test_stream_name() -> str:
    """Generate a unique stream name for each test."""
    thread_id = str(uuid.uuid4())
    return f"agent:v0-{thread_id}"


class TestWriteEvent:
    """Tests for write_event function."""

    def test_write_single_event(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test writing a single event to a stream."""
        with client:
            position = write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data={"message": "Hello, world!", "timestamp": "2025-10-19T10:00:00Z"},
                metadata={"user_id": "user123"},
            )

            assert position == 0  # First event is at position 0

    def test_write_multiple_events(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test writing multiple events to the same stream."""
        with client:
            pos1 = write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            pos2 = write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data={"message": "First message"},
            )

            pos3 = write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data={"message": "Second message"},
            )

            assert pos1 == 0
            assert pos2 == 1
            assert pos3 == 2

    def test_write_event_without_metadata(
        self, client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing an event without metadata."""
        with client:
            position = write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionStarted",
                data={"thread_id": "thread123"},
                metadata=None,
            )

            assert position == 0

    def test_write_event_with_complex_data(
        self, client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test writing an event with complex nested data."""
        with client:
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

            position = write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="LLMResponseReceived",
                data=complex_data,
            )

            assert position == 0

    def test_optimistic_concurrency_success(
        self, client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test successful optimistic concurrency control."""
        with client:
            # Write first event without OCC
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            # Write second event with correct expected_version
            position = write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data={"message": "Hello"},
                expected_version=0,  # Stream is at version 0 after first write
            )

            assert position == 1

    def test_optimistic_concurrency_failure(
        self, client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test optimistic concurrency control failure."""
        with client:
            # Write first event
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            # Try to write with wrong expected_version
            with pytest.raises(OptimisticConcurrencyError) as exc_info:
                write_event(
                    client=client,
                    stream_name=test_stream_name,
                    event_type="UserMessageAdded",
                    data={"message": "Hello"},
                    expected_version=5,  # Wrong version
                )

            error = exc_info.value
            assert error.stream_name == test_stream_name
            assert error.expected_version == 5
            # actual_version should be 0 (position of last event)
            assert error.actual_version == 0


class TestReadStream:
    """Tests for read_stream function."""

    def test_read_empty_stream(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test reading from an empty stream."""
        with client:
            events = read_stream(
                client=client,
                stream_name=test_stream_name,
            )

            assert events == []

    def test_read_single_event(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test reading a single event from a stream."""
        with client:
            # Write an event
            event_data = {
                "message": "Hello, world!",
                "timestamp": "2025-10-19T10:00:00Z",
            }
            event_metadata = {"user_id": "user123"}

            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data=event_data,
                metadata=event_metadata,
            )

            # Read the event
            events = read_stream(
                client=client,
                stream_name=test_stream_name,
            )

            assert len(events) == 1
            event = events[0]

            assert event.stream_name == test_stream_name
            assert event.type == "UserMessageAdded"
            assert event.position == 0
            assert event.data == event_data
            assert event.metadata == event_metadata
            assert isinstance(event.time, datetime)
            assert isinstance(event.id, str)
            assert isinstance(event.global_position, int)

    def test_read_multiple_events(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test reading multiple events from a stream."""
        with client:
            # Write multiple events
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionStarted",
                data={"thread_id": "thread123"},
            )

            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data={"message": "First message"},
            )

            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data={"message": "Second message"},
            )

            # Read all events
            events = read_stream(
                client=client,
                stream_name=test_stream_name,
            )

            assert len(events) == 3
            assert events[0].type == "SessionStarted"
            assert events[0].position == 0
            assert events[1].type == "UserMessageAdded"
            assert events[1].position == 1
            assert events[1].data == {"message": "First message"}
            assert events[2].type == "UserMessageAdded"
            assert events[2].position == 2
            assert events[2].data == {"message": "Second message"}

    def test_read_from_position(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test reading from a specific position."""
        with client:
            # Write multiple events
            for i in range(5):
                write_event(
                    client=client,
                    stream_name=test_stream_name,
                    event_type="UserMessageAdded",
                    data={"message": f"Message {i}"},
                )

            # Read from position 2
            events = read_stream(client=client, stream_name=test_stream_name, position=2)

            assert len(events) == 3  # Positions 2, 3, 4
            assert events[0].position == 2
            assert events[0].data == {"message": "Message 2"}
            assert events[1].position == 3
            assert events[2].position == 4

    def test_read_with_batch_size(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test reading with a batch size limit."""
        with client:
            # Write 10 events
            for i in range(10):
                write_event(
                    client=client,
                    stream_name=test_stream_name,
                    event_type="UserMessageAdded",
                    data={"message": f"Message {i}"},
                )

            # Read with batch size of 5
            events = read_stream(client=client, stream_name=test_stream_name, batch_size=5)

            assert len(events) == 5
            assert events[0].position == 0
            assert events[4].position == 4

    def test_read_event_without_metadata(
        self, client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading an event that has no metadata."""
        with client:
            # Write event without metadata
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionStarted",
                data={"thread_id": "thread123"},
                metadata=None,
            )

            # Read the event
            events = read_stream(
                client=client,
                stream_name=test_stream_name,
            )

            assert len(events) == 1
            assert events[0].metadata is None

    def test_read_event_with_complex_data(
        self, client: MessageDBClient, test_stream_name: str
    ) -> None:
        """Test reading an event with complex nested data."""
        with client:
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

            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="LLMResponseReceived",
                data=complex_data,
            )

            # Read the event
            events = read_stream(
                client=client,
                stream_name=test_stream_name,
            )

            assert len(events) == 1
            assert events[0].data == complex_data


class TestWriteReadIntegration:
    """Integration tests for write_event and read_stream together."""

    def test_write_and_read_lifecycle(self, client: MessageDBClient, test_stream_name: str) -> None:
        """Test complete write and read lifecycle."""
        with client:
            # Simulate a simple agent session
            # 1. Start session
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionStarted",
                data={"thread_id": test_stream_name.split("-")[1]},
            )

            # 2. User sends message
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="UserMessageAdded",
                data={"message": "What's 2+2?"},
            )

            # 3. LLM responds
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="LLMResponseReceived",
                data={"response": "2+2 equals 4", "tool_calls": []},
            )

            # 4. Session completes
            write_event(
                client=client,
                stream_name=test_stream_name,
                event_type="SessionCompleted",
                data={"reason": "success"},
            )

            # Read all events and verify
            events = read_stream(
                client=client,
                stream_name=test_stream_name,
            )

            assert len(events) == 4
            assert events[0].type == "SessionStarted"
            assert events[1].type == "UserMessageAdded"
            assert events[2].type == "LLMResponseReceived"
            assert events[3].type == "SessionCompleted"

            # Verify ordering
            for i, event in enumerate(events):
                assert event.position == i

            # Verify global_position is increasing
            for i in range(1, len(events)):
                assert events[i].global_position > events[i - 1].global_position

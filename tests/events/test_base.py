"""Tests for base event structure and types."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from messagedb_agent.events.base import BaseEvent, EventData


class TestEventData:
    """Tests for EventData base class."""

    def test_event_data_is_immutable(self):
        """EventData subclasses should be immutable when frozen."""

        @dataclass(frozen=True)
        class SampleData(EventData):
            value: str

        data = SampleData(value="test")
        with pytest.raises(AttributeError):
            data.value = "modified"  # type: ignore

    def test_event_data_can_be_subclassed(self):
        """EventData can be subclassed for custom event payloads."""

        @dataclass(frozen=True)
        class UserMessageData(EventData):
            message: str
            timestamp: datetime

        now = datetime.now()
        data = UserMessageData(message="Hello", timestamp=now)
        assert data.message == "Hello"
        assert data.timestamp == now


class TestBaseEvent:
    """Tests for BaseEvent structure."""

    def test_create_base_event(self):
        """BaseEvent can be created with all required fields."""
        event_id = uuid4()
        event_time = datetime.now()
        event = BaseEvent(
            id=event_id,
            type="TestEvent",
            data={"key": "value"},
            metadata={"trace_id": "123"},
            position=0,
            global_position=100,
            time=event_time,
            stream_name="test:v0-thread123",
        )

        assert event.id == event_id
        assert event.type == "TestEvent"
        assert event.data == {"key": "value"}
        assert event.metadata == {"trace_id": "123"}
        assert event.position == 0
        assert event.global_position == 100
        assert event.time == event_time
        assert event.stream_name == "test:v0-thread123"

    def test_base_event_is_immutable(self):
        """BaseEvent instances are immutable (frozen)."""
        event = BaseEvent(
            id=uuid4(),
            type="TestEvent",
            data={},
            metadata={},
            position=0,
            global_position=0,
            time=datetime.now(),
            stream_name="test:v0-thread123",
        )

        with pytest.raises(AttributeError):
            event.type = "ModifiedEvent"  # type: ignore

    def test_base_event_validates_empty_type(self):
        """BaseEvent raises ValueError for empty event type."""
        with pytest.raises(ValueError, match="Event type cannot be empty"):
            BaseEvent(
                id=uuid4(),
                type="",
                data={},
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(),
                stream_name="test:v0-thread123",
            )

    def test_base_event_validates_negative_position(self):
        """BaseEvent raises ValueError for negative position."""
        with pytest.raises(ValueError, match="Event position must be >= 0"):
            BaseEvent(
                id=uuid4(),
                type="TestEvent",
                data={},
                metadata={},
                position=-1,
                global_position=0,
                time=datetime.now(),
                stream_name="test:v0-thread123",
            )

    def test_base_event_validates_negative_global_position(self):
        """BaseEvent raises ValueError for negative global_position."""
        with pytest.raises(ValueError, match="Event global_position must be >= 0"):
            BaseEvent(
                id=uuid4(),
                type="TestEvent",
                data={},
                metadata={},
                position=0,
                global_position=-1,
                time=datetime.now(),
                stream_name="test:v0-thread123",
            )

    def test_base_event_with_empty_metadata(self):
        """BaseEvent can be created with empty metadata dict."""
        event = BaseEvent(
            id=uuid4(),
            type="TestEvent",
            data={"test": "data"},
            metadata={},
            position=0,
            global_position=0,
            time=datetime.now(),
            stream_name="test:v0-thread123",
        )

        assert event.metadata == {}

    def test_base_event_with_empty_data(self):
        """BaseEvent can be created with empty data dict."""
        event = BaseEvent(
            id=uuid4(),
            type="TestEvent",
            data={},
            metadata={},
            position=0,
            global_position=0,
            time=datetime.now(),
            stream_name="test:v0-thread123",
        )

        assert event.data == {}

    def test_base_event_with_complex_data(self):
        """BaseEvent can store complex nested data structures."""
        complex_data = {
            "user": {"name": "Alice", "id": 123},
            "messages": ["Hello", "World"],
            "metadata": {"timestamp": "2024-01-01T00:00:00Z", "version": 1},
        }

        event = BaseEvent(
            id=uuid4(),
            type="ComplexEvent",
            data=complex_data,
            metadata={},
            position=0,
            global_position=0,
            time=datetime.now(),
            stream_name="test:v0-thread123",
        )

        assert event.data == complex_data
        assert event.data["user"]["name"] == "Alice"
        assert event.data["messages"] == ["Hello", "World"]

    def test_base_event_preserves_uuid_type(self):
        """BaseEvent preserves UUID type for id field."""
        event_id = UUID("12345678-1234-5678-1234-567812345678")
        event = BaseEvent(
            id=event_id,
            type="TestEvent",
            data={},
            metadata={},
            position=0,
            global_position=0,
            time=datetime.now(),
            stream_name="test:v0-thread123",
        )

        assert isinstance(event.id, UUID)
        assert event.id == event_id

    def test_base_event_preserves_datetime_type(self):
        """BaseEvent preserves datetime type for time field."""
        event_time = datetime(2024, 1, 1, 12, 0, 0)
        event = BaseEvent(
            id=uuid4(),
            type="TestEvent",
            data={},
            metadata={},
            position=0,
            global_position=0,
            time=event_time,
            stream_name="test:v0-thread123",
        )

        assert isinstance(event.time, datetime)
        assert event.time == event_time

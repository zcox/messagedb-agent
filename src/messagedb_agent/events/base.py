"""Base event types and structures for the event-sourced agent system.

This module defines the core event structure used throughout the system.
Events are immutable records of state changes, actions, or observations.

All events stored in Message DB streams will conform to the BaseEvent structure,
and event-specific data will be typed using EventData subclasses.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class EventData:
    """Base class for type-safe event payloads.

    All event-specific data classes should inherit from this base class
    to ensure type safety and enable validation.

    Event data classes should be immutable (frozen dataclasses) to ensure
    events cannot be modified after creation.

    Example:
        >>> @dataclass(frozen=True)
        ... class UserMessageData(EventData):
        ...     message: str
        ...     timestamp: datetime
    """

    pass


@dataclass(frozen=True)
class BaseEvent:
    """Immutable event record representing a state change or action in the system.

    Events are the single source of truth in the event-sourced architecture.
    They are append-only and never modified or deleted after being written
    to the event stream.

    Attributes:
        id: Unique identifier for this event (UUID)
        type: Event type name (e.g., "UserMessageAdded", "LLMResponseReceived")
        data: Event-specific payload data (typed as EventData subclass)
        metadata: Optional contextual information (e.g., trace IDs, timestamps)
        position: Position of this event within its stream (0-indexed)
        global_position: Global position across all streams in Message DB
        time: Timestamp when the event was recorded
        stream_name: Full stream name where this event is stored

    Example:
        >>> event = BaseEvent(
        ...     id=UUID("12345678-1234-5678-1234-567812345678"),
        ...     type="UserMessageAdded",
        ...     data={"message": "Hello", "timestamp": "2024-01-01T00:00:00Z"},
        ...     metadata={"trace_id": "abc123"},
        ...     position=0,
        ...     global_position=1000,
        ...     time=datetime(2024, 1, 1),
        ...     stream_name="agent:v0-thread123"
        ... )
    """

    id: UUID
    type: str
    data: dict[str, Any]
    metadata: dict[str, Any]
    position: int
    global_position: int
    time: datetime
    stream_name: str

    def __post_init__(self) -> None:
        """Validate event structure after initialization.

        Raises:
            ValueError: If event type is empty or positions are negative
        """
        if not self.type:
            raise ValueError("Event type cannot be empty")
        if self.position < 0:
            raise ValueError(f"Event position must be >= 0, got {self.position}")
        if self.global_position < 0:
            raise ValueError(f"Event global_position must be >= 0, got {self.global_position}")

"""Message DB operations for writing and reading events.

This module provides functions for writing events to and reading events from
Message DB event streams.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

import structlog
from psycopg import errors as psycopg_errors

from messagedb_agent.store.client import MessageDBClient

logger = structlog.get_logger(__name__)


@dataclass
class Event:
    """Represents a single event read from a Message DB stream.

    Attributes:
        id: Unique identifier of the event (UUID)
        stream_name: Name of the stream containing this event
        type: Event type/name (e.g., "UserMessageAdded")
        position: Position of the event within its stream
        global_position: Global position across all streams
        data: Event payload (deserialized from JSON)
        metadata: Event metadata (deserialized from JSON, may be None)
        time: Timestamp when the event was recorded
    """

    id: str
    stream_name: str
    type: str
    position: int
    global_position: int
    data: dict[str, Any]
    metadata: dict[str, Any] | None
    time: datetime


class OptimisticConcurrencyError(Exception):
    """Raised when an optimistic concurrency check fails during write.

    This occurs when the expected_version doesn't match the current stream version,
    indicating that another process has written to the stream since it was last read.

    Attributes:
        stream_name: Name of the stream where the conflict occurred
        expected_version: The version that was expected
        actual_version: The actual current version of the stream
    """

    def __init__(
        self,
        stream_name: str,
        expected_version: int | None,
        actual_version: int | None = None,
    ) -> None:
        """Initialize the optimistic concurrency error.

        Args:
            stream_name: Name of the stream
            expected_version: Expected version number
            actual_version: Actual version number (if known)
        """
        self.stream_name = stream_name
        self.expected_version = expected_version
        self.actual_version = actual_version
        message = (
            f"Optimistic concurrency check failed for stream '{stream_name}'. "
            f"Expected version: {expected_version}"
        )
        if actual_version is not None:
            message += f", Actual version: {actual_version}"
        super().__init__(message)


def write_event(
    client: MessageDBClient,
    stream_name: str,
    event_type: str,
    data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    expected_version: int | None = None,
) -> int:
    """Write an event to a Message DB stream.

    This function writes a new event to the specified stream using the Message DB
    write_message stored procedure. It handles JSON serialization, generates a UUID
    for the message, and supports optimistic concurrency control.

    Args:
        client: MessageDBClient instance (must be connected)
        stream_name: Name of the stream to write to (e.g., "agent:v0-{threadId}")
        event_type: Type/name of the event (e.g., "UserMessageAdded")
        data: Event payload as a dictionary (will be serialized to JSON)
        metadata: Optional metadata dictionary (will be serialized to JSON)
        expected_version: Optional stream version for optimistic concurrency control.
            If provided, the write will fail if the stream is not at this version.

    Returns:
        Position of the written event in the stream

    Raises:
        OptimisticConcurrencyError: If expected_version is provided and doesn't match
            the current stream version
        psycopg.Error: If database operation fails
        RuntimeError: If client is not connected

    Example:
        ```python
        from messagedb_agent.store import MessageDBClient, MessageDBConfig
        from messagedb_agent.store.operations import write_event

        config = MessageDBConfig()
        with MessageDBClient(config) as client:
            position = write_event(
                client=client,
                stream_name="agent:v0-thread123",
                event_type="UserMessageAdded",
                data={"message": "Hello, world!", "timestamp": "2025-10-19T10:00:00Z"},
                metadata={"user_id": "user456", "session_id": "session789"}
            )
            print(f"Event written at position: {position}")
        ```
    """
    event_id = str(uuid.uuid4())
    log = logger.bind(
        stream_name=stream_name,
        event_type=event_type,
        event_id=event_id,
        expected_version=expected_version,
    )

    log.info("Writing event to stream")

    # Serialize data and metadata to JSON
    data_json = json.dumps(data)
    metadata_json = json.dumps(metadata) if metadata is not None else None

    conn = client.get_connection()
    try:
        with conn.cursor() as cur:
            # Call the write_message stored procedure
            cur.execute(
                """
                SELECT write_message(
                    %(id)s,
                    %(stream_name)s,
                    %(type)s,
                    %(data)s::jsonb,
                    %(metadata)s::jsonb,
                    %(expected_version)s
                )
                """,
                {
                    "id": event_id,
                    "stream_name": stream_name,
                    "type": event_type,
                    "data": data_json,
                    "metadata": metadata_json,
                    "expected_version": expected_version,
                },
            )

            result = cast(dict[str, Any] | None, cur.fetchone())
            if result is None:
                raise RuntimeError("write_message returned no result")

            # The stored procedure returns the position
            position: int = result["write_message"]

            log.info("Event written successfully", position=position)
            return position

    except psycopg_errors.RaiseException as e:
        # Message DB raises an exception for optimistic concurrency violations
        error_message = str(e)
        if "Wrong expected version" in error_message:
            log.warning(
                "Optimistic concurrency check failed",
                error_message=error_message,
            )
            # Try to parse the actual version from the error message
            # Format: "Wrong expected version: {expected} (Stream: {stream},
            # Stream Version: {actual})"
            actual_version = None
            if "Stream Version:" in error_message:
                try:
                    actual_version = int(
                        error_message.split("Stream Version:")[1].strip().rstrip(")")
                    )
                except (IndexError, ValueError):
                    pass

            raise OptimisticConcurrencyError(
                stream_name=stream_name,
                expected_version=expected_version,
                actual_version=actual_version,
            ) from e
        else:
            # Some other database error
            log.error("Database error while writing event", error=str(e))
            raise

    except Exception as e:
        log.error("Unexpected error while writing event", error=str(e), error_type=type(e).__name__)
        raise

    finally:
        client.return_connection(conn)


def read_stream(
    client: MessageDBClient,
    stream_name: str,
    position: int = 0,
    batch_size: int = 1000,
) -> list[Event]:
    """Read events from a Message DB stream.

    This function reads events from the specified stream using the Message DB
    get_stream_messages stored procedure. It deserializes JSON data and returns
    a list of Event objects in chronological order.

    Args:
        client: MessageDBClient instance (must be connected)
        stream_name: Name of the stream to read from (e.g., "agent:v0-{threadId}")
        position: Starting position to read from (default: 0, reads from beginning)
        batch_size: Maximum number of events to retrieve (default: 1000)

    Returns:
        List of Event objects in chronological order. Empty list if no events found.

    Raises:
        psycopg.Error: If database operation fails
        RuntimeError: If client is not connected
        json.JSONDecodeError: If event data or metadata cannot be deserialized

    Example:
        ```python
        from messagedb_agent.store import MessageDBClient, MessageDBConfig
        from messagedb_agent.store.operations import read_stream

        config = MessageDBConfig()
        with MessageDBClient(config) as client:
            events = read_stream(
                client=client,
                stream_name="agent:v0-thread123",
                position=0,
                batch_size=100
            )
            for event in events:
                print(f"Event {event.type} at position {event.position}: {event.data}")
        ```
    """
    log = logger.bind(
        stream_name=stream_name,
        position=position,
        batch_size=batch_size,
    )

    log.info("Reading events from stream")

    conn = client.get_connection()
    try:
        with conn.cursor() as cur:
            # Call the get_stream_messages stored procedure
            cur.execute(
                """
                SELECT
                    id,
                    stream_name,
                    type,
                    position,
                    global_position,
                    data,
                    metadata,
                    time
                FROM get_stream_messages(
                    %(stream_name)s,
                    %(position)s,
                    %(batch_size)s
                )
                """,
                {
                    "stream_name": stream_name,
                    "position": position,
                    "batch_size": batch_size,
                },
            )

            events: list[Event] = []
            for row in cur.fetchall():
                # Cast row to dict for type safety
                event_row = cast(dict[str, Any], row)

                # Deserialize data and metadata
                # data is already a dict if it came from jsonb column
                raw_data = event_row["data"]
                if isinstance(raw_data, dict):
                    data: dict[str, Any] = cast(dict[str, Any], raw_data)
                else:
                    data = cast(dict[str, Any], json.loads(raw_data))

                # metadata might be None
                metadata: dict[str, Any] | None = None
                raw_metadata = event_row["metadata"]
                if raw_metadata is not None:
                    if isinstance(raw_metadata, dict):
                        metadata = cast(dict[str, Any], raw_metadata)
                    else:
                        metadata = cast(dict[str, Any], json.loads(raw_metadata))

                # Create Event object
                event = Event(
                    id=event_row["id"],
                    stream_name=event_row["stream_name"],
                    type=event_row["type"],
                    position=int(event_row["position"]),
                    global_position=int(event_row["global_position"]),
                    data=data,
                    metadata=metadata,
                    time=event_row["time"],
                )
                events.append(event)

            log.info("Successfully read events from stream", event_count=len(events))
            return events

    except Exception as e:
        log.error("Error while reading stream", error=str(e), error_type=type(e).__name__)
        raise

    finally:
        client.return_connection(conn)

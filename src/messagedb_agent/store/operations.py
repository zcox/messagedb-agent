"""Message DB operations for writing and reading events.

This module provides functions for writing events to and reading events from
Message DB event streams.
"""

import json
import uuid
from typing import Any, cast

import structlog
from psycopg import errors as psycopg_errors

from messagedb_agent.store.client import MessageDBClient

logger = structlog.get_logger(__name__)


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

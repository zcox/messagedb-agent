"""Message DB operations for reading messages from categories.

This module provides functions for reading messages from Message DB categories,
which are logical groupings of streams that share a common prefix.
"""

import json
from typing import Any, cast

import structlog

from messagedb_agent.store.client import MessageDBClient
from messagedb_agent.store.operations import Message

logger = structlog.get_logger(__name__)


def get_category_messages(
    client: MessageDBClient,
    category: str,
    position: int = 0,
    batch_size: int = 1000,
    correlation: str | None = None,
    consumer_group_member: int | None = None,
    consumer_group_size: int | None = None,
    condition: str | None = None,
) -> list[Message]:
    """Read messages from a Message DB category.

    This function reads messages from all streams in a category using the Message DB
    get_category_messages stored procedure. It deserializes JSON data and returns
    a list of Message objects ordered by global position.

    A category is a logical grouping of streams. For example, streams named
    "agent:v0-thread1" and "agent:v0-thread2" both belong to the "agent:v0" category.

    Args:
        client: MessageDBClient instance (must be connected)
        category: Name of the category to read from (e.g., "agent:v0")
        position: Starting global position to read from (default: 0)
        batch_size: Maximum number of messages to retrieve (default: 1000)
        correlation: Filter messages by correlation stream name (for pub/sub patterns)
        consumer_group_member: Consumer group member number (0-based,
            requires consumer_group_size)
        consumer_group_size: Total number of consumers in the group
            (required if consumer_group_member set)
        condition: SQL condition string to filter messages
            (e.g., "messages.time >= current_time")

    Returns:
        List of Message objects ordered by global position. Empty list if no messages found.

    Raises:
        ValueError: If consumer_group_member is set but consumer_group_size is not, or vice versa
        psycopg.Error: If database operation fails
        RuntimeError: If client is not connected
        json.JSONDecodeError: If message data or metadata cannot be deserialized

    Example:
        ```python
        from messagedb_agent.store import MessageDBClient, MessageDBConfig
        from messagedb_agent.store.category import get_category_messages

        config = MessageDBConfig()
        with MessageDBClient(config) as client:
            # Read all messages from agent:v0 category
            messages = get_category_messages(
                client=client,
                category="agent:v0",
                position=0,
                batch_size=100
            )

            # Read with consumer group (e.g., member 0 of 3 consumers)
            messages = get_category_messages(
                client=client,
                category="agent:v0",
                consumer_group_member=0,
                consumer_group_size=3
            )

            # Read with correlation filter
            messages = get_category_messages(
                client=client,
                category="agent:v0",
                correlation="user-requests"
            )

            for message in messages:
                print(
                    f"Message {message.type} at position "
                    f"{message.global_position}: {message.data}"
                )
        ```
    """
    # Validate consumer group parameters
    if (consumer_group_member is not None) != (consumer_group_size is not None):
        raise ValueError(
            "consumer_group_member and consumer_group_size must both be set or both be None"
        )

    log = logger.bind(
        category=category,
        position=position,
        batch_size=batch_size,
        correlation=correlation,
        consumer_group_member=consumer_group_member,
        consumer_group_size=consumer_group_size,
        has_condition=condition is not None,
    )

    log.info("Reading messages from category")

    conn = client.get_connection()
    try:
        with conn.cursor() as cur:
            # Call the get_category_messages stored procedure
            # Note: Message DB functions are in the message_store schema
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
                FROM message_store.get_category_messages(
                    %(category)s,
                    %(position)s,
                    %(batch_size)s,
                    %(correlation)s,
                    %(consumer_group_member)s,
                    %(consumer_group_size)s,
                    %(condition)s
                )
                """,
                {
                    "category": category,
                    "position": position,
                    "batch_size": batch_size,
                    "correlation": correlation,
                    "consumer_group_member": consumer_group_member,
                    "consumer_group_size": consumer_group_size,
                    "condition": condition,
                },
            )

            messages: list[Message] = []
            for row in cur.fetchall():
                # Cast row to dict for type safety
                message_row = cast(dict[str, Any], row)

                # Deserialize data and metadata
                # data is already a dict if it came from jsonb column
                raw_data = message_row["data"]
                if isinstance(raw_data, dict):
                    data: dict[str, Any] = cast(dict[str, Any], raw_data)
                else:
                    data = cast(dict[str, Any], json.loads(raw_data))

                # metadata might be None
                metadata: dict[str, Any] | None = None
                raw_metadata = message_row["metadata"]
                if raw_metadata is not None:
                    if isinstance(raw_metadata, dict):
                        metadata = cast(dict[str, Any], raw_metadata)
                    else:
                        metadata = cast(dict[str, Any], json.loads(raw_metadata))

                # Create Message object
                message = Message(
                    id=message_row["id"],
                    stream_name=message_row["stream_name"],
                    type=message_row["type"],
                    position=int(message_row["position"]),
                    global_position=int(message_row["global_position"]),
                    data=data,
                    metadata=metadata,
                    time=message_row["time"],
                )
                messages.append(message)

        # Commit the transaction to release locks
        conn.commit()

        log.info("Successfully read messages from category", message_count=len(messages))
        return messages

    except Exception as e:
        log.error("Error while reading category", error=str(e), error_type=type(e).__name__)
        raise

    finally:
        client.return_connection(conn)

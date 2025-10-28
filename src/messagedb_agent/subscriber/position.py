"""Position persistence for Message DB subscribers.

This module provides position tracking and persistence for subscribers, allowing
them to resume from where they left off after restarts or failures.
"""

from abc import ABC, abstractmethod

import structlog

from messagedb_agent.store import MessageDBClient
from messagedb_agent.store.operations import get_last_stream_message, write_message

logger = structlog.get_logger(__name__)


class PositionStore(ABC):
    """Abstract base class for subscriber position persistence.

    Position stores track the current processing position for a subscriber,
    allowing the subscriber to resume from where it left off after a restart.
    """

    @abstractmethod
    def get_position(self, subscriber_id: str) -> int:
        """Get the current position for a subscriber.

        Args:
            subscriber_id: Unique identifier for the subscriber

        Returns:
            The current position (global_position + 1), or 0 if no position stored
        """
        ...

    @abstractmethod
    def update_position(self, subscriber_id: str, position: int) -> None:
        """Update the position for a subscriber.

        Args:
            subscriber_id: Unique identifier for the subscriber
            position: The new position to store (global_position + 1)
        """
        ...


class InMemoryPositionStore(PositionStore):
    """In-memory position store for testing.

    This store keeps positions in memory and does not persist them across
    process restarts. Useful for testing and development.

    Example:
        >>> store = InMemoryPositionStore()
        >>> store.update_position("my-subscriber", 42)
        >>> position = store.get_position("my-subscriber")
        >>> print(position)
        42
    """

    def __init__(self) -> None:
        """Initialize the in-memory position store."""
        self._positions: dict[str, int] = {}
        logger.debug("in_memory_position_store_initialized")

    def get_position(self, subscriber_id: str) -> int:
        """Get the current position for a subscriber.

        Args:
            subscriber_id: Unique identifier for the subscriber

        Returns:
            The current position, or 0 if no position stored
        """
        position = self._positions.get(subscriber_id, 0)
        logger.debug(
            "position_retrieved",
            subscriber_id=subscriber_id,
            position=position,
            store_type="in_memory",
        )
        return position

    def update_position(self, subscriber_id: str, position: int) -> None:
        """Update the position for a subscriber.

        Args:
            subscriber_id: Unique identifier for the subscriber
            position: The new position to store
        """
        self._positions[subscriber_id] = position
        logger.debug(
            "position_updated",
            subscriber_id=subscriber_id,
            position=position,
            store_type="in_memory",
        )


class MessageDBPositionStore(PositionStore):
    """Position store that persists positions in Message DB streams.

    This store writes position updates as events to a dedicated stream per subscriber.
    The stream name format is: subscriberPosition-{subscriber_id}

    Example:
        >>> config = MessageDBConfig(...)
        >>> client = MessageDBClient(config)
        >>> store = MessageDBPositionStore(client)
        >>> store.update_position("my-subscriber", 42)
        >>> position = store.get_position("my-subscriber")
        >>> print(position)
        42
    """

    def __init__(self, client: MessageDBClient):
        """Initialize the Message DB position store.

        Args:
            client: Message DB client for reading and writing position events
        """
        self.client = client
        logger.debug("messagedb_position_store_initialized")

    def _build_stream_name(self, subscriber_id: str) -> str:
        """Build the stream name for a subscriber's position.

        Args:
            subscriber_id: Unique identifier for the subscriber

        Returns:
            Stream name in format: subscriberPosition-{subscriber_id}
        """
        return f"subscriberPosition-{subscriber_id}"

    def get_position(self, subscriber_id: str) -> int:
        """Get the current position for a subscriber.

        Reads the latest PositionUpdated event from the subscriber's position stream.

        Args:
            subscriber_id: Unique identifier for the subscriber

        Returns:
            The current position, or 0 if no position stored
        """
        stream_name = self._build_stream_name(subscriber_id)

        # Get the last position event (much more efficient than reading entire stream)
        latest_message = get_last_stream_message(
            client=self.client,
            stream_name=stream_name,
        )

        if latest_message is None:
            logger.debug(
                "position_retrieved",
                subscriber_id=subscriber_id,
                position=0,
                store_type="messagedb",
                stream_name=stream_name,
            )
            return 0

        # Extract position from the event data
        position: int = latest_message.data.get("position", 0)

        logger.debug(
            "position_retrieved",
            subscriber_id=subscriber_id,
            position=position,
            store_type="messagedb",
            stream_name=stream_name,
        )

        return position

    def update_position(self, subscriber_id: str, position: int) -> None:
        """Update the position for a subscriber.

        Writes a PositionUpdated event to the subscriber's position stream.

        Args:
            subscriber_id: Unique identifier for the subscriber
            position: The new position to store
        """
        stream_name = self._build_stream_name(subscriber_id)

        # Write position update event
        write_message(
            client=self.client,
            stream_name=stream_name,
            message_type="PositionUpdated",
            data={"position": position, "subscriber_id": subscriber_id},
            metadata=None,
        )

        logger.debug(
            "position_updated",
            subscriber_id=subscriber_id,
            position=position,
            store_type="messagedb",
            stream_name=stream_name,
        )

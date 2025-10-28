"""Integration tests for subscriber with position persistence."""

import pytest

from messagedb_agent.store import MessageDBClient
from messagedb_agent.store.operations import Message, write_message
from messagedb_agent.subscriber import (
    InMemoryPositionStore,
    MessageDBPositionStore,
    Subscriber,
)


def test_subscriber_with_in_memory_position_store(messagedb_client: MessageDBClient):
    """Test that subscriber correctly uses in-memory position store."""
    category = "test-subscriber-inmem"
    stream_name = f"{category}:v0-abc123"

    # Write some test messages
    for i in range(5):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="TestEvent",
            data={"index": i},
        )

    # Create position store and subscriber
    position_store = InMemoryPositionStore()
    subscriber_id = "test-sub-1"

    # Track processed messages
    processed = []

    def handler(message: Message) -> None:
        processed.append(message.data["index"])
        if len(processed) >= 5:
            subscriber.stop()

    subscriber = Subscriber(
        category=category,
        handler=handler,
        store_client=messagedb_client,
        poll_interval_ms=10,
        position_store=position_store,
        subscriber_id=subscriber_id,
    )

    # Start processing
    subscriber.start()

    # Verify all messages were processed
    assert processed == [0, 1, 2, 3, 4]

    # Verify position was saved
    position = position_store.get_position(subscriber_id)
    assert position > 0


def test_subscriber_with_messagedb_position_store(messagedb_client: MessageDBClient):
    """Test that subscriber correctly uses Message DB position store."""
    category = "test-subscriber-msgdb"
    stream_name = f"{category}:v0-xyz789"

    # Write some test messages
    for i in range(5):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="TestEvent",
            data={"index": i},
        )

    # Create position store and subscriber
    position_store = MessageDBPositionStore(messagedb_client)
    subscriber_id = "test-sub-2"

    # Track processed messages
    processed = []

    def handler(message: Message) -> None:
        processed.append(message.data["index"])
        if len(processed) >= 5:
            subscriber.stop()

    subscriber = Subscriber(
        category=category,
        handler=handler,
        store_client=messagedb_client,
        poll_interval_ms=10,
        position_store=position_store,
        subscriber_id=subscriber_id,
    )

    # Start processing
    subscriber.start()

    # Verify all messages were processed
    assert processed == [0, 1, 2, 3, 4]

    # Verify position was saved in Message DB
    position = position_store.get_position(subscriber_id)
    assert position > 0


def test_subscriber_resumes_from_saved_position(messagedb_client: MessageDBClient):
    """Test that subscriber resumes from saved position after restart."""
    category = "test-subscriber-resume"
    stream_name = f"{category}:v0-resume1"

    # Write initial batch of messages
    for i in range(3):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="TestEvent",
            data={"index": i},
        )

    # Create position store
    position_store = MessageDBPositionStore(messagedb_client)
    subscriber_id = "test-sub-resume"

    # First subscriber - process first 3 messages
    processed_first = []

    def handler_first(message: Message) -> None:
        processed_first.append(message.data["index"])
        if len(processed_first) >= 3:
            subscriber1.stop()

    subscriber1 = Subscriber(
        category=category,
        handler=handler_first,
        store_client=messagedb_client,
        poll_interval_ms=10,
        position_store=position_store,
        subscriber_id=subscriber_id,
    )

    subscriber1.start()
    assert processed_first == [0, 1, 2]

    # Write more messages
    for i in range(3, 6):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="TestEvent",
            data={"index": i},
        )

    # Second subscriber - should resume from where first left off
    processed_second = []

    def handler_second(message: Message) -> None:
        processed_second.append(message.data["index"])
        if len(processed_second) >= 3:
            subscriber2.stop()

    subscriber2 = Subscriber(
        category=category,
        handler=handler_second,
        store_client=messagedb_client,
        poll_interval_ms=10,
        position_store=position_store,
        subscriber_id=subscriber_id,
    )

    subscriber2.start()

    # Should only process messages 3, 4, 5 (not 0, 1, 2 again)
    assert processed_second == [3, 4, 5]


def test_subscriber_requires_id_with_position_store(messagedb_client: MessageDBClient):
    """Test that subscriber raises error if position_store provided without subscriber_id."""
    position_store = InMemoryPositionStore()

    def handler(message: Message) -> None:
        pass

    # Should raise error
    with pytest.raises(Exception) as exc_info:
        Subscriber(
            category="test",
            handler=handler,
            store_client=messagedb_client,
            position_store=position_store,
            subscriber_id=None,  # Missing subscriber_id!
        )

    assert "subscriber_id must be provided" in str(exc_info.value)

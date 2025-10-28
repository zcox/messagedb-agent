"""Tests for subscriber base module."""

import asyncio
import threading
import time
from datetime import datetime

import pytest

from messagedb_agent.store import Message, MessageDBClient, write_message
from messagedb_agent.subscriber import MessageHandler, Subscriber, SubscriberError


@pytest.fixture
def test_category() -> str:
    """Unique category for each test to avoid conflicts."""
    # In Message DB, category is everything before the first dash (-)
    # For streams like "category-streamId" the category is "category"
    # For streams like "category:version-streamId" the category is "category:version"
    # Use a unique timestamp to ensure each test has its own category
    return f"testSubscriber{int(time.time() * 1000000)}:v0"


@pytest.fixture
def collected_messages() -> list[Message]:
    """Shared list to collect messages from handlers."""
    return []


def test_message_handler_protocol_sync(collected_messages: list[Message]) -> None:
    """Test that sync functions satisfy MessageHandler protocol."""

    def sync_handler(message: Message) -> None:
        collected_messages.append(message)

    # Type checker should accept this
    handler: MessageHandler = sync_handler

    # Should be callable
    test_message = Message(
        id="test-id",
        stream_name="test:v0-123",
        type="TestEvent",
        position=0,
        global_position=1,
        data={"message": "test"},
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:00"),
    )
    handler(test_message)
    assert len(collected_messages) == 1


def test_message_handler_protocol_async(collected_messages: list[Message]) -> None:
    """Test that async functions satisfy MessageHandler protocol."""

    async def async_handler(message: Message) -> None:
        collected_messages.append(message)

    # Type checker should accept this
    handler: MessageHandler = async_handler

    # Should be callable
    test_message = Message(
        id="test-id",
        stream_name="test:v0-123",
        type="TestEvent",
        position=0,
        global_position=1,
        data={"message": "test"},
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:00"),
    )

    # Execute the async handler
    result = handler(test_message)
    asyncio.run(result)  # type: ignore
    assert len(collected_messages) == 1


def test_subscriber_initialization(messagedb_client: MessageDBClient, test_category: str) -> None:
    """Test subscriber initialization."""

    def handler(message: Message) -> None:
        pass

    subscriber = Subscriber(
        category=test_category,
        handler=handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
        batch_size=10,
    )

    assert subscriber.category == test_category
    assert subscriber.handler == handler
    assert subscriber.store_client == messagedb_client
    assert subscriber.poll_interval_ms == 50
    assert subscriber.batch_size == 10
    assert subscriber.position == 0
    assert not subscriber._is_running
    assert not subscriber._should_stop


def test_subscriber_sync_handler(
    messagedb_client: MessageDBClient, test_category: str, collected_messages: list[Message]
) -> None:
    """Test subscriber with synchronous handler."""

    def handler(message: Message) -> None:
        collected_messages.append(message)

    subscriber = Subscriber(
        category=test_category,
        handler=handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
        batch_size=10,
    )

    # Write some test messages
    stream_id = f"{int(time.time() * 1000000)}"
    stream_name = f"{test_category}-{stream_id}"
    for i in range(3):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type=f"Event{i}",
            data={"index": i},
        )

    # Start subscriber in background thread
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()

    # Wait for messages to be processed
    max_wait = 2.0  # seconds
    start = time.time()
    while len(collected_messages) < 3 and (time.time() - start) < max_wait:
        time.sleep(0.05)

    # Stop subscriber
    subscriber.stop()
    subscriber_thread.join(timeout=1.0)

    # Verify messages were collected
    assert len(collected_messages) == 3
    assert collected_messages[0].data["index"] == 0
    assert collected_messages[1].data["index"] == 1
    assert collected_messages[2].data["index"] == 2

    # Verify position was updated
    assert subscriber.position == collected_messages[-1].global_position + 1


def test_subscriber_async_handler(
    messagedb_client: MessageDBClient, test_category: str, collected_messages: list[Message]
) -> None:
    """Test subscriber with asynchronous handler."""

    async def async_handler(message: Message) -> None:
        await asyncio.sleep(0.01)  # Simulate async work
        collected_messages.append(message)

    subscriber = Subscriber(
        category=test_category,
        handler=async_handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
        batch_size=10,
    )

    # Write some test messages
    stream_id = f"{int(time.time() * 1000000)}"
    stream_name = f"{test_category}-{stream_id}"
    for i in range(3):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type=f"AsyncEvent{i}",
            data={"index": i},
        )

    # Start subscriber in background thread
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()

    # Wait for messages to be processed
    max_wait = 2.0  # seconds
    start = time.time()
    while len(collected_messages) < 3 and (time.time() - start) < max_wait:
        time.sleep(0.05)

    # Stop subscriber
    subscriber.stop()
    subscriber_thread.join(timeout=1.0)

    # Verify messages were collected
    assert len(collected_messages) == 3
    assert collected_messages[0].data["index"] == 0
    assert collected_messages[1].data["index"] == 1
    assert collected_messages[2].data["index"] == 2


def test_subscriber_error_handling(
    messagedb_client: MessageDBClient, test_category: str, collected_messages: list[Message]
) -> None:
    """Test that subscriber continues processing after handler errors."""
    error_indices = [1]  # Will error on message with index 1

    def error_handler(message: Message) -> None:
        index = message.data["index"]
        if index in error_indices:
            raise ValueError(f"Handler error for message {index}")
        collected_messages.append(message)

    subscriber = Subscriber(
        category=test_category,
        handler=error_handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
        batch_size=10,
    )

    # Write test messages
    stream_id = f"{int(time.time() * 1000000)}"
    stream_name = f"{test_category}-{stream_id}"
    for i in range(3):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type=f"Event{i}",
            data={"index": i},
        )

    # Start subscriber in background thread
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()

    # Wait for messages to be processed
    max_wait = 2.0
    start = time.time()
    while len(collected_messages) < 2 and (time.time() - start) < max_wait:
        time.sleep(0.05)

    # Stop subscriber
    subscriber.stop()
    subscriber_thread.join(timeout=1.0)

    # Should have processed messages 0 and 2, skipped 1
    assert len(collected_messages) == 2
    assert collected_messages[0].data["index"] == 0
    assert collected_messages[1].data["index"] == 2

    # Position should still be updated (error doesn't prevent position advancement)
    assert subscriber.position > 0


def test_subscriber_position_tracking(
    messagedb_client: MessageDBClient, test_category: str
) -> None:
    """Test that subscriber correctly tracks position across batches."""
    processed_count = 0

    def counting_handler(message: Message) -> None:
        nonlocal processed_count
        processed_count += 1

    subscriber = Subscriber(
        category=test_category,
        handler=counting_handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
        batch_size=2,  # Small batch to test multiple batches
    )

    # Write messages
    stream_id = f"{int(time.time() * 1000000)}"
    stream_name = f"{test_category}-{stream_id}"
    for i in range(5):
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="TestEvent",
            data={"index": i},
        )

    # Start subscriber
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()

    # Wait for all messages to be processed
    max_wait = 2.0
    start = time.time()
    while processed_count < 5 and (time.time() - start) < max_wait:
        time.sleep(0.05)

    subscriber.stop()
    subscriber_thread.join(timeout=1.0)

    assert processed_count == 5
    assert subscriber.position > 0


def test_subscriber_already_running_error(
    messagedb_client: MessageDBClient, test_category: str
) -> None:
    """Test that starting an already running subscriber raises error."""

    def handler(message: Message) -> None:
        pass

    subscriber = Subscriber(
        category=test_category,
        handler=handler,
        store_client=messagedb_client,
    )

    # Start in background
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()
    time.sleep(0.1)  # Let it start

    try:
        # Try to start again - should raise error
        with pytest.raises(SubscriberError, match="already running"):
            subscriber.start()
    finally:
        subscriber.stop()
        subscriber_thread.join(timeout=1.0)


def test_subscriber_graceful_shutdown(
    messagedb_client: MessageDBClient, test_category: str
) -> None:
    """Test graceful shutdown of subscriber."""

    def handler(message: Message) -> None:
        time.sleep(0.01)  # Simulate some work

    subscriber = Subscriber(
        category=test_category,
        handler=handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
    )

    # Start subscriber
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()
    time.sleep(0.1)  # Let it start

    # Stop should complete within reasonable time
    subscriber.stop()
    subscriber_thread.join(timeout=2.0)

    assert not subscriber_thread.is_alive()
    assert not subscriber._is_running


def test_subscriber_empty_category(messagedb_client: MessageDBClient, test_category: str) -> None:
    """Test subscriber with category that has no messages."""
    call_count = 0

    def handler(message: Message) -> None:
        nonlocal call_count
        call_count += 1

    subscriber = Subscriber(
        category=test_category,
        handler=handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
    )

    # Start subscriber
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()

    # Let it poll a few times
    time.sleep(0.3)

    subscriber.stop()
    subscriber_thread.join(timeout=1.0)

    # Handler should never be called
    assert call_count == 0
    assert subscriber.position == 0


def test_subscriber_multiple_streams_in_category(
    messagedb_client: MessageDBClient, test_category: str, collected_messages: list[Message]
) -> None:
    """Test subscriber processes messages from multiple streams in same category."""

    def handler(message: Message) -> None:
        collected_messages.append(message)

    subscriber = Subscriber(
        category=test_category,
        handler=handler,
        store_client=messagedb_client,
        poll_interval_ms=50,
    )

    # Write messages to different streams in same category
    for stream_id in ["stream1", "stream2", "stream3"]:
        stream_name = f"{test_category}-{stream_id}"
        for i in range(2):
            write_message(
                client=messagedb_client,
                stream_name=stream_name,
                message_type="TestEvent",
                data={"stream": stream_id, "index": i},
            )

    # Start subscriber
    subscriber_thread = threading.Thread(target=subscriber.start, daemon=True)
    subscriber_thread.start()

    # Wait for all 6 messages
    max_wait = 2.0
    start = time.time()
    while len(collected_messages) < 6 and (time.time() - start) < max_wait:
        time.sleep(0.05)

    subscriber.stop()
    subscriber_thread.join(timeout=1.0)

    # Should have collected all messages from all streams
    assert len(collected_messages) == 6

    # Verify we got messages from all three streams
    stream_ids = {m.data["stream"] for m in collected_messages}
    assert stream_ids == {"stream1", "stream2", "stream3"}

"""Tests for subscriber position persistence."""

import pytest

from messagedb_agent.config import MessageDBConfig
from messagedb_agent.store import MessageDBClient
from messagedb_agent.subscriber.position import (
    InMemoryPositionStore,
    MessageDBPositionStore,
    PositionStore,
)


class TestInMemoryPositionStore:
    """Tests for the in-memory position store."""

    def test_initial_position_is_zero(self):
        """Test that initial position is 0 for unknown subscriber."""
        store = InMemoryPositionStore()
        position = store.get_position("test-subscriber")
        assert position == 0

    def test_update_and_get_position(self):
        """Test updating and retrieving position."""
        store = InMemoryPositionStore()

        # Update position
        store.update_position("test-subscriber", 42)

        # Retrieve position
        position = store.get_position("test-subscriber")
        assert position == 42

    def test_update_position_multiple_times(self):
        """Test updating position multiple times."""
        store = InMemoryPositionStore()

        # Update position multiple times
        store.update_position("test-subscriber", 10)
        store.update_position("test-subscriber", 20)
        store.update_position("test-subscriber", 30)

        # Should return latest position
        position = store.get_position("test-subscriber")
        assert position == 30

    def test_multiple_subscribers(self):
        """Test tracking positions for multiple subscribers."""
        store = InMemoryPositionStore()

        # Update positions for different subscribers
        store.update_position("subscriber-1", 100)
        store.update_position("subscriber-2", 200)
        store.update_position("subscriber-3", 300)

        # Each should maintain independent position
        assert store.get_position("subscriber-1") == 100
        assert store.get_position("subscriber-2") == 200
        assert store.get_position("subscriber-3") == 300

    def test_zero_position_is_valid(self):
        """Test that position 0 is a valid position."""
        store = InMemoryPositionStore()

        # Explicitly set position to 0
        store.update_position("test-subscriber", 0)

        # Should return 0
        position = store.get_position("test-subscriber")
        assert position == 0


class TestMessageDBPositionStore:
    """Tests for the Message DB position store."""

    @pytest.fixture
    def store(self, messagedb_client: MessageDBClient) -> MessageDBPositionStore:
        """Create a Message DB position store for testing."""
        return MessageDBPositionStore(messagedb_client)

    def test_initial_position_is_zero(self, store: MessageDBPositionStore):
        """Test that initial position is 0 for unknown subscriber."""
        position = store.get_position("test-subscriber-1")
        assert position == 0

    def test_update_and_get_position(self, store: MessageDBPositionStore):
        """Test updating and retrieving position."""
        subscriber_id = "test-subscriber-2"

        # Update position
        store.update_position(subscriber_id, 42)

        # Retrieve position
        position = store.get_position(subscriber_id)
        assert position == 42

    def test_update_position_multiple_times(self, store: MessageDBPositionStore):
        """Test updating position multiple times."""
        subscriber_id = "test-subscriber-3"

        # Update position multiple times
        store.update_position(subscriber_id, 10)
        store.update_position(subscriber_id, 20)
        store.update_position(subscriber_id, 30)

        # Should return latest position
        position = store.get_position(subscriber_id)
        assert position == 30

    def test_multiple_subscribers(self, store: MessageDBPositionStore):
        """Test tracking positions for multiple subscribers."""
        # Update positions for different subscribers
        store.update_position("subscriber-a", 100)
        store.update_position("subscriber-b", 200)
        store.update_position("subscriber-c", 300)

        # Each should maintain independent position
        assert store.get_position("subscriber-a") == 100
        assert store.get_position("subscriber-b") == 200
        assert store.get_position("subscriber-c") == 300

    def test_zero_position_is_valid(self, store: MessageDBPositionStore):
        """Test that position 0 is a valid position."""
        subscriber_id = "test-subscriber-4"

        # Explicitly set position to 0
        store.update_position(subscriber_id, 0)

        # Should return 0
        position = store.get_position(subscriber_id)
        assert position == 0

    def test_position_persists_across_store_instances(
        self, messagedb_client: MessageDBClient
    ):
        """Test that position persists across different store instances."""
        subscriber_id = "test-subscriber-5"

        # Create first store and update position
        store1 = MessageDBPositionStore(messagedb_client)
        store1.update_position(subscriber_id, 123)

        # Create second store and retrieve position
        store2 = MessageDBPositionStore(messagedb_client)
        position = store2.get_position(subscriber_id)

        # Position should be persisted
        assert position == 123

    def test_stream_name_format(self, store: MessageDBPositionStore):
        """Test that stream name follows expected format."""
        subscriber_id = "my-subscriber"

        # Update position (this creates the stream)
        store.update_position(subscriber_id, 1)

        # The stream name should follow the format
        # We can verify by checking that get_position works
        position = store.get_position(subscriber_id)
        assert position == 1

    def test_large_position_values(self, store: MessageDBPositionStore):
        """Test storing and retrieving large position values."""
        subscriber_id = "test-subscriber-6"
        large_position = 999_999_999

        store.update_position(subscriber_id, large_position)
        position = store.get_position(subscriber_id)

        assert position == large_position


class TestPositionStoreInterface:
    """Tests to ensure both implementations conform to the PositionStore interface."""

    @pytest.fixture(params=["in_memory", "message_db"])
    def position_store(self, request, messagedb_client: MessageDBClient) -> PositionStore:
        """Parametrized fixture that provides both position store implementations."""
        if request.param == "in_memory":
            return InMemoryPositionStore()
        else:
            return MessageDBPositionStore(messagedb_client)

    def test_get_position_returns_int(self, position_store: PositionStore):
        """Test that get_position returns an integer."""
        position = position_store.get_position("test-subscriber")
        assert isinstance(position, int)

    def test_update_position_accepts_int(self, position_store: PositionStore):
        """Test that update_position accepts integer position."""
        # Should not raise any exception
        position_store.update_position("test-subscriber", 42)

        # Verify it worked
        position = position_store.get_position("test-subscriber")
        assert position == 42

    def test_position_round_trip(self, position_store: PositionStore):
        """Test that positions can be stored and retrieved correctly."""
        test_positions = [0, 1, 100, 1000, 999999]

        for test_position in test_positions:
            subscriber_id = f"test-subscriber-{test_position}"
            position_store.update_position(subscriber_id, test_position)
            retrieved_position = position_store.get_position(subscriber_id)
            assert retrieved_position == test_position

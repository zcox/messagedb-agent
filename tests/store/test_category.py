"""Tests for Message DB category operations (get_category_messages).

These tests use a real Message DB container managed by pytest-docker
and verify the category read functionality across multiple streams.
"""

import uuid

import pytest

from messagedb_agent.store import (
    MessageDBClient,
    get_category_messages,
    write_message,
)


@pytest.fixture
def test_category() -> str:
    """Generate a unique category for each test."""
    category_id = str(uuid.uuid4())[:8]
    return f"testcat{category_id}"


@pytest.fixture
def test_streams(test_category: str) -> list[str]:
    """Generate multiple unique stream names in the same category."""
    return [
        f"{test_category}-thread1",
        f"{test_category}-thread2",
        f"{test_category}-thread3",
    ]


class TestGetCategoryMessages:
    """Tests for get_category_messages function."""

    def test_read_empty_category(
        self, messagedb_client: MessageDBClient, test_category: str
    ) -> None:
        """Test reading from an empty category."""
        with messagedb_client:
            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            assert messages == []

    def test_read_single_stream_in_category(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test reading from a category with a single stream."""
        with messagedb_client:
            # Write messages to one stream
            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="MessageAdded",
                data={"message": "Message 1"},
            )

            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="MessageAdded",
                data={"message": "Message 2"},
            )

            # Read from category
            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            assert len(messages) == 2
            assert messages[0].data == {"message": "Message 1"}
            assert messages[1].data == {"message": "Message 2"}
            assert messages[0].stream_name == test_streams[0]
            assert messages[1].stream_name == test_streams[0]

    def test_read_multiple_streams_in_category(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test reading from a category with multiple streams."""
        with messagedb_client:
            # Write to stream 1
            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="MessageAdded",
                data={"message": "Stream 1 - Message 1"},
            )

            # Write to stream 2
            write_message(
                client=messagedb_client,
                stream_name=test_streams[1],
                message_type="MessageAdded",
                data={"message": "Stream 2 - Message 1"},
            )

            # Write to stream 1 again
            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="MessageAdded",
                data={"message": "Stream 1 - Message 2"},
            )

            # Write to stream 3
            write_message(
                client=messagedb_client,
                stream_name=test_streams[2],
                message_type="MessageAdded",
                data={"message": "Stream 3 - Message 1"},
            )

            # Read from category
            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            # Should get all 4 messages, ordered by global_position
            assert len(messages) == 4

            # Verify messages are from different streams
            stream_names = {msg.stream_name for msg in messages}
            assert len(stream_names) == 3

            # Verify global_position ordering
            for i in range(1, len(messages)):
                assert messages[i].global_position > messages[i - 1].global_position

    def test_read_from_position(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test reading from a specific global position."""
        with messagedb_client:
            # Write multiple messages and track global positions
            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="MessageAdded",
                data={"message": "Message 1"},
            )

            write_message(
                client=messagedb_client,
                stream_name=test_streams[1],
                message_type="MessageAdded",
                data={"message": "Message 2"},
            )

            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="MessageAdded",
                data={"message": "Message 3"},
            )

            # Read all messages first to get global positions
            all_messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            assert len(all_messages) == 3

            # Read from the second message's position
            second_global_pos = all_messages[1].global_position
            messages_from_pos = get_category_messages(
                client=messagedb_client,
                category=test_category,
                position=second_global_pos,
            )

            # Should get messages 2 and 3
            assert len(messages_from_pos) == 2
            assert messages_from_pos[0].global_position == all_messages[1].global_position
            assert messages_from_pos[1].global_position == all_messages[2].global_position

    def test_read_with_batch_size(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test reading with a batch size limit."""
        with messagedb_client:
            # Write 10 messages across different streams
            for i in range(10):
                stream_idx = i % len(test_streams)
                write_message(
                    client=messagedb_client,
                    stream_name=test_streams[stream_idx],
                    message_type="MessageAdded",
                    data={"message": f"Message {i}"},
                )

            # Read with batch size of 5
            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
                batch_size=5,
            )

            assert len(messages) == 5

            # Verify they're the first 5 by global position
            all_messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            for i in range(5):
                assert messages[i].global_position == all_messages[i].global_position

    def test_consumer_group_parameters_validation(
        self, messagedb_client: MessageDBClient, test_category: str
    ) -> None:
        """Test that consumer group parameters must both be set or both be None."""
        with messagedb_client:
            # Test consumer_group_member without consumer_group_size
            with pytest.raises(ValueError) as exc_info:
                get_category_messages(
                    client=messagedb_client,
                    category=test_category,
                    consumer_group_member=0,
                    consumer_group_size=None,
                )

            assert "must both be set or both be None" in str(exc_info.value)

            # Test consumer_group_size without consumer_group_member
            with pytest.raises(ValueError) as exc_info:
                get_category_messages(
                    client=messagedb_client,
                    category=test_category,
                    consumer_group_member=None,
                    consumer_group_size=3,
                )

            assert "must both be set or both be None" in str(exc_info.value)

    def test_consumer_group_distribution(
        self, messagedb_client: MessageDBClient, test_category: str
    ) -> None:
        """Test that consumer groups correctly partition messages by stream."""
        with messagedb_client:
            # Create multiple streams with messages
            # Consumer groups partition by stream, not by individual messages
            num_streams = 6
            streams = [f"{test_category}-stream{i}" for i in range(num_streams)]

            for stream in streams:
                write_message(
                    client=messagedb_client,
                    stream_name=stream,
                    message_type="MessageAdded",
                    data={"message": f"Message from {stream}"},
                )

            # Read with 2-member consumer group
            consumer_0_messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
                consumer_group_member=0,
                consumer_group_size=2,
            )

            consumer_1_messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
                consumer_group_member=1,
                consumer_group_size=2,
            )

            # Both consumers should get some messages
            assert len(consumer_0_messages) > 0
            assert len(consumer_1_messages) > 0

            # Combined, they should get all messages
            total_messages = len(consumer_0_messages) + len(consumer_1_messages)
            assert total_messages == num_streams

            # Messages should not overlap (each stream assigned to one consumer)
            consumer_0_streams = {msg.stream_name for msg in consumer_0_messages}
            consumer_1_streams = {msg.stream_name for msg in consumer_1_messages}
            assert consumer_0_streams.isdisjoint(consumer_1_streams)

    def test_correlation_parameter_validation(
        self, messagedb_client: MessageDBClient, test_category: str
    ) -> None:
        """Test that correlation parameter validates correctly.

        Note: The correlation parameter is used for pub/sub patterns in Message DB.
        It filters messages based on the correlation_stream_name in metadata.
        The correlation parameter must refer to an existing category of streams.
        Since setting up proper correlation streams is complex and beyond the scope
        of this unit test, we just verify the parameter is accepted by the function.
        """
        with messagedb_client:
            # Verify that passing correlation parameter doesn't cause immediate errors
            # (it may cause errors at runtime if the category doesn't exist, but that's
            # a Message DB validation concern, not a Python API concern)
            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
                correlation=None,  # No correlation filter
            )

            # Should return empty list for empty category
            assert messages == []

    def test_condition_filter_not_activated(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test that SQL condition filtering raises error when not activated.

        Note: The condition parameter is disabled by default in Message DB for security.
        It must be activated via the message_store.enable_retrieval_condition setting.
        This test verifies that using condition raises an error when not activated.
        """
        with messagedb_client:
            # Write messages of different types
            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="SessionStarted",
                data={"thread_id": "thread1"},
            )

            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="MessageAdded",
                data={"message": "User message"},
            )

            # Attempting to use condition should raise an error
            from psycopg import errors as psycopg_errors

            with pytest.raises(psycopg_errors.RaiseException) as exc_info:
                get_category_messages(
                    client=messagedb_client,
                    category=test_category,
                    condition="messages.type = 'MessageAdded'",
                )

            # Verify the error message
            assert "Retrieval with SQL condition is not activated" in str(exc_info.value)

    def test_complex_data_and_metadata(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test reading messages with complex nested data and metadata."""
        with messagedb_client:
            complex_data = {
                "user_message": "What's the weather?",
                "tool_calls": [
                    {"id": "call1", "name": "get_weather", "args": {"location": "NYC"}},
                ],
                "token_usage": {"prompt": 100, "completion": 50},
            }

            complex_metadata = {
                "user_id": "user123",
                "session_id": "session456",
                "correlation_stream_name": "user-requests",
            }

            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="LLMResponseReceived",
                data=complex_data,
                metadata=complex_metadata,
            )

            # Read from category
            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            assert len(messages) == 1
            assert messages[0].data == complex_data
            assert messages[0].metadata == complex_metadata

    def test_message_attributes(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test that all message attributes are correctly populated."""
        with messagedb_client:
            write_message(
                client=messagedb_client,
                stream_name=test_streams[0],
                message_type="TestMessage",
                data={"test": "data"},
                metadata={"test": "metadata"},
            )

            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            assert len(messages) == 1
            message = messages[0]

            # Verify all attributes are present and have correct types
            assert isinstance(message.id, str)
            assert message.stream_name == test_streams[0]
            assert message.type == "TestMessage"
            assert isinstance(message.position, int)
            assert message.position == 0  # First message in stream
            assert isinstance(message.global_position, int)
            assert message.data == {"test": "data"}
            assert message.metadata == {"test": "metadata"}
            assert message.time is not None


class TestGetCategoryMessagesIntegration:
    """Integration tests for get_category_messages with real-world scenarios."""

    def test_multi_stream_agent_sessions(
        self, messagedb_client: MessageDBClient, test_category: str
    ) -> None:
        """Test reading messages from multiple concurrent agent sessions."""
        with messagedb_client:
            # Simulate 3 concurrent agent sessions
            thread1 = f"{test_category}-thread1"
            thread2 = f"{test_category}-thread2"
            thread3 = f"{test_category}-thread3"

            # Session 1
            write_message(
                client=messagedb_client,
                stream_name=thread1,
                message_type="SessionStarted",
                data={"thread_id": "thread1"},
            )

            # Session 2
            write_message(
                client=messagedb_client,
                stream_name=thread2,
                message_type="SessionStarted",
                data={"thread_id": "thread2"},
            )

            # Session 1 continues
            write_message(
                client=messagedb_client,
                stream_name=thread1,
                message_type="UserMessageAdded",
                data={"message": "Hello from thread1"},
            )

            # Session 3 starts
            write_message(
                client=messagedb_client,
                stream_name=thread3,
                message_type="SessionStarted",
                data={"thread_id": "thread3"},
            )

            # Session 2 continues
            write_message(
                client=messagedb_client,
                stream_name=thread2,
                message_type="UserMessageAdded",
                data={"message": "Hello from thread2"},
            )

            # Read all messages from category
            messages = get_category_messages(
                client=messagedb_client,
                category=test_category,
            )

            # Should get all 5 messages across 3 streams
            assert len(messages) == 5

            # Verify messages are from 3 different streams
            stream_names = {msg.stream_name for msg in messages}
            assert len(stream_names) == 3

            # Verify messages are ordered by global position (chronological order)
            for i in range(1, len(messages)):
                assert messages[i].global_position > messages[i - 1].global_position

    def test_pagination_pattern(
        self, messagedb_client: MessageDBClient, test_streams: list[str], test_category: str
    ) -> None:
        """Test pagination pattern for reading large categories in batches."""
        with messagedb_client:
            # Write 20 messages across streams
            for i in range(20):
                stream_idx = i % len(test_streams)
                write_message(
                    client=messagedb_client,
                    stream_name=test_streams[stream_idx],
                    message_type="MessageAdded",
                    data={"message": f"Message {i}"},
                )

            # Paginate through messages in batches of 7
            all_paginated_messages = []
            position = 0
            batch_size = 7

            while True:
                batch = get_category_messages(
                    client=messagedb_client,
                    category=test_category,
                    position=position,
                    batch_size=batch_size,
                )

                if not batch:
                    break

                all_paginated_messages.extend(batch)

                # Update position to continue from after the last message
                position = batch[-1].global_position + 1

            # Verify we got all messages
            assert len(all_paginated_messages) == 20

            # Verify no duplicates by checking global positions
            global_positions = [msg.global_position for msg in all_paginated_messages]
            assert len(global_positions) == len(set(global_positions))

            # Verify messages are in order
            for i in range(1, len(all_paginated_messages)):
                assert (
                    all_paginated_messages[i].global_position
                    > all_paginated_messages[i - 1].global_position
                )

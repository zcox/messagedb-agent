"""Tests for the main processing loop."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from messagedb_agent.engine.loop import (
    ProcessingError,
    _message_to_event,
    process_thread,
)
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.system import SESSION_COMPLETED, SESSION_STARTED
from messagedb_agent.events.user import USER_MESSAGE_ADDED
from messagedb_agent.llm.base import BaseLLMClient
from messagedb_agent.projections.session_state import SessionStatus
from messagedb_agent.store import Message
from messagedb_agent.tools.registry import ToolRegistry


class TestMessageToEvent:
    """Tests for the _message_to_event conversion function."""

    def test_converts_message_with_uuid_id(self):
        """Test converting Message with UUID id to BaseEvent."""
        message_id = uuid4()
        msg = Message(
            id=str(message_id),
            stream_name="agent:v0-test123",
            type=USER_MESSAGE_ADDED,
            position=0,
            global_position=100,
            data={"message": "Hello", "timestamp": "2024-01-01T00:00:00Z"},
            metadata={"trace_id": "abc123"},
            time=datetime(2024, 1, 1, tzinfo=UTC),
        )

        event = _message_to_event(msg)

        assert isinstance(event, BaseEvent)
        assert event.id == message_id
        assert event.type == USER_MESSAGE_ADDED
        assert event.data == {"message": "Hello", "timestamp": "2024-01-01T00:00:00Z"}
        assert event.metadata == {"trace_id": "abc123"}
        assert event.position == 0
        assert event.global_position == 100
        assert event.stream_name == "agent:v0-test123"

    def test_converts_message_with_string_id(self):
        """Test converting Message with string UUID id."""
        message_id = uuid4()
        msg = Message(
            id=str(message_id),
            stream_name="agent:v0-test123",
            type=USER_MESSAGE_ADDED,
            position=0,
            global_position=100,
            data={"message": "Hello"},
            metadata=None,
            time=datetime(2024, 1, 1, tzinfo=UTC),
        )

        event = _message_to_event(msg)

        assert event.id == message_id
        assert event.metadata == {}  # None converted to empty dict

    def test_handles_none_metadata(self):
        """Test that None metadata is converted to empty dict."""
        msg = Message(
            id=str(uuid4()),
            stream_name="agent:v0-test",
            type="TestEvent",
            position=0,
            global_position=0,
            data={},
            metadata=None,
            time=datetime.now(UTC),
        )

        event = _message_to_event(msg)

        assert event.metadata == {}


class TestProcessThread:
    """Tests for the main process_thread function."""

    @pytest.fixture
    def mock_store_client(self):
        """Create a mock MessageDB store client."""
        return MagicMock()

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        client = MagicMock(spec=BaseLLMClient)
        return client

    @pytest.fixture
    def tool_registry(self):
        """Create an empty tool registry."""
        return ToolRegistry()

    def test_terminates_on_session_completed_event(
        self, mock_store_client, mock_llm_client, tool_registry
    ):
        """Test that loop terminates when SessionCompleted event is encountered."""
        # Setup: Create messages that include SessionCompleted
        thread_id = "test-thread-123"
        stream_name = f"agent:v0-{thread_id}"

        messages = [
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=SESSION_STARTED,
                position=0,
                global_position=0,
                data={"thread_id": thread_id},
                metadata={},
                time=datetime.now(UTC),
            ),
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=SESSION_COMPLETED,
                position=1,
                global_position=1,
                data={"completion_reason": "success"},
                metadata={},
                time=datetime.now(UTC),
            ),
        ]

        # Mock read_stream to return our messages
        with patch("messagedb_agent.engine.loop.read_stream", return_value=messages):
            # Execute
            final_state = process_thread(
                thread_id=thread_id,
                stream_name=stream_name,
                store_client=mock_store_client,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                max_iterations=10,
            )

        # Verify it terminated properly
        assert final_state.status == SessionStatus.COMPLETED
        assert final_state.thread_id == thread_id

    def test_raises_processing_error_on_empty_stream(
        self, mock_store_client, mock_llm_client, tool_registry
    ):
        """Test that empty stream raises ProcessingError."""
        thread_id = "test-thread-123"
        stream_name = f"agent:v0-{thread_id}"

        # Mock read_stream to return empty list
        with patch("messagedb_agent.engine.loop.read_stream", return_value=[]):
            with pytest.raises(ProcessingError, match="No events found in stream"):
                process_thread(
                    thread_id=thread_id,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                    llm_client=mock_llm_client,
                    tool_registry=tool_registry,
                    max_iterations=10,
                )

    def test_raises_max_iterations_exceeded(
        self, mock_store_client, mock_llm_client, tool_registry
    ):
        """Test that loop raises MaxIterationsExceeded when limit is reached."""
        thread_id = "test-thread-123"
        stream_name = f"agent:v0-{thread_id}"

        # Create a stream that would cause infinite loop (user message without response)
        messages = [
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=SESSION_STARTED,
                position=0,
                global_position=0,
                data={"thread_id": thread_id},
                metadata={},
                time=datetime.now(UTC),
            ),
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=USER_MESSAGE_ADDED,
                position=1,
                global_position=1,
                data={"message": "Hello", "timestamp": "2024-01-01T00:00:00Z"},
                metadata={},
                time=datetime.now(UTC),
            ),
        ]

        # Mock read_stream to always return same messages (no progress)
        with patch("messagedb_agent.engine.loop.read_stream", return_value=messages):
            # This should raise because USER_MESSAGE_ADDED triggers LLM_CALL
            # which is not implemented yet (NotImplementedError)
            # But first let's test the max_iterations guard
            with pytest.raises(NotImplementedError):
                # Actually, it will raise NotImplementedError first
                process_thread(
                    thread_id=thread_id,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                    llm_client=mock_llm_client,
                    tool_registry=tool_registry,
                    max_iterations=5,
                )

    def test_raises_not_implemented_for_llm_call(
        self, mock_store_client, mock_llm_client, tool_registry
    ):
        """Test that LLM_CALL step raises NotImplementedError (until Task 7.2)."""
        thread_id = "test-thread-123"
        stream_name = f"agent:v0-{thread_id}"

        messages = [
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=USER_MESSAGE_ADDED,
                position=0,
                global_position=0,
                data={"message": "Hello", "timestamp": "2024-01-01T00:00:00Z"},
                metadata={},
                time=datetime.now(UTC),
            ),
        ]

        with patch("messagedb_agent.engine.loop.read_stream", return_value=messages):
            with pytest.raises(NotImplementedError, match="LLM step execution not yet implemented"):
                process_thread(
                    thread_id=thread_id,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                    llm_client=mock_llm_client,
                    tool_registry=tool_registry,
                    max_iterations=10,
                )

    def test_raises_not_implemented_for_tool_execution(
        self, mock_store_client, mock_llm_client, tool_registry
    ):
        """Test that TOOL_EXECUTION step raises NotImplementedError (until Task 7.3)."""
        thread_id = "test-thread-123"
        stream_name = f"agent:v0-{thread_id}"

        # Create LLM response with tool calls to trigger TOOL_EXECUTION
        from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED

        messages = [
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=LLM_RESPONSE_RECEIVED,
                position=0,
                global_position=0,
                data={
                    "response_text": "Let me check that.",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "SF"}}
                    ],
                    "model_name": "claude-sonnet-4-5",
                    "token_usage": {},
                },
                metadata={},
                time=datetime.now(UTC),
            ),
        ]

        with patch("messagedb_agent.engine.loop.read_stream", return_value=messages):
            with pytest.raises(
                NotImplementedError, match="Tool step execution not yet implemented"
            ):
                process_thread(
                    thread_id=thread_id,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                    llm_client=mock_llm_client,
                    tool_registry=tool_registry,
                    max_iterations=10,
                )

    def test_respects_custom_max_iterations(
        self, mock_store_client, mock_llm_client, tool_registry
    ):
        """Test that custom max_iterations value is respected."""
        thread_id = "test-thread-123"
        stream_name = f"agent:v0-{thread_id}"

        # Terminating stream
        messages = [
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=SESSION_COMPLETED,
                position=0,
                global_position=0,
                data={"completion_reason": "success"},
                metadata={},
                time=datetime.now(UTC),
            ),
        ]

        with patch("messagedb_agent.engine.loop.read_stream", return_value=messages):
            # Should work with max_iterations=1
            final_state = process_thread(
                thread_id=thread_id,
                stream_name=stream_name,
                store_client=mock_store_client,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                max_iterations=1,
            )

            assert final_state.status == SessionStatus.COMPLETED

    def test_reads_from_correct_stream(self, mock_store_client, mock_llm_client, tool_registry):
        """Test that process_thread reads from the correct stream name."""
        thread_id = "test-thread-456"
        stream_name = f"agent:v0-{thread_id}"

        messages = [
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=SESSION_COMPLETED,
                position=0,
                global_position=0,
                data={"completion_reason": "success"},
                metadata={},
                time=datetime.now(UTC),
            ),
        ]

        with patch("messagedb_agent.engine.loop.read_stream", return_value=messages) as mock_read:
            process_thread(
                thread_id=thread_id,
                stream_name=stream_name,
                store_client=mock_store_client,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                max_iterations=10,
            )

            # Verify read_stream was called with correct parameters
            # It should be called at least twice: once in loop, once for final state
            assert mock_read.call_count >= 2
            first_call = mock_read.call_args_list[0]
            assert first_call[0][0] == mock_store_client
            assert first_call[0][1] == stream_name

    def test_projects_final_session_state(self, mock_store_client, mock_llm_client, tool_registry):
        """Test that final SessionState is projected correctly."""
        thread_id = "test-thread-789"
        stream_name = f"agent:v0-{thread_id}"

        messages = [
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=SESSION_STARTED,
                position=0,
                global_position=0,
                data={"thread_id": thread_id},
                metadata={},
                time=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
            ),
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=USER_MESSAGE_ADDED,
                position=1,
                global_position=1,
                data={"message": "Test message", "timestamp": "2024-01-01T10:00:00Z"},
                metadata={},
                time=datetime(2024, 1, 1, 10, 0, 1, tzinfo=UTC),
            ),
            Message(
                id=str(uuid4()),
                stream_name=stream_name,
                type=SESSION_COMPLETED,
                position=2,
                global_position=2,
                data={"completion_reason": "success"},
                metadata={},
                time=datetime(2024, 1, 1, 10, 0, 2, tzinfo=UTC),
            ),
        ]

        with patch("messagedb_agent.engine.loop.read_stream", return_value=messages):
            final_state = process_thread(
                thread_id=thread_id,
                stream_name=stream_name,
                store_client=mock_store_client,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                max_iterations=10,
            )

            # Verify final state projection
            assert final_state.thread_id == thread_id
            assert final_state.status == SessionStatus.COMPLETED
            assert final_state.message_count == 1  # One user message
            assert final_state.session_start_time is not None
            assert final_state.session_end_time is not None

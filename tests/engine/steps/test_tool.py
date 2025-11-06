"""Tests for tool step execution."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from messagedb_agent.engine.steps.tool import ToolStepError, execute_tool_step
from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_COMPLETED,
    TOOL_EXECUTION_FAILED,
    TOOL_EXECUTION_REQUESTED,
    TOOL_EXECUTION_STARTED,
)
from messagedb_agent.tools import ToolRegistry, register_tool


class TestExecuteToolStep:
    """Tests for the execute_tool_step function."""

    @pytest.fixture
    def sample_events_with_tool_calls(self):
        """Create sample events with LLM response containing tool calls."""
        return [
            BaseEvent(
                id=uuid4(),
                type=LLM_RESPONSE_RECEIVED,
                data={
                    "response_text": "Let me check that for you.",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "name": "get_weather",
                            "arguments": {"city": "San Francisco"},
                        }
                    ],
                    "model_name": "claude-sonnet-4-5",
                    "token_usage": {},
                },
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(UTC),
                stream_name="agent:v0-test123",
            )
        ]

    @pytest.fixture
    def sample_events_no_tool_calls(self):
        """Create sample events without tool calls."""
        return [
            BaseEvent(
                id=uuid4(),
                type=LLM_RESPONSE_RECEIVED,
                data={
                    "response_text": "I don't need any tools for this.",
                    "tool_calls": [],
                    "model_name": "claude-sonnet-4-5",
                    "token_usage": {},
                },
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(UTC),
                stream_name="agent:v0-test123",
            )
        ]

    @pytest.fixture
    def tool_registry(self):
        """Create a tool registry with a sample tool."""
        registry = ToolRegistry()

        @register_tool(registry=registry, description="Get weather for a city")
        def get_weather(city: str) -> str:
            return f"Weather in {city}: Sunny, 72°F"

        return registry

    @pytest.fixture
    def mock_store_client(self):
        """Create a mock store client."""
        return MagicMock()

    def test_successful_tool_execution_writes_all_events(
        self, sample_events_with_tool_calls, tool_registry, mock_store_client
    ):
        """Test that successful tool execution writes all required events."""
        stream_name = "agent:v0-test123"

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1) as mock_write:
            success = execute_tool_step(
                events=sample_events_with_tool_calls,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Should succeed
        assert success is True

        # Should write 3 events: Requested, Started, Completed
        assert mock_write.call_count == 3

        # Verify first write is ToolExecutionRequested
        first_call = mock_write.call_args_list[0][1]
        assert first_call["message_type"] == TOOL_EXECUTION_REQUESTED
        assert first_call["data"]["tool_name"] == "get_weather"
        assert first_call["data"]["arguments"] == {"city": "San Francisco"}
        assert first_call["metadata"]["tool_id"] == "call_1"

        # Verify second write is ToolExecutionStarted
        second_call = mock_write.call_args_list[1][1]
        assert second_call["message_type"] == TOOL_EXECUTION_STARTED
        assert second_call["data"]["tool_name"] == "get_weather"
        assert second_call["data"]["arguments"] == {"city": "San Francisco"}

        # Verify third write is ToolExecutionCompleted
        third_call = mock_write.call_args_list[2][1]
        assert third_call["message_type"] == TOOL_EXECUTION_COMPLETED
        assert third_call["data"]["tool_name"] == "get_weather"
        assert "Weather in San Francisco" in third_call["data"]["result"]
        assert third_call["data"]["execution_time_ms"] >= 0

    def test_no_tool_calls_returns_success(
        self, sample_events_no_tool_calls, tool_registry, mock_store_client
    ):
        """Test that events with no tool calls return success without writing events."""
        stream_name = "agent:v0-test123"

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1) as mock_write:
            success = execute_tool_step(
                events=sample_events_no_tool_calls,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Should succeed (no tools to execute is success)
        assert success is True

        # Should not write any events
        assert mock_write.call_count == 0

    def test_tool_execution_failure_writes_failed_event(
        self, sample_events_with_tool_calls, mock_store_client
    ):
        """Test that tool execution failure writes ToolExecutionFailed event."""
        stream_name = "agent:v0-test123"

        # Create registry with a tool that will fail
        registry = ToolRegistry()

        @register_tool(registry=registry, description="Get weather")
        def get_weather(city: str) -> str:
            raise ValueError("Weather API unavailable")

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1) as mock_write:
            success = execute_tool_step(
                events=sample_events_with_tool_calls,
                tool_registry=registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Should fail
        assert success is False

        # Should write 3 events: Requested, Started, Failed
        assert mock_write.call_count == 3

        # Verify first write is ToolExecutionRequested
        first_call = mock_write.call_args_list[0][1]
        assert first_call["message_type"] == TOOL_EXECUTION_REQUESTED

        # Verify second write is ToolExecutionStarted
        second_call = mock_write.call_args_list[1][1]
        assert second_call["message_type"] == TOOL_EXECUTION_STARTED

        # Verify third write is ToolExecutionFailed
        third_call = mock_write.call_args_list[2][1]
        assert third_call["message_type"] == TOOL_EXECUTION_FAILED
        assert third_call["data"]["tool_name"] == "get_weather"
        assert "ValueError" in third_call["data"]["error_message"]
        assert "Weather API unavailable" in third_call["data"]["error_message"]
        assert third_call["data"]["retry_count"] == 0

    def test_multiple_tool_calls_all_executed(self, tool_registry, mock_store_client):
        """Test that multiple tool calls are all executed in order."""
        # Create registry with two tools
        registry = ToolRegistry()

        @register_tool(registry=registry, description="Get weather")
        def get_weather(city: str) -> str:
            return f"Weather: {city}"

        @register_tool(registry=registry, description="Get time")
        def get_time() -> str:
            return "12:00 PM"

        # Create events with multiple tool calls
        events = [
            BaseEvent(
                id=uuid4(),
                type=LLM_RESPONSE_RECEIVED,
                data={
                    "response_text": "Let me help.",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}},
                        {"id": "call_2", "name": "get_time", "arguments": {}},
                    ],
                    "model_name": "claude-sonnet-4-5",
                    "token_usage": {},
                },
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(UTC),
                stream_name="agent:v0-test",
            )
        ]

        stream_name = "agent:v0-test"

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1) as mock_write:
            success = execute_tool_step(
                events=events,
                tool_registry=registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Should succeed
        assert success is True

        # Should write 6 events (2 * (requested + started + completed))
        assert mock_write.call_count == 6

        # Verify order: requested, started, completed, requested, started, completed
        assert mock_write.call_args_list[0][1]["message_type"] == TOOL_EXECUTION_REQUESTED
        assert mock_write.call_args_list[0][1]["data"]["tool_name"] == "get_weather"

        assert mock_write.call_args_list[1][1]["message_type"] == TOOL_EXECUTION_STARTED
        assert mock_write.call_args_list[1][1]["data"]["tool_name"] == "get_weather"

        assert mock_write.call_args_list[2][1]["message_type"] == TOOL_EXECUTION_COMPLETED
        assert mock_write.call_args_list[2][1]["data"]["tool_name"] == "get_weather"

        assert mock_write.call_args_list[3][1]["message_type"] == TOOL_EXECUTION_REQUESTED
        assert mock_write.call_args_list[3][1]["data"]["tool_name"] == "get_time"

        assert mock_write.call_args_list[4][1]["message_type"] == TOOL_EXECUTION_STARTED
        assert mock_write.call_args_list[4][1]["data"]["tool_name"] == "get_time"

        assert mock_write.call_args_list[5][1]["message_type"] == TOOL_EXECUTION_COMPLETED
        assert mock_write.call_args_list[5][1]["data"]["tool_name"] == "get_time"

    def test_mixed_success_and_failure_returns_false(self, mock_store_client):
        """Test that if some tools succeed and some fail, returns False."""
        # Create registry with one working and one failing tool
        registry = ToolRegistry()

        @register_tool(registry=registry, description="Working tool")
        def working_tool() -> str:
            return "Success"

        @register_tool(registry=registry, description="Failing tool")
        def failing_tool() -> str:
            raise RuntimeError("Tool error")

        events = [
            BaseEvent(
                id=uuid4(),
                type=LLM_RESPONSE_RECEIVED,
                data={
                    "response_text": "Using tools",
                    "tool_calls": [
                        {"id": "call_1", "name": "working_tool", "arguments": {}},
                        {"id": "call_2", "name": "failing_tool", "arguments": {}},
                    ],
                    "model_name": "claude-sonnet-4-5",
                    "token_usage": {},
                },
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(UTC),
                stream_name="agent:v0-test",
            )
        ]

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1):
            success = execute_tool_step(
                events=events,
                tool_registry=registry,
                stream_name="agent:v0-test",
                store_client=mock_store_client,
            )

        # Should fail overall because one tool failed
        assert success is False

    def test_tool_not_found_writes_failed_event(
        self, sample_events_with_tool_calls, mock_store_client
    ):
        """Test that unknown tool writes ToolExecutionFailed event."""
        stream_name = "agent:v0-test123"

        # Create empty registry (tool won't be found)
        empty_registry = ToolRegistry()

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1) as mock_write:
            success = execute_tool_step(
                events=sample_events_with_tool_calls,
                tool_registry=empty_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Should fail
        assert success is False

        # Should write 3 events: Requested, Started, Failed (tool not found happens during execution)
        assert mock_write.call_count == 3

        # Verify ToolExecutionFailed was written
        third_call = mock_write.call_args_list[2][1]
        assert third_call["message_type"] == TOOL_EXECUTION_FAILED
        assert "not found" in third_call["data"]["error_message"].lower()

    def test_raises_error_if_requested_event_write_fails(
        self, sample_events_with_tool_calls, tool_registry, mock_store_client
    ):
        """Test that ToolStepError is raised if requested event write fails."""
        stream_name = "agent:v0-test123"

        with patch(
            "messagedb_agent.engine.steps.tool.write_message",
            side_effect=Exception("Database error"),
        ):
            with pytest.raises(ToolStepError, match="Failed to write requested event"):
                execute_tool_step(
                    events=sample_events_with_tool_calls,
                    tool_registry=tool_registry,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                )

    def test_raises_error_if_completed_event_write_fails(
        self, sample_events_with_tool_calls, tool_registry, mock_store_client
    ):
        """Test that ToolStepError is raised if started event write fails."""
        stream_name = "agent:v0-test123"

        # First write succeeds (requested), second write fails (started)
        with patch(
            "messagedb_agent.engine.steps.tool.write_message",
            side_effect=[1, Exception("Database error")],
        ):
            with pytest.raises(ToolStepError, match="Failed to write started event"):
                execute_tool_step(
                    events=sample_events_with_tool_calls,
                    tool_registry=tool_registry,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                )

    def test_raises_error_if_failed_event_write_fails(
        self, sample_events_with_tool_calls, mock_store_client
    ):
        """Test that ToolStepError is raised if started event write fails."""
        stream_name = "agent:v0-test123"

        # Create registry with failing tool
        registry = ToolRegistry()

        @register_tool(registry=registry, description="Failing tool")
        def get_weather(city: str) -> str:
            raise ValueError("Error")

        # First write succeeds (requested), second write fails (started)
        with patch(
            "messagedb_agent.engine.steps.tool.write_message",
            side_effect=[1, Exception("Database error")],
        ):
            with pytest.raises(ToolStepError, match="Failed to write started event"):
                execute_tool_step(
                    events=sample_events_with_tool_calls,
                    tool_registry=registry,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                )

    def test_execution_time_tracking(
        self, sample_events_with_tool_calls, tool_registry, mock_store_client
    ):
        """Test that execution time is tracked and included in events."""
        stream_name = "agent:v0-test123"

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1) as mock_write:
            execute_tool_step(
                events=sample_events_with_tool_calls,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Verify execution time is in completed event (third write)
        completed_call = mock_write.call_args_list[2][1]
        assert "execution_time_ms" in completed_call["data"]
        assert completed_call["data"]["execution_time_ms"] >= 0

    def test_tool_index_metadata(self, tool_registry, mock_store_client):
        """Test that tool index is tracked in metadata for multiple tools."""
        # Create events with multiple tool calls
        events = [
            BaseEvent(
                id=uuid4(),
                type=LLM_RESPONSE_RECEIVED,
                data={
                    "response_text": "Using tools",
                    "tool_calls": [
                        {"id": "call_1", "name": "get_weather", "arguments": {"city": "NYC"}},
                        {"id": "call_2", "name": "get_weather", "arguments": {"city": "LA"}},
                    ],
                    "model_name": "claude-sonnet-4-5",
                    "token_usage": {},
                },
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(UTC),
                stream_name="agent:v0-test",
            )
        ]

        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1) as mock_write:
            execute_tool_step(
                events=events,
                tool_registry=tool_registry,
                stream_name="agent:v0-test",
                store_client=mock_store_client,
            )

        # Verify tool_index in metadata (requested, started, completed for each tool)
        # Tool 0
        assert mock_write.call_args_list[0][1]["metadata"]["tool_index"] == 0  # requested
        assert mock_write.call_args_list[1][1]["metadata"]["tool_index"] == 0  # started
        assert mock_write.call_args_list[2][1]["metadata"]["tool_index"] == 0  # completed
        # Tool 1
        assert mock_write.call_args_list[3][1]["metadata"]["tool_index"] == 1  # requested
        assert mock_write.call_args_list[4][1]["metadata"]["tool_index"] == 1  # started
        assert mock_write.call_args_list[5][1]["metadata"]["tool_index"] == 1  # completed

    def test_empty_events_list_returns_success(self, tool_registry, mock_store_client):
        """Test that empty events list returns success."""
        with patch("messagedb_agent.engine.steps.tool.write_message", return_value=1):
            success = execute_tool_step(
                events=[],
                tool_registry=tool_registry,
                stream_name="agent:v0-test",
                store_client=mock_store_client,
            )

        # Empty events means no tool calls, which is considered success
        assert success is True

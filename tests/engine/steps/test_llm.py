"""Tests for LLM step execution."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from messagedb_agent.engine.steps.llm import LLMStepError, execute_llm_step
from messagedb_agent.events.agent import LLM_CALL_FAILED, LLM_CALL_STARTED, LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.user import USER_MESSAGE_ADDED
from messagedb_agent.llm import LLMAPIError, LLMResponse, ToolCall
from messagedb_agent.tools import ToolRegistry


class TestExecuteLLMStep:
    """Tests for the execute_llm_step function."""

    @pytest.fixture
    def sample_events(self):
        """Create sample events for testing."""
        return [
            BaseEvent(
                id=uuid4(),
                type=USER_MESSAGE_ADDED,
                data={"message": "Hello, how are you?", "timestamp": "2024-01-01T00:00:00Z"},
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(UTC),
                stream_name="agent:v0-test123",
            )
        ]

    @pytest.fixture
    def mock_llm_client(self):
        """Create a mock LLM client."""
        return MagicMock()

    @pytest.fixture
    def tool_registry(self):
        """Create an empty tool registry."""
        return ToolRegistry()

    @pytest.fixture
    def mock_store_client(self):
        """Create a mock store client."""
        return MagicMock()

    def test_successful_llm_call_writes_response_event(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that successful LLM call writes LLMResponseReceived event."""
        stream_name = "agent:v0-test123"

        # Mock successful LLM response
        mock_llm_client.call.return_value = LLMResponse(
            text="I'm doing great, thanks!",
            tool_calls=None,
            model_name="claude-sonnet-4-5",
            token_usage={"input_tokens": 10, "output_tokens": 8},
        )

        # Mock successful event write
        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1) as mock_write:
            # Execute LLM step
            success = execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Verify success
        assert success is True

        # Verify LLM was called
        assert mock_llm_client.call.call_count == 1
        call_kwargs = mock_llm_client.call.call_args[1]
        assert len(call_kwargs["messages"]) == 1
        assert call_kwargs["messages"][0].role == "user"
        assert call_kwargs["system_prompt"] is not None

        # Verify both events were written (Started + Response)
        assert mock_write.call_count == 2

        # Check LLMCallStarted event (first call)
        started_args = mock_write.call_args_list[0][1]
        assert started_args["stream_name"] == stream_name
        assert started_args["message_type"] == LLM_CALL_STARTED
        assert "message_count" in started_args["data"]
        assert "tool_count" in started_args["data"]

        # Check LLMResponseReceived event (second call)
        response_args = mock_write.call_args_list[1][1]
        assert response_args["stream_name"] == stream_name
        assert response_args["message_type"] == LLM_RESPONSE_RECEIVED
        assert response_args["data"]["response_text"] == "I'm doing great, thanks!"
        assert response_args["data"]["model_name"] == "claude-sonnet-4-5"
        assert response_args["data"]["tool_calls"] == []

    def test_llm_call_with_tool_calls_includes_them_in_event(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that LLM response with tool calls includes them in the event."""
        stream_name = "agent:v0-test123"

        # Mock LLM response with tool calls
        mock_llm_client.call.return_value = LLMResponse(
            text="Let me check the weather for you.",
            tool_calls=[
                ToolCall(id="call_1", name="get_weather", arguments={"city": "San Francisco"})
            ],
            model_name="claude-sonnet-4-5",
            token_usage={"input_tokens": 15, "output_tokens": 12},
        )

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1) as mock_write:
            success = execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        assert success is True

        # Verify tool calls in event data
        write_args = mock_write.call_args[1]
        assert len(write_args["data"]["tool_calls"]) == 1
        assert write_args["data"]["tool_calls"][0]["id"] == "call_1"
        assert write_args["data"]["tool_calls"][0]["name"] == "get_weather"
        assert write_args["data"]["tool_calls"][0]["arguments"] == {"city": "San Francisco"}

    def test_passes_tools_to_llm_if_registry_has_tools(
        self, sample_events, mock_llm_client, mock_store_client
    ):
        """Test that tool declarations are passed to LLM if registry has tools."""
        from messagedb_agent.tools import register_tool

        # Create registry with a tool
        registry = ToolRegistry()

        @register_tool(registry=registry, description="Get current time")
        def get_time() -> str:
            return "12:00"

        stream_name = "agent:v0-test123"

        mock_llm_client.call.return_value = LLMResponse(
            text="It is 12:00",
            tool_calls=None,
            model_name="claude-sonnet-4-5",
            token_usage={},
        )

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1):
            execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Verify tools were passed
        call_kwargs = mock_llm_client.call.call_args[1]
        assert call_kwargs["tools"] is not None
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0].name == "get_time"

    def test_does_not_pass_tools_if_registry_empty(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that tools parameter is None if registry is empty."""
        stream_name = "agent:v0-test123"

        mock_llm_client.call.return_value = LLMResponse(
            text="Response", tool_calls=None, model_name="claude-sonnet-4-5", token_usage={}
        )

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1):
            execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Verify tools were NOT passed (None)
        call_kwargs = mock_llm_client.call.call_args[1]
        assert call_kwargs["tools"] is None

    def test_uses_custom_system_prompt_if_provided(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that custom system prompt is used when provided."""
        stream_name = "agent:v0-test123"
        custom_prompt = "You are a helpful assistant focused on code."

        mock_llm_client.call.return_value = LLMResponse(
            text="Response", tool_calls=None, model_name="claude-sonnet-4-5", token_usage={}
        )

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1):
            execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
                system_prompt=custom_prompt,
            )

        # Verify custom prompt was used
        call_kwargs = mock_llm_client.call.call_args[1]
        assert call_kwargs["system_prompt"] == custom_prompt

    def test_llm_failure_retries_and_writes_failure_event(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that LLM failure triggers retries and writes LLMCallFailed event."""
        stream_name = "agent:v0-test123"

        # Mock LLM to always fail
        mock_llm_client.call.side_effect = LLMAPIError("API rate limit exceeded")

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1) as mock_write:
            success = execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
                max_retries=2,
            )

        # Verify failure
        assert success is False

        # Verify LLM was called 3 times (initial + 2 retries)
        assert mock_llm_client.call.call_count == 3

        # Verify both events were written (Started + Failed)
        assert mock_write.call_count == 2

        # Check LLMCallStarted event (first call)
        started_args = mock_write.call_args_list[0][1]
        assert started_args["message_type"] == LLM_CALL_STARTED

        # Check LLMCallFailed event (second call)
        failed_args = mock_write.call_args_list[1][1]
        assert failed_args["message_type"] == LLM_CALL_FAILED
        assert "API rate limit exceeded" in failed_args["data"]["error_message"]
        assert failed_args["data"]["retry_count"] == 2

    def test_llm_succeeds_after_retry(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that LLM can succeed after initial failure."""
        stream_name = "agent:v0-test123"

        # Mock LLM to fail twice, then succeed
        mock_llm_client.call.side_effect = [
            LLMAPIError("Temporary error"),
            LLMAPIError("Temporary error"),
            LLMResponse(
                text="Success!", tool_calls=None, model_name="claude-sonnet-4-5", token_usage={}
            ),
        ]

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1) as mock_write:
            success = execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
                max_retries=2,
            )

        # Verify success
        assert success is True

        # Verify LLM was called 3 times
        assert mock_llm_client.call.call_count == 3

        # Verify both events were written (Started + Response)
        assert mock_write.call_count == 2

        # Check LLMCallStarted event (first call)
        started_args = mock_write.call_args_list[0][1]
        assert started_args["message_type"] == LLM_CALL_STARTED

        # Check LLMResponseReceived event (second call)
        response_args = mock_write.call_args_list[1][1]
        assert response_args["message_type"] == LLM_RESPONSE_RECEIVED
        assert response_args["metadata"]["retry_count"] == 2

    def test_raises_error_if_success_event_write_fails(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that LLMStepError is raised if LLMCallStarted event write fails."""
        stream_name = "agent:v0-test123"

        mock_llm_client.call.return_value = LLMResponse(
            text="Response", tool_calls=None, model_name="claude-sonnet-4-5", token_usage={}
        )

        # Mock LLMCallStarted event write to fail
        with patch(
            "messagedb_agent.engine.steps.llm.write_message",
            side_effect=Exception("Database error"),
        ):
            with pytest.raises(LLMStepError, match="Failed to write LLMCallStarted event"):
                execute_llm_step(
                    events=sample_events,
                    llm_client=mock_llm_client,
                    tool_registry=tool_registry,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                )

    def test_raises_error_if_failure_event_write_fails(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that LLMStepError is raised if LLMCallStarted event write fails."""
        stream_name = "agent:v0-test123"

        # Mock LLM to always fail
        mock_llm_client.call.side_effect = LLMAPIError("API error")

        # Mock LLMCallStarted event write to fail (first write)
        with patch(
            "messagedb_agent.engine.steps.llm.write_message",
            side_effect=Exception("Database error"),
        ):
            with pytest.raises(LLMStepError, match="Failed to write LLMCallStarted event"):
                execute_llm_step(
                    events=sample_events,
                    llm_client=mock_llm_client,
                    tool_registry=tool_registry,
                    stream_name=stream_name,
                    store_client=mock_store_client,
                    max_retries=1,
                )

    def test_respects_max_retries_parameter(
        self, sample_events, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that max_retries parameter is respected."""
        stream_name = "agent:v0-test123"

        # Mock LLM to always fail
        mock_llm_client.call.side_effect = LLMAPIError("Error")

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1):
            execute_llm_step(
                events=sample_events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
                max_retries=0,  # No retries
            )

        # Should only call LLM once (no retries)
        assert mock_llm_client.call.call_count == 1

    def test_projects_multiple_events_to_llm_context(
        self, mock_llm_client, tool_registry, mock_store_client
    ):
        """Test that multiple events are correctly projected to LLM context."""
        events = [
            BaseEvent(
                id=uuid4(),
                type=USER_MESSAGE_ADDED,
                data={"message": "First message", "timestamp": "2024-01-01T00:00:00Z"},
                metadata={},
                position=0,
                global_position=0,
                time=datetime.now(UTC),
                stream_name="agent:v0-test",
            ),
            BaseEvent(
                id=uuid4(),
                type=LLM_RESPONSE_RECEIVED,
                data={
                    "response_text": "First response",
                    "tool_calls": [],
                    "model_name": "claude",
                    "token_usage": {},
                },
                metadata={},
                position=1,
                global_position=1,
                time=datetime.now(UTC),
                stream_name="agent:v0-test",
            ),
            BaseEvent(
                id=uuid4(),
                type=USER_MESSAGE_ADDED,
                data={"message": "Second message", "timestamp": "2024-01-01T00:01:00Z"},
                metadata={},
                position=2,
                global_position=2,
                time=datetime.now(UTC),
                stream_name="agent:v0-test",
            ),
        ]

        stream_name = "agent:v0-test"

        mock_llm_client.call.return_value = LLMResponse(
            text="Response", tool_calls=None, model_name="claude-sonnet-4-5", token_usage={}
        )

        with patch("messagedb_agent.engine.steps.llm.write_message", return_value=1):
            execute_llm_step(
                events=events,
                llm_client=mock_llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=mock_store_client,
            )

        # Verify LLM received multiple messages
        call_kwargs = mock_llm_client.call.call_args[1]
        messages = call_kwargs["messages"]
        assert len(messages) == 3  # user, assistant, user
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[2].role == "user"

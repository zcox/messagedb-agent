"""Tests for agent event types."""

import pytest

from messagedb_agent.events.agent import (
    LLM_CALL_FAILED,
    LLM_RESPONSE_RECEIVED,
    LLMCallFailedData,
    LLMResponseReceivedData,
    ToolCall,
)


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_create_tool_call(self):
        """ToolCall can be created with valid fields."""
        tool_call = ToolCall(id="call_123", name="get_current_time", arguments={"timezone": "UTC"})

        assert tool_call.id == "call_123"
        assert tool_call.name == "get_current_time"
        assert tool_call.arguments == {"timezone": "UTC"}

    def test_tool_call_is_immutable(self):
        """ToolCall instances are immutable (frozen)."""
        tool_call = ToolCall(id="call_123", name="test_tool", arguments={})

        with pytest.raises(AttributeError):
            tool_call.id = "modified"  # type: ignore

    def test_tool_call_validates_empty_id(self):
        """ToolCall raises ValueError for empty id."""
        with pytest.raises(ValueError, match="Tool call id cannot be empty"):
            ToolCall(id="", name="test_tool", arguments={})

    def test_tool_call_validates_whitespace_only_id(self):
        """ToolCall raises ValueError for whitespace-only id."""
        with pytest.raises(ValueError, match="Tool call id cannot be empty"):
            ToolCall(id="   ", name="test_tool", arguments={})

    def test_tool_call_validates_empty_name(self):
        """ToolCall raises ValueError for empty name."""
        with pytest.raises(ValueError, match="Tool call name cannot be empty"):
            ToolCall(id="call_123", name="", arguments={})

    def test_tool_call_validates_whitespace_only_name(self):
        """ToolCall raises ValueError for whitespace-only name."""
        with pytest.raises(ValueError, match="Tool call name cannot be empty"):
            ToolCall(id="call_123", name="   ", arguments={})

    def test_tool_call_with_empty_arguments(self):
        """ToolCall can be created with empty arguments dict."""
        tool_call = ToolCall(id="call_123", name="test_tool", arguments={})

        assert tool_call.arguments == {}

    def test_tool_call_with_complex_arguments(self):
        """ToolCall handles complex nested arguments."""
        arguments = {
            "query": "test query",
            "options": {"limit": 10, "offset": 0},
            "filters": ["active", "verified"],
        }
        tool_call = ToolCall(id="call_123", name="search", arguments=arguments)

        assert tool_call.arguments == arguments


class TestLLMResponseReceivedData:
    """Tests for LLMResponseReceivedData event payload."""

    def test_create_llm_response_with_text_only(self):
        """LLMResponseReceivedData can be created with text response only."""
        data = LLMResponseReceivedData(
            response_text="Hello, I can help with that.",
            tool_calls=[],
            model_name="claude-sonnet-4-5@20250929",
            token_usage={"input_tokens": 100, "output_tokens": 20},
        )

        assert data.response_text == "Hello, I can help with that."
        assert data.tool_calls == []
        assert data.model_name == "claude-sonnet-4-5@20250929"
        assert data.token_usage == {"input_tokens": 100, "output_tokens": 20}

    def test_create_llm_response_with_tool_calls_only(self):
        """LLMResponseReceivedData can be created with tool calls only (no text)."""
        tool_call = ToolCall(id="call_123", name="get_current_time", arguments={"timezone": "UTC"})
        data = LLMResponseReceivedData(
            response_text="",
            tool_calls=[tool_call],
            model_name="claude-sonnet-4-5@20250929",
            token_usage={"input_tokens": 100, "output_tokens": 15},
        )

        assert data.response_text == ""
        assert len(data.tool_calls) == 1
        assert data.tool_calls[0].name == "get_current_time"

    def test_create_llm_response_with_text_and_tool_calls(self):
        """LLMResponseReceivedData can have both text and tool calls."""
        tool_call = ToolCall(id="call_123", name="search", arguments={"query": "test"})
        data = LLMResponseReceivedData(
            response_text="Let me search for that.",
            tool_calls=[tool_call],
            model_name="gemini-2.5-pro",
            token_usage={"input_tokens": 50, "output_tokens": 25},
        )

        assert data.response_text == "Let me search for that."
        assert len(data.tool_calls) == 1

    def test_llm_response_data_is_immutable(self):
        """LLMResponseReceivedData instances are immutable (frozen)."""
        data = LLMResponseReceivedData(
            response_text="Test",
            tool_calls=[],
            model_name="test-model",
            token_usage={},
        )

        with pytest.raises(AttributeError):
            data.response_text = "Modified"  # type: ignore

    def test_llm_response_validates_empty_model_name(self):
        """LLMResponseReceivedData raises ValueError for empty model_name."""
        with pytest.raises(ValueError, match="Model name cannot be empty"):
            LLMResponseReceivedData(
                response_text="Test", tool_calls=[], model_name="", token_usage={}
            )

    def test_llm_response_validates_whitespace_only_model_name(self):
        """LLMResponseReceivedData raises ValueError for whitespace-only model_name."""
        with pytest.raises(ValueError, match="Model name cannot be empty"):
            LLMResponseReceivedData(
                response_text="Test", tool_calls=[], model_name="   ", token_usage={}
            )

    def test_llm_response_validates_empty_response_and_no_tools(self):
        """LLMResponseReceivedData requires either text or tool calls."""
        with pytest.raises(
            ValueError, match="LLM response must contain either response_text or tool_calls"
        ):
            LLMResponseReceivedData(
                response_text="", tool_calls=[], model_name="test-model", token_usage={}
            )

    def test_llm_response_validates_whitespace_only_text_and_no_tools(self):
        """LLMResponseReceivedData rejects whitespace-only text with no tools."""
        with pytest.raises(
            ValueError, match="LLM response must contain either response_text or tool_calls"
        ):
            LLMResponseReceivedData(
                response_text="   ",
                tool_calls=[],
                model_name="test-model",
                token_usage={},
            )

    def test_llm_response_with_multiple_tool_calls(self):
        """LLMResponseReceivedData can contain multiple tool calls."""
        tool_calls = [
            ToolCall(id="call_1", name="tool_a", arguments={"arg1": "val1"}),
            ToolCall(id="call_2", name="tool_b", arguments={"arg2": "val2"}),
            ToolCall(id="call_3", name="tool_c", arguments={}),
        ]
        data = LLMResponseReceivedData(
            response_text="",
            tool_calls=tool_calls,
            model_name="test-model",
            token_usage={},
        )

        assert len(data.tool_calls) == 3
        assert data.tool_calls[0].name == "tool_a"
        assert data.tool_calls[1].name == "tool_b"
        assert data.tool_calls[2].name == "tool_c"

    def test_llm_response_with_empty_token_usage(self):
        """LLMResponseReceivedData can be created with empty token_usage."""
        data = LLMResponseReceivedData(
            response_text="Test", tool_calls=[], model_name="test-model", token_usage={}
        )

        assert data.token_usage == {}

    def test_llm_response_with_detailed_token_usage(self):
        """LLMResponseReceivedData handles detailed token usage statistics."""
        token_usage = {
            "input_tokens": 1500,
            "output_tokens": 250,
            "cache_read_tokens": 500,
            "cache_write_tokens": 300,
        }
        data = LLMResponseReceivedData(
            response_text="Test",
            tool_calls=[],
            model_name="test-model",
            token_usage=token_usage,
        )

        assert data.token_usage == token_usage

    def test_llm_response_with_multiline_text(self):
        """LLMResponseReceivedData handles multiline response text."""
        response_text = """This is a
        multiline
        response from the LLM."""
        data = LLMResponseReceivedData(
            response_text=response_text,
            tool_calls=[],
            model_name="test-model",
            token_usage={},
        )

        assert data.response_text == response_text


class TestLLMCallFailedData:
    """Tests for LLMCallFailedData event payload."""

    def test_create_llm_call_failed_data(self):
        """LLMCallFailedData can be created with error message and retry count."""
        data = LLMCallFailedData(error_message="API rate limit exceeded", retry_count=0)

        assert data.error_message == "API rate limit exceeded"
        assert data.retry_count == 0

    def test_llm_call_failed_data_is_immutable(self):
        """LLMCallFailedData instances are immutable (frozen)."""
        data = LLMCallFailedData(error_message="Test error", retry_count=0)

        with pytest.raises(AttributeError):
            data.error_message = "Modified"  # type: ignore

    def test_llm_call_failed_validates_empty_error_message(self):
        """LLMCallFailedData raises ValueError for empty error_message."""
        with pytest.raises(ValueError, match="Error message cannot be empty"):
            LLMCallFailedData(error_message="", retry_count=0)

    def test_llm_call_failed_validates_whitespace_only_error_message(self):
        """LLMCallFailedData raises ValueError for whitespace-only error_message."""
        with pytest.raises(ValueError, match="Error message cannot be empty"):
            LLMCallFailedData(error_message="   ", retry_count=0)

    def test_llm_call_failed_validates_negative_retry_count(self):
        """LLMCallFailedData raises ValueError for negative retry_count."""
        with pytest.raises(ValueError, match="Retry count must be >= 0"):
            LLMCallFailedData(error_message="Test error", retry_count=-1)

    def test_llm_call_failed_with_zero_retry_count(self):
        """LLMCallFailedData accepts retry_count of 0 (first failure)."""
        data = LLMCallFailedData(error_message="First failure", retry_count=0)

        assert data.retry_count == 0

    def test_llm_call_failed_with_multiple_retries(self):
        """LLMCallFailedData can track multiple retry attempts."""
        data = LLMCallFailedData(error_message="Still failing after retries", retry_count=3)

        assert data.retry_count == 3

    def test_llm_call_failed_with_various_error_messages(self):
        """LLMCallFailedData accepts various error message types."""
        error_messages = [
            "Connection timeout",
            "Invalid API key",
            "Model not found",
            "Request too large",
            "Internal server error (500)",
        ]

        for error_msg in error_messages:
            data = LLMCallFailedData(error_message=error_msg, retry_count=0)
            assert data.error_message == error_msg

    def test_llm_call_failed_with_multiline_error_message(self):
        """LLMCallFailedData handles multiline error messages."""
        error_message = """API Error:
        Status: 429
        Message: Rate limit exceeded
        Retry after: 60 seconds"""
        data = LLMCallFailedData(error_message=error_message, retry_count=0)

        assert data.error_message == error_message


class TestEventTypeConstants:
    """Tests for event type constants."""

    def test_llm_response_received_constant(self):
        """LLM_RESPONSE_RECEIVED constant has correct value."""
        assert LLM_RESPONSE_RECEIVED == "LLMResponseReceived"

    def test_llm_call_failed_constant(self):
        """LLM_CALL_FAILED constant has correct value."""
        assert LLM_CALL_FAILED == "LLMCallFailed"

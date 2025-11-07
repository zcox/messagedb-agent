"""Integration tests for LLM streaming interface.

These tests verify that both Gemini and Claude models support streaming
through the unified BaseLLMClient interface.

To run these tests, you need:
1. GCP credentials configured (via `gcloud auth application-default login`)
2. Environment variables set:
   - GCP_PROJECT: Your GCP project ID
   - GCP_LOCATION: GCP region (default: us-central1)
3. Vertex AI API enabled in your GCP project

Run with: pytest tests/llm/test_streaming_integration.py -v -s
Skip with: pytest -m "not integration"
"""

import os

import pytest

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.llm import (
    Message,
    StreamDelta,
    ToolDeclaration,
    create_llm_client,
)

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


@pytest.fixture
def gcp_project():
    """Get GCP project from environment or skip test."""
    project = os.getenv("GCP_PROJECT")
    if not project:
        pytest.skip("GCP_PROJECT environment variable not set")
    return project


@pytest.fixture
def gcp_location():
    """Get GCP location from environment with default."""
    return os.getenv("GCP_LOCATION", "us-central1")


@pytest.fixture
def gemini_client(gcp_project, gcp_location):
    """Create unified client for Gemini model."""
    config = VertexAIConfig(
        project=gcp_project,
        location=gcp_location,
        model_name="gemini-2.5-flash",
    )
    return create_llm_client(config)


@pytest.fixture
def claude_client(gcp_project, gcp_location):
    """Create unified client for Claude model."""
    config = VertexAIConfig(
        project=gcp_project,
        location=gcp_location,
        model_name="claude-sonnet-4-5@20250929",
    )
    return create_llm_client(config)


class TestClaudeStreaming:
    """Test Claude streaming through the unified interface."""

    def test_claude_simple_text_streaming(self, claude_client):
        """Test basic text streaming with Claude."""
        messages = [Message(role="user", text="Count from 1 to 5.")]

        deltas = list(claude_client.call_stream(messages))

        # Should have at least some text deltas and a final done delta
        text_deltas = [d for d in deltas if d.delta_type == "text"]
        done_deltas = [d for d in deltas if d.delta_type == "done"]

        assert len(text_deltas) > 0, "Should have text deltas"
        assert len(done_deltas) == 1, "Should have exactly one done delta"

        # Concatenate all text
        full_text = "".join(d.text for d in text_deltas if d.text)
        assert len(full_text) > 0, "Should have received text content"

        # Check token usage
        done_delta = done_deltas[0]
        assert done_delta.token_usage is not None
        assert "input_tokens" in done_delta.token_usage
        assert "output_tokens" in done_delta.token_usage
        assert "total_tokens" in done_delta.token_usage

        print(f"\n[Claude Streaming] Full text: {full_text}")
        print(f"[Claude Streaming] Token usage: {done_delta.token_usage}")
        print(f"[Claude Streaming] Text deltas received: {len(text_deltas)}")

    def test_claude_streaming_with_system_prompt(self, claude_client):
        """Test Claude streaming with system prompt."""
        messages = [Message(role="user", text="What is 2+2?")]

        deltas = list(
            claude_client.call_stream(
                messages,
                system_prompt="You are a concise calculator. Respond with only the answer.",
            )
        )

        text_deltas = [d for d in deltas if d.delta_type == "text"]
        assert len(text_deltas) > 0

        full_text = "".join(d.text for d in text_deltas if d.text)
        print(f"\n[Claude Streaming with system] Response: {full_text}")

    def test_claude_streaming_tool_calls(self, claude_client):
        """Test Claude streaming with tool calls."""
        tool = ToolDeclaration(
            name="calculate",
            description="Perform a mathematical calculation",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate",
                    }
                },
                "required": ["expression"],
            },
        )

        messages = [Message(role="user", text="What is 25 * 4?")]

        deltas = list(claude_client.call_stream(messages, tools=[tool]))

        # Should have tool call deltas
        tool_call_deltas = [d for d in deltas if d.delta_type == "tool_call"]
        tool_input_deltas = [d for d in deltas if d.delta_type == "tool_input"]
        done_deltas = [d for d in deltas if d.delta_type == "done"]

        assert len(tool_call_deltas) > 0, "Should have tool call deltas"
        assert len(done_deltas) == 1, "Should have exactly one done delta"

        # Check first tool call
        first_tool_call = tool_call_deltas[0]
        assert first_tool_call.tool_call_id is not None
        assert first_tool_call.tool_name == "calculate"
        assert first_tool_call.tool_call_index is not None

        print(f"\n[Claude Streaming tools] Tool call deltas: {len(tool_call_deltas)}")
        print(f"[Claude Streaming tools] Tool input deltas: {len(tool_input_deltas)}")
        if tool_input_deltas:
            full_input = "".join(
                d.tool_input_delta for d in tool_input_deltas if d.tool_input_delta
            )
            print(f"[Claude Streaming tools] Full tool input: {full_input}")


class TestGeminiStreaming:
    """Test Gemini streaming through the unified interface."""

    def test_gemini_simple_text_streaming(self, gemini_client):
        """Test basic text streaming with Gemini."""
        messages = [Message(role="user", text="Write a short haiku about coding.")]

        deltas = list(gemini_client.call_stream(messages))

        # Should have at least some text deltas and a final done delta
        text_deltas = [d for d in deltas if d.delta_type == "text"]
        done_deltas = [d for d in deltas if d.delta_type == "done"]

        assert len(text_deltas) > 0, "Should have text deltas"
        assert len(done_deltas) == 1, "Should have exactly one done delta"

        # Concatenate all text
        full_text = "".join(d.text for d in text_deltas if d.text)
        assert len(full_text) > 0, "Should have received text content"

        # Check token usage
        done_delta = done_deltas[0]
        assert done_delta.token_usage is not None

        print(f"\n[Gemini Streaming] Full text: {full_text}")
        print(f"[Gemini Streaming] Token usage: {done_delta.token_usage}")
        print(f"[Gemini Streaming] Text deltas received: {len(text_deltas)}")

    def test_gemini_streaming_with_system_prompt(self, gemini_client):
        """Test Gemini streaming with system prompt."""
        messages = [Message(role="user", text="What is the capital of France?")]

        deltas = list(
            gemini_client.call_stream(
                messages,
                system_prompt="You are a geography expert. Be concise.",
            )
        )

        text_deltas = [d for d in deltas if d.delta_type == "text"]
        assert len(text_deltas) > 0

        full_text = "".join(d.text for d in text_deltas if d.text)
        print(f"\n[Gemini Streaming with system] Response: {full_text}")

    def test_gemini_streaming_tool_calls(self, gemini_client):
        """Test Gemini streaming with tool calls."""
        tool = ToolDeclaration(
            name="get_weather",
            description="Get the current weather for a location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and state",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                },
                "required": ["location"],
            },
        )

        messages = [Message(role="user", text="What's the weather in Tokyo?")]

        deltas = list(gemini_client.call_stream(messages, tools=[tool]))

        # Should have tool call deltas
        tool_call_deltas = [d for d in deltas if d.delta_type == "tool_call"]
        done_deltas = [d for d in deltas if d.delta_type == "done"]

        assert len(tool_call_deltas) > 0, "Should have tool call deltas"
        assert len(done_deltas) == 1, "Should have exactly one done delta"

        # Check first tool call
        first_tool_call = tool_call_deltas[0]
        assert first_tool_call.tool_call_id is not None
        assert first_tool_call.tool_name == "get_weather"
        assert first_tool_call.tool_call_index is not None

        print(f"\n[Gemini Streaming tools] Tool call deltas: {len(tool_call_deltas)}")


class TestStreamingCrossModelCompatibility:
    """Test that streaming works consistently across both models."""

    def test_both_models_stream_text(self, gemini_client, claude_client):
        """Verify both models can stream text responses."""
        messages = [Message(role="user", text="Say hello in exactly three words.")]

        # Test Gemini
        gemini_deltas = list(gemini_client.call_stream(messages))
        gemini_text_deltas = [d for d in gemini_deltas if d.delta_type == "text"]
        gemini_done_deltas = [d for d in gemini_deltas if d.delta_type == "done"]
        gemini_text = "".join(d.text for d in gemini_text_deltas if d.text)

        assert len(gemini_text_deltas) > 0
        assert len(gemini_done_deltas) == 1
        assert len(gemini_text) > 0

        # Test Claude
        claude_deltas = list(claude_client.call_stream(messages))
        claude_text_deltas = [d for d in claude_deltas if d.delta_type == "text"]
        claude_done_deltas = [d for d in claude_deltas if d.delta_type == "done"]
        claude_text = "".join(d.text for d in claude_text_deltas if d.text)

        assert len(claude_text_deltas) > 0
        assert len(claude_done_deltas) == 1
        assert len(claude_text) > 0

        print(f"\n[Streaming compatibility] Gemini text: {gemini_text}")
        print(f"[Streaming compatibility] Claude text: {claude_text}")

    def test_stream_delta_types_consistent(self, gemini_client, claude_client):
        """Verify both models use the same StreamDelta types."""
        messages = [Message(role="user", text="Hello!")]

        # Collect deltas from both
        gemini_deltas = list(gemini_client.call_stream(messages))
        claude_deltas = list(claude_client.call_stream(messages))

        # Both should have done deltas
        assert any(d.delta_type == "done" for d in gemini_deltas)
        assert any(d.delta_type == "done" for d in claude_deltas)

        # Both should have text deltas
        assert any(d.delta_type == "text" for d in gemini_deltas)
        assert any(d.delta_type == "text" for d in claude_deltas)

        # Verify all deltas are StreamDelta instances
        for delta in gemini_deltas + claude_deltas:
            assert isinstance(delta, StreamDelta)

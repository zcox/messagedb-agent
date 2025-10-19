"""Integration tests for unified LLM client interface.

These tests verify that both Gemini and Claude models work through the
unified BaseLLMClient interface, using the new create_llm_client factory.

To run these tests, you need:
1. GCP credentials configured (via `gcloud auth application-default login`)
2. Environment variables set:
   - GCP_PROJECT: Your GCP project ID
   - GCP_LOCATION: GCP region (default: us-central1)
3. Vertex AI API enabled in your GCP project

Run with: pytest tests/llm/test_unified_integration.py -v -s
Skip with: pytest -m "not integration"
"""

import os

import pytest

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.llm import (
    Message,
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


class TestUnifiedGeminiInterface:
    """Test Gemini models through the unified BaseLLMClient interface."""

    def test_gemini_simple_text_generation(self, gemini_client):
        """Test basic text generation with Gemini through unified API."""
        messages = [Message(role="user", text="Write a haiku about coding.")]

        response = gemini_client.call(messages)

        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        assert response.model_name == "gemini-2.5-flash"
        assert response.tool_calls == []

        assert "input_tokens" in response.token_usage or "total_tokens" in response.token_usage
        print(f"\n[Gemini Unified] Response: {response.text}")
        print(f"[Gemini Unified] Token usage: {response.token_usage}")

    def test_gemini_with_system_prompt(self, gemini_client):
        """Test Gemini with system prompt through unified API."""
        messages = [Message(role="user", text="What is 2+2?")]

        response = gemini_client.call(
            messages,
            system_prompt="You are a helpful math tutor. Always show your work.",
        )

        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        print(f"\n[Gemini Unified with system] Response: {response.text}")

    def test_gemini_function_calling(self, gemini_client):
        """Test Gemini function calling through unified API."""
        tool = ToolDeclaration(
            name="get_weather",
            description="Get the current weather for a location",
            parameters={
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and state, e.g. San Francisco, CA",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "Temperature unit",
                    },
                },
                "required": ["location"],
            },
        )

        messages = [Message(role="user", text="What's the weather in San Francisco?")]

        response = gemini_client.call(messages, tools=[tool])

        assert response is not None
        assert len(response.tool_calls) > 0
        assert response.tool_calls[0].name == "get_weather"
        assert "location" in response.tool_calls[0].arguments

        print(f"\n[Gemini Unified function call] Tool calls: {response.tool_calls}")
        if response.text:
            print(f"[Gemini Unified function call] Text: {response.text}")


class TestUnifiedClaudeInterface:
    """Test Claude models through the unified BaseLLMClient interface."""

    def test_claude_simple_text_generation(self, claude_client):
        """Test basic text generation with Claude through unified API."""
        messages = [Message(role="user", text="Write a haiku about programming.")]

        response = claude_client.call(messages)

        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        assert response.model_name == "claude-sonnet-4-5@20250929"
        assert response.tool_calls == []

        assert "input_tokens" in response.token_usage
        assert "output_tokens" in response.token_usage
        print(f"\n[Claude Unified] Response: {response.text}")
        print(f"[Claude Unified] Token usage: {response.token_usage}")

    def test_claude_with_system_prompt(self, claude_client):
        """Test Claude with system prompt through unified API."""
        messages = [Message(role="user", text="What is 2+2?")]

        response = claude_client.call(
            messages,
            system_prompt="You are a concise calculator. Respond with only the numerical answer.",
        )

        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        print(f"\n[Claude Unified with system] Response: {response.text}")

    def test_claude_function_calling(self, claude_client):
        """Test Claude function calling through unified API."""
        tool = ToolDeclaration(
            name="calculate",
            description="Perform a mathematical calculation",
            parameters={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate, e.g. '2 + 2'",
                    }
                },
                "required": ["expression"],
            },
        )

        messages = [Message(role="user", text="What is 15 * 7?")]

        response = claude_client.call(messages, tools=[tool])

        assert response is not None
        # Claude should use the tool
        assert len(response.tool_calls) > 0
        assert response.tool_calls[0].name == "calculate"
        assert "expression" in response.tool_calls[0].arguments

        print(f"\n[Claude Unified function call] Tool calls: {response.tool_calls}")
        if response.text:
            print(f"[Claude Unified function call] Text: {response.text}")

    def test_claude_multi_turn_conversation(self, claude_client):
        """Test Claude multi-turn conversation with tool use."""
        # First turn: ask for calculation
        tool = ToolDeclaration(
            name="calculate",
            description="Perform a mathematical calculation",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "Math expression"}},
                "required": ["expression"],
            },
        )

        messages = [Message(role="user", text="What is 100 divided by 5?")]

        response1 = claude_client.call(messages, tools=[tool])

        # Should call the tool
        assert len(response1.tool_calls) > 0
        tool_call = response1.tool_calls[0]

        print(f"\n[Claude multi-turn] First response: {response1.text}")
        print(f"[Claude multi-turn] Tool call: {tool_call}")

        # Second turn: provide tool result
        messages.append(
            Message(
                role="assistant",
                text=response1.text,
                tool_calls=response1.tool_calls,
            )
        )
        messages.append(
            Message(
                role="tool",
                text="20",
                tool_call_id=tool_call.id,
                tool_name=tool_call.name,
            )
        )

        response2 = claude_client.call(messages)

        # Should respond with the answer
        assert response2.text is not None
        print(f"[Claude multi-turn] Second response: {response2.text}")


class TestCrossModelCompatibility:
    """Test that the same code works with both Gemini and Claude."""

    def test_same_interface_both_models(self, gemini_client, claude_client):
        """Verify the unified interface works identically for both models."""
        prompt = "Respond with exactly three words."
        messages = [Message(role="user", text=prompt)]

        # Test with Gemini
        gemini_response = gemini_client.call(messages)
        assert gemini_response is not None
        assert gemini_response.text is not None
        assert gemini_response.model_name == "gemini-2.5-flash"

        # Test with Claude
        claude_response = claude_client.call(messages)
        assert claude_response is not None
        assert claude_response.text is not None
        assert claude_response.model_name == "claude-sonnet-4-5@20250929"

        print(f"\n[Unified API] Gemini response: {gemini_response.text}")
        print(f"[Unified API] Claude response: {claude_response.text}")

        # Both should have token usage
        assert gemini_response.token_usage
        assert claude_response.token_usage

    def test_same_tool_declaration_both_models(self, gemini_client, claude_client):
        """Verify the same tool declaration works for both models."""
        tool = ToolDeclaration(
            name="get_time",
            description="Get the current time",
            parameters={
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone name, e.g. America/New_York",
                    }
                },
            },
        )

        messages = [Message(role="user", text="What time is it in New York?")]

        # Both should be able to use the same tool
        gemini_response = gemini_client.call(messages, tools=[tool])
        claude_response = claude_client.call(messages, tools=[tool])

        print(f"\n[Tool compatibility] Gemini tool calls: {gemini_response.tool_calls}")
        print(f"[Tool compatibility] Claude tool calls: {claude_response.tool_calls}")

        # At least one should call the tool (both models should support it)
        assert len(gemini_response.tool_calls) > 0 or len(claude_response.tool_calls) > 0

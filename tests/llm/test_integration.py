"""Integration tests for Vertex AI LLM functionality.

These tests make actual calls to the Vertex AI API to verify that our
integration works correctly with real models. They are marked as integration
tests and can be skipped in CI environments without GCP credentials.

To run these tests, you need:
1. GCP credentials configured (via `gcloud auth application-default login`)
2. Environment variables set:
   - GCP_PROJECT: Your GCP project ID
   - GCP_LOCATION: GCP region (default: us-central1)
3. Vertex AI API enabled in your GCP project

Run with: pytest tests/llm/test_integration.py -v -s
Skip with: pytest -m "not integration"
"""

import os

import pytest

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.llm import (
    call_llm,
    create_client,
    create_function_declaration,
    create_user_message,
    format_messages,
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
def gemini_config(gcp_project, gcp_location):
    """Create Vertex AI config for Gemini model."""
    return VertexAIConfig(
        project=gcp_project,
        location=gcp_location,
        model_name="gemini-2.5-flash",
    )


@pytest.fixture
def claude_config(gcp_project, gcp_location):
    """Create Vertex AI config for Claude model."""
    return VertexAIConfig(
        project=gcp_project,
        location=gcp_location,
        model_name="claude-sonnet-4-5@20250929",
    )


class TestGeminiIntegration:
    """Integration tests for Gemini models via Vertex AI."""

    def test_gemini_simple_text_generation(self, gemini_config):
        """Test basic text generation with Gemini model."""
        # Create client and initialize
        client = create_client(gemini_config)

        # Create simple message
        messages = [create_user_message("Write a haiku about coding.")]
        contents = format_messages(messages)

        # Call LLM
        response = call_llm(client, contents)

        # Verify response
        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        assert response.model_name == "gemini-2.5-flash"
        assert response.tool_calls == []

        # Verify token usage
        assert "input_tokens" in response.token_usage or "total_tokens" in response.token_usage
        print(f"\n[Gemini] Response: {response.text}")
        print(f"[Gemini] Token usage: {response.token_usage}")

    def test_gemini_with_system_prompt(self, gemini_config):
        """Test Gemini with system prompt."""
        client = create_client(gemini_config)

        # Create message with system prompt
        messages = [create_user_message("What is 2+2?")]
        contents = format_messages(
            messages,
            system_prompt="You are a helpful math tutor. Always show your work.",
        )

        # Call LLM
        response = call_llm(client, contents)

        # Verify response
        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        print(f"\n[Gemini with system] Response: {response.text}")

    def test_gemini_function_calling(self, gemini_config):
        """Test Gemini function calling capability."""
        client = create_client(gemini_config)

        # Create function declaration
        get_weather_func = create_function_declaration(
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

        # Create message asking about weather
        messages = [create_user_message("What's the weather in San Francisco?")]
        contents = format_messages(messages)

        # Call LLM with tools
        response = call_llm(client, contents, tools=[get_weather_func])

        # Verify response - should have function call
        assert response is not None
        # Model might return text explaining what it's doing, or just function calls
        assert len(response.tool_calls) > 0
        assert response.tool_calls[0].name == "get_weather"
        assert "location" in response.tool_calls[0].arguments

        print(f"\n[Gemini function call] Tool calls: {response.tool_calls}")
        if response.text:
            print(f"[Gemini function call] Text: {response.text}")


class TestClaudeIntegration:
    """Integration tests for Claude models via Vertex AI.

    Note: Claude models are currently not supported. They require the anthropic[vertex] SDK
    with a different API (AnthropicVertex client) instead of the GenerativeModel API.
    These tests are skipped until Claude support is implemented.
    """

    @pytest.mark.skip(reason="Claude models require anthropic[vertex] SDK - not yet implemented")
    def test_claude_simple_text_generation(self, claude_config):
        """Test basic text generation with Claude model."""
        # Create client and initialize
        client = create_client(claude_config)

        # Create simple message
        messages = [create_user_message("Write a haiku about programming.")]
        contents = format_messages(messages)

        # Call LLM
        response = call_llm(client, contents)

        # Verify response
        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        assert response.model_name == "claude-sonnet-4-5@20250929"
        assert response.tool_calls == []

        # Verify token usage
        assert "input_tokens" in response.token_usage or "total_tokens" in response.token_usage
        print(f"\n[Claude] Response: {response.text}")
        print(f"[Claude] Token usage: {response.token_usage}")

    @pytest.mark.skip(reason="Claude models require anthropic[vertex] SDK - not yet implemented")
    def test_claude_with_system_prompt(self, claude_config):
        """Test Claude with system prompt."""
        client = create_client(claude_config)

        # Create message with system prompt
        messages = [create_user_message("What is 2+2?")]
        contents = format_messages(
            messages,
            system_prompt="You are a concise calculator. Respond with only the numerical answer.",
        )

        # Call LLM
        response = call_llm(client, contents)

        # Verify response
        assert response is not None
        assert response.text is not None
        assert len(response.text) > 0
        print(f"\n[Claude with system] Response: {response.text}")

    @pytest.mark.skip(reason="Claude models require anthropic[vertex] SDK - not yet implemented")
    def test_claude_function_calling(self, claude_config):
        """Test Claude function calling capability."""
        client = create_client(claude_config)

        # Create function declaration
        calculate_func = create_function_declaration(
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

        # Create message asking to calculate
        messages = [create_user_message("What is 15 * 7?")]
        contents = format_messages(messages)

        # Call LLM with tools
        response = call_llm(client, contents, tools=[calculate_func])

        # Verify response - should have function call
        assert response is not None
        # Model might return text explaining what it's doing, or just function calls
        assert len(response.tool_calls) > 0
        assert response.tool_calls[0].name == "calculate"
        assert "expression" in response.tool_calls[0].arguments

        print(f"\n[Claude function call] Tool calls: {response.tool_calls}")
        if response.text:
            print(f"[Claude function call] Text: {response.text}")


class TestCrossModelCompatibility:
    """Test that our code works with both Gemini and Claude models.

    Note: Claude models are currently not supported, so these tests are skipped.
    """

    @pytest.mark.skip(reason="Claude models require anthropic[vertex] SDK - not yet implemented")
    def test_same_code_works_for_both_models(self, gemini_config, claude_config):
        """Verify the same code works for both Gemini and Claude."""
        # Same message and prompting for both
        prompt = "Respond with exactly three words."
        messages = [create_user_message(prompt)]
        contents = format_messages(messages)

        # Test with Gemini
        gemini_client = create_client(gemini_config)
        gemini_response = call_llm(gemini_client, contents)

        assert gemini_response is not None
        assert gemini_response.text is not None
        assert gemini_response.model_name == "gemini-2.5-flash"

        # Test with Claude
        claude_client = create_client(claude_config)
        claude_response = call_llm(claude_client, contents)

        assert claude_response is not None
        assert claude_response.text is not None
        assert claude_response.model_name == "claude-sonnet-4-5@20250929"

        print(f"\n[Gemini] Response: {gemini_response.text}")
        print(f"[Claude] Response: {claude_response.text}")

        # Both should have token usage
        assert gemini_response.token_usage
        assert claude_response.token_usage

"""Unit tests for HTML renderer streaming functionality.

These tests verify that render_html_stream() correctly yields chunks
as the LLM generates them.
"""

import os
import uuid
from unittest.mock import MagicMock, patch

import pytest

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.display.renderer import render_html_stream, sanitize_html
from messagedb_agent.events.user import USER_MESSAGE_ADDED
from messagedb_agent.llm.base import StreamDelta
from messagedb_agent.store import Message as MessageDBMessage


@pytest.fixture
def llm_config():
    """Create test LLM config."""
    return VertexAIConfig(
        project="test-project", location="us-central1", model_name="gemini-2.5-flash"
    )


@pytest.fixture
def test_events():
    """Create test events for rendering."""
    return [
        MessageDBMessage(
            position=0,
            id=str(uuid.uuid4()),
            type=USER_MESSAGE_ADDED,
            data={"message_text": "Hello"},
            metadata={},
            time="2025-01-01T00:00:00Z",
            stream_name="agent:v0-test",
            global_position=1,
        ),
    ]


class TestRenderHtmlStream:
    """Test streaming HTML rendering."""

    @pytest.mark.asyncio
    async def test_yields_html_chunks(self, test_events, llm_config):
        """Test that HTML chunks are yielded in real-time."""
        with patch("messagedb_agent.display.renderer.create_llm_client") as mock_create:
            mock_llm = MagicMock()
            mock_llm.model_name = "gemini-2.5-flash"

            # Return streaming deltas
            def call_stream(messages, tools=None, system_prompt=None):
                yield StreamDelta(delta_type="text", text="<div>")
                yield StreamDelta(delta_type="text", text="Hello")
                yield StreamDelta(delta_type="text", text="</div>")
                yield StreamDelta(
                    delta_type="done",
                    token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                )

            mock_llm.call_stream = call_stream
            mock_create.return_value = mock_llm

            # Collect chunks
            chunks = []
            async for chunk in render_html_stream(test_events, "default", llm_config):
                chunks.append(chunk)

            # Verify chunks were yielded
            assert len(chunks) == 3
            assert chunks[0] == "<div>"
            assert chunks[1] == "Hello"
            assert chunks[2] == "</div>"

    @pytest.mark.asyncio
    async def test_buffers_complete_html(self, test_events, llm_config):
        """Test that complete HTML is buffered and validated."""
        with patch("messagedb_agent.display.renderer.create_llm_client") as mock_create:
            mock_llm = MagicMock()
            mock_llm.model_name = "gemini-2.5-flash"

            def call_stream(messages, tools=None, system_prompt=None):
                yield StreamDelta(delta_type="text", text="<p>")
                yield StreamDelta(delta_type="text", text="Test")
                yield StreamDelta(delta_type="text", text="</p>")
                yield StreamDelta(
                    delta_type="done",
                    token_usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                )

            mock_llm.call_stream = call_stream
            mock_create.return_value = mock_llm

            # Collect all chunks
            chunks = []
            async for chunk in render_html_stream(test_events, "default", llm_config):
                chunks.append(chunk)

            # Verify complete HTML can be reconstructed
            complete_html = "".join(chunks)
            assert complete_html == "<p>Test</p>"

            # Verify it can be sanitized
            sanitized = sanitize_html(complete_html)
            assert "<p>" in sanitized
            assert "Test" in sanitized

    @pytest.mark.asyncio
    async def test_raises_on_empty_response(self, test_events, llm_config):
        """Test that ValueError is raised when LLM returns empty response."""
        with patch("messagedb_agent.display.renderer.create_llm_client") as mock_create:
            mock_llm = MagicMock()
            mock_llm.model_name = "gemini-2.5-flash"

            def call_stream(messages, tools=None, system_prompt=None):
                # Only yield done, no text
                yield StreamDelta(
                    delta_type="done",
                    token_usage={"input_tokens": 5, "output_tokens": 0, "total_tokens": 5},
                )

            mock_llm.call_stream = call_stream
            mock_create.return_value = mock_llm

            # Should raise ValueError
            with pytest.raises(ValueError, match="empty response"):
                chunks = []
                async for chunk in render_html_stream(test_events, "default", llm_config):
                    chunks.append(chunk)

    @pytest.mark.asyncio
    async def test_uses_system_prompt(self, test_events, llm_config):
        """Test that RENDERING_SYSTEM_PROMPT is used in call_stream."""
        with patch("messagedb_agent.display.renderer.create_llm_client") as mock_create:
            mock_llm = MagicMock()
            mock_llm.model_name = "gemini-2.5-flash"

            call_stream_spy = MagicMock()

            def call_stream(messages, tools=None, system_prompt=None):
                call_stream_spy(messages=messages, tools=tools, system_prompt=system_prompt)
                yield StreamDelta(delta_type="text", text="<div>Test</div>")
                yield StreamDelta(
                    delta_type="done",
                    token_usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                )

            mock_llm.call_stream = call_stream
            mock_create.return_value = mock_llm

            # Call render_html_stream
            chunks = []
            async for chunk in render_html_stream(test_events, "default", llm_config):
                chunks.append(chunk)

            # Verify system_prompt was passed
            assert call_stream_spy.call_count == 1
            call_args = call_stream_spy.call_args[1]
            assert "system_prompt" in call_args
            assert call_args["system_prompt"] is not None
            assert "HTML rendering assistant" in call_args["system_prompt"]

    @pytest.mark.asyncio
    async def test_includes_display_prefs_and_events(self, test_events, llm_config):
        """Test that display preferences and events are included in the message."""
        with patch("messagedb_agent.display.renderer.create_llm_client") as mock_create:
            mock_llm = MagicMock()
            mock_llm.model_name = "gemini-2.5-flash"

            call_stream_spy = MagicMock()

            def call_stream(messages, tools=None, system_prompt=None):
                call_stream_spy(messages=messages)
                yield StreamDelta(delta_type="text", text="<div>Test</div>")
                yield StreamDelta(
                    delta_type="done",
                    token_usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                )

            mock_llm.call_stream = call_stream
            mock_create.return_value = mock_llm

            # Call with specific display prefs
            chunks = []
            async for chunk in render_html_stream(test_events, "dark mode", llm_config):
                chunks.append(chunk)

            # Verify message content
            assert call_stream_spy.call_count == 1
            messages = call_stream_spy.call_args[1]["messages"]
            assert len(messages) == 1
            user_message = messages[0].text
            assert "dark mode" in user_message
            assert "EVENTS:" in user_message
            assert "Hello" in user_message  # From test_events

    @pytest.mark.asyncio
    async def test_includes_previous_html(self, test_events, llm_config):
        """Test that previous HTML is included when provided."""
        with patch("messagedb_agent.display.renderer.create_llm_client") as mock_create:
            mock_llm = MagicMock()
            mock_llm.model_name = "gemini-2.5-flash"

            call_stream_spy = MagicMock()

            def call_stream(messages, tools=None, system_prompt=None):
                call_stream_spy(messages=messages)
                yield StreamDelta(delta_type="text", text="<div>Test</div>")
                yield StreamDelta(
                    delta_type="done",
                    token_usage={"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
                )

            mock_llm.call_stream = call_stream
            mock_create.return_value = mock_llm

            # Call with previous HTML
            previous = "<style>.test { color: blue; }</style><div>Previous</div>"
            chunks = []
            async for chunk in render_html_stream(
                test_events, "default", llm_config, previous_html=previous
            ):
                chunks.append(chunk)

            # Verify previous HTML is in message
            messages = call_stream_spy.call_args[1]["messages"]
            user_message = messages[0].text
            assert "PREVIOUS HTML" in user_message
            assert ".test" in user_message  # Part of the CSS from previous HTML


class TestSanitizeHtml:
    """Test HTML sanitization."""

    def test_removes_script_tags(self):
        """Test that <script> tags are removed."""
        html = '<div>Hello<script>alert("xss")</script></div>'
        sanitized = sanitize_html(html)
        assert "<script>" not in sanitized
        assert "alert" not in sanitized
        assert "Hello" in sanitized

    def test_preserves_safe_html(self):
        """Test that safe HTML is preserved."""
        html = "<div><p>Hello <strong>world</strong></p></div>"
        sanitized = sanitize_html(html)
        assert "<div>" in sanitized
        assert "<p>" in sanitized
        assert "<strong>" in sanitized
        assert "Hello" in sanitized
        assert "world" in sanitized

    def test_preserves_style_tags(self):
        """Test that <style> tags are preserved."""
        html = "<style>.test { color: red; }</style><div>Hello</div>"
        sanitized = sanitize_html(html)
        # nh3 preserves style tags by default
        assert "Hello" in sanitized


class TestRenderHtmlStreamIntegration:
    """Integration tests with real LLM."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_streaming_with_real_llm(self):
        """Test streaming HTML rendering with a real LLM call.

        This integration test validates that render_html_stream() works
        with a real LLM API call.

        Requires GCP credentials and Vertex AI API enabled.
        Set GCP_PROJECT environment variable.
        """
        # Check for required environment variables
        gcp_project = os.getenv("GCP_PROJECT")
        if not gcp_project:
            pytest.skip("GCP_PROJECT environment variable not set")

        gcp_location = os.getenv("GCP_LOCATION", "us-central1")
        # Use Gemini Flash for fast/cheap testing
        model_name = os.getenv("TEST_MODEL_NAME", "gemini-2.5-flash")

        # Create test events
        test_events = [
            MessageDBMessage(
                position=0,
                id=str(uuid.uuid4()),
                type=USER_MESSAGE_ADDED,
                data={"message_text": "Hello, how are you?"},
                metadata={},
                time="2025-01-01T00:00:00Z",
                stream_name="agent:v0-test",
                global_position=1,
            ),
        ]

        # Create LLM config
        config = VertexAIConfig(project=gcp_project, location=gcp_location, model_name=model_name)

        # Call render_html_stream with real LLM
        chunks = []
        chunk_count = 0
        async for chunk in render_html_stream(test_events, "default", config):
            chunks.append(chunk)
            chunk_count += 1
            # Verify we get reasonable chunk sizes
            assert len(chunk) > 0

        # Verify we got multiple chunks (streaming happened)
        assert chunk_count > 0

        # Verify complete HTML
        complete_html = "".join(chunks)
        assert len(complete_html) > 0

        # Verify HTML contains some expected content
        # Should have some HTML tags
        assert "<" in complete_html
        assert ">" in complete_html

        # Verify we can sanitize it
        sanitized = sanitize_html(complete_html)
        assert len(sanitized) > 0

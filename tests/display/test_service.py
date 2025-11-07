"""Integration tests for the FastAPI display service.

These tests verify that the /render-stream endpoint correctly handles
dual streaming (agent LLM + HTML rendering) with proper SSE event ordering.
"""

import json
import os
import uuid
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from messagedb_agent.display.service import create_app
from messagedb_agent.events.system import SESSION_STARTED
from messagedb_agent.events.user import USER_MESSAGE_ADDED


@pytest.fixture
def test_client():
    """Create FastAPI test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_db_config_env(monkeypatch):
    """Mock database configuration environment variables."""
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "message_store")
    monkeypatch.setenv("DB_USER", "postgres")
    monkeypatch.setenv("DB_PASSWORD", "test_password")
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("GCP_LOCATION", "us-central1")
    monkeypatch.setenv("AGENT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("RENDER_MODEL", "gemini-2.5-flash")


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_returns_healthy(self, test_client):
        """Test that /health returns healthy status."""
        response = test_client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestIndexEndpoint:
    """Test index endpoint."""

    def test_index_without_thread_id_redirects(self, test_client):
        """Test that accessing / without thread_id redirects with new UUID."""
        response = test_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert "thread_id=" in response.headers["location"]

    def test_index_with_thread_id_returns_html(self, test_client):
        """Test that accessing / with thread_id returns HTML page."""
        thread_id = str(uuid.uuid4())
        response = test_client.get(f"/?thread_id={thread_id}")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestRenderStreamEndpointMock:
    """Mock tests for /render-stream endpoint (fast feedback)."""

    def test_sse_event_ordering_with_user_message(self, test_client, mock_db_config_env):
        """Test SSE event ordering: agent_start → agent_delta* → agent_complete → html_start → html_chunk* → result."""  # noqa: E501
        thread_id = str(uuid.uuid4())

        # Mock all the dependencies
        with patch("messagedb_agent.display.service.MessageDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch("messagedb_agent.display.service.write_message"):
                with patch("messagedb_agent.display.service.read_stream") as mock_read:
                    # Mock read_stream to return test events
                    mock_read.return_value = [
                        Mock(
                            position=0,
                            id=str(uuid.uuid4()),
                            type=SESSION_STARTED,
                            data={},
                            metadata={},
                            time="2025-01-01T00:00:00Z",
                            stream_name=f"agent:v0-{thread_id}",
                            global_position=1,
                        ),
                        Mock(
                            position=1,
                            id=str(uuid.uuid4()),
                            type=USER_MESSAGE_ADDED,
                            data={"message_text": "Hello"},
                            metadata={},
                            time="2025-01-01T00:00:01Z",
                            stream_name=f"agent:v0-{thread_id}",
                            global_position=2,
                        ),
                    ]

                    # Mock run_agent_step_streaming
                    async def mock_agent_streaming(*args, **kwargs):
                        yield {"type": "llm_text", "text": "Hello"}
                        yield {"type": "llm_text", "text": " "}
                        yield {"type": "llm_text", "text": "world"}
                        yield {
                            "type": "llm_done",
                            "token_usage": {
                                "input_tokens": 10,
                                "output_tokens": 5,
                                "total_tokens": 15,
                            },
                        }

                    with patch(
                        "messagedb_agent.display.service.run_agent_step_streaming",
                        side_effect=mock_agent_streaming,
                    ):
                        # Mock render_html_stream
                        async def mock_html_streaming(*args, **kwargs):
                            yield "<div>"
                            yield "Hello world"
                            yield "</div>"

                        with patch(
                            "messagedb_agent.display.service.render_html_stream",
                            side_effect=mock_html_streaming,
                        ):
                            # Make request
                            response = test_client.post(
                                "/render-stream",
                                json={
                                    "thread_id": thread_id,
                                    "user_message": "Hello",
                                    "previous_html": None,
                                },
                            )

                            assert response.status_code == 200
                            assert (
                                response.headers["content-type"]
                                == "text/event-stream; charset=utf-8"
                            )

                            # Parse SSE events
                            events = self._parse_sse_events(response.text)

                            # Verify event ordering
                            event_types = [e["event"] for e in events]
                            assert event_types == [
                                "agent_start",
                                "agent_delta",
                                "agent_delta",
                                "agent_delta",
                                "agent_delta",
                                "agent_complete",
                                "html_start",
                                "html_chunk",
                                "html_chunk",
                                "html_chunk",
                                "result",
                            ]

                            # Verify agent_delta events
                            agent_deltas = [e for e in events if e["event"] == "agent_delta"]
                            assert len(agent_deltas) == 4
                            assert agent_deltas[0]["data"]["type"] == "llm_text"
                            assert agent_deltas[0]["data"]["text"] == "Hello"

                            # Verify html_chunk events
                            html_chunks = [e for e in events if e["event"] == "html_chunk"]
                            assert len(html_chunks) == 3
                            assert html_chunks[0]["data"]["chunk"] == "<div>"
                            assert html_chunks[1]["data"]["chunk"] == "Hello world"
                            assert html_chunks[2]["data"]["chunk"] == "</div>"

                            # Verify final result
                            result_events = [e for e in events if e["event"] == "result"]
                            assert len(result_events) == 1
                            assert "html" in result_events[0]["data"]
                            assert "display_prefs" in result_events[0]["data"]

    def test_sse_event_ordering_without_user_message(self, test_client, mock_db_config_env):
        """Test SSE event ordering when no user message: html_start → html_chunk* → result."""
        thread_id = str(uuid.uuid4())

        with patch("messagedb_agent.display.service.MessageDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch("messagedb_agent.display.service.read_stream") as mock_read:
                mock_read.return_value = [
                    Mock(
                        position=0,
                        id=str(uuid.uuid4()),
                        type=USER_MESSAGE_ADDED,
                        data={"message_text": "Test"},
                        metadata={},
                        time="2025-01-01T00:00:00Z",
                        stream_name=f"agent:v0-{thread_id}",
                        global_position=1,
                    ),
                ]

                # Mock render_html_stream
                async def mock_html_streaming(*args, **kwargs):
                    yield "<p>"
                    yield "Test"
                    yield "</p>"

                with patch(
                    "messagedb_agent.display.service.render_html_stream",
                    side_effect=mock_html_streaming,
                ):
                    # Make request without user_message
                    response = test_client.post(
                        "/render-stream",
                        json={
                            "thread_id": thread_id,
                            "user_message": None,
                            "previous_html": None,
                        },
                    )

                    assert response.status_code == 200

                    # Parse SSE events
                    events = self._parse_sse_events(response.text)

                    # Verify event ordering (no agent events)
                    event_types = [e["event"] for e in events]
                    assert event_types == [
                        "html_start",
                        "html_chunk",
                        "html_chunk",
                        "html_chunk",
                        "result",
                    ]

    def test_error_event_on_failure(self, test_client, mock_db_config_env):
        """Test that error event is sent when rendering fails."""
        thread_id = str(uuid.uuid4())

        with patch("messagedb_agent.display.service.MessageDBClient") as mock_client_class:
            # Make MessageDBClient raise an exception
            mock_client_class.side_effect = Exception("Database connection failed")

            response = test_client.post(
                "/render-stream",
                json={
                    "thread_id": thread_id,
                    "user_message": "Test",
                    "previous_html": None,
                },
            )

            assert response.status_code == 200

            # Parse SSE events
            events = self._parse_sse_events(response.text)

            # Should have error event
            error_events = [e for e in events if e["event"] == "error"]
            assert len(error_events) == 1
            assert "Database connection failed" in error_events[0]["data"]["error"]

    def test_sse_headers_correct(self, test_client, mock_db_config_env):
        """Test that SSE headers are correctly set."""
        thread_id = str(uuid.uuid4())

        with patch("messagedb_agent.display.service.MessageDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch("messagedb_agent.display.service.read_stream") as mock_read:
                mock_read.return_value = []

                async def mock_html_streaming(*args, **kwargs):
                    yield "<p>Test</p>"

                with patch(
                    "messagedb_agent.display.service.render_html_stream",
                    side_effect=mock_html_streaming,
                ):
                    response = test_client.post(
                        "/render-stream",
                        json={
                            "thread_id": thread_id,
                            "user_message": None,
                            "previous_html": None,
                        },
                    )

                    # Verify SSE headers
                    assert response.headers["content-type"] == "text/event-stream; charset=utf-8"
                    assert response.headers["cache-control"] == "no-cache"
                    assert response.headers["connection"] == "keep-alive"
                    assert response.headers["x-accel-buffering"] == "no"

    def test_markdown_code_block_extraction(self, test_client, mock_db_config_env):
        """Test that HTML wrapped in markdown code blocks is extracted."""
        thread_id = str(uuid.uuid4())

        with patch("messagedb_agent.display.service.MessageDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.__enter__ = Mock(return_value=mock_client)
            mock_client.__exit__ = Mock(return_value=None)
            mock_client_class.return_value = mock_client

            with patch("messagedb_agent.display.service.read_stream") as mock_read:
                mock_read.return_value = []

                # Mock HTML stream with markdown code block
                async def mock_html_streaming(*args, **kwargs):
                    yield "```html\n"
                    yield "<div>Test</div>\n"
                    yield "```"

                with patch(
                    "messagedb_agent.display.service.render_html_stream",
                    side_effect=mock_html_streaming,
                ):
                    response = test_client.post(
                        "/render-stream",
                        json={
                            "thread_id": thread_id,
                            "user_message": None,
                            "previous_html": None,
                        },
                    )

                    # Parse result event
                    events = self._parse_sse_events(response.text)
                    result_events = [e for e in events if e["event"] == "result"]
                    assert len(result_events) == 1

                    # Verify markdown was stripped
                    final_html = result_events[0]["data"]["html"]
                    assert "```" not in final_html
                    assert "<div>" in final_html
                    assert "Test" in final_html

    @staticmethod
    def _parse_sse_events(sse_text: str) -> list[dict[str, Any]]:
        """Parse SSE event stream into structured events.

        Args:
            sse_text: Raw SSE response text

        Returns:
            List of events with 'event' and 'data' keys
        """
        events = []
        lines = sse_text.strip().split("\n")

        current_event = None
        current_data = None

        for line in lines:
            if line.startswith("event: "):
                current_event = line[7:].strip()
            elif line.startswith("data: "):
                current_data = line[6:].strip()
            elif line == "" and current_event and current_data:
                # End of event
                try:
                    data_obj = json.loads(current_data)
                except json.JSONDecodeError:
                    data_obj = current_data
                events.append({"event": current_event, "data": data_obj})
                current_event = None
                current_data = None

        # Handle last event if stream doesn't end with blank line
        if current_event and current_data:
            try:
                data_obj = json.loads(current_data)
            except json.JSONDecodeError:
                data_obj = current_data
            events.append({"event": current_event, "data": data_obj})

        return events


class TestRenderStreamEndpointIntegration:
    """Integration tests for /render-stream endpoint with real components.

    These tests use real Message DB but mock LLM calls.
    """

    @pytest.mark.integration
    def test_end_to_end_with_messagedb(
        self, test_client, messagedb_config, mock_db_config_env, monkeypatch
    ):
        """Test complete flow with real Message DB and mocked LLM.

        This test verifies:
        - Events are written to real Message DB
        - Events are read back correctly
        - SSE event ordering is correct
        - Final HTML is sanitized
        """
        # Set env vars to use test MessageDB
        monkeypatch.setenv("DB_HOST", messagedb_config.host)
        monkeypatch.setenv("DB_PORT", str(messagedb_config.port))
        monkeypatch.setenv("DB_NAME", messagedb_config.database)
        monkeypatch.setenv("DB_USER", messagedb_config.user)
        monkeypatch.setenv("DB_PASSWORD", messagedb_config.password)

        thread_id = str(uuid.uuid4())

        # Mock run_agent_step_streaming to avoid real LLM calls
        async def mock_agent_streaming(*args, **kwargs):
            yield {"type": "llm_text", "text": "Test"}
            yield {"type": "llm_text", "text": " response"}
            yield {
                "type": "llm_done",
                "token_usage": {
                    "input_tokens": 5,
                    "output_tokens": 2,
                    "total_tokens": 7,
                },
            }

        with patch(
            "messagedb_agent.display.service.run_agent_step_streaming",
            side_effect=mock_agent_streaming,
        ):
            # Mock render_html_stream to avoid real LLM calls
            async def mock_html_streaming(*args, **kwargs):
                yield "<div>Test response</div>"

            with patch(
                "messagedb_agent.display.service.render_html_stream",
                side_effect=mock_html_streaming,
            ):
                # Make request
                response = test_client.post(
                    "/render-stream",
                    json={
                        "thread_id": thread_id,
                        "user_message": "Hello world",
                        "previous_html": None,
                    },
                )

                assert response.status_code == 200

                # Parse SSE events
                events = TestRenderStreamEndpointMock._parse_sse_events(response.text)

                # Verify event ordering
                event_types = [e["event"] for e in events]
                assert "agent_start" in event_types
                assert "agent_complete" in event_types
                assert "html_start" in event_types
                assert "result" in event_types

                # Verify final result
                result_events = [e for e in events if e["event"] == "result"]
                assert len(result_events) == 1
                assert "html" in result_events[0]["data"]
                assert "Test response" in result_events[0]["data"]["html"]


class TestRenderStreamEndpointRealLLM:
    """Integration tests with real LLM calls.

    These tests require GCP credentials and are marked with @pytest.mark.integration.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_dual_streaming_with_gemini(self, test_client, messagedb_config, monkeypatch):
        """Test complete dual streaming flow with real Gemini LLM.

        This test verifies the entire streaming pipeline:
        1. Agent LLM streaming (Gemini)
        2. HTML rendering streaming (Gemini)
        3. Correct SSE event ordering
        4. Events written to Message DB
        5. Final HTML sanitized

        Requires:
        - GCP_PROJECT environment variable
        - Vertex AI API enabled
        - Application Default Credentials configured
        """
        # Check for required environment variables
        gcp_project = os.getenv("GCP_PROJECT")
        if not gcp_project:
            pytest.skip("GCP_PROJECT environment variable not set")

        gcp_location = os.getenv("GCP_LOCATION", "us-central1")

        # Set up environment
        monkeypatch.setenv("DB_HOST", messagedb_config.host)
        monkeypatch.setenv("DB_PORT", str(messagedb_config.port))
        monkeypatch.setenv("DB_NAME", messagedb_config.database)
        monkeypatch.setenv("DB_USER", messagedb_config.user)
        monkeypatch.setenv("DB_PASSWORD", messagedb_config.password)
        monkeypatch.setenv("GCP_PROJECT", gcp_project)
        monkeypatch.setenv("GCP_LOCATION", gcp_location)
        monkeypatch.setenv("AGENT_MODEL", "gemini-2.5-flash")
        monkeypatch.setenv("RENDER_MODEL", "gemini-2.5-flash")

        thread_id = str(uuid.uuid4())

        # Make request with real LLM calls
        response = test_client.post(
            "/render-stream",
            json={
                "thread_id": thread_id,
                "user_message": "Say hello in exactly 3 words",
                "previous_html": None,
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

        # Parse SSE events
        events = TestRenderStreamEndpointMock._parse_sse_events(response.text)

        # Verify we got events
        assert len(events) > 0

        # Verify event ordering
        event_types = [e["event"] for e in events]
        assert event_types[0] == "agent_start"
        assert "agent_delta" in event_types
        assert "agent_complete" in event_types
        assert "html_start" in event_types
        assert "html_chunk" in event_types
        assert event_types[-1] == "result"

        # Verify agent_start comes before agent_complete
        agent_start_idx = event_types.index("agent_start")
        agent_complete_idx = event_types.index("agent_complete")
        assert agent_start_idx < agent_complete_idx

        # Verify html_start comes after agent_complete
        html_start_idx = event_types.index("html_start")
        assert html_start_idx > agent_complete_idx

        # Verify we got agent deltas (streaming happened)
        agent_deltas = [e for e in events if e["event"] == "agent_delta"]
        assert len(agent_deltas) > 0

        # Verify we got HTML chunks (streaming happened)
        html_chunks = [e for e in events if e["event"] == "html_chunk"]
        assert len(html_chunks) > 0

        # Verify final result
        result_events = [e for e in events if e["event"] == "result"]
        assert len(result_events) == 1
        assert "html" in result_events[0]["data"]
        assert "display_prefs" in result_events[0]["data"]

        # Verify final HTML is not empty
        final_html = result_events[0]["data"]["html"]
        assert len(final_html) > 0
        assert "<" in final_html  # Has HTML tags

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_dual_streaming_with_claude(self, test_client, messagedb_config, monkeypatch):
        """Test complete dual streaming flow with real Claude LLM.

        Same as test_dual_streaming_with_gemini but uses Claude model.
        """
        gcp_project = os.getenv("GCP_PROJECT")
        if not gcp_project:
            pytest.skip("GCP_PROJECT environment variable not set")

        gcp_location = os.getenv("GCP_LOCATION", "us-central1")

        # Set up environment with Claude models
        monkeypatch.setenv("DB_HOST", messagedb_config.host)
        monkeypatch.setenv("DB_PORT", str(messagedb_config.port))
        monkeypatch.setenv("DB_NAME", messagedb_config.database)
        monkeypatch.setenv("DB_USER", messagedb_config.user)
        monkeypatch.setenv("DB_PASSWORD", messagedb_config.password)
        monkeypatch.setenv("GCP_PROJECT", gcp_project)
        monkeypatch.setenv("GCP_LOCATION", gcp_location)
        monkeypatch.setenv("AGENT_MODEL", "claude-sonnet-4-5@20250929")
        monkeypatch.setenv("RENDER_MODEL", "claude-sonnet-4-5@20250929")

        thread_id = str(uuid.uuid4())

        response = test_client.post(
            "/render-stream",
            json={
                "thread_id": thread_id,
                "user_message": "Say hello in exactly 3 words",
                "previous_html": None,
            },
        )

        assert response.status_code == 200

        # Parse SSE events
        events = TestRenderStreamEndpointMock._parse_sse_events(response.text)

        # Verify event ordering (same checks as Gemini test)
        event_types = [e["event"] for e in events]
        assert event_types[0] == "agent_start"
        assert event_types[-1] == "result"

        # Verify streaming happened
        agent_deltas = [e for e in events if e["event"] == "agent_delta"]
        assert len(agent_deltas) > 0

        html_chunks = [e for e in events if e["event"] == "html_chunk"]
        assert len(html_chunks) > 0

        # Verify final result
        result_events = [e for e in events if e["event"] == "result"]
        assert len(result_events) == 1
        final_html = result_events[0]["data"]["html"]
        assert len(final_html) > 0

    @pytest.mark.integration
    def test_error_handling_with_messagedb(self, test_client, messagedb_config, monkeypatch):
        """Test error handling when agent processing fails.

        This test verifies that errors during agent processing
        result in proper error events being sent via SSE.
        """
        monkeypatch.setenv("DB_HOST", messagedb_config.host)
        monkeypatch.setenv("DB_PORT", str(messagedb_config.port))
        monkeypatch.setenv("DB_NAME", messagedb_config.database)
        monkeypatch.setenv("DB_USER", messagedb_config.user)
        monkeypatch.setenv("DB_PASSWORD", messagedb_config.password)
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        thread_id = str(uuid.uuid4())

        # Mock run_agent_step_streaming to raise an error
        async def mock_agent_error(*args, **kwargs):
            raise ValueError("Test error in agent processing")
            yield  # Make it a generator

        with patch(
            "messagedb_agent.display.service.run_agent_step_streaming",
            side_effect=mock_agent_error,
        ):
            response = test_client.post(
                "/render-stream",
                json={
                    "thread_id": thread_id,
                    "user_message": "Test",
                    "previous_html": None,
                },
            )

            assert response.status_code == 200

            # Parse SSE events
            events = TestRenderStreamEndpointMock._parse_sse_events(response.text)

            # Should have error event
            error_events = [e for e in events if e["event"] == "error"]
            assert len(error_events) == 1
            assert "Test error in agent processing" in error_events[0]["data"]["error"]

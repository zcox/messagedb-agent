"""Unit tests for streaming agent runner.

These tests verify that run_agent_step_streaming() correctly yields deltas
and buffers complete responses for MessageDB storage.
"""

import uuid
from unittest.mock import MagicMock, Mock, patch

import pytest

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.display.agent_runner import run_agent_step_streaming
from messagedb_agent.events.agent import LLM_RESPONSE_RECEIVED
from messagedb_agent.events.system import SESSION_STARTED
from messagedb_agent.events.tool import TOOL_EXECUTION_COMPLETED
from messagedb_agent.events.user import USER_MESSAGE_ADDED
from messagedb_agent.llm.base import StreamDelta
from messagedb_agent.store import MessageDBClient


@pytest.fixture
def mock_store_client():
    """Create a mock MessageDB client."""
    client = MagicMock(spec=MessageDBClient)
    conn = MagicMock()
    conn.autocommit = False
    client.get_connection.return_value = conn
    return client


@pytest.fixture
def llm_config():
    """Create test LLM config."""
    return VertexAIConfig(
        project="test-project", location="us-central1", model_name="gemini-2.5-flash"
    )


class TestStreamingTextDeltas:
    """Test streaming of LLM text deltas."""

    @pytest.mark.asyncio
    async def test_yields_text_deltas(self, mock_store_client, llm_config):
        """Test that text deltas are yielded in real-time."""
        # Mock read_stream to return initial events
        with patch("messagedb_agent.display.agent_runner.read_stream") as mock_read:
            # First call: return session start and user message
            # Second call: return empty (to trigger termination)
            mock_read.side_effect = [
                [
                    Mock(
                        position=0,
                        id=str(uuid.uuid4()),
                        type=SESSION_STARTED,
                        data={},
                        metadata={},
                        time="2025-01-01T00:00:00Z",
                        stream_name="agent:v0-test",
                        global_position=1,
                    ),
                    Mock(
                        position=1,
                        id=str(uuid.uuid4()),
                        type=USER_MESSAGE_ADDED,
                        data={"message_text": "Hello"},
                        metadata={},
                        time="2025-01-01T00:00:01Z",
                        stream_name="agent:v0-test",
                        global_position=2,
                    ),
                ],
                [
                    Mock(
                        position=2,
                        id=str(uuid.uuid4()),
                        type=LLM_RESPONSE_RECEIVED,
                        data={
                            "response_text": "Hello world",
                            "tool_calls": [],
                            "model_name": "gemini-2.5-flash",
                            "token_usage": {},
                        },
                        metadata={},
                        time="2025-01-01T00:00:02Z",
                        stream_name="agent:v0-test",
                        global_position=3,
                    ),
                ],
            ]

            # Mock LLM client to return streaming deltas
            with patch("messagedb_agent.display.agent_runner.create_llm_client") as mock_create:
                mock_llm = MagicMock()
                mock_llm.model_name = "gemini-2.5-flash"

                # Return streaming deltas
                def call_stream(messages, tools=None, system_prompt=None):
                    yield StreamDelta(delta_type="text", text="Hello")
                    yield StreamDelta(delta_type="text", text=" ")
                    yield StreamDelta(delta_type="text", text="world")
                    yield StreamDelta(
                        delta_type="done",
                        token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    )

                mock_llm.call_stream = call_stream
                mock_create.return_value = mock_llm

                # Mock write_message
                with patch("messagedb_agent.display.agent_runner.write_message"):
                    # Collect deltas
                    deltas = []
                    async for delta in run_agent_step_streaming(
                        "test-thread", mock_store_client, llm_config
                    ):
                        deltas.append(delta)

                    # Verify text deltas were yielded
                    text_deltas = [d for d in deltas if d["type"] == "llm_text"]
                    assert len(text_deltas) == 3
                    assert text_deltas[0]["text"] == "Hello"
                    assert text_deltas[1]["text"] == " "
                    assert text_deltas[2]["text"] == "world"

                    # Verify done delta was yielded
                    done_deltas = [d for d in deltas if d["type"] == "llm_done"]
                    assert len(done_deltas) == 1
                    assert done_deltas[0]["token_usage"]["total_tokens"] == 15


class TestStreamingToolCalls:
    """Test streaming of tool call deltas."""

    @pytest.mark.asyncio
    async def test_yields_tool_call_deltas(self, mock_store_client, llm_config):
        """Test that tool call deltas are yielded correctly."""
        with patch("messagedb_agent.display.agent_runner.read_stream") as mock_read:
            # Return initial events and then LLM response with tool calls
            mock_read.side_effect = [
                [
                    Mock(
                        position=0,
                        id=str(uuid.uuid4()),
                        type=SESSION_STARTED,
                        data={},
                        metadata={},
                        time="2025-01-01T00:00:00Z",
                        stream_name="agent:v0-test",
                        global_position=1,
                    ),
                    Mock(
                        position=1,
                        id=str(uuid.uuid4()),
                        type=USER_MESSAGE_ADDED,
                        data={"message_text": "Get weather"},
                        metadata={},
                        time="2025-01-01T00:00:01Z",
                        stream_name="agent:v0-test",
                        global_position=2,
                    ),
                ],
                [
                    Mock(
                        position=2,
                        id=str(uuid.uuid4()),
                        type=LLM_RESPONSE_RECEIVED,
                        data={
                            "response_text": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "name": "get_weather",
                                    "arguments": {"city": "NYC"},
                                }
                            ],
                            "model_name": "gemini-2.5-flash",
                            "token_usage": {},
                        },
                        metadata={},
                        time="2025-01-01T00:00:02Z",
                        stream_name="agent:v0-test",
                        global_position=3,
                    ),
                ],
                [
                    Mock(
                        position=3,
                        id=str(uuid.uuid4()),
                        type=TOOL_EXECUTION_COMPLETED,
                        data={
                            "tool_name": "get_weather",
                            "result": {"temperature": 72},
                            "execution_time_ms": 100,
                        },
                        metadata={"tool_id": "call_1", "tool_call_id": "call_1", "tool_index": 0},
                        time="2025-01-01T00:00:03Z",
                        stream_name="agent:v0-test",
                        global_position=4,
                    ),
                ],
                [
                    Mock(
                        position=4,
                        id=str(uuid.uuid4()),
                        type=LLM_RESPONSE_RECEIVED,
                        data={
                            "response_text": "The weather is 72°F",
                            "tool_calls": [],
                            "model_name": "gemini-2.5-flash",
                            "token_usage": {},
                        },
                        metadata={},
                        time="2025-01-01T00:00:04Z",
                        stream_name="agent:v0-test",
                        global_position=5,
                    ),
                ],
                [],  # Empty list to stop the loop
            ]

            # Mock LLM client to return tool call deltas
            with patch("messagedb_agent.display.agent_runner.create_llm_client") as mock_create:
                mock_llm = MagicMock()
                mock_llm.model_name = "gemini-2.5-flash"

                def call_stream(messages, tools=None, system_prompt=None):
                    yield StreamDelta(
                        delta_type="tool_call",
                        tool_call_index=0,
                        tool_call_id="call_1",
                        tool_name="get_weather",
                    )
                    yield StreamDelta(
                        delta_type="tool_input",
                        tool_call_index=0,
                        tool_input_delta='{"city": "NYC"}',
                    )
                    yield StreamDelta(
                        delta_type="done",
                        token_usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                    )

                mock_llm.call_stream = call_stream
                mock_create.return_value = mock_llm

                # Mock write_message
                with patch("messagedb_agent.display.agent_runner.write_message"):
                    # Mock execute_tool
                    with patch("messagedb_agent.display.agent_runner.execute_tool") as mock_exec:
                        mock_result = MagicMock()
                        mock_result.success = True
                        mock_result.result = {"temperature": 72}
                        mock_result.execution_time_ms = 100
                        mock_exec.return_value = mock_result

                        # Collect deltas
                        deltas = []
                        async for delta in run_agent_step_streaming(
                            "test-thread", mock_store_client, llm_config
                        ):
                            deltas.append(delta)

                        # Verify tool call deltas (may have multiple if LLM is called again)
                        tool_call_deltas = [d for d in deltas if d["type"] == "llm_tool_call"]
                        assert len(tool_call_deltas) >= 1
                        assert tool_call_deltas[0]["name"] == "get_weather"
                        assert tool_call_deltas[0]["id"] == "call_1"
                        assert tool_call_deltas[0]["index"] == 0

                        # Verify tool input deltas
                        tool_input_deltas = [d for d in deltas if d["type"] == "llm_tool_input"]
                        assert len(tool_input_deltas) >= 1
                        assert tool_input_deltas[0]["index"] == 0
                        assert '{"city": "NYC"}' in tool_input_deltas[0]["input"]

                        # Verify tool execution deltas
                        tool_started = [d for d in deltas if d["type"] == "tool_started"]
                        assert len(tool_started) == 1
                        assert tool_started[0]["name"] == "get_weather"

                        tool_completed = [d for d in deltas if d["type"] == "tool_completed"]
                        assert len(tool_completed) == 1
                        assert tool_completed[0]["result"]["temperature"] == 72


class TestEventBuffering:
    """Test that complete responses are buffered for MessageDB."""

    @pytest.mark.asyncio
    async def test_buffers_complete_response(self, mock_store_client, llm_config):
        """Test that complete LLM response is written to MessageDB."""
        with patch("messagedb_agent.display.agent_runner.read_stream") as mock_read:
            mock_read.side_effect = [
                [
                    Mock(
                        position=0,
                        id=str(uuid.uuid4()),
                        type=SESSION_STARTED,
                        data={},
                        metadata={},
                        time="2025-01-01T00:00:00Z",
                        stream_name="agent:v0-test",
                        global_position=1,
                    ),
                    Mock(
                        position=1,
                        id=str(uuid.uuid4()),
                        type=USER_MESSAGE_ADDED,
                        data={"message_text": "Test"},
                        metadata={},
                        time="2025-01-01T00:00:01Z",
                        stream_name="agent:v0-test",
                        global_position=2,
                    ),
                ],
                [
                    Mock(
                        position=2,
                        id=str(uuid.uuid4()),
                        type=LLM_RESPONSE_RECEIVED,
                        data={
                            "response_text": "Complete response",
                            "tool_calls": [],
                            "model_name": "gemini-2.5-flash",
                            "token_usage": {},
                        },
                        metadata={},
                        time="2025-01-01T00:00:02Z",
                        stream_name="agent:v0-test",
                        global_position=3,
                    ),
                ],
            ]

            with patch("messagedb_agent.display.agent_runner.create_llm_client") as mock_create:
                mock_llm = MagicMock()
                mock_llm.model_name = "gemini-2.5-flash"

                def call_stream(messages, tools=None, system_prompt=None):
                    yield StreamDelta(delta_type="text", text="Complete")
                    yield StreamDelta(delta_type="text", text=" ")
                    yield StreamDelta(delta_type="text", text="response")
                    yield StreamDelta(
                        delta_type="done",
                        token_usage={
                            "input_tokens": 5,
                            "output_tokens": 3,
                            "total_tokens": 8,
                        },
                    )

                mock_llm.call_stream = call_stream
                mock_create.return_value = mock_llm

                with patch("messagedb_agent.display.agent_runner.write_message") as mock_write:
                    # Run streaming
                    deltas = []
                    async for delta in run_agent_step_streaming(
                        "test-thread", mock_store_client, llm_config
                    ):
                        deltas.append(delta)

                    # Verify write_message was called with complete buffered response
                    llm_response_writes = [
                        call
                        for call in mock_write.call_args_list
                        if call[1]["message_type"] == LLM_RESPONSE_RECEIVED
                    ]
                    assert len(llm_response_writes) == 1

                    # Check buffered text is complete
                    written_data = llm_response_writes[0][1]["data"]
                    assert written_data["response_text"] == "Complete response"

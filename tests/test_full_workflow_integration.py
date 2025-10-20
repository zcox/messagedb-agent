"""
Full workflow integration test using start_session and process_thread.

This test validates the complete agent workflow:
1. start_session() - Initialize a new session
2. process_thread() - Run the complete processing loop
3. Verify events, LLM calls, tool execution, and termination
"""

import os

import pytest

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.engine import process_thread, start_session
from messagedb_agent.llm import create_llm_client
from messagedb_agent.projections.session_state import SessionStatus
from messagedb_agent.store import MessageDBClient, build_stream_name, read_stream
from messagedb_agent.tools import ToolRegistry, register_tool


@pytest.mark.integration
def test_full_workflow_without_tools(messagedb_client: MessageDBClient) -> None:
    """
    Test complete workflow: start_session → process_thread → verify completion.

    This is a simple workflow without tool calls - just user message and LLM response.

    Requires GCP credentials and Vertex AI API enabled.
    Set GCP_PROJECT environment variable.
    """
    # Check for required environment variables
    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        pytest.skip("GCP_PROJECT environment variable not set")

    gcp_location = os.getenv("GCP_LOCATION", "us-central1")
    # Use Gemini for faster/cheaper testing
    model_name = os.getenv("TEST_MODEL_NAME", "gemini-2.5-flash")

    # Setup
    config = VertexAIConfig(project=gcp_project, location=gcp_location, model_name=model_name)
    llm_client = create_llm_client(config)
    tool_registry = ToolRegistry()  # Empty registry - no tools

    # Step 1: Start session
    with messagedb_client:
        thread_id = start_session(
            initial_message="What is 2 + 2? Please answer with just the number.",
            store_client=messagedb_client,
        )

    assert thread_id is not None
    assert len(thread_id) > 0

    stream_name = build_stream_name("agent", "v0", thread_id)

    # Verify initial events were written
    with messagedb_client:
        events = read_stream(client=messagedb_client, stream_name=stream_name)

    assert len(events) == 2
    assert events[0].type == "SessionStarted"
    assert events[1].type == "UserMessageAdded"

    # Step 2: Process thread (this should call LLM and get response)
    # Since we have no tools and just one user message, the LLM should respond
    # The processing loop will:
    # - Read events
    # - Determine next step is LLM_CALL
    # - Call LLM
    # - Write LLMResponseReceived
    # - Loop again
    # - LLM response with no tools triggers TERMINATION (natural completion)

    # The loop should terminate naturally when LLM provides a text response
    with messagedb_client:
        final_state = process_thread(
            thread_id=thread_id,
            stream_name=stream_name,
            store_client=messagedb_client,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_iterations=10,  # Allow enough iterations
        )

    # Should have terminated naturally after LLM response
    # Verify we got a session state back
    with messagedb_client:
        final_events = read_stream(client=messagedb_client, stream_name=stream_name)

    # Should have: SessionStarted, UserMessageAdded, LLMResponseReceived (at least)
    assert len(final_events) >= 3

    # Find LLM response
    llm_responses = [e for e in final_events if e.type == "LLMResponseReceived"]
    assert len(llm_responses) >= 1

    # Verify response contains answer
    first_response = llm_responses[0]
    assert "4" in first_response.data["response_text"]

    # Verify session state from process_thread return value
    assert final_state.thread_id == thread_id
    assert final_state.message_count == 1  # One user message
    assert final_state.llm_call_count >= 1  # At least one LLM call


def _message_to_event(message):
    """Helper to convert Message to BaseEvent for projection."""
    from uuid import UUID

    from messagedb_agent.events.base import BaseEvent

    event_id = message.id if isinstance(message.id, UUID) else UUID(message.id)
    return BaseEvent(
        id=event_id,
        type=message.type,
        data=message.data,
        metadata=message.metadata or {},
        position=message.position,
        global_position=message.global_position,
        time=message.time,
        stream_name=message.stream_name,
    )


@pytest.mark.integration
def test_full_workflow_with_tools(messagedb_client: MessageDBClient) -> None:
    """
    Test complete workflow with tool execution.

    This validates:
    - start_session
    - process_thread with tools available
    - LLM calls a tool
    - Tool execution writes events
    - LLM gets tool result and responds
    - Session completes naturally
    """
    # Check for required environment variables
    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        pytest.skip("GCP_PROJECT environment variable not set")

    gcp_location = os.getenv("GCP_LOCATION", "us-central1")
    model_name = os.getenv("TEST_MODEL_NAME", "gemini-2.5-flash")

    # Setup with tools
    config = VertexAIConfig(project=gcp_project, location=gcp_location, model_name=model_name)
    llm_client = create_llm_client(config)
    tool_registry = ToolRegistry()

    # Register a simple calculator tool
    @register_tool(registry=tool_registry, description="Add two numbers together")
    def add_numbers(a: int, b: int) -> int:
        """Add two numbers and return the sum."""
        return a + b

    # Start session with a math question
    with messagedb_client:
        thread_id = start_session(
            initial_message="What is 15 + 27? Use the add_numbers tool to calculate this.",
            store_client=messagedb_client,
        )

    stream_name = build_stream_name("agent", "v0", thread_id)

    # Process thread - LLM should use the tool
    # Expected flow:
    # 1. LLM_CALL → LLM responds with tool call
    # 2. TOOL_EXECUTION → Execute add_numbers(15, 27) = 42
    # 3. LLM_CALL → LLM gets tool result and responds with answer
    # 4. TERMINATION (LLM response without tool calls terminates naturally)

    with messagedb_client:
        final_state = process_thread(
            thread_id=thread_id,
            stream_name=stream_name,
            store_client=messagedb_client,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_iterations=10,  # Allow enough iterations
        )

    # Verify events
    with messagedb_client:
        final_events = read_stream(client=messagedb_client, stream_name=stream_name)

    # Should have: SessionStarted, UserMessageAdded, LLMResponseReceived (with tool call),
    # ToolExecutionRequested, ToolExecutionCompleted, LLMResponseReceived (final answer)
    assert len(final_events) >= 6

    # Check for tool execution events
    tool_requested = [e for e in final_events if e.type == "ToolExecutionRequested"]
    tool_completed = [e for e in final_events if e.type == "ToolExecutionCompleted"]

    assert len(tool_requested) >= 1
    assert len(tool_completed) >= 1

    # Verify tool was called correctly
    assert tool_requested[0].data["tool_name"] == "add_numbers"
    assert tool_requested[0].data["arguments"] == {"a": 15, "b": 27}

    # Verify tool result
    assert tool_completed[0].data["result"] == 42

    # Verify final LLM response mentions the answer
    llm_responses = [e for e in final_events if e.type == "LLMResponseReceived"]
    assert len(llm_responses) >= 2  # One with tool call, one with final answer

    # Final response should mention 42 or the calculation
    # (LLM might say "I calculated it" without repeating the number)
    final_response_text = llm_responses[-1].data["response_text"]
    # At minimum, verify we got a text response after tool execution
    assert len(final_response_text) > 0

    # Verify session state from process_thread return value
    assert final_state.thread_id == thread_id
    assert final_state.message_count == 1
    assert final_state.llm_call_count >= 2
    assert final_state.tool_call_count >= 1


@pytest.mark.integration
def test_full_workflow_with_termination(messagedb_client: MessageDBClient) -> None:
    """
    Test complete workflow with explicit termination.

    This validates:
    - start_session
    - process_thread
    - Manual SessionCompleted event causes natural termination
    """
    # Check for required environment variables
    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        pytest.skip("GCP_PROJECT environment variable not set")

    gcp_location = os.getenv("GCP_LOCATION", "us-central1")
    model_name = os.getenv("TEST_MODEL_NAME", "gemini-2.5-flash")

    # Setup
    config = VertexAIConfig(project=gcp_project, location=gcp_location, model_name=model_name)
    llm_client = create_llm_client(config)
    tool_registry = ToolRegistry()

    # Start session
    with messagedb_client:
        thread_id = start_session(
            initial_message="Say hello!",
            store_client=messagedb_client,
        )

    stream_name = build_stream_name("agent", "v0", thread_id)

    # Process one iteration to get LLM response
    # This will hit max_iterations since there's no termination event yet
    from messagedb_agent.engine.loop import MaxIterationsExceeded

    with messagedb_client:
        with pytest.raises(MaxIterationsExceeded):
            process_thread(
                thread_id=thread_id,
                stream_name=stream_name,
                store_client=messagedb_client,
                llm_client=llm_client,
                tool_registry=tool_registry,
                max_iterations=1,
            )

    # Now manually terminate the session with "success" reason
    # (which makes status = COMPLETED instead of FAILED)
    from messagedb_agent.engine import terminate_session

    with messagedb_client:
        position = terminate_session(
            thread_id=thread_id,
            reason="success",
            store_client=messagedb_client,
        )

    assert position >= 0

    # Process again - should terminate immediately
    with messagedb_client:
        final_state_2 = process_thread(
            thread_id=thread_id,
            stream_name=stream_name,
            store_client=messagedb_client,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_iterations=10,
        )

    # Should be completed
    assert final_state_2.status == SessionStatus.COMPLETED

    # Verify events include SessionCompleted
    with messagedb_client:
        final_events = read_stream(client=messagedb_client, stream_name=stream_name)

    session_completed = [e for e in final_events if e.type == "SessionCompleted"]
    assert len(session_completed) == 1
    assert session_completed[0].data["completion_reason"] == "success"

"""
End-to-end integration test.

This test validates multiple components working together:
1. Write events to Message DB
2. Read events from Message DB
3. Project events to LLM context
4. Call LLM with projected context
"""

import os
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from messagedb_agent.events.agent import LLMResponseReceivedData
from messagedb_agent.events.system import SessionStartedData
from messagedb_agent.events.user import UserMessageData
from messagedb_agent.llm import create_llm_client
from messagedb_agent.llm.prompts import MINIMAL_SYSTEM_PROMPT
from messagedb_agent.projections.llm_context import project_to_llm_context
from messagedb_agent.store import (
    MessageDBClient,
    build_stream_name,
    generate_thread_id,
    read_stream,
    write_message,
)


@pytest.mark.integration
def test_e2e_write_read_project_llm(messagedb_client: MessageDBClient) -> None:
    """
    Test end-to-end flow: write events → read events → project → call LLM.

    This integration test validates that all major components work together:
    - Event store operations (write/read)
    - Event type definitions
    - Projection to LLM context
    - LLM client integration

    Requires GCP credentials and Vertex AI API enabled.
    Set GCP_PROJECT environment variable.
    """
    # Check for required environment variables
    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        pytest.skip("GCP_PROJECT environment variable not set")

    gcp_location = os.getenv("GCP_LOCATION", "us-central1")
    # Default to Gemini for faster/cheaper testing, but Claude works too
    # Use gemini-1.5-flash for better availability across regions
    model_name = os.getenv("TEST_MODEL_NAME", "gemini-1.5-flash")

    # Step 1: Write events to Message DB
    thread_id = generate_thread_id()
    stream_name = build_stream_name("agent", "v0", thread_id)

    with messagedb_client:
        # Write SessionStarted event
        session_data = SessionStartedData(thread_id=thread_id)
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="SessionStarted",
            data=asdict(session_data),
        )

        # Write UserMessageAdded event
        user_message = UserMessageData(
            message="What is 2 + 2? Please answer with just the number.",
            timestamp=datetime.now(UTC).isoformat(),
        )
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="UserMessageAdded",
            data=asdict(user_message),
        )

        # Step 2: Read events from Message DB
        events = read_stream(client=messagedb_client, stream_name=stream_name)

    # Verify we got the events we wrote
    assert len(events) == 2
    assert events[0].type == "SessionStarted"
    assert events[1].type == "UserMessageAdded"

    # Step 3: Project events to LLM context
    messages = project_to_llm_context(events)

    # Verify projection created a user message
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert "2 + 2" in messages[0].text

    # Step 4: Call LLM with projected context
    from messagedb_agent.config import VertexAIConfig

    config = VertexAIConfig(project=gcp_project, location=gcp_location, model_name=model_name)
    llm_client = create_llm_client(config)

    response = llm_client.call(messages, system_prompt=MINIMAL_SYSTEM_PROMPT)

    # Verify we got a response
    assert response.text is not None
    assert len(response.text) > 0
    assert response.model_name == model_name
    assert response.token_usage is not None

    # The answer should contain "4" somewhere
    assert "4" in response.text

    # Step 5: Write LLM response back to event stream
    with messagedb_client:
        llm_response_data = LLMResponseReceivedData(
            response_text=response.text,
            tool_calls=[],
            model_name=response.model_name,
            token_usage=response.token_usage,
        )
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="LLMResponseReceived",
            data=asdict(llm_response_data),
        )

        # Step 6: Read events again and verify the complete flow
        all_events = read_stream(client=messagedb_client, stream_name=stream_name)

    assert len(all_events) == 3
    assert all_events[0].type == "SessionStarted"
    assert all_events[1].type == "UserMessageAdded"
    assert all_events[2].type == "LLMResponseReceived"

    # Step 7: Project again to verify LLM response is included in context
    final_messages = project_to_llm_context(all_events)

    assert len(final_messages) == 2
    assert final_messages[0].role == "user"
    assert final_messages[1].role == "assistant"
    assert "4" in final_messages[1].text


@pytest.mark.integration
def test_e2e_multi_turn_conversation(messagedb_client: MessageDBClient) -> None:
    """
    Test end-to-end multi-turn conversation flow.

    This validates:
    - Multiple user messages
    - Multiple LLM responses
    - Projection maintains conversation history
    - LLM can reference previous context
    """
    # Check for required environment variables
    gcp_project = os.getenv("GCP_PROJECT")
    if not gcp_project:
        pytest.skip("GCP_PROJECT environment variable not set")

    gcp_location = os.getenv("GCP_LOCATION", "us-central1")
    model_name = os.getenv("TEST_MODEL_NAME", "gemini-1.5-flash")

    # Initialize
    thread_id = generate_thread_id()
    stream_name = build_stream_name("agent", "v0", thread_id)

    from messagedb_agent.config import VertexAIConfig

    config = VertexAIConfig(project=gcp_project, location=gcp_location, model_name=model_name)
    llm_client = create_llm_client(config)

    # Turn 1: User asks first question
    with messagedb_client:
        session_data = SessionStartedData(thread_id=thread_id)
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="SessionStarted",
            data=asdict(session_data),
        )

        user_message_1 = UserMessageData(
            message="My favorite color is blue.",
            timestamp=datetime.now(UTC).isoformat(),
        )
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="UserMessageAdded",
            data=asdict(user_message_1),
        )

        events = read_stream(client=messagedb_client, stream_name=stream_name)

    messages = project_to_llm_context(events)
    response_1 = llm_client.call(messages, system_prompt=MINIMAL_SYSTEM_PROMPT)

    with messagedb_client:
        llm_response_1 = LLMResponseReceivedData(
            response_text=response_1.text,
            tool_calls=[],
            model_name=response_1.model_name,
            token_usage=response_1.token_usage,
        )
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="LLMResponseReceived",
            data=asdict(llm_response_1),
        )

        # Turn 2: User asks follow-up that requires context
        user_message_2 = UserMessageData(
            message="What color did I just tell you about?",
            timestamp=datetime.now(UTC).isoformat(),
        )
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="UserMessageAdded",
            data=asdict(user_message_2),
        )

        events = read_stream(client=messagedb_client, stream_name=stream_name)

    messages = project_to_llm_context(events)

    # Verify context includes both turns
    assert len(messages) == 3  # user, assistant, user
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[2].role == "user"

    response_2 = llm_client.call(messages, system_prompt=MINIMAL_SYSTEM_PROMPT)

    # LLM should reference the previous context
    assert "blue" in response_2.text.lower()

    with messagedb_client:
        llm_response_2 = LLMResponseReceivedData(
            response_text=response_2.text,
            tool_calls=[],
            model_name=response_2.model_name,
            token_usage=response_2.token_usage,
        )
        write_message(
            client=messagedb_client,
            stream_name=stream_name,
            message_type="LLMResponseReceived",
            data=asdict(llm_response_2),
        )

        # Verify final state
        all_events = read_stream(client=messagedb_client, stream_name=stream_name)
    assert len(all_events) == 5  # SessionStarted, 2 user messages, 2 LLM responses

    final_messages = project_to_llm_context(all_events)
    assert len(final_messages) == 4  # user, assistant, user, assistant

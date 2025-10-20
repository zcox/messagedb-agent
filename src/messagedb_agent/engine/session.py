"""Session lifecycle management for the event-sourced agent system.

This module provides functions for managing agent session lifecycle:
- Starting new sessions with initial user messages
- Terminating sessions gracefully

Sessions are identified by thread IDs and stored in Message DB streams
using the format: {category}:{version}-{threadId}
"""

from datetime import UTC, datetime

import structlog

from messagedb_agent.events.system import SESSION_STARTED
from messagedb_agent.events.user import USER_MESSAGE_ADDED
from messagedb_agent.store import MessageDBClient, build_stream_name, generate_thread_id
from messagedb_agent.store.operations import write_message

logger = structlog.get_logger(__name__)


class SessionError(Exception):
    """Raised when session operations encounter an error."""

    pass


def start_session(
    initial_message: str,
    store_client: MessageDBClient,
    category: str = "agent",
    version: str = "v0",
) -> str:
    """Start a new agent session with an initial user message.

    This function initializes a new session by:
    1. Generating a unique thread ID
    2. Building the stream name
    3. Writing a SessionStarted event
    4. Writing a UserMessageAdded event with the initial message
    5. Returning the thread ID for further processing

    Args:
        initial_message: The initial message from the user to start the session
        store_client: Connected MessageDB client for writing events
        category: Stream category (default: "agent")
        version: Stream version (default: "v0")

    Returns:
        The generated thread ID (UUID string)

    Raises:
        SessionError: If event writing fails or other critical error occurs
        ValueError: If initial_message is empty or whitespace-only

    Example:
        ```python
        from messagedb_agent.store import MessageDBClient, MessageDBConfig
        from messagedb_agent.engine.session import start_session

        config = MessageDBConfig()
        with MessageDBClient(config) as store_client:
            thread_id = start_session(
                initial_message="Hello, I need help with my code",
                store_client=store_client
            )
            print(f"Started session: {thread_id}")

            # Now process the session
            from messagedb_agent.engine.loop import process_thread
            final_state = process_thread(
                thread_id=thread_id,
                stream_name=f"agent:v0-{thread_id}",
                store_client=store_client,
                llm_client=llm_client,
                tool_registry=tool_registry
            )
        ```
    """
    # Validate input
    if not initial_message or not initial_message.strip():
        raise ValueError("initial_message cannot be empty or whitespace-only")

    log = logger.bind(
        category=category,
        version=version,
    )

    log.info("Starting new session")

    # Step 1: Generate unique thread ID
    thread_id = generate_thread_id()
    log = log.bind(thread_id=thread_id)

    log.debug("Generated thread ID")

    # Step 2: Build stream name
    stream_name = build_stream_name(category, version, thread_id)
    log = log.bind(stream_name=stream_name)

    log.debug("Built stream name")

    # Step 3: Write SessionStarted event
    try:
        session_started_position = write_message(
            client=store_client,
            stream_name=stream_name,
            message_type=SESSION_STARTED,
            data={
                "thread_id": thread_id,
            },
            metadata={},
        )
        log.debug("SessionStarted event written", position=session_started_position)
    except Exception as e:
        log.error("Failed to write SessionStarted event", error=str(e))
        raise SessionError(f"Failed to write SessionStarted event: {e}") from e

    # Step 4: Write UserMessageAdded event with initial message
    # Generate ISO 8601 timestamp
    timestamp = datetime.now(UTC).isoformat()

    try:
        user_message_position = write_message(
            client=store_client,
            stream_name=stream_name,
            message_type=USER_MESSAGE_ADDED,
            data={
                "message": initial_message,
                "timestamp": timestamp,
            },
            metadata={},
        )
        log.info(
            "Session started successfully",
            session_started_position=session_started_position,
            user_message_position=user_message_position,
            message_length=len(initial_message),
        )
    except Exception as e:
        log.error("Failed to write UserMessageAdded event", error=str(e))
        raise SessionError(f"Failed to write UserMessageAdded event: {e}") from e

    return thread_id

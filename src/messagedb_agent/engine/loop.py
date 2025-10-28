"""Main processing loop for the event-sourced agent system.

This module implements the core processing loop that executes agent workflows
by reading events from Message DB streams, projecting them into state, determining
the next step, and executing that step.

The loop follows the specification's processing model:
1. Read events from stream for threadId
2. Project events into required state/context
3. Determine next step based on current state
4. Execute step (LLM call, tool execution, or termination)
5. Write result as new event(s) to stream
6. Repeat until termination or max_iterations

This implementation uses an explicit while-loop within a single process,
though the architecture supports distributed processing where each step
is triggered by events across multiple processes.
"""

from uuid import UUID

import structlog

from messagedb_agent.engine.steps.llm import execute_llm_step
from messagedb_agent.engine.steps.tool import execute_tool_step
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.llm.base import BaseLLMClient
from messagedb_agent.projections.next_step import StepType, project_to_next_step
from messagedb_agent.projections.session_state import SessionState, project_to_session_state
from messagedb_agent.store import Message, MessageDBClient, read_stream
from messagedb_agent.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


class ProcessingError(Exception):
    """Raised when processing loop encounters an error."""

    pass


class MaxIterationsExceeded(ProcessingError):
    """Raised when processing loop exceeds maximum iterations."""

    pass


def _message_to_event(message: Message) -> BaseEvent:
    """Convert a Message DB Message to a BaseEvent.

    Args:
        message: Message object from read_stream

    Returns:
        BaseEvent with same data
    """
    # Convert id string to UUID if needed
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


def process_thread(
    thread_id: str,
    stream_name: str,
    store_client: MessageDBClient,
    llm_client: BaseLLMClient,
    tool_registry: ToolRegistry,
    max_iterations: int = 100,
) -> SessionState:
    """Process an agent thread until completion or max iterations.

    This is the main processing loop that orchestrates the event-sourced agent
    workflow. It continuously reads events, determines the next step, executes
    that step, and writes results back to the stream.

    The loop terminates when:
    - The session is explicitly terminated (SessionCompleted event)
    - max_iterations is reached (prevents infinite loops)

    Args:
        thread_id: Unique identifier for this agent session
        stream_name: Full Message DB stream name (e.g., "agent:v0-{threadId}")
        store_client: Connected MessageDB client for reading/writing events
        llm_client: LLM client for making LLM calls
        tool_registry: Registry of available tools for execution
        max_iterations: Maximum number of loop iterations (default: 100)

    Returns:
        Final SessionState after processing completes

    Raises:
        MaxIterationsExceeded: If loop exceeds max_iterations
        ProcessingError: If processing encounters an unrecoverable error

    Example:
        ```python
        from messagedb_agent.store import MessageDBClient, MessageDBConfig
        from messagedb_agent.llm import create_llm_client
        from messagedb_agent.tools import ToolRegistry
        from messagedb_agent.engine import process_thread

        # Setup clients
        store_config = MessageDBConfig()
        with MessageDBClient(store_config) as store_client:
            llm_client = create_llm_client(llm_config)
            tool_registry = ToolRegistry()

            # Process thread
            final_state = process_thread(
                thread_id="abc-123",
                stream_name="agent:v0-abc-123",
                store_client=store_client,
                llm_client=llm_client,
                tool_registry=tool_registry,
                max_iterations=50
            )

            print(f"Session completed with status: {final_state.status}")
        ```
    """
    log = logger.bind(
        thread_id=thread_id,
        stream_name=stream_name,
        max_iterations=max_iterations,
    )

    log.info("Starting thread processing")

    iteration = 0
    terminated_naturally = False
    last_position = -1  # Track last position read (-1 means nothing read yet)
    accumulated_events: list[BaseEvent] = []  # Accumulate all events for projections

    while iteration < max_iterations:
        iteration += 1
        log_iter = log.bind(iteration=iteration)
        log_iter.debug("Processing loop iteration")

        # Step 1: Read events from the stream
        # First iteration (last_position=-1): reads from position 0 (beginning)
        # Subsequent iterations: read only new messages after last_position
        messages = read_stream(store_client, stream_name, position=last_position + 1)
        log_iter.debug(
            "Reading events from stream",
            last_position=last_position,
            reading_from_position=last_position + 1,
        )

        # Convert messages to events and accumulate them
        new_events = [_message_to_event(msg) for msg in messages]
        accumulated_events.extend(new_events)

        # Update last_position if we read any messages
        if messages:
            last_position = max(msg.position for msg in messages)
            log_iter.debug(
                "Read events from stream",
                new_event_count=len(new_events),
                total_event_count=len(accumulated_events),
                last_position=last_position,
            )

        # Use accumulated_events for projections (they need full history)
        events = accumulated_events

        # Handle empty stream case (shouldn't happen in normal flow)
        if not events:
            log_iter.warning("No events found in stream, ending processing")
            raise ProcessingError(f"No events found in stream: {stream_name}")

        # Step 2: Project events to determine next step
        step_type, step_metadata = project_to_next_step(events)

        log_iter.info(
            "Determined next step",
            step_type=step_type.value,
            step_metadata=step_metadata,
        )

        # Step 3: Check for termination
        if step_type == StepType.TERMINATION:
            log_iter.info("Session termination requested", reason=step_metadata.get("reason"))
            terminated_naturally = True
            break

        # Step 4: Execute the appropriate step
        if step_type == StepType.LLM_CALL:
            log_iter.info("Executing LLM step")
            success = execute_llm_step(
                events=events,
                llm_client=llm_client,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=store_client,
            )
            if not success:
                log_iter.warning("LLM step failed after retries")
                # Continue loop - the LLMCallFailed event was written
                # Next iteration will determine next step based on failure event

        elif step_type == StepType.TOOL_EXECUTION:
            log_iter.info("Executing tool step")
            success = execute_tool_step(
                events=events,
                tool_registry=tool_registry,
                stream_name=stream_name,
                store_client=store_client,
            )
            if not success:
                log_iter.warning("Some tools failed during execution")
                # Continue loop - tool failure events were written
                # Next iteration will determine next step based on tool results

    # Check if we exceeded max iterations without natural termination
    if not terminated_naturally and iteration >= max_iterations:
        log.error("Exceeded maximum iterations", iterations=iteration)
        raise MaxIterationsExceeded(
            f"Processing exceeded maximum iterations ({max_iterations}) for thread {thread_id}"
        )

    # Step 5: Project final session state
    # Re-read events one final time to get the complete state
    messages = read_stream(store_client, stream_name)
    events = [_message_to_event(msg) for msg in messages]
    final_state = project_to_session_state(events)

    log.info(
        "Thread processing complete",
        final_status=final_state.status.value,
        iterations=iteration,
        message_count=final_state.message_count,
        llm_call_count=final_state.llm_call_count,
        tool_call_count=final_state.tool_call_count,
    )

    return final_state

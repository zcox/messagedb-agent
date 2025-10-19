"""Session State projection for tracking agent session status and statistics.

This module provides projection functions that analyze event streams to compute
the current state and statistics of an agent session. This enables monitoring,
debugging, and decision-making based on session activity.

The projection aggregates information from all events to build a comprehensive
view of the session status, activity levels, and timing.

Example:
    >>> from messagedb_agent.store import read_stream
    >>> from messagedb_agent.projections import project_to_session_state
    >>>
    >>> # Read events from a stream
    >>> events = read_stream(client, "agent:v0-thread123")
    >>>
    >>> # Get current session state
    >>> state = project_to_session_state(events)
    >>>
    >>> print(f"Status: {state.status}")
    >>> print(f"Messages: {state.message_count}")
    >>> print(f"Tools called: {state.tool_call_count}")
    >>> print(f"Last activity: {state.last_activity_time}")
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from messagedb_agent.events.agent import LLM_CALL_FAILED, LLM_RESPONSE_RECEIVED
from messagedb_agent.events.base import BaseEvent
from messagedb_agent.events.system import SESSION_COMPLETED, SESSION_STARTED
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_COMPLETED,
    TOOL_EXECUTION_FAILED,
)
from messagedb_agent.events.user import SESSION_TERMINATION_REQUESTED, USER_MESSAGE_ADDED


class SessionStatus(Enum):
    """Status of an agent session.

    Attributes:
        ACTIVE: Session is currently active and processing
        COMPLETED: Session has completed successfully
        FAILED: Session has failed due to an error
        TERMINATED: Session was terminated by user request
    """

    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass(frozen=True)
class SessionState:
    """Computed state of an agent session.

    This represents the current state of a session as derived from the
    complete event history. All fields are computed via projection and
    represent a point-in-time snapshot.

    Attributes:
        thread_id: Unique identifier for the session thread
        status: Current status of the session (active/completed/failed/terminated)
        message_count: Total number of user messages received
        tool_call_count: Total number of tool executions completed
        llm_call_count: Total number of successful LLM calls
        error_count: Total number of errors (LLM failures + tool failures)
        last_activity_time: Timestamp of the most recent event
        session_start_time: Timestamp when the session started (None if no SessionStarted event)
        session_end_time: Timestamp when the session ended (None if still active)

    Example:
        >>> state = SessionState(
        ...     thread_id="abc123",
        ...     status=SessionStatus.ACTIVE,
        ...     message_count=3,
        ...     tool_call_count=2,
        ...     llm_call_count=4,
        ...     error_count=0,
        ...     last_activity_time=datetime(2025, 1, 15, 10, 30, 0),
        ...     session_start_time=datetime(2025, 1, 15, 10, 0, 0),
        ...     session_end_time=None
        ... )
    """

    thread_id: str
    status: SessionStatus
    message_count: int
    tool_call_count: int
    llm_call_count: int
    error_count: int
    last_activity_time: datetime | None
    session_start_time: datetime | None
    session_end_time: datetime | None

    def __post_init__(self) -> None:
        """Validate session state after initialization.

        Raises:
            ValueError: If counts are negative or thread_id is empty
        """
        if not self.thread_id or not self.thread_id.strip():
            raise ValueError("Thread ID cannot be empty")
        if self.message_count < 0:
            raise ValueError("Message count cannot be negative")
        if self.tool_call_count < 0:
            raise ValueError("Tool call count cannot be negative")
        if self.llm_call_count < 0:
            raise ValueError("LLM call count cannot be negative")
        if self.error_count < 0:
            raise ValueError("Error count cannot be negative")


def project_to_session_state(events: list[BaseEvent]) -> SessionState:
    """Project event stream to compute current session state.

    This function analyzes the complete event history to derive the current
    state and statistics of the session. It counts various event types and
    determines session status based on the presence of completion events.

    Decision Logic:
    - If SessionCompleted event present -> status based on completion_reason
    - If SessionTerminationRequested present -> status is TERMINATED
    - If any errors present -> status is FAILED
    - Otherwise -> status is ACTIVE

    Args:
        events: List of events from the event stream in chronological order

    Returns:
        SessionState object with computed state and statistics

    Raises:
        ValueError: If event list is empty or no thread_id can be determined

    Example:
        >>> events = [
        ...     BaseEvent(
        ...         type="SessionStarted",
        ...         data={"thread_id": "abc123"},
        ...         time=datetime(2025, 1, 15, 10, 0, 0),
        ...         ...
        ...     ),
        ...     BaseEvent(
        ...         type="UserMessageAdded",
        ...         data={"message": "Hello"},
        ...         time=datetime(2025, 1, 15, 10, 1, 0),
        ...         ...
        ...     ),
        ... ]
        >>> state = project_to_session_state(events)
        >>> state.status == SessionStatus.ACTIVE
        True
        >>> state.message_count
        1
    """
    if not events:
        raise ValueError("Cannot compute session state from empty event list")

    # Extract thread_id from stream_name of first event
    thread_id = _extract_thread_id(events[0].stream_name)

    # Initialize counters
    message_count = 0
    tool_call_count = 0
    llm_call_count = 0
    error_count = 0

    # Track session lifecycle
    session_start_time: datetime | None = None
    session_end_time: datetime | None = None
    status = SessionStatus.ACTIVE
    completion_reason: str | None = None
    termination_requested = False

    # Track last activity
    last_activity_time = events[-1].time if events else None

    # Process events in order
    for event in events:
        # Count messages
        if event.type == USER_MESSAGE_ADDED:
            message_count += 1

        # Count successful tool executions
        elif event.type == TOOL_EXECUTION_COMPLETED:
            tool_call_count += 1

        # Count successful LLM calls
        elif event.type == LLM_RESPONSE_RECEIVED:
            llm_call_count += 1

        # Count errors
        elif event.type in (LLM_CALL_FAILED, TOOL_EXECUTION_FAILED):
            error_count += 1

        # Track session start
        elif event.type == SESSION_STARTED:
            session_start_time = event.time

        # Track termination request
        elif event.type == SESSION_TERMINATION_REQUESTED:
            termination_requested = True

        # Track session completion
        elif event.type == SESSION_COMPLETED:
            session_end_time = event.time
            completion_reason = event.data.get("completion_reason", "unknown")

    # Determine final status based on events
    if completion_reason is not None:
        # Session completed - determine if success or failure
        if completion_reason in ("success", "completed"):
            status = SessionStatus.COMPLETED
        else:
            status = SessionStatus.FAILED
    elif termination_requested:
        status = SessionStatus.TERMINATED
    elif error_count > 0:
        # Has errors but hasn't completed yet - still active but problematic
        # Keep as ACTIVE since session hasn't officially ended
        status = SessionStatus.ACTIVE
    else:
        status = SessionStatus.ACTIVE

    return SessionState(
        thread_id=thread_id,
        status=status,
        message_count=message_count,
        tool_call_count=tool_call_count,
        llm_call_count=llm_call_count,
        error_count=error_count,
        last_activity_time=last_activity_time,
        session_start_time=session_start_time,
        session_end_time=session_end_time,
    )


def _extract_thread_id(stream_name: str) -> str:
    """Extract thread_id from stream name.

    Stream names have format: {category}:{version}-{thread_id}
    For example: "agent:v0-abc123" -> "abc123"

    Args:
        stream_name: Full stream name

    Returns:
        Thread ID portion of the stream name

    Raises:
        ValueError: If stream name format is invalid
    """
    try:
        # Split on colon to separate category from version-threadId
        parts = stream_name.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid stream name format: {stream_name}")

        # Split version-threadId on dash
        version_thread = parts[1]
        thread_parts = version_thread.split("-", 1)
        if len(thread_parts) != 2:
            raise ValueError(f"Invalid stream name format: {stream_name}")

        thread_id = thread_parts[1]
        if not thread_id:
            raise ValueError(f"Thread ID is empty in stream name: {stream_name}")

        return thread_id
    except (IndexError, AttributeError) as e:
        raise ValueError(f"Failed to extract thread_id from stream name: {stream_name}") from e


def is_session_active(state: SessionState) -> bool:
    """Check if a session is currently active.

    Args:
        state: SessionState to check

    Returns:
        True if status is ACTIVE, False otherwise

    Example:
        >>> state = SessionState(status=SessionStatus.ACTIVE, ...)
        >>> is_session_active(state)
        True
    """
    return state.status == SessionStatus.ACTIVE


def get_session_duration(state: SessionState) -> float | None:
    """Calculate session duration in seconds.

    Returns the duration from session start to end (if completed)
    or to last activity (if still active).

    Args:
        state: SessionState to calculate duration for

    Returns:
        Duration in seconds, or None if timing information unavailable

    Example:
        >>> state = SessionState(
        ...     session_start_time=datetime(2025, 1, 15, 10, 0, 0),
        ...     last_activity_time=datetime(2025, 1, 15, 10, 5, 0),
        ...     ...
        ... )
        >>> get_session_duration(state)
        300.0
    """
    if state.session_start_time is None:
        return None

    end_time = state.session_end_time or state.last_activity_time
    if end_time is None:
        return None

    duration = end_time - state.session_start_time
    return duration.total_seconds()

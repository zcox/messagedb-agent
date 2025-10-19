"""Projection framework for transforming event streams into derived states.

This module provides the base infrastructure for projection functions, which are pure
functions that transform event histories into specific views or states needed by the system.

Key Concepts:
    - Projections are pure functions: same input events always produce same output
    - Multiple projections can exist from the same event stream
    - Projections enable separation of event storage from event consumption
    - Events stored in stream ≠ data sent to downstream consumers

Available Projections:
    - Base infrastructure (ProjectionFunction, ProjectionResult)
    - LLM Context projection (project_to_llm_context)
    - Next Step projection (project_to_next_step, StepType)
    - Session State projection (project_to_session_state, SessionStatus, SessionState)
    - Tool Arguments projection (project_to_tool_arguments, get_tool_call_by_name)

Example:
    >>> from messagedb_agent.projections import ProjectionFunction, project_with_metadata
    >>> from messagedb_agent.events import BaseEvent
    >>>
    >>> # Define a custom projection
    >>> def count_messages(events: list[BaseEvent]) -> int:
    ...     return sum(1 for e in events if e.type == "UserMessageAdded")
    >>>
    >>> # Use the projection
    >>> events = [...]  # Load events from stream
    >>> result = project_with_metadata(events, count_messages)
    >>> print(f"Found {result.value} messages in {result.event_count} events")
"""

from messagedb_agent.projections.base import (
    ProjectionFunction,
    ProjectionResult,
    compose_projections,
    project_with_metadata,
)
from messagedb_agent.projections.llm_context import (
    count_conversation_turns,
    get_last_user_message,
    project_to_llm_context,
)
from messagedb_agent.projections.next_step import (
    StepType,
    count_steps_taken,
    get_pending_tool_calls,
    project_to_next_step,
    should_terminate,
)
from messagedb_agent.projections.session_state import (
    SessionState,
    SessionStatus,
    get_session_duration,
    is_session_active,
    project_to_session_state,
)
from messagedb_agent.projections.tool_args import (
    count_tool_calls,
    get_all_tool_names,
    get_tool_call_by_name,
    has_pending_tool_calls,
    project_to_tool_arguments,
)

__all__ = [
    # Base infrastructure
    "ProjectionFunction",
    "ProjectionResult",
    "project_with_metadata",
    "compose_projections",
    # LLM Context projection
    "project_to_llm_context",
    "get_last_user_message",
    "count_conversation_turns",
    # Next Step projection
    "StepType",
    "project_to_next_step",
    "should_terminate",
    "get_pending_tool_calls",
    "count_steps_taken",
    # Session State projection
    "SessionState",
    "SessionStatus",
    "project_to_session_state",
    "is_session_active",
    "get_session_duration",
    # Tool Arguments projection
    "project_to_tool_arguments",
    "get_tool_call_by_name",
    "get_all_tool_names",
    "has_pending_tool_calls",
    "count_tool_calls",
]

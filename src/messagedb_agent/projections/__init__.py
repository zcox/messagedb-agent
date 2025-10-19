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
    - LLM Context projection (coming in Task 4.2)
    - Session State projection (coming in Task 4.3)
    - Tool Arguments projection (coming in Task 4.4)
    - Next Step projection (coming in Task 4.5)

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

__all__ = [
    "ProjectionFunction",
    "ProjectionResult",
    "project_with_metadata",
    "compose_projections",
]

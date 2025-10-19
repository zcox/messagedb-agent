"""Base infrastructure for projection functions.

Projections are pure functions that transform event histories into derived states
or views. They enable the system to store rich event data while providing specific
views optimized for different consumers (LLM, tools, UI, etc.).

Core Principles:
    - Projections are pure functions: same inputs always produce same outputs
    - No side effects (no I/O, no state mutation, no randomness)
    - Deterministic and testable
    - Multiple projections can exist from the same event stream
    - Events stored in stream ` data sent to consumers

Type Safety:
    The projection framework uses generics to provide type-safe projections:
    - ProjectionFunction[T] - A function that projects events to type T
    - ProjectionResult[T] - A wrapper for projection results of type T

Example:
    >>> from messagedb_agent.events import BaseEvent
    >>> from messagedb_agent.projections.base import ProjectionFunction
    >>>
    >>> # Define a projection that counts user messages
    >>> def count_user_messages(events: list[BaseEvent]) -> int:
    ...     return sum(1 for e in events if e.type == "UserMessageAdded")
    >>>
    >>> # The function is a ProjectionFunction[int]
    >>> projection: ProjectionFunction[int] = count_user_messages
    >>>
    >>> # Use it
    >>> events = [...]  # Load from stream
    >>> count = projection(events)  # Returns int
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

from messagedb_agent.events.base import BaseEvent

# Generic type variable for projection results
T = TypeVar("T")


# Type alias for projection functions
# A projection function takes a list of events and returns a value of type T
ProjectionFunction = Callable[[list[BaseEvent]], T]


@dataclass(frozen=True)
class ProjectionResult(Generic[T]):
    """A wrapper for projection results that provides metadata and type safety.

    This class wraps the result of a projection function along with metadata
    about the projection itself. It's useful for tracking which events were
    processed and providing context about the projection.

    Attributes:
        value: The result of the projection
        event_count: Number of events that were projected
        last_position: Position of the last event processed (None if no events)

    Example:
        >>> events = [event1, event2, event3]
        >>> result = project_with_metadata(events, count_user_messages)
        >>> print(result.value)  # The count
        >>> print(result.event_count)  # 3
        >>> print(result.last_position)  # Position of event3
    """

    value: T
    event_count: int
    last_position: int | None

    def __post_init__(self) -> None:
        """Validate the projection result.

        Raises:
            ValueError: If event_count is negative
        """
        if self.event_count < 0:
            raise ValueError(f"event_count must be non-negative, got {self.event_count}")


def project_with_metadata(
    events: list[BaseEvent],
    projection: ProjectionFunction[T],
) -> ProjectionResult[T]:
    """Apply a projection function and wrap the result with metadata.

    This helper function applies a projection and automatically captures
    metadata about the events that were processed.

    Args:
        events: List of events to project
        projection: The projection function to apply

    Returns:
        ProjectionResult containing the projected value and metadata

    Example:
        >>> def count_messages(events: list[BaseEvent]) -> int:
        ...     return len(events)
        >>>
        >>> events = [event1, event2, event3]
        >>> result = project_with_metadata(events, count_messages)
        >>> assert result.value == 3
        >>> assert result.event_count == 3
        >>> assert result.last_position == event3.position
    """
    value = projection(events)
    event_count = len(events)
    last_position = events[-1].position if events else None

    return ProjectionResult(
        value=value,
        event_count=event_count,
        last_position=last_position,
    )


def compose_projections(
    *projections: ProjectionFunction[T],
) -> ProjectionFunction[list[T]]:
    """Compose multiple projection functions into a single projection.

    This utility allows you to apply multiple projections to the same event
    stream in a single pass, which can be more efficient than applying them
    separately.

    Args:
        *projections: Variable number of projection functions to compose

    Returns:
        A projection function that returns a list of results, one per input projection

    Example:
        >>> def count_messages(events: list[BaseEvent]) -> int:
        ...     return len(events)
        >>>
        >>> def count_users(events: list[BaseEvent]) -> int:
        ...     return len({e.data.get("user_id") for e in events})
        >>>
        >>> combined = compose_projections(count_messages, count_users)
        >>> results = combined(events)
        >>> message_count, user_count = results
    """

    def combined_projection(events: list[BaseEvent]) -> list[T]:
        return [projection(events) for projection in projections]

    return combined_projection

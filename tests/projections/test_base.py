"""Tests for projection base infrastructure."""

from datetime import UTC, datetime
from typing import Any

import pytest

from messagedb_agent.events.base import BaseEvent
from messagedb_agent.projections.base import (
    ProjectionFunction,
    ProjectionResult,
    compose_projections,
    project_with_metadata,
)


# Test fixtures and helper functions
def create_test_event(
    event_type: str,
    data: dict[str, Any] | None = None,
    position: int = 0,
    global_position: int = 0,
) -> BaseEvent:
    """Create a test event for projection testing."""
    return BaseEvent(
        id="test-id",
        type=event_type,
        data=data or {},
        metadata={},
        position=position,
        global_position=global_position,
        time=datetime.now(UTC),
        stream_name="test:v0-thread123",
    )


# Sample projection functions for testing
def count_events(events: list[BaseEvent]) -> int:
    """Count total number of events."""
    return len(events)


def count_by_type(events: list[BaseEvent]) -> dict[str, int]:
    """Count events by type."""
    counts: dict[str, int] = {}
    for event in events:
        counts[event.type] = counts.get(event.type, 0) + 1
    return counts


def get_last_event_position(events: list[BaseEvent]) -> int | None:
    """Get position of last event."""
    return events[-1].position if events else None


def filter_user_messages(events: list[BaseEvent]) -> list[BaseEvent]:
    """Filter only user message events."""
    return [e for e in events if e.type == "UserMessageAdded"]


# Tests for ProjectionResult
class TestProjectionResult:
    """Tests for ProjectionResult dataclass."""

    def test_create_projection_result_with_value(self):
        """Test creating a projection result with a simple value."""
        result = ProjectionResult(value=42, event_count=10, last_position=9)
        assert result.value == 42
        assert result.event_count == 10
        assert result.last_position == 9

    def test_create_projection_result_with_none_position(self):
        """Test creating a projection result with no last position (empty events)."""
        result = ProjectionResult(value=0, event_count=0, last_position=None)
        assert result.value == 0
        assert result.event_count == 0
        assert result.last_position is None

    def test_projection_result_is_frozen(self):
        """Test that ProjectionResult is immutable."""
        result = ProjectionResult(value=42, event_count=10, last_position=9)
        with pytest.raises((AttributeError, TypeError)):
            result.value = 100  # type: ignore

    def test_projection_result_with_complex_value(self):
        """Test projection result with complex value types."""
        value = {"count": 5, "types": ["A", "B"]}
        result = ProjectionResult(value=value, event_count=5, last_position=4)
        assert result.value == value
        assert result.value["count"] == 5

    def test_projection_result_validates_negative_event_count(self):
        """Test that negative event counts are rejected."""
        with pytest.raises(ValueError, match="event_count must be non-negative"):
            ProjectionResult(value=42, event_count=-1, last_position=0)


# Tests for project_with_metadata
class TestProjectWithMetadata:
    """Tests for project_with_metadata helper function."""

    def test_project_with_metadata_simple_projection(self):
        """Test projecting events with metadata tracking."""
        events = [
            create_test_event("UserMessageAdded", position=0),
            create_test_event("LLMResponseReceived", position=1),
            create_test_event("UserMessageAdded", position=2),
        ]

        result = project_with_metadata(events, count_events)

        assert result.value == 3
        assert result.event_count == 3
        assert result.last_position == 2

    def test_project_with_metadata_empty_events(self):
        """Test projecting empty event list."""
        events: list[BaseEvent] = []

        result = project_with_metadata(events, count_events)

        assert result.value == 0
        assert result.event_count == 0
        assert result.last_position is None

    def test_project_with_metadata_complex_projection(self):
        """Test projecting with a function that returns complex data."""
        events = [
            create_test_event("UserMessageAdded", position=0),
            create_test_event("UserMessageAdded", position=1),
            create_test_event("LLMResponseReceived", position=2),
        ]

        result = project_with_metadata(events, count_by_type)

        assert result.value == {"UserMessageAdded": 2, "LLMResponseReceived": 1}
        assert result.event_count == 3
        assert result.last_position == 2

    def test_project_with_metadata_preserves_projection_purity(self):
        """Test that calling projection multiple times gives same result."""
        events = [
            create_test_event("UserMessageAdded", position=0),
            create_test_event("LLMResponseReceived", position=1),
        ]

        result1 = project_with_metadata(events, count_events)
        result2 = project_with_metadata(events, count_events)

        assert result1.value == result2.value
        assert result1.event_count == result2.event_count
        assert result1.last_position == result2.last_position

    def test_project_with_metadata_tracks_global_position(self):
        """Test that last_position comes from the event's position field."""
        events = [
            create_test_event("UserMessageAdded", position=100, global_position=1000),
            create_test_event("LLMResponseReceived", position=101, global_position=1001),
        ]

        result = project_with_metadata(events, count_events)

        # Should use position, not global_position
        assert result.last_position == 101


# Tests for compose_projections
class TestComposeProjections:
    """Tests for compose_projections utility."""

    def test_compose_two_projections(self):
        """Test composing two projection functions."""
        events = [
            create_test_event("UserMessageAdded", position=0),
            create_test_event("LLMResponseReceived", position=1),
            create_test_event("UserMessageAdded", position=2),
        ]

        combined = compose_projections(count_events, get_last_event_position)
        results = combined(events)

        assert len(results) == 2
        assert results[0] == 3  # count_events
        assert results[1] == 2  # get_last_event_position

    def test_compose_single_projection(self):
        """Test composing a single projection (edge case)."""
        events = [create_test_event("UserMessageAdded", position=0)]

        combined = compose_projections(count_events)
        results = combined(events)

        assert len(results) == 1
        assert results[0] == 1

    def test_compose_multiple_projections(self):
        """Test composing more than two projections."""
        events = [
            create_test_event("UserMessageAdded", position=0),
            create_test_event("UserMessageAdded", position=1),
            create_test_event("LLMResponseReceived", position=2),
        ]

        def count_user_messages(evts: list[BaseEvent]) -> int:
            return sum(1 for e in evts if e.type == "UserMessageAdded")

        def count_llm_responses(evts: list[BaseEvent]) -> int:
            return sum(1 for e in evts if e.type == "LLMResponseReceived")

        combined = compose_projections(
            count_events,
            count_user_messages,
            count_llm_responses,
        )
        results = combined(events)

        assert len(results) == 3
        assert results[0] == 3  # total count
        assert results[1] == 2  # user messages
        assert results[2] == 1  # LLM responses

    def test_compose_projections_with_empty_events(self):
        """Test composed projections with empty event list."""
        events: list[BaseEvent] = []

        combined = compose_projections(count_events, get_last_event_position)
        results = combined(events)

        assert len(results) == 2
        assert results[0] == 0
        assert results[1] is None

    def test_compose_projections_purity(self):
        """Test that composed projections are pure (same input -> same output)."""
        events = [
            create_test_event("UserMessageAdded", position=0),
            create_test_event("LLMResponseReceived", position=1),
        ]

        combined = compose_projections(count_events, count_by_type)

        results1 = combined(events)
        results2 = combined(events)

        assert results1 == results2


# Tests for ProjectionFunction type
class TestProjectionFunctionType:
    """Tests for ProjectionFunction type alias and usage."""

    def test_projection_function_type_hint(self):
        """Test that functions can be typed as ProjectionFunction."""
        # This is a compile-time test, but we can verify runtime behavior
        projection: ProjectionFunction[int] = count_events

        events = [create_test_event("UserMessageAdded", position=0)]
        result = projection(events)

        assert result == 1
        assert isinstance(result, int)

    def test_projection_function_with_different_return_types(self):
        """Test ProjectionFunction with various return types."""
        int_projection: ProjectionFunction[int] = count_events
        dict_projection: ProjectionFunction[dict[str, int]] = count_by_type
        optional_projection: ProjectionFunction[int | None] = get_last_event_position

        events = [create_test_event("UserMessageAdded", position=5)]

        assert isinstance(int_projection(events), int)
        assert isinstance(dict_projection(events), dict)
        assert isinstance(optional_projection(events), int)


# Integration tests
class TestProjectionIntegration:
    """Integration tests for the projection framework."""

    def test_end_to_end_projection_workflow(self):
        """Test a complete projection workflow with multiple steps."""
        # Create a realistic event sequence
        events = [
            create_test_event("SessionStarted", {"thread_id": "thread-1"}, position=0),
            create_test_event("UserMessageAdded", {"message": "Hello"}, position=1),
            create_test_event("LLMResponseReceived", {"text": "Hi there"}, position=2),
            create_test_event("UserMessageAdded", {"message": "How are you?"}, position=3),
            create_test_event("LLMResponseReceived", {"text": "I'm good"}, position=4),
        ]

        # Apply multiple projections
        count_result = project_with_metadata(events, count_events)
        type_count_result = project_with_metadata(events, count_by_type)

        # Verify results
        assert count_result.value == 5
        assert count_result.event_count == 5
        assert count_result.last_position == 4

        assert type_count_result.value["UserMessageAdded"] == 2
        assert type_count_result.value["LLMResponseReceived"] == 2
        assert type_count_result.value["SessionStarted"] == 1

    def test_projection_with_filtering(self):
        """Test projecting after filtering events."""
        events = [
            create_test_event("SessionStarted", position=0),
            create_test_event("UserMessageAdded", position=1),
            create_test_event("LLMResponseReceived", position=2),
            create_test_event("UserMessageAdded", position=3),
        ]

        # Filter then project
        user_events = filter_user_messages(events)
        result = project_with_metadata(user_events, count_events)

        assert result.value == 2
        assert result.event_count == 2

    def test_chaining_projections_manually(self):
        """Test manually chaining projection results."""
        events = [
            create_test_event("UserMessageAdded", position=0),
            create_test_event("UserMessageAdded", position=1),
            create_test_event("LLMResponseReceived", position=2),
        ]

        # First projection: count all events
        total_count = count_events(events)

        # Second projection: count by type
        type_counts = count_by_type(events)

        # Use both results together
        user_message_count = type_counts.get("UserMessageAdded", 0)
        assert total_count == 3
        assert user_message_count == 2
        assert user_message_count / total_count == pytest.approx(0.666, rel=0.01)

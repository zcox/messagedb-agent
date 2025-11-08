"""Tests for display preference tools."""

from datetime import UTC, datetime

import pytest

from messagedb_agent.store.client import MessageDBClient
from messagedb_agent.store.operations import Message, write_message
from messagedb_agent.tools.display_tools import (
    DISPLAY_TOOLS,
    get_display_preferences,
    merge_display_prefs,
    project_display_prefs,
    register_display_tools,
    set_display_preferences,
)
from messagedb_agent.tools.registry import ToolRegistry


class TestDisplayToolDeclarations:
    """Tests for DISPLAY_TOOLS declarations."""

    def test_has_two_tools(self):
        """Test that DISPLAY_TOOLS contains exactly two tools."""
        assert len(DISPLAY_TOOLS) == 2

    def test_get_display_preferences_declaration(self):
        """Test get_display_preferences tool declaration."""
        tool = next(t for t in DISPLAY_TOOLS if t.name == "get_display_preferences")
        assert tool.name == "get_display_preferences"
        assert "display preferences" in tool.description.lower()
        assert tool.parameters["type"] == "object"
        assert tool.parameters["properties"] == {}
        assert tool.parameters["required"] == []

    def test_set_display_preferences_declaration(self):
        """Test set_display_preferences tool declaration."""
        tool = next(t for t in DISPLAY_TOOLS if t.name == "set_display_preferences")
        assert tool.name == "set_display_preferences"
        assert "update" in tool.description.lower()
        assert tool.parameters["type"] == "object"
        assert "instruction" in tool.parameters["properties"]
        assert "merge_with_existing" in tool.parameters["properties"]
        assert tool.parameters["required"] == ["instruction"]


class TestProjectDisplayPrefs:
    """Tests for project_display_prefs function."""

    def test_empty_events_returns_default(self):
        """Test that empty event list returns 'default'."""
        result = project_display_prefs([])
        assert result == "default"

    def test_single_event_returns_merged_preferences(self):
        """Test projection with a single DisplayPreferenceUpdated event."""
        events = [
            Message(
                id="1",
                stream_name="display-prefs:thread123",
                type="DisplayPreferenceUpdated",
                position=0,
                global_position=0,
                data={"merged_preferences": "Show compact view"},
                metadata=None,
                time=datetime.now(UTC),
            )
        ]
        result = project_display_prefs(events)
        assert result == "Show compact view"

    def test_multiple_events_returns_most_recent(self):
        """Test that projection returns the most recent preference."""
        events = [
            Message(
                id="1",
                stream_name="display-prefs:thread123",
                type="DisplayPreferenceUpdated",
                position=0,
                global_position=0,
                data={"merged_preferences": "Show compact view"},
                metadata=None,
                time=datetime.now(UTC),
            ),
            Message(
                id="2",
                stream_name="display-prefs:thread123",
                type="DisplayPreferenceUpdated",
                position=1,
                global_position=1,
                data={"merged_preferences": "Show compact view. Highlight errors in red"},
                metadata=None,
                time=datetime.now(UTC),
            ),
        ]
        result = project_display_prefs(events)
        assert result == "Show compact view. Highlight errors in red"

    def test_missing_merged_preferences_returns_default(self):
        """Test handling of event without merged_preferences field."""
        events = [
            Message(
                id="1",
                stream_name="display-prefs:thread123",
                type="DisplayPreferenceUpdated",
                position=0,
                global_position=0,
                data={},
                metadata=None,
                time=datetime.now(UTC),
            )
        ]
        result = project_display_prefs(events)
        assert result == "default"

    def test_ignores_non_display_preference_events(self):
        """Test that non-DisplayPreferenceUpdated events are ignored."""
        events = [
            Message(
                id="1",
                stream_name="display-prefs:thread123",
                type="SomeOtherEvent",
                position=0,
                global_position=0,
                data={"merged_preferences": "Should be ignored"},
                metadata=None,
                time=datetime.now(UTC),
            )
        ]
        result = project_display_prefs(events)
        assert result == "default"


class TestMergeDisplayPrefs:
    """Tests for merge_display_prefs function."""

    @pytest.mark.asyncio
    async def test_default_current_returns_instruction(self):
        """Test merging when current is 'default'."""
        result = await merge_display_prefs("default", "Show compact view")
        assert result == "Show compact view"

    @pytest.mark.asyncio
    async def test_empty_current_returns_instruction(self):
        """Test merging when current is empty string."""
        result = await merge_display_prefs("", "Show compact view")
        assert result == "Show compact view"

    @pytest.mark.asyncio
    async def test_merge_appends_with_period(self):
        """Test that merging appends new instruction with period separator."""
        result = await merge_display_prefs("Show compact view", "Highlight errors in red")
        assert result == "Show compact view. Highlight errors in red"

    @pytest.mark.asyncio
    async def test_reset_instruction_returns_default(self):
        """Test that 'reset' instruction returns 'default'."""
        result = await merge_display_prefs("Show compact view", "reset")
        assert result == "default"

    @pytest.mark.asyncio
    async def test_default_instruction_returns_default(self):
        """Test that 'default' instruction returns 'default'."""
        result = await merge_display_prefs("Show compact view", "default")
        assert result == "default"

    @pytest.mark.asyncio
    async def test_default_instruction_case_insensitive(self):
        """Test that 'DEFAULT' and 'Reset' work case-insensitively."""
        result1 = await merge_display_prefs("Show compact view", "DEFAULT")
        result2 = await merge_display_prefs("Show compact view", "Reset")
        assert result1 == "default"
        assert result2 == "default"


class TestGetDisplayPreferences:
    """Tests for get_display_preferences function."""

    def test_no_events_returns_default(self, messagedb_client: MessageDBClient):
        """Test that get_display_preferences returns 'default' when no events exist."""
        result = get_display_preferences(messagedb_client, "thread123")
        assert result == "default"

    def test_returns_merged_preferences_from_event(self, messagedb_client: MessageDBClient):
        """Test that get_display_preferences returns merged preferences from event."""
        # Write a DisplayPreferenceUpdated event
        write_message(
            client=messagedb_client,
            stream_name="display-prefs:thread123",
            message_type="DisplayPreferenceUpdated",
            data={
                "instruction": "Show compact view",
                "merged_preferences": "Show compact view",
                "previous_preferences": None,
            },
        )

        result = get_display_preferences(messagedb_client, "thread123")
        assert result == "Show compact view"

    def test_returns_most_recent_preferences(self, messagedb_client: MessageDBClient):
        """Test that get_display_preferences returns the most recent preferences."""
        # Write multiple events
        write_message(
            client=messagedb_client,
            stream_name="display-prefs:thread456",
            message_type="DisplayPreferenceUpdated",
            data={
                "instruction": "Show compact view",
                "merged_preferences": "Show compact view",
                "previous_preferences": None,
            },
        )
        write_message(
            client=messagedb_client,
            stream_name="display-prefs:thread456",
            message_type="DisplayPreferenceUpdated",
            data={
                "instruction": "Highlight errors in red",
                "merged_preferences": "Show compact view. Highlight errors in red",
                "previous_preferences": "Show compact view",
            },
        )

        result = get_display_preferences(messagedb_client, "thread456")
        assert result == "Show compact view. Highlight errors in red"


class TestSetDisplayPreferences:
    """Tests for set_display_preferences function."""

    @pytest.mark.asyncio
    async def test_sets_preference_with_no_existing(self, messagedb_client: MessageDBClient):
        """Test setting preferences when no existing preferences exist."""
        result = await set_display_preferences(messagedb_client, "thread789", "Show compact view")

        assert "Show compact view" in result
        # Verify event was written
        stored_prefs = get_display_preferences(messagedb_client, "thread789")
        assert stored_prefs == "Show compact view"

    @pytest.mark.asyncio
    async def test_merges_with_existing_by_default(self, messagedb_client: MessageDBClient):
        """Test that set_display_preferences merges with existing by default."""
        # Set initial preference
        await set_display_preferences(messagedb_client, "threadabc", "Show compact view")

        # Set another preference (should merge)
        result = await set_display_preferences(
            messagedb_client, "threadabc", "Highlight errors in red"
        )

        assert "Show compact view. Highlight errors in red" in result
        stored_prefs = get_display_preferences(messagedb_client, "threadabc")
        assert stored_prefs == "Show compact view. Highlight errors in red"

    @pytest.mark.asyncio
    async def test_replaces_when_merge_false(self, messagedb_client: MessageDBClient):
        """Test that set_display_preferences replaces when merge_with_existing=False."""
        # Set initial preference
        await set_display_preferences(messagedb_client, "threaddef", "Show compact view")

        # Set another preference (should replace)
        result = await set_display_preferences(
            messagedb_client,
            "threaddef",
            "Show detailed view",
            merge_with_existing=False,
        )

        assert "Show detailed view" in result
        # Should NOT contain old preference
        assert "compact" not in result.lower()
        stored_prefs = get_display_preferences(messagedb_client, "threaddef")
        assert stored_prefs == "Show detailed view"

    @pytest.mark.asyncio
    async def test_writes_correct_event_structure(self, messagedb_client: MessageDBClient):
        """Test that set_display_preferences writes the correct event structure."""
        await set_display_preferences(messagedb_client, "threadxyz", "Test instruction")

        # Read the event directly
        from messagedb_agent.store.operations import read_stream

        events = read_stream(messagedb_client, "display-prefs:threadxyz")
        assert len(events) == 1

        event = events[0]
        assert event.type == "DisplayPreferenceUpdated"
        assert event.data["instruction"] == "Test instruction"
        assert event.data["merged_preferences"] == "Test instruction"
        assert event.data["previous_preferences"] == "default"

    @pytest.mark.asyncio
    async def test_returns_confirmation_message(self, messagedb_client: MessageDBClient):
        """Test that set_display_preferences returns a confirmation message."""
        result = await set_display_preferences(messagedb_client, "thread999", "My preference")

        assert "Display preferences updated to:" in result
        assert "My preference" in result


class TestRegisterDisplayTools:
    """Tests for register_display_tools function."""

    def test_registers_both_tools(self):
        """Test that register_display_tools registers both tools."""
        registry = ToolRegistry()
        register_display_tools(registry)

        assert "get_display_preferences" in registry
        assert "set_display_preferences" in registry

    def test_registered_tools_have_correct_names(self):
        """Test that registered tools have correct names."""
        registry = ToolRegistry()
        register_display_tools(registry)

        get_tool = registry.get("get_display_preferences")
        set_tool = registry.get("set_display_preferences")

        assert get_tool.name == "get_display_preferences"
        assert set_tool.name == "set_display_preferences"

    def test_registered_tools_have_descriptions(self):
        """Test that registered tools have descriptions."""
        registry = ToolRegistry()
        register_display_tools(registry)

        get_tool = registry.get("get_display_preferences")
        set_tool = registry.get("set_display_preferences")

        assert len(get_tool.description) > 0
        assert len(set_tool.description) > 0

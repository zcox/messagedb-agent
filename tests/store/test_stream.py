"""Tests for stream name utilities."""

import re
import uuid

import pytest

from messagedb_agent.store.stream import (
    build_stream_name,
    generate_thread_id,
    parse_stream_name,
)


class TestGenerateThreadId:
    """Tests for generate_thread_id function."""

    def test_generates_valid_uuid4(self):
        """Should generate a valid UUID4 string."""
        thread_id = generate_thread_id()

        # Should be a valid UUID
        parsed = uuid.UUID(thread_id)
        assert str(parsed) == thread_id

        # Should be version 4
        assert parsed.version == 4

    def test_generates_unique_ids(self):
        """Should generate unique IDs on each call."""
        ids = {generate_thread_id() for _ in range(100)}
        assert len(ids) == 100

    def test_returns_string(self):
        """Should return a string type."""
        thread_id = generate_thread_id()
        assert isinstance(thread_id, str)

    def test_standard_uuid_format(self):
        """Should return UUID in standard format (with dashes)."""
        thread_id = generate_thread_id()
        # Standard UUID format: 8-4-4-4-12 hex digits
        pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        assert re.match(pattern, thread_id)


class TestBuildStreamName:
    """Tests for build_stream_name function."""

    def test_builds_correct_format(self):
        """Should build stream name in correct format."""
        stream_name = build_stream_name("agent", "v0", "abc123")
        assert stream_name == "agent:v0-abc123"

    def test_preserves_all_components(self):
        """Should preserve all input components exactly."""
        category = "myCategory"
        version = "v42"
        thread_id = "thread-xyz-789"

        stream_name = build_stream_name(category, version, thread_id)
        assert stream_name == "myCategory:v42-thread-xyz-789"

    def test_with_uuid_thread_id(self):
        """Should work with UUID thread IDs."""
        thread_id = str(uuid.uuid4())
        stream_name = build_stream_name("agent", "v0", thread_id)
        assert stream_name.startswith("agent:v0-")
        assert thread_id in stream_name

    def test_rejects_empty_category(self):
        """Should raise ValueError for empty category."""
        with pytest.raises(ValueError, match="category cannot be empty"):
            build_stream_name("", "v0", "thread123")

    def test_rejects_whitespace_only_category(self):
        """Should raise ValueError for whitespace-only category."""
        with pytest.raises(ValueError, match="category cannot be empty"):
            build_stream_name("   ", "v0", "thread123")

    def test_rejects_empty_version(self):
        """Should raise ValueError for empty version."""
        with pytest.raises(ValueError, match="version cannot be empty"):
            build_stream_name("agent", "", "thread123")

    def test_rejects_whitespace_only_version(self):
        """Should raise ValueError for whitespace-only version."""
        with pytest.raises(ValueError, match="version cannot be empty"):
            build_stream_name("agent", "  ", "thread123")

    def test_rejects_empty_thread_id(self):
        """Should raise ValueError for empty thread_id."""
        with pytest.raises(ValueError, match="thread_id cannot be empty"):
            build_stream_name("agent", "v0", "")

    def test_rejects_whitespace_only_thread_id(self):
        """Should raise ValueError for whitespace-only thread_id."""
        with pytest.raises(ValueError, match="thread_id cannot be empty"):
            build_stream_name("agent", "v0", "   ")

    def test_rejects_colon_in_category(self):
        """Should raise ValueError if category contains colon."""
        with pytest.raises(ValueError, match="category cannot contain ':' character"):
            build_stream_name("my:category", "v0", "thread123")

    def test_rejects_dash_in_version(self):
        """Should raise ValueError if version contains dash."""
        with pytest.raises(ValueError, match="version cannot contain '-' character"):
            build_stream_name("agent", "v0-beta", "thread123")

    def test_allows_dash_in_thread_id(self):
        """Should allow dashes in thread_id (for UUIDs)."""
        stream_name = build_stream_name("agent", "v0", "abc-def-123")
        assert stream_name == "agent:v0-abc-def-123"

    def test_allows_colon_in_thread_id(self):
        """Should allow colons in thread_id."""
        stream_name = build_stream_name("agent", "v0", "thread:123")
        assert stream_name == "agent:v0-thread:123"


class TestParseStreamName:
    """Tests for parse_stream_name function."""

    def test_parses_simple_stream_name(self):
        """Should parse a simple stream name correctly."""
        category, version, thread_id = parse_stream_name("agent:v0-abc123")
        assert category == "agent"
        assert version == "v0"
        assert thread_id == "abc123"

    def test_parses_with_uuid_thread_id(self):
        """Should parse stream name with UUID thread ID."""
        original_thread_id = str(uuid.uuid4())
        stream_name = f"agent:v0-{original_thread_id}"

        category, version, thread_id = parse_stream_name(stream_name)
        assert category == "agent"
        assert version == "v0"
        assert thread_id == original_thread_id

    def test_parses_complex_names(self):
        """Should parse stream names with complex components."""
        stream_name = "myCategory:v42-thread-xyz-789"
        category, version, thread_id = parse_stream_name(stream_name)

        assert category == "myCategory"
        assert version == "v42"
        assert thread_id == "thread-xyz-789"

    def test_parses_thread_id_with_colon(self):
        """Should handle thread_id containing colons."""
        stream_name = "agent:v0-thread:with:colons"
        category, version, thread_id = parse_stream_name(stream_name)

        assert category == "agent"
        assert version == "v0"
        assert thread_id == "thread:with:colons"

    def test_round_trip_consistency(self):
        """Should maintain consistency in build -> parse -> build cycle."""
        original_category = "agent"
        original_version = "v0"
        original_thread_id = str(uuid.uuid4())

        # Build stream name
        stream_name = build_stream_name(original_category, original_version, original_thread_id)

        # Parse it back
        category, version, thread_id = parse_stream_name(stream_name)

        # Verify all components match
        assert category == original_category
        assert version == original_version
        assert thread_id == original_thread_id

        # Build again and verify it matches
        rebuilt = build_stream_name(category, version, thread_id)
        assert rebuilt == stream_name

    def test_rejects_empty_stream_name(self):
        """Should raise ValueError for empty stream name."""
        with pytest.raises(ValueError, match="stream_name cannot be empty"):
            parse_stream_name("")

    def test_rejects_whitespace_only_stream_name(self):
        """Should raise ValueError for whitespace-only stream name."""
        with pytest.raises(ValueError, match="stream_name cannot be empty"):
            parse_stream_name("   ")

    def test_rejects_missing_colon(self):
        """Should raise ValueError if stream name has no colon."""
        with pytest.raises(ValueError, match="Invalid stream name format"):
            parse_stream_name("agentv0-thread123")

    def test_rejects_missing_dash(self):
        """Should raise ValueError if stream name has no dash."""
        with pytest.raises(ValueError, match="Invalid stream name format"):
            parse_stream_name("agent:v0thread123")

    def test_rejects_only_category(self):
        """Should raise ValueError if only category is provided."""
        with pytest.raises(ValueError, match="Invalid stream name format"):
            parse_stream_name("agent")

    def test_rejects_category_and_version_only(self):
        """Should raise ValueError if thread_id is missing."""
        with pytest.raises(ValueError, match="Invalid stream name format"):
            parse_stream_name("agent:v0")

    def test_rejects_empty_category_component(self):
        """Should raise ValueError if category component is empty."""
        with pytest.raises(ValueError, match="category component cannot be empty"):
            parse_stream_name(":v0-thread123")

    def test_rejects_empty_version_component(self):
        """Should raise ValueError if version component is empty."""
        with pytest.raises(ValueError, match="version component cannot be empty"):
            parse_stream_name("agent:-thread123")

    def test_rejects_empty_thread_id_component(self):
        """Should raise ValueError if thread_id component is empty."""
        with pytest.raises(ValueError, match="thread_id component cannot be empty"):
            parse_stream_name("agent:v0-")

    def test_handles_multiple_colons_in_category_and_thread(self):
        """Should only split on first colon, allowing colons in thread_id."""
        # This has colon in thread_id which should be preserved
        stream_name = "agent:v0-thread:with:many:colons"
        category, version, thread_id = parse_stream_name(stream_name)

        assert category == "agent"
        assert version == "v0"
        assert thread_id == "thread:with:many:colons"

    def test_handles_multiple_dashes_in_thread_id(self):
        """Should only split on first dash after colon, allowing dashes in thread_id."""
        stream_name = "agent:v0-thread-with-many-dashes"
        category, version, thread_id = parse_stream_name(stream_name)

        assert category == "agent"
        assert version == "v0"
        assert thread_id == "thread-with-many-dashes"


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_end_to_end_workflow(self):
        """Should support typical workflow: generate -> build -> parse."""
        # Generate thread ID
        thread_id = generate_thread_id()
        assert len(thread_id) == 36  # Standard UUID length with dashes

        # Build stream name
        stream_name = build_stream_name("agent", "v0", thread_id)
        assert "agent:v0-" in stream_name

        # Parse it back
        parsed_category, parsed_version, parsed_thread_id = parse_stream_name(stream_name)
        assert parsed_category == "agent"
        assert parsed_version == "v0"
        assert parsed_thread_id == thread_id

    def test_multiple_threads_have_unique_stream_names(self):
        """Should generate unique stream names for different threads."""
        stream_names = set()
        for _ in range(100):
            thread_id = generate_thread_id()
            stream_name = build_stream_name("agent", "v0", thread_id)
            stream_names.add(stream_name)

        # All stream names should be unique
        assert len(stream_names) == 100

    def test_same_category_different_versions(self):
        """Should distinguish between different versions of same category."""
        thread_id = generate_thread_id()

        v0_stream = build_stream_name("agent", "v0", thread_id)
        v1_stream = build_stream_name("agent", "v1", thread_id)

        assert v0_stream != v1_stream
        assert "agent:v0-" in v0_stream
        assert "agent:v1-" in v1_stream

        # Both should parse correctly
        cat0, ver0, tid0 = parse_stream_name(v0_stream)
        cat1, ver1, tid1 = parse_stream_name(v1_stream)

        assert cat0 == cat1 == "agent"
        assert ver0 == "v0"
        assert ver1 == "v1"
        assert tid0 == tid1 == thread_id

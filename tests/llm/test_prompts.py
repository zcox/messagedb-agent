"""Tests for LLM system prompts module."""

import pytest

from messagedb_agent.llm.prompts import (
    DEFAULT_SYSTEM_PROMPT,
    MINIMAL_SYSTEM_PROMPT,
    TOOL_FOCUSED_SYSTEM_PROMPT,
    create_system_prompt,
    get_prompt_for_task,
)


class TestDefaultPrompts:
    """Test the default system prompts."""

    def test_default_system_prompt_exists(self):
        """Test that default system prompt is defined and non-empty."""
        assert DEFAULT_SYSTEM_PROMPT
        assert len(DEFAULT_SYSTEM_PROMPT) > 0
        assert isinstance(DEFAULT_SYSTEM_PROMPT, str)

    def test_default_system_prompt_content(self):
        """Test that default system prompt contains expected content."""
        # Should mention event-sourced architecture
        assert "event" in DEFAULT_SYSTEM_PROMPT.lower()
        # Should mention tools
        assert "tool" in DEFAULT_SYSTEM_PROMPT.lower()
        # Should have clear structure
        assert len(DEFAULT_SYSTEM_PROMPT.split("\n")) > 5

    def test_minimal_system_prompt_exists(self):
        """Test that minimal system prompt is defined and shorter."""
        assert MINIMAL_SYSTEM_PROMPT
        assert len(MINIMAL_SYSTEM_PROMPT) > 0
        assert len(MINIMAL_SYSTEM_PROMPT) < len(DEFAULT_SYSTEM_PROMPT)

    def test_tool_focused_system_prompt_exists(self):
        """Test that tool-focused prompt is defined."""
        assert TOOL_FOCUSED_SYSTEM_PROMPT
        assert len(TOOL_FOCUSED_SYSTEM_PROMPT) > 0
        # Should emphasize tools
        assert "tool" in TOOL_FOCUSED_SYSTEM_PROMPT.lower()


class TestCreateSystemPrompt:
    """Test the create_system_prompt function."""

    def test_create_system_prompt_default(self):
        """Test creating prompt with default parameters."""
        prompt = create_system_prompt()
        assert prompt == DEFAULT_SYSTEM_PROMPT

    def test_create_system_prompt_with_minimal_base(self):
        """Test creating prompt with minimal base."""
        prompt = create_system_prompt(base_prompt=MINIMAL_SYSTEM_PROMPT)
        assert prompt == MINIMAL_SYSTEM_PROMPT

    def test_create_system_prompt_with_additional_instructions(self):
        """Test adding additional instructions."""
        additional = "You are a coding assistant."
        prompt = create_system_prompt(additional_instructions=additional)

        assert DEFAULT_SYSTEM_PROMPT in prompt
        assert additional in prompt
        assert len(prompt) > len(DEFAULT_SYSTEM_PROMPT)

    def test_create_system_prompt_with_tools_list(self):
        """Test adding available tools list."""
        tools = ["calculate", "search_web", "read_file"]
        prompt = create_system_prompt(available_tools=tools)

        assert DEFAULT_SYSTEM_PROMPT in prompt
        assert "Available Tools:" in prompt
        for tool in tools:
            assert tool in prompt

    def test_create_system_prompt_with_both(self):
        """Test adding both additional instructions and tools."""
        additional = "Focus on accuracy."
        tools = ["verify", "validate"]
        prompt = create_system_prompt(
            additional_instructions=additional,
            available_tools=tools,
        )

        assert DEFAULT_SYSTEM_PROMPT in prompt
        assert additional in prompt
        assert "Available Tools:" in prompt
        assert "verify" in prompt
        assert "validate" in prompt

    def test_create_system_prompt_custom_base_with_additions(self):
        """Test custom base prompt with additions."""
        custom_base = "You are a test assistant."
        additional = "Be thorough."
        tools = ["test_runner"]

        prompt = create_system_prompt(
            base_prompt=custom_base,
            additional_instructions=additional,
            available_tools=tools,
        )

        assert custom_base in prompt
        assert additional in prompt
        assert "test_runner" in prompt
        # Should not contain default prompt
        assert DEFAULT_SYSTEM_PROMPT not in prompt


class TestGetPromptForTask:
    """Test the get_prompt_for_task function."""

    def test_get_prompt_for_default_task(self):
        """Test getting default task prompt."""
        prompt = get_prompt_for_task("default")
        assert prompt == DEFAULT_SYSTEM_PROMPT

    def test_get_prompt_for_minimal_task(self):
        """Test getting minimal task prompt."""
        prompt = get_prompt_for_task("minimal")
        assert prompt == MINIMAL_SYSTEM_PROMPT

    def test_get_prompt_for_tool_focused_task(self):
        """Test getting tool-focused task prompt."""
        prompt = get_prompt_for_task("tool_focused")
        assert prompt == TOOL_FOCUSED_SYSTEM_PROMPT

    def test_get_prompt_for_analytical_task(self):
        """Test getting analytical task prompt."""
        prompt = get_prompt_for_task("analytical")
        assert len(prompt) > 0
        # Should be based on default with additions
        assert DEFAULT_SYSTEM_PROMPT in prompt
        assert "analytical" in prompt.lower() or "reasoning" in prompt.lower()

    def test_get_prompt_for_invalid_task(self):
        """Test that invalid task type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            get_prompt_for_task("invalid_task_type")

        assert "Unknown task_type" in str(exc_info.value)
        assert "invalid_task_type" in str(exc_info.value)
        # Should list valid types
        assert "default" in str(exc_info.value)
        assert "minimal" in str(exc_info.value)

    def test_all_task_types_return_strings(self):
        """Test that all valid task types return non-empty strings."""
        task_types = ["default", "minimal", "tool_focused", "analytical"]

        for task_type in task_types:
            prompt = get_prompt_for_task(task_type)
            assert isinstance(prompt, str)
            assert len(prompt) > 0


class TestPromptQuality:
    """Test the quality and consistency of prompts."""

    def test_prompts_are_non_empty(self):
        """Test that all exported prompts are non-empty."""
        prompts = [
            DEFAULT_SYSTEM_PROMPT,
            MINIMAL_SYSTEM_PROMPT,
            TOOL_FOCUSED_SYSTEM_PROMPT,
        ]

        for prompt in prompts:
            assert prompt
            assert len(prompt.strip()) > 0

    def test_prompts_have_reasonable_length(self):
        """Test that prompts are not excessively long."""
        # Prompts should be < 2000 characters to be token-efficient
        assert len(DEFAULT_SYSTEM_PROMPT) < 2000
        assert len(MINIMAL_SYSTEM_PROMPT) < 500
        assert len(TOOL_FOCUSED_SYSTEM_PROMPT) < 1000

    def test_prompts_are_properly_formatted(self):
        """Test that prompts are properly formatted."""
        # Should not have excessive whitespace
        assert not DEFAULT_SYSTEM_PROMPT.startswith(" ")
        assert not DEFAULT_SYSTEM_PROMPT.endswith(" ")

        # Should not have multiple consecutive blank lines
        assert "\n\n\n" not in DEFAULT_SYSTEM_PROMPT

    def test_create_system_prompt_preserves_structure(self):
        """Test that created prompts have good structure."""
        prompt = create_system_prompt(
            additional_instructions="Test instruction",
            available_tools=["tool1", "tool2"],
        )

        # Should have clear sections
        sections = prompt.split("\n\n")
        assert len(sections) >= 2  # At least base + one addition

        # Should not have trailing/leading whitespace
        assert prompt == prompt.strip()

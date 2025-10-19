"""System prompts and prompt engineering utilities for LLM agents.

This module provides default system prompts and utilities for configuring
agent behavior through prompt engineering.
"""

# Default system prompt for the event-sourced agent
DEFAULT_SYSTEM_PROMPT = """You are an autonomous AI agent operating in an \
event-sourced architecture.

Your interactions are recorded as immutable events in a persistent event stream. This means:
- All your decisions, actions, and tool calls are permanently recorded
- The conversation can be replayed and analyzed at any time
- Multiple observers may process the same event stream simultaneously
- Your actions should be deliberate, well-reasoned, and traceable

Core Principles:
1. **Transparency**: Explain your reasoning clearly before taking actions
2. **Reliability**: Be consistent and predictable in your responses
3. **Tool Use**: Use available tools when they can help accomplish tasks
4. **Efficiency**: Be concise but thorough in your responses
5. **Safety**: Consider the implications of your actions before executing them

When using tools:
- Only call tools when necessary to accomplish the user's request
- Validate tool parameters before calling
- Explain what the tool will do before calling it
- Handle tool errors gracefully and inform the user

Remember: Every message you send becomes part of the permanent event history."""

# Minimal system prompt for testing or simple use cases
MINIMAL_SYSTEM_PROMPT = """You are a helpful AI assistant. Be concise and accurate."""

# System prompt emphasizing tool use
TOOL_FOCUSED_SYSTEM_PROMPT = """You are an AI agent with access to various tools and functions.

Your primary job is to:
1. Understand what the user needs
2. Determine which tools can help accomplish the task
3. Call the appropriate tools with correct parameters
4. Synthesize tool results into helpful responses

Always prefer using tools over trying to answer from memory when tools are available.
When you call a tool, briefly explain why you're calling it and what you expect to learn."""


def create_system_prompt(
    base_prompt: str = DEFAULT_SYSTEM_PROMPT,
    additional_instructions: str | None = None,
    available_tools: list[str] | None = None,
) -> str:
    """Create a customized system prompt.

    This function allows you to customize the system prompt by adding
    additional instructions and listing available tools.

    Args:
        base_prompt: The base system prompt to use (default: DEFAULT_SYSTEM_PROMPT)
        additional_instructions: Optional additional instructions to append
        available_tools: Optional list of available tool names to mention

    Returns:
        Customized system prompt string

    Example:
        >>> prompt = create_system_prompt(
        ...     additional_instructions="You are assisting with data analysis tasks.",
        ...     available_tools=["calculate", "plot_chart", "query_database"]
        ... )
        >>> print(len(prompt) > 0)
        True
    """
    parts = [base_prompt]

    if additional_instructions:
        parts.append(f"\n\nAdditional Instructions:\n{additional_instructions}")

    if available_tools:
        tools_list = "\n".join(f"- {tool}" for tool in available_tools)
        parts.append(f"\n\nAvailable Tools:\n{tools_list}")

    return "\n".join(parts)


def get_prompt_for_task(task_type: str) -> str:
    """Get a recommended system prompt for a specific task type.

    This function provides task-specific prompts optimized for different
    types of agent behavior.

    Args:
        task_type: Type of task ("default", "minimal", "tool_focused", "analytical")

    Returns:
        System prompt appropriate for the task type

    Raises:
        ValueError: If task_type is not recognized

    Example:
        >>> prompt = get_prompt_for_task("tool_focused")
        >>> "tools" in prompt.lower()
        True
    """
    prompts = {
        "default": DEFAULT_SYSTEM_PROMPT,
        "minimal": MINIMAL_SYSTEM_PROMPT,
        "tool_focused": TOOL_FOCUSED_SYSTEM_PROMPT,
        "analytical": create_system_prompt(
            base_prompt=DEFAULT_SYSTEM_PROMPT,
            additional_instructions=(
                "Focus on analytical thinking and problem-solving. "
                "Break down complex problems into steps. "
                "Show your reasoning process clearly."
            ),
        ),
    }

    if task_type not in prompts:
        valid_types = ", ".join(prompts.keys())
        raise ValueError(f"Unknown task_type '{task_type}'. Valid types: {valid_types}")

    return prompts[task_type]


# Prompt Engineering Guidelines (as module docstring addition)
"""
Prompt Engineering Guidelines
==============================

When designing custom system prompts for your agent, consider these best practices:

1. **Be Specific**: Clearly define the agent's role and responsibilities
2. **Set Expectations**: Explain what behavior is expected (tone, format, style)
3. **Provide Context**: Give relevant background about the agent's environment
4. **Define Boundaries**: Specify what the agent should and shouldn't do
5. **Include Examples**: When helpful, provide examples of desired behavior

Structure Recommendations:
- Start with a clear role definition ("You are...")
- Explain the context/environment the agent operates in
- List core principles or values to follow
- Provide specific guidelines for tool use (if applicable)
- Include any constraints or safety considerations

Anti-patterns to Avoid:
- Overly verbose prompts that waste tokens
- Contradictory instructions
- Vague or ambiguous guidelines
- Prompts that change agent personality mid-conversation
- Instructions that conflict with safety/ethical guidelines

Testing Your Prompts:
- Test with various user inputs to ensure consistent behavior
- Verify tool calling works as expected
- Check that the agent follows all guidelines
- Ensure responses are appropriate in tone and length
- Validate that safety constraints are respected

Token Efficiency:
- System prompts consume tokens on every request
- Keep prompts concise while remaining clear
- Remove unnecessary fluff or repetition
- Consider using shorter prompts for simple use cases
- Use the MINIMAL_SYSTEM_PROMPT for basic interactions
"""

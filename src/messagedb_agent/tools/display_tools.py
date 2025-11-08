"""Display preference tools for customizing event display in the UI.

This module provides tools that allow the LLM agent to get and set display
preferences based on user requests, without requiring explicit intent detection.
"""

from typing import Any

import structlog

from messagedb_agent.llm.base import ToolDeclaration
from messagedb_agent.store.client import MessageDBClient
from messagedb_agent.store.operations import Message, read_stream, write_message

logger = structlog.get_logger(__name__)

# Tool declarations that will be exposed to the LLM
DISPLAY_TOOLS = [
    ToolDeclaration(
        name="get_display_preferences",
        description="Get the current display preferences for how events are rendered in the UI",
        parameters={"type": "object", "properties": {}, "required": []},
    ),
    ToolDeclaration(
        name="set_display_preferences",
        description="""Update how events are displayed in the UI. Use this when the user wants to \
customize the display.

Examples:
- User: "show compact view" → set_display_preferences(instruction="show compact view")
- User: "highlight errors in red" → set_display_preferences(instruction="highlight errors in red")
- User: "reset display" → set_display_preferences(instruction="default", merge_with_existing=False)
""",
        parameters={
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "The display instruction",
                },
                "merge_with_existing": {
                    "type": "boolean",
                    "description": "If true, merge with current preferences. If false, replace.",
                    "default": True,
                },
            },
            "required": ["instruction"],
        },
    ),
]


def project_display_prefs(events: list[Message]) -> str:
    """Project display preferences from event history.

    This is a pure projection function that takes a list of DisplayPreferenceUpdated
    events and returns the current display preferences as a string.

    Args:
        events: List of events from the display-prefs stream

    Returns:
        String describing current display preferences, or "default" if no events

    Example:
        >>> events = [
        ...     Message(
        ...         id="1",
        ...         stream_name="display-prefs:thread123",
        ...         type="DisplayPreferenceUpdated",
        ...         position=0,
        ...         global_position=0,
        ...         data={"merged_preferences": "Show compact view"},
        ...         metadata=None,
        ...         time=datetime.now()
        ...     )
        ... ]
        >>> project_display_prefs(events)
        'Show compact view'
    """
    if not events:
        return "default"

    # Get the most recent DisplayPreferenceUpdated event
    for event in reversed(events):
        if event.type == "DisplayPreferenceUpdated":
            return event.data.get("merged_preferences", "default")

    return "default"


async def merge_display_prefs(current: str, instruction: str) -> str:
    """Merge new display instruction with current preferences.

    This function takes the current preferences and a new instruction and
    combines them intelligently. For now, it uses a simple approach of
    concatenating them. In the future, this could use an LLM to merge
    preferences more intelligently.

    Args:
        current: Current display preferences string
        instruction: New instruction to merge in

    Returns:
        Merged preferences string

    Example:
        >>> import asyncio
        >>> asyncio.run(merge_display_prefs("Show compact view", "Highlight errors in red"))
        'Show compact view. Highlight errors in red'
    """
    if current == "default" or not current:
        return instruction

    # Handle reset instruction
    if instruction.lower() in ("default", "reset"):
        return "default"

    # Simple concatenation - could be enhanced with LLM-based merging
    return f"{current}. {instruction}"


def get_display_preferences(client: MessageDBClient, thread_id: str) -> str:
    """Get current display preferences from display-prefs stream.

    This tool function reads the display-prefs stream for the given thread
    and projects the current preferences.

    Args:
        client: MessageDBClient instance (must be connected)
        thread_id: Thread ID to get preferences for

    Returns:
        String describing current display preferences

    Example:
        >>> from messagedb_agent.store import MessageDBClient, MessageDBConfig
        >>> config = MessageDBConfig()
        >>> with MessageDBClient(config) as client:
        ...     prefs = get_display_preferences(client, "thread123")
        ...     print(prefs)
        'default'
    """
    stream_name = f"display-prefs:{thread_id}"
    log = logger.bind(stream_name=stream_name, thread_id=thread_id)

    log.info("Getting display preferences")

    events = read_stream(client, stream_name)
    preferences = project_display_prefs(events)

    log.info("Display preferences retrieved", preferences=preferences)
    return preferences


async def set_display_preferences(
    client: MessageDBClient,
    thread_id: str,
    instruction: str,
    merge_with_existing: bool = True,
) -> str:
    """Update display preferences by writing event to display-prefs stream.

    This tool function updates the display preferences for a thread by writing
    a DisplayPreferenceUpdated event to the display-prefs stream.

    Args:
        client: MessageDBClient instance (must be connected)
        thread_id: Thread ID to set preferences for
        instruction: The display instruction from the user
        merge_with_existing: If True, merge with current prefs. If False, replace.

    Returns:
        Confirmation message with the updated preferences

    Example:
        >>> import asyncio
        >>> from messagedb_agent.store import MessageDBClient, MessageDBConfig
        >>> config = MessageDBConfig()
        >>> with MessageDBClient(config) as client:
        ...     result = asyncio.run(set_display_preferences(
        ...         client, "thread123", "show compact view"
        ...     ))
        ...     print(result)
        'Display preferences updated to: show compact view'
    """
    stream_name = f"display-prefs:{thread_id}"
    log = logger.bind(
        stream_name=stream_name,
        thread_id=thread_id,
        instruction=instruction,
        merge_with_existing=merge_with_existing,
    )

    log.info("Setting display preferences")

    # Get current preferences if merging
    current = None
    merged = instruction

    if merge_with_existing:
        current = get_display_preferences(client, thread_id)
        merged = await merge_display_prefs(current, instruction)
        log.info("Merged preferences", current=current, merged=merged)

    # Write DisplayPreferenceUpdated event
    write_message(
        client=client,
        stream_name=stream_name,
        message_type="DisplayPreferenceUpdated",
        data={
            "instruction": instruction,
            "merged_preferences": merged,
            "previous_preferences": current,
        },
    )

    log.info("Display preferences updated", merged_preferences=merged)
    return f"Display preferences updated to: {merged}"


def register_display_tools(registry: Any, client: MessageDBClient, thread_id: str) -> None:
    """Register display preference tools to a registry with context injection.

    This function registers the get_display_preferences and set_display_preferences
    tools to the provided registry. The tools are created as closures that capture
    the MessageDBClient and thread_id from the execution context.

    Args:
        registry: ToolRegistry instance to register tools to
        client: MessageDBClient instance to use for reading/writing events
        thread_id: Thread ID for this agent session

    Example:
        >>> from messagedb_agent.tools import ToolRegistry
        >>> from messagedb_agent.store import MessageDBClient, MessageDBConfig
        >>> from messagedb_agent.tools.display_tools import register_display_tools
        >>> config = MessageDBConfig()
        >>> with MessageDBClient(config) as client:
        ...     registry = ToolRegistry()
        ...     register_display_tools(registry, client, "thread123")
        ...     "get_display_preferences" in registry
        True
    """
    from messagedb_agent.tools.registry import PermissionLevel, Tool

    # Create closures that capture client and thread_id
    def get_prefs_impl() -> str:
        """Implementation that uses captured context."""
        return get_display_preferences(client, thread_id)

    def set_prefs_impl(instruction: str, merge_with_existing: bool = True) -> str:
        """Implementation that uses captured context."""
        import asyncio

        return asyncio.run(
            set_display_preferences(client, thread_id, instruction, merge_with_existing)
        )

    # Register get_display_preferences with explicit schema (no parameters)
    get_prefs_tool = Tool(
        name="get_display_preferences",
        description="Get the current display preferences for how events are rendered in the UI",
        parameters_schema={"type": "object", "properties": {}, "required": []},
        function=get_prefs_impl,
        permission_level=PermissionLevel.SAFE,
    )
    registry.register(get_prefs_tool)

    # Register set_display_preferences with explicit schema (only LLM-provided params)
    set_prefs_tool = Tool(
        name="set_display_preferences",
        description="Update how events are displayed in the UI",
        parameters_schema={
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "The display instruction from the user",
                },
                "merge_with_existing": {
                    "type": "boolean",
                    "description": "If true, merge with current preferences. "
                    "If false, replace entirely.",
                },
            },
            "required": ["instruction"],
        },
        function=set_prefs_impl,
        permission_level=PermissionLevel.SAFE,
    )
    registry.register(set_prefs_tool)

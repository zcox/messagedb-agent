"""Tool framework for agent execution.

This module provides the tool registration and execution infrastructure
for the event-sourced agent system.
"""

from messagedb_agent.tools.registry import (
    Tool,
    ToolError,
    ToolNotFoundError,
    ToolRegistrationError,
    ToolRegistry,
    get_tool_metadata,
    register_tool,
    tool,
)

__all__ = [
    "Tool",
    "ToolRegistry",
    "ToolError",
    "ToolNotFoundError",
    "ToolRegistrationError",
    "tool",
    "register_tool",
    "get_tool_metadata",
]

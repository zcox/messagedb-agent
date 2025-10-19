"""Tool framework for agent execution.

This module provides the tool registration and execution infrastructure
for the event-sourced agent system.
"""

from messagedb_agent.tools.builtin import (
    calculate,
    echo,
    get_builtin_tools,
    get_current_time,
    register_builtin_tools,
)
from messagedb_agent.tools.executor import (
    ToolExecutionError,
    ToolExecutionResult,
    ToolExecutionTimeoutError,
    batch_execute_tools,
    execute_tool,
    execute_tool_safe,
)
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
    # Registry
    "Tool",
    "ToolRegistry",
    "ToolError",
    "ToolNotFoundError",
    "ToolRegistrationError",
    "tool",
    "register_tool",
    "get_tool_metadata",
    # Executor
    "ToolExecutionResult",
    "ToolExecutionError",
    "ToolExecutionTimeoutError",
    "execute_tool",
    "execute_tool_safe",
    "batch_execute_tools",
    # Builtin tools
    "get_current_time",
    "echo",
    "calculate",
    "get_builtin_tools",
    "register_builtin_tools",
]

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
    PermissionLevel,
    Tool,
    ToolError,
    ToolNotFoundError,
    ToolRegistrationError,
    ToolRegistry,
    get_tool_metadata,
    register_tool,
    tool,
)
from messagedb_agent.tools.schema import (
    filter_tools_by_name,
    get_tool_names_from_declarations,
    merge_schema_properties,
    registry_to_function_declarations,
    tool_to_function_declaration,
    tools_to_function_declarations,
    validate_function_declaration,
)

__all__ = [
    # Registry
    "PermissionLevel",
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
    # Schema conversion
    "tool_to_function_declaration",
    "tools_to_function_declarations",
    "registry_to_function_declarations",
    "get_tool_names_from_declarations",
    "validate_function_declaration",
    "filter_tools_by_name",
    "merge_schema_properties",
]

"""Schema conversion utilities for tools.

This module provides functions to convert Tool objects into format suitable
for LLM function calling APIs.
"""

from typing import Any

from messagedb_agent.llm.base import ToolDeclaration
from messagedb_agent.tools.registry import Tool, ToolRegistry


def tool_to_function_declaration(tool: Tool) -> ToolDeclaration:
    """Convert a Tool object to a ToolDeclaration for LLM function calling.

    Args:
        tool: Tool object to convert

    Returns:
        ToolDeclaration suitable for LLM API

    Example:
        >>> from messagedb_agent.tools import Tool
        >>> tool = Tool(
        ...     name="add",
        ...     description="Add two numbers",
        ...     parameters_schema={
        ...         "type": "object",
        ...         "properties": {
        ...             "a": {"type": "integer"},
        ...             "b": {"type": "integer"}
        ...         },
        ...         "required": ["a", "b"]
        ...     },
        ...     function=lambda a, b: a + b
        ... )
        >>> declaration = tool_to_function_declaration(tool)
        >>> declaration.name
        'add'
    """
    return ToolDeclaration(
        name=tool.name,
        description=tool.description,
        parameters=tool.parameters_schema,
    )


def tools_to_function_declarations(tools: list[Tool]) -> list[ToolDeclaration]:
    """Convert a list of Tool objects to ToolDeclarations.

    Args:
        tools: List of Tool objects to convert

    Returns:
        List of ToolDeclarations suitable for LLM API

    Example:
        >>> tools = [tool1, tool2, tool3]
        >>> declarations = tools_to_function_declarations(tools)
        >>> len(declarations) == len(tools)
        True
    """
    return [tool_to_function_declaration(tool) for tool in tools]


def registry_to_function_declarations(registry: ToolRegistry) -> list[ToolDeclaration]:
    """Convert all tools in a registry to ToolDeclarations.

    Args:
        registry: ToolRegistry containing tools to convert

    Returns:
        List of ToolDeclarations for all tools in registry

    Example:
        >>> from messagedb_agent.tools import ToolRegistry, register_builtin_tools
        >>> registry = ToolRegistry()
        >>> register_builtin_tools(registry)
        >>> declarations = registry_to_function_declarations(registry)
        >>> len(declarations) == len(registry)
        True
    """
    return tools_to_function_declarations(registry.list_tools())


def get_tool_names_from_declarations(
    declarations: list[ToolDeclaration],
) -> list[str]:
    """Extract tool names from a list of ToolDeclarations.

    Args:
        declarations: List of ToolDeclarations

    Returns:
        List of tool names

    Example:
        >>> declarations = [
        ...     ToolDeclaration(name="add", description="Add", parameters={}),
        ...     ToolDeclaration(name="multiply", description="Multiply", parameters={})
        ... ]
        >>> get_tool_names_from_declarations(declarations)
        ['add', 'multiply']
    """
    return [decl.name for decl in declarations]


def validate_function_declaration(declaration: ToolDeclaration) -> bool:
    """Validate that a ToolDeclaration is properly formed.

    Args:
        declaration: ToolDeclaration to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> decl = ToolDeclaration(
        ...     name="test",
        ...     description="Test tool",
        ...     parameters={"type": "object", "properties": {}}
        ... )
        >>> validate_function_declaration(decl)
        True
    """
    # Check required fields
    if not declaration.name or not declaration.name.strip():
        return False

    if not declaration.description or not declaration.description.strip():
        return False

    # Validate parameters schema structure
    if "type" not in declaration.parameters:
        return False

    if declaration.parameters.get("type") != "object":
        return False

    # Properties should be a dict if present
    if "properties" in declaration.parameters:
        if not isinstance(declaration.parameters["properties"], dict):
            return False

    # Required should be a list if present
    if "required" in declaration.parameters:
        if not isinstance(declaration.parameters["required"], list):
            return False

    return True


def filter_tools_by_name(
    declarations: list[ToolDeclaration],
    tool_names: list[str],
) -> list[ToolDeclaration]:
    """Filter ToolDeclarations to only include specified tool names.

    Args:
        declarations: List of all ToolDeclarations
        tool_names: List of tool names to include

    Returns:
        Filtered list of ToolDeclarations

    Example:
        >>> all_tools = [
        ...     ToolDeclaration(name="add", description="Add", parameters={}),
        ...     ToolDeclaration(name="multiply", description="Multiply", parameters={}),
        ...     ToolDeclaration(name="divide", description="Divide", parameters={})
        ... ]
        >>> filtered = filter_tools_by_name(all_tools, ["add", "divide"])
        >>> [t.name for t in filtered]
        ['add', 'divide']
    """
    tool_names_set = set(tool_names)
    return [decl for decl in declarations if decl.name in tool_names_set]


def merge_schema_properties(
    base_schema: dict[str, Any],
    additional_properties: dict[str, Any],
) -> dict[str, Any]:
    """Merge additional properties into a base parameter schema.

    This is useful for extending tool schemas with additional parameters.

    Args:
        base_schema: Base parameter schema
        additional_properties: Additional properties to add

    Returns:
        Merged schema

    Example:
        >>> base = {
        ...     "type": "object",
        ...     "properties": {"a": {"type": "integer"}},
        ...     "required": ["a"]
        ... }
        >>> additional = {"b": {"type": "string"}}
        >>> merged = merge_schema_properties(base, additional)
        >>> "b" in merged["properties"]
        True
    """
    # Create a copy to avoid modifying the original
    merged = base_schema.copy()

    # Ensure properties key exists
    if "properties" not in merged:
        merged["properties"] = {}

    # Merge properties
    merged["properties"] = {**merged["properties"], **additional_properties}

    return merged

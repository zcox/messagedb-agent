"""Tool registration system for the agent framework.

This module provides a registry for tools that can be executed by the agent,
along with utilities for defining tools with automatic schema generation.
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class ToolError(Exception):
    """Base exception for tool-related errors."""

    pass


class ToolNotFoundError(ToolError):
    """Raised when a tool is not found in the registry."""

    pass


class ToolRegistrationError(ToolError):
    """Raised when tool registration fails."""

    pass


@dataclass(frozen=True)
class Tool:
    """Represents a tool that can be executed by the agent.

    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description of what the tool does
        parameters_schema: JSON schema defining the tool's parameters
        function: The callable that implements the tool's functionality
    """

    name: str
    description: str
    parameters_schema: dict[str, Any]
    function: Callable[..., Any]

    def __post_init__(self) -> None:
        """Validate tool attributes."""
        if not self.name or not self.name.strip():
            raise ValueError("Tool name cannot be empty")
        if not self.description or not self.description.strip():
            raise ValueError("Tool description cannot be empty")
        if not callable(self.function):
            raise ValueError("Tool function must be callable")


class ToolRegistry:
    """Registry for managing tools available to the agent.

    The registry maintains a collection of tools that can be looked up by name
    and provides methods for registration and retrieval.

    Example:
        >>> registry = ToolRegistry()
        >>> def my_tool(x: int) -> int:
        ...     return x * 2
        >>> tool = Tool(
        ...     name="double",
        ...     description="Doubles a number",
        ...     parameters_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        ...     function=my_tool
        ... )
        >>> registry.register(tool)
        >>> result = registry.get("double")
    """

    def __init__(self) -> None:
        """Initialize an empty tool registry."""
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool in the registry.

        Args:
            tool: The tool to register

        Raises:
            ToolRegistrationError: If a tool with the same name already exists
        """
        if tool.name in self._tools:
            raise ToolRegistrationError(
                f"Tool '{tool.name}' is already registered. "
                f"Use a different name or unregister the existing tool first."
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Retrieve a tool by name.

        Args:
            name: The name of the tool to retrieve

        Returns:
            The requested tool

        Raises:
            ToolNotFoundError: If no tool with the given name exists
        """
        if name not in self._tools:
            raise ToolNotFoundError(
                f"Tool '{name}' not found in registry. "
                f"Available tools: {', '.join(self.list_names())}"
            )
        return self._tools[name]

    def has(self, name: str) -> bool:
        """Check if a tool exists in the registry.

        Args:
            name: The name of the tool to check

        Returns:
            True if the tool exists, False otherwise
        """
        return name in self._tools

    def list_names(self) -> list[str]:
        """Get a list of all registered tool names.

        Returns:
            List of tool names in registration order
        """
        return list(self._tools.keys())

    def list_tools(self) -> list[Tool]:
        """Get a list of all registered tools.

        Returns:
            List of Tool objects in registration order
        """
        return list(self._tools.values())

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: The name of the tool to remove

        Raises:
            ToolNotFoundError: If no tool with the given name exists
        """
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not found in registry")
        del self._tools[name]

    def clear(self) -> None:
        """Remove all tools from the registry."""
        self._tools.clear()

    def __len__(self) -> int:
        """Return the number of registered tools."""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if a tool exists using 'in' operator."""
        return name in self._tools


def _python_type_to_json_schema_type(py_type: type) -> str:
    """Convert Python type to JSON Schema type string.

    Args:
        py_type: Python type to convert

    Returns:
        JSON Schema type string
    """
    # Handle common types
    type_mapping = {
        int: "integer",
        float: "number",
        str: "string",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    # Get the origin type for generics (e.g., list[str] -> list)
    origin = getattr(py_type, "__origin__", None)
    if origin is not None:
        py_type = origin

    return type_mapping.get(py_type, "string")


def _extract_parameter_schema_from_function(func: Callable[..., Any]) -> dict[str, Any]:
    """Extract JSON Schema for function parameters from type hints.

    Args:
        func: Function to extract schema from

    Returns:
        JSON Schema object describing the function's parameters
    """
    sig = inspect.signature(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        # Skip self, cls, *args, **kwargs
        if param_name in ("self", "cls") or param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        # Determine type
        param_type = param.annotation
        if param_type == inspect.Parameter.empty:
            # No type hint, default to string
            json_type = "string"
        else:
            json_type = _python_type_to_json_schema_type(param_type)

        # Build property schema
        prop_schema: dict[str, Any] = {"type": json_type}

        # Extract description from docstring if available
        # (Simple implementation - could be enhanced with docstring parsing)
        properties[param_name] = prop_schema

        # Check if parameter is required (no default value)
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }

    if required:
        schema["required"] = required

    return schema


def tool(
    name: str | None = None,
    description: str | None = None,
    parameters_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to register a function as a tool.

    This decorator can be used to easily register functions as tools with
    automatic schema generation from type hints.

    Args:
        name: Tool name (defaults to function name)
        description: Tool description (defaults to function docstring)
        parameters_schema: Explicit parameter schema (auto-generated if not provided)

    Returns:
        Decorator function

    Example:
        >>> registry = ToolRegistry()
        >>> @tool(name="add", description="Add two numbers")
        ... def add_numbers(a: int, b: int) -> int:
        ...     '''Add two numbers together.'''
        ...     return a + b
        >>> # Function is decorated but not automatically registered
        >>> # You need to register it manually or use a registry-specific decorator

    Note:
        This decorator does NOT automatically register the tool. It attaches
        metadata to the function. Use register_tool() or create a custom
        decorator that registers to a specific registry.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        # Determine name
        tool_name = name if name is not None else func.__name__

        # Determine description
        tool_description = description
        if tool_description is None:
            tool_description = func.__doc__ or ""
            tool_description = tool_description.strip()
        if not tool_description:
            tool_description = f"Function {func.__name__}"

        # Determine schema
        tool_schema = parameters_schema
        if tool_schema is None:
            tool_schema = _extract_parameter_schema_from_function(func)

        # Attach metadata to function
        func._tool_metadata = Tool(  # type: ignore[attr-defined]
            name=tool_name,
            description=tool_description,
            parameters_schema=tool_schema,
            function=func,
        )

        return func

    return decorator


def register_tool(
    registry: ToolRegistry,
    name: str | None = None,
    description: str | None = None,
    parameters_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Create a decorator that registers tools to a specific registry.

    This is a convenience decorator factory that combines the @tool decorator
    with automatic registration to a specific registry.

    Args:
        registry: The ToolRegistry to register tools to
        name: Optional custom name for the tool
        description: Optional custom description for the tool
        parameters_schema: Optional custom parameter schema

    Returns:
        Decorator function that registers tools

    Example:
        >>> registry = ToolRegistry()
        >>> @register_tool(registry)
        ... def my_tool(x: int) -> int:
        ...     '''Double a number.'''
        ...     return x * 2
        >>> assert "my_tool" in registry
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        # Apply the tool decorator
        decorated = tool(name, description, parameters_schema)(func)

        # Register the tool
        tool_obj = decorated._tool_metadata  # type: ignore[attr-defined]
        registry.register(tool_obj)

        return decorated

    return decorator


def get_tool_metadata(func: Callable[..., Any]) -> Tool | None:
    """Extract tool metadata from a decorated function.

    Args:
        func: Function to extract metadata from

    Returns:
        Tool object if function was decorated with @tool, None otherwise
    """
    return getattr(func, "_tool_metadata", None)

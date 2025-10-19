"""Tool execution framework for the agent system.

This module provides functionality for executing registered tools with
proper error handling, timing, and result wrapping.
"""

import time
from dataclasses import dataclass
from typing import Any

from messagedb_agent.tools.registry import ToolRegistry


class ToolExecutionError(Exception):
    """Base exception for tool execution errors."""

    pass


class ToolExecutionTimeoutError(ToolExecutionError):
    """Raised when a tool execution times out."""

    pass


@dataclass(frozen=True)
class ToolExecutionResult:
    """Result of a tool execution.

    Attributes:
        success: Whether the execution succeeded
        result: The result value if successful, None if failed
        error: Error message if failed, None if successful
        execution_time_ms: Execution time in milliseconds
        tool_name: Name of the tool that was executed
    """

    success: bool
    result: Any
    error: str | None
    execution_time_ms: float
    tool_name: str

    def __post_init__(self) -> None:
        """Validate execution result attributes."""
        if self.execution_time_ms < 0:
            raise ValueError("Execution time cannot be negative")
        if not self.tool_name or not self.tool_name.strip():
            raise ValueError("Tool name cannot be empty")
        if self.success and self.error is not None:
            raise ValueError("Success result cannot have an error message")
        if not self.success and self.error is None:
            raise ValueError("Failed result must have an error message")


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
    registry: ToolRegistry,
) -> ToolExecutionResult:
    """Execute a tool from the registry with the given arguments.

    This function looks up the tool by name, executes it with the provided
    arguments, and returns a result object containing the outcome and timing
    information.

    Args:
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments to pass to the tool
        registry: ToolRegistry containing the tool

    Returns:
        ToolExecutionResult with success status, result/error, and timing

    Example:
        >>> registry = ToolRegistry()
        >>> @register_tool(registry)
        ... def add(a: int, b: int) -> int:
        ...     return a + b
        >>> result = execute_tool("add", {"a": 5, "b": 3}, registry)
        >>> result.success
        True
        >>> result.result
        8
    """
    start_time = time.perf_counter()

    try:
        # Look up the tool in the registry
        tool = registry.get(tool_name)

        # Execute the tool function with the arguments
        result = tool.function(**arguments)

        # Calculate execution time
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000

        return ToolExecutionResult(
            success=True,
            result=result,
            error=None,
            execution_time_ms=execution_time_ms,
            tool_name=tool_name,
        )

    except Exception as e:
        # Calculate execution time even on failure
        end_time = time.perf_counter()
        execution_time_ms = (end_time - start_time) * 1000

        # Format error message with exception type and message
        error_type = type(e).__name__
        error_message = str(e)
        full_error = f"{error_type}: {error_message}" if error_message else error_type

        return ToolExecutionResult(
            success=False,
            result=None,
            error=full_error,
            execution_time_ms=execution_time_ms,
            tool_name=tool_name,
        )


def execute_tool_safe(
    tool_name: str,
    arguments: dict[str, Any],
    registry: ToolRegistry,
) -> tuple[Any, str | None]:
    """Execute a tool and return result and error as a simple tuple.

    This is a convenience wrapper around execute_tool() for cases where
    you just need the result and error without the full metadata.

    Args:
        tool_name: Name of the tool to execute
        arguments: Dictionary of arguments to pass to the tool
        registry: ToolRegistry containing the tool

    Returns:
        Tuple of (result, error) where:
        - result is the tool's return value if successful, None if failed
        - error is the error message if failed, None if successful

    Example:
        >>> result, error = execute_tool_safe("add", {"a": 5, "b": 3}, registry)
        >>> if error is None:
        ...     print(f"Result: {result}")
        ... else:
        ...     print(f"Error: {error}")
    """
    execution_result = execute_tool(tool_name, arguments, registry)
    return execution_result.result, execution_result.error


def batch_execute_tools(
    tool_calls: list[dict[str, Any]],
    registry: ToolRegistry,
) -> list[ToolExecutionResult]:
    """Execute multiple tool calls in sequence.

    Each tool call should be a dict with 'name' and 'arguments' keys.

    Args:
        tool_calls: List of tool call dicts with 'name' and 'arguments'
        registry: ToolRegistry containing the tools

    Returns:
        List of ToolExecutionResult objects, one per tool call

    Example:
        >>> calls = [
        ...     {"name": "add", "arguments": {"a": 1, "b": 2}},
        ...     {"name": "multiply", "arguments": {"a": 3, "b": 4}}
        ... ]
        >>> results = batch_execute_tools(calls, registry)
    """
    results: list[ToolExecutionResult] = []

    for tool_call in tool_calls:
        tool_name = tool_call.get("name", "")
        arguments = tool_call.get("arguments", {})

        if not tool_name:
            # Create a failure result for missing tool name
            results.append(
                ToolExecutionResult(
                    success=False,
                    result=None,
                    error="Missing tool name in tool call",
                    execution_time_ms=0.0,
                    tool_name="<unknown>",
                )
            )
            continue

        result = execute_tool(tool_name, arguments, registry)
        results.append(result)

    return results

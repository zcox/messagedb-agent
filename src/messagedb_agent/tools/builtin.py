"""Built-in tools for the agent system.

This module provides a set of example and utility tools that can be used
by agents out of the box.
"""

import ast
import operator
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


def get_current_time(timezone_name: str = "UTC") -> str:
    """Get the current date and time.

    Args:
        timezone_name: Timezone name (default: UTC). For basic implementation,
                      only UTC is supported.

    Returns:
        ISO 8601 formatted datetime string

    Example:
        >>> time = get_current_time()
        >>> # Returns something like: "2025-10-19T14:30:00.123456+00:00"
    """
    if timezone_name != "UTC":
        raise ValueError(
            f"Timezone '{timezone_name}' not supported. "
            f"Only UTC is supported in basic implementation."
        )

    now = datetime.now(UTC)
    return now.isoformat()


def echo(message: str) -> str:
    """Echo a message back.

    This is primarily useful for testing and debugging.

    Args:
        message: The message to echo back

    Returns:
        The same message that was provided

    Example:
        >>> echo("Hello, World!")
        'Hello, World!'
    """
    return message


# Safe operators for mathematical expressions
_SAFE_OPERATORS: dict[type[ast.operator] | type[ast.unaryop], Callable[..., Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluate_node(node: ast.AST) -> float:
    """Evaluate an AST node safely.

    Args:
        node: AST node to evaluate

    Returns:
        Numerical result of the evaluation

    Raises:
        ValueError: If the expression contains unsafe operations
        ZeroDivisionError: If division by zero occurs
    """
    if isinstance(node, ast.Constant):
        # Python 3.8+ uses ast.Constant for numbers
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        # Binary operation (e.g., 1 + 2, 3 * 4)
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported operation: {op_type.__name__}")

        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        op_func = _SAFE_OPERATORS[op_type]

        # Special handling for division by zero
        if op_type in (ast.Div, ast.FloorDiv, ast.Mod) and right == 0:
            raise ZeroDivisionError("Division by zero")

        return float(op_func(left, right))

    if isinstance(node, ast.UnaryOp):
        # Unary operation (e.g., -5, +3)
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Unsupported operation: {op_type.__name__}")

        operand = _evaluate_node(node.operand)
        op_func = _SAFE_OPERATORS[op_type]
        return float(op_func(operand))

    else:
        raise ValueError(f"Unsupported expression type: {type(node).__name__}")


def calculate(expression: str) -> float:
    """Safely evaluate a mathematical expression.

    This function parses and evaluates simple mathematical expressions using
    Python's AST module. Only basic arithmetic operations are supported:
    addition (+), subtraction (-), multiplication (*), division (/),
    floor division (//), modulo (%), power (**), and unary operators (+, -).

    Security: This function does NOT use eval() and only supports a limited
    set of safe mathematical operations. Function calls, variable access,
    and other potentially dangerous operations are not allowed.

    Args:
        expression: Mathematical expression as a string

    Returns:
        The numerical result of the calculation

    Raises:
        ValueError: If the expression is invalid or contains unsafe operations
        ZeroDivisionError: If division by zero occurs

    Examples:
        >>> calculate("2 + 3")
        5.0
        >>> calculate("10 * (5 - 2)")
        30.0
        >>> calculate("2 ** 8")
        256.0
        >>> calculate("-5 + 3")
        -2.0
    """
    if not expression or not expression.strip():
        raise ValueError("Expression cannot be empty")

    try:
        # Parse the expression into an AST
        tree = ast.parse(expression.strip(), mode="eval")

        # Evaluate the AST
        result = _evaluate_node(tree.body)

        return result

    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}") from e
    except Exception as e:
        # Re-raise known exceptions as-is
        if isinstance(e, (ValueError, ZeroDivisionError)):
            raise
        # Wrap unexpected exceptions
        raise ValueError(f"Error evaluating expression: {e}") from e


def get_builtin_tools() -> dict[str, Any]:
    """Get a dictionary of all built-in tools.

    Returns:
        Dictionary mapping tool names to tool functions

    Example:
        >>> tools = get_builtin_tools()
        >>> tools["echo"]("test")
        'test'
    """
    return {
        "get_current_time": get_current_time,
        "echo": echo,
        "calculate": calculate,
    }


def register_builtin_tools(registry: Any) -> None:
    """Register all built-in tools to a registry.

    Args:
        registry: ToolRegistry instance to register tools to

    Example:
        >>> from messagedb_agent.tools import ToolRegistry
        >>> registry = ToolRegistry()
        >>> register_builtin_tools(registry)
        >>> "echo" in registry
        True
    """
    from messagedb_agent.tools.registry import register_tool

    # Register get_current_time
    register_tool(
        registry,
        name="get_current_time",
        description="Get the current date and time in ISO 8601 format",
    )(get_current_time)

    # Register echo
    register_tool(
        registry,
        name="echo",
        description="Echo a message back (useful for testing)",
    )(echo)

    # Register calculate
    register_tool(
        registry,
        name="calculate",
        description="Safely evaluate a mathematical expression (supports +, -, *, /, //, %, **)",
    )(calculate)

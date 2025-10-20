"""Output formatting utilities for the CLI.

This module provides clean, formatted output functions for displaying
LLM responses, tool calls, and tool results to the user during execution.
"""

import json
from typing import Any


def print_separator(char: str = "=", width: int = 80) -> None:
    """Print a separator line.

    Args:
        char: Character to use for the separator
        width: Width of the separator line
    """
    print(char * width)


def print_section_header(title: str, width: int = 80) -> None:
    """Print a section header with a title.

    Args:
        title: Title text to display
        width: Total width of the header
    """
    print()
    print_separator("=", width)
    print(title)
    print_separator("=", width)


def print_subsection_header(title: str, width: int = 80) -> None:
    """Print a subsection header with a title.

    Args:
        title: Title text to display
        width: Total width of the header
    """
    print()
    print_separator("-", width)
    print(title)
    print_separator("-", width)


def print_llm_text_response(text: str, model_name: str) -> None:
    """Print an LLM text response in a clear, formatted way.

    Args:
        text: The response text from the LLM
        model_name: Name of the model that generated the response
    """
    print_subsection_header(f"LLM Response ({model_name})")
    print(text)
    print()


def print_tool_call(tool_call_id: str, tool_name: str, arguments: dict[str, Any]) -> None:
    """Print a tool call in a clear, formatted way.

    Args:
        tool_call_id: Unique identifier for the tool call
        tool_name: Name of the tool being called
        arguments: Arguments passed to the tool
    """
    print_subsection_header(f"Tool Call: {tool_name}")
    print(f"ID: {tool_call_id}")
    print("Arguments:")
    # Pretty-print the arguments as JSON with indentation
    print(json.dumps(arguments, indent=2))
    print()


def print_tool_result(
    tool_name: str,
    success: bool,
    result: Any = None,
    error: str | None = None,
    execution_time_ms: float | None = None,
) -> None:
    """Print a tool execution result in a clear, formatted way.

    Args:
        tool_name: Name of the tool that was executed
        success: Whether the tool execution succeeded
        result: The result value (if successful)
        error: Error message (if failed)
        execution_time_ms: Execution time in milliseconds
    """
    status = "SUCCESS" if success else "FAILED"
    print_subsection_header(f"Tool Result: {tool_name} [{status}]")

    if execution_time_ms is not None:
        print(f"Execution time: {execution_time_ms:.2f}ms")

    if success and result is not None:
        print("Result:")
        # Pretty-print the result
        if isinstance(result, (dict, list)):
            print(json.dumps(result, indent=2))
        else:
            print(result)
    elif not success and error:
        print(f"Error: {error}")

    print()


def print_llm_response_summary(
    text_length: int,
    tool_call_count: int,
    model_name: str,
    token_usage: dict[str, Any] | None = None,
) -> None:
    """Print a summary of an LLM response.

    Args:
        text_length: Length of the response text
        tool_call_count: Number of tool calls in the response
        model_name: Name of the model
        token_usage: Token usage information (if available)
    """
    print("LLM Response Summary:")
    print(f"  Model: {model_name}")
    print(f"  Text length: {text_length} characters")
    print(f"  Tool calls: {tool_call_count}")

    if token_usage:
        print("  Token usage:")
        for key, value in token_usage.items():
            print(f"    {key}: {value}")
    print()

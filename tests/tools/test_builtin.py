"""Tests for built-in tools."""

from datetime import UTC, datetime

import pytest

from messagedb_agent.tools import (
    ToolRegistry,
    calculate,
    echo,
    get_builtin_tools,
    get_current_time,
    register_builtin_tools,
)


# get_current_time tests
class TestGetCurrentTime:
    """Tests for the get_current_time tool."""

    def test_returns_iso_format(self):
        """Test that get_current_time returns ISO 8601 format."""
        result = get_current_time()

        # Should be parseable as ISO format
        parsed = datetime.fromisoformat(result)
        assert isinstance(parsed, datetime)

    def test_returns_utc_timezone(self):
        """Test that get_current_time returns UTC timezone."""
        result = get_current_time()

        parsed = datetime.fromisoformat(result)
        # Should have timezone info
        assert parsed.tzinfo is not None
        # Should be UTC (offset +00:00)
        assert parsed.utcoffset().total_seconds() == 0

    def test_default_timezone_is_utc(self):
        """Test that default timezone is UTC."""
        result = get_current_time()
        assert "+00:00" in result or "Z" in result.replace("+00:00", "Z")

    def test_explicit_utc_timezone(self):
        """Test explicitly requesting UTC timezone."""
        result = get_current_time(timezone_name="UTC")
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None

    def test_non_utc_timezone_raises_error(self):
        """Test that non-UTC timezones raise an error."""
        with pytest.raises(ValueError, match="not supported"):
            get_current_time(timezone_name="America/New_York")

    def test_result_is_recent(self):
        """Test that returned time is recent (within last second)."""
        before = datetime.now(UTC)
        result = get_current_time()
        after = datetime.now(UTC)

        parsed = datetime.fromisoformat(result)
        # Should be between before and after
        assert before <= parsed <= after

    def test_includes_microseconds(self):
        """Test that result includes microseconds."""
        result = get_current_time()
        # ISO format with microseconds has a dot before the timezone
        assert "." in result or "," in result  # Some locales use comma


# echo tests
class TestEcho:
    """Tests for the echo tool."""

    def test_echo_simple_string(self):
        """Test echoing a simple string."""
        result = echo("Hello, World!")
        assert result == "Hello, World!"

    def test_echo_empty_string(self):
        """Test echoing an empty string."""
        result = echo("")
        assert result == ""

    def test_echo_multiline_string(self):
        """Test echoing a multiline string."""
        message = "Line 1\nLine 2\nLine 3"
        result = echo(message)
        assert result == message

    def test_echo_special_characters(self):
        """Test echoing special characters."""
        message = "!@#$%^&*()_+-={}[]|\\:;\"'<>,.?/"
        result = echo(message)
        assert result == message

    def test_echo_unicode(self):
        """Test echoing unicode characters."""
        message = "Hello 世界 🌍"
        result = echo(message)
        assert result == message

    def test_echo_whitespace(self):
        """Test echoing whitespace."""
        message = "   \t\n   "
        result = echo(message)
        assert result == message

    def test_echo_long_string(self):
        """Test echoing a long string."""
        message = "a" * 10000
        result = echo(message)
        assert result == message


# calculate tests
class TestCalculate:
    """Tests for the calculate tool."""

    def test_simple_addition(self):
        """Test simple addition."""
        assert calculate("2 + 3") == 5.0

    def test_simple_subtraction(self):
        """Test simple subtraction."""
        assert calculate("10 - 3") == 7.0

    def test_simple_multiplication(self):
        """Test simple multiplication."""
        assert calculate("4 * 5") == 20.0

    def test_simple_division(self):
        """Test simple division."""
        assert calculate("15 / 3") == 5.0

    def test_floor_division(self):
        """Test floor division."""
        assert calculate("17 // 5") == 3.0

    def test_modulo(self):
        """Test modulo operation."""
        assert calculate("17 % 5") == 2.0

    def test_power(self):
        """Test power operation."""
        assert calculate("2 ** 8") == 256.0

    def test_negative_number(self):
        """Test unary minus."""
        assert calculate("-5") == -5.0

    def test_positive_number(self):
        """Test unary plus."""
        assert calculate("+5") == 5.0

    def test_complex_expression(self):
        """Test complex expression with multiple operations."""
        assert calculate("(2 + 3) * 4") == 20.0

    def test_nested_parentheses(self):
        """Test nested parentheses."""
        assert calculate("((2 + 3) * (4 - 1))") == 15.0

    def test_operator_precedence(self):
        """Test operator precedence."""
        assert calculate("2 + 3 * 4") == 14.0

    def test_float_numbers(self):
        """Test floating point numbers."""
        result = calculate("3.5 + 2.5")
        assert result == 6.0

    def test_negative_expression(self):
        """Test negative expression."""
        assert calculate("-5 + 3") == -2.0

    def test_division_by_zero_raises_error(self):
        """Test that division by zero raises ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError, match="Division by zero"):
            calculate("10 / 0")

    def test_floor_division_by_zero_raises_error(self):
        """Test that floor division by zero raises ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError, match="Division by zero"):
            calculate("10 // 0")

    def test_modulo_by_zero_raises_error(self):
        """Test that modulo by zero raises ZeroDivisionError."""
        with pytest.raises(ZeroDivisionError, match="Division by zero"):
            calculate("10 % 0")

    def test_empty_expression_raises_error(self):
        """Test that empty expression raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            calculate("")

    def test_whitespace_only_expression_raises_error(self):
        """Test that whitespace-only expression raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            calculate("   ")

    def test_invalid_syntax_raises_error(self):
        """Test that invalid syntax raises ValueError."""
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            calculate("2 +")

    def test_variable_access_raises_error(self):
        """Test that variable access is not allowed."""
        with pytest.raises(ValueError, match="Unsupported expression type"):
            calculate("x + 5")

    def test_function_call_raises_error(self):
        """Test that function calls are not allowed."""
        with pytest.raises(ValueError, match="Unsupported expression type"):
            calculate("abs(-5)")

    def test_string_expression_raises_error(self):
        """Test that string expressions are not allowed."""
        with pytest.raises(ValueError, match="Unsupported constant type"):
            calculate("'hello'")

    def test_whitespace_in_expression(self):
        """Test that whitespace is handled correctly."""
        assert calculate("  2  +  3  ") == 5.0

    def test_very_long_expression(self):
        """Test a very long expression."""
        # 1 + 1 + 1 + ... (100 times)
        expr = " + ".join(["1"] * 100)
        assert calculate(expr) == 100.0

    def test_large_power(self):
        """Test large power calculation."""
        assert calculate("10 ** 6") == 1000000.0

    def test_mixed_operations(self):
        """Test mixed operations."""
        assert calculate("2 * 3 + 4 / 2 - 1") == 7.0


# get_builtin_tools tests
class TestGetBuiltinTools:
    """Tests for the get_builtin_tools function."""

    def test_returns_dict(self):
        """Test that get_builtin_tools returns a dictionary."""
        tools = get_builtin_tools()
        assert isinstance(tools, dict)

    def test_contains_all_tools(self):
        """Test that all expected tools are present."""
        tools = get_builtin_tools()
        assert "get_current_time" in tools
        assert "echo" in tools
        assert "calculate" in tools

    def test_all_values_are_callable(self):
        """Test that all tools are callable."""
        tools = get_builtin_tools()
        for tool_func in tools.values():
            assert callable(tool_func)

    def test_tools_are_correct_functions(self):
        """Test that tools map to correct functions."""
        tools = get_builtin_tools()
        assert tools["get_current_time"] is get_current_time
        assert tools["echo"] is echo
        assert tools["calculate"] is calculate

    def test_can_call_tools_from_dict(self):
        """Test that tools can be called from the dictionary."""
        tools = get_builtin_tools()
        assert tools["echo"]("test") == "test"
        assert tools["calculate"]("2 + 2") == 4.0


# register_builtin_tools tests
class TestRegisterBuiltinTools:
    """Tests for the register_builtin_tools function."""

    def test_registers_all_tools(self):
        """Test that all builtin tools are registered."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        assert "get_current_time" in registry
        assert "echo" in registry
        assert "calculate" in registry

    def test_registered_tools_are_callable(self):
        """Test that registered tools can be executed."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        time_tool = registry.get("get_current_time")
        echo_tool = registry.get("echo")
        calc_tool = registry.get("calculate")

        assert callable(time_tool.function)
        assert callable(echo_tool.function)
        assert callable(calc_tool.function)

    def test_registered_tools_have_descriptions(self):
        """Test that registered tools have descriptions."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        for tool_name in ["get_current_time", "echo", "calculate"]:
            tool = registry.get(tool_name)
            assert tool.description
            assert len(tool.description) > 0

    def test_registered_tools_have_schemas(self):
        """Test that registered tools have parameter schemas."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        for tool_name in ["get_current_time", "echo", "calculate"]:
            tool = registry.get(tool_name)
            assert isinstance(tool.parameters_schema, dict)
            assert "type" in tool.parameters_schema

    def test_can_execute_registered_tools(self):
        """Test that registered tools can be executed successfully."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        echo_tool = registry.get("echo")
        result = echo_tool.function("Hello!")
        assert result == "Hello!"

        calc_tool = registry.get("calculate")
        result = calc_tool.function("10 + 5")
        assert result == 15.0


# Integration tests
class TestBuiltinToolsIntegration:
    """Integration tests for builtin tools."""

    def test_end_to_end_workflow(self):
        """Test complete workflow with builtin tools."""
        # Create registry
        registry = ToolRegistry()

        # Register builtin tools
        register_builtin_tools(registry)

        # Verify all tools are available
        assert len(registry) == 3

        # Execute each tool
        time_result = registry.get("get_current_time").function()
        assert isinstance(time_result, str)

        echo_result = registry.get("echo").function("test")
        assert echo_result == "test"

        calc_result = registry.get("calculate").function("5 * 5")
        assert calc_result == 25.0

    def test_with_tool_executor(self):
        """Test builtin tools with the executor framework."""
        from messagedb_agent.tools import execute_tool

        registry = ToolRegistry()
        register_builtin_tools(registry)

        # Execute echo
        result = execute_tool("echo", {"message": "Hello!"}, registry)
        assert result.success is True
        assert result.result == "Hello!"

        # Execute calculate
        result = execute_tool("calculate", {"expression": "100 / 4"}, registry)
        assert result.success is True
        assert result.result == 25.0

    def test_error_handling_with_executor(self):
        """Test that errors are properly handled with executor."""
        from messagedb_agent.tools import execute_tool

        registry = ToolRegistry()
        register_builtin_tools(registry)

        # Division by zero
        result = execute_tool("calculate", {"expression": "1 / 0"}, registry)
        assert result.success is False
        assert "ZeroDivisionError" in result.error

        # Invalid expression
        result = execute_tool("calculate", {"expression": "invalid"}, registry)
        assert result.success is False
        assert "ValueError" in result.error

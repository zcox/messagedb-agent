"""Tests for the tool execution framework."""

import time

import pytest

from messagedb_agent.tools import (
    ToolExecutionError,
    ToolExecutionResult,
    ToolRegistry,
    batch_execute_tools,
    execute_tool,
    execute_tool_safe,
    register_tool,
)


# Test fixtures
@pytest.fixture
def registry():
    """Create a fresh tool registry with sample tools."""
    reg = ToolRegistry()

    @register_tool(reg)
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @register_tool(reg)
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    @register_tool(reg)
    def echo(message: str) -> str:
        """Echo a message."""
        return message

    @register_tool(reg)
    def divide(a: float, b: float) -> float:
        """Divide two numbers."""
        if b == 0:
            raise ValueError("Division by zero")
        return a / b

    @register_tool(reg)
    def slow_operation() -> str:
        """A slow operation for timing tests."""
        time.sleep(0.1)
        return "done"

    @register_tool(reg)
    def raise_error() -> None:
        """Always raises an error."""
        raise RuntimeError("This tool always fails")

    @register_tool(reg)
    def no_args() -> str:
        """Tool with no arguments."""
        return "success"

    @register_tool(reg)
    def complex_args(items: list, config: dict) -> dict:
        """Tool with complex arguments."""
        return {"items": items, "config": config}

    return reg


# ToolExecutionResult tests
class TestToolExecutionResult:
    """Tests for the ToolExecutionResult dataclass."""

    def test_create_success_result(self):
        """Test creating a successful execution result."""
        result = ToolExecutionResult(
            success=True,
            result=42,
            error=None,
            execution_time_ms=10.5,
            tool_name="test_tool",
        )
        assert result.success is True
        assert result.result == 42
        assert result.error is None
        assert result.execution_time_ms == 10.5
        assert result.tool_name == "test_tool"

    def test_create_failure_result(self):
        """Test creating a failed execution result."""
        result = ToolExecutionResult(
            success=False,
            result=None,
            error="Something went wrong",
            execution_time_ms=5.0,
            tool_name="test_tool",
        )
        assert result.success is False
        assert result.result is None
        assert result.error == "Something went wrong"
        assert result.execution_time_ms == 5.0

    def test_result_is_frozen(self):
        """Test that ToolExecutionResult is immutable."""
        result = ToolExecutionResult(
            success=True,
            result=42,
            error=None,
            execution_time_ms=10.0,
            tool_name="test",
        )
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore

    def test_validates_negative_execution_time(self):
        """Test that negative execution time raises error."""
        with pytest.raises(ValueError, match="Execution time cannot be negative"):
            ToolExecutionResult(
                success=True,
                result=42,
                error=None,
                execution_time_ms=-1.0,
                tool_name="test",
            )

    def test_validates_empty_tool_name(self):
        """Test that empty tool name raises error."""
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            ToolExecutionResult(
                success=True,
                result=42,
                error=None,
                execution_time_ms=10.0,
                tool_name="",
            )

    def test_validates_success_with_error(self):
        """Test that success result cannot have error message."""
        with pytest.raises(ValueError, match="Success result cannot have an error message"):
            ToolExecutionResult(
                success=True,
                result=42,
                error="This shouldn't be here",
                execution_time_ms=10.0,
                tool_name="test",
            )

    def test_validates_failure_without_error(self):
        """Test that failure result must have error message."""
        with pytest.raises(ValueError, match="Failed result must have an error message"):
            ToolExecutionResult(
                success=False,
                result=None,
                error=None,
                execution_time_ms=10.0,
                tool_name="test",
            )


# execute_tool tests
class TestExecuteTool:
    """Tests for the execute_tool function."""

    def test_execute_simple_tool_success(self, registry):
        """Test executing a simple tool successfully."""
        result = execute_tool("add", {"a": 5, "b": 3}, registry)

        assert result.success is True
        assert result.result == 8
        assert result.error is None
        assert result.execution_time_ms >= 0
        assert result.tool_name == "add"

    def test_execute_tool_with_string_args(self, registry):
        """Test executing a tool with string arguments."""
        result = execute_tool("echo", {"message": "Hello, World!"}, registry)

        assert result.success is True
        assert result.result == "Hello, World!"
        assert result.error is None

    def test_execute_tool_with_no_args(self, registry):
        """Test executing a tool with no arguments."""
        result = execute_tool("no_args", {}, registry)

        assert result.success is True
        assert result.result == "success"
        assert result.error is None

    def test_execute_tool_with_complex_args(self, registry):
        """Test executing a tool with complex arguments."""
        items = [1, 2, 3]
        config = {"key": "value", "nested": {"data": 42}}
        result = execute_tool("complex_args", {"items": items, "config": config}, registry)

        assert result.success is True
        assert result.result == {"items": items, "config": config}

    def test_execute_tool_not_found(self, registry):
        """Test executing a non-existent tool."""
        result = execute_tool("nonexistent", {}, registry)

        assert result.success is False
        assert result.result is None
        assert result.error is not None
        assert "ToolNotFoundError" in result.error
        assert "nonexistent" in result.error

    def test_execute_tool_with_missing_argument(self, registry):
        """Test executing a tool with missing required argument."""
        result = execute_tool("add", {"a": 5}, registry)

        assert result.success is False
        assert result.result is None
        assert result.error is not None
        assert "TypeError" in result.error

    def test_execute_tool_with_extra_arguments(self, registry):
        """Test executing a tool with extra arguments."""
        result = execute_tool("add", {"a": 5, "b": 3, "c": 7}, registry)

        # Python raises TypeError for unexpected keyword arguments
        assert result.success is False
        assert result.error is not None
        assert "TypeError" in result.error
        assert "unexpected keyword argument" in result.error

    def test_execute_tool_with_wrong_argument_type(self, registry):
        """Test executing a tool with wrong argument types."""
        # Python doesn't enforce type hints at runtime, so this might succeed
        # depending on the operation
        result = execute_tool("add", {"a": "5", "b": "3"}, registry)

        # String concatenation will work, but might not be what we want
        # This is expected behavior for basic implementation
        assert result.success is True

    def test_execute_tool_that_raises_exception(self, registry):
        """Test executing a tool that raises an exception."""
        result = execute_tool("raise_error", {}, registry)

        assert result.success is False
        assert result.result is None
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "always fails" in result.error

    def test_execute_tool_with_custom_exception(self, registry):
        """Test executing a tool that raises a specific exception."""
        result = execute_tool("divide", {"a": 10.0, "b": 0.0}, registry)

        assert result.success is False
        assert result.result is None
        assert result.error is not None
        assert "ValueError" in result.error
        assert "Division by zero" in result.error

    def test_execution_time_tracking(self, registry):
        """Test that execution time is tracked correctly."""
        result = execute_tool("slow_operation", {}, registry)

        assert result.success is True
        # Should take at least 100ms (0.1 seconds)
        assert result.execution_time_ms >= 100
        # But not too much longer (allow 50ms overhead)
        assert result.execution_time_ms < 200

    def test_execution_time_tracked_on_failure(self, registry):
        """Test that execution time is tracked even on failure."""
        result = execute_tool("raise_error", {}, registry)

        assert result.success is False
        assert result.execution_time_ms >= 0
        # Should be very fast since it just raises an error
        assert result.execution_time_ms < 100

    def test_multiple_executions_independent(self, registry):
        """Test that multiple executions don't interfere with each other."""
        result1 = execute_tool("add", {"a": 1, "b": 2}, registry)
        result2 = execute_tool("multiply", {"a": 3, "b": 4}, registry)
        result3 = execute_tool("add", {"a": 10, "b": 20}, registry)

        assert result1.result == 3
        assert result2.result == 12
        assert result3.result == 30


# execute_tool_safe tests
class TestExecuteToolSafe:
    """Tests for the execute_tool_safe convenience function."""

    def test_execute_tool_safe_success(self, registry):
        """Test execute_tool_safe with successful execution."""
        result, error = execute_tool_safe("add", {"a": 5, "b": 3}, registry)

        assert result == 8
        assert error is None

    def test_execute_tool_safe_failure(self, registry):
        """Test execute_tool_safe with failed execution."""
        result, error = execute_tool_safe("raise_error", {}, registry)

        assert result is None
        assert error is not None
        assert "RuntimeError" in error

    def test_execute_tool_safe_usage_pattern(self, registry):
        """Test typical usage pattern with execute_tool_safe."""
        result, error = execute_tool_safe("divide", {"a": 10.0, "b": 2.0}, registry)

        if error is None:
            assert result == 5.0
        else:
            pytest.fail("Should not have error")

    def test_execute_tool_safe_error_handling_pattern(self, registry):
        """Test error handling pattern with execute_tool_safe."""
        result, error = execute_tool_safe("divide", {"a": 10.0, "b": 0.0}, registry)

        if error is not None:
            assert result is None
            assert "Division by zero" in error
        else:
            pytest.fail("Should have error")


# batch_execute_tools tests
class TestBatchExecuteTools:
    """Tests for the batch_execute_tools function."""

    def test_batch_execute_empty_list(self, registry):
        """Test batch execution with empty list."""
        results = batch_execute_tools([], registry)

        assert results == []

    def test_batch_execute_single_tool(self, registry):
        """Test batch execution with single tool."""
        calls = [{"name": "add", "arguments": {"a": 1, "b": 2}}]
        results = batch_execute_tools(calls, registry)

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].result == 3

    def test_batch_execute_multiple_tools(self, registry):
        """Test batch execution with multiple tools."""
        calls = [
            {"name": "add", "arguments": {"a": 1, "b": 2}},
            {"name": "multiply", "arguments": {"a": 3, "b": 4}},
            {"name": "echo", "arguments": {"message": "test"}},
        ]
        results = batch_execute_tools(calls, registry)

        assert len(results) == 3
        assert results[0].result == 3
        assert results[1].result == 12
        assert results[2].result == "test"
        assert all(r.success for r in results)

    def test_batch_execute_with_failures(self, registry):
        """Test batch execution with some failures."""
        calls = [
            {"name": "add", "arguments": {"a": 1, "b": 2}},
            {"name": "raise_error", "arguments": {}},
            {"name": "multiply", "arguments": {"a": 3, "b": 4}},
        ]
        results = batch_execute_tools(calls, registry)

        assert len(results) == 3
        assert results[0].success is True
        assert results[0].result == 3
        assert results[1].success is False
        assert results[1].error is not None
        assert results[2].success is True
        assert results[2].result == 12

    def test_batch_execute_continues_after_failure(self, registry):
        """Test that batch execution continues after a failure."""
        calls = [
            {"name": "raise_error", "arguments": {}},
            {"name": "add", "arguments": {"a": 5, "b": 3}},
        ]
        results = batch_execute_tools(calls, registry)

        # Both should be executed despite first one failing
        assert len(results) == 2
        assert results[0].success is False
        assert results[1].success is True
        assert results[1].result == 8

    def test_batch_execute_missing_tool_name(self, registry):
        """Test batch execution with missing tool name."""
        calls = [
            {"arguments": {"a": 1, "b": 2}},  # Missing 'name'
            {"name": "add", "arguments": {"a": 5, "b": 3}},
        ]
        results = batch_execute_tools(calls, registry)

        assert len(results) == 2
        assert results[0].success is False
        assert "Missing tool name" in results[0].error
        assert results[1].success is True

    def test_batch_execute_missing_arguments(self, registry):
        """Test batch execution with missing arguments key."""
        calls = [
            {"name": "no_args"},  # Missing 'arguments' key
        ]
        results = batch_execute_tools(calls, registry)

        assert len(results) == 1
        assert results[0].success is True  # no_args doesn't need arguments

    def test_batch_execute_preserves_order(self, registry):
        """Test that batch execution preserves call order."""
        calls = [
            {"name": "echo", "arguments": {"message": "first"}},
            {"name": "echo", "arguments": {"message": "second"}},
            {"name": "echo", "arguments": {"message": "third"}},
        ]
        results = batch_execute_tools(calls, registry)

        assert len(results) == 3
        assert results[0].result == "first"
        assert results[1].result == "second"
        assert results[2].result == "third"


# Integration tests
class TestToolExecutionIntegration:
    """Integration tests for tool execution."""

    def test_full_execution_workflow(self, registry):
        """Test complete workflow from registration to execution."""
        # Tool is already registered in fixture
        result = execute_tool("add", {"a": 10, "b": 20}, registry)

        assert result.success is True
        assert result.result == 30
        assert result.error is None
        assert result.execution_time_ms >= 0
        assert result.tool_name == "add"

    def test_execution_with_result_inspection(self, registry):
        """Test inspecting execution result properties."""
        result = execute_tool("multiply", {"a": 7, "b": 6}, registry)

        # All expected properties should be present
        assert hasattr(result, "success")
        assert hasattr(result, "result")
        assert hasattr(result, "error")
        assert hasattr(result, "execution_time_ms")
        assert hasattr(result, "tool_name")

    def test_error_message_formatting(self, registry):
        """Test that error messages are properly formatted."""
        result = execute_tool("divide", {"a": 10.0, "b": 0.0}, registry)

        # Should include exception type and message
        assert "ValueError" in result.error
        assert "Division by zero" in result.error
        assert ":" in result.error  # Format is "Type: message"


# Error handling tests
class TestErrorHandling:
    """Tests for error handling in tool execution."""

    def test_tool_execution_error_inheritance(self):
        """Test that ToolExecutionError inherits from Exception."""
        assert issubclass(ToolExecutionError, Exception)

    def test_registry_error_caught_and_wrapped(self, registry):
        """Test that registry errors are caught and wrapped in result."""
        result = execute_tool("nonexistent_tool", {}, registry)

        # Should not raise, but return failed result
        assert result.success is False
        assert "ToolNotFoundError" in result.error

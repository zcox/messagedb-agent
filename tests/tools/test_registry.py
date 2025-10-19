"""Tests for the tool registry system."""

import pytest

from messagedb_agent.tools import (
    Tool,
    ToolError,
    ToolNotFoundError,
    ToolRegistrationError,
    ToolRegistry,
    get_tool_metadata,
    register_tool,
    tool,
)


# Test fixtures
@pytest.fixture
def sample_function():
    """Sample function for testing."""

    def add(a: int, b: int) -> int:
        """Add two numbers together."""
        return a + b

    return add


@pytest.fixture
def sample_tool(sample_function):
    """Sample tool for testing."""
    return Tool(
        name="add",
        description="Add two numbers",
        parameters_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
        function=sample_function,
    )


@pytest.fixture
def registry():
    """Create a fresh tool registry for each test."""
    return ToolRegistry()


# Tool dataclass tests
class TestTool:
    """Tests for the Tool dataclass."""

    def test_tool_creation(self, sample_function):
        """Test creating a valid tool."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            parameters_schema={"type": "object"},
            function=sample_function,
        )
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.parameters_schema == {"type": "object"}
        assert tool.function == sample_function

    def test_tool_is_frozen(self, sample_tool):
        """Test that Tool instances are immutable."""
        with pytest.raises(AttributeError):
            sample_tool.name = "new_name"  # type: ignore

    def test_tool_empty_name_raises_error(self, sample_function):
        """Test that empty tool name raises ValueError."""
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            Tool(
                name="",
                description="Test",
                parameters_schema={},
                function=sample_function,
            )

    def test_tool_whitespace_name_raises_error(self, sample_function):
        """Test that whitespace-only tool name raises ValueError."""
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            Tool(
                name="   ",
                description="Test",
                parameters_schema={},
                function=sample_function,
            )

    def test_tool_empty_description_raises_error(self, sample_function):
        """Test that empty description raises ValueError."""
        with pytest.raises(ValueError, match="Tool description cannot be empty"):
            Tool(
                name="test",
                description="",
                parameters_schema={},
                function=sample_function,
            )

    def test_tool_non_callable_function_raises_error(self):
        """Test that non-callable function raises ValueError."""
        with pytest.raises(ValueError, match="Tool function must be callable"):
            Tool(
                name="test",
                description="Test",
                parameters_schema={},
                function="not a function",  # type: ignore
            )


# ToolRegistry tests
class TestToolRegistry:
    """Tests for the ToolRegistry class."""

    def test_registry_creation(self):
        """Test creating an empty registry."""
        registry = ToolRegistry()
        assert len(registry) == 0
        assert registry.list_names() == []
        assert registry.list_tools() == []

    def test_register_tool(self, registry, sample_tool):
        """Test registering a tool."""
        registry.register(sample_tool)
        assert len(registry) == 1
        assert "add" in registry
        assert registry.has("add")

    def test_register_duplicate_raises_error(self, registry, sample_tool):
        """Test that registering duplicate tool raises error."""
        registry.register(sample_tool)
        with pytest.raises(ToolRegistrationError, match="Tool 'add' is already registered"):
            registry.register(sample_tool)

    def test_get_tool(self, registry, sample_tool):
        """Test retrieving a tool by name."""
        registry.register(sample_tool)
        retrieved = registry.get("add")
        assert retrieved == sample_tool
        assert retrieved.name == "add"

    def test_get_nonexistent_tool_raises_error(self, registry):
        """Test that getting nonexistent tool raises error."""
        with pytest.raises(ToolNotFoundError, match="Tool 'nonexistent' not found"):
            registry.get("nonexistent")

    def test_has_tool(self, registry, sample_tool):
        """Test checking if tool exists."""
        assert not registry.has("add")
        registry.register(sample_tool)
        assert registry.has("add")

    def test_contains_operator(self, registry, sample_tool):
        """Test 'in' operator for registry."""
        assert "add" not in registry
        registry.register(sample_tool)
        assert "add" in registry

    def test_list_names(self, registry, sample_tool):
        """Test listing all tool names."""
        registry.register(sample_tool)
        names = registry.list_names()
        assert names == ["add"]

    def test_list_tools(self, registry, sample_tool):
        """Test listing all tools."""
        registry.register(sample_tool)
        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0] == sample_tool

    def test_unregister_tool(self, registry, sample_tool):
        """Test unregistering a tool."""
        registry.register(sample_tool)
        assert "add" in registry
        registry.unregister("add")
        assert "add" not in registry

    def test_unregister_nonexistent_raises_error(self, registry):
        """Test that unregistering nonexistent tool raises error."""
        with pytest.raises(ToolNotFoundError, match="Tool 'nonexistent' not found"):
            registry.unregister("nonexistent")

    def test_clear_registry(self, registry, sample_tool):
        """Test clearing all tools from registry."""
        registry.register(sample_tool)
        assert len(registry) == 1
        registry.clear()
        assert len(registry) == 0
        assert registry.list_names() == []

    def test_multiple_tools(self, registry, sample_function):
        """Test registering multiple tools."""
        tool1 = Tool("add", "Add numbers", {}, sample_function)
        tool2 = Tool("multiply", "Multiply numbers", {}, sample_function)
        tool3 = Tool("subtract", "Subtract numbers", {}, sample_function)

        registry.register(tool1)
        registry.register(tool2)
        registry.register(tool3)

        assert len(registry) == 3
        assert set(registry.list_names()) == {"add", "multiply", "subtract"}


# Schema generation tests
class TestSchemaGeneration:
    """Tests for automatic schema generation from type hints."""

    def test_simple_function_schema(self):
        """Test schema generation for simple typed function."""

        @tool()
        def add(a: int, b: int) -> int:
            """Add two numbers."""
            return a + b

        metadata = get_tool_metadata(add)
        assert metadata is not None
        assert metadata.name == "add"
        assert metadata.description == "Add two numbers."
        schema = metadata.parameters_schema
        assert schema["type"] == "object"
        assert "a" in schema["properties"]
        assert "b" in schema["properties"]
        assert schema["properties"]["a"]["type"] == "integer"
        assert schema["properties"]["b"]["type"] == "integer"
        assert set(schema["required"]) == {"a", "b"}

    def test_function_with_optional_params(self):
        """Test schema generation with optional parameters."""

        @tool()
        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone."""
            return f"{greeting}, {name}!"

        metadata = get_tool_metadata(greet)
        assert metadata is not None
        schema = metadata.parameters_schema
        assert "name" in schema["required"]
        assert "greeting" not in schema.get("required", [])

    def test_function_with_various_types(self):
        """Test schema generation with various Python types."""

        @tool()
        def complex_func(text: str, count: int, ratio: float, active: bool, items: list) -> dict:
            """A function with various types."""
            return {}

        metadata = get_tool_metadata(complex_func)
        assert metadata is not None
        schema = metadata.parameters_schema
        assert schema["properties"]["text"]["type"] == "string"
        assert schema["properties"]["count"]["type"] == "integer"
        assert schema["properties"]["ratio"]["type"] == "number"
        assert schema["properties"]["active"]["type"] == "boolean"
        assert schema["properties"]["items"]["type"] == "array"

    def test_function_without_type_hints(self):
        """Test schema generation for function without type hints."""

        @tool()
        def no_hints(a, b):  # type: ignore
            """Function without type hints."""
            return a + b

        metadata = get_tool_metadata(no_hints)
        assert metadata is not None
        schema = metadata.parameters_schema
        # Should default to string for untyped params
        assert schema["properties"]["a"]["type"] == "string"
        assert schema["properties"]["b"]["type"] == "string"

    def test_custom_name_and_description(self):
        """Test decorator with custom name and description."""

        @tool(name="custom_add", description="Custom description")
        def add(a: int, b: int) -> int:
            return a + b

        metadata = get_tool_metadata(add)
        assert metadata is not None
        assert metadata.name == "custom_add"
        assert metadata.description == "Custom description"

    def test_custom_schema(self):
        """Test decorator with custom schema."""
        custom_schema = {
            "type": "object",
            "properties": {"x": {"type": "number", "minimum": 0}},
            "required": ["x"],
        }

        @tool(parameters_schema=custom_schema)
        def func(x: float) -> float:
            """A function."""
            return x * 2

        metadata = get_tool_metadata(func)
        assert metadata is not None
        assert metadata.parameters_schema == custom_schema

    def test_function_without_docstring(self):
        """Test decorator on function without docstring."""

        @tool()
        def no_doc(x: int) -> int:
            return x

        metadata = get_tool_metadata(no_doc)
        assert metadata is not None
        assert metadata.description == "Function no_doc"

    def test_get_metadata_on_undecorated_function(self):
        """Test getting metadata from undecorated function."""

        def normal_func():
            pass

        metadata = get_tool_metadata(normal_func)
        assert metadata is None


# register_tool decorator tests
class TestRegisterToolDecorator:
    """Tests for the register_tool decorator factory."""

    def test_register_tool_decorator(self):
        """Test register_tool decorator registers tool automatically."""
        registry = ToolRegistry()

        @register_tool(registry)
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b

        assert "multiply" in registry
        tool = registry.get("multiply")
        assert tool.name == "multiply"
        assert tool.description == "Multiply two numbers."
        assert tool.function(3, 4) == 12

    def test_register_with_custom_name(self):
        """Test register_tool with custom name."""
        registry = ToolRegistry()

        @register_tool(registry, name="mult")
        def multiply(a: int, b: int) -> int:
            """Multiply two numbers."""
            return a * b

        assert "mult" in registry
        assert "multiply" not in registry

    def test_multiple_registrations_to_same_registry(self):
        """Test registering multiple tools to the same registry."""
        registry = ToolRegistry()

        @register_tool(registry)
        def add(a: int, b: int) -> int:
            return a + b

        @register_tool(registry)
        def subtract(a: int, b: int) -> int:
            return a - b

        assert len(registry) == 2
        assert "add" in registry
        assert "subtract" in registry


# Integration tests
class TestToolExecution:
    """Integration tests for tool execution."""

    def test_execute_registered_tool(self, registry):
        """Test executing a registered tool."""

        def calculator(operation: str, a: int, b: int) -> int:
            """Perform calculation."""
            if operation == "add":
                return a + b
            elif operation == "subtract":
                return a - b
            return 0

        tool_obj = Tool(
            name="calculator",
            description="Calculator tool",
            parameters_schema={},
            function=calculator,
        )
        registry.register(tool_obj)

        # Execute the tool
        retrieved_tool = registry.get("calculator")
        result = retrieved_tool.function("add", 5, 3)
        assert result == 8

    def test_tool_metadata_preserved(self):
        """Test that tool metadata is preserved through decoration."""

        @tool(name="test", description="Test tool")
        def my_func(x: int) -> int:
            """Original docstring."""
            return x * 2

        # Function should still be callable
        assert my_func(5) == 10

        # Metadata should be attached
        metadata = get_tool_metadata(my_func)
        assert metadata is not None
        assert metadata.name == "test"

        # Original function should still work
        assert callable(my_func)


# Error handling tests
class TestErrorHandling:
    """Tests for error handling in the registry system."""

    def test_tool_error_inheritance(self):
        """Test that custom errors inherit from ToolError."""
        assert issubclass(ToolNotFoundError, ToolError)
        assert issubclass(ToolRegistrationError, ToolError)

    def test_detailed_error_messages(self, registry):
        """Test that errors provide helpful messages."""
        try:
            registry.get("nonexistent")
        except ToolNotFoundError as e:
            assert "nonexistent" in str(e)
            assert "Available tools" in str(e)

"""Tests for tool schema conversion."""

import pytest

from messagedb_agent.llm.base import ToolDeclaration
from messagedb_agent.tools import (
    Tool,
    ToolRegistry,
    filter_tools_by_name,
    get_tool_names_from_declarations,
    merge_schema_properties,
    register_builtin_tools,
    registry_to_function_declarations,
    tool_to_function_declaration,
    tools_to_function_declarations,
    validate_function_declaration,
)


# Test fixtures
@pytest.fixture
def sample_tool():
    """Create a sample tool for testing."""

    def add(a: int, b: int) -> int:
        return a + b

    return Tool(
        name="add",
        description="Add two numbers together",
        parameters_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer", "description": "First number"},
                "b": {"type": "integer", "description": "Second number"},
            },
            "required": ["a", "b"],
        },
        function=add,
    )


@pytest.fixture
def sample_tools():
    """Create multiple sample tools for testing."""

    def add(a: int, b: int) -> int:
        return a + b

    def multiply(a: int, b: int) -> int:
        return a * b

    def greet(name: str, greeting: str = "Hello") -> str:
        return f"{greeting}, {name}!"

    return [
        Tool(
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
            function=add,
        ),
        Tool(
            name="multiply",
            description="Multiply two numbers",
            parameters_schema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
            function=multiply,
        ),
        Tool(
            name="greet",
            description="Greet someone",
            parameters_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "greeting": {"type": "string"},
                },
                "required": ["name"],
            },
            function=greet,
        ),
    ]


# tool_to_function_declaration tests
class TestToolToFunctionDeclaration:
    """Tests for tool_to_function_declaration function."""

    def test_converts_tool_to_declaration(self, sample_tool):
        """Test converting a tool to ToolDeclaration."""
        declaration = tool_to_function_declaration(sample_tool)

        assert isinstance(declaration, ToolDeclaration)
        assert declaration.name == "add"
        assert declaration.description == "Add two numbers together"
        assert declaration.parameters == sample_tool.parameters_schema

    def test_preserves_parameter_schema(self, sample_tool):
        """Test that parameter schema is preserved exactly."""
        declaration = tool_to_function_declaration(sample_tool)

        assert declaration.parameters["type"] == "object"
        assert "properties" in declaration.parameters
        assert "a" in declaration.parameters["properties"]
        assert "b" in declaration.parameters["properties"]
        assert declaration.parameters["required"] == ["a", "b"]

    def test_preserves_parameter_descriptions(self, sample_tool):
        """Test that parameter descriptions are preserved."""
        declaration = tool_to_function_declaration(sample_tool)

        assert declaration.parameters["properties"]["a"]["description"] == "First number"
        assert declaration.parameters["properties"]["b"]["description"] == "Second number"


# tools_to_function_declarations tests
class TestToolsToFunctionDeclarations:
    """Tests for tools_to_function_declarations function."""

    def test_converts_empty_list(self):
        """Test converting empty list of tools."""
        declarations = tools_to_function_declarations([])
        assert declarations == []

    def test_converts_single_tool(self, sample_tool):
        """Test converting single tool."""
        declarations = tools_to_function_declarations([sample_tool])

        assert len(declarations) == 1
        assert declarations[0].name == "add"

    def test_converts_multiple_tools(self, sample_tools):
        """Test converting multiple tools."""
        declarations = tools_to_function_declarations(sample_tools)

        assert len(declarations) == 3
        assert declarations[0].name == "add"
        assert declarations[1].name == "multiply"
        assert declarations[2].name == "greet"

    def test_preserves_order(self, sample_tools):
        """Test that tool order is preserved."""
        declarations = tools_to_function_declarations(sample_tools)

        tool_names = [decl.name for decl in declarations]
        assert tool_names == ["add", "multiply", "greet"]

    def test_all_declarations_valid(self, sample_tools):
        """Test that all converted declarations are ToolDeclaration instances."""
        declarations = tools_to_function_declarations(sample_tools)

        for decl in declarations:
            assert isinstance(decl, ToolDeclaration)


# registry_to_function_declarations tests
class TestRegistryToFunctionDeclarations:
    """Tests for registry_to_function_declarations function."""

    def test_converts_empty_registry(self):
        """Test converting empty registry."""
        registry = ToolRegistry()
        declarations = registry_to_function_declarations(registry)

        assert declarations == []

    def test_converts_registry_with_builtin_tools(self):
        """Test converting registry with builtin tools."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        declarations = registry_to_function_declarations(registry)

        assert len(declarations) == 4
        tool_names = {decl.name for decl in declarations}
        assert tool_names == {"get_current_time", "echo", "calculate", "write_note"}

    def test_all_registry_tools_converted(self, sample_tools):
        """Test that all tools in registry are converted."""
        registry = ToolRegistry()
        for tool in sample_tools:
            registry.register(tool)

        declarations = registry_to_function_declarations(registry)

        assert len(declarations) == len(sample_tools)

    def test_declaration_count_matches_registry(self):
        """Test that declaration count matches registry count."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        declarations = registry_to_function_declarations(registry)

        assert len(declarations) == len(registry)


# get_tool_names_from_declarations tests
class TestGetToolNamesFromDeclarations:
    """Tests for get_tool_names_from_declarations function."""

    def test_empty_list_returns_empty(self):
        """Test empty list returns empty list."""
        names = get_tool_names_from_declarations([])
        assert names == []

    def test_extracts_single_name(self):
        """Test extracting single tool name."""
        declarations = [
            ToolDeclaration(name="test", description="Test", parameters={}),
        ]
        names = get_tool_names_from_declarations(declarations)

        assert names == ["test"]

    def test_extracts_multiple_names(self):
        """Test extracting multiple tool names."""
        declarations = [
            ToolDeclaration(name="add", description="Add", parameters={}),
            ToolDeclaration(name="multiply", description="Multiply", parameters={}),
            ToolDeclaration(name="divide", description="Divide", parameters={}),
        ]
        names = get_tool_names_from_declarations(declarations)

        assert names == ["add", "multiply", "divide"]

    def test_preserves_order(self):
        """Test that name order is preserved."""
        declarations = [
            ToolDeclaration(name="z", description="Z", parameters={}),
            ToolDeclaration(name="a", description="A", parameters={}),
            ToolDeclaration(name="m", description="M", parameters={}),
        ]
        names = get_tool_names_from_declarations(declarations)

        assert names == ["z", "a", "m"]


# validate_function_declaration tests
class TestValidateFunctionDeclaration:
    """Tests for validate_function_declaration function."""

    def test_valid_declaration(self):
        """Test that valid declaration passes validation."""
        declaration = ToolDeclaration(
            name="test",
            description="Test tool",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "integer"}},
                "required": ["x"],
            },
        )
        assert validate_function_declaration(declaration) is True

    def test_minimal_valid_declaration(self):
        """Test minimal valid declaration."""
        declaration = ToolDeclaration(
            name="test",
            description="Test",
            parameters={"type": "object"},
        )
        assert validate_function_declaration(declaration) is True

    def test_empty_name_invalid(self):
        """Test that empty name fails validation."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            ToolDeclaration(
                name="",
                description="Test",
                parameters={"type": "object"},
            )

    def test_whitespace_only_name_invalid(self):
        """Test that whitespace-only name fails validation."""
        with pytest.raises(ValueError, match="name cannot be empty"):
            ToolDeclaration(
                name="   ",
                description="Test",
                parameters={"type": "object"},
            )

    def test_empty_description_invalid(self):
        """Test that empty description fails validation."""
        with pytest.raises(ValueError, match="description cannot be empty"):
            ToolDeclaration(
                name="test",
                description="",
                parameters={"type": "object"},
            )

    def test_non_dict_parameters_invalid(self):
        """Test that non-dict parameters fail validation."""
        declaration = ToolDeclaration(
            name="test",
            description="Test",
            parameters="not a dict",  # type: ignore
        )
        assert validate_function_declaration(declaration) is False

    def test_missing_type_invalid(self):
        """Test that missing 'type' fails validation."""
        declaration = ToolDeclaration(
            name="test",
            description="Test",
            parameters={"properties": {}},
        )
        assert validate_function_declaration(declaration) is False

    def test_wrong_type_value_invalid(self):
        """Test that wrong type value fails validation."""
        declaration = ToolDeclaration(
            name="test",
            description="Test",
            parameters={"type": "array"},
        )
        assert validate_function_declaration(declaration) is False

    def test_non_dict_properties_invalid(self):
        """Test that non-dict properties fail validation."""
        declaration = ToolDeclaration(
            name="test",
            description="Test",
            parameters={"type": "object", "properties": "not a dict"},
        )
        assert validate_function_declaration(declaration) is False

    def test_non_list_required_invalid(self):
        """Test that non-list required fails validation."""
        declaration = ToolDeclaration(
            name="test",
            description="Test",
            parameters={"type": "object", "required": "not a list"},
        )
        assert validate_function_declaration(declaration) is False

    def test_valid_with_properties_and_required(self):
        """Test valid declaration with properties and required."""
        declaration = ToolDeclaration(
            name="test",
            description="Test",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "integer"}},
                "required": ["a"],
            },
        )
        assert validate_function_declaration(declaration) is True


# filter_tools_by_name tests
class TestFilterToolsByName:
    """Tests for filter_tools_by_name function."""

    def test_filter_empty_list(self):
        """Test filtering empty list."""
        filtered = filter_tools_by_name([], ["test"])
        assert filtered == []

    def test_filter_with_empty_names(self):
        """Test filtering with empty names list."""
        declarations = [
            ToolDeclaration(name="add", description="Add", parameters={}),
        ]
        filtered = filter_tools_by_name(declarations, [])
        assert filtered == []

    def test_filter_single_match(self):
        """Test filtering single match."""
        declarations = [
            ToolDeclaration(name="add", description="Add", parameters={}),
            ToolDeclaration(name="multiply", description="Multiply", parameters={}),
            ToolDeclaration(name="divide", description="Divide", parameters={}),
        ]
        filtered = filter_tools_by_name(declarations, ["add"])

        assert len(filtered) == 1
        assert filtered[0].name == "add"

    def test_filter_multiple_matches(self):
        """Test filtering multiple matches."""
        declarations = [
            ToolDeclaration(name="add", description="Add", parameters={}),
            ToolDeclaration(name="multiply", description="Multiply", parameters={}),
            ToolDeclaration(name="divide", description="Divide", parameters={}),
        ]
        filtered = filter_tools_by_name(declarations, ["add", "divide"])

        assert len(filtered) == 2
        assert {t.name for t in filtered} == {"add", "divide"}

    def test_filter_preserves_order(self):
        """Test that filter preserves original order."""
        declarations = [
            ToolDeclaration(name="add", description="Add", parameters={}),
            ToolDeclaration(name="multiply", description="Multiply", parameters={}),
            ToolDeclaration(name="divide", description="Divide", parameters={}),
        ]
        filtered = filter_tools_by_name(declarations, ["divide", "add"])

        # Order should match original list, not filter list
        assert filtered[0].name == "add"
        assert filtered[1].name == "divide"

    def test_filter_no_matches(self):
        """Test filtering with no matches."""
        declarations = [
            ToolDeclaration(name="add", description="Add", parameters={}),
        ]
        filtered = filter_tools_by_name(declarations, ["nonexistent"])

        assert filtered == []

    def test_filter_duplicate_names(self):
        """Test filtering with duplicate names in filter list."""
        declarations = [
            ToolDeclaration(name="add", description="Add", parameters={}),
            ToolDeclaration(name="multiply", description="Multiply", parameters={}),
        ]
        filtered = filter_tools_by_name(declarations, ["add", "add", "add"])

        # Should only return one instance
        assert len(filtered) == 1
        assert filtered[0].name == "add"


# merge_schema_properties tests
class TestMergeSchemaProperties:
    """Tests for merge_schema_properties function."""

    def test_merge_into_empty_schema(self):
        """Test merging into schema with no properties."""
        base = {"type": "object"}
        additional = {"b": {"type": "string"}}

        merged = merge_schema_properties(base, additional)

        assert "properties" in merged
        assert "b" in merged["properties"]
        assert merged["properties"]["b"]["type"] == "string"

    def test_merge_with_existing_properties(self):
        """Test merging with existing properties."""
        base = {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
            "required": ["a"],
        }
        additional = {"b": {"type": "string"}}

        merged = merge_schema_properties(base, additional)

        assert "a" in merged["properties"]
        assert "b" in merged["properties"]
        assert merged["required"] == ["a"]

    def test_does_not_modify_original(self):
        """Test that original schema is not modified."""
        base = {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
        }
        additional = {"b": {"type": "string"}}

        merged = merge_schema_properties(base, additional)

        # Original should not have 'b'
        assert "b" not in base["properties"]
        # Merged should have both
        assert "b" in merged["properties"]

    def test_additional_overwrites_existing(self):
        """Test that additional properties overwrite existing ones."""
        base = {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
        }
        additional = {"a": {"type": "string"}}

        merged = merge_schema_properties(base, additional)

        assert merged["properties"]["a"]["type"] == "string"

    def test_preserves_other_schema_fields(self):
        """Test that other schema fields are preserved."""
        base = {
            "type": "object",
            "properties": {"a": {"type": "integer"}},
            "required": ["a"],
            "additionalProperties": False,
        }
        additional = {"b": {"type": "string"}}

        merged = merge_schema_properties(base, additional)

        assert merged["type"] == "object"
        assert merged["required"] == ["a"]
        assert merged["additionalProperties"] is False


# Integration tests
class TestSchemaIntegration:
    """Integration tests for schema conversion."""

    def test_full_conversion_pipeline(self):
        """Test complete conversion from Tool to ToolDeclaration."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        # Convert registry to declarations
        declarations = registry_to_function_declarations(registry)

        # Validate all declarations
        for decl in declarations:
            assert validate_function_declaration(decl) is True

        # Extract names
        names = get_tool_names_from_declarations(declarations)
        assert len(names) == len(declarations)

    def test_filter_and_validate(self):
        """Test filtering and validation together."""
        registry = ToolRegistry()
        register_builtin_tools(registry)

        declarations = registry_to_function_declarations(registry)
        filtered = filter_tools_by_name(declarations, ["echo", "calculate"])

        assert len(filtered) == 2
        for decl in filtered:
            assert validate_function_declaration(decl) is True

    def test_round_trip_conversion(self, sample_tools):
        """Test that conversion preserves all necessary information."""
        # Convert tools to declarations
        declarations = tools_to_function_declarations(sample_tools)

        # Extract names and verify
        names = get_tool_names_from_declarations(declarations)
        expected_names = [tool.name for tool in sample_tools]
        assert names == expected_names

        # Validate all
        for decl in declarations:
            assert validate_function_declaration(decl) is True

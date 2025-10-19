"""LLM call function for Vertex AI integration.

This module provides the core LLM calling functionality, including
response parsing, error handling, and token usage tracking.
"""

from dataclasses import dataclass
from typing import Any

from vertexai.generative_models import (
    Content,
    FunctionDeclaration,
    GenerationResponse,
    Tool,
)

from messagedb_agent.llm.client import VertexAIClient


@dataclass(frozen=True)
class ToolCall:
    """Represents a tool/function call from the LLM.

    Attributes:
        id: Unique identifier for this tool call (generated from name + args hash)
        name: Name of the tool/function to call
        arguments: Dictionary of arguments to pass to the tool

    Example:
        >>> tool_call = ToolCall(
        ...     id="call_123",
        ...     name="get_weather",
        ...     arguments={"city": "San Francisco"}
        ... )
    """

    id: str
    name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        """Validate tool call after initialization.

        Raises:
            ValueError: If fields are invalid
        """
        if not self.id or not self.id.strip():
            raise ValueError("id cannot be empty or whitespace-only")
        if not self.name or not self.name.strip():
            raise ValueError("name cannot be empty or whitespace-only")


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM call.

    This encapsulates all information returned from a successful LLM call,
    including the response text, any tool calls, model metadata, and token usage.

    Attributes:
        text: The text response from the model (may be None if only tool calls)
        tool_calls: List of tool calls requested by the model
        model_name: Name of the model that generated this response
        token_usage: Dictionary with token usage statistics
            (input_tokens, output_tokens, total_tokens)

    Example:
        >>> response = LLMResponse(
        ...     text="Let me check the weather for you.",
        ...     tool_calls=[ToolCall(id="1", name="get_weather", arguments={"city": "NYC"})],
        ...     model_name="claude-sonnet-4-5@20250929",
        ...     token_usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        ... )
    """

    text: str | None
    tool_calls: list[ToolCall]
    model_name: str
    token_usage: dict[str, int]

    def __post_init__(self) -> None:
        """Validate LLM response after initialization.

        Raises:
            ValueError: If fields are invalid
        """
        if not self.model_name or not self.model_name.strip():
            raise ValueError("model_name cannot be empty or whitespace-only")

        # Either text or tool_calls must be present
        if not self.text and not self.tool_calls:
            raise ValueError("LLMResponse must have either text or tool_calls")


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMAPIError(LLMError):
    """Exception raised when the LLM API call fails."""

    pass


class LLMResponseError(LLMError):
    """Exception raised when parsing the LLM response fails."""

    pass


def call_llm(
    client: VertexAIClient,
    contents: list[Content],
    tools: list[FunctionDeclaration] | None = None,
) -> LLMResponse:
    """Call the LLM with the given contents and optional tools.

    This function makes a synchronous call to the Vertex AI API, handles
    errors, and parses the response into a structured LLMResponse object.

    Args:
        client: Initialized VertexAIClient instance
        contents: List of Content objects representing the conversation
        tools: Optional list of FunctionDeclaration objects for tool calling

    Returns:
        LLMResponse with text, tool calls, model name, and token usage

    Raises:
        LLMAPIError: If the API call fails
        LLMResponseError: If the response cannot be parsed
        ValueError: If inputs are invalid

    Example:
        >>> from messagedb_agent.llm import create_client, format_messages, create_user_message
        >>> from messagedb_agent.config import VertexAIConfig
        >>> config = VertexAIConfig(
        ...     project="my-project",
        ...     location="us-central1",
        ...     model_name="gemini-2.0-flash-exp"
        ... )
        >>> client = create_client(config)
        >>> messages = [create_user_message("What is 2+2?")]
        >>> contents = format_messages(messages)
        >>> response = call_llm(client, contents)
        >>> print(response.text)
    """
    if not contents:
        raise ValueError("contents cannot be empty")

    try:
        # Get the model from the client
        model = client.get_model()

        # Prepare tools if provided
        vertex_tools: list[Tool] | None = None
        if tools:
            vertex_tools = [Tool(function_declarations=tools)]

        # Make the API call
        generation_response: GenerationResponse = model.generate_content(
            contents=contents,
            tools=vertex_tools,
        )

        # Parse the response
        return _parse_response(generation_response, client.model_name)

    except LLMError:
        # Re-raise our own errors
        raise
    except Exception as e:
        # Wrap any other exceptions as LLMAPIError
        raise LLMAPIError(f"LLM API call failed: {e}") from e


def _parse_response(response: GenerationResponse, model_name: str) -> LLMResponse:
    """Parse a GenerationResponse into an LLMResponse.

    Args:
        response: The response from the Vertex AI API
        model_name: Name of the model that generated the response

    Returns:
        Parsed LLMResponse

    Raises:
        LLMResponseError: If the response cannot be parsed
    """
    try:
        # Get the first candidate (Vertex AI typically returns one)
        if not response.candidates:
            raise LLMResponseError("Response has no candidates")

        candidate = response.candidates[0]

        # Extract tool calls first (before trying to access text)
        tool_calls: list[ToolCall] = []
        if hasattr(candidate, "function_calls") and candidate.function_calls:
            for i, fc in enumerate(candidate.function_calls):
                # Generate a simple ID based on index and function name
                tool_call_id = f"{fc.name}_{i}"
                tool_calls.append(
                    ToolCall(
                        id=tool_call_id,
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {},
                    )
                )

        # Extract text (may be None if only function calls)
        # Note: Accessing candidate.text raises ValueError (wrapped AttributeError)
        # if the response contains ONLY function calls and no text.
        text: str | None = None
        try:
            # Try to get the text - this will fail with ValueError if there's
            # a function call instead of text
            text = candidate.text if candidate.text else None
        except (AttributeError, ValueError):
            # This is expected when there are only function calls and no text
            # The Vertex AI SDK raises ValueError when accessing .text on a
            # candidate that has function_call instead
            text = None

        # Extract token usage
        token_usage: dict[str, int] = {}
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            # Map Vertex AI usage field names to our standard names
            if hasattr(usage, "prompt_token_count"):
                token_usage["input_tokens"] = usage.prompt_token_count
            if hasattr(usage, "candidates_token_count"):
                token_usage["output_tokens"] = usage.candidates_token_count
            if hasattr(usage, "total_token_count"):
                token_usage["total_tokens"] = usage.total_token_count

        # Create the LLMResponse
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            model_name=model_name,
            token_usage=token_usage,
        )

    except LLMError:
        # Re-raise our own errors
        raise
    except Exception as e:
        # Wrap any other exceptions as LLMResponseError
        raise LLMResponseError(f"Failed to parse LLM response: {e}") from e


def create_function_declaration(
    name: str, description: str, parameters: dict[str, Any]
) -> FunctionDeclaration:
    """Create a FunctionDeclaration for tool calling.

    This is a convenience function for creating FunctionDeclaration objects
    with proper validation.

    Args:
        name: Function name
        description: Human-readable description of what the function does
        parameters: JSON Schema object describing the function parameters

    Returns:
        FunctionDeclaration ready to be used in LLM calls

    Raises:
        ValueError: If inputs are invalid

    Example:
        >>> func_decl = create_function_declaration(
        ...     name="get_weather",
        ...     description="Get current weather for a location",
        ...     parameters={
        ...         "type": "object",
        ...         "properties": {
        ...             "city": {"type": "string", "description": "City name"}
        ...         },
        ...         "required": ["city"]
        ...     }
        ... )
    """
    if not name or not name.strip():
        raise ValueError("name cannot be empty or whitespace-only")
    if not description or not description.strip():
        raise ValueError("description cannot be empty or whitespace-only")

    return FunctionDeclaration(
        name=name,
        description=description,
        parameters=parameters,
    )

"""Base LLM client interface for unified Gemini and Claude support.

This module defines the abstract base class that all LLM clients must implement,
providing a unified interface regardless of the underlying model (Gemini or Claude).
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


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
        tool_calls: List of tool calls requested by the model (may be None/empty)
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
    tool_calls: list[ToolCall] | None
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
        # Empty list [] is valid (no tools), but we need at least text or tool calls
        has_text = self.text is not None and self.text.strip()
        has_tool_calls = self.tool_calls is not None and len(self.tool_calls) > 0

        if not has_text and not has_tool_calls:
            raise ValueError("LLMResponse must have either text or tool_calls")


@dataclass(frozen=True)
class ToolDeclaration:
    """Unified tool/function declaration format.

    This provides a model-agnostic way to declare tools that can be used
    by the LLM. The client implementations will convert this to the
    appropriate format for their respective APIs.

    Attributes:
        name: Function name
        description: Human-readable description of what the function does
        parameters: JSON Schema object describing the function parameters

    Example:
        >>> tool = ToolDeclaration(
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

    name: str
    description: str
    parameters: dict[str, Any]

    def __post_init__(self) -> None:
        """Validate tool declaration after initialization.

        Raises:
            ValueError: If fields are invalid
        """
        if not self.name or not self.name.strip():
            raise ValueError("name cannot be empty or whitespace-only")
        if not self.description or not self.description.strip():
            raise ValueError("description cannot be empty or whitespace-only")


@dataclass(frozen=True)
class Message:
    """Internal message representation for LLM conversations.

    This is the format that projection functions produce. The LLM client
    implementations convert these to their respective API formats.

    Attributes:
        role: Message role ("user", "assistant", or "tool")
        text: Optional text content
        tool_calls: Optional list of tool calls (for assistant messages)
        tool_call_id: Optional tool call ID (for tool result messages)
        tool_name: Optional tool name (for tool result messages)

    Example:
        >>> msg = Message(role="user", text="Hello, how are you?")
        >>> msg = Message(
        ...     role="assistant",
        ...     text="I'll check the weather",
        ...     tool_calls=[ToolCall(id="1", name="get_weather", arguments={"city": "NYC"})]
        ... )
        >>> msg = Message(
        ...     role="tool",
        ...     text='{"temperature": 72}',
        ...     tool_call_id="1",
        ...     tool_name="get_weather"
        ... )
    """

    role: str
    text: str | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None

    def __post_init__(self) -> None:
        """Validate message after initialization.

        Raises:
            ValueError: If message is invalid
        """
        valid_roles = {"user", "assistant", "tool"}
        if self.role not in valid_roles:
            raise ValueError(f"role must be one of {valid_roles}, got {self.role}")

        # At least one content field must be present
        if not any([self.text, self.tool_calls]):
            raise ValueError("Message must have at least one of: text, tool_calls")

        # Tool role messages must have tool_call_id and tool_name
        if self.role == "tool":
            if not self.tool_call_id:
                raise ValueError("Messages with role='tool' must have tool_call_id")
            if not self.tool_name:
                raise ValueError("Messages with role='tool' must have tool_name")


@dataclass(frozen=True)
class StreamDelta:
    """Represents an incremental update in a streaming LLM response.

    This class encapsulates the various types of deltas that can be received
    during streaming: text deltas, tool call deltas, and final token usage.

    Attributes:
        delta_type: Type of delta ("text", "tool_call", "tool_input", "usage", "done")
        text: Text delta content (for delta_type="text")
        tool_call_index: Index of the tool call being streamed (for tool deltas)
        tool_call_id: ID of the tool call (for tool deltas)
        tool_name: Name of the tool being called (for delta_type="tool_call")
        tool_input_delta: Partial JSON string for tool arguments (for delta_type="tool_input")
        token_usage: Final token usage statistics (for delta_type="usage" or "done")

    Example:
        >>> # Text delta
        >>> delta = StreamDelta(delta_type="text", text="Hello")
        >>> # Tool call start
        >>> delta = StreamDelta(
        ...     delta_type="tool_call",
        ...     tool_call_index=0,
        ...     tool_call_id="call_123",
        ...     tool_name="get_weather"
        ... )
        >>> # Tool input delta
        >>> delta = StreamDelta(
        ...     delta_type="tool_input",
        ...     tool_call_index=0,
        ...     tool_input_delta='{"city": "SF"}'
        ... )
        >>> # Final usage
        >>> delta = StreamDelta(
        ...     delta_type="done",
        ...     token_usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        ... )
    """

    delta_type: str
    text: str | None = None
    tool_call_index: int | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_input_delta: str | None = None
    token_usage: dict[str, int] | None = None

    def __post_init__(self) -> None:
        """Validate stream delta after initialization.

        Raises:
            ValueError: If delta is invalid
        """
        valid_types = {"text", "tool_call", "tool_input", "usage", "done"}
        if self.delta_type not in valid_types:
            raise ValueError(f"delta_type must be one of {valid_types}, got {self.delta_type}")

        # Validate type-specific fields
        if self.delta_type == "text" and not self.text:
            raise ValueError("text deltas must have non-empty text")
        if self.delta_type == "tool_call":
            if self.tool_call_index is None:
                raise ValueError("tool_call deltas must have tool_call_index")
            if not self.tool_call_id:
                raise ValueError("tool_call deltas must have tool_call_id")
            if not self.tool_name:
                raise ValueError("tool_call deltas must have tool_name")
        if self.delta_type == "tool_input":
            if self.tool_call_index is None:
                raise ValueError("tool_input deltas must have tool_call_index")
            if not self.tool_input_delta:
                raise ValueError("tool_input deltas must have tool_input_delta")
        if self.delta_type in ("usage", "done") and not self.token_usage:
            raise ValueError(f"{self.delta_type} deltas must have token_usage")


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.

    This defines the interface that all LLM client implementations must follow,
    enabling unified code that works with both Gemini and Claude models.
    """

    @abstractmethod
    def call(
        self,
        messages: list[Message],
        tools: list[ToolDeclaration] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Call the LLM with the given messages and optional tools.

        Args:
            messages: List of conversation messages
            tools: Optional list of tool declarations for function calling
            system_prompt: Optional system prompt to set context

        Returns:
            LLMResponse with text, tool calls, model name, and token usage

        Raises:
            LLMError: If the LLM call fails
        """
        pass

    @abstractmethod
    def call_stream(
        self,
        messages: list[Message],
        tools: list[ToolDeclaration] | None = None,
        system_prompt: str | None = None,
    ) -> Iterator[StreamDelta]:
        """Call the LLM with streaming enabled, yielding incremental updates.

        This method enables streaming responses from the LLM, yielding deltas
        as they become available. This is useful for real-time rendering and
        improved user experience.

        Args:
            messages: List of conversation messages
            tools: Optional list of tool declarations for function calling
            system_prompt: Optional system prompt to set context

        Yields:
            StreamDelta objects representing incremental updates:
            - text deltas: Partial text content as it's generated
            - tool_call deltas: Tool call initiation with name and ID
            - tool_input deltas: Partial JSON for tool arguments
            - usage/done deltas: Final token usage when stream completes

        Raises:
            LLMError: If the LLM call fails

        Example:
            >>> for delta in client.call_stream(messages):
            ...     if delta.delta_type == "text":
            ...         print(delta.text, end="", flush=True)
            ...     elif delta.delta_type == "done":
            ...         print(f"\\nUsed {delta.token_usage['total_tokens']} tokens")
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Get the model name.

        Returns:
            The model name (e.g., "claude-sonnet-4-5@20250929", "gemini-2.5-flash")
        """
        pass


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMAPIError(LLMError):
    """Exception raised when the LLM API call fails."""

    pass


class LLMResponseError(LLMError):
    """Exception raised when parsing the LLM response fails."""

    pass

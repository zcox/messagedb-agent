"""Message formatting for Vertex AI LLM integration.

This module handles conversion between internal message representations
(from projections) and the Vertex AI API format using Content and Part objects.
"""

from dataclasses import dataclass
from typing import Any

from vertexai.generative_models import Content, Part


@dataclass(frozen=True)
class Message:
    """Internal message representation from projections.

    This is the format that projection functions produce. The format_messages()
    function converts these to Vertex AI Content objects.

    Attributes:
        role: Message role ("user", "model", or "function")
        text: Optional text content
        function_call: Optional function call (name and arguments)
        function_response: Optional function response (name and result)

    Example:
        >>> msg = Message(role="user", text="Hello, how are you?")
        >>> msg = Message(
        ...     role="model",
        ...     text="I'll check the weather",
        ...     function_call={"name": "get_weather", "arguments": {"city": "NYC"}}
        ... )
    """

    role: str
    text: str | None = None
    function_call: dict[str, Any] | None = None
    function_response: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Validate message after initialization.

        Raises:
            ValueError: If message is invalid
        """
        valid_roles = {"user", "model", "function"}
        if self.role not in valid_roles:
            raise ValueError(f"role must be one of {valid_roles}, got {self.role}")

        # At least one of text, function_call, or function_response must be present
        if not any([self.text, self.function_call, self.function_response]):
            raise ValueError(
                "Message must have at least one of: text, function_call, function_response"
            )

        # Function role messages must have function_response
        if self.role == "function" and not self.function_response:
            raise ValueError("Messages with role='function' must have function_response")

        # Validate function_call structure
        if self.function_call is not None:
            if "name" not in self.function_call:
                raise ValueError("function_call must have 'name' field")
            if "arguments" not in self.function_call:
                raise ValueError("function_call must have 'arguments' field")
            if not isinstance(self.function_call["name"], str):
                raise ValueError("function_call 'name' must be a string")
            if not isinstance(self.function_call["arguments"], dict):
                raise ValueError("function_call 'arguments' must be a dict")

        # Validate function_response structure
        if self.function_response is not None:
            if "name" not in self.function_response:
                raise ValueError("function_response must have 'name' field")
            if "response" not in self.function_response:
                raise ValueError("function_response must have 'response' field")
            if not isinstance(self.function_response["name"], str):
                raise ValueError("function_response 'name' must be a string")
            if not isinstance(self.function_response["response"], dict):
                raise ValueError("function_response 'response' must be a dict")


def format_messages(messages: list[Message], system_prompt: str | None = None) -> list[Content]:
    """Convert internal messages to Vertex AI Content format.

    This function transforms our internal Message representation (produced by
    projection functions) into the Content objects required by the Vertex AI API.

    System prompts in Vertex AI are typically handled via the GenerationConfig
    or as the first user message, depending on the model. For Gemini models,
    we prepend the system prompt as the first user message if provided.

    Args:
        messages: List of internal Message objects
        system_prompt: Optional system prompt to prepend

    Returns:
        List of Content objects ready for Vertex AI API

    Raises:
        ValueError: If messages are invalid or contain unsupported formats

    Example:
        >>> messages = [
        ...     Message(role="user", text="What's the weather?"),
        ...     Message(
        ...         role="model",
        ...         text="I'll check",
        ...         function_call={"name": "get_weather", "arguments": {"city": "NYC"}}
        ...     ),
        ...     Message(
        ...         role="function",
        ...         function_response={"name": "get_weather", "response": {"temp": 72}}
        ...     ),
        ... ]
        >>> contents = format_messages(messages)
    """
    if not messages:
        raise ValueError("messages list cannot be empty")

    contents: list[Content] = []

    # Add system prompt as first user message if provided
    # Note: Some models support system instructions via GenerationConfig,
    # but for maximum compatibility we use a user message
    if system_prompt:
        if not system_prompt.strip():
            raise ValueError("system_prompt cannot be empty or whitespace-only")
        contents.append(Content(role="user", parts=[Part.from_text(system_prompt)]))

    # Convert each message to Content
    for msg in messages:
        parts: list[Part] = []

        # Add text part if present
        if msg.text:
            parts.append(Part.from_text(msg.text))

        # Add function call part if present
        # Note: Function calls are typically generated BY the model, not sent TO it.
        # When we receive a model response with function calls, those Parts are
        # already properly formatted. Here we're constructing messages for replay
        # scenarios where we need to reconstruct the conversation history.
        # For now, we'll represent function calls as text to avoid using internal APIs.
        # TODO: Investigate proper SDK support for constructing function call Parts
        if msg.function_call:
            # Represent function call as structured text for conversation history
            function_text = (
                f"[Function Call: {msg.function_call['name']} "
                f"with args {msg.function_call['arguments']}]"
            )
            parts.append(Part.from_text(function_text))

        # Add function response part if present
        if msg.function_response:
            parts.append(
                Part.from_function_response(
                    name=msg.function_response["name"],
                    response=msg.function_response["response"],
                )
            )

        # Create Content with appropriate role
        # Note: function responses use role="function" internally,
        # but Vertex AI expects role="user" for function responses
        role = "user" if msg.role == "function" else msg.role
        contents.append(Content(role=role, parts=parts))

    return contents


def create_user_message(text: str) -> Message:
    """Create a user message.

    Args:
        text: User message text

    Returns:
        Message object with role="user"

    Raises:
        ValueError: If text is empty or whitespace-only

    Example:
        >>> msg = create_user_message("Hello!")
        >>> msg.role
        'user'
    """
    if not text or not text.strip():
        raise ValueError("text cannot be empty or whitespace-only")
    return Message(role="user", text=text)


def create_model_message(
    text: str | None = None, function_call: dict[str, Any] | None = None
) -> Message:
    """Create a model (assistant) message.

    Args:
        text: Optional model response text
        function_call: Optional function call dict with 'name' and 'arguments'

    Returns:
        Message object with role="model"

    Raises:
        ValueError: If both text and function_call are None

    Example:
        >>> msg = create_model_message(text="The weather is nice")
        >>> msg = create_model_message(
        ...     text="Let me check",
        ...     function_call={"name": "get_weather", "arguments": {"city": "NYC"}}
        ... )
    """
    if text is None and function_call is None:
        raise ValueError("Must provide either text or function_call")
    return Message(role="model", text=text, function_call=function_call)


def create_function_response_message(name: str, response: dict[str, Any]) -> Message:
    """Create a function response message.

    Args:
        name: Function name that was called
        response: Function response data

    Returns:
        Message object with role="function"

    Raises:
        ValueError: If name is empty or response is invalid

    Example:
        >>> msg = create_function_response_message(
        ...     name="get_weather",
        ...     response={"temperature": 72, "condition": "sunny"}
        ... )
    """
    if not name or not name.strip():
        raise ValueError("name cannot be empty or whitespace-only")
    return Message(role="function", function_response={"name": name, "response": response})

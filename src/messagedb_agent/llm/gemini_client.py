"""Gemini LLM client implementation using Vertex AI.

This module provides a Gemini-specific implementation of the BaseLLMClient
interface, using the Vertex AI SDK's GenerativeModel API.
"""

import vertexai
from google.auth import default  # type: ignore[import-untyped]
from vertexai.generative_models import (
    Content,
    FunctionDeclaration,
    GenerationResponse,
    GenerativeModel,
    Part,
    Tool,
)

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.llm.base import (
    BaseLLMClient,
    LLMAPIError,
    LLMResponse,
    LLMResponseError,
    Message,
    ToolCall,
    ToolDeclaration,
)


class GeminiClient(BaseLLMClient):
    """Gemini LLM client using Vertex AI GenerativeModel API.

    This client implements the BaseLLMClient interface for Gemini models,
    using Application Default Credentials (ADC) for authentication.

    Attributes:
        config: Vertex AI configuration containing project, location, and model name
        _initialized: Whether the Vertex AI SDK has been initialized

    Example:
        >>> config = VertexAIConfig(
        ...     project="my-project",
        ...     location="us-central1",
        ...     model_name="gemini-2.5-flash"
        ... )
        >>> client = GeminiClient(config)
        >>> client.initialize()
        >>> response = client.call([Message(role="user", text="Hello!")])
    """

    def __init__(self, config: VertexAIConfig) -> None:
        """Initialize the Gemini client.

        Args:
            config: Vertex AI configuration with project, location, and model name
        """
        self.config = config
        self._initialized = False

    def initialize(self) -> None:
        """Initialize the Vertex AI SDK with ADC credentials.

        This method must be called before making any LLM calls. It initializes
        the Vertex AI SDK with the configured project and location, using
        Application Default Credentials for authentication.

        The method is idempotent - calling it multiple times has no effect
        after the first successful initialization.

        Raises:
            google.auth.exceptions.DefaultCredentialsError: If ADC is not configured
            Exception: If Vertex AI initialization fails
        """
        if self._initialized:
            return

        # Use Application Default Credentials
        credentials, _ = default()  # type: ignore[reportUnknownVariableType]

        # Initialize Vertex AI
        vertexai.init(
            project=self.config.project,
            location=self.config.location,
            credentials=credentials,  # type: ignore[arg-type]
        )

        self._initialized = True

    def call(
        self,
        messages: list[Message],
        tools: list[ToolDeclaration] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Call the Gemini LLM with the given messages and optional tools.

        Args:
            messages: List of conversation messages
            tools: Optional list of tool declarations for function calling
            system_prompt: Optional system prompt to set context

        Returns:
            LLMResponse with text, tool calls, model name, and token usage

        Raises:
            LLMAPIError: If the API call fails
            LLMResponseError: If the response cannot be parsed
            RuntimeError: If called before initialize()
        """
        if not self._initialized:
            raise RuntimeError(
                "GeminiClient must be initialized before calling. Call initialize()."
            )

        if not messages:
            raise ValueError("messages cannot be empty")

        try:
            # Convert messages to Vertex AI Content format
            contents = self._format_messages(messages, system_prompt)

            # Convert tools to Vertex AI format
            vertex_tools: list[Tool] | None = None
            if tools:
                function_declarations = [
                    FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                    for tool in tools
                ]
                vertex_tools = [Tool(function_declarations=function_declarations)]

            # Get model and make API call
            model = GenerativeModel(self.config.model_name)
            generation_response: GenerationResponse = model.generate_content(
                contents=contents,
                tools=vertex_tools,
            )

            # Parse response
            return self._parse_response(generation_response)

        except (LLMAPIError, LLMResponseError):
            # Re-raise our own errors
            raise
        except Exception as e:
            # Wrap any other exceptions as LLMAPIError
            raise LLMAPIError(f"Gemini API call failed: {e}") from e

    @property
    def model_name(self) -> str:
        """Get the configured model name.

        Returns:
            The Gemini model name (e.g., "gemini-2.5-flash")
        """
        return self.config.model_name

    def _format_messages(
        self, messages: list[Message], system_prompt: str | None = None
    ) -> list[Content]:
        """Convert internal messages to Vertex AI Content format.

        Args:
            messages: List of internal Message objects
            system_prompt: Optional system prompt to prepend

        Returns:
            List of Content objects for Vertex AI API
        """
        contents: list[Content] = []

        # Add system prompt as first user message if provided
        if system_prompt:
            if not system_prompt.strip():
                raise ValueError("system_prompt cannot be empty or whitespace-only")
            contents.append(Content(role="user", parts=[Part.from_text(system_prompt)]))

        # Convert each message
        for msg in messages:
            parts: list[Part] = []

            # Add text if present
            if msg.text:
                parts.append(Part.from_text(msg.text))

            # Add tool calls as text (for conversation history)
            # Note: Function calls generated BY the model are already properly formatted
            # in the response. This is for reconstructing conversation history.
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_text = f"[Function Call: {tc.name} with args {tc.arguments}]"
                    parts.append(Part.from_text(tool_text))

            # Add tool result if this is a tool message
            if msg.role == "tool" and msg.tool_name:
                # Tool results need to be in function_response format
                # The text field should contain the result as a dict
                result_dict = {"result": msg.text} if msg.text else {}
                parts.append(
                    Part.from_function_response(
                        name=msg.tool_name,
                        response=result_dict,
                    )
                )

            # Map role (tool -> user for Vertex AI)
            role = "user" if msg.role == "tool" else msg.role
            # Map assistant -> model for Vertex AI
            role = "model" if role == "assistant" else role

            contents.append(Content(role=role, parts=parts))

        return contents

    def _parse_response(self, response: GenerationResponse) -> LLMResponse:
        """Parse a GenerationResponse into an LLMResponse.

        Args:
            response: The response from the Vertex AI API

        Returns:
            Parsed LLMResponse

        Raises:
            LLMResponseError: If the response cannot be parsed
        """
        try:
            if not response.candidates:
                raise LLMResponseError("Response has no candidates")

            candidate = response.candidates[0]

            # Extract tool calls first
            tool_calls: list[ToolCall] = []
            if hasattr(candidate, "function_calls") and candidate.function_calls:
                for i, fc in enumerate(candidate.function_calls):
                    tool_call_id = f"{fc.name}_{i}"
                    tool_calls.append(
                        ToolCall(
                            id=tool_call_id,
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                    )

            # Extract text (may be None if only function calls)
            text: str | None = None
            try:
                text = candidate.text if candidate.text else None
            except (AttributeError, ValueError):
                # Expected when there are only function calls
                text = None

            # Extract token usage
            token_usage: dict[str, int] = {}
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                usage = response.usage_metadata
                if hasattr(usage, "prompt_token_count"):
                    token_usage["input_tokens"] = usage.prompt_token_count
                if hasattr(usage, "candidates_token_count"):
                    token_usage["output_tokens"] = usage.candidates_token_count
                if hasattr(usage, "total_token_count"):
                    token_usage["total_tokens"] = usage.total_token_count

            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                model_name=self.config.model_name,
                token_usage=token_usage,
            )

        except LLMResponseError:
            raise
        except Exception as e:
            raise LLMResponseError(f"Failed to parse Gemini response: {e}") from e

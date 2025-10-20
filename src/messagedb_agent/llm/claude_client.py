"""Claude LLM client implementation using Anthropic Vertex AI SDK.

This module provides a Claude-specific implementation of the BaseLLMClient
interface, using the AnthropicVertex SDK.
"""

from typing import Any

from anthropic import AnthropicVertex
from anthropic.types import Message as AnthropicMessage
from anthropic.types import MessageParam, TextBlock, ToolUseBlock

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


class ClaudeClient(BaseLLMClient):
    """Claude LLM client using AnthropicVertex SDK.

    This client implements the BaseLLMClient interface for Claude models
    available through Vertex AI, using the AnthropicVertex SDK.

    Attributes:
        config: Vertex AI configuration containing project, location, and model name
        _client: AnthropicVertex client instance (created after initialization)

    Example:
        >>> config = VertexAIConfig(
        ...     project="my-project",
        ...     location="us-central1",
        ...     model_name="claude-sonnet-4-5@20250929"
        ... )
        >>> client = ClaudeClient(config)
        >>> client.initialize()
        >>> response = client.call([Message(role="user", text="Hello!")])
    """

    def __init__(self, config: VertexAIConfig) -> None:
        """Initialize the Claude client.

        Args:
            config: Vertex AI configuration with project, location, and model name
        """
        self.config = config
        self._client: AnthropicVertex | None = None

    def initialize(self) -> None:
        """Initialize the AnthropicVertex client.

        This method must be called before making any LLM calls. It creates
        an AnthropicVertex client configured for the specified project and region.

        The method is idempotent - calling it multiple times has no effect
        after the first successful initialization.

        Raises:
            Exception: If client initialization fails
        """
        if self._client is not None:
            return

        # Create AnthropicVertex client
        # This automatically uses Application Default Credentials
        self._client = AnthropicVertex(
            project_id=self.config.project,
            region=self.config.location,
        )

    def call(
        self,
        messages: list[Message],
        tools: list[ToolDeclaration] | None = None,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Call the Claude LLM with the given messages and optional tools.

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
        if self._client is None:
            raise RuntimeError(
                "ClaudeClient must be initialized before calling. Call initialize()."
            )

        if not messages:
            raise ValueError("messages cannot be empty")

        try:
            # Convert messages to Anthropic format
            anthropic_messages = self._format_messages(messages)

            # Convert tools to Anthropic format
            anthropic_tools: list[dict[str, Any]] | None = None
            if tools:
                anthropic_tools = [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.parameters,
                    }
                    for tool in tools
                ]

            # Make API call
            # Claude API requires max_tokens parameter
            # Build kwargs for messages.create()
            create_kwargs: dict[str, Any] = {
                "model": self.config.model_name,
                "max_tokens": 4096,  # Default max tokens
                "messages": anthropic_messages,
            }
            if anthropic_tools:
                create_kwargs["tools"] = anthropic_tools
            if system_prompt:
                create_kwargs["system"] = system_prompt

            # Type ignore needed because **create_kwargs confuses the type checker
            response = self._client.messages.create(**create_kwargs)  # type: ignore[arg-type]

            # Parse response - response is AnthropicMessage
            return self._parse_response(response)  # type: ignore[arg-type]

        except (LLMAPIError, LLMResponseError):
            # Re-raise our own errors
            raise
        except Exception as e:
            # Wrap any other exceptions as LLMAPIError
            raise LLMAPIError(f"Claude API call failed: {e}") from e

    @property
    def model_name(self) -> str:
        """Get the configured model name.

        Returns:
            The Claude model name (e.g., "claude-sonnet-4-5@20250929")
        """
        return self.config.model_name

    def _format_messages(self, messages: list[Message]) -> list[MessageParam]:
        """Convert internal messages to Anthropic MessageParam format.

        Args:
            messages: List of internal Message objects

        Returns:
            List of MessageParam objects for Anthropic API

        Raises:
            ValueError: If message format is invalid
        """
        anthropic_messages: list[MessageParam] = []

        for msg in messages:
            # Handle user messages
            if msg.role == "user":
                if msg.text:
                    anthropic_messages.append({"role": "user", "content": msg.text})
                else:
                    raise ValueError("User messages must have text")

            # Handle assistant messages
            elif msg.role == "assistant":
                content: list[dict[str, Any]] = []

                # Add text content if present
                if msg.text:
                    content.append({"type": "text", "text": msg.text})

                # Add tool use blocks if present
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content.append(
                            {
                                "type": "tool_use",
                                "id": tc.id,
                                "name": tc.name,
                                "input": tc.arguments,
                            }
                        )

                if content:
                    # Type ignore needed - dict[str, Any] list is valid but type checker is strict
                    anthropic_messages.append({"role": "assistant", "content": content})  # type: ignore[typeddict-item]
                else:
                    raise ValueError("Assistant messages must have text or tool_calls")

            # Handle tool result messages
            elif msg.role == "tool":
                if not msg.tool_call_id or not msg.tool_name:
                    raise ValueError("Tool messages must have tool_call_id and tool_name")

                # Tool results are sent as user messages with tool_result content
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.text if msg.text else "",
                            }
                        ],
                    }
                )

            else:
                raise ValueError(f"Unsupported message role: {msg.role}")

        return anthropic_messages

    def _parse_response(self, response: AnthropicMessage) -> LLMResponse:
        """Parse an Anthropic Message response into an LLMResponse.

        Args:
            response: The response from the Anthropic API

        Returns:
            Parsed LLMResponse

        Raises:
            LLMResponseError: If the response cannot be parsed
        """
        try:
            text_parts: list[str] = []
            tool_calls: list[ToolCall] = []

            # Parse content blocks
            for block in response.content:
                if isinstance(block, TextBlock):
                    # Only append non-empty text to avoid empty strings
                    if block.text and block.text.strip():
                        text_parts.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    # Extract arguments from ToolUseBlock.input
                    # The input is a dict but type checker sees it as dict[Unknown, Unknown]
                    # Type ignore needed for unknown dict types from anthropic SDK
                    arguments: dict[str, Any] = (
                        dict(block.input) if isinstance(block.input, dict) else {}  # type: ignore[arg-type]
                    )
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=arguments,
                        )
                    )

            # Combine text parts
            text = " ".join(text_parts) if text_parts else None

            # Extract token usage
            token_usage: dict[str, int] = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

            return LLMResponse(
                text=text,
                tool_calls=tool_calls,
                model_name=self.config.model_name,
                token_usage=token_usage,
            )

        except Exception as e:
            raise LLMResponseError(f"Failed to parse Claude response: {e}") from e

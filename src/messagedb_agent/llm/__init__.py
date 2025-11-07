"""
LLM integration for agent execution.

This module provides integration with Vertex AI and other LLM providers,
supporting both Gemini and Claude models through a unified interface.

Usage:
    >>> from messagedb_agent.llm import create_llm_client, Message, ToolDeclaration
    >>> from messagedb_agent.config import VertexAIConfig
    >>>
    >>> config = VertexAIConfig(
    ...     project="...", location="...", model_name="claude-sonnet-4-5@20250929"
    ... )
    >>> client = create_llm_client(config)  # Auto-detects Gemini or Claude
    >>>
    >>> messages = [Message(role="user", text="Hello!")]
    >>> response = client.call(messages)
    >>> print(response.text)

System Prompts:
    >>> from messagedb_agent.llm import DEFAULT_SYSTEM_PROMPT, create_system_prompt
    >>> # Use default prompt
    >>> response = client.call(messages, system_prompt=DEFAULT_SYSTEM_PROMPT)
    >>> # Create custom prompt
    >>> custom_prompt = create_system_prompt(
    ...     additional_instructions="Focus on code quality",
    ...     available_tools=["lint", "format", "test"]
    ... )
"""

from messagedb_agent.llm.base import (
    BaseLLMClient,
    LLMAPIError,
    LLMError,
    LLMResponse,
    LLMResponseError,
    Message,
    StreamDelta,
    ToolCall,
    ToolDeclaration,
)
from messagedb_agent.llm.claude_client import ClaudeClient
from messagedb_agent.llm.factory import create_llm_client
from messagedb_agent.llm.gemini_client import GeminiClient
from messagedb_agent.llm.prompts import (
    DEFAULT_SYSTEM_PROMPT,
    MINIMAL_SYSTEM_PROMPT,
    TOOL_FOCUSED_SYSTEM_PROMPT,
    create_system_prompt,
    get_prompt_for_task,
)

__all__ = [
    # Client types
    "BaseLLMClient",
    "GeminiClient",
    "ClaudeClient",
    # Factory
    "create_llm_client",
    # Data types
    "Message",
    "ToolDeclaration",
    "LLMResponse",
    "ToolCall",
    "StreamDelta",
    # Errors
    "LLMError",
    "LLMAPIError",
    "LLMResponseError",
    # System prompts
    "DEFAULT_SYSTEM_PROMPT",
    "MINIMAL_SYSTEM_PROMPT",
    "TOOL_FOCUSED_SYSTEM_PROMPT",
    "create_system_prompt",
    "get_prompt_for_task",
]

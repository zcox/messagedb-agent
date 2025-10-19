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
"""

from messagedb_agent.llm.base import (
    BaseLLMClient,
    LLMAPIError,
    LLMError,
    LLMResponse,
    LLMResponseError,
    Message,
    ToolCall,
    ToolDeclaration,
)
from messagedb_agent.llm.claude_client import ClaudeClient
from messagedb_agent.llm.factory import create_llm_client
from messagedb_agent.llm.gemini_client import GeminiClient

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
    # Errors
    "LLMError",
    "LLMAPIError",
    "LLMResponseError",
]

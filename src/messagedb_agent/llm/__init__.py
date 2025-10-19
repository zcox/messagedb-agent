"""
LLM integration for agent execution.

This module provides integration with Vertex AI and other LLM providers,
supporting both Gemini and Claude models through a unified interface.

Recommended Usage (Unified API):
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

Legacy Usage (Gemini-only, deprecated):
    >>> from messagedb_agent.llm import (
    ...     create_client, call_llm, create_user_message, format_messages
    ... )
    >>> # This older API only works with Gemini models
"""

# New unified API (recommended)
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

# Legacy API (backward compatibility - Gemini only)
from messagedb_agent.llm.call import call_llm, create_function_declaration
from messagedb_agent.llm.claude_client import ClaudeClient
from messagedb_agent.llm.client import VertexAIClient, create_client
from messagedb_agent.llm.factory import create_llm_client
from messagedb_agent.llm.format import (
    create_function_response_message,
    create_model_message,
    create_user_message,
    format_messages,
)
from messagedb_agent.llm.gemini_client import GeminiClient

__all__ = [
    # New unified API (recommended)
    "BaseLLMClient",
    "GeminiClient",
    "ClaudeClient",
    "create_llm_client",
    "Message",
    "ToolDeclaration",
    "LLMResponse",
    "ToolCall",
    # Errors
    "LLMError",
    "LLMAPIError",
    "LLMResponseError",
    # Legacy API (backward compatibility - Gemini only)
    "VertexAIClient",
    "create_client",
    "format_messages",
    "create_user_message",
    "create_model_message",
    "create_function_response_message",
    "call_llm",
    "create_function_declaration",
]

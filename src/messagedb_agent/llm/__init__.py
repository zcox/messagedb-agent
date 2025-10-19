"""
LLM integration for agent execution.

This module provides integration with Vertex AI and other LLM providers,
including message formatting and response handling.
"""

from messagedb_agent.llm.call import (
    LLMAPIError,
    LLMError,
    LLMResponse,
    LLMResponseError,
    ToolCall,
    call_llm,
    create_function_declaration,
)
from messagedb_agent.llm.client import VertexAIClient, create_client
from messagedb_agent.llm.format import (
    Message,
    create_function_response_message,
    create_model_message,
    create_user_message,
    format_messages,
)

__all__ = [
    # Client
    "VertexAIClient",
    "create_client",
    # Message formatting
    "Message",
    "format_messages",
    "create_user_message",
    "create_model_message",
    "create_function_response_message",
    # LLM calling
    "call_llm",
    "create_function_declaration",
    "LLMResponse",
    "ToolCall",
    # Errors
    "LLMError",
    "LLMAPIError",
    "LLMResponseError",
]

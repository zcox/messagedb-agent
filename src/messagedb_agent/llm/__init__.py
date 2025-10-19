"""
LLM integration for agent execution.

This module provides integration with Vertex AI and other LLM providers,
including message formatting and response handling.
"""

from messagedb_agent.llm.client import VertexAIClient, create_client
from messagedb_agent.llm.format import (
    Message,
    create_function_response_message,
    create_model_message,
    create_user_message,
    format_messages,
)

__all__ = [
    "VertexAIClient",
    "create_client",
    "Message",
    "format_messages",
    "create_user_message",
    "create_model_message",
    "create_function_response_message",
]

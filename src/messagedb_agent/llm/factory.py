"""Factory functions for creating LLM clients.

This module provides factory functions to automatically create the appropriate
LLM client (Gemini or Claude) based on the model name.
"""

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.llm.base import BaseLLMClient
from messagedb_agent.llm.claude_client import ClaudeClient
from messagedb_agent.llm.gemini_client import GeminiClient


def create_llm_client(config: VertexAIConfig) -> BaseLLMClient:
    """Create and initialize the appropriate LLM client based on model name.

    This factory function examines the model name and automatically creates
    either a GeminiClient or ClaudeClient, then initializes it.

    Args:
        config: Vertex AI configuration with project, location, and model name

    Returns:
        Initialized LLM client (GeminiClient or ClaudeClient)

    Raises:
        ValueError: If model name is not recognized
        Exception: If client initialization fails

    Example:
        >>> config = VertexAIConfig(
        ...     project="my-project",
        ...     location="us-central1",
        ...     model_name="claude-sonnet-4-5@20250929"
        ... )
        >>> client = create_llm_client(config)
        >>> # Client is ready to use - automatically chose ClaudeClient
        >>> response = client.call([Message(role="user", text="Hello!")])
    """
    model_name = config.model_name.lower()

    # Determine which client to use based on model name
    if "claude" in model_name:
        client: BaseLLMClient = ClaudeClient(config)
    elif "gemini" in model_name:
        client = GeminiClient(config)
    else:
        raise ValueError(
            f"Unsupported model: {config.model_name}. "
            "Supported models: Gemini (gemini-*) and Claude (claude-*)"
        )

    # Initialize and return
    # Both GeminiClient and ClaudeClient have initialize() method
    client.initialize()
    return client

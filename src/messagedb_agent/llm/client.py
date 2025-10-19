"""Vertex AI client for LLM integration.

This module provides a unified client interface for interacting with Vertex AI,
supporting both Gemini models and Claude models via the Vertex AI API.
It uses Application Default Credentials (ADC) for authentication.
"""

import vertexai
from google.auth import default  # type: ignore[import-untyped]
from vertexai.generative_models import GenerativeModel

from messagedb_agent.config import VertexAIConfig


class VertexAIClient:
    """Client for interacting with Vertex AI models.

    This client provides a unified interface for calling LLMs via Vertex AI,
    supporting both Gemini models (e.g., gemini-2.5-pro) and Claude models
    (e.g., claude-sonnet-4-5@20250929) through the Anthropic on Vertex AI integration.

    Authentication uses Application Default Credentials (ADC). Ensure you have
    authenticated via `gcloud auth application-default login` or are running
    in an environment with ADC configured (e.g., GCE, Cloud Run).

    Attributes:
        config: Vertex AI configuration containing project, location, and model name
        _initialized: Whether the Vertex AI SDK has been initialized

    Example:
        >>> config = VertexAIConfig(
        ...     project="my-project",
        ...     location="us-central1",
        ...     model_name="claude-sonnet-4-5@20250929"
        ... )
        >>> client = VertexAIClient(config)
        >>> # Use client for LLM calls...
    """

    def __init__(self, config: VertexAIConfig) -> None:
        """Initialize the Vertex AI client.

        Args:
            config: Vertex AI configuration with project, location, and model name

        Example:
            >>> config = VertexAIConfig(
            ...     project="my-project",
            ...     location="us-central1",
            ...     model_name="gemini-2.5-pro"
            ... )
            >>> client = VertexAIClient(config)
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

        Example:
            >>> client = VertexAIClient(config)
            >>> client.initialize()  # Must call before making LLM calls
        """
        if self._initialized:
            return

        # Use Application Default Credentials
        # This will work if user has run: gcloud auth application-default login
        # or if running in GCP environment (GCE, Cloud Run, etc.)
        credentials, _ = default()  # type: ignore[reportUnknownVariableType]

        # Initialize Vertex AI with the configured project and location
        # Note: We use self.config.project rather than the detected project
        # to allow explicit project specification
        # Type ignore needed because google.auth.default() returns a union type
        # that is compatible with Credentials but basedpyright can't infer it
        vertexai.init(
            project=self.config.project,
            location=self.config.location,
            credentials=credentials,  # type: ignore[arg-type]
        )

        self._initialized = True

    def get_model(self) -> GenerativeModel:
        """Get a GenerativeModel instance for the configured model.

        This method returns a GenerativeModel instance that can be used to
        generate content. It ensures the SDK is initialized before creating
        the model.

        Returns:
            GenerativeModel instance configured with the specified model name

        Raises:
            RuntimeError: If called before initialize()

        Example:
            >>> client = VertexAIClient(config)
            >>> client.initialize()
            >>> model = client.get_model()
            >>> # Use model to generate content...
        """
        if not self._initialized:
            raise RuntimeError(
                "VertexAIClient must be initialized before getting a model. "
                "Call client.initialize() first."
            )

        return GenerativeModel(self.config.model_name)

    @property
    def model_name(self) -> str:
        """Get the configured model name.

        Returns:
            The model name (e.g., "claude-sonnet-4-5@20250929", "gemini-2.5-pro")

        Example:
            >>> client = VertexAIClient(config)
            >>> print(client.model_name)
            claude-sonnet-4-5@20250929
        """
        return self.config.model_name

    @property
    def project(self) -> str:
        """Get the configured GCP project ID.

        Returns:
            The GCP project ID

        Example:
            >>> client = VertexAIClient(config)
            >>> print(client.project)
            my-project
        """
        return self.config.project

    @property
    def location(self) -> str:
        """Get the configured GCP location.

        Returns:
            The GCP location/region (e.g., "us-central1")

        Example:
            >>> client = VertexAIClient(config)
            >>> print(client.location)
            us-central1
        """
        return self.config.location


def create_client(config: VertexAIConfig) -> VertexAIClient:
    """Factory function to create and initialize a Vertex AI client.

    This is a convenience function that creates a VertexAIClient and
    initializes it in one step.

    Args:
        config: Vertex AI configuration with project, location, and model name

    Returns:
        Initialized VertexAIClient ready for use

    Raises:
        google.auth.exceptions.DefaultCredentialsError: If ADC is not configured
        Exception: If Vertex AI initialization fails

    Example:
        >>> config = VertexAIConfig(
        ...     project="my-project",
        ...     location="us-central1",
        ...     model_name="claude-sonnet-4-5@20250929"
        ... )
        >>> client = create_client(config)
        >>> model = client.get_model()  # Ready to use
    """
    client = VertexAIClient(config)
    client.initialize()
    return client

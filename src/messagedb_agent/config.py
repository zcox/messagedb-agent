"""Configuration management for the event-sourced agent system.

This module handles loading and validating configuration from environment
variables. It provides type-safe configuration for Message DB connection,
Vertex AI integration, and processing engine settings.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class MessageDBConfig:
    """Configuration for Message DB connection.

    Attributes:
        host: PostgreSQL host (default: localhost)
        port: PostgreSQL port (default: 5432)
        database: Database name (default: message_store)
        user: Database user (required)
        password: Database password (required)

    Example:
        >>> config = MessageDBConfig(
        ...     host="localhost",
        ...     port=5432,
        ...     database="message_store",
        ...     user="postgres",
        ...     password="secret"
        ... )
    """

    host: str
    port: int
    database: str
    user: str
    password: str

    def __post_init__(self) -> None:
        """Validate Message DB configuration after initialization.

        Raises:
            ValueError: If required fields are empty or invalid
        """
        if not self.host or not self.host.strip():
            raise ValueError("Message DB host cannot be empty")
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Message DB port must be 1-65535, got {self.port}")
        if not self.database or not self.database.strip():
            raise ValueError("Message DB database cannot be empty")
        if not self.user or not self.user.strip():
            raise ValueError("Message DB user cannot be empty")
        if not self.password:
            raise ValueError("Message DB password cannot be empty")


@dataclass(frozen=True)
class VertexAIConfig:
    """Configuration for Vertex AI integration.

    Attributes:
        project: GCP project ID (required)
        location: GCP region/location (e.g., us-central1, default: us-central1)
        model_name: Model name (e.g., gemini-2.5-pro, claude-sonnet-4-5@20250929)

    Example:
        >>> config = VertexAIConfig(
        ...     project="my-gcp-project",
        ...     location="us-central1",
        ...     model_name="claude-sonnet-4-5@20250929"
        ... )
    """

    project: str
    location: str
    model_name: str

    def __post_init__(self) -> None:
        """Validate Vertex AI configuration after initialization.

        Raises:
            ValueError: If required fields are empty or invalid
        """
        if not self.project or not self.project.strip():
            raise ValueError("GCP project cannot be empty")
        if not self.location or not self.location.strip():
            raise ValueError("GCP location cannot be empty")
        if not self.model_name or not self.model_name.strip():
            raise ValueError("Model name cannot be empty")


@dataclass(frozen=True)
class ProcessingConfig:
    """Configuration for processing engine.

    Attributes:
        max_iterations: Maximum number of processing loop iterations (default: 100)
        enable_tracing: Whether to enable OpenTelemetry tracing (default: False)

    Example:
        >>> config = ProcessingConfig(max_iterations=100, enable_tracing=True)
    """

    max_iterations: int
    enable_tracing: bool

    def __post_init__(self) -> None:
        """Validate processing configuration after initialization.

        Raises:
            ValueError: If max_iterations is invalid
        """
        if self.max_iterations <= 0:
            raise ValueError(f"max_iterations must be > 0, got {self.max_iterations}")


@dataclass(frozen=True)
class LoggingConfig:
    """Configuration for logging.

    Attributes:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Log format (json, text)

    Example:
        >>> config = LoggingConfig(log_level="INFO", log_format="json")
    """

    log_level: str
    log_format: str

    def __post_init__(self) -> None:
        """Validate logging configuration after initialization.

        Raises:
            ValueError: If log_level or log_format is invalid
        """
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}, got {self.log_level}")

        valid_formats = {"json", "text"}
        if self.log_format.lower() not in valid_formats:
            raise ValueError(f"log_format must be one of {valid_formats}, got {self.log_format}")


@dataclass(frozen=True)
class Config:
    """Complete configuration for the event-sourced agent system.

    This is the top-level configuration object that combines all sub-configurations.

    Attributes:
        message_db: Message DB connection configuration
        vertex_ai: Vertex AI integration configuration
        processing: Processing engine configuration
        logging: Logging configuration

    Example:
        >>> config = load_config()
        >>> print(config.message_db.host)
        >>> print(config.vertex_ai.model_name)
    """

    message_db: MessageDBConfig
    vertex_ai: VertexAIConfig
    processing: ProcessingConfig
    logging: LoggingConfig


def load_config(env_file: str | None = None) -> Config:
    """Load configuration from environment variables.

    This function loads environment variables (optionally from a .env file)
    and constructs a complete Config object with all necessary settings.

    Args:
        env_file: Optional path to .env file to load (default: .env in current directory)

    Returns:
        Complete Config object with all sub-configurations

    Raises:
        ValueError: If required environment variables are missing or invalid

    Environment Variables:
        Message DB:
            - DB_HOST: PostgreSQL host (default: localhost)
            - DB_PORT: PostgreSQL port (default: 5432)
            - DB_NAME: Database name (default: message_store)
            - DB_USER: Database user (required)
            - DB_PASSWORD: Database password (required)

        Vertex AI:
            - GCP_PROJECT: GCP project ID (required)
            - GCP_LOCATION: GCP region (default: us-central1)
            - MODEL_NAME: Model name (default: claude-sonnet-4-5@20250929)

        Processing:
            - MAX_ITERATIONS: Max processing loop iterations (default: 100)
            - ENABLE_TRACING: Enable OpenTelemetry tracing (default: false)

        Logging:
            - LOG_LEVEL: Logging level (default: INFO)
            - LOG_FORMAT: Log format (default: json)

    Example:
        >>> config = load_config()  # Loads from .env
        >>> config = load_config(".env.test")  # Loads from custom file
    """
    # Load environment variables from .env file if it exists
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    # Message DB configuration
    message_db = MessageDBConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "message_store"),
        user=_get_required_env("DB_USER"),
        password=_get_required_env("DB_PASSWORD"),
    )

    # Vertex AI configuration
    vertex_ai = VertexAIConfig(
        project=_get_required_env("GCP_PROJECT"),
        location=os.getenv("GCP_LOCATION", "us-central1"),
        model_name=os.getenv("MODEL_NAME", "claude-sonnet-4-5@20250929"),
    )

    # Processing configuration
    processing = ProcessingConfig(
        max_iterations=int(os.getenv("MAX_ITERATIONS", "100")),
        enable_tracing=os.getenv("ENABLE_TRACING", "false").lower() == "true",
    )

    # Logging configuration
    logging = LoggingConfig(
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        log_format=os.getenv("LOG_FORMAT", "json").lower(),
    )

    return Config(
        message_db=message_db,
        vertex_ai=vertex_ai,
        processing=processing,
        logging=logging,
    )


def _get_required_env(var_name: str) -> str:
    """Get a required environment variable or raise an error.

    Args:
        var_name: Name of the environment variable

    Returns:
        Value of the environment variable

    Raises:
        ValueError: If the environment variable is not set
    """
    value = os.getenv(var_name)
    if value is None:
        raise ValueError(
            f"Required environment variable {var_name} is not set. "
            f"Please set it in your environment or .env file."
        )
    return value

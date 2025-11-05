"""Tests for configuration module."""

import pytest

from messagedb_agent.config import (
    Config,
    LoggingConfig,
    MessageDBConfig,
    ProcessingConfig,
    VertexAIConfig,
    load_config,
)


class TestMessageDBConfig:
    """Tests for MessageDBConfig."""

    def test_create_messagedb_config(self):
        """MessageDBConfig can be created with valid parameters."""
        config = MessageDBConfig(
            host="localhost",
            port=5432,
            database="message_store",
            user="postgres",
            password="secret",
        )

        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "message_store"
        assert config.user == "postgres"
        assert config.password == "secret"

    def test_messagedb_config_is_immutable(self):
        """MessageDBConfig instances are immutable (frozen)."""
        config = MessageDBConfig(
            host="localhost",
            port=5432,
            database="message_store",
            user="postgres",
            password="secret",
        )

        with pytest.raises(AttributeError):
            config.host = "newhost"  # type: ignore

    def test_messagedb_config_validates_empty_host(self):
        """MessageDBConfig raises ValueError for empty host."""
        with pytest.raises(ValueError, match="Message DB host cannot be empty"):
            MessageDBConfig(
                host="", port=5432, database="message_store", user="postgres", password="secret"
            )

    def test_messagedb_config_validates_whitespace_only_host(self):
        """MessageDBConfig raises ValueError for whitespace-only host."""
        with pytest.raises(ValueError, match="Message DB host cannot be empty"):
            MessageDBConfig(
                host="   ",
                port=5432,
                database="message_store",
                user="postgres",
                password="secret",
            )

    def test_messagedb_config_validates_port_too_low(self):
        """MessageDBConfig raises ValueError for port <= 0."""
        with pytest.raises(ValueError, match="Message DB port must be 1-65535"):
            MessageDBConfig(
                host="localhost",
                port=0,
                database="message_store",
                user="postgres",
                password="secret",
            )

    def test_messagedb_config_validates_port_too_high(self):
        """MessageDBConfig raises ValueError for port > 65535."""
        with pytest.raises(ValueError, match="Message DB port must be 1-65535"):
            MessageDBConfig(
                host="localhost",
                port=65536,
                database="message_store",
                user="postgres",
                password="secret",
            )

    def test_messagedb_config_validates_empty_database(self):
        """MessageDBConfig raises ValueError for empty database."""
        with pytest.raises(ValueError, match="Message DB database cannot be empty"):
            MessageDBConfig(
                host="localhost", port=5432, database="", user="postgres", password="secret"
            )

    def test_messagedb_config_validates_empty_user(self):
        """MessageDBConfig raises ValueError for empty user."""
        with pytest.raises(ValueError, match="Message DB user cannot be empty"):
            MessageDBConfig(
                host="localhost",
                port=5432,
                database="message_store",
                user="",
                password="secret",
            )

    def test_messagedb_config_validates_empty_password(self):
        """MessageDBConfig raises ValueError for empty password."""
        with pytest.raises(ValueError, match="Message DB password cannot be empty"):
            MessageDBConfig(
                host="localhost",
                port=5432,
                database="message_store",
                user="postgres",
                password="",
            )

    def test_messagedb_config_with_custom_port(self):
        """MessageDBConfig accepts custom port."""
        config = MessageDBConfig(
            host="localhost",
            port=5433,
            database="message_store",
            user="postgres",
            password="secret",
        )

        assert config.port == 5433


class TestVertexAIConfig:
    """Tests for VertexAIConfig."""

    def test_create_vertexai_config(self):
        """VertexAIConfig can be created with valid parameters."""
        config = VertexAIConfig(
            project="my-project", location="us-central1", model_name="claude-sonnet-4-5@20250929"
        )

        assert config.project == "my-project"
        assert config.location == "us-central1"
        assert config.model_name == "claude-sonnet-4-5@20250929"

    def test_vertexai_config_is_immutable(self):
        """VertexAIConfig instances are immutable (frozen)."""
        config = VertexAIConfig(
            project="my-project", location="us-central1", model_name="claude-sonnet-4-5"
        )

        with pytest.raises(AttributeError):
            config.project = "new-project"  # type: ignore

    def test_vertexai_config_validates_empty_project(self):
        """VertexAIConfig raises ValueError for empty project."""
        with pytest.raises(ValueError, match="GCP project cannot be empty"):
            VertexAIConfig(project="", location="us-central1", model_name="claude-sonnet-4-5")

    def test_vertexai_config_validates_empty_location(self):
        """VertexAIConfig raises ValueError for empty location."""
        with pytest.raises(ValueError, match="GCP location cannot be empty"):
            VertexAIConfig(project="my-project", location="", model_name="claude-sonnet-4-5")

    def test_vertexai_config_validates_empty_model_name(self):
        """VertexAIConfig raises ValueError for empty model_name."""
        with pytest.raises(ValueError, match="Model name cannot be empty"):
            VertexAIConfig(project="my-project", location="us-central1", model_name="")

    def test_vertexai_config_with_gemini_model(self):
        """VertexAIConfig works with Gemini models."""
        config = VertexAIConfig(
            project="my-project", location="us-central1", model_name="gemini-2.5-pro"
        )

        assert config.model_name == "gemini-2.5-pro"


class TestProcessingConfig:
    """Tests for ProcessingConfig."""

    def test_create_processing_config(self):
        """ProcessingConfig can be created with valid parameters."""
        config = ProcessingConfig(max_iterations=100, enable_tracing=True)

        assert config.max_iterations == 100
        assert config.enable_tracing is True

    def test_processing_config_is_immutable(self):
        """ProcessingConfig instances are immutable (frozen)."""
        config = ProcessingConfig(max_iterations=100, enable_tracing=False)

        with pytest.raises(AttributeError):
            config.max_iterations = 200  # type: ignore

    def test_processing_config_validates_max_iterations_zero(self):
        """ProcessingConfig raises ValueError for max_iterations = 0."""
        with pytest.raises(ValueError, match="max_iterations must be > 0"):
            ProcessingConfig(max_iterations=0, enable_tracing=False)

    def test_processing_config_validates_max_iterations_negative(self):
        """ProcessingConfig raises ValueError for negative max_iterations."""
        with pytest.raises(ValueError, match="max_iterations must be > 0"):
            ProcessingConfig(max_iterations=-1, enable_tracing=False)

    def test_processing_config_with_tracing_disabled(self):
        """ProcessingConfig can be created with tracing disabled."""
        config = ProcessingConfig(max_iterations=50, enable_tracing=False)

        assert config.enable_tracing is False


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_create_logging_config(self):
        """LoggingConfig can be created with valid parameters."""
        config = LoggingConfig(log_level="INFO", log_format="json")

        assert config.log_level == "INFO"
        assert config.log_format == "json"

    def test_logging_config_is_immutable(self):
        """LoggingConfig instances are immutable (frozen)."""
        config = LoggingConfig(log_level="INFO", log_format="json")

        with pytest.raises(AttributeError):
            config.log_level = "DEBUG"  # type: ignore

    def test_logging_config_validates_invalid_log_level(self):
        """LoggingConfig raises ValueError for invalid log_level."""
        with pytest.raises(ValueError, match="log_level must be one of"):
            LoggingConfig(log_level="INVALID", log_format="json")

    def test_logging_config_validates_invalid_log_format(self):
        """LoggingConfig raises ValueError for invalid log_format."""
        with pytest.raises(ValueError, match="log_format must be one of"):
            LoggingConfig(log_level="INFO", log_format="invalid")

    def test_logging_config_with_various_log_levels(self):
        """LoggingConfig accepts all valid log levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

        for level in valid_levels:
            config = LoggingConfig(log_level=level, log_format="json")
            assert config.log_level == level

    def test_logging_config_normalizes_case(self):
        """LoggingConfig accepts lowercase log levels."""
        config = LoggingConfig(log_level="info", log_format="json")
        # Validation should pass with case-insensitive check
        assert config.log_level == "info"

    def test_logging_config_with_text_format(self):
        """LoggingConfig accepts text format."""
        config = LoggingConfig(log_level="INFO", log_format="text")

        assert config.log_format == "text"


class TestConfig:
    """Tests for main Config class."""

    def test_create_config(self):
        """Config can be created with all sub-configurations."""
        message_db = MessageDBConfig(
            host="localhost",
            port=5432,
            database="message_store",
            user="postgres",
            password="secret",
        )
        vertex_ai = VertexAIConfig(
            project="my-project", location="us-central1", model_name="claude-sonnet-4-5"
        )
        processing = ProcessingConfig(max_iterations=100, enable_tracing=False)
        logging = LoggingConfig(log_level="INFO", log_format="json")

        config = Config(
            message_db=message_db, vertex_ai=vertex_ai, processing=processing, logging=logging
        )

        assert config.message_db == message_db
        assert config.vertex_ai == vertex_ai
        assert config.processing == processing
        assert config.logging == logging

    def test_config_is_immutable(self):
        """Config instances are immutable (frozen)."""
        message_db = MessageDBConfig(
            host="localhost",
            port=5432,
            database="message_store",
            user="postgres",
            password="secret",
        )
        vertex_ai = VertexAIConfig(
            project="my-project", location="us-central1", model_name="claude-sonnet-4-5"
        )
        processing = ProcessingConfig(max_iterations=100, enable_tracing=False)
        logging = LoggingConfig(log_level="INFO", log_format="json")

        config = Config(
            message_db=message_db, vertex_ai=vertex_ai, processing=processing, logging=logging
        )

        with pytest.raises(AttributeError):
            config.message_db = message_db  # type: ignore


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_with_all_env_vars(self, monkeypatch):
        """load_config creates Config from environment variables."""
        # Set all required environment variables
        monkeypatch.setenv("DB_HOST", "testhost")
        monkeypatch.setenv("DB_PORT", "5433")
        monkeypatch.setenv("DB_NAME", "test_db")
        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("GCP_PROJECT", "test-project")
        monkeypatch.setenv("GCP_LOCATION", "us-west1")
        monkeypatch.setenv("MODEL_NAME", "gemini-2.5-pro")
        monkeypatch.setenv("MAX_ITERATIONS", "50")
        monkeypatch.setenv("ENABLE_TRACING", "true")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("LOG_FORMAT", "text")

        # Pass empty env_file to prevent loading from .env
        config = load_config(env_file="/dev/null")

        assert config.message_db.host == "testhost"
        assert config.message_db.port == 5433
        assert config.message_db.database == "test_db"
        assert config.message_db.user == "testuser"
        assert config.message_db.password == "testpass"
        assert config.vertex_ai.project == "test-project"
        assert config.vertex_ai.location == "us-west1"
        assert config.vertex_ai.model_name == "gemini-2.5-pro"
        assert config.processing.max_iterations == 50
        assert config.processing.enable_tracing is True
        assert config.logging.log_level == "DEBUG"
        assert config.logging.log_format == "text"

    def test_load_config_with_defaults(self, monkeypatch):
        """load_config uses defaults for optional environment variables."""
        # Clear ALL environment variables that load_config uses
        monkeypatch.delenv("DB_HOST", raising=False)
        monkeypatch.delenv("DB_PORT", raising=False)
        monkeypatch.delenv("DB_NAME", raising=False)
        monkeypatch.delenv("GCP_LOCATION", raising=False)
        monkeypatch.delenv("MODEL_NAME", raising=False)
        monkeypatch.delenv("MAX_ITERATIONS", raising=False)
        monkeypatch.delenv("ENABLE_TRACING", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("LOG_FORMAT", raising=False)
        monkeypatch.delenv("AUTO_APPROVE_TOOLS", raising=False)
        monkeypatch.delenv("APPROVAL_TIMEOUT_SECONDS", raising=False)

        # Set only required variables
        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        # Pass empty env_file to prevent loading from .env
        config = load_config(env_file="/dev/null")

        # Check defaults
        assert config.message_db.host == "localhost"
        assert config.message_db.port == 5432
        assert config.message_db.database == "message_store"
        assert config.vertex_ai.location == "us-central1"
        assert config.vertex_ai.model_name == "claude-sonnet-4-5@20250929"
        assert config.processing.max_iterations == 100
        assert config.processing.enable_tracing is False
        assert config.logging.log_level == "INFO"
        assert config.logging.log_format == "json"

    def test_load_config_missing_db_user(self, monkeypatch):
        """load_config raises ValueError if DB_USER is missing."""
        # Clear DB_USER to ensure it's not loaded from .env
        monkeypatch.delenv("DB_USER", raising=False)
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        # Pass empty env_file to prevent loading from .env
        with pytest.raises(ValueError, match="Required environment variable DB_USER"):
            load_config(env_file="/dev/null")

    def test_load_config_missing_db_password(self, monkeypatch):
        """load_config raises ValueError if DB_PASSWORD is missing."""
        # Clear DB_PASSWORD to ensure it's not loaded from .env
        monkeypatch.delenv("DB_PASSWORD", raising=False)
        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("GCP_PROJECT", "test-project")

        # Pass empty env_file to prevent loading from .env
        with pytest.raises(ValueError, match="Required environment variable DB_PASSWORD"):
            load_config(env_file="/dev/null")

    def test_load_config_missing_gcp_project(self, monkeypatch):
        """load_config raises ValueError if GCP_PROJECT is missing."""
        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")

        # Ensure GCP_PROJECT is not set
        monkeypatch.delenv("GCP_PROJECT", raising=False)

        # Pass empty env_file to prevent loading from .env
        with pytest.raises(ValueError, match="Required environment variable GCP_PROJECT"):
            load_config(env_file="/dev/null")

    def test_load_config_enable_tracing_false(self, monkeypatch):
        """load_config parses ENABLE_TRACING=false correctly."""
        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("GCP_PROJECT", "test-project")
        monkeypatch.setenv("ENABLE_TRACING", "false")

        # Pass empty env_file to prevent loading from .env
        config = load_config(env_file="/dev/null")

        assert config.processing.enable_tracing is False

    def test_load_config_enable_tracing_invalid(self, monkeypatch):
        """load_config treats non-'true' ENABLE_TRACING as false."""
        monkeypatch.setenv("DB_USER", "testuser")
        monkeypatch.setenv("DB_PASSWORD", "testpass")
        monkeypatch.setenv("GCP_PROJECT", "test-project")
        monkeypatch.setenv("ENABLE_TRACING", "maybe")

        # Pass empty env_file to prevent loading from .env
        config = load_config(env_file="/dev/null")

        assert config.processing.enable_tracing is False

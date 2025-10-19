"""Message DB client for event store operations.

This module provides a client for connecting to and interacting with Message DB,
a PostgreSQL-based event store.
"""

import os
from typing import Optional

import structlog
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

logger = structlog.get_logger(__name__)


class MessageDBConfig:
    """Configuration for Message DB connection.

    Loads configuration from environment variables with sensible defaults.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        min_size: int = 2,
        max_size: int = 10,
    ) -> None:
        """Initialize Message DB configuration.

        Args:
            host: Database host (defaults to DB_HOST env var or 'localhost')
            port: Database port (defaults to DB_PORT env var or 5432)
            database: Database name (defaults to DB_NAME env var or 'message_store')
            user: Database user (defaults to DB_USER env var or 'message_store')
            password: Database password (defaults to DB_PASSWORD env var or empty string)
            min_size: Minimum pool size (default: 2)
            max_size: Maximum pool size (default: 10)
        """
        self.host = host or os.getenv("DB_HOST", "localhost")
        self.port = port or int(os.getenv("DB_PORT", "5432"))
        self.database = database or os.getenv("DB_NAME", "message_store")
        self.user = user or os.getenv("DB_USER", "message_store")
        self.password = password or os.getenv("DB_PASSWORD", "")
        self.min_size = min_size
        self.max_size = max_size

    def to_connection_string(self) -> str:
        """Generate PostgreSQL connection string.

        Returns:
            Connection string in DSN format
        """
        return (
            f"host={self.host} "
            f"port={self.port} "
            f"dbname={self.database} "
            f"user={self.user} "
            f"password={self.password}"
        )

    def validate(self) -> None:
        """Validate that required configuration is present.

        Raises:
            ValueError: If required configuration is missing
        """
        if not self.host:
            raise ValueError("Database host is required")
        if not self.database:
            raise ValueError("Database name is required")
        if not self.user:
            raise ValueError("Database user is required")


class MessageDBClient:
    """Client for interacting with Message DB event store.

    This client provides connection pooling, automatic connection management,
    and health check capabilities for Message DB operations.

    Example:
        ```python
        # Using as context manager
        config = MessageDBConfig()
        with MessageDBClient(config) as client:
            client.health_check()
            # Use client for operations

        # Manual lifecycle management
        client = MessageDBClient(config)
        client.connect()
        try:
            client.health_check()
            # Use client
        finally:
            client.close()
        ```
    """

    def __init__(self, config: MessageDBConfig) -> None:
        """Initialize Message DB client.

        Args:
            config: Message DB configuration
        """
        self.config = config
        self.config.validate()
        self._pool: Optional[ConnectionPool] = None
        self._logger = logger.bind(
            db_host=config.host,
            db_port=config.port,
            db_name=config.database,
        )

    def connect(self) -> None:
        """Establish connection pool to Message DB.

        Creates a connection pool with the configured min/max size.

        Raises:
            psycopg.OperationalError: If connection cannot be established
        """
        if self._pool is not None:
            self._logger.warning("Connection pool already exists, skipping connect")
            return

        conninfo = self.config.to_connection_string()
        self._logger.info(
            "Creating connection pool",
            min_size=self.config.min_size,
            max_size=self.config.max_size,
        )

        self._pool = ConnectionPool(
            conninfo=conninfo,
            min_size=self.config.min_size,
            max_size=self.config.max_size,
            kwargs={"row_factory": dict_row},  # Return results as dictionaries
        )

        self._logger.info("Connection pool created successfully")

    def close(self) -> None:
        """Close the connection pool and release all connections.

        This should be called when the client is no longer needed to properly
        release database resources.
        """
        if self._pool is not None:
            self._logger.info("Closing connection pool")
            self._pool.close()
            self._pool = None
            self._logger.info("Connection pool closed")

    def get_connection(self) -> Connection:
        """Get a connection from the pool.

        Returns:
            A database connection from the pool

        Raises:
            RuntimeError: If connection pool is not initialized
            psycopg.OperationalError: If connection cannot be acquired
        """
        if self._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. Call connect() first or use as context manager."
            )
        return self._pool.getconn()

    def return_connection(self, conn: Connection) -> None:
        """Return a connection to the pool.

        Args:
            conn: Connection to return to the pool
        """
        if self._pool is not None:
            self._pool.putconn(conn)

    def health_check(self) -> bool:
        """Check if the database connection is healthy.

        Performs a simple query to verify database connectivity and that
        Message DB functions are available.

        Returns:
            True if connection is healthy and Message DB is accessible

        Raises:
            RuntimeError: If connection pool is not initialized
            psycopg.Error: If database query fails
        """
        self._logger.info("Performing health check")

        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                # Check basic connectivity
                cur.execute("SELECT 1 as health")
                result = cur.fetchone()
                if result is None or result.get("health") != 1:
                    self._logger.error("Health check failed: unexpected result")
                    return False

                # Check that Message DB functions exist
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_proc
                        WHERE proname = 'write_message'
                    ) as has_write_message
                    """
                )
                result = cur.fetchone()
                if result is None or not result.get("has_write_message"):
                    self._logger.error(
                        "Health check failed: write_message function not found. "
                        "Is Message DB installed?"
                    )
                    return False

                self._logger.info("Health check passed")
                return True
        finally:
            self.return_connection(conn)

    def __enter__(self) -> "MessageDBClient":
        """Enter context manager - establish connection pool.

        Returns:
            Self for use in with statement
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Exit context manager - close connection pool.

        Args:
            exc_type: Exception type if an exception occurred
            exc_val: Exception value if an exception occurred
            exc_tb: Exception traceback if an exception occurred
        """
        self.close()

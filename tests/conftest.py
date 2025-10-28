"""Pytest configuration and fixtures for testing.

This module provides pytest fixtures for:
- Message DB Docker container management
- Database connection configuration
- Test database cleanup
"""

import os

import psycopg
import pytest

from messagedb_agent.store import MessageDBClient, MessageDBConfig


@pytest.fixture(scope="session")
def docker_compose_file():
    """Return the path to the docker-compose.yml file."""
    return os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")


@pytest.fixture(scope="session")
def docker_setup():
    """Override docker setup to not use --build flag."""
    return ["up -d"]


@pytest.fixture(scope="session")
def docker_cleanup():
    """Override docker cleanup to not delete volumes.

    Default is 'down -v' which deletes volumes and causes database to be reset.
    We just want 'down' to preserve the initialized database.
    """
    return ["down"]


@pytest.fixture(scope="session")
def messagedb_service(docker_services):
    """Start Message DB container and wait for it to be ready.

    This fixture starts the Message DB Docker container and waits for it
    to accept connections and for Message DB to be fully installed before running tests.
    """
    # Wait for Message DB to be ready
    # Container initializes in ~8 seconds
    docker_services.wait_until_responsive(
        timeout=30.0, pause=0.5, check=lambda: is_messagedb_responsive()
    )
    return "messagedb"


def is_messagedb_responsive():
    """Check if Message DB is responsive and fully installed.

    Returns:
        True if Message DB accepts connections and has functions installed, False otherwise.
    """
    import time

    try:
        # Use a direct connection (not connection pool) for health check
        # Connection pool creation was causing delays
        conninfo = (
            "host=localhost port=5433 "
            "dbname=message_store user=postgres password=message_store_password"
        )
        with psycopg.connect(conninfo) as conn:
            with conn.cursor() as cur:
                # Check basic connectivity
                cur.execute("SELECT 1")
                # Check that ALL Message DB functions are installed
                # The database accepts connections before all functions are created,
                # so we need to check for helper functions like acquire_lock too
                cur.execute(
                    """
                    SELECT COUNT(*) FROM pg_proc
                    WHERE proname IN ('write_message', 'acquire_lock', 'get_stream_messages')
                    AND pronamespace = (
                        SELECT oid FROM pg_namespace WHERE nspname = 'message_store'
                    )
                    """
                )
                result = cur.fetchone()
                # Should have all 3 functions
                count = result[0] if result else 0
                if count >= 3:
                    # Give it an extra second after functions appear to ensure stability
                    time.sleep(1)
                    return True
                return False
    except Exception:
        return False


@pytest.fixture
def messagedb_config(messagedb_service):
    """Provide MessageDB configuration for tests.

    This fixture depends on messagedb_service to ensure the container is running.
    Uses the postgres superuser for testing.
    """
    return MessageDBConfig(
        host="localhost",
        port=5433,
        database="message_store",
        user="postgres",
        password="message_store_password",
    )


@pytest.fixture
def messagedb_client(messagedb_config):
    """Provide a MessageDB client connected to the test database.

    The client is properly closed after the test completes.
    """
    client = MessageDBClient(messagedb_config)
    client.connect()
    yield client
    # Cleanup: close the client if it's still open
    if client._pool is not None:
        client.close()

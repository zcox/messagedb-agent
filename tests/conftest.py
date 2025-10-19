"""Pytest configuration and fixtures for testing.

This module provides pytest fixtures for:
- Message DB Docker container management
- Database connection configuration
- Test database cleanup
"""

import os

import pytest

from messagedb_agent.store import MessageDBClient, MessageDBConfig


@pytest.fixture(scope="session")
def docker_compose_file():
    """Return the path to the docker-compose.test.yml file."""
    return os.path.join(os.path.dirname(__file__), "..", "docker-compose.test.yml")


@pytest.fixture(scope="session")
def docker_setup():
    """Override docker setup to not use --build flag."""
    return ["up -d"]


@pytest.fixture(scope="session")
def messagedb_service(docker_services):
    """Start Message DB container and wait for it to be ready.

    This fixture starts the Message DB Docker container and waits for it
    to accept connections and for Message DB to be fully installed before running tests.
    """
    # Wait for Message DB to be ready (give it time to run install scripts)
    # Message DB initialization can take 30-45 seconds
    docker_services.wait_until_responsive(
        timeout=90.0, pause=2.0, check=lambda: is_messagedb_responsive()
    )
    return "messagedb"


def is_messagedb_responsive():
    """Check if Message DB is responsive and fully installed.

    Returns:
        True if Message DB accepts connections and has functions installed, False otherwise.
    """
    try:
        config = MessageDBConfig(
            host="localhost",
            port=5433,
            database="message_store",
            user="postgres",
            password="message_store_password",
        )
        with MessageDBClient(config) as client:
            conn = client.get_connection()
            try:
                with conn.cursor() as cur:
                    # Check basic connectivity
                    cur.execute("SELECT 1")
                    # Check that Message DB functions are installed
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM pg_proc
                        WHERE proname = 'write_message'
                        AND pronamespace = (
                            SELECT oid FROM pg_namespace WHERE nspname = 'message_store'
                        )
                        """
                    )
                    result = cur.fetchone()
                    if result and result[0] > 0:
                        return True
                    return False
            finally:
                client.return_connection(conn)
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
    yield client
    # Cleanup: close the client if it's still open
    if client._pool is not None:
        client.close()

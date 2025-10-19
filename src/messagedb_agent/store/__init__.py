"""
Message store integration with Message DB.

This module provides the client and utilities for reading and writing messages
to Message DB (PostgreSQL-based message store).
"""

from messagedb_agent.store.client import MessageDBClient, MessageDBConfig
from messagedb_agent.store.operations import (
    Message,
    OptimisticConcurrencyError,
    read_stream,
    write_message,
)
from messagedb_agent.store.stream import (
    build_stream_name,
    generate_thread_id,
    parse_stream_name,
)

__all__ = [
    "MessageDBClient",
    "MessageDBConfig",
    "Message",
    "OptimisticConcurrencyError",
    "read_stream",
    "write_message",
    "build_stream_name",
    "generate_thread_id",
    "parse_stream_name",
]

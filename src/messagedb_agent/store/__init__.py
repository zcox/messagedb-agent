"""
Event store integration with Message DB.

This module provides the client and utilities for reading and writing events
to Message DB (PostgreSQL-based event store).
"""

from messagedb_agent.store.client import MessageDBClient, MessageDBConfig
from messagedb_agent.store.operations import (
    Event,
    OptimisticConcurrencyError,
    read_stream,
    write_event,
)
from messagedb_agent.store.stream import (
    build_stream_name,
    generate_thread_id,
    parse_stream_name,
)

__all__ = [
    "MessageDBClient",
    "MessageDBConfig",
    "Event",
    "OptimisticConcurrencyError",
    "read_stream",
    "write_event",
    "build_stream_name",
    "generate_thread_id",
    "parse_stream_name",
]

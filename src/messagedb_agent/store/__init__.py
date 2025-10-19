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

__all__ = [
    "MessageDBClient",
    "MessageDBConfig",
    "Event",
    "OptimisticConcurrencyError",
    "read_stream",
    "write_event",
]

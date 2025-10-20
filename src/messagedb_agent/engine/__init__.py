"""
Processing engine for executing agent workflows.

This module contains the main processing loop, step execution logic,
and session management for running event-sourced agent workflows.
"""

from messagedb_agent.engine.loop import (
    MaxIterationsExceeded,
    ProcessingError,
    process_thread,
)
from messagedb_agent.engine.session import SessionError, start_session, terminate_session

__all__ = [
    "process_thread",
    "ProcessingError",
    "MaxIterationsExceeded",
    "start_session",
    "terminate_session",
    "SessionError",
]

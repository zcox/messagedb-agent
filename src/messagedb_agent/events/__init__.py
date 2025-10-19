"""Event type definitions for the event-sourced agent system.

This package contains event schemas and type definitions for all events
that can be recorded in the Message DB event streams.
"""

from messagedb_agent.events.base import BaseEvent, EventData

__all__ = ["BaseEvent", "EventData"]

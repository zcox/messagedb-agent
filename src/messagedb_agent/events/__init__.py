"""Event type definitions for the event-sourced agent system.

This package contains event schemas and type definitions for all events
that can be recorded in the Message DB event streams.
"""

from messagedb_agent.events.agent import (
    LLM_CALL_FAILED,
    LLM_RESPONSE_RECEIVED,
    LLMCallFailedData,
    LLMResponseReceivedData,
    ToolCall,
)
from messagedb_agent.events.base import BaseEvent, EventData
from messagedb_agent.events.user import (
    SESSION_TERMINATION_REQUESTED,
    USER_MESSAGE_ADDED,
    SessionTerminationRequestedData,
    UserMessageData,
)

__all__ = [
    "BaseEvent",
    "EventData",
    "UserMessageData",
    "SessionTerminationRequestedData",
    "USER_MESSAGE_ADDED",
    "SESSION_TERMINATION_REQUESTED",
    "LLMResponseReceivedData",
    "LLMCallFailedData",
    "ToolCall",
    "LLM_RESPONSE_RECEIVED",
    "LLM_CALL_FAILED",
]

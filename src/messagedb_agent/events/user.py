"""User event types for the event-sourced agent system.

This module defines events that represent user actions, such as sending
messages to the agent or requesting session termination.

User events are the primary way users interact with the agent system.
They trigger the processing loop and drive agent behavior.
"""

from dataclasses import dataclass
from datetime import datetime

from messagedb_agent.events.base import EventData


@dataclass(frozen=True)
class UserMessageData(EventData):
    """Data payload for UserMessageAdded event.

    Attributes:
        message: The text content of the user's message
        timestamp: ISO 8601 timestamp when the message was created

    Example:
        >>> data = UserMessageData(
        ...     message="Hello, can you help me?",
        ...     timestamp="2024-01-01T12:00:00Z"
        ... )
    """

    message: str
    timestamp: str

    def __post_init__(self) -> None:
        """Validate user message data after initialization.

        Raises:
            ValueError: If message is empty or timestamp is invalid format
        """
        if not self.message or not self.message.strip():
            raise ValueError("User message cannot be empty")

        # Validate timestamp is valid ISO 8601 format
        try:
            datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            raise ValueError(
                f"Timestamp must be valid ISO 8601 format, got: {self.timestamp}"
            ) from e


@dataclass(frozen=True)
class SessionTerminationRequestedData(EventData):
    """Data payload for SessionTerminationRequested event.

    This event signals that the user wants to end the agent session.
    The session will be gracefully terminated and a SessionCompleted
    event will be written.

    Attributes:
        reason: Optional reason for termination (e.g., "user_request", "timeout")

    Example:
        >>> data = SessionTerminationRequestedData(reason="user_request")
    """

    reason: str = "user_request"

    def __post_init__(self) -> None:
        """Validate session termination data after initialization.

        Raises:
            ValueError: If reason is empty
        """
        if not self.reason or not self.reason.strip():
            raise ValueError("Termination reason cannot be empty")


# Event type constants for consistency
USER_MESSAGE_ADDED = "UserMessageAdded"
SESSION_TERMINATION_REQUESTED = "SessionTerminationRequested"

"""Progress tracking for display service operations.

This module provides types and utilities for streaming progress updates
during long-running operations like agent processing and HTML rendering.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ProgressStage(str, Enum):
    """Stages of the render operation."""

    WRITING_USER_MESSAGE = "writing_user_message"
    AGENT_PROCESSING = "agent_processing"
    READING_EVENTS = "reading_events"
    READING_PREFERENCES = "reading_preferences"
    RENDERING_HTML = "rendering_html"
    COMPLETE = "complete"


class ProgressEvent(BaseModel):
    """A progress update event."""

    stage: ProgressStage
    message: str
    details: dict[str, Any] | None = None

    def to_sse(self) -> str:
        """Convert to Server-Sent Events format.

        Returns:
            SSE-formatted string (data: {...})
        """
        import json

        return f"data: {json.dumps(self.model_dump())}\n\n"

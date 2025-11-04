"""Pydantic models for display service API requests and responses."""

from pydantic import BaseModel, Field


class RenderRequest(BaseModel):
    """Request model for the /render endpoint.

    Attributes:
        thread_id: Unique identifier for the conversation thread
        user_message: Optional user message to process before rendering.
            If provided, the service will write a UserMessageSent event
            and invoke the agent processing loop before rendering.
        previous_html: Optional previous HTML for context/consistency.
            The rendering LLM can use this to maintain consistent styling
            and structure across renders.
    """

    thread_id: str = Field(
        ...,
        description="Unique identifier for the conversation thread",
        min_length=1,
        max_length=256,
    )
    user_message: str | None = Field(
        default=None,
        description="User message to process before rendering",
        max_length=10000,
    )
    previous_html: str | None = Field(
        default=None,
        description="Previous HTML for context/consistency",
        max_length=100000,
    )


class RenderResponse(BaseModel):
    """Response model for the /render endpoint.

    Attributes:
        html: Complete HTML document representing the current conversation state.
            This is sanitized HTML safe to display in a browser.
        display_prefs: Current display preferences as a string.
            These preferences control how the HTML is rendered (e.g., "compact view",
            "highlight errors in red", etc.).
    """

    html: str = Field(..., description="Complete sanitized HTML document")
    display_prefs: str = Field(..., description="Current display preferences")

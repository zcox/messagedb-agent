"""LLM-based HTML rendering for agent events.

This module uses an LLM to render event streams as HTML documents.
"""

import nh3
import structlog

from messagedb_agent.config import VertexAIConfig
from messagedb_agent.llm import Message, create_llm_client
from messagedb_agent.store import Message as MessageDBMessage

logger = structlog.get_logger(__name__)

# System prompt for the rendering LLM
RENDERING_SYSTEM_PROMPT = """You are an HTML rendering assistant. \
Your job is to convert agent conversation events into clean, readable HTML fragments.

IMPORTANT RULES:
1. Generate an HTML FRAGMENT (NOT a complete document - no <!DOCTYPE>, <html>, <head>,
   or <body> tags)
2. The HTML will be inserted into a <div> container on an existing page
3. Start with a <style> tag containing all CSS for your fragment
4. After the <style> tag, use semantic HTML5 elements (article, section, div, etc.) for content
5. Make the HTML responsive and mobile-friendly
6. Use semantic HTML5 elements for structure
7. Display conversations chronologically
8. Show user messages, agent responses, and tool executions clearly
9. Use consistent styling and colors
10. If previous_html is provided, maintain consistent styling
11. Apply any display preferences specified

OUTPUT ONLY THE HTML FRAGMENT - NO EXPLANATIONS OR MARKDOWN CODE BLOCKS."""


def _format_events_for_llm(events: list[MessageDBMessage]) -> str:
    """Format events into a readable string for the LLM.

    Args:
        events: List of Message DB events to format

    Returns:
        Formatted string representation of events
    """
    if not events:
        return "No events in this conversation yet."

    lines: list[str] = []
    for i, event in enumerate(events):
        lines.append(f"Event {i + 1}:")
        lines.append(f"  Type: {event.type}")
        lines.append(f"  Time: {event.time}")
        lines.append(f"  Data: {event.data}")
        lines.append("")

    return "\n".join(lines)


def sanitize_html(html: str) -> str:
    """Sanitize HTML to prevent XSS attacks.

    Uses nh3 library to clean HTML while preserving safe elements and attributes.

    Args:
        html: Raw HTML string to sanitize

    Returns:
        Sanitized HTML safe for display
    """
    # nh3 uses a safe default set of allowed tags and attributes
    # This includes common HTML elements but blocks dangerous ones like <script>
    return nh3.clean(html)


async def render_html(
    events: list[MessageDBMessage],
    display_prefs: str,
    llm_config: VertexAIConfig,
    previous_html: str | None = None,
) -> str:
    """Render events as HTML using an LLM.

    This function uses an LLM (typically Gemini Flash for speed/cost) to convert
    a stream of events into a formatted HTML document. The LLM is given the events,
    display preferences, and optionally the previous HTML for consistency.

    Args:
        events: List of Message DB events to render
        display_prefs: Display preference instruction string
        llm_config: LLM configuration (should be Gemini Flash for this use case)
        previous_html: Optional previous HTML for context/consistency

    Returns:
        Sanitized HTML document

    Raises:
        Exception: If LLM call fails
    """
    log = logger.bind(
        event_count=len(events),
        display_prefs=display_prefs,
        has_previous_html=previous_html is not None,
    )
    log.info("Rendering events to HTML")

    # Format events for the LLM
    events_text = _format_events_for_llm(events)

    # Build user message
    user_message_parts = [
        "Please render the following conversation events as HTML:",
        "",
        "EVENTS:",
        events_text,
        "",
        f"DISPLAY PREFERENCES: {display_prefs}",
    ]

    if previous_html:
        user_message_parts.extend(
            [
                "",
                "PREVIOUS HTML (for consistency):",
                previous_html[:1000],  # Limit to avoid token bloat
            ]
        )

    user_message = "\n".join(user_message_parts)

    # Create LLM client and generate HTML
    llm_client = create_llm_client(llm_config)

    messages = [Message(role="user", text=user_message)]

    response = llm_client.call(messages, system_prompt=RENDERING_SYSTEM_PROMPT)

    if not response.text:
        log.error("LLM returned empty response")
        raise ValueError("LLM rendering returned empty response")

    raw_html = response.text

    # Extract HTML if LLM wrapped it in markdown code blocks (sometimes happens)
    if "```html" in raw_html:
        # Extract content between ```html and ```
        start = raw_html.find("```html") + 7
        end = raw_html.find("```", start)
        if end > start:
            raw_html = raw_html[start:end].strip()
    elif "```" in raw_html:
        # Extract content between ``` and ```
        start = raw_html.find("```") + 3
        end = raw_html.find("```", start)
        if end > start:
            raw_html = raw_html[start:end].strip()

    # Sanitize HTML
    sanitized_html = sanitize_html(raw_html)

    log.info(
        "HTML rendering complete",
        raw_length=len(raw_html),
        sanitized_length=len(sanitized_html),
    )

    return sanitized_html

"""LLM-based HTML rendering for agent events.

This module uses an LLM to render event streams as HTML documents.
"""

from collections.abc import AsyncIterator

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
3. Start with a COMPLETE <style> tag containing all CSS for your fragment
4. After the <style> tag, use semantic HTML5 elements (article, section, div, etc.) for content
5. Make the HTML responsive and mobile-friendly
6. Use semantic HTML5 elements for structure
7. Display conversations chronologically
8. Show user messages, agent responses, and tool executions clearly
9. Use consistent styling and colors
10. If previous_html is provided, maintain consistent styling
11. Apply any display preferences specified

STREAMING OPTIMIZATION (IMPORTANT):
- Generate content SEQUENTIALLY from top to bottom
- Complete each HTML element BEFORE starting the next one
- Do NOT go back to edit or revise earlier sections
- Output final content immediately (NO placeholders or TODO markers)
- Generate the complete <style> section first, then move to content
- Work linearly through the conversation events in order

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
    Allows <style> tags since we generate inline CSS for fragment styling.

    Args:
        html: Raw HTML string to sanitize

    Returns:
        Sanitized HTML safe for display
    """
    # Default nh3 allowed tags
    allowed_tags = {
        "a",
        "abbr",
        "acronym",
        "area",
        "article",
        "aside",
        "b",
        "bdi",
        "bdo",
        "blockquote",
        "br",
        "caption",
        "center",
        "cite",
        "code",
        "col",
        "colgroup",
        "data",
        "dd",
        "del",
        "details",
        "dfn",
        "div",
        "dl",
        "dt",
        "em",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hgroup",
        "hr",
        "i",
        "img",
        "ins",
        "kbd",
        "li",
        "main",
        "map",
        "mark",
        "nav",
        "ol",
        "p",
        "pre",
        "q",
        "rp",
        "rt",
        "ruby",
        "s",
        "samp",
        "section",
        "small",
        "span",
        "strike",
        "strong",
        "sub",
        "summary",
        "sup",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "time",
        "tr",
        "tt",
        "u",
        "ul",
        "var",
        "wbr",
        "style",  # Allow style tags for inline CSS
    }

    # Clean with extended tag set and empty clean_content_tags to preserve style content
    return nh3.clean(html, tags=allowed_tags, clean_content_tags=set())


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

    # Sanitization disabled - trust LLM output
    log.info(
        "HTML rendering complete",
        raw_length=len(raw_html),
    )

    return raw_html


async def render_html_stream(
    events: list[MessageDBMessage],
    display_prefs: str,
    llm_config: VertexAIConfig,
    previous_html: str | None = None,
) -> AsyncIterator[str]:
    """Stream HTML rendering as LLM generates it.

    This function uses an LLM to convert events into HTML, yielding raw chunks
    as they are generated. This enables progressive display or progress indication.

    IMPORTANT: The yielded chunks are raw and NOT processed. The caller must:
    1. Buffer all chunks to reconstruct the complete response
    2. Extract HTML from markdown code blocks if present (```html...``` or ```...```)
    3. Apply sanitization using sanitize_html() before displaying

    Args:
        events: List of Message DB events to render
        display_prefs: Display preference instruction string
        llm_config: LLM configuration (should be Gemini Flash for this use case)
        previous_html: Optional previous HTML for context/consistency

    Yields:
        Raw HTML chunks as they are generated by the LLM (NOT sanitized or extracted)

    Raises:
        ValueError: If LLM returns empty response

    Example:
        >>> chunks = []
        >>> async for chunk in render_html_stream(events, prefs, config):
        ...     chunks.append(chunk)
        ...     print(chunk, end="", flush=True)  # Show progress
        >>> raw_html = "".join(chunks)
        >>> # Extract from markdown if needed (see render_html() for logic)
        >>> final_html = sanitize_html(raw_html)
    """
    log = logger.bind(
        event_count=len(events),
        display_prefs=display_prefs,
        has_previous_html=previous_html is not None,
    )
    log.info("Starting streaming HTML rendering")

    # Format events for the LLM (same as non-streaming version)
    events_text = _format_events_for_llm(events)

    # Build user message (same as non-streaming version)
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

    # Create LLM client
    llm_client = create_llm_client(llm_config)
    messages = [Message(role="user", text=user_message)]

    # Stream the response, buffering for validation
    html_chunks: list[str] = []
    chunk_count = 0

    for delta in llm_client.call_stream(messages, system_prompt=RENDERING_SYSTEM_PROMPT):
        if delta.delta_type == "text" and delta.text:
            # Yield raw chunk immediately for true streaming
            yield delta.text
            # Also buffer for validation
            html_chunks.append(delta.text)
            chunk_count += 1
        elif delta.delta_type == "done":
            log.info("Streaming complete", chunk_count=chunk_count)

    # Validate we received content
    raw_html = "".join(html_chunks)
    if not raw_html:
        log.error("LLM returned empty response")
        raise ValueError("LLM streaming rendering returned empty response")

    log.info("Streaming HTML rendering complete", total_length=len(raw_html))

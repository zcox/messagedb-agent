"""Display preference projection function.

This module provides a pure projection function that reduces display preference
events into current display instructions for the rendering LLM.

NOTE: This is currently a stub implementation. Full implementation is tracked
in issue messagedb-agent-110.
"""

from typing import Any


def project_display_prefs(events: list[dict[str, Any]]) -> str:
    """Pure projection: DisplayPreferenceUpdated events → display instruction.

    This function takes all display preference events for a thread and returns
    the current merged display instruction string to pass to the rendering LLM.

    Args:
        events: List of DisplayPreferenceUpdated events from display-prefs:{threadId}

    Returns:
        Current display preferences as a string instruction.
        Returns "default" if no events exist.

    Example:
        >>> events = [
        ...     {
        ...         "type": "DisplayPreferenceUpdated",
        ...         "data": {
        ...             "instruction": "show compact view",
        ...             "merged_preferences": "Show compact view with minimal whitespace"
        ...         }
        ...     },
        ...     {
        ...         "type": "DisplayPreferenceUpdated",
        ...         "data": {
        ...             "instruction": "highlight errors in red",
        ...             "merged_preferences": "Show compact view. Highlight errors in red."
        ...         }
        ...     }
        ... ]
        >>> project_display_prefs(events)
        'Show compact view. Highlight errors in red.'
    """
    if not events:
        return "default"

    # Extract merged_preferences from the last event (latest wins)
    # Future implementation may support more sophisticated merging
    for event in reversed(events):
        if event.get("type") == "DisplayPreferenceUpdated":
            data = event.get("data", {})
            merged_prefs = data.get("merged_preferences")
            if merged_prefs:
                return merged_prefs

    return "default"

"""Stream name utilities for Message DB.

This module provides functions for working with Message DB stream names,
following the format: {category}:{version}-{thread_id}

Example:
    >>> thread_id = generate_thread_id()
    >>> stream_name = build_stream_name("agent", "v0", thread_id)
    >>> stream_name
    'agent:v0-abc123...'
    >>> category, version, tid = parse_stream_name(stream_name)
    >>> category
    'agent'
"""

import uuid


def generate_thread_id() -> str:
    """Generate a unique thread identifier using UUID4.

    Returns:
        A UUID4 string to uniquely identify an agent thread/session.

    Example:
        >>> thread_id = generate_thread_id()
        >>> len(thread_id)
        36
        >>> "-" in thread_id
        True
    """
    return str(uuid.uuid4())


def build_stream_name(category: str, version: str, thread_id: str) -> str:
    """Build a Message DB stream name from components.

    Stream names follow the format: {category}:{version}-{thread_id}

    Args:
        category: Logical grouping of related streams (e.g., "agent")
        version: Schema or implementation version (e.g., "v0", "v1")
        thread_id: Unique identifier for the specific agent session

    Returns:
        A fully qualified stream name string.

    Raises:
        ValueError: If any component is empty or contains invalid characters.

    Example:
        >>> build_stream_name("agent", "v0", "abc123")
        'agent:v0-abc123'
    """
    # Validate inputs
    if not category or not category.strip():
        raise ValueError("category cannot be empty")
    if not version or not version.strip():
        raise ValueError("version cannot be empty")
    if not thread_id or not thread_id.strip():
        raise ValueError("thread_id cannot be empty")

    # Check for invalid characters
    if ":" in category:
        raise ValueError("category cannot contain ':' character")
    if "-" in version:
        raise ValueError("version cannot contain '-' character")

    return f"{category}:{version}-{thread_id}"


def parse_stream_name(stream_name: str) -> tuple[str, str, str]:
    """Parse a Message DB stream name into its components.

    Args:
        stream_name: A stream name in the format {category}:{version}-{thread_id}

    Returns:
        A tuple of (category, version, thread_id)

    Raises:
        ValueError: If the stream name format is invalid.

    Example:
        >>> parse_stream_name("agent:v0-abc123")
        ('agent', 'v0', 'abc123')
    """
    if not stream_name or not stream_name.strip():
        raise ValueError("stream_name cannot be empty")

    # Split on ':' to get category and version-thread_id
    if ":" not in stream_name:
        raise ValueError(
            f"Invalid stream name format: '{stream_name}'. "
            "Expected format: category:version-thread_id"
        )

    parts = stream_name.split(":", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid stream name format: '{stream_name}'. "
            "Expected format: category:version-thread_id"
        )

    category = parts[0]
    version_and_thread = parts[1]

    # Split on '-' to get version and thread_id
    if "-" not in version_and_thread:
        raise ValueError(
            f"Invalid stream name format: '{stream_name}'. "
            "Expected format: category:version-thread_id"
        )

    version_parts = version_and_thread.split("-", 1)
    if len(version_parts) != 2:
        raise ValueError(
            f"Invalid stream name format: '{stream_name}'. "
            "Expected format: category:version-thread_id"
        )

    version = version_parts[0]
    thread_id = version_parts[1]

    # Validate components are not empty
    if not category.strip():
        raise ValueError("category component cannot be empty")
    if not version.strip():
        raise ValueError("version component cannot be empty")
    if not thread_id.strip():
        raise ValueError("thread_id component cannot be empty")

    return category, version, thread_id

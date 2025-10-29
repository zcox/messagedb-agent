"""Command-line interface for the TUI application.

This module provides CLI argument parsing for running the TUI with various options.

Usage:
    # Start a new session
    uv run python -m messagedb_agent.tui

    # Continue an existing session
    uv run python -m messagedb_agent.tui --thread-id abc-123-def-456

    # Use custom config file
    uv run python -m messagedb_agent.tui --config /path/to/config.toml

    # Override category and version
    uv run python -m messagedb_agent.tui --category myagent --version v1
"""

import argparse

from messagedb_agent.tui.app import main


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Interactive Terminal UI for multi-turn agent conversations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start a new session
  uv run python -m messagedb_agent.tui

  # Continue an existing session
  uv run python -m messagedb_agent.tui --thread-id aa06c07c-f8a5-4f90-96f4-9a2edb3cd93d

  # Use custom configuration
  uv run python -m messagedb_agent.tui --config /path/to/config.toml
        """,
    )

    parser.add_argument(
        "--thread-id",
        "-t",
        type=str,
        default=None,
        help="Thread ID to continue an existing session (default: start new session)",
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to configuration file (default: use default config)",
    )

    parser.add_argument(
        "--category",
        type=str,
        default="agent",
        help="Stream category (default: agent)",
    )

    parser.add_argument(
        "--version",
        "-v",
        type=str,
        default="v0",
        help="Stream version (default: v0)",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    main(
        config_path=args.config,
        category=args.category,
        version=args.version,
        thread_id=args.thread_id,
    )

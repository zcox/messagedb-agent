"""Command-line interface for the event-sourced agent system.

This module provides a CLI for interacting with the agent system, including
commands for starting new sessions, continuing existing sessions, viewing
session events, and listing recent sessions.
"""

import argparse
import json
import sys
from typing import Any
from uuid import UUID

from messagedb_agent.config import Config, load_config
from messagedb_agent.engine import process_thread, start_session
from messagedb_agent.events import BaseEvent
from messagedb_agent.llm import create_llm_client
from messagedb_agent.projections import project_to_session_state
from messagedb_agent.store import (
    Message,
    MessageDBClient,
    MessageDBConfig,
    build_stream_name,
    read_stream,
)
from messagedb_agent.tools import ToolRegistry, register_builtin_tools


def _convert_db_config(config: Config) -> MessageDBConfig:
    """Convert config.MessageDBConfig to store.MessageDBConfig.

    Args:
        config: System configuration

    Returns:
        MessageDBConfig for store operations
    """
    return MessageDBConfig(
        host=config.message_db.host,
        port=config.message_db.port,
        database=config.message_db.database,
        user=config.message_db.user,
        password=config.message_db.password,
    )


def _message_to_event(message: Message) -> BaseEvent:
    """Convert a Message from read_stream to a BaseEvent.

    Args:
        message: Message object from read_stream

    Returns:
        BaseEvent with same data
    """
    # Convert id string to UUID if needed
    event_id = message.id if isinstance(message.id, UUID) else UUID(message.id)

    return BaseEvent(
        id=event_id,
        type=message.type,
        data=message.data,
        metadata=message.metadata or {},
        position=message.position,
        global_position=message.global_position,
        time=message.time,
        stream_name=message.stream_name,
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI.

    Returns:
        Configured argument parser with all subcommands
    """
    parser = argparse.ArgumentParser(
        prog="messagedb-agent",
        description="Event-sourced agent system using Message DB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file (.env format)",
        metavar="FILE",
    )
    parser.add_argument(
        "--category",
        type=str,
        default="agent",
        help="Stream category (default: agent)",
    )
    parser.add_argument(
        "--version",
        type=str,
        default="v0",
        help="Stream version (default: v0)",
    )

    # Create subparsers for commands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Start command - start new session with initial message
    start_parser = subparsers.add_parser(
        "start", help="Start a new agent session with an initial message"
    )
    start_parser.add_argument("message", type=str, help="Initial message to send to the agent")
    start_parser.add_argument(
        "--max-iterations",
        type=int,
        help="Override max iterations from config",
        metavar="N",
    )

    # Continue command - continue existing session
    continue_parser = subparsers.add_parser("continue", help="Continue an existing agent session")
    continue_parser.add_argument("thread_id", type=str, help="Thread ID to continue")
    continue_parser.add_argument(
        "--max-iterations",
        type=int,
        help="Override max iterations from config",
        metavar="N",
    )

    # Show command - display session events
    show_parser = subparsers.add_parser("show", help="Display events for a specific session")
    show_parser.add_argument("thread_id", type=str, help="Thread ID to display")
    show_parser.add_argument(
        "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    show_parser.add_argument(
        "--full", action="store_true", help="Show full event data (including metadata)"
    )

    # List command - list recent sessions
    list_parser = subparsers.add_parser("list", help="List recent sessions")
    list_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of sessions to list (default: 10)",
        metavar="N",
    )
    list_parser.add_argument(
        "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    return parser


def cmd_start(args: argparse.Namespace, config: Config) -> int:
    """Handle the 'start' command - start a new agent session.

    Args:
        args: Parsed command-line arguments
        config: System configuration

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Initialize clients
        store_client = MessageDBClient(_convert_db_config(config))
        llm_client = create_llm_client(config.vertex_ai)

        # Initialize tool registry with builtin tools
        tool_registry = ToolRegistry()
        register_builtin_tools(tool_registry)

        # Start the session
        print(f"Starting new session with message: {args.message}")
        thread_id = start_session(
            initial_message=args.message,
            store_client=store_client,
            category=args.category,
            version=args.version,
        )
        print(f"Session started with thread ID: {thread_id}")

        # Build stream name
        stream_name = build_stream_name(args.category, args.version, thread_id)

        # Process the session
        max_iterations = (
            args.max_iterations if args.max_iterations else config.processing.max_iterations
        )
        print(f"Processing session (max {max_iterations} iterations)...")

        final_state = process_thread(
            thread_id=thread_id,
            stream_name=stream_name,
            store_client=store_client,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_iterations=max_iterations,
        )

        # Display results
        print("\n" + "=" * 80)
        print("SESSION COMPLETE")
        print("=" * 80)
        print(f"Thread ID: {thread_id}")
        print(f"Status: {final_state.status.value}")
        print(f"Messages: {final_state.message_count}")
        print(f"LLM Calls: {final_state.llm_call_count}")
        print(f"Tool Calls: {final_state.tool_call_count}")
        print(f"Errors: {final_state.error_count}")

        if final_state.session_start_time and final_state.session_end_time:
            duration = (
                final_state.session_end_time - final_state.session_start_time
            ).total_seconds()
            print(f"Duration: {duration:.2f}s")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_continue(args: argparse.Namespace, config: Config) -> int:
    """Handle the 'continue' command - continue an existing session.

    Args:
        args: Parsed command-line arguments
        config: System configuration

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Initialize clients
        store_client = MessageDBClient(_convert_db_config(config))
        llm_client = create_llm_client(config.vertex_ai)

        # Initialize tool registry with builtin tools
        tool_registry = ToolRegistry()
        register_builtin_tools(tool_registry)

        # Build stream name
        stream_name = build_stream_name(args.category, args.version, args.thread_id)

        # Check if session exists
        events = read_stream(store_client, stream_name)
        if not events:
            print(f"Error: No session found with thread ID: {args.thread_id}", file=sys.stderr)
            return 1

        print(f"Continuing session: {args.thread_id}")

        # Process the session
        max_iterations = (
            args.max_iterations if args.max_iterations else config.processing.max_iterations
        )
        print(f"Processing session (max {max_iterations} iterations)...")

        final_state = process_thread(
            thread_id=args.thread_id,
            stream_name=stream_name,
            store_client=store_client,
            llm_client=llm_client,
            tool_registry=tool_registry,
            max_iterations=max_iterations,
        )

        # Display results
        print("\n" + "=" * 80)
        print("SESSION COMPLETE")
        print("=" * 80)
        print(f"Thread ID: {args.thread_id}")
        print(f"Status: {final_state.status.value}")
        print(f"Messages: {final_state.message_count}")
        print(f"LLM Calls: {final_state.llm_call_count}")
        print(f"Tool Calls: {final_state.tool_call_count}")
        print(f"Errors: {final_state.error_count}")

        if final_state.session_start_time and final_state.session_end_time:
            duration = (
                final_state.session_end_time - final_state.session_start_time
            ).total_seconds()
            print(f"Duration: {duration:.2f}s")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_show(args: argparse.Namespace, config: Config) -> int:
    """Handle the 'show' command - display session events.

    Args:
        args: Parsed command-line arguments
        config: System configuration

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Initialize store client
        store_client = MessageDBClient(_convert_db_config(config))

        # Build stream name
        stream_name = build_stream_name(args.category, args.version, args.thread_id)

        # Read messages and convert to events
        messages = read_stream(store_client, stream_name)

        if not messages:
            print(f"No events found for thread ID: {args.thread_id}", file=sys.stderr)
            return 1

        # Convert messages to events for projection
        events = [_message_to_event(msg) for msg in messages]

        # Output based on format
        if args.format == "json":
            # JSON format
            events_data: list[dict[str, Any]] = []
            for event in events:
                event_dict: dict[str, Any] = {
                    "id": str(event.id),
                    "type": event.type,
                    "position": event.position,
                    "global_position": event.global_position,
                    "time": event.time.isoformat(),
                    "data": event.data,
                }
                if args.full and event.metadata:
                    event_dict["metadata"] = event.metadata
                events_data.append(event_dict)

            print(json.dumps(events_data, indent=2))

        else:
            # Text format
            print(f"Events for session: {args.thread_id}")
            print(f"Stream: {stream_name}")
            print(f"Total events: {len(events)}")
            print("=" * 80)

            for event in events:
                print(f"\n[{event.position}] {event.type}")
                print(f"  ID: {event.id}")
                print(f"  Time: {event.time.isoformat()}")
                print(f"  Global Position: {event.global_position}")

                # Pretty-print data
                if event.data:
                    print("  Data:")
                    for key, value in event.data.items():
                        # Truncate long values
                        value_str = str(value)
                        if len(value_str) > 100 and not args.full:
                            value_str = value_str[:97] + "..."
                        print(f"    {key}: {value_str}")

                # Show metadata if --full flag is set
                if args.full and event.metadata:
                    print("  Metadata:")
                    for key, value in event.metadata.items():
                        print(f"    {key}: {value}")

            # Show session summary
            session_state = project_to_session_state(events)
            print("\n" + "=" * 80)
            print("SESSION SUMMARY")
            print("=" * 80)
            print(f"Status: {session_state.status.value}")
            print(f"Messages: {session_state.message_count}")
            print(f"LLM Calls: {session_state.llm_call_count}")
            print(f"Tool Calls: {session_state.tool_call_count}")
            print(f"Errors: {session_state.error_count}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def cmd_list(args: argparse.Namespace, config: Config) -> int:
    """Handle the 'list' command - list recent sessions.

    Args:
        args: Parsed command-line arguments
        config: System configuration

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Initialize store client
        store_client = MessageDBClient(_convert_db_config(config))

        # Query all streams for this category
        # We'll use get_category_messages to find all sessions
        category_pattern = f"{args.category}:{args.version}"

        with store_client as conn:
            with conn.cursor() as cur:  # type: ignore[attr-defined]
                # Get all distinct streams in this category
                # We query the messages table directly to find unique stream names
                cur.execute(
                    """
                    SELECT DISTINCT stream_name, MAX(time) as last_activity
                    FROM message_store.messages
                    WHERE stream_name LIKE %s
                    GROUP BY stream_name
                    ORDER BY last_activity DESC
                    LIMIT %s
                    """,
                    (f"{category_pattern}-%", args.limit),
                )

                streams: list[tuple[str, Any]] = cur.fetchall()  # type: ignore[assignment]

        if not streams:
            print(f"No sessions found for category: {args.category}:{args.version}")
            return 0

        # Output based on format
        if args.format == "json":
            # JSON format - get full session state for each stream
            sessions_data: list[dict[str, Any]] = []
            for stream_name, last_activity in streams:  # type: ignore[misc]
                messages = read_stream(store_client, stream_name)
                if messages:
                    events = [_message_to_event(msg) for msg in messages]
                    session_state = project_to_session_state(events)
                    sessions_data.append(
                        {
                            "thread_id": session_state.thread_id,
                            "stream_name": stream_name,
                            "status": session_state.status.value,
                            "message_count": session_state.message_count,
                            "llm_call_count": session_state.llm_call_count,
                            "tool_call_count": session_state.tool_call_count,
                            "error_count": session_state.error_count,
                            "last_activity": last_activity.isoformat(),
                            "start_time": (
                                session_state.session_start_time.isoformat()
                                if session_state.session_start_time
                                else None
                            ),
                            "end_time": (
                                session_state.session_end_time.isoformat()
                                if session_state.session_end_time
                                else None
                            ),
                        }
                    )

            print(json.dumps(sessions_data, indent=2))

        else:
            # Text format
            print(f"Recent sessions (category: {args.category}:{args.version})")
            print("=" * 80)
            print(f"{'Thread ID':<40} {'Status':<12} {'Messages':<10} {'Last Activity':<20}")
            print("=" * 80)

            for stream_name, last_activity in streams:  # type: ignore[misc]
                # Extract thread_id from stream_name
                # Format: category:version-thread_id
                parts: list[str] = stream_name.split("-", 1)  # type: ignore[assignment]
                if len(parts) == 2:
                    thread_id = parts[1]

                    # Get session state
                    messages = read_stream(store_client, stream_name)
                    if messages:
                        events = [_message_to_event(msg) for msg in messages]
                        session_state = project_to_session_state(events)
                        last_activity_str = last_activity.strftime("%Y-%m-%d %H:%M:%S")
                        print(
                            f"{thread_id:<40} {session_state.status.value:<12} "
                            f"{session_state.message_count:<10} {last_activity_str:<20}"
                        )

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments (default: sys.argv[1:])

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Check if a command was provided
    if not args.command:
        parser.print_help()
        return 1

    # Load configuration
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Dispatch to command handler
    if args.command == "start":
        return cmd_start(args, config)
    elif args.command == "continue":
        return cmd_continue(args, config)
    elif args.command == "show":
        return cmd_show(args, config)
    elif args.command == "list":
        return cmd_list(args, config)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

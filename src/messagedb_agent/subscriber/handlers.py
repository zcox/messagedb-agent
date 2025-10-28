"""Event-specific subscriber handlers and utilities for processing messages.

This module provides helper functions and classes for common message handling patterns:
- Printing events to console
- Filtering events based on predicates
- Routing events by type
- Logging events
- Pretty-printing LLM conversations
"""

import json
from collections.abc import Callable

import structlog

from messagedb_agent.store.operations import Message
from messagedb_agent.subscriber.base import MessageHandler

logger = structlog.get_logger(__name__)


def print_event_handler(message: Message) -> None:
    """Pretty-print events to console.

    Formats the message as JSON with indentation for readability.

    Args:
        message: The message to print

    Example:
        >>> subscriber = Subscriber(
        ...     category="agent",
        ...     handler=print_event_handler,
        ...     store_client=client
        ... )
    """
    event_dict = {
        "id": str(message.id),
        "type": message.type,
        "stream_name": message.stream_name,
        "position": message.position,
        "global_position": message.global_position,
        "time": message.time.isoformat(),
        "data": message.data,
        "metadata": message.metadata,
    }
    print(json.dumps(event_dict, indent=2))


def filter_handler(predicate: Callable[[Message], bool], handler: MessageHandler) -> MessageHandler:
    """Create a handler that only processes messages matching a predicate.

    Args:
        predicate: Function that returns True if message should be processed
        handler: Handler to call for matching messages

    Returns:
        A new handler that filters messages before calling the wrapped handler

    Example:
        >>> # Only process events from a specific thread
        >>> def is_my_thread(msg: Message) -> bool:
        ...     return "thread123" in msg.stream_name
        ...
        >>> filtered = filter_handler(is_my_thread, print_event_handler)
        >>> subscriber = Subscriber(category="agent", handler=filtered, store_client=client)
    """

    def filtered_handler(message: Message) -> None:
        if predicate(message):
            result = handler(message)
            # Handle both sync and async handlers
            if result is not None:
                # This is an async handler, but we can't await here in sync context
                # The subscriber will handle this appropriately
                return result  # type: ignore
        return None

    return filtered_handler


def event_type_router(handlers_map: dict[str, MessageHandler]) -> MessageHandler:
    """Route events to different handlers based on event type.

    Args:
        handlers_map: Dictionary mapping event type to handler function

    Returns:
        A handler that routes messages to type-specific handlers

    Example:
        >>> def handle_user_message(msg: Message) -> None:
        ...     print(f"User: {msg.data.get('message')}")
        ...
        >>> def handle_llm_response(msg: Message) -> None:
        ...     print(f"Agent: {msg.data.get('response')}")
        ...
        >>> router = event_type_router({
        ...     "UserMessageAdded": handle_user_message,
        ...     "LLMResponseReceived": handle_llm_response,
        ... })
        >>> subscriber = Subscriber(category="agent", handler=router, store_client=client)
    """

    def routing_handler(message: Message) -> None:
        handler = handlers_map.get(message.type)
        if handler is not None:
            result = handler(message)
            # Handle both sync and async handlers
            if result is not None:
                return result  # type: ignore
        else:
            logger.debug(
                "event_type_not_routed",
                event_type=message.type,
                available_types=list(handlers_map.keys()),
            )
        return None

    return routing_handler


def log_event_handler(event_logger: structlog.BoundLogger | None = None) -> MessageHandler:
    """Create a handler that logs events using structlog.

    Args:
        event_logger: Optional logger to use. If not provided, uses default logger.

    Returns:
        A handler that logs each message

    Example:
        >>> custom_logger = structlog.get_logger("my_subscriber")
        >>> handler = log_event_handler(custom_logger)
        >>> subscriber = Subscriber(category="agent", handler=handler, store_client=client)
    """
    log = event_logger if event_logger is not None else logger

    def logging_handler(message: Message) -> None:
        log.info(
            "event_received",
            event_id=str(message.id),
            event_type=message.type,
            stream_name=message.stream_name,
            position=message.position,
            global_position=message.global_position,
            data=message.data,
            metadata=message.metadata,
        )

    return logging_handler


class ConversationPrinter:
    """Pretty-printer for LLM conversations from event streams.

    Formats user messages, LLM responses, tool calls, and tool results
    in a human-readable format suitable for console output.

    Attributes:
        show_tool_calls: Whether to display tool call events
        show_tool_results: Whether to display tool result events
        show_system: Whether to display system events
    """

    def __init__(
        self,
        show_tool_calls: bool = True,
        show_tool_results: bool = True,
        show_system: bool = False,
    ):
        """Initialize the conversation printer.

        Args:
            show_tool_calls: Whether to display tool call events (default: True)
            show_tool_results: Whether to display tool result events (default: True)
            show_system: Whether to display system events (default: False)
        """
        self.show_tool_calls = show_tool_calls
        self.show_tool_results = show_tool_results
        self.show_system = show_system

    def __call__(self, message: Message) -> None:
        """Process and print a message.

        Args:
            message: The message to print
        """
        event_type = message.type
        data = message.data

        # User messages
        if event_type == "UserMessageAdded":
            user_message = data.get("message", "")
            print("\n[User]")
            print(f"{user_message}")

        # LLM responses
        elif event_type == "LLMResponseReceived":
            response_text = data.get("response_text", "")
            if response_text:
                print("\n[Assistant]")
                print(f"{response_text}")

            # Show tool calls if enabled
            if self.show_tool_calls:
                tool_calls = data.get("tool_calls", [])
                if tool_calls:
                    print("\n[Tool Calls]")
                    for tool_call in tool_calls:
                        name = tool_call.get("name", "unknown")
                        args = tool_call.get("arguments", {})
                        print(f"  - {name}({json.dumps(args, indent=4)})")

        # Tool execution requests
        elif event_type == "ToolExecutionRequested" and self.show_tool_calls:
            tool_name = data.get("tool_name", "unknown")
            arguments = data.get("arguments", {})
            print(f"\n[Tool Call: {tool_name}]")
            print(f"Arguments: {json.dumps(arguments, indent=2)}")

        # Tool results
        elif event_type == "ToolResultReceived" and self.show_tool_results:
            tool_name = data.get("tool_name", "unknown")
            result = data.get("result", {})
            print(f"\n[Tool Result: {tool_name}]")
            print(f"{json.dumps(result, indent=2)}")

        # System events
        elif self.show_system:
            if event_type == "SessionStarted":
                print("\n[Session Started]")
                print(f"Thread ID: {data.get('thread_id', 'unknown')}")
            elif event_type == "SessionCompleted":
                print("\n[Session Completed]")
                reason = data.get("reason", "unknown")
                print(f"Reason: {reason}")
            elif event_type == "ErrorOccurred":
                print("\n[Error]")
                error_message = data.get("error", "unknown error")
                print(f"{error_message}")
            else:
                # Generic system event
                print(f"\n[{event_type}]")
                print(json.dumps(data, indent=2))

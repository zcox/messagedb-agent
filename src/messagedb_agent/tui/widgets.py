"""Custom widgets for the TUI application.

This module provides specialized widgets for displaying agent conversations,
including message lists, tool calls, and system events.
"""

import json
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from messagedb_agent.store.operations import Message


class MessageWidget(Static):
    """Widget for displaying a single message with appropriate styling.

    Handles different message types (user, assistant, tool calls, tool results)
    and applies appropriate formatting and styling to each.
    """

    def __init__(
        self,
        message: Message,
        show_timestamp: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize a message widget.

        Args:
            message: The message to display
            show_timestamp: Whether to show the timestamp
            **kwargs: Additional arguments to pass to Static
        """
        self.message = message
        self.show_timestamp = show_timestamp

        # Create the renderable content
        content = self._render_message()
        super().__init__(content, **kwargs)

        # Apply styling based on message type
        self._apply_style()

    def _render_message(self) -> Group:
        """Render the message content with appropriate formatting.

        Returns:
            A Rich Group containing the formatted message content
        """
        event_type = self.message.type
        data = self.message.data
        parts: list[Text | Panel | Group] = []

        # Skip rendering entirely for ToolExecutionRequested
        # (tool calls already shown in LLMResponseReceived)
        if event_type == "ToolExecutionRequested":
            return Group(*parts)

        # Add timestamp if enabled
        if self.show_timestamp:
            timestamp = self.message.time.strftime("%H:%M:%S")
            timestamp_text = Text(f"[{timestamp}]", style="dim")
            parts.append(timestamp_text)

        # Render based on event type
        if event_type == "UserMessageAdded":
            parts.append(self._render_user_message(data))
        elif event_type == "LLMResponseReceived":
            parts.append(self._render_llm_response(data))
        elif event_type == "ToolResultReceived":
            parts.append(self._render_tool_result(data))
        elif event_type == "SessionStarted":
            parts.append(self._render_session_started(data))
        elif event_type == "SessionCompleted":
            parts.append(self._render_session_completed(data))
        elif event_type == "ErrorOccurred":
            parts.append(self._render_error(data))
        else:
            # Generic event rendering
            parts.append(self._render_generic_event(event_type, data))

        return Group(*parts)

    def _render_user_message(self, data: dict[str, Any]) -> Panel:
        """Render a user message.

        Args:
            data: The event data

        Returns:
            A Panel containing the formatted user message
        """
        message_text: str = str(data.get("message", ""))
        content = Text(message_text, style="white")
        return Panel(
            content,
            title="[bold cyan]User[/bold cyan]",
            border_style="cyan",
            padding=(0, 1),
        )

    def _render_llm_response(self, data: dict[str, Any]) -> Group:
        """Render an LLM response with optional tool calls.

        Args:
            data: The event data

        Returns:
            A Group containing the response text and any tool calls
        """
        parts: list[Panel] = []

        # Render response text
        response_text: str = str(data.get("response_text", ""))
        if response_text:
            content = Text(response_text, style="white")
            parts.append(
                Panel(
                    content,
                    title="[bold green]Assistant[/bold green]",
                    border_style="green",
                    padding=(0, 1),
                )
            )

        # Render tool calls if present
        tool_calls: list[Any] = list(data.get("tool_calls", []))
        if tool_calls:
            tool_parts: list[Text | Syntax] = []
            for tool_call in tool_calls:
                name: str = str(tool_call.get("name", "unknown"))
                args: dict[str, Any] = dict(tool_call.get("arguments", {}))

                # Use syntax highlighting for JSON arguments
                args_json = json.dumps(args, indent=2)
                syntax = Syntax(
                    args_json,
                    "json",
                    theme="monokai",
                    background_color="default",
                )

                tool_text = Text()
                tool_text.append(f"{name}", style="bold yellow")
                tool_text.append("()\n")

                tool_parts.append(tool_text)
                tool_parts.append(syntax)

            parts.append(
                Panel(
                    Group(*tool_parts),
                    title="[bold yellow]Tool Calls[/bold yellow]",
                    border_style="yellow",
                    padding=(0, 1),
                )
            )

        return Group(*parts)

    def _render_tool_result(self, data: dict[str, Any]) -> Panel:
        """Render a tool execution result.

        Args:
            data: The event data

        Returns:
            A Panel containing the formatted tool result
        """
        tool_name: str = str(data.get("tool_name", "unknown"))
        result: dict[str, Any] = dict(data.get("result", {}))

        # Use syntax highlighting for JSON result
        result_json = json.dumps(result, indent=2)
        syntax = Syntax(
            result_json,
            "json",
            theme="monokai",
            background_color="default",
        )

        return Panel(
            syntax,
            title=f"[bold magenta]Tool Result: {tool_name}[/bold magenta]",
            border_style="magenta",
            padding=(0, 1),
        )

    def _render_session_started(self, data: dict[str, Any]) -> Panel:
        """Render a session started event.

        Args:
            data: The event data

        Returns:
            A Panel containing the session start information
        """
        thread_id: str = str(data.get("thread_id", "unknown"))
        content = Text(f"Thread ID: {thread_id}", style="bright_white")
        return Panel(
            content,
            title="[bold blue]Session Started[/bold blue]",
            border_style="blue",
            padding=(0, 1),
        )

    def _render_session_completed(self, data: dict[str, Any]) -> Panel:
        """Render a session completed event.

        Args:
            data: The event data

        Returns:
            A Panel containing the session completion information
        """
        reason: str = str(data.get("reason", "unknown"))
        content = Text(f"Reason: {reason}", style="bright_white")
        return Panel(
            content,
            title="[bold blue]Session Completed[/bold blue]",
            border_style="blue",
            padding=(0, 1),
        )

    def _render_error(self, data: dict[str, Any]) -> Panel:
        """Render an error event.

        Args:
            data: The event data

        Returns:
            A Panel containing the error information
        """
        error_message: str = str(data.get("error", "unknown error"))
        content = Text(error_message, style="bold red")
        return Panel(
            content,
            title="[bold red]Error[/bold red]",
            border_style="red",
            padding=(0, 1),
        )

    def _render_generic_event(self, event_type: str, data: dict[str, Any]) -> Panel:
        """Render a generic event.

        Args:
            event_type: The event type name
            data: The event data

        Returns:
            A Panel containing the formatted event
        """
        # Use syntax highlighting for JSON data
        data_json = json.dumps(data, indent=2)
        syntax = Syntax(
            data_json,
            "json",
            theme="monokai",
            background_color="default",
        )

        return Panel(
            syntax,
            title=f"[bold white]{event_type}[/bold white]",
            border_style="white",
            padding=(0, 1),
        )

    def _apply_style(self) -> None:
        """Apply CSS classes based on message type."""
        event_type = self.message.type

        if event_type == "UserMessageAdded":
            self.add_class("user-message")
        elif event_type == "LLMResponseReceived":
            self.add_class("assistant-message")
        elif event_type in ("ToolExecutionRequested", "ToolResultReceived"):
            self.add_class("tool-message")
        elif event_type == "ErrorOccurred":
            self.add_class("error-message")
        else:
            self.add_class("system-message")


class MessageList(VerticalScroll):
    """Scrollable container for displaying a list of messages.

    This widget maintains a list of messages and automatically scrolls
    to show the latest message when new messages are added.
    """

    DEFAULT_CSS = """
    MessageList {
        height: 100%;
        background: $panel;
        padding: 1;
    }

    MessageList > .user-message {
        margin-bottom: 1;
    }

    MessageList > .assistant-message {
        margin-bottom: 1;
    }

    MessageList > .tool-message {
        margin-bottom: 1;
    }

    MessageList > .system-message {
        margin-bottom: 1;
    }

    MessageList > .error-message {
        margin-bottom: 1;
    }
    """

    def __init__(
        self,
        show_timestamps: bool = True,
        auto_scroll: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize the message list.

        Args:
            show_timestamps: Whether to show timestamps on messages
            auto_scroll: Whether to automatically scroll to latest message
            **kwargs: Additional arguments to pass to VerticalScroll
        """
        super().__init__(**kwargs)
        self.show_timestamps = show_timestamps
        self.auto_scroll = auto_scroll
        self._message_count = 0

    def add_message(self, message: Message) -> None:
        """Add a new message to the list.

        Args:
            message: The message to add
        """
        # Create a message widget
        widget = MessageWidget(
            message=message,
            show_timestamp=self.show_timestamps,
        )

        # Mount the widget
        self.mount(widget)
        self._message_count += 1

        # Auto-scroll to the bottom if enabled
        if self.auto_scroll:
            self.scroll_end(animate=True)

    def clear_messages(self) -> None:
        """Clear all messages from the list."""
        # Remove all children
        self.remove_children()
        self._message_count = 0

    @property
    def message_count(self) -> int:
        """Get the number of messages currently displayed.

        Returns:
            The number of messages in the list
        """
        return self._message_count


class MessageInput(Input):
    """Single-line text input widget for user messages.

    This widget provides:
    - Single-line text input (Enter to submit)
    - Auto-clear after submission
    - Edge case handling (empty/whitespace-only messages)

    Uses the built-in Input.Submitted message when Enter is pressed.
    """

    def __init__(
        self,
        input_placeholder: str = "Type your message and press Enter...",
        **kwargs: Any,
    ) -> None:
        """Initialize the message input widget.

        Args:
            input_placeholder: Placeholder text to show when empty
            **kwargs: Additional arguments to pass to Input
        """
        super().__init__(
            placeholder=input_placeholder,
            **kwargs,
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission (Enter key).

        This method is called when the user presses Enter. We validate and trim
        the input, but don't stop the event from bubbling to the parent.

        Args:
            event: The input submitted event
        """
        text = event.value.strip()

        # Handle edge case: empty or whitespace-only messages
        if not text:
            # Don't submit empty messages, just clear the input and stop propagation
            self.value = ""
            event.stop()
            return

        # Update the event value to the trimmed text
        event.value = text

        # Clear the input after submission
        self.value = ""

        # Don't call event.stop() - let it bubble to the parent

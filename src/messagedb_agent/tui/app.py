"""Main TUI application for interactive agent conversations."""

import threading
from typing import Any, cast

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header

from messagedb_agent.config import Config, load_config
from messagedb_agent.store import Message, MessageDBClient, MessageDBConfig
from messagedb_agent.subscriber import InMemoryPositionStore, Subscriber
from messagedb_agent.tui.widgets import MessageInput, MessageList


class AgentTUI(App[None]):
    """Terminal UI application for interactive multi-message conversations with the agent.

    This TUI provides a persistent session where users can:
    - Send multiple messages in the same thread
    - View tool calls and LLM responses in real-time
    - See conversation history
    - Navigate with keyboard controls
    """

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
    }

    #content-container {
        height: 1fr;
        background: $panel;
        padding: 1;
    }

    #input-container {
        height: auto;
        background: $surface;
        padding: 1;
    }

    #placeholder {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $text-muted;
    }

    #loading {
        content-align: center middle;
        height: 100%;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def __init__(
        self,
        config_path: str | None = None,
        category: str = "agent",
        version: str = "v0",
        thread_id: str | None = None,
    ):
        """Initialize the TUI application.

        Args:
            config_path: Optional path to configuration file
            category: Stream category (default: agent)
            version: Stream version (default: v0)
            thread_id: Optional thread ID to continue existing session
        """
        super().__init__()
        self.config_path = config_path
        self.category = category
        self.version = version
        self.thread_id = thread_id

        # Will be initialized in on_mount
        self.config: Config | None = None
        self.store_client: MessageDBClient | None = None
        self.subscriber: Subscriber | None = None
        self.subscriber_thread: threading.Thread | None = None
        self.subscriber_stop_event = threading.Event()

    def compose(self) -> ComposeResult:
        """Compose the UI layout.

        Returns:
            The widgets that make up the UI.
        """
        yield Header(show_clock=True)
        yield Vertical(
            Container(
                MessageList(id="message-list", show_timestamps=True, auto_scroll=True),
                id="content-container",
            ),
            Container(
                MessageInput(id="message-input"),
                id="input-container",
            ),
            id="main-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the TUI when mounted.

        Loads configuration, initializes the Message DB client, and starts
        the subscriber for real-time event updates.
        """
        try:
            # Load configuration
            self.config = load_config(self.config_path)

            # Initialize Message DB client
            db_config = MessageDBConfig(
                host=self.config.message_db.host,
                port=self.config.message_db.port,
                database=self.config.message_db.database,
                user=self.config.message_db.user,
                password=self.config.message_db.password,
            )
            self.store_client = MessageDBClient(db_config)
            self.store_client.__enter__()

            # If thread_id is provided, start subscriber immediately
            if self.thread_id:
                self._start_subscriber(self.thread_id)

            self.log("TUI initialized successfully")

        except Exception as e:
            self.log(f"Error initializing TUI: {e}")
            # Show error to user
            self.notify(f"Error: {e}", severity="error", timeout=10)

    def on_message_input_submitted(self, message: MessageInput.Submitted) -> None:
        """Handle message input submission.

        Args:
            message: The submitted message event
        """
        # For now, just log the message
        # This will be replaced with actual agent integration
        self.log(f"User message submitted: {message.text}")

    def _start_subscriber(self, thread_id: str) -> None:
        """Start the subscriber for a specific thread.

        Args:
            thread_id: The thread ID to subscribe to
        """
        if self.store_client is None:
            self.log("Cannot start subscriber: store_client not initialized")
            return

        # Stop any existing subscriber
        self._stop_subscriber()

        # Build stream name for filtering
        stream_name = f"{self.category}:{self.version}-{thread_id}"

        # Get current max global position to start following from
        conn = self.store_client.get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COALESCE(MAX(global_position), -1) as max_position
                    FROM message_store.messages
                    WHERE category(stream_name) = %s
                    """,
                    (self.category,),
                )
                result = cast(dict[str, Any] | None, cur.fetchone())
                max_position: int = result["max_position"] if result else -1
                position_store = InMemoryPositionStore()
                if max_position >= 0:
                    position_store.update_position("tui-subscriber", max_position + 1)
                else:
                    position_store.update_position("tui-subscriber", 0)
        finally:
            self.store_client.return_connection(conn)

        # Create handler that updates the message list
        def handle_event(message: Message) -> None:
            # Only process events for our thread
            if message.stream_name != stream_name:
                return

            # Use call_from_thread to safely update UI from background thread
            self.call_from_thread(self._add_message_to_list, message)

        # Create subscriber
        self.subscriber = Subscriber(
            category=self.category,
            handler=handle_event,
            store_client=self.store_client,
            position_store=position_store,
            subscriber_id="tui-subscriber",
            poll_interval_ms=100,
            batch_size=100,
        )

        # Reset stop event
        self.subscriber_stop_event.clear()

        # Start subscriber in background thread
        def run_subscriber() -> None:
            if self.subscriber is None:
                return
            try:
                self.subscriber.start()
            except Exception as e:
                self.log(f"Subscriber error: {e}")
                self.call_from_thread(
                    self.notify, f"Subscriber error: {e}", severity="error", timeout=5
                )

        self.subscriber_thread = threading.Thread(target=run_subscriber, daemon=True)
        self.subscriber_thread.start()

        self.log(f"Subscriber started for thread {thread_id}")

    def _stop_subscriber(self) -> None:
        """Stop the subscriber and wait for thread to finish."""
        if self.subscriber is not None:
            self.log("Stopping subscriber...")
            self.subscriber.stop()
            self.subscriber_stop_event.set()

            # Wait for thread to finish
            if self.subscriber_thread is not None:
                self.subscriber_thread.join(timeout=2.0)
                self.subscriber_thread = None

            self.subscriber = None
            self.log("Subscriber stopped")

    def _add_message_to_list(self, message: Message) -> None:
        """Add a message to the message list widget.

        This method is called from the background subscriber thread via
        call_from_thread to safely update the UI.

        Args:
            message: The message to add
        """
        message_list = self.query_one("#message-list", MessageList)
        message_list.add_message(message)

    def show_loading(self, message: str = "Loading...") -> None:
        """Show a loading indicator in the message list.

        Args:
            message: Optional message to display
        """
        # This could be enhanced to show a loading widget in the message list
        self.notify(message, severity="information", timeout=2)

    def hide_loading(self) -> None:
        """Hide the loading indicator."""
        # Currently a no-op since we're using notify for loading states
        pass

    def on_unmount(self) -> None:
        """Clean up resources when the TUI is unmounted."""
        # Stop subscriber
        self._stop_subscriber()

        # Close store client
        if self.store_client is not None:
            self.store_client.__exit__(None, None, None)  # type: ignore[reportUnknownMemberType]
            self.store_client = None

        self.log("TUI cleaned up")


def main(
    config_path: str | None = None,
    category: str = "agent",
    version: str = "v0",
    thread_id: str | None = None,
) -> None:
    """Entry point for the TUI application.

    Args:
        config_path: Optional path to configuration file
        category: Stream category (default: agent)
        version: Stream version (default: v0)
        thread_id: Optional thread ID to continue existing session
    """
    app = AgentTUI(config_path=config_path, category=category, version=version, thread_id=thread_id)
    app.run()


if __name__ == "__main__":
    main()

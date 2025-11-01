"""Main TUI application for interactive agent conversations."""

import threading

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header

from messagedb_agent.config import Config, load_config
from messagedb_agent.engine.loop import process_thread
from messagedb_agent.engine.session import add_user_message, start_session
from messagedb_agent.events.tool import (
    TOOL_EXECUTION_APPROVED,
    TOOL_EXECUTION_REJECTED,
    TOOL_EXECUTION_REQUESTED,
)
from messagedb_agent.llm import create_llm_client
from messagedb_agent.llm.base import BaseLLMClient
from messagedb_agent.store import (
    Message,
    MessageDBClient,
    MessageDBConfig,
    read_stream,
    write_message,
)
from messagedb_agent.subscriber import InMemoryPositionStore, Subscriber
from messagedb_agent.tools import PermissionLevel, ToolRegistry, register_builtin_tools
from messagedb_agent.tui.approval_modal import ToolApprovalModal
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

        # Session state
        self.session_active = False
        self.session_completed = False

        # Will be initialized in on_mount
        self.config: Config | None = None
        self.store_client: MessageDBClient | None = None
        self.llm_client: BaseLLMClient | None = None
        self.tool_registry: ToolRegistry | None = None
        self.subscriber: Subscriber | None = None
        self.subscriber_thread: threading.Thread | None = None
        self.subscriber_stop_event = threading.Event()
        self.processing_thread: threading.Thread | None = None

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

            # Initialize LLM client
            self.llm_client = create_llm_client(self.config.vertex_ai)

            # Initialize tool registry
            self.tool_registry = ToolRegistry()
            register_builtin_tools(self.tool_registry)

            # If thread_id is provided, load existing session
            if self.thread_id:
                self._load_existing_session(self.thread_id)

            # Update header with thread ID
            self._update_header()

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
        # Check if session is completed
        if self.session_completed:
            self.notify(
                "Session has been completed. Please restart the app for a new session.",
                severity="warning",
                timeout=5,
            )
            return

        # Check if clients are initialized
        if self.store_client is None or self.llm_client is None or self.tool_registry is None:
            self.notify("Error: System not initialized", severity="error", timeout=5)
            return

        try:
            # If no thread_id, start a new session
            if self.thread_id is None:
                self.log(f"Starting new session with message: {message.text}")
                self.thread_id = start_session(
                    initial_message=message.text,
                    store_client=self.store_client,
                    category=self.category,
                    version=self.version,
                )
                self.session_active = True
                self._update_header()
                self.notify(f"Session started: {self.thread_id}", severity="information", timeout=3)

                # Start subscriber for real-time updates
                self._start_subscriber(self.thread_id)

                # Start processing in background thread
                self._start_processing()

            else:
                # Add message to existing session
                self.log(f"Adding message to existing session: {message.text}")
                add_user_message(
                    thread_id=self.thread_id,
                    message=message.text,
                    store_client=self.store_client,
                    category=self.category,
                    version=self.version,
                )

                # If processing thread is not running, start it
                if self.processing_thread is None or not self.processing_thread.is_alive():
                    self._start_processing()

        except Exception as e:
            self.log(f"Error handling message submission: {e}")
            self.notify(f"Error: {e}", severity="error", timeout=10)

    def _start_subscriber(self, thread_id: str, start_position: int = 0) -> None:
        """Start the subscriber for a specific thread.

        Args:
            thread_id: The thread ID to subscribe to
            start_position: Global position to start reading from (default: 0)
        """
        if self.store_client is None:
            self.log("Cannot start subscriber: store_client not initialized")
            return

        # Stop any existing subscriber
        self._stop_subscriber()

        # Build stream name for filtering
        stream_name = f"{self.category}:{self.version}-{thread_id}"

        # Build category (includes version, e.g., "agent:v0")
        category = f"{self.category}:{self.version}"

        # Initialize position store with the starting position
        position_store = InMemoryPositionStore()
        position_store.update_position("tui-subscriber", start_position)

        # Create handler that updates the message list
        def handle_event(message: Message) -> None:
            # Only process events for our thread
            if message.stream_name != stream_name:
                return

            # Use call_from_thread to safely update UI from background thread
            self.call_from_thread(self._add_message_to_list, message)

        # Create subscriber
        self.subscriber = Subscriber(
            category=category,
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

        # Handle SessionCompleted event
        if message.type == "SessionCompleted":
            self.session_completed = True
            self.session_active = False

            # Disable the input widget
            message_input = self.query_one("#message-input", MessageInput)
            message_input.disabled = True

            self.notify("Session completed", severity="information", timeout=5)

        # Handle ToolExecutionRequested event - check if approval needed
        elif message.type == TOOL_EXECUTION_REQUESTED:
            self._handle_tool_execution_requested(message)

    def _handle_tool_execution_requested(self, message: Message) -> None:
        """Handle ToolExecutionRequested event and prompt for approval if needed.

        This method checks if the requested tool requires approval based on its
        permission level. If approval is required, it shows the approval modal
        and writes the approval/rejection event based on user response.

        Args:
            message: The ToolExecutionRequested event message
        """
        if self.tool_registry is None or self.store_client is None or self.thread_id is None:
            self.log("Cannot handle tool approval: clients not initialized")
            return

        # Extract tool info from message data
        tool_name = message.data.get("tool_name", "unknown")
        arguments = message.data.get("arguments", {})

        # Check if tool exists and requires approval
        if not self.tool_registry.has(tool_name):
            self.log(f"Tool {tool_name} not found in registry, skipping approval check")
            return

        tool_obj = self.tool_registry.get(tool_name)
        permission_level = tool_obj.permission_level

        # Only show approval modal for tools that require approval
        if permission_level not in (PermissionLevel.REQUIRES_APPROVAL, PermissionLevel.DANGEROUS):
            self.log(f"Tool {tool_name} is SAFE, no approval needed")
            return

        self.log(f"Tool {tool_name} requires approval, showing modal")

        # Show approval modal asynchronously
        async def show_approval_and_respond() -> None:
            """Async function to show modal and handle response."""
            if self.store_client is None or self.thread_id is None:
                return

            # Show modal and wait for user response
            approved = await self.push_screen_wait(
                ToolApprovalModal(
                    tool_name=tool_name,
                    arguments=arguments,
                    permission_level=permission_level.value,
                )
            )

            # Build stream name
            stream_name = f"{self.category}:{self.version}-{self.thread_id}"

            # Get metadata from original message (includes tool_id, tool_call_id, tool_index)
            metadata = message.metadata or {}

            if approved:
                # User approved - write ToolExecutionApproved event
                self.log(f"User approved tool {tool_name}")
                try:
                    write_message(
                        client=self.store_client,
                        stream_name=stream_name,
                        message_type=TOOL_EXECUTION_APPROVED,
                        data={
                            "tool_name": tool_name,
                            "approved_by": "user",
                        },
                        metadata=metadata,
                    )
                    self.notify(
                        f"Approved: {tool_name}",
                        severity="information",
                        timeout=3,
                    )
                except Exception as e:
                    self.log(f"Error writing approval event: {e}")
                    self.notify(
                        f"Error writing approval: {e}",
                        severity="error",
                        timeout=5,
                    )
            else:
                # User rejected - write ToolExecutionRejected event
                self.log(f"User rejected tool {tool_name}")
                try:
                    write_message(
                        client=self.store_client,
                        stream_name=stream_name,
                        message_type=TOOL_EXECUTION_REJECTED,
                        data={
                            "tool_name": tool_name,
                            "rejected_by": "user",
                            "reason": "User rejected execution",
                        },
                        metadata=metadata,
                    )
                    self.notify(
                        f"Rejected: {tool_name}",
                        severity="warning",
                        timeout=3,
                    )
                except Exception as e:
                    self.log(f"Error writing rejection event: {e}")
                    self.notify(
                        f"Error writing rejection: {e}",
                        severity="error",
                        timeout=5,
                    )

        # Schedule the async function to run
        self.call_later(show_approval_and_respond)

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

    def _update_header(self) -> None:
        """Update the header to display current thread ID."""
        if self.thread_id:
            # Update the app's sub_title to show thread ID
            self.sub_title = f"Thread: {self.thread_id[:8]}..."
        else:
            self.sub_title = "No active session"

    def _load_existing_session(self, thread_id: str) -> None:
        """Load an existing session and display its conversation history.

        Args:
            thread_id: The thread ID to load
        """
        if self.store_client is None:
            self.log("Cannot load session: store_client not initialized")
            return

        try:
            # Build stream name
            stream_name = f"{self.category}:{self.version}-{thread_id}"

            # Read all events from the stream
            messages = read_stream(self.store_client, stream_name)

            # Add all messages to the display
            message_list = self.query_one("#message-list", MessageList)
            last_global_position = -1
            for message in messages:
                message_list.add_message(message)
                last_global_position = message.global_position

                # Check if session is already completed
                if message.type == "SessionCompleted":
                    self.session_completed = True
                    self.session_active = False

                    # Disable the input widget
                    message_input = self.query_one("#message-input", MessageInput)
                    message_input.disabled = True

            # If not completed, mark session as active and start subscriber
            # Start from position after the last loaded event
            if not self.session_completed:
                self.session_active = True
                next_position = last_global_position + 1 if last_global_position >= 0 else 0
                self._start_subscriber(thread_id, start_position=next_position)

            self.log(f"Loaded existing session with {len(messages)} messages")
            self.notify(
                f"Loaded session: {len(messages)} messages",
                severity="information",
                timeout=3,
            )

        except Exception as e:
            self.log(f"Error loading existing session: {e}")
            self.notify(f"Error loading session: {e}", severity="error", timeout=10)

    def _start_processing(self) -> None:
        """Start the processing loop in a background thread."""
        if self.thread_id is None:
            self.log("Cannot start processing: no thread_id")
            return

        if self.store_client is None or self.llm_client is None or self.tool_registry is None:
            self.log("Cannot start processing: clients not initialized")
            return

        # Build stream name
        stream_name = f"{self.category}:{self.version}-{self.thread_id}"

        # Define processing function to run in background
        def run_processing() -> None:
            if (
                self.store_client is None
                or self.llm_client is None
                or self.tool_registry is None
                or self.thread_id is None
            ):
                return

            try:
                self.log("Starting processing loop")
                process_thread(
                    thread_id=self.thread_id,
                    stream_name=stream_name,
                    store_client=self.store_client,
                    llm_client=self.llm_client,
                    tool_registry=self.tool_registry,
                    max_iterations=100,
                    auto_approve_tools=False,  # Use manual approval via TUI modal
                )
                self.log("Processing loop completed")
            except Exception as e:
                self.log(f"Processing error: {e}")
                self.call_from_thread(
                    self.notify,
                    f"Processing error: {e}",
                    severity="error",
                    timeout=10,
                )

        # Start processing thread
        self.processing_thread = threading.Thread(target=run_processing, daemon=True)
        self.processing_thread.start()
        self.log("Processing thread started")

    def on_unmount(self) -> None:
        """Clean up resources when the TUI is unmounted."""
        # Stop subscriber
        self._stop_subscriber()

        # Wait for processing thread to finish (with timeout)
        if self.processing_thread is not None:
            self.log("Waiting for processing thread to finish...")
            self.processing_thread.join(timeout=5.0)
            if self.processing_thread.is_alive():
                self.log("Processing thread did not finish in time")
            self.processing_thread = None

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

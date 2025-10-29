"""Main TUI application for interactive agent conversations."""

from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Static


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

    #content-container {
        height: 100%;
        background: $panel;
        padding: 1;
    }

    #placeholder {
        width: 100%;
        height: 100%;
        content-align: center middle;
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("ctrl+c", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the UI layout.

        Returns:
            The widgets that make up the UI.
        """
        yield Header(show_clock=True)
        yield Container(
            Vertical(
                Static("Agent TUI - Ready to start conversation", id="placeholder"),
                id="content-container",
            )
        )
        yield Footer()


def main() -> None:
    """Entry point for the TUI application."""
    app = AgentTUI()
    app.run()


if __name__ == "__main__":
    main()

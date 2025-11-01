"""Tool approval modal for the TUI.

This module provides a modal dialog for approving or rejecting tool executions
that require user permission.
"""

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static


class ToolApprovalModal(ModalScreen[bool]):
    """Modal screen for approving or rejecting tool execution.

    This modal displays:
    - Tool name
    - Tool arguments (formatted as JSON)
    - Permission level
    - Approve/Reject buttons

    Returns:
        True if approved, False if rejected
    """

    CSS = """
    ToolApprovalModal {
        align: center middle;
    }

    #approval-dialog {
        width: 80;
        height: auto;
        max-height: 30;
        background: $panel;
        border: thick $primary;
        padding: 1 2;
    }

    #approval-header {
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }

    #tool-info {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }

    #tool-name {
        width: 100%;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    #permission-level {
        width: 100%;
        color: $warning;
        margin-bottom: 1;
    }

    #arguments-label {
        width: 100%;
        margin-bottom: 1;
    }

    #arguments {
        width: 100%;
        max-height: 10;
        background: $surface;
        padding: 1;
        border: round $primary;
        overflow-y: auto;
        margin-bottom: 1;
    }

    #button-container {
        width: 100%;
        height: auto;
        align: center middle;
    }

    Button {
        margin: 0 1;
    }

    .approve-button {
        background: $success;
    }

    .reject-button {
        background: $error;
    }
    """

    BINDINGS = [
        ("y", "approve", "Approve"),
        ("n", "reject", "Reject"),
        ("escape", "reject", "Reject"),
    ]

    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        permission_level: str,
        **kwargs: Any,
    ):
        """Initialize the tool approval modal.

        Args:
            tool_name: Name of the tool requesting approval
            arguments: Arguments that will be passed to the tool
            permission_level: Permission level of the tool (for display)
            **kwargs: Additional keyword arguments for ModalScreen
        """
        super().__init__(**kwargs)
        self.tool_name = tool_name
        self.arguments = arguments
        self.permission_level = permission_level

    def compose(self) -> ComposeResult:
        """Compose the modal UI.

        Returns:
            The widgets that make up the modal.
        """
        # Format arguments as pretty JSON
        try:
            args_formatted = json.dumps(self.arguments, indent=2)
        except Exception:
            args_formatted = str(self.arguments)

        yield Container(
            Vertical(
                Label("⚠️  Tool Approval Required", id="approval-header"),
                Container(
                    Label(f"Tool: {self.tool_name}", id="tool-name"),
                    Label(
                        f"Permission Level: {self.permission_level}",
                        id="permission-level",
                    ),
                    Label("Arguments:", id="arguments-label"),
                    Static(args_formatted, id="arguments"),
                    id="tool-info",
                ),
                Horizontal(
                    Button("Approve (y)", variant="success", id="approve-button"),
                    Button("Reject (n)", variant="error", id="reject-button"),
                    id="button-container",
                ),
            ),
            id="approval-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events.

        Args:
            event: The button press event
        """
        if event.button.id == "approve-button":
            self.dismiss(True)
        elif event.button.id == "reject-button":
            self.dismiss(False)

    def action_approve(self) -> None:
        """Action to approve tool execution (bound to 'y' key)."""
        self.dismiss(True)

    def action_reject(self) -> None:
        """Action to reject tool execution (bound to 'n' and 'escape' keys)."""
        self.dismiss(False)

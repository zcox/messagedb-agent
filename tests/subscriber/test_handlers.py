"""Tests for subscriber handlers module."""

import json
from datetime import datetime
from uuid import UUID

import pytest

from messagedb_agent.store.operations import Message
from messagedb_agent.subscriber.handlers import (
    ConversationPrinter,
    event_type_router,
    filter_handler,
    log_event_handler,
    print_event_handler,
)


@pytest.fixture
def sample_message() -> Message:
    """Create a sample message for testing."""
    return Message(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="TestEvent",
        position=0,
        global_position=100,
        data={"message": "Hello, world!"},
        metadata={"trace_id": "abc123"},
        time=datetime.fromisoformat("2024-01-01T00:00:00"),
    )


@pytest.fixture
def user_message() -> Message:
    """Create a user message event."""
    return Message(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="UserMessageAdded",
        position=0,
        global_position=100,
        data={"message": "What is the weather today?"},
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:00"),
    )


@pytest.fixture
def llm_response_message() -> Message:
    """Create an LLM response event."""
    return Message(
        id=UUID("22345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="LLMResponseReceived",
        position=1,
        global_position=101,
        data={
            "response": {
                "text": "Let me check the weather for you.",
                "tool_calls": [
                    {
                        "name": "get_weather",
                        "arguments": {"city": "San Francisco"},
                    }
                ],
            }
        },
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:01"),
    )


@pytest.fixture
def tool_result_message() -> Message:
    """Create a tool result event."""
    return Message(
        id=UUID("32345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="ToolResultReceived",
        position=2,
        global_position=102,
        data={
            "tool_name": "get_weather",
            "result": {"temperature": 72, "conditions": "sunny"},
        },
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:02"),
    )


def test_print_event_handler(sample_message: Message, capsys) -> None:
    """Test print_event_handler outputs formatted JSON."""
    print_event_handler(sample_message)

    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert output["id"] == str(sample_message.id)
    assert output["type"] == "TestEvent"
    assert output["stream_name"] == "agent:v0-thread123"
    assert output["position"] == 0
    assert output["global_position"] == 100
    assert output["data"] == {"message": "Hello, world!"}
    assert output["metadata"] == {"trace_id": "abc123"}
    assert output["time"] == "2024-01-01T00:00:00"


def test_filter_handler_matches(sample_message: Message) -> None:
    """Test filter_handler calls handler when predicate is True."""
    called = []

    def handler(msg: Message) -> None:
        called.append(msg)

    def predicate(msg: Message) -> bool:
        return "thread123" in msg.stream_name

    filtered = filter_handler(predicate, handler)
    filtered(sample_message)

    assert len(called) == 1
    assert called[0] == sample_message


def test_filter_handler_rejects(sample_message: Message) -> None:
    """Test filter_handler skips handler when predicate is False."""
    called = []

    def handler(msg: Message) -> None:
        called.append(msg)

    def predicate(msg: Message) -> bool:
        return "thread999" in msg.stream_name

    filtered = filter_handler(predicate, handler)
    filtered(sample_message)

    assert len(called) == 0


def test_filter_handler_by_event_type(sample_message: Message) -> None:
    """Test filtering by event type."""
    called = []

    def handler(msg: Message) -> None:
        called.append(msg)

    def is_user_message(msg: Message) -> bool:
        return msg.type == "UserMessageAdded"

    filtered = filter_handler(is_user_message, handler)
    filtered(sample_message)  # TestEvent - should be filtered out

    assert len(called) == 0


def test_event_type_router_routes_correctly(sample_message: Message, user_message: Message) -> None:
    """Test event_type_router routes events to correct handlers."""
    test_events = []
    user_events = []

    def test_handler(msg: Message) -> None:
        test_events.append(msg)

    def user_handler(msg: Message) -> None:
        user_events.append(msg)

    router = event_type_router(
        {
            "TestEvent": test_handler,
            "UserMessageAdded": user_handler,
        }
    )

    router(sample_message)
    router(user_message)

    assert len(test_events) == 1
    assert test_events[0] == sample_message
    assert len(user_events) == 1
    assert user_events[0] == user_message


def test_event_type_router_unrouted_event(sample_message: Message) -> None:
    """Test event_type_router handles unrouted event types gracefully."""
    called = []

    def handler(msg: Message) -> None:
        called.append(msg)

    router = event_type_router({"DifferentEvent": handler})

    # Should not raise, just not call any handler
    router(sample_message)

    assert len(called) == 0


def test_event_type_router_empty_handlers() -> None:
    """Test event_type_router with no handlers."""
    message = Message(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        stream_name="test:v0-123",
        type="AnyEvent",
        position=0,
        global_position=1,
        data={},
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:00"),
    )

    router = event_type_router({})

    # Should not raise
    router(message)


def test_log_event_handler_default_logger(sample_message: Message) -> None:
    """Test log_event_handler logs events with default logger."""
    logged_events = []

    # Create a mock logger that captures log calls
    class TestLogger:
        def info(self, event: str, **kwargs) -> None:
            logged_events.append({"event": event, **kwargs})

    # Temporarily replace the logger in the handlers module
    import messagedb_agent.subscriber.handlers as handlers_module

    original_logger = handlers_module.logger
    handlers_module.logger = TestLogger()  # type: ignore

    try:
        handler = log_event_handler()
        handler(sample_message)

        assert len(logged_events) == 1
        assert logged_events[0]["event"] == "event_received"
        assert logged_events[0]["event_type"] == "TestEvent"
    finally:
        # Restore original logger
        handlers_module.logger = original_logger


def test_log_event_handler_custom_logger(sample_message: Message) -> None:
    """Test log_event_handler with custom logger."""
    logged_events = []

    class TestLogger:
        def info(self, event: str, **kwargs) -> None:
            logged_events.append({"event": event, **kwargs})

    custom_logger = TestLogger()
    handler = log_event_handler(custom_logger)  # type: ignore

    handler(sample_message)

    assert len(logged_events) == 1
    assert logged_events[0]["event"] == "event_received"
    assert logged_events[0]["event_type"] == "TestEvent"
    assert logged_events[0]["stream_name"] == "agent:v0-thread123"


def test_conversation_printer_user_message(user_message: Message, capsys) -> None:
    """Test ConversationPrinter formats user messages."""
    printer = ConversationPrinter()
    printer(user_message)

    captured = capsys.readouterr()
    assert "[User]" in captured.out
    assert "What is the weather today?" in captured.out


def test_conversation_printer_llm_response(llm_response_message: Message, capsys) -> None:
    """Test ConversationPrinter formats LLM responses."""
    printer = ConversationPrinter()
    printer(llm_response_message)

    captured = capsys.readouterr()
    assert "[Assistant]" in captured.out
    assert "Let me check the weather for you." in captured.out
    assert "[Tool Calls]" in captured.out
    assert "get_weather" in captured.out


def test_conversation_printer_hide_tool_calls(llm_response_message: Message, capsys) -> None:
    """Test ConversationPrinter can hide tool calls."""
    printer = ConversationPrinter(show_tool_calls=False)
    printer(llm_response_message)

    captured = capsys.readouterr()
    assert "[Assistant]" in captured.out
    assert "[Tool Calls]" not in captured.out


def test_conversation_printer_tool_result(tool_result_message: Message, capsys) -> None:
    """Test ConversationPrinter formats tool results."""
    printer = ConversationPrinter()
    printer(tool_result_message)

    captured = capsys.readouterr()
    assert "[Tool Result: get_weather]" in captured.out
    assert "temperature" in captured.out
    assert "72" in captured.out


def test_conversation_printer_hide_tool_results(tool_result_message: Message, capsys) -> None:
    """Test ConversationPrinter can hide tool results."""
    printer = ConversationPrinter(show_tool_results=False)
    printer(tool_result_message)

    captured = capsys.readouterr()
    assert captured.out == ""  # Nothing should be printed


def test_conversation_printer_system_event(capsys) -> None:
    """Test ConversationPrinter handles system events."""
    session_started = Message(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="SessionStarted",
        position=0,
        global_position=100,
        data={"thread_id": "thread123"},
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:00"),
    )

    # By default, system events are not shown
    printer = ConversationPrinter()
    printer(session_started)
    captured = capsys.readouterr()
    assert captured.out == ""

    # When show_system=True, system events should be shown
    printer = ConversationPrinter(show_system=True)
    printer(session_started)
    captured = capsys.readouterr()
    assert "[Session Started]" in captured.out
    assert "thread123" in captured.out


def test_conversation_printer_session_completed(capsys) -> None:
    """Test ConversationPrinter handles session completed events."""
    session_completed = Message(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="SessionCompleted",
        position=10,
        global_position=110,
        data={"reason": "User request completed"},
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:10"),
    )

    printer = ConversationPrinter(show_system=True)
    printer(session_completed)

    captured = capsys.readouterr()
    assert "[Session Completed]" in captured.out
    assert "User request completed" in captured.out


def test_conversation_printer_error_event(capsys) -> None:
    """Test ConversationPrinter handles error events."""
    error_event = Message(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="ErrorOccurred",
        position=5,
        global_position=105,
        data={"error": "Tool execution failed"},
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:05"),
    )

    printer = ConversationPrinter(show_system=True)
    printer(error_event)

    captured = capsys.readouterr()
    assert "[Error]" in captured.out
    assert "Tool execution failed" in captured.out


def test_conversation_printer_tool_execution_requested(capsys) -> None:
    """Test ConversationPrinter handles tool execution requested events."""
    tool_execution = Message(
        id=UUID("12345678-1234-5678-1234-567812345678"),
        stream_name="agent:v0-thread123",
        type="ToolExecutionRequested",
        position=3,
        global_position=103,
        data={
            "tool_name": "search_web",
            "arguments": {"query": "Python event sourcing"},
        },
        metadata={},
        time=datetime.fromisoformat("2024-01-01T00:00:03"),
    )

    printer = ConversationPrinter()
    printer(tool_execution)

    captured = capsys.readouterr()
    assert "[Tool Call: search_web]" in captured.out
    assert "Python event sourcing" in captured.out


def test_filter_handler_composition(sample_message: Message) -> None:
    """Test that filter_handler can be composed with other handlers."""
    called = []

    def handler(msg: Message) -> None:
        called.append(msg)

    def is_agent_category(msg: Message) -> bool:
        return msg.stream_name.startswith("agent:")

    def is_position_zero(msg: Message) -> bool:
        return msg.position == 0

    # Compose two filters
    filtered = filter_handler(is_agent_category, filter_handler(is_position_zero, handler))

    filtered(sample_message)

    assert len(called) == 1


def test_event_type_router_with_filter(user_message: Message) -> None:
    """Test combining event_type_router with filter_handler."""
    called = []

    def handler(msg: Message) -> None:
        called.append(msg)

    def is_thread123(msg: Message) -> bool:
        return "thread123" in msg.stream_name

    # Route events, then filter
    router = event_type_router({"UserMessageAdded": handler})
    filtered_router = filter_handler(is_thread123, router)

    filtered_router(user_message)

    assert len(called) == 1

"""Tests for the CLI module."""

import json
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import Mock, patch

import pytest

from messagedb_agent.cli import (
    cmd_continue,
    cmd_list,
    cmd_message,
    cmd_show,
    cmd_start,
    create_parser,
    main,
)
from messagedb_agent.config import (
    Config,
    LoggingConfig,
    MessageDBConfig,
    ProcessingConfig,
    VertexAIConfig,
)
from messagedb_agent.events import (
    LLM_RESPONSE_RECEIVED,
    SESSION_COMPLETED,
    SESSION_STARTED,
    USER_MESSAGE_ADDED,
)
from messagedb_agent.projections import SessionState, SessionStatus
from messagedb_agent.store import Message


@pytest.fixture
def test_config():
    """Create a test configuration."""
    return Config(
        message_db=MessageDBConfig(
            host="localhost",
            port=5432,
            database="message_store",
            user="postgres",
            password="password",
        ),
        vertex_ai=VertexAIConfig(
            project="test-project",
            location="us-central1",
            model_name="claude-sonnet-4-5@20250929",
        ),
        processing=ProcessingConfig(max_iterations=100, enable_tracing=False),
        logging=LoggingConfig(log_level="INFO", log_format="json"),
    )


@pytest.fixture
def sample_messages():
    """Create sample messages for testing (returned by read_stream)."""
    from uuid import uuid4

    now = datetime.now(UTC)
    return [
        Message(
            id=str(uuid4()),
            stream_name="agent:v0-thread-123",
            type=SESSION_STARTED,
            position=0,
            global_position=100,
            data={"thread_id": "thread-123"},
            metadata={},
            time=now,
        ),
        Message(
            id=str(uuid4()),
            stream_name="agent:v0-thread-123",
            type=USER_MESSAGE_ADDED,
            position=1,
            global_position=101,
            data={"message": "Hello", "timestamp": now.isoformat()},
            metadata={},
            time=now,
        ),
        Message(
            id=str(uuid4()),
            stream_name="agent:v0-thread-123",
            type=LLM_RESPONSE_RECEIVED,
            position=2,
            global_position=102,
            data={
                "response_text": "Hi there!",
                "tool_calls": [],
                "model_name": "claude-sonnet-4-5@20250929",
                "token_usage": {"input": 10, "output": 5},
            },
            metadata={},
            time=now,
        ),
        Message(
            id=str(uuid4()),
            stream_name="agent:v0-thread-123",
            type=SESSION_COMPLETED,
            position=3,
            global_position=103,
            data={"completion_reason": "success"},
            metadata={},
            time=now,
        ),
    ]


class TestParser:
    """Tests for argument parser."""

    def test_create_parser(self):
        """Test parser creation."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "messagedb-agent"

    def test_parse_start_command(self):
        """Test parsing start command."""
        parser = create_parser()
        args = parser.parse_args(["start", "Hello world"])
        assert args.command == "start"
        assert args.message == "Hello world"
        assert args.category == "agent"
        assert args.version == "v0"

    def test_parse_start_with_options(self):
        """Test parsing start command with options."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "--category",
                "test",
                "--version",
                "v1",
                "start",
                "Hello",
                "--max-iterations",
                "50",
            ]
        )
        assert args.command == "start"
        assert args.message == "Hello"
        assert args.category == "test"
        assert args.version == "v1"
        assert args.max_iterations == 50

    def test_parse_continue_command(self):
        """Test parsing continue command."""
        parser = create_parser()
        args = parser.parse_args(["continue", "thread-123"])
        assert args.command == "continue"
        assert args.thread_id == "thread-123"

    def test_parse_message_command(self):
        """Test parsing message command."""
        parser = create_parser()
        args = parser.parse_args(["message", "thread-123", "Hello again!"])
        assert args.command == "message"
        assert args.thread_id == "thread-123"
        assert args.message == "Hello again!"

    def test_parse_show_command(self):
        """Test parsing show command."""
        parser = create_parser()
        args = parser.parse_args(["show", "thread-123"])
        assert args.command == "show"
        assert args.thread_id == "thread-123"
        assert args.format == "text"
        assert not args.full

    def test_parse_show_with_options(self):
        """Test parsing show command with options."""
        parser = create_parser()
        args = parser.parse_args(["show", "thread-123", "--format", "json", "--full"])
        assert args.format == "json"
        assert args.full

    def test_parse_list_command(self):
        """Test parsing list command."""
        parser = create_parser()
        args = parser.parse_args(["list"])
        assert args.command == "list"
        assert args.limit == 10
        assert args.format == "text"

    def test_parse_list_with_options(self):
        """Test parsing list command with options."""
        parser = create_parser()
        args = parser.parse_args(["list", "--limit", "20", "--format", "json"])
        assert args.limit == 20
        assert args.format == "json"

    def test_parse_config_option(self):
        """Test parsing global config option."""
        parser = create_parser()
        args = parser.parse_args(["--config", ".env.test", "list"])
        assert args.config == ".env.test"


class TestStartCommand:
    """Tests for start command."""

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.create_llm_client")
    @patch("messagedb_agent.cli.start_session")
    @patch("messagedb_agent.cli.process_thread")
    def test_cmd_start_success(
        self,
        mock_process,
        mock_start_session,
        mock_create_llm,
        mock_db_client,
        test_config,
    ):
        """Test successful start command execution."""
        # Setup mocks
        mock_start_session.return_value = "thread-123"
        mock_final_state = SessionState(
            thread_id="thread-123",
            status=SessionStatus.COMPLETED,
            message_count=2,
            tool_call_count=0,
            llm_call_count=1,
            error_count=0,
            last_activity_time=datetime.now(UTC),
            session_start_time=datetime.now(UTC),
            session_end_time=datetime.now(UTC),
        )
        mock_process.return_value = mock_final_state

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["start", "Hello world"])

        # Execute command
        result = cmd_start(args, test_config)

        # Verify
        assert result == 0
        mock_start_session.assert_called_once()
        mock_process.assert_called_once()

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.create_llm_client")
    @patch("messagedb_agent.cli.start_session")
    def test_cmd_start_failure(
        self, mock_start_session, mock_create_llm, mock_db_client, test_config
    ):
        """Test start command with error."""
        # Setup mock to raise error
        mock_start_session.side_effect = Exception("Database error")

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["start", "Hello"])

        # Execute command
        result = cmd_start(args, test_config)

        # Verify
        assert result == 1


class TestContinueCommand:
    """Tests for continue command."""

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.create_llm_client")
    @patch("messagedb_agent.cli.read_stream")
    @patch("messagedb_agent.cli.process_thread")
    def test_cmd_continue_success(
        self,
        mock_process,
        mock_read_stream,
        mock_create_llm,
        mock_db_client,
        test_config,
        sample_messages,
    ):
        """Test successful continue command execution."""
        # Setup mocks
        mock_read_stream.return_value = sample_messages
        mock_final_state = SessionState(
            thread_id="thread-123",
            status=SessionStatus.COMPLETED,
            message_count=2,
            tool_call_count=0,
            llm_call_count=1,
            error_count=0,
            last_activity_time=datetime.now(UTC),
            session_start_time=datetime.now(UTC),
            session_end_time=datetime.now(UTC),
        )
        mock_process.return_value = mock_final_state

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["continue", "thread-123"])

        # Execute command
        result = cmd_continue(args, test_config)

        # Verify
        assert result == 0
        mock_process.assert_called_once()

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.create_llm_client")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_continue_not_found(
        self, mock_read_stream, mock_create_llm, mock_db_client, test_config
    ):
        """Test continue command with non-existent session."""
        # Setup mock to return empty events
        mock_read_stream.return_value = []

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["continue", "thread-999"])

        # Execute command
        result = cmd_continue(args, test_config)

        # Verify
        assert result == 1


class TestMessageCommand:
    """Tests for message command."""

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.create_llm_client")
    @patch("messagedb_agent.cli.read_stream")
    @patch("messagedb_agent.cli.add_user_message")
    @patch("messagedb_agent.cli.process_thread")
    def test_cmd_message_success(
        self,
        mock_process,
        mock_add_message,
        mock_read_stream,
        mock_create_llm,
        mock_db_client,
        test_config,
        sample_messages,
    ):
        """Test successful message command execution."""
        # Setup mocks
        mock_read_stream.return_value = sample_messages
        mock_add_message.return_value = 4
        mock_final_state = SessionState(
            thread_id="thread-123",
            status=SessionStatus.COMPLETED,
            message_count=3,
            tool_call_count=0,
            llm_call_count=2,
            error_count=0,
            last_activity_time=datetime.now(UTC),
            session_start_time=datetime.now(UTC),
            session_end_time=datetime.now(UTC),
        )
        mock_process.return_value = mock_final_state

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["message", "thread-123", "Hello again!"])

        # Execute command
        result = cmd_message(args, test_config)

        # Verify
        assert result == 0
        mock_add_message.assert_called_once()
        mock_process.assert_called_once()

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.create_llm_client")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_message_session_not_found(
        self, mock_read_stream, mock_create_llm, mock_db_client, test_config
    ):
        """Test message command with non-existent session."""
        # Setup mock to return empty events
        mock_read_stream.return_value = []

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["message", "thread-999", "Test message"])

        # Execute command
        result = cmd_message(args, test_config)

        # Verify
        assert result == 1

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.create_llm_client")
    @patch("messagedb_agent.cli.read_stream")
    @patch("messagedb_agent.cli.add_user_message")
    def test_cmd_message_add_fails(
        self,
        mock_add_message,
        mock_read_stream,
        mock_create_llm,
        mock_db_client,
        test_config,
        sample_messages,
    ):
        """Test message command when add_user_message fails."""
        # Setup mocks
        mock_read_stream.return_value = sample_messages
        mock_add_message.side_effect = Exception("Failed to write message")

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["message", "thread-123", "Test message"])

        # Execute command
        result = cmd_message(args, test_config)

        # Verify
        assert result == 1


class TestShowCommand:
    """Tests for show command."""

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_show_text_format(
        self, mock_read_stream, mock_db_client, test_config, sample_messages
    ):
        """Test show command with text format."""
        # Setup mocks
        mock_read_stream.return_value = sample_messages

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["show", "thread-123"])

        # Execute command
        result = cmd_show(args, test_config)

        # Verify
        assert result == 0

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_show_json_format(
        self, mock_read_stream, mock_db_client, test_config, sample_messages
    ):
        """Test show command with JSON format."""
        # Setup mocks
        mock_read_stream.return_value = sample_messages

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["show", "thread-123", "--format", "json"])

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            result = cmd_show(args, test_config)

            # Verify
            assert result == 0
            output = fake_out.getvalue()
            parsed = json.loads(output)
            assert len(parsed) == 4
            assert parsed[0]["type"] == SESSION_STARTED

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_show_full_flag(
        self, mock_read_stream, mock_db_client, test_config, sample_messages
    ):
        """Test show command with --full flag."""
        # Setup mocks
        mock_read_stream.return_value = sample_messages

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["show", "thread-123", "--full"])

        # Execute command
        result = cmd_show(args, test_config)

        # Verify
        assert result == 0

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_show_not_found(self, mock_read_stream, mock_db_client, test_config):
        """Test show command with non-existent session."""
        # Setup mock to return empty events
        mock_read_stream.return_value = []

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["show", "thread-999"])

        # Execute command
        result = cmd_show(args, test_config)

        # Verify
        assert result == 1


class TestListCommand:
    """Tests for list command."""

    def _setup_db_mock(self, mock_db_client, fetchall_result):
        """Helper to setup database mock properly."""
        mock_store = Mock()
        mock_conn = Mock()
        mock_cursor = Mock()

        # Setup outer context manager (MessageDBClient)
        mock_client_cm = Mock()
        mock_client_cm.__enter__ = Mock(return_value=mock_store)
        mock_client_cm.__exit__ = Mock(return_value=False)
        mock_db_client.return_value = mock_client_cm

        # Setup inner context manager (connection)
        mock_store.__enter__ = Mock(return_value=mock_conn)
        mock_store.__exit__ = Mock(return_value=False)

        # Setup cursor context manager
        mock_cursor_cm = Mock()
        mock_cursor_cm.__enter__ = Mock(return_value=mock_cursor)
        mock_cursor_cm.__exit__ = Mock(return_value=False)
        mock_conn.cursor = Mock(return_value=mock_cursor_cm)

        # Set fetchall result
        mock_cursor.fetchall.return_value = fetchall_result
        mock_cursor.execute = Mock()

        return mock_cursor

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_list_text_format(
        self, mock_read_stream, mock_db_client, test_config, sample_messages
    ):
        """Test list command with text format."""
        # Mock database query results
        now = datetime.now(UTC)
        fetchall_result = [
            ("agent:v0-thread-123", now),
            ("agent:v0-thread-456", now),
        ]
        self._setup_db_mock(mock_db_client, fetchall_result)

        # Mock read_stream to return sample events
        mock_read_stream.return_value = sample_messages

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["list"])

        # Execute command
        result = cmd_list(args, test_config)

        # Verify
        assert result == 0

    @patch("messagedb_agent.cli.MessageDBClient")
    @patch("messagedb_agent.cli.read_stream")
    def test_cmd_list_json_format(
        self, mock_read_stream, mock_db_client, test_config, sample_messages
    ):
        """Test list command with JSON format."""
        # Mock database query results
        now = datetime.now(UTC)
        fetchall_result = [("agent:v0-thread-123", now)]
        self._setup_db_mock(mock_db_client, fetchall_result)

        # Mock read_stream to return sample events
        mock_read_stream.return_value = sample_messages

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["list", "--format", "json"])

        # Capture stdout
        with patch("sys.stdout", new=StringIO()) as fake_out:
            result = cmd_list(args, test_config)

            # Verify
            assert result == 0
            output = fake_out.getvalue()
            parsed = json.loads(output)
            assert len(parsed) == 1
            assert parsed[0]["thread_id"] == "thread-123"

    @patch("messagedb_agent.cli.MessageDBClient")
    def test_cmd_list_no_sessions(self, mock_db_client, test_config):
        """Test list command with no sessions."""
        # Mock empty results
        self._setup_db_mock(mock_db_client, [])

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["list"])

        # Execute command
        result = cmd_list(args, test_config)

        # Verify
        assert result == 0

    @patch("messagedb_agent.cli.MessageDBClient")
    def test_cmd_list_with_limit(self, mock_db_client, test_config):
        """Test list command with custom limit."""
        # Mock empty results
        mock_cursor = self._setup_db_mock(mock_db_client, [])

        # Create args namespace
        parser = create_parser()
        args = parser.parse_args(["list", "--limit", "20"])

        # Execute command
        result = cmd_list(args, test_config)

        # Verify
        assert result == 0
        # Check that SQL query used correct limit
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1][1] == 20


class TestMain:
    """Tests for main entry point."""

    def test_main_no_command(self):
        """Test main with no command."""
        result = main([])
        assert result == 1

    @patch("messagedb_agent.cli.load_config")
    def test_main_config_error(self, mock_load_config):
        """Test main with configuration error."""
        mock_load_config.side_effect = ValueError("Missing DB_USER")

        result = main(["list"])
        assert result == 1

    @patch("messagedb_agent.cli.load_config")
    @patch("messagedb_agent.cli.cmd_start")
    def test_main_start_command(self, mock_cmd_start, mock_load_config, test_config):
        """Test main dispatching to start command."""
        mock_load_config.return_value = test_config
        mock_cmd_start.return_value = 0

        result = main(["start", "Hello"])
        assert result == 0
        mock_cmd_start.assert_called_once()

    @patch("messagedb_agent.cli.load_config")
    @patch("messagedb_agent.cli.cmd_continue")
    def test_main_continue_command(self, mock_cmd_continue, mock_load_config, test_config):
        """Test main dispatching to continue command."""
        mock_load_config.return_value = test_config
        mock_cmd_continue.return_value = 0

        result = main(["continue", "thread-123"])
        assert result == 0
        mock_cmd_continue.assert_called_once()

    @patch("messagedb_agent.cli.load_config")
    @patch("messagedb_agent.cli.cmd_message")
    def test_main_message_command(self, mock_cmd_message, mock_load_config, test_config):
        """Test main dispatching to message command."""
        mock_load_config.return_value = test_config
        mock_cmd_message.return_value = 0

        result = main(["message", "thread-123", "Hello again!"])
        assert result == 0
        mock_cmd_message.assert_called_once()

    @patch("messagedb_agent.cli.load_config")
    @patch("messagedb_agent.cli.cmd_show")
    def test_main_show_command(self, mock_cmd_show, mock_load_config, test_config):
        """Test main dispatching to show command."""
        mock_load_config.return_value = test_config
        mock_cmd_show.return_value = 0

        result = main(["show", "thread-123"])
        assert result == 0
        mock_cmd_show.assert_called_once()

    @patch("messagedb_agent.cli.load_config")
    @patch("messagedb_agent.cli.cmd_list")
    def test_main_list_command(self, mock_cmd_list, mock_load_config, test_config):
        """Test main dispatching to list command."""
        mock_load_config.return_value = test_config
        mock_cmd_list.return_value = 0

        result = main(["list"])
        assert result == 0
        mock_cmd_list.assert_called_once()

    @patch("messagedb_agent.cli.load_config")
    @patch("messagedb_agent.cli.cmd_list")
    def test_main_custom_config_file(self, mock_cmd_list, mock_load_config, test_config):
        """Test main with custom config file."""
        mock_load_config.return_value = test_config
        mock_cmd_list.return_value = 0

        main(["--config", ".env.test", "list"])
        # Verify load_config was called with custom path
        mock_load_config.assert_called_once_with(".env.test")

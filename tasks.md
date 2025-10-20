# Implementation Tasks

This document tracks the implementation tasks for the Event-Sourced Agent System based on the specifications in `spec.md` and technology decisions in `basic-python.md`.

## Phase 1: Project Foundation

### 1. Project Setup and Structure
- [x] **Task 1.1: Initialize Python project with uv**
  - Create `pyproject.toml` with project metadata
  - Configure Python version (3.11+)
  - Set up project structure: `src/messagedb_agent/` as main package
  - Configure build system and dependencies in pyproject.toml

- [x] **Task 1.2: Define project structure**
  - Create directory structure:
    - `src/messagedb_agent/` - main package
    - `src/messagedb_agent/events/` - event definitions
    - `src/messagedb_agent/projections/` - projection functions
    - `src/messagedb_agent/tools/` - tool implementations
    - `src/messagedb_agent/store/` - event store integration
    - `src/messagedb_agent/llm/` - LLM integration
    - `src/messagedb_agent/engine/` - processing engine
    - `tests/` - test files mirroring src structure

- [x] **Task 1.3: Add core dependencies**
  - Add psycopg2-binary or psycopg3 for PostgreSQL/Message DB connection
  - Add google-cloud-aiplatform for Vertex AI integration
  - Add structlog for structured logging
  - Add opentelemetry-api and opentelemetry-sdk for observability
  - Add pytest for testing
  - Add python-dotenv for environment variable management

## Phase 2: Event Store Integration

### 2. Message DB Connection and Operations

[Message DB](https://github.com/message-db/message-db) documentation:
- [Server Functions](https://docs.eventide-project.org/user-guide/message-db/server-functions.html)

- [x] **Task 2.1: Create Message DB client**
  - Implement `src/messagedb_agent/store/client.py`
  - Create MessageDBClient class with connection pooling
  - Configuration from environment variables (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
  - Implement context manager for connection lifecycle
  - Add connection health check method
  - Added psycopg-pool dependency for connection pooling

- [x] **Task 2.2: Implement write_event function**
  - Create function to write events to Message DB using `write_message` stored procedure
  - Parameters: stream_name, event_type, data (dict), metadata (optional), expected_version (optional for OCC)
  - Serialize data to JSON
  - Handle optimistic concurrency conflicts
  - Return position of written event
  - Created OptimisticConcurrencyError exception class
  - Added comprehensive error handling and structured logging

- [x] **Task 2.3: Implement read_stream function**
  - Created `Event` dataclass in `src/messagedb_agent/store/operations.py` to represent events
  - Implemented `read_stream` function using `message_store.get_stream_messages()`
  - Parameters: stream_name, position (optional, default 0), batch_size (optional, default 1000)
  - Deserializes JSON data and metadata from JSONB columns
  - Returns list of Event objects with: id, type, data, metadata, position, global_position, time, stream_name
  - Added comprehensive test suite in `tests/store/test_operations.py` (14 tests)
  - Exported Event class and read_stream function from store module
  - NOTE: Must use `message_store.get_stream_messages()` with schema prefix - functions are in message_store schema

- [x] **Task 2.4: Implement stream utilities**
  - Created `src/messagedb_agent/store/stream.py` with three core functions:
    - `generate_thread_id()`: Generates unique UUID4 thread identifiers
    - `build_stream_name(category, version, thread_id)`: Builds stream names in format `category:version-thread_id`
    - `parse_stream_name(stream_name)`: Parses stream names back into (category, version, thread_id) components
  - Comprehensive input validation with clear error messages
  - Prevents invalid characters: colon in category, dash in version
  - Added comprehensive test suite in `tests/store/test_stream.py` (38 tests covering all functions)
  - Tests include: UUID validation, format validation, round-trip consistency, error cases, edge cases
  - Exported all three functions from store module
  - All tests passing (52 total tests in project)

## Phase 3: Event Schema and Types

### 3. Event Type Definitions
- [x] **Task 3.1: Define base event structure**
  - Create `src/messagedb_agent/events/base.py`
  - Define BaseEvent dataclass/TypedDict with: id, type, data, metadata, position, time
  - Define EventData base class for type-safe event payloads
  - Created BaseEvent frozen dataclass with all required fields: id, type, data, metadata, position, global_position, time, stream_name
  - Created EventData base class for type-safe event payloads
  - Added validation in __post_init__ for event type and positions

- [x] **Task 3.2: Define User event types**
  - Create `src/messagedb_agent/events/user.py`
  - Define UserMessageAdded event with payload: message (str), timestamp
  - Define SessionTerminationRequested event
  - Created UserMessageData with message and timestamp fields
  - Created SessionTerminationRequestedData with reason field
  - Added event type constants: USER_MESSAGE_ADDED, SESSION_TERMINATION_REQUESTED
  - Comprehensive validation for message content and ISO 8601 timestamps

- [x] **Task 3.3: Define Agent event types**
  - Create `src/messagedb_agent/events/agent.py`
  - Define LLMCallRequested event with payload: projected_context
  - Define LLMResponseReceived event with payload: response_text, tool_calls (list), model_name, token_usage
  - Define LLMCallFailed event with payload: error_message, retry_count
  - Created ToolCall dataclass with id, name, arguments
  - Created LLMResponseReceivedData with response_text, tool_calls, model_name, token_usage
  - Created LLMCallFailedData with error_message, retry_count
  - Added event type constants: LLM_RESPONSE_RECEIVED, LLM_CALL_FAILED
  - Note: LLMCallRequested not implemented (not required for basic flow)
  - Validation ensures either response_text or tool_calls is present

- [x] **Task 3.4: Define Tool event types**
  - Create `src/messagedb_agent/events/tool.py`
  - Define ToolExecutionRequested event with payload: tool_name, arguments (dict)
  - Define ToolExecutionCompleted event with payload: tool_name, result, execution_time_ms
  - Define ToolExecutionFailed event with payload: tool_name, error_message, retry_count
  - Created ToolExecutionRequestedData with tool_name and arguments (dict[str, Any])
  - Created ToolExecutionCompletedData with tool_name, result (Any), and execution_time_ms
  - Created ToolExecutionFailedData with tool_name, error_message, and retry_count
  - Added event type constants: TOOL_EXECUTION_REQUESTED, TOOL_EXECUTION_COMPLETED, TOOL_EXECUTION_FAILED
  - Comprehensive validation for all fields (non-empty names, non-negative times/retries)

- [x] **Task 3.5: Define System event types**
  - Create `src/messagedb_agent/events/system.py`
  - Define SessionStarted event with payload: thread_id, initial_context (optional)
  - Define SessionCompleted event with payload: completion_reason (success/failure/timeout)
  - Define ErrorOccurred event with payload: error_type, error_message, stack_trace (optional)
  - Created SessionStartedData with thread_id and optional initial_context
  - Created SessionCompletedData with completion_reason
  - Added event type constants: SESSION_STARTED, SESSION_COMPLETED
  - Note: ErrorOccurred not implemented (not required for basic flow)
  - Validation for thread_id and completion_reason

## Phase 4: Projection Framework

### 4. Projection Functions
- [x] **Task 4.1: Create projection base infrastructure**
  - Create `src/messagedb_agent/projections/base.py`
  - Define ProjectionFunction type: `Callable[[List[BaseEvent]], T]`
  - Create ProjectionResult generic type for typed projection outputs
  - Document projection purity requirements in docstrings
  - Created ProjectionFunction[T] type alias for type-safe projections
  - Created ProjectionResult[T] dataclass with metadata (value, event_count, last_position)
  - Implemented project_with_metadata() helper and compose_projections() utility
  - Added 20 comprehensive tests with 100% coverage

- [x] **Task 4.2: Implement LLM Context projection**
  - Create `src/messagedb_agent/projections/llm_context.py`
  - Implement `project_to_llm_context(events) -> List[Message]` function
  - Convert UserMessageAdded → user message
  - Convert LLMResponseReceived → assistant message (text + tool_calls)
  - Convert ToolExecutionCompleted → tool result message
  - Skip system/metadata events in context
  - Return messages in chronological order suitable for Vertex AI API
  - Created projection that converts events to Message objects for LLM calls
  - Added helper functions: get_last_user_message(), count_conversation_turns()
  - Handles malformed event data gracefully with proper error handling
  - Added 13 comprehensive tests with 88% code coverage
  - Proper type annotations and cast usage for basedpyright compliance

- [x] **Task 4.3: Implement Session State projection**
  - Create `src/messagedb_agent/projections/session_state.py`
  - Define SessionState dataclass: thread_id, status (active/completed/failed/terminated), message_count, tool_call_count, llm_call_count, error_count, last_activity_time, session_start_time, session_end_time
  - Implement `project_to_session_state(events) -> SessionState`
  - Aggregate statistics from events
  - Track current session status based on event types
  - Created SessionStatus enum with 4 states
  - Added helper functions: is_session_active(), get_session_duration()
  - Thread ID extraction from stream name
  - 33 comprehensive tests with 95% code coverage

- [x] **Task 4.4: Implement Tool Arguments projection**
  - Create `src/messagedb_agent/projections/tool_args.py`
  - Implement `project_to_tool_arguments(events) -> list[dict[str, Any]]`
  - Extract tool call arguments from most recent LLMResponseReceived event
  - Return list of tool call dicts (id, name, arguments)
  - Handle case where no tool calls present
  - Handle both dict and ToolCall dataclass formats
  - Helper functions: get_tool_call_by_name(), get_all_tool_names(), has_pending_tool_calls(), count_tool_calls()
  - 28 comprehensive tests with 100% code coverage

- [x] **Task 4.5: Implement Next Step projection**
  - Create `src/messagedb_agent/projections/next_step.py`
  - Define StepType enum: LLM_CALL, TOOL_EXECUTION, TERMINATION
  - Implement `project_to_next_step(events) -> Tuple[StepType, Any]`
  - Logic: last event determines next step (as per spec 3.3)
    - UserMessageAdded → LLM_CALL
    - LLMResponseReceived (with tool_calls) → TOOL_EXECUTION
    - LLMResponseReceived (no tool_calls) → LLM_CALL (to allow agent to respond to user)
    - ToolExecutionCompleted → LLM_CALL (to process tool results)
    - SessionTerminationRequested → TERMINATION
    - SessionCompleted → TERMINATION
  - Created StepType enum with three states
  - Implemented Last Event Pattern decision logic
  - Added helper functions: should_terminate(), get_pending_tool_calls(), count_steps_taken()
  - 24 comprehensive tests with 93% code coverage
  - Handles unknown event types gracefully (defaults to LLM_CALL)

## Phase 5: LLM Integration

### 5. Vertex AI Integration
- [x] **Task 5.1: Setup Vertex AI client**
  - Create `src/messagedb_agent/llm/client.py`
  - Initialize Vertex AI using google.auth.default() for ADC
  - Configure from environment variables: GCP_PROJECT, GCP_LOCATION, MODEL_NAME (eg gemini-2.5-pro or claude-sonnet-4-5@20250929)
  - Create wrapper for unified interface regardless of model choice
  - Created VertexAIClient class with ADC authentication support
  - Supports both Gemini and Claude models via Vertex AI
  - Added comprehensive docstrings and type hints
  - All tests passing, linting clean

- [x] **Task 5.2: Implement message formatting**
  - Create `src/messagedb_agent/llm/format.py`
  - Implement function to convert projection messages to Vertex AI format
  - Handle system prompts
  - Handle user/assistant message formatting
  - Handle function/tool call formatting
  - Handle tool result formatting
  - Created Message dataclass for internal representation
  - Implemented format_messages() to convert to Vertex AI Content/Part objects
  - Added convenience functions: create_user_message(), create_model_message(), create_function_response_message()
  - Comprehensive validation and error handling
  - All tests passing, linting clean

- [x] **Task 5.3: Implement LLM call function**
  - Create `src/messagedb_agent/llm/call.py`
  - Implement `call_llm(messages, tools, model_name) -> LLMResponse`
  - LLMResponse dataclass: text, tool_calls (List[ToolCall]), model_name, token_usage (dict)
  - ToolCall dataclass: id, name, arguments (dict)
  - Handle Vertex AI API errors with proper error types
  - Extract text and tool calls from response
  - Track token usage from response metadata
  - Created ToolCall and LLMResponse dataclasses with validation
  - Implemented call_llm() with error handling and response parsing
  - Added LLM error hierarchy: LLMError, LLMAPIError, LLMResponseError
  - Created create_function_declaration() helper function
  - Extracts token usage from Vertex AI usage_metadata
  - Fixed Gemini function calling to handle ValueError when accessing text on function call responses
  - All tests passing, linting clean

- [x] **Task 5.3.1: Add Claude model support via AnthropicVertex SDK**
  - Added `anthropic[vertex]>=0.42.0` dependency to pyproject.toml
  - Created unified `BaseLLMClient` abstract base class for both Gemini and Claude
  - Implemented `ClaudeClient` using `AnthropicVertex.messages.create()` API
  - Refactored existing Gemini code into `GeminiClient` implementing same interface
  - Created `create_llm_client()` factory that auto-detects model type from name
  - Unified data types: `Message`, `ToolCall`, `ToolDeclaration`, `LLMResponse`
  - Both clients implement same `client.call(messages, tools, system_prompt)` interface
  - Removed legacy Gemini-only API (call.py, client.py, format.py) - 1,049 lines deleted
  - Created comprehensive integration tests for both models (9 tests, all passing)
  - Verified tool calling works with both Gemini and Claude
  - Verified multi-turn conversations work with both models
  - Code coverage: 80% for ClaudeClient, 78% for GeminiClient
  - All 169 unit tests + 9 integration tests passing

- [x] **Task 5.4: Define system prompt**
  - Created `src/messagedb_agent/llm/prompts.py` with comprehensive prompt utilities
  - Defined `DEFAULT_SYSTEM_PROMPT` for event-sourced agent behavior
  - Defined `MINIMAL_SYSTEM_PROMPT` for simple use cases
  - Defined `TOOL_FOCUSED_SYSTEM_PROMPT` emphasizing tool usage
  - Created `create_system_prompt()` function for customization
  - Created `get_prompt_for_task()` function for task-specific prompts
  - Documented comprehensive prompt engineering guidelines in module
  - Exported all prompts and utilities from llm module
  - Added 20 comprehensive tests (100% coverage of prompts.py)
  - All 189 unit tests passing

## Phase 6: Tool Framework

### 6. Tool Definition and Execution
- [x] **Task 6.1: Create tool registration system**
  - Created `src/messagedb_agent/tools/registry.py`
  - Defined Tool frozen dataclass: name, description, parameters_schema (dict), function (Callable)
  - Created ToolRegistry class with register/get/has/unregister/clear/list_names/list_tools methods
  - Implemented @tool decorator for easy registration with auto-schema generation
  - Implemented register_tool() decorator factory for automatic registration to registry
  - Auto-generates JSON Schema from Python type hints (int→integer, str→string, float→number, bool→boolean, list→array, dict→object)
  - Added get_tool_metadata() to extract metadata from decorated functions
  - Custom error hierarchy: ToolError, ToolNotFoundError, ToolRegistrationError
  - 34 comprehensive tests with 98% code coverage
  - All tests passing, linting/formatting/type checking clean

- [x] **Task 6.2: Implement tool execution**
  - Created `src/messagedb_agent/tools/executor.py`
  - Created ToolExecutionResult dataclass with success, result, error, execution_time_ms, tool_name
  - Implemented execute_tool(tool_name, arguments, registry) -> ToolExecutionResult
  - Looks up tool in registry and executes with provided arguments
  - Catches all exceptions and wraps in result object (never raises)
  - Tracks execution time using time.perf_counter() in milliseconds
  - Formats errors as "ExceptionType: message"
  - Added execute_tool_safe() convenience wrapper returning (result, error) tuple
  - Added batch_execute_tools() for executing multiple tool calls in sequence
  - Custom error hierarchy: ToolExecutionError, ToolExecutionTimeoutError
  - 37 comprehensive tests with 100% code coverage
  - All tests passing, linting/formatting/type checking clean

- [x] **Task 6.3: Create example tools**
  - Created `src/messagedb_agent/tools/builtin.py`
  - Implemented get_current_time() - returns current UTC time in ISO 8601 format
  - Implemented calculate() - safe math evaluator using AST (NO eval())
    - Supports: +, -, *, /, //, %, **, unary +/-
    - Rejects: function calls, variables, unsafe operations
    - Comprehensive error handling (division by zero, invalid syntax, etc.)
  - Implemented echo() - simple echo for testing
  - Implemented get_builtin_tools() - returns dict of all builtin tools
  - Implemented register_builtin_tools() - registers all tools to registry
  - 54 comprehensive tests with 95% code coverage
  - All tests passing, linting/formatting/type checking clean

- [x] **Task 6.4: Convert tools to LLM function declarations**
  - Created `src/messagedb_agent/tools/schema.py` with 7 utility functions
  - Implemented tool_to_function_declaration() - converts single Tool to ToolDeclaration
  - Implemented tools_to_function_declarations() - converts list of Tools
  - Implemented registry_to_function_declarations() - converts entire ToolRegistry
  - Implemented get_tool_names_from_declarations() - extracts tool names
  - Implemented validate_function_declaration() - validates ToolDeclaration structure
  - Implemented filter_tools_by_name() - filters declarations by name
  - Implemented merge_schema_properties() - merges additional schema properties
  - Converts to ToolDeclaration format (unified for both Gemini and Claude)
  - Preserves parameter schemas exactly, including required vs optional parameters
  - Created comprehensive test suite in tests/tools/test_schema.py (42 tests, 94% coverage)
  - All tests passing, linting/formatting/type checking clean

## Phase 7: Processing Engine

### 7. Main Processing Loop
- [x] **Task 7.1: Implement processing loop** (COMPLETE)
  - Created `src/messagedb_agent/engine/loop.py` with main processing loop
  - Implemented `process_thread(thread_id, stream_name, store_client, llm_client, tool_registry, max_iterations=100)`
  - Main loop structure:
    1. Read all events for thread from stream
    2. Convert Message objects to BaseEvent objects
    3. Project to next_step to determine action
    4. If TERMINATION, break and return final state
    5. If LLM_CALL, raise NotImplementedError (Task 7.2)
    6. If TOOL_EXECUTION, raise NotImplementedError (Task 7.3)
    7. Repeat until termination or max_iterations
  - Returns final SessionState projection
  - Created `ProcessingError` and `MaxIterationsExceeded` exception classes
  - Created `_message_to_event()` helper to convert Message DB Messages to BaseEvents
  - Tracks whether termination was natural (via event) or hit max_iterations limit
  - Exported process_thread and exceptions from engine module
  - Created comprehensive test suite in `tests/engine/test_loop.py`:
    - 11 tests covering conversion, termination, error handling, iteration limits
    - Tests verify NotImplementedError for LLM/Tool steps (will be implemented in 7.2/7.3)
    - 96% code coverage on loop.py (only untested path is max_iterations exception)
  - All 485 unit tests passing, linting/formatting/type checking clean

- [x] **Task 7.2: Implement LLM step execution** (COMPLETE)
  - Created `src/messagedb_agent/engine/steps/llm.py` with LLM step execution
  - Implemented `execute_llm_step(events, llm_client, tool_registry, stream_name, store_client, system_prompt, max_retries)`
  - Projects events to LLM context using `project_to_llm_context()`
  - Gets tool declarations from registry using `registry_to_function_declarations()`
  - Calls LLM with context, tools, and system prompt (defaults to DEFAULT_SYSTEM_PROMPT)
  - Success path: writes LLMResponseReceived event with response text, tool calls, model name, and token usage
  - Failure path: implements retry logic (max_retries=2 default), writes LLMCallFailed event after exhausting retries
  - Returns True on success, False on failure after retries
  - Created `LLMStepError` exception for critical failures (event write failures)
  - Only passes tools to LLM if registry has tools (passes None for empty registry)
  - Supports custom system prompts
  - Tracks retry count in event metadata
  - Integrated into main processing loop (loop.py now calls execute_llm_step)
  - Updated loop tests to reflect LLM step implementation
  - Created comprehensive test suite in `tests/engine/steps/test_llm.py`:
    - 11 tests covering success/failure, retries, tool passing, custom prompts, event writing
    - 96% code coverage on llm.py
  - All 496 unit tests passing, linting/formatting/type checking clean

- [x] **Task 7.3: Implement Tool step execution** (COMPLETE)
  - Created `src/messagedb_agent/engine/steps/tool.py` with `execute_tool_step()` function
  - Projects events to get tool calls using `project_to_tool_arguments()`
  - For each tool call:
    - Writes ToolExecutionRequested event
    - Executes tool using `execute_tool(tool_name, arguments, tool_registry)`
    - Writes ToolExecutionCompleted (success) or ToolExecutionFailed (failure) event
  - Returns True if all tools succeeded, False if any failed
  - Created `ToolStepError` exception for critical failures (event write failures)
  - Updated main processing loop (loop.py) to call execute_tool_step
  - Updated loop tests to verify tool step execution works
  - Created comprehensive test suite in `tests/engine/steps/test_tool.py`:
    - 12 tests covering success/failure, multiple tools, error handling, event writing
    - 100% code coverage on tool.py
  - All 508 unit tests passing, linting/formatting/type checking clean

- [x] **Task 7.4: Implement session initialization** (COMPLETE)
  - Created `src/messagedb_agent/engine/session.py` with `start_session()` function
  - Generates unique thread_id using `generate_thread_id()`
  - Builds stream_name using `build_stream_name(category, version, thread_id)`
  - Writes SessionStarted event with thread_id to the stream
  - Writes UserMessageAdded event with initial message and ISO 8601 timestamp
  - Returns thread_id for subsequent processing
  - Created `SessionError` exception for critical failures (event write errors)
  - Supports custom category and version (defaults: "agent", "v0")
  - Validates initial_message is not empty or whitespace-only
  - Exported start_session and SessionError from engine module
  - Created comprehensive test suite in `tests/engine/test_session.py`:
    - 16 tests covering success, validation, error handling, event structure
    - 100% code coverage on session.py
  - All 524 unit tests passing, 84% overall coverage

- [x] **Task 7.5: Implement session termination** (COMPLETE)
  - Added `terminate_session(thread_id, reason, store_client, category, version)` to session.py
  - Writes SessionCompleted event with termination reason
  - Handles graceful shutdown by writing final event to stream
  - Validates thread_id and reason are not empty or whitespace-only
  - Supports custom category and version (defaults: "agent", "v0")
  - Returns position of SessionCompleted event in stream
  - Exported terminate_session from engine module
  - Created comprehensive test suite in `tests/engine/test_session.py`:
    - Added 14 tests for terminate_session (30 total session tests)
    - Tests cover: success, validation, error handling, various reasons
    - Tests event structure, position tracking, special cases
    - 100% code coverage on session.py
  - All 538 unit tests passing, 84% overall coverage

## Phase 8: Observability

### 8. Logging and Tracing
- [ ] **Task 8.1: Setup structured logging**
  - Create `src/messagedb_agent/observability/logging.py`
  - Configure structlog with JSON output
  - Add processors for: timestamp, log level, logger name, stack info
  - Create logger factory function
  - Add context binding helpers for thread_id, event_type

- [ ] **Task 8.2: Setup OpenTelemetry**
  - Create `src/messagedb_agent/observability/tracing.py`
  - Initialize OpenTelemetry SDK
  - Configure tracer provider
  - Set up console exporter for basic impl (can swap to OTLP later)
  - Create tracer factory function

- [ ] **Task 8.3: Add instrumentation to processing loop**
  - Add span creation for: process_thread, execute_llm_step, execute_tool_step
  - Add span attributes: thread_id, event_count, step_type
  - Record exceptions in spans

- [ ] **Task 8.4: Add instrumentation to LLM calls**
  - Wrap LLM calls in spans
  - Add attributes: model_name, token_count, latency
  - Record errors

- [ ] **Task 8.5: Add instrumentation to tool executions**
  - Wrap tool executions in spans
  - Add attributes: tool_name, execution_time_ms
  - Record errors

## Phase 9: Configuration and CLI

### 9. Configuration Management
- [ ] **Task 9.1: Create configuration module**
  - Create `src/messagedb_agent/config.py`
  - Define Config dataclass with all configuration fields
  - Load from environment variables using python-dotenv
  - Provide sensible defaults
  - Validate required fields
  - Config fields:
    - Message DB: host, port, database, user, password
    - Vertex AI: project, location, model_name
    - Processing: max_iterations, enable_tracing
    - Logging: log_level, log_format

- [ ] **Task 9.2: Create CLI interface**
  - Create `src/messagedb_agent/cli.py`
  - Use argparse or click for CLI
  - Commands:
    - `start <message>` - start new session with initial message
    - `continue <thread_id>` - continue existing session
    - `show <thread_id>` - display session events
    - `list` - list recent sessions
  - Add --config flag for custom config file

- [ ] **Task 9.3: Create main entry point**
  - Create `src/messagedb_agent/__main__.py`
  - Initialize configuration
  - Initialize logging and tracing
  - Initialize clients (store, LLM)
  - Initialize tool registry
  - Dispatch to CLI commands

## Phase 10: Testing

### 10. Test Infrastructure
- [ ] **Task 10.1: Setup pytest infrastructure**
  - Create `tests/conftest.py`
  - Add pytest fixtures for:
    - Mock MessageDB client
    - Mock LLM client
    - Sample events
    - Test thread_id
    - Tool registry with test tools

- [x] **Task 10.2: Setup Message DB test container** (Complete)
  - Created `docker-compose.test.yml` using `ethangarofolo/message-db:1.3.1` image
  - Configured PostgreSQL with Message DB v1.3.0 extension installed
  - Added pytest-docker dependency and fixtures in `tests/conftest.py`:
    - `messagedb_service`: Starts container automatically and waits for full initialization
    - `messagedb_config`: Provides test database configuration (postgres user, port 5433)
    - `messagedb_client`: Provides connected MessageDB client instance
  - Updated `src/messagedb_agent/store/client.py` to set `search_path=message_store,public` in connection string
    - This allows Message DB internal functions like `acquire_lock()` and `is_category()` to be found
  - Updated `src/messagedb_agent/store/operations.py` to commit transactions after writes and reads
    - Added explicit `conn.commit()` calls to persist changes and release locks
  - All Message DB functions are in the `message_store` schema (e.g., `message_store.write_message()`)

  **Usage:**
  ```bash
  # Simply run tests - Docker container starts automatically via pytest-docker
  uv run pytest

  # Run with verbose output
  uv run pytest -v

  # Run specific test file
  uv run pytest tests/store/test_operations.py -v
  ```

  **Database Connection Details:**
  - Host: localhost
  - Port: 5433 (to avoid conflicts with local postgres on 5432)
  - Database: message_store
  - User: postgres
  - Password: message_store_password
  - Search path: message_store,public (configured in connection string)
  - All Message DB functions are in `message_store` schema (e.g., `message_store.write_message()`)

  **Implementation Notes:**
  - The `ethangarofolo/message-db:1.3.1` image provides clean, reliable initialization
  - Health check waits for all Message DB functions to be installed before proceeding
  - Container is automatically cleaned up after test session completes
  - Fresh database for each test run ensures test isolation

- [ ] **Task 10.3: Write projection tests**
  - Create `tests/test_projections.py`
  - Test each projection function with sample event sequences
  - Test edge cases: empty events, missing event types
  - Verify projection purity (same input → same output)

- [ ] **Task 10.4: Write event store tests**
  - Create `tests/test_store.py`
  - Test write_event function
  - Test read_stream function
  - Test optimistic concurrency control
  - Test against real Message DB container

- [ ] **Task 10.5: Write tool framework tests**
  - Create `tests/test_tools.py`
  - Test tool registration
  - Test tool execution
  - Test function declaration generation
  - Test error handling

- [ ] **Task 10.6: Write integration tests**
  - Create `tests/test_integration.py`
  - Test complete session lifecycle: start → LLM call → tool execution → completion
  - Test against real Message DB
  - Mock LLM API calls
  - Verify event sequence correctness

- [ ] **Task 10.7: Write engine tests**
  - Create `tests/test_engine.py`
  - Test step selection logic
  - Test loop termination conditions
  - Test error recovery
  - Test max_iterations limit

## Phase 11: Documentation and Examples

### 11. Documentation
- [ ] **Task 11.1: Write README.md**
  - Project overview and architecture
  - Installation instructions using uv
  - Quick start guide
  - Configuration documentation
  - Link to spec.md and implementation-decisions.md

- [ ] **Task 11.2: Write API documentation**
  - Document all public functions and classes
  - Add docstrings following Google or NumPy style
  - Include type hints everywhere
  - Add usage examples in docstrings

- [ ] **Task 11.3: Create example script**
  - Create `examples/simple_agent.py`
  - Demonstrate basic usage:
    - Initialize system
    - Start session with user message
    - Process until completion
    - Display results
  - Add comments explaining each step

- [ ] **Task 11.4: Create custom tool example**
  - Create `examples/custom_tool.py`
  - Show how to define and register custom tool
  - Show how to use projection customization (when implemented)
  - Demonstrate tool in agent session

- [ ] **Task 11.5: Create troubleshooting guide**
  - Common issues and solutions
  - How to inspect event streams
  - How to debug projection functions
  - How to replay sessions

## Phase 12: Polish and Deployment Prep

### 12. Final Steps
- [ ] **Task 12.1: Add .env.example file**
  - Document all environment variables
  - Provide example values
  - Add comments explaining each variable

- [ ] **Task 12.2: Add .gitignore**
  - Ignore __pycache__, .pyc files
  - Ignore .env (but not .env.example)
  - Ignore IDE-specific files
  - Ignore test coverage reports

- [ ] **Task 12.3: Add pre-commit hooks**
  - Format code with black
  - Lint with ruff or flake8
  - Type check with mypy
  - Run tests before commit

- [ ] **Task 12.4: Create development setup script**
  - Create `scripts/setup_dev.sh`
  - Install uv if not present
  - Create virtual environment
  - Install dependencies
  - Setup Message DB container
  - Verify setup

- [ ] **Task 12.5: Performance testing**
  - Create `tests/test_performance.py`
  - Benchmark projection performance with large event counts
  - Benchmark event write/read throughput
  - Document performance characteristics

- [ ] **Task 12.6: Security audit**
  - Review all external inputs for injection risks
  - Ensure secrets not logged
  - Verify SQL injection protection in Message DB client
  - Review tool execution security (eval usage, etc.)

## Implementation Order

### Basic End-to-End Flow (Minimum Viable Implementation)

**Goal**: Get a working flow of user message → LLM call → response, all event-sourced through Message DB, without tool support.

**Flow**:
```
1. User provides initial message
2. start_session() → writes SessionStarted + UserMessageAdded events
3. process_thread() loop:
   - read_stream() → get all events
   - project_to_next_step() → determine: LLM_CALL or TERMINATION
   - if LLM_CALL:
     - project_to_llm_context() → convert events to messages
     - call_llm() → get response from Vertex AI
     - write LLMResponseReceived event (or LLMCallFailed)
   - if TERMINATION:
     - write SessionCompleted event
     - break
4. Return final response to user
```

**Recommended Implementation Order** (~10-15 hours):

1. **Event Definitions** (Tasks 3.1, 3.2, 3.3 partial, 3.5 partial)
   - Task 3.1: Base event structure
   - Task 3.2: User events (UserMessageAdded, SessionTerminationRequested)
   - Task 3.3 (partial): Agent events (LLMResponseReceived, LLMCallFailed) - skip LLMCallRequested for now
   - Task 3.5 (partial): System events (SessionStarted, SessionCompleted) - skip ErrorOccurred for now

2. **Configuration** (Task 9.1)
   - Task 9.1: Configuration module for Message DB + Vertex AI settings

3. **LLM Integration** (Tasks 5.1-5.4)
   - Task 5.1: Setup Vertex AI client
   - Task 5.2: Message formatting for Vertex AI
   - Task 5.3: LLM call function (without tools parameter for now)
   - Task 5.4: System prompt definition

4. **Projections** (Tasks 4.1, 4.2, 4.5)
   - Task 4.1: Projection base infrastructure
   - Task 4.2: LLM Context projection (UserMessageAdded → user message, LLMResponseReceived → assistant message)
   - Task 4.5: Next Step projection (UserMessageAdded → LLM_CALL, LLMResponseReceived → TERMINATION for now, SessionCompleted → TERMINATION)

5. **Processing Engine** (Tasks 7.4, 7.2 partial, 7.5, 7.1 simplified)
   - Task 7.4: Session initialization
   - Task 7.2 (simplified): LLM step execution (without tool registry parameter)
   - Task 7.5: Session termination
   - Task 7.1 (simplified): Processing loop (without tool execution step)

6. **Simple Test Script** (Task 9.3 simplified)
   - Create minimal script to test end-to-end flow
   - Skip full CLI for now, just a simple Python script

**What to Skip for Basic Flow**:
- Task 3.4: Tool event types (entire task)
- Task 4.3: Session State projection (nice-to-have)
- Task 4.4: Tool Arguments projection (entire task)
- Task 6.1-6.4: All tool framework tasks
- Task 7.3: Tool step execution
- Task 9.2: Full CLI interface
- Task 8.1-8.5: Observability (can add later)

**After Basic Flow Works, Add Tools**:
- Phase 6: Tool Framework (Tasks 6.1-6.4)
- Task 3.4: Tool event types
- Task 4.4: Tool Arguments projection
- Task 7.3: Tool step execution
- Update Task 4.5: Next Step projection to handle tool execution
- Update Task 7.2: LLM step to pass tools to LLM

### Full Implementation Order

Recommended implementation order for complete system:

1. **Phase 1: Project Foundation** (Tasks 1.1-1.3) ✅ COMPLETE
2. **Phase 2: Event Store Integration** (Tasks 2.1-2.4) ✅ COMPLETE
3. **Basic End-to-End Flow** (see above) ⬅ **START HERE**
4. **Phase 6: Tool Framework** (Tasks 6.1-6.4)
5. **Phase 8: Observability** (Tasks 8.1-8.5)
6. **Phase 9: Full CLI** (Task 9.2, complete 9.3)
7. **Phase 10: Testing** (Tasks 10.1, 10.3-10.7) - complete remaining tests
8. **Phase 11: Documentation** (Tasks 11.1-11.5)
9. **Phase 12: Polish** (Tasks 12.1-12.6)

## Progress Tracking

- Total Tasks: 78
- Completed: 32 (Tasks 1.1-1.3, 2.1-2.4, 3.1-3.5, 4.1-4.5, 5.1-5.4, 6.1-6.4, 7.1-7.5, 10.2)
- In Progress: 0
- Remaining: 46
- Completion: 41.0%

Last Updated: 2025-10-19

**Recent Completions:**
- Task 7.5: Implement session termination (COMPLETE - Phase 7 COMPLETE! 🎉)
  - Added terminate_session() function for graceful session shutdown
  - Writes SessionCompleted event with termination reason
  - Validates inputs and handles errors gracefully
  - 14 comprehensive tests with 100% coverage on session.py
  - All 538 unit tests passing, 84% overall coverage
  - **Phase 7 (Processing Engine) is now complete!** All 5 tasks done.
- Task 7.4: Implement session initialization (COMPLETE)
  - Created start_session() function that initializes new agent sessions
  - Generates thread_id, builds stream_name, writes SessionStarted and UserMessageAdded events
  - Returns thread_id for subsequent processing
  - Comprehensive validation and error handling
  - 16 comprehensive tests with 100% coverage
  - All 524 unit tests passing, 84% overall coverage
- Task 7.3: Implement Tool step execution (COMPLETE)
  - Created execute_tool_step() function that projects events, executes tools, and writes result events
  - Projects events to get tool calls using project_to_tool_arguments()
  - For each tool call: writes ToolExecutionRequested, executes tool, writes result event
  - Returns True if all tools succeeded, False if any failed
  - Updated main processing loop to call execute_tool_step
  - 12 comprehensive tests with 100% coverage
  - All 508 unit tests passing, 83% overall coverage
- Task 7.2: Implement LLM step execution (COMPLETE)
  - Created execute_llm_step() function that projects events, calls LLM, and writes result events
  - Implements retry logic with configurable max_retries (default 2)
  - Writes LLMResponseReceived on success, LLMCallFailed on failure
  - Returns True/False to indicate success/failure
  - Integrated into main processing loop
  - 11 comprehensive tests with 96% coverage
  - All 496 unit tests passing, 83% overall coverage
- Task 7.1: Implement processing loop (COMPLETE)
  - Created src/messagedb_agent/engine/loop.py with main processing loop
  - Implemented process_thread() with event reading, projection, and step routing
  - Created ProcessingError and MaxIterationsExceeded exception classes
  - Created _message_to_event() helper to convert Message DB Messages to BaseEvents
  - Handles termination detection and max_iterations limit
  - LLM_CALL and TOOL_EXECUTION steps raise NotImplementedError (for Tasks 7.2/7.3)
  - 11 comprehensive tests with 96% coverage
  - All 485 unit tests passing, linting/formatting/type checking clean
- Task 6.4: Convert tools to LLM function declarations (COMPLETE - Phase 6 complete! ✅)
  - Created schema.py with 7 utility functions for Tool→ToolDeclaration conversion
  - tool_to_function_declaration(), tools_to_function_declarations(), registry_to_function_declarations()
  - get_tool_names_from_declarations(), validate_function_declaration(), filter_tools_by_name()
  - merge_schema_properties() for extending tool schemas
  - Converts to unified ToolDeclaration format (works for both Gemini and Claude)
  - Preserves parameter schemas exactly, handles required vs optional parameters
  - 42 tests with 94% coverage, all passing
  - Phase 6 (Tool Framework) now complete - all tasks 6.1-6.4 done!
- Task 6.3: Create example builtin tools (COMPLETE)
  - Implemented get_current_time(), echo(), and calculate() tools
  - calculate() uses safe AST parsing (NO eval()) for security
  - Supports all basic arithmetic operators with comprehensive error handling
  - Added get_builtin_tools() and register_builtin_tools() helpers
  - 54 tests with 95% coverage, all passing
- Task 6.2: Implement tool execution (COMPLETE)
  - Created ToolExecutionResult dataclass and execute_tool() function
  - Full exception handling with no raised exceptions (all wrapped in result)
  - Execution time tracking in milliseconds using perf_counter
  - Added execute_tool_safe() and batch_execute_tools() utilities
  - 37 tests with 100% coverage, all passing
- Task 6.1: Create tool registration system (COMPLETE)
  - Created Tool dataclass and ToolRegistry class
  - Implemented @tool decorator with auto-schema generation from type hints
  - Implemented register_tool() decorator factory
  - Custom error hierarchy and comprehensive validation
  - 34 tests with 98% coverage, all passing
- Task 4.4: Implement Tool Arguments projection (COMPLETE)
  - Created project_to_tool_arguments() to extract tool calls from events
  - Returns list of tool call dicts with id, name, arguments
  - Helper functions for tool lookup, counting, and checking
  - Handles both dict and ToolCall dataclass formats
  - 28 comprehensive tests with 100% code coverage
  - All 307 unit tests passing
- Task 4.3: Implement Session State projection (COMPLETE)
  - Created SessionState dataclass and SessionStatus enum
  - Implemented project_to_session_state() to aggregate session statistics
  - Tracks: status, message/LLM/tool/error counts, session timing
  - Helper functions: is_session_active(), get_session_duration()
  - Thread ID extraction from stream name
  - 33 comprehensive tests with 95% code coverage
  - All 279 unit tests passing
- Task 4.5: Implement Next Step projection (COMPLETE)
  - Created StepType enum (LLM_CALL, TOOL_EXECUTION, TERMINATION)
  - Implemented project_to_next_step() using Last Event Pattern
  - Decision logic based on most recent event type
  - Helper functions: should_terminate(), get_pending_tool_calls(), count_steps_taken()
  - 24 comprehensive tests with 93% code coverage
  - All type checking passed, handles edge cases gracefully
- Task 4.2: Implement LLM Context projection (COMPLETE)
  - Created project_to_llm_context() function that converts events to Message objects
  - Converts UserMessageAdded, LLMResponseReceived, ToolExecutionCompleted events
  - Filters out system/metadata events not relevant to LLM context
  - Added get_last_user_message() and count_conversation_turns() helper functions
  - 13 comprehensive tests with 88% code coverage
  - All type checking passed with proper type annotations
- Task 4.1: Create projection base infrastructure (COMPLETE)
  - Created ProjectionFunction[T] type alias for type-safe projection functions
  - Created ProjectionResult[T] dataclass wrapping results with metadata
  - Implemented project_with_metadata() and compose_projections() utilities
  - 20 comprehensive tests with 100% code coverage
  - All linting, formatting, and type checking passed
- Phase 3: Event Schema and Types (COMPLETE - All 5 tasks done! ✅)
  - Task 3.1: Base event structure with BaseEvent and EventData classes
  - Task 3.2: User event types (UserMessageAdded, SessionTerminationRequested)
  - Task 3.3: Agent event types (LLMResponseReceived, LLMCallFailed, ToolCall)
  - Task 3.4: Tool event types (ToolExecutionRequested, ToolExecutionCompleted, ToolExecutionFailed)
  - Task 3.5: System event types (SessionStarted, SessionCompleted)
  - All event types have comprehensive validation and are exported from events module
- Task 5.4: Define system prompt (COMPLETE - Phase 5 LLM Integration now complete!)
  - Created comprehensive prompts.py module with 3 default prompts
  - `DEFAULT_SYSTEM_PROMPT` - Event-sourced agent with tool guidance
  - `MINIMAL_SYSTEM_PROMPT` - Simple, concise prompt
  - `TOOL_FOCUSED_SYSTEM_PROMPT` - Emphasizes tool usage
  - Utilities: `create_system_prompt()` for customization, `get_prompt_for_task()` for presets
  - Comprehensive prompt engineering guidelines documented in module
  - 20 tests with 100% coverage of prompts module
  - All 189 unit tests passing
- Task 5.3.1: Add Claude model support via AnthropicVertex SDK (COMPLETE)
  - Added `anthropic[vertex]>=0.42.0` dependency
  - Created unified `BaseLLMClient` interface for both Gemini and Claude
  - Implemented `ClaudeClient` using AnthropicVertex SDK
  - Refactored Gemini into `GeminiClient` with same interface
  - Created `create_llm_client()` factory for auto-detection
  - Removed 1,049 lines of legacy Gemini-only API code
  - Both models use same `client.call(messages, tools, system_prompt)` API
  - Tool calling works identically for both models
  - Created 9 comprehensive integration tests (all passing)
  - All 169 unit tests + 9 integration tests passing
  - Code coverage: 80% ClaudeClient, 78% GeminiClient, 92% factory
- Task 5.3: Implement LLM call function
  - Note: This task was superseded by Task 5.3.1 unified implementation
  - Legacy call_llm() removed in favor of BaseLLMClient.call()
- Task 5.2: Implement message formatting
  - Created Message dataclass for internal message representation
  - Implemented format_messages() to convert to Vertex AI Content/Part format
  - Handles user, model, and function messages with validation
  - Supports system prompts, text, function calls, and function responses
  - Added convenience functions for message creation
- Task 5.1: Setup Vertex AI client
  - Created `VertexAIClient` class with ADC authentication support
  - Supports both Gemini and Claude models via Vertex AI API
  - Uses Application Default Credentials via `google.auth.default()`
  - Added factory function `create_client()` for convenient initialization
  - Comprehensive docstrings and type hints with google.auth type compatibility
- Task 2.4: Implemented stream utilities for Message DB stream name management
  - Created `generate_thread_id()` for UUID4 thread identifier generation
  - Created `build_stream_name()` to build stream names in format `category:version-thread_id`
  - Created `parse_stream_name()` to parse stream names back into components
  - Comprehensive validation: prevents invalid characters, validates all components
  - Added 38 comprehensive tests covering all functions, edge cases, and round-trip consistency
- Task 2.3: Implemented `read_stream` function with Event dataclass and comprehensive tests
- Task 10.2: Set up Docker-based Message DB test infrastructure with automatic container management
  - Switched to `ethangarofolo/message-db:1.3.1` image for reliable initialization
  - Fixed transaction management with explicit commits in write_event and read_stream
  - Configured search_path in connection string to support Message DB internal functions

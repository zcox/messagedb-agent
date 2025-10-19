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
- [ ] **Task 3.1: Define base event structure**
  - Create `src/messagedb_agent/events/base.py`
  - Define BaseEvent dataclass/TypedDict with: id, type, data, metadata, position, time
  - Define EventData base class for type-safe event payloads

- [ ] **Task 3.2: Define User event types**
  - Create `src/messagedb_agent/events/user.py`
  - Define UserMessageAdded event with payload: message (str), timestamp
  - Define SessionTerminationRequested event

- [ ] **Task 3.3: Define Agent event types**
  - Create `src/messagedb_agent/events/agent.py`
  - Define LLMCallRequested event with payload: projected_context
  - Define LLMResponseReceived event with payload: response_text, tool_calls (list), model_name, token_usage
  - Define LLMCallFailed event with payload: error_message, retry_count

- [ ] **Task 3.4: Define Tool event types**
  - Create `src/messagedb_agent/events/tool.py`
  - Define ToolExecutionRequested event with payload: tool_name, arguments (dict)
  - Define ToolExecutionCompleted event with payload: tool_name, result, execution_time_ms
  - Define ToolExecutionFailed event with payload: tool_name, error_message, retry_count

- [ ] **Task 3.5: Define System event types**
  - Create `src/messagedb_agent/events/system.py`
  - Define SessionStarted event with payload: thread_id, initial_context (optional)
  - Define SessionCompleted event with payload: completion_reason (success/failure/timeout)
  - Define ErrorOccurred event with payload: error_type, error_message, stack_trace (optional)

## Phase 4: Projection Framework

### 4. Projection Functions
- [ ] **Task 4.1: Create projection base infrastructure**
  - Create `src/messagedb_agent/projections/base.py`
  - Define ProjectionFunction type: `Callable[[List[BaseEvent]], T]`
  - Create ProjectionResult generic type for typed projection outputs
  - Document projection purity requirements in docstrings

- [ ] **Task 4.2: Implement LLM Context projection**
  - Create `src/messagedb_agent/projections/llm_context.py`
  - Implement `project_to_llm_context(events) -> List[Message]` function
  - Convert UserMessageAdded → user message
  - Convert LLMResponseReceived → assistant message (text + tool_calls)
  - Convert ToolExecutionCompleted → tool result message
  - Skip system/metadata events in context
  - Return messages in chronological order suitable for Vertex AI API

- [ ] **Task 4.3: Implement Session State projection**
  - Create `src/messagedb_agent/projections/session_state.py`
  - Define SessionState dataclass: thread_id, status (active/completed/failed), message_count, tool_call_count, last_activity_time
  - Implement `project_to_session_state(events) -> SessionState`
  - Aggregate statistics from events
  - Track current session status based on event types

- [ ] **Task 4.4: Implement Tool Arguments projection**
  - Create `src/messagedb_agent/projections/tool_args.py`
  - Implement `project_to_tool_arguments(events) -> Dict[str, Any]`
  - Extract tool call arguments from most recent LLMResponseReceived event
  - Return dict mapping tool_name to arguments
  - Handle case where no tool calls present

- [ ] **Task 4.5: Implement Next Step projection**
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

## Phase 5: LLM Integration

### 5. Vertex AI Integration
- [ ] **Task 5.1: Setup Vertex AI client**
  - Create `src/messagedb_agent/llm/client.py`
  - Initialize Vertex AI using google.auth.default() for ADC
  - Configure from environment variables: GCP_PROJECT, GCP_LOCATION, MODEL_NAME (eg gemini-2.5-pro or claude-sonnet-4-5@20250929)
  - Create wrapper for unified interface regardless of model choice

- [ ] **Task 5.2: Implement message formatting**
  - Create `src/messagedb_agent/llm/format.py`
  - Implement function to convert projection messages to Vertex AI format
  - Handle system prompts
  - Handle user/assistant message formatting
  - Handle function/tool call formatting
  - Handle tool result formatting

- [ ] **Task 5.3: Implement LLM call function**
  - Create `src/messagedb_agent/llm/call.py`
  - Implement `call_llm(messages, tools, model_name) -> LLMResponse`
  - LLMResponse dataclass: text, tool_calls (List[ToolCall]), model_name, token_usage (dict)
  - ToolCall dataclass: id, name, arguments (dict)
  - Handle Vertex AI API errors with proper error types
  - Extract text and tool calls from response
  - Track token usage from response metadata

- [ ] **Task 5.4: Define system prompt**
  - Create `src/messagedb_agent/llm/prompts.py`
  - Define default system prompt for agent behavior
  - Make system prompt configurable
  - Document prompt engineering guidelines

## Phase 6: Tool Framework

### 6. Tool Definition and Execution
- [ ] **Task 6.1: Create tool registration system**
  - Create `src/messagedb_agent/tools/registry.py`
  - Define Tool dataclass: name, description, parameters_schema (dict), function (Callable)
  - Create ToolRegistry class with register/get methods
  - Implement function decorator `@tool(name, description)` for easy registration
  - Auto-generate parameters_schema from function type hints and docstrings

- [ ] **Task 6.2: Implement tool execution**
  - Create `src/messagedb_agent/tools/executor.py`
  - Implement `execute_tool(tool_name, arguments, registry) -> Any`
  - Look up tool in registry
  - Call tool function with arguments (no validation in basic impl)
  - Catch and wrap exceptions
  - Return result or error
  - Track execution time

- [ ] **Task 6.3: Create example tools**
  - Create `src/messagedb_agent/tools/builtin.py`
  - Implement `get_current_time() -> str` - returns current datetime
  - Implement `calculate(expression: str) -> float` - evaluates math expression safely
  - Implement `echo(message: str) -> str` - returns the message (for testing)
  - Register all builtin tools

- [ ] **Task 6.4: Convert tools to LLM function declarations**
  - Create `src/messagedb_agent/tools/schema.py`
  - Implement `tools_to_function_declarations(tools) -> List[Dict]`
  - Convert Tool objects to Vertex AI function calling format
  - Include name, description, and parameters schema
  - Handle required vs optional parameters

## Phase 7: Processing Engine

### 7. Main Processing Loop
- [ ] **Task 7.1: Implement processing loop**
  - Create `src/messagedb_agent/engine/loop.py`
  - Implement `process_thread(thread_id, store_client, llm_client, tool_registry, max_iterations=100)`
  - Main loop structure:
    1. Read all events for thread from stream
    2. Project to next_step
    3. If TERMINATION, break
    4. If LLM_CALL, execute LLM step
    5. If TOOL_EXECUTION, execute tool step
    6. Write result events back to stream
    7. Repeat until termination or max_iterations
  - Return final session state

- [ ] **Task 7.2: Implement LLM step execution**
  - Create `src/messagedb_agent/engine/steps/llm.py`
  - Implement `execute_llm_step(events, llm_client, tool_registry, stream_name, store_client)`
  - Project events to LLM context
  - Get tool declarations from registry
  - Call LLM with context and tools
  - Handle success: write LLMResponseReceived event
  - Handle failure: write LLMCallFailed event, implement simple retry logic
  - Return success/failure status

- [ ] **Task 7.3: Implement Tool step execution**
  - Create `src/messagedb_agent/engine/steps/tool.py`
  - Implement `execute_tool_step(events, tool_registry, stream_name, store_client)`
  - Project events to get tool calls from last LLM response
  - For each tool call:
    - Write ToolExecutionRequested event
    - Execute tool
    - Write ToolExecutionCompleted or ToolExecutionFailed event
  - Return success/failure status

- [ ] **Task 7.4: Implement session initialization**
  - Create `src/messagedb_agent/engine/session.py`
  - Implement `start_session(initial_message: str, store_client) -> str`
  - Generate new thread_id
  - Build stream_name
  - Write SessionStarted event
  - Write UserMessageAdded event with initial_message
  - Return thread_id

- [ ] **Task 7.5: Implement session termination**
  - Add `terminate_session(thread_id, reason, store_client)` to session.py
  - Write SessionCompleted event with reason
  - Handle graceful shutdown

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

Recommended implementation order for efficient development:

1. **Phase 1: Project Foundation** (Tasks 1.1-1.3)
2. **Phase 2: Event Store Integration** (Tasks 2.1-2.4)
3. **Phase 3: Event Schema** (Tasks 3.1-3.5)
4. **Phase 10.2: Setup test infrastructure** (Task 10.1-10.2) - interleave with development
5. **Phase 4: Projection Framework** (Tasks 4.1-4.5)
6. **Phase 6: Tool Framework** (Tasks 6.1-6.4)
7. **Phase 5: LLM Integration** (Tasks 5.1-5.4)
8. **Phase 7: Processing Engine** (Tasks 7.1-7.5)
9. **Phase 9: Configuration and CLI** (Tasks 9.1-9.3)
10. **Phase 8: Observability** (Tasks 8.1-8.5)
11. **Phase 10: Testing** (Tasks 10.3-10.7) - complete remaining tests
12. **Phase 11: Documentation** (Tasks 11.1-11.5)
13. **Phase 12: Polish** (Tasks 12.1-12.6)

## Progress Tracking

- Total Tasks: 77
- Completed: 8 (Tasks 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 2.4, 10.2)
- In Progress: 0
- Remaining: 69
- Completion: 10.4%

Last Updated: 2025-10-19

**Recent Completions:**
- Task 2.4: Implemented stream utilities for Message DB stream name management
  - Created `generate_thread_id()` for UUID4 thread identifier generation
  - Created `build_stream_name()` to build stream names in format `category:version-thread_id`
  - Created `parse_stream_name()` to parse stream names back into components
  - Comprehensive validation: prevents invalid characters, validates all components
  - Added 38 comprehensive tests covering all functions, edge cases, and round-trip consistency
  - All 52 tests passing across the project
- Task 2.3: Implemented `read_stream` function with Event dataclass and comprehensive tests
- Task 10.2: Set up Docker-based Message DB test infrastructure with automatic container management
  - Switched to `ethangarofolo/message-db:1.3.1` image for reliable initialization
  - Fixed transaction management with explicit commits in write_event and read_stream
  - Configured search_path in connection string to support Message DB internal functions

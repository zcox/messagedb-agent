# CLAUDE.md

**Note**: This project uses [bd (beads)](https://github.com/steveyegge/beads) for issue tracking. Use `bd` commands instead of markdown TODOs. See AGENTS.md for workflow details.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow for Claude Code

**IMPORTANT**: After making any major code changes (new features, bug fixes, refactoring), you MUST:

1. **Run all linting and formatting tools** in this order:
   - `uv run ruff check src/ tests/` - Check for issues
   - `uv run ruff check --fix src/ tests/` - Auto-fix issues
   - `uv run black src/ tests/` - Format code
   - `uv run basedpyright src/` - Type check
   - **Fix any remaining errors** reported by these tools before proceeding

2. **Run all tests** to verify functionality:
   - `uv run pytest` - Run all tests (Docker container starts automatically)
   - **Fix any failing tests** before proceeding
   - Tests must pass before committing changes

3. **Commit changes to git** when major work is complete:
   - Stage relevant files with `git add`
   - Include the `.beads/issues.jsonl` file since it likely contains changes related to your work
   - Create a descriptive commit message following the existing style
   - Include the Claude Code footer in commit messages
   - Verify commit success with `git status`

Do NOT ask the user if they want you to run linting, tests, or commit - do it proactively as part of completing the work.

## Project Overview

This is an event-sourced agent system using Message DB (PostgreSQL) for durable, observable, and distributed LLM agent execution. The core architecture follows an event sourcing pattern where all agent interactions, decisions, and actions are recorded as immutable events in persistent streams.

## Key Architectural Concepts

### Event Sourcing Model
- **Events are the source of truth**: All state changes are recorded as append-only events in Message DB
- **Projections/Reductions**: Pure functions that transform event history into derived states (e.g., LLM context, session state)
- **Stream format**: `{category}:{version}-{threadId}` (e.g., `agent:v0-abc123`)
- **Critical principle**: Events stored ≠ data sent to consumers. Projections enable storing rich information while sending only what's needed downstream.

### Processing Loop
The system operates in a while-loop pattern:
1. Read events from stream for threadId
2. Project events into required state/context
3. Determine next step based on current state
4. Execute step (LLM call, tool execution, or termination)
5. Write result as new event(s) to stream

This loop can be explicit (single process) or distributed (event-triggered steps across processes).

### Step Types
- **LLM Step**: `llm(reduce(events))` - Projects events to conversation context, calls LLM, records response
- **Tool Step**: `tool(reduce(events))` - Projects events to tool parameters, executes tool, records result
- **Termination Step**: Signals session completion

### Event Categories
- **User Events**: Messages or commands from users
- **Agent Events**: LLM responses, reasoning, decisions
- **Tool Events**: Tool invocations and results
- **System Events**: Session lifecycle, errors, control flow
- **Metadata Events**: Timestamps, performance metrics, tracing

## Technology Stack

- **Language**: Python 3.11+ with type hints
- **Package Manager**: `uv` (not pip/poetry)
- **Event Store**: Message DB (PostgreSQL extension)
- **LLM**: Google Vertex AI with unified interface supporting:
  - Gemini models (via `google-cloud-aiplatform` SDK)
  - Claude models (via `anthropic[vertex]` SDK)
  - Both use Application Default Credentials (ADC) for authentication
- **Connection Pooling**: psycopg3 with psycopg-pool
- **Logging**: structlog (structured logging)
- **Tracing**: OpenTelemetry
- **Testing**: pytest with docker-compose for Message DB

## Development Commands

### Setup
```bash
# Install dependencies
uv sync

# With development tools
uv sync --dev
```

### Running Code
```bash
# Run Python scripts/modules
uv run python -m messagedb_agent

# Import and test modules
uv run python -c "from messagedb_agent.store import MessageDBClient; ..."
```

### Linting and Formatting
```bash
# Run all linting tools (recommended order)
uv run ruff check src/ tests/          # Check for code issues
uv run ruff check --fix src/ tests/    # Auto-fix issues
uv run black src/ tests/               # Format code
uv run basedpyright src/               # Type check (src only, not tests)

# Individual commands
uv run ruff check src/                 # Ruff linter only
uv run ruff check --fix src/           # Fix auto-fixable ruff issues
uv run black src/                      # Black formatter only
uv run basedpyright src/               # basedpyright type checker only
```

**Note**: Always run linting on both `src/` and `tests/` directories. Type checking with basedpyright is typically only run on `src/` since test files may have looser type requirements.

### Testing
```bash
# Run all tests (Docker container starts automatically via pytest-docker)
uv run pytest

# Run only unit tests (skip integration tests that call real LLM APIs)
uv run pytest -m "not integration"

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/store/test_operations.py

# Run all integration tests (requires GCP credentials)
uv run pytest -m integration -v -s

# Run specific integration test files
uv run pytest tests/llm/test_unified_integration.py -v -s
uv run pytest tests/test_e2e_integration.py -v -s

# Run with coverage
uv run pytest --cov=messagedb_agent --cov-report=term-missing

# Run specific test function
uv run pytest tests/store/test_operations.py::test_write_event
```

**Note**: Tests automatically start a Message DB Docker container using `ethangarofolo/message-db:1.3.1`. The container is managed by pytest-docker and will be cleaned up after tests complete. No manual container management required.

**Integration Tests**: All integration tests are marked with `@pytest.mark.integration` and require:
1. GCP credentials configured via `gcloud auth application-default login`
2. Environment variables: `GCP_PROJECT` and optionally `GCP_LOCATION` (defaults to us-central1)
3. Vertex AI API enabled in your GCP project
4. Run all integration tests with: `uv run pytest -m integration -v -s` (use `-s` to see output)

## Code Style Guidelines

- **Line length**: 100 characters
- **Type hints**: Required on all functions (enforced by basedpyright)
- **Type annotations**: Use modern Python 3.10+ syntax (`X | None` not `Optional[X]`, `dict` not `Dict`)
- **Import order**: stdlib, third-party, local (enforced by ruff's isort)
- **Docstrings**: Google or NumPy style with examples for public APIs

### Common Type Issues and Solutions

**psycopg dict_row results**: When using `dict_row` as the row factory, `fetchone()` returns `dict[str, Any] | None` but type checkers may infer it as `tuple[Any, ...] | None`. Use type casting:

```python
from typing import Any, cast

# Correct way to handle fetchone() with dict_row
result = cast(dict[str, Any] | None, cur.fetchone())
if result is not None:
    value = result["column_name"]  # Now the type checker knows this is a dict
```

**Explicit type annotations**: When assigning from `Any` types (like dict values), add explicit type annotations to maintain type safety:

```python
position: int = result["write_message"]  # Explicitly annotate the type
```

## Module Organization

```
src/messagedb_agent/
├── store/          # Message DB client and event operations (write_event, read_stream)
├── events/         # Event type definitions and schemas
├── projections/    # Pure projection functions (events → state)
├── engine/         # Processing loop and step execution
├── llm/            # Vertex AI integration and LLM calls
└── tools/          # Tool registry and execution framework
```

## Important Implementation Notes

### Message DB Integration
- Use `write_message` stored procedure for writes (implemented in `store/operations.py`)
- Use `get_stream_messages` for reads (to be implemented)
- **Optimistic Concurrency Control**: Use `expected_version` parameter when appropriate
- Handle `OptimisticConcurrencyError` exceptions for version conflicts
- Connection pooling via `MessageDBClient` context manager

### Configuration
- Environment variables for all config (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD)
- Google Cloud auth uses Application Default Credentials (ADC)
- Config class: `MessageDBConfig` with validation

### Projections
- Must be pure functions: `projection(events) → state`
- No caching in basic implementation
- Multiple projections can exist from same event stream
- Examples: LLM context projection, session state projection, tool arguments projection

### LLM Integration (Unified API)

The system provides a unified interface for both Gemini and Claude models via Vertex AI:

```python
from messagedb_agent.llm import create_llm_client, Message, ToolDeclaration
from messagedb_agent.config import VertexAIConfig

# Create config (works for either model - just change model_name)
config = VertexAIConfig(
    project="my-project",
    location="us-central1",
    model_name="claude-sonnet-4-5@20250929"  # or "gemini-2.5-flash"
)

# Factory auto-detects and creates appropriate client
client = create_llm_client(config)

# Same API for both models
messages = [Message(role="user", text="Hello!")]
response = client.call(messages)

# Tool calling works the same way
tool = ToolDeclaration(
    name="get_weather",
    description="Get weather for a location",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name"}
        },
        "required": ["city"]
    }
)
response = client.call(messages, tools=[tool], system_prompt="You are helpful")
```

**Key Classes:**
- `BaseLLMClient` - Abstract base class for all LLM clients
- `GeminiClient` - Gemini implementation using Vertex AI GenerativeModel API
- `ClaudeClient` - Claude implementation using AnthropicVertex SDK
- `create_llm_client()` - Factory that auto-detects model type from name
- `Message` - Universal message format (role: user/assistant/tool, text, tool_calls, etc.)
- `ToolDeclaration` - Universal tool definition format
- `LLMResponse` - Universal response format (text, tool_calls, token_usage)

**Both models support:**
- Text generation
- System prompts
- Tool/function calling
- Multi-turn conversations
- Token usage tracking

## Testing Strategy

- **Unit tests**: All pure functions (especially projections)
- **Integration tests**: Against real Message DB in Docker container
- **No mocking** of Message DB in integration tests
- Test event stream operations with optimistic concurrency scenarios

## Documentation References

- `spec.md`: Comprehensive system specification and architecture
- The beads system contains all tasks
- `basic-python.md`: Technology decisions and implementation approach
- Message DB docs: https://docs.eventide-project.org/user-guide/message-db/

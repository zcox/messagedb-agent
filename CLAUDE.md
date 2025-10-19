# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Workflow for Claude Code

**IMPORTANT**: After making any major code changes (new features, bug fixes, refactoring), you MUST:

1. **Run all linting and formatting tools** in this order:
   - `uv run ruff check src/ tests/` - Check for issues
   - `uv run ruff check --fix src/ tests/` - Auto-fix issues
   - `uv run black src/ tests/` - Format code
   - `uv run mypy src/` - Type check
   - **Fix any remaining errors** reported by these tools before proceeding

2. **Commit changes to git** when major work is complete:
   - Stage relevant files with `git add`
   - Create a descriptive commit message following the existing style
   - Include the Claude Code footer in commit messages
   - Verify commit success with `git status`

Do NOT ask the user if they want you to run linting or commit - do it proactively as part of completing the work.

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
- **LLM**: Google Vertex AI (Gemini or Claude models via ADC auth)
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
uv run mypy src/                       # Type check (src only, not tests)

# Individual commands
uv run ruff check src/                 # Ruff linter only
uv run ruff check --fix src/           # Fix auto-fixable ruff issues
uv run black src/                      # Black formatter only
uv run mypy src/                       # Mypy type checker only
```

**Note**: Always run linting on both `src/` and `tests/` directories. Type checking with mypy is typically only run on `src/` since test files may have looser type requirements.

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_store.py

# Run with coverage
uv run pytest --cov=messagedb_agent --cov-report=term-missing

# Run specific test function
uv run pytest tests/test_store.py::test_write_event
```

## Code Style Guidelines

- **Line length**: 100 characters
- **Type hints**: Required on all functions (enforced by mypy)
- **Type annotations**: Use modern Python 3.10+ syntax (`X | None` not `Optional[X]`, `dict` not `Dict`)
- **Import order**: stdlib, third-party, local (enforced by ruff's isort)
- **Docstrings**: Google or NumPy style with examples for public APIs

### Common Type Issues and Solutions

**psycopg dict_row results**: When using `dict_row` as the row factory, `fetchone()` returns `dict[str, Any] | None` but mypy infers it as `tuple[Any, ...] | None`. Use type casting:

```python
from typing import Any, cast

# Correct way to handle fetchone() with dict_row
result = cast(dict[str, Any] | None, cur.fetchone())
if result is not None:
    value = result["column_name"]  # Now mypy knows this is a dict
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

### Current Implementation Status
See `tasks.md` for detailed progress. Key completed tasks:
- Phase 1: Project foundation (complete)
- Task 2.1: Message DB client with connection pooling (complete)
- Task 2.2: write_event function with OCC (complete)

Still to implement:
- Task 2.3: read_stream function
- Event type definitions
- Projection framework
- LLM integration
- Tool framework
- Processing engine

## Testing Strategy

- **Unit tests**: All pure functions (especially projections)
- **Integration tests**: Against real Message DB in Docker container
- **No mocking** of Message DB in integration tests
- Test event stream operations with optimistic concurrency scenarios

## Documentation References

- `spec.md`: Comprehensive system specification and architecture
- `tasks.md`: Implementation task tracking with progress
- `basic-python.md`: Technology decisions and implementation approach
- Message DB docs: https://docs.eventide-project.org/user-guide/message-db/

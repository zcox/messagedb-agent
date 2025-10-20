# messagedb-agent

Event-sourced agent system using Message DB for durable, observable, and distributed execution.

## Overview

This project implements an event-sourced architecture for agent systems where all agent interactions, decisions, and actions are recorded as immutable events in persistent streams. The system enables durable, observable, and distributed execution of agent workflows through event-driven processing.

## Features

- **Durability**: Event storage persists beyond process lifetime with recovery from crashes
- **Distributed Execution**: Steps can execute on different processes or machines
- **Observability**: Complete audit trail of all agent actions with replay capabilities
- **Flexibility**: Modify projection logic without changing stored events
- **Extensibility**: Additional consumers can process event streams

## Installation

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install dependencies
uv sync

# Install with development dependencies
uv sync --dev
```

## Requirements

- Python 3.11+
- PostgreSQL with Message DB extension
- Vertex AI access (for LLM integration)

## Configuration

Create a `.env` file in the project root with the following variables:

```bash
# Message DB Configuration
DB_HOST=localhost
DB_PORT=5433
DB_NAME=message_store
DB_USER=postgres
DB_PASSWORD=message_store_password

# Vertex AI Configuration
GCP_PROJECT=your-gcp-project-id
GCP_LOCATION=us-central1
MODEL_NAME=claude-sonnet-4-5@20250929  # or gemini-2.5-pro

# Processing Configuration (optional)
MAX_ITERATIONS=100
ENABLE_TRACING=false
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Setting up Message DB

Start the Message DB Docker container:

```bash
docker-compose up -d
```

### Setting up GCP Authentication

Authenticate with Google Cloud to access Vertex AI:

```bash
gcloud auth application-default login
```

## Connecting to Local Message DB

```
PGPASSWORD=message_store_password PGOPTIONS="--search_path=message_store" psql -h localhost -p 5433 -U postgres -d message_store
```

## CLI Usage

The CLI provides commands for managing agent sessions:

### Start a New Session

Start a new conversation with the agent:

```bash
uv run python -m messagedb_agent.cli start "What is the current time?"
```

This will:
1. Create a new session with a unique thread ID
2. Send your initial message to the agent
3. Process the session and display the results
4. Show the thread ID for future interactions

### Add a Message to Existing Session

Continue a conversation by adding a new message:

```bash
uv run python -m messagedb_agent.cli message <thread-id> "Can you calculate 42 * 7?"
```

This enables multi-turn conversations while maintaining full conversation history.

### Continue an Existing Session

Resume processing an existing session:

```bash
uv run python -m messagedb_agent.cli continue <thread-id>
```

### Show Session Events

Display all events for a session:

```bash
# Text format (default)
uv run python -m messagedb_agent.cli show <thread-id>

# JSON format
uv run python -m messagedb_agent.cli show <thread-id> --format json

# Show full event data including metadata
uv run python -m messagedb_agent.cli show <thread-id> --full
```

### List Recent Sessions

List recent agent sessions:

```bash
# List 10 most recent sessions (default)
uv run python -m messagedb_agent.cli list

# List 20 sessions
uv run python -m messagedb_agent.cli list --limit 20

# JSON format
uv run python -m messagedb_agent.cli list --format json
```

### Global Options

All commands support these global options:

```bash
# Use custom config file
--config .env.production

# Use custom stream category
--category my-agent

# Use custom stream version
--version v2
```

### Example Multi-turn Conversation

```bash
# Start a conversation
uv run python -m messagedb_agent.cli start "What is 5 + 3?"
# Output: Session started with thread ID: abc-123-def-456

# Continue the conversation
uv run python -m messagedb_agent.cli message abc-123-def-456 "Can you also tell me the time?"

# Add another message
uv run python -m messagedb_agent.cli message abc-123-def-456 "Thanks for your help!"

# View the entire conversation
uv run python -m messagedb_agent.cli show abc-123-def-456
```

## Project Status

This project is currently in development. See [tasks.md](tasks.md) for implementation progress.

**Completed Features:**
- ✅ Event store integration (Message DB)
- ✅ Event schema and types
- ✅ Projection framework
- ✅ LLM integration (Vertex AI with Gemini and Claude support)
- ✅ Tool framework with builtin tools
- ✅ Processing engine with main loop
- ✅ CLI with multi-turn conversation support
- ✅ Configuration management

**Progress:** 33/78 tasks complete (42.3%)

## Documentation

- [Specification](spec.md) - Detailed system specification
- [Implementation Decisions](basic-python.md) - Technology choices and rationale
- [Tasks](tasks.md) - Implementation task tracking

## License

MIT

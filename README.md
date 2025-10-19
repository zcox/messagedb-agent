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

## Project Status

This project is currently in development. See [tasks.md](tasks.md) for implementation progress.

## Documentation

- [Specification](spec.md) - Detailed system specification
- [Implementation Decisions](basic-python.md) - Technology choices and rationale
- [Tasks](tasks.md) - Implementation task tracking

## License

MIT

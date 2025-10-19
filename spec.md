# Event-Sourced Agent System Specification

## 1. Overview

This specification defines an event-sourced agent system architecture where all agent interactions, decisions, and actions are recorded as immutable events in persistent streams. The system enables durable, observable, and distributed execution of agent workflows through event-driven processing.

## 2. Core Concepts

### 2.1 Event Stream
A persistent, ordered sequence of events representing the complete history of an agent session. Each stream is uniquely identified and maintains a chronological log of all activities.

**Properties:**
- Append-only: Events can only be added, never modified or deleted
- Ordered: Events maintain strict chronological ordering
- Persistent: Events survive process restarts and failures
- Multi-reader: Multiple processes can consume the same stream

**Stream Identity:**
- Format: `{category}:{version}-{threadId}`
- Category: Logical grouping of related streams
- Version: Schema or implementation version
- ThreadId: Unique identifier for the specific agent session

### 2.2 Thread
A thread represents a single agent session, conceptually similar to a conversational session or multi-turn interaction. Each thread corresponds to one event stream.

**Characteristics:**
- Contains a series of user messages, LLM responses, tool executions, and internal state transitions
- Maintains session context through event accumulation
- Can be resumed after interruption by replaying events
- Enables audit trail and debugging capabilities

### 2.3 Events
Immutable records of state changes, actions, or observations within the system. Events are the single source of truth.

**Event Categories:**
- **User Events**: Messages or commands from the user
- **Agent Events**: LLM responses, reasoning steps, decisions
- **Tool Events**: Tool invocations and results
- **System Events**: Session lifecycle, errors, control flow
- **Metadata Events**: Timestamps, performance metrics, trace information

**Event Properties:**
- Unique identifier
- Event type/name
- Timestamp
- Sequence number within stream
- Payload (event-specific data)
- Metadata (optional contextual information)

### 2.4 Projection/Reduction
The process of transforming the event history into a derived state or view suitable for a specific purpose.

**Key Principles:**
- Events stored in the stream ≠ data sent to downstream consumers
- Projections are pure functions: `projection(events) → state`
- Multiple projections can exist from the same event stream
- Projections enable separation of storage from consumption

**Common Projections:**
- LLM Context: Transform events into conversation messages for the language model
- Tool Arguments: Extract and format parameters for tool execution
- Session State: Compute current state of the agent session
- Summary View: Condensed representation for human consumption

## 3. System Architecture

### 3.1 Processing Model

The system operates in a loop, executing discrete steps until completion:

```
while not done:
    1. Read events from stream for threadId
    2. Project events into required state/context
    3. Determine next step based on current state
    4. Execute step (LLM call, tool execution, or termination)
    5. Write result as new event(s) to stream
```

This while-loop may be explicit, written as a while or for loop in the implementation language, and executing within the same process. Or, it may be distributed, with one step triggered by an event and executed at a time.

### 3.2 Step Types

#### 3.2.1 LLM Step
Invokes the language model to generate responses, make decisions, or produce plans.

**Input:** `llm(reduce(events))`
- Events are projected into conversation context
- May include compression, summarization, or filtering
- Format optimized for the specific LLM API

**Output:**
- Agent response text
- Tool calls (if any)
- Reasoning traces (optional)
- Metadata (tokens used, latency, model version)

**Event Recording:**
- Store complete LLM request (projected context)
- Store complete LLM response (raw output)
- Store any intermediate artifacts

#### 3.2.2 Tool Step
Executes external functions, APIs, or capabilities.

**Input:** `tool(reduce(events))`
- Events are projected into tool parameters
- May transform LLM tool call into actual tool arguments
- Enables validation and transformation layer

**Output:**
- Tool execution result
- Side effects (file writes, HTTP requests, state changes)
- Error information (if failed)
- Performance metrics

**Event Recording:**
- Store tool invocation parameters
- Store tool execution results
- Store side effects separately for auditability
- Record errors and retry attempts

#### 3.2.3 Termination Step
Signals completion of the agent session.

**Triggers:**
- User explicitly ends session
- Agent determines task is complete
- Error condition requiring session termination
- Timeout or resource limit reached

**Event Recording:**
- Final status (success, failure, timeout)
- Summary information
- Cleanup actions

### 3.3 Event Processing Strategy

**Last Event Pattern:**
The most recent event typically determines the next action:
- `UserMessageAdded` → Call LLM
- `LLMCalled` → Parse for tool calls or respond to user
- `ToolCalled` → Call LLM with result
- `SessionTerminationRequested` → End session

**State Accumulation:**
Some decisions require analyzing multiple events or the entire history:
- Detecting conversation loops
- Enforcing rate limits or quotas
- Maintaining long-term memory
- Computing aggregate statistics

### 3.4 Customization Points

#### 3.4.1 Projection Functions
Users can define custom projection logic:
- How events map to LLM messages
- How to compress or summarize long histories
- Which events to include/exclude
- How to format tool parameters

#### 3.4.2 Step Selection Logic
The algorithm for determining the next step can be customized:
- Custom routing based on event patterns
- Insertion of additional step types
- Conditional branching logic
- Integration with external decision systems

#### 3.4.3 Additional Steps
The system should support extension with new step types:
- Human-in-the-loop approval steps
- External validation or review
- Integration with other systems
- Custom business logic

#### 3.4.4 Custom Events
The system should support recording additional, custom event types in the stream
- Domain-specific state changes
- Used in custom projection functions

## 4. Key Advantages

### 4.1 Durability
- Event storage persists beyond process lifetime
- Recovery from crashes by replaying events
- No loss of conversation context or state

### 4.2 Distributed Execution
- Steps can execute on different processes or machines
- Event stream serves as coordination mechanism
- Enables horizontal scaling across workers
- Location-independent processing

### 4.3 Observability
- Complete audit trail of all agent actions
- Replay and analyze past sessions
- Debug issues by examining event history
- Performance analysis via event metadata

### 4.4 Flexibility
- Modify projection logic without changing stored events
- Reprocess history with updated logic
- Filter or transform events before consumption
- Store rich information, send only what's needed

### 4.5 Extensibility
- Additional consumers can process event streams
- Trigger notifications or alerts on specific events
- Spawn secondary agents in response to events
- Export to analytics or monitoring systems
- Integration with observability platforms (distributed tracing, metrics)

### 4.6 Event Stream as Integration Point
- Other systems can subscribe to event streams
- Real-time reaction to agent activities
- Cross-agent communication via events
- Event-driven microservices architecture
- Project events and store results in other views/databases, optimized for certain queries

## 5. Open Questions & Future Considerations

### 5.1 Human-in-the-Loop Integration
**Challenge:** How to incorporate human approval or input into the event-driven flow?

**Potential Approaches:**
- Emit `HumanApprovalRequested` event, pause until `HumanApprovalProvided` event
- Separate streams for agent automation vs. human interaction
- Timeout mechanisms for pending human actions
- Queue or notification system for human attention

### 5.2 Streaming Partial Results
**Challenge:** How to stream incremental results while maintaining event consistency?

**Potential Approaches:**
- Fine-grained events for token-by-token streaming
- Separate ephemeral stream for real-time updates
- Coarse-grained events with final results only
- Hybrid: stream to clients, record final results as events

### 5.3 External Integration
**Challenge:** How to integrate with observability and tracing platforms?

**Potential Approaches:**
- Generate distributed traces from event metadata
- Map events to OpenTelemetry spans
- Export events to external systems (LangSmith, DataDog, etc.)
- Standardized event format for interoperability

### 5.4 Event Schema Evolution
**Challenge:** How to handle schema changes over time?

**Considerations:**
- Version identifiers in stream names
- Forward/backward compatibility strategies
- Migration tools for old event formats
- Schema registry for event definitions

### 5.5 Performance & Scale
**Challenge:** Managing performance with large event streams

**Considerations:**
- Snapshotting to avoid replaying entire history
- Event archival and retention policies
- Indexing strategies for efficient queries
- Partitioning strategies for high throughput

## 6. Implementation Guidelines

### 6.1 Event Store Requirements
The underlying event storage system should provide:
- Strong ordering guarantees
- Atomic append operations
- Optimistic concurrency control
- Efficient sequential reads
- Stream partitioning/sharding capabilities
- Subscription/notification mechanisms (optional but valuable)
- [Message DB](https://github.com/message-db/message-db) is a good reference implementation

### 6.2 Processing Engine Requirements
The step execution engine should support:
- Idempotent step execution
- Error handling and retry logic
- Concurrent processing with coordination
- Graceful shutdown and recovery
- Resource limits and quotas

### 6.3 Projection Framework Requirements
The projection/reduction framework should provide:
- Pure, deterministic functions
- Composability and reusability
- Testing and validation capabilities
- Performance optimization (caching, incremental updates)

## 7. Non-Functional Requirements

### 7.1 Reliability
- No event loss under normal operation
- Automatic recovery from transient failures
- Data consistency guarantees

### 7.2 Performance
- Low latency for event appending
- Efficient event stream reading
- Scalable to thousands of concurrent threads

### 7.3 Security
- Access control for event streams
- Encryption for sensitive data
- Audit logging of system access

### 7.4 Maintainability
- Clear event schemas and documentation
- Monitoring and alerting capabilities
- Debugging and diagnostic tools

## 8. Summary

This specification defines an event-sourced architecture for agent systems that prioritizes durability, observability, and distributed execution. By recording all agent activities as immutable events, the system enables sophisticated replay, analysis, and recovery capabilities while maintaining flexibility in how events are processed and consumed. The separation between event storage and consumption through projections allows for rich data capture while maintaining efficient processing.

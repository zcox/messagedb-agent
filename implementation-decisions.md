# Implementation Technology Decisions

This document catalogs all technology and design decisions required to implement the Event-Sourced Agent System as specified in `spec.md`. Each decision should be evaluated and documented before or during implementation.

## 1. Event Store

### 1.1 Event Storage Technology
**Decision Required:** Which event store implementation to use?

**Options:**
- Message DB (PostgreSQL-based, recommended in spec)
- EventStore DB
- Apache Kafka
- Custom implementation on PostgreSQL/MySQL
- DynamoDB Streams
- Redis Streams
- Other event sourcing database

**Considerations:**
- Strong ordering guarantees (required)
- Atomic append operations (required)
- Optimistic concurrency control (required)
- Efficient sequential reads (required)
- Stream partitioning/sharding capabilities (required)
- Subscription/notification mechanisms (optional but valuable)
- Operational complexity
- Cost and licensing
- Team familiarity

### 1.2 Stream Naming Convention
**Decision Required:** Exact format and rules for stream identifiers

**Spec Guideline:** `{category}:{version}-{threadId}`

**Questions to Answer:**
- What categories will be used? (e.g., "agent", "session", "workflow")
- Version format? (semantic versioning, simple integers, timestamps)
- ThreadId generation strategy? (UUID, ULID, custom)
- Character restrictions and validation rules
- Case sensitivity

### 1.3 Event Schema Format
**Decision Required:** How to structure and serialize event data

**Options:**
- JSON (human-readable, flexible)
- Protocol Buffers (compact, strongly typed)
- Avro (schema evolution support)
- MessagePack (compact, fast)
- Custom binary format

**Considerations:**
- Schema evolution requirements (section 5.4)
- Human readability vs performance
- Type safety requirements
- Tooling availability
- Interoperability needs

### 1.4 Event Metadata Standard
**Decision Required:** Standard fields and format for event metadata

**Required Fields (from spec):**
- Unique identifier
- Event type/name
- Timestamp
- Sequence number within stream
- Payload
- Optional metadata

**Questions to Answer:**
- Timestamp format and timezone handling
- Event ID generation (UUID v4, v7, ULID, sequential)
- Metadata schema (free-form or structured)
- Causation/correlation ID strategy
- Event versioning approach

## 2. Processing Engine

### 2.1 Processing Model Implementation
**Decision Required:** Explicit loop vs distributed event-driven architecture

**Options:**
- **In-process loop:** Single process with explicit while/for loop
- **Distributed:** Event-triggered functions (serverless, message queues)
- **Hybrid:** Coordinated workers with explicit loops

**Considerations:**
- Scalability requirements
- Latency tolerance
- Operational complexity
- Cost model
- Debugging complexity

### 2.2 Concurrency and Coordination
**Decision Required:** How to handle concurrent processing of streams

**Questions to Answer:**
- Single writer per stream or optimistic concurrency?
- Locking/coordination mechanism if distributed
- How to prevent duplicate step execution
- Worker assignment strategy (if distributed)

### 2.3 Idempotency Strategy
**Decision Required:** How to ensure idempotent step execution

**Options:**
- Event-based deduplication (check for duplicate events before writing)
- Operation IDs and tracking
- Natural idempotency (design steps to be inherently idempotent)
- Distributed locks

### 2.4 Error Handling and Retry Logic
**Decision Required:** Strategy for handling failures

**Questions to Answer:**
- Retry policy (exponential backoff, fixed intervals)
- Maximum retry attempts
- Dead letter queue/stream for failed events
- Error event schema
- Circuit breaker implementation
- Transient vs permanent failure handling

### 2.5 Resource Limits and Quotas
**Decision Required:** How to enforce limits

**Limits to Consider:**
- Maximum events per stream
- Maximum stream lifetime
- Rate limits for LLM calls
- Rate limits for tool executions
- Token/cost budgets per thread
- Concurrent thread limits

## 3. LLM Integration

### 3.1 LLM Provider Selection
**Decision Required:** Which language model API to use

**Options:**
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Google (Gemini)
- Open-source models (Llama, Mistral via API or local)
- Multiple providers with abstraction layer

**Considerations:**
- Capability requirements
- Cost
- Latency
- Reliability
- Tool calling support
- Context window size

### 3.2 LLM API Format
**Decision Required:** How to structure LLM requests

**Questions to Answer:**
- Message format (OpenAI format, Anthropic format, custom)
- System prompt strategy
- Tool/function calling format
- Response parsing approach
- Streaming vs complete responses

### 3.3 Context Compression Strategy
**Decision Required:** How to handle long conversation histories

**Options:**
- No compression (use full context until limit)
- Sliding window (keep last N messages)
- Summarization (periodic summaries of old messages)
- Semantic compression (remove redundant information)
- Hybrid approaches

**Considerations:**
- Token limits of chosen LLM
- Cost optimization
- Information preservation requirements
- Latency impact

## 4. Tool Framework

### 4.1 Tool Definition Format
**Decision Required:** How to define and register tools

**Options:**
- JSON Schema
- TypeScript/Python type definitions
- OpenAPI/Swagger specs
- Custom DSL
- Code annotations/decorators

### 4.2 Tool Execution Environment
**Decision Required:** How and where tools execute

**Options:**
- In-process execution
- Sandboxed containers
- Separate microservices
- Serverless functions
- WebAssembly modules

**Considerations:**
- Security isolation needs
- Latency requirements
- Resource limits
- Deployment complexity

### 4.3 Tool Parameter Validation
**Decision Required:** Validation and transformation approach

**Questions to Answer:**
- Schema validation library
- Type coercion rules
- Error handling for invalid parameters
- Default value handling

### 4.4 Side Effect Recording
**Decision Required:** How to capture and record tool side effects (spec 3.2.2)

**Questions to Answer:**
- What constitutes a "side effect" event?
- Separate events vs metadata?
- How to record file system changes, HTTP requests, etc.
- Audit trail requirements

## 5. Projection Framework

### 5.1 Projection Function Implementation
**Decision Required:** Framework for defining projections

**Options:**
- Pure functions (functional programming style)
- Object-oriented reducers
- Declarative configuration
- Code generation from schemas

**Requirements (from spec 6.3):**
- Pure, deterministic functions
- Composability and reusability
- Testing and validation capabilities
- Performance optimization (caching, incremental updates)

### 5.2 Projection Caching Strategy
**Decision Required:** How to optimize projection performance

**Options:**
- No caching (recompute each time)
- Snapshot-based (periodic state snapshots)
- Incremental (cache last state, apply new events)
- Materialized views

**Considerations:**
- Memory vs CPU tradeoff
- Consistency requirements
- Snapshot storage location

### 5.3 Standard Projections
**Decision Required:** Which projections to provide out-of-box

**From Spec (2.4):**
- LLM Context projection
- Tool Arguments projection
- Session State projection
- Summary View projection

**Questions to Answer:**
- Default implementations for each
- Customization/override mechanism
- Testing approach for projections

## 6. Programming Language and Framework

### 6.1 Primary Implementation Language
**Decision Required:** Language for core system

**Options:**
- TypeScript/Node.js
- Python
- Go
- Rust
- Java/Kotlin
- Other

**Considerations:**
- Team expertise
- Ecosystem and libraries
- Performance requirements
- Type safety needs
- Async/concurrency model

### 6.2 Dependency Management
**Decision Required:** Required libraries and frameworks

**Categories:**
- Event store client/SDK
- LLM SDK
- HTTP client (for tools)
- Testing framework
- Logging and observability
- Serialization libraries

## 7. Observability and Monitoring

### 7.1 Logging Strategy
**Decision Required:** Logging framework and approach

**Questions to Answer:**
- Structured logging format (JSON, key-value)
- Log levels and verbosity
- Log aggregation system
- Correlation ID strategy

### 7.2 Distributed Tracing
**Decision Required:** Tracing implementation (spec 5.3)

**Options:**
- OpenTelemetry
- Jaeger
- Zipkin
- Proprietary (DataDog, New Relic)
- No tracing

**Questions to Answer:**
- Span creation strategy from events
- Trace context propagation
- Sampling rate

### 7.3 Metrics and Monitoring
**Decision Required:** Metrics collection approach

**Metrics to Track:**
- Events written per second
- Processing latency per step type
- LLM token usage and cost
- Tool execution times
- Error rates
- Active threads

**Technology:**
- Prometheus
- StatsD
- CloudWatch
- Custom metrics

### 7.4 External Integration
**Decision Required:** Integration with observability platforms (spec 5.3)

**Platforms to Consider:**
- LangSmith (LLM-specific)
- LangFuse
- Weights & Biases
- DataDog
- Generic OpenTelemetry exporters

## 8. Security

### 8.1 Access Control
**Decision Required:** Authentication and authorization mechanism

**Questions to Answer:**
- Who can create threads?
- Who can read event streams?
- Who can write events?
- Role-based access control model
- API key management
- Token-based auth vs other

### 8.2 Data Encryption
**Decision Required:** Encryption strategy

**Considerations:**
- Encryption at rest (event store)
- Encryption in transit (TLS)
- Sensitive data in events (PII, secrets)
- Key management system

### 8.3 Audit Logging
**Decision Required:** Security audit trail

**Questions to Answer:**
- What actions to audit?
- Separate audit stream or events?
- Retention requirements
- Compliance needs (GDPR, SOC2, etc.)

## 9. Deployment and Operations

### 9.1 Deployment Model
**Decision Required:** How to deploy the system

**Options:**
- Single monolithic service
- Microservices (separate services for LLM, tools, processing)
- Serverless (Lambda, Cloud Functions)
- Container-based (Kubernetes)
- Hybrid

### 9.2 Environment Configuration
**Decision Required:** Configuration management approach

**Questions to Answer:**
- Environment variables vs config files
- Secret management (API keys, credentials)
- Configuration validation
- Hot reloading support

### 9.3 Scaling Strategy
**Decision Required:** Horizontal vs vertical scaling approach

**Considerations (from spec 5.5):**
- Concurrent thread limits
- Event throughput requirements
- Processing latency targets
- Cost optimization

### 9.4 Backup and Disaster Recovery
**Decision Required:** Data protection strategy

**Questions to Answer:**
- Event store backup frequency
- Recovery point objective (RPO)
- Recovery time objective (RTO)
- Geographic redundancy

## 10. Event Schema Evolution

### 10.1 Schema Registry
**Decision Required:** How to manage event schemas over time (spec 5.4)

**Options:**
- Confluent Schema Registry
- Custom schema versioning system
- Git-based schema repository
- No formal registry

### 10.2 Compatibility Strategy
**Decision Required:** Forward/backward compatibility approach

**Options:**
- Strict compatibility (never break)
- Forward compatible (new readers can read old events)
- Backward compatible (old readers can read new events)
- No guarantees (version streams separately)

### 10.3 Migration Tools
**Decision Required:** Handling old event formats

**Questions to Answer:**
- In-place migration vs new streams?
- Automatic upcasting/downcasting?
- Migration validation and testing?

## 11. Performance Optimization

### 11.1 Snapshotting Strategy
**Decision Required:** How to avoid replaying entire history (spec 5.5)

**Options:**
- No snapshots (always replay)
- Periodic snapshots (every N events)
- On-demand snapshots
- Hybrid (snapshot for expensive projections only)

**Questions to Answer:**
- Snapshot storage location
- Snapshot format
- Snapshot versioning
- Invalidation strategy

### 11.2 Event Archival
**Decision Required:** Long-term event retention (spec 5.5)

**Questions to Answer:**
- Archive after N days/events?
- Archive storage (S3, Glacier, etc.)
- Archive format (compressed, raw)
- Restore process

### 11.3 Indexing Strategy
**Decision Required:** How to enable efficient queries (spec 5.5)

**Questions to Answer:**
- Index event types?
- Index metadata fields?
- Full-text search capability?
- Query patterns to optimize

### 11.4 Connection Pooling
**Decision Required:** Database connection management

**Questions to Answer:**
- Pool size
- Connection timeout
- Retry logic
- Health checks

## 12. Testing Strategy

### 12.1 Unit Testing Approach
**Decision Required:** Testing framework and patterns

**Components to Test:**
- Projection functions (pure functions, easy to test)
- Event serialization/deserialization
- Step selection logic
- Tool implementations

### 12.2 Integration Testing
**Decision Required:** Testing with real/mock dependencies

**Questions to Answer:**
- Mock LLM responses or use real API?
- Mock event store or use test instance?
- Test data management
- Fixture/factory patterns

### 12.3 Replay Testing
**Decision Required:** Testing with recorded event streams

**Approach:**
- Record production events (sanitized)
- Replay with different projection logic
- Validate outcomes

### 12.4 Performance Testing
**Decision Required:** Load and stress testing strategy

**Metrics:**
- Events per second throughput
- Latency percentiles (p50, p95, p99)
- Concurrent thread scaling
- Resource utilization

## 13. Human-in-the-Loop (Future)

### 13.1 Approval Mechanism
**Decision Required:** How to implement human approval (spec 5.1)

**Options:**
- Polling for approval events
- Webhook notifications
- Message queue for approval requests
- WebSocket for real-time coordination

### 13.2 Timeout Handling
**Decision Required:** What happens when human doesn't respond

**Questions to Answer:**
- Default timeout duration
- Timeout event type
- Automatic fallback action
- Notification escalation

## 14. Streaming Partial Results

### 14.1 Streaming Strategy
**Decision Required:** How to stream incremental results (spec 5.2)

**Options from Spec:**
- Fine-grained events (token-by-token)
- Separate ephemeral stream
- Coarse-grained events (final results only)
- Hybrid (stream to clients, record finals as events)

**Questions to Answer:**
- Client protocol (SSE, WebSocket, gRPC streaming)
- Buffering strategy
- Error handling during stream
- Consistency guarantees

## 15. Custom Extensions

### 15.1 Custom Event Types
**Decision Required:** API for user-defined events (spec 3.4.4)

**Questions to Answer:**
- Event type registration mechanism
- Schema validation for custom events
- Namespace/collision prevention
- Documentation generation

### 15.2 Custom Step Types
**Decision Required:** Plugin system for new step types (spec 3.4.3)

**Questions to Answer:**
- Step registration API
- Step lifecycle hooks
- Error handling contract
- Examples: approval steps, validation steps, external integration steps

### 15.3 Custom Projection API
**Decision Required:** User-defined projection functions (spec 3.4.1)

**Questions to Answer:**
- Function signature/contract
- Composition with built-in projections
- Testing utilities
- Performance guidelines

### 15.4 Custom Step Selection Logic
**Decision Required:** Customizable routing logic (spec 3.4.2)

**Questions to Answer:**
- Rules engine vs programmatic
- Default behavior vs override
- Composition of multiple routing rules
- Debugging/troubleshooting custom logic

## 16. Event Categories and Types

### 16.1 Event Type Taxonomy
**Decision Required:** Naming and organization of event types

**Categories from Spec:**
- User Events (UserMessageAdded, etc.)
- Agent Events (LLMCalled, etc.)
- Tool Events (ToolCalled, ToolExecuted, etc.)
- System Events (SessionTerminationRequested, etc.)
- Metadata Events (TimestampRecorded, etc.)

**Questions to Answer:**
- Exact event type names
- Event naming convention
- Event hierarchy/inheritance
- Required vs optional fields per type

### 16.2 Event Payload Standards
**Decision Required:** Common structure for event data

**Questions to Answer:**
- Envelope format
- Payload nesting strategy
- Null/optional field handling
- Size limits

## 17. Cost Management

### 17.1 Cost Tracking
**Decision Required:** How to monitor and control costs

**Cost Centers:**
- LLM API usage (tokens)
- Event store operations
- Tool executions (external APIs)
- Compute resources
- Storage

**Questions to Answer:**
- Cost attribution per thread/user
- Budget enforcement mechanism
- Cost reporting and alerts

### 17.2 Cost Optimization
**Decision Required:** Strategies to reduce operational costs

**Approaches:**
- LLM call caching
- Context compression
- Cheaper models for simple tasks
- Batch processing
- Reserved capacity

## Decision Tracking

For each decision made, document:
- **Decision:** What was decided
- **Date:** When decided
- **Rationale:** Why this choice
- **Alternatives Considered:** Other options evaluated
- **Trade-offs:** Pros and cons
- **Owner:** Who made/approved the decision
- **Status:** Proposed, Approved, Implemented, Deprecated

Use separate documentation (e.g., ADRs - Architecture Decision Records) or add sections below for tracking actual decisions made.

1. Event Store
1.1 [Message DB](https://github.com/message-db/message-db)
1.2 `agent:v0-{threadId}`
1.3 json
1.4 message-db metadata field empty for now
2. Processing Engine
2.1 Simple, explicit loop
2.2 Assume single writer per stream/thread, but use message-db expected version for OCC
2.3 Ignore idempotency in basic impl
2.4 Record failures as events, simple retry of certain failures
2.5 No limits/quotas for now in basic impl
3. LLM Integration
3.1 Use Google Vertex AI API, authenticated using ADC, with either gemini or claude models (configurable)
3.2 System prompt and messages with function declarations for tools
3.3 No compression for now
4. Tool Framework
4.1 Tools are python functions
4.2 In-process execution
4.3 No validation
4.4 None
5. Projection Framework
5.1 Pure functions
5.2 No caching
5.3 Default implementations, no customization yet
6. Programming Language
6.1 Python with type hints
6.2 uv
7. Observability and Monitoring
7.1 Structured logging
7.2 otel
7.3 none
7.4 none yet
8. Security
8.1 none
8.2 none
8.3 none
9. Deployment and Operations
9.1 Local process execution
9.2 env vars
9.3 none
9.4 none
10. Event Schema Evolution
10.1 none
10.2 Strict: evolved schema in different stream version
10.3 none
11. Performance Optimization
11.1 none
11.2 forever
11.3 rely on message-db
11.4 none
12. Testing Strategy
12.1 Unit tests for all pure functions
12.2 Integration tests against message-db in docker container
12.3 none
12.4 none
13-17. Ignore for now

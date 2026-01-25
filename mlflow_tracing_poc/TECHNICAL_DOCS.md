# MLflow Multi-Agent Tracing - Technical Documentation

## How the Solution Works

This document explains the core mechanisms used to solve both tracing challenges.

---

## Challenge 1: Nested Tracing Across Agents

### Problem

When the Supervisor Agent delegates to the Remote Superagent, the remote agent's spans need to appear as children of the Supervisor's delegation span.

### Solution: Trace Context Propagation

The solution uses **trace context propagation** through the A2A protocol:

1. **Context Creation**: When the Supervisor creates a span for delegation, it extracts the `trace_id` and `span_id`:

```python
# In supervisor_agent.py
with mlflow.start_span(name="delegate_to_remote_agent", ...) as delegate_span:
    # Create context for propagation
    trace_context = TraceContext(
        trace_id=delegate_span.request_id,
        span_id=delegate_span.span_id,
        request_id=str(uuid.uuid4()),
        session_id=session_id
    )
    
    # Pass context to remote agent
    response = self.a2a_client.execute_task(task_request, trace_context)
```

2. **Context Transmission**: The A2A client includes trace context in HTTP headers:

```python
# In a2a_protocol.py
headers.update(trace_context.to_headers())
# Results in headers like:
# X-MLflow-Trace-ID: abc123...
# X-MLflow-Span-ID: def456...
# X-Session-ID: ghi789...
```

3. **Context Reception**: The Remote Superagent extracts and uses the context:

```python
# In remote_superagent.py
trace_context = extract_trace_context_from_request(data, dict(request.headers))

# Create span with parent reference
with mlflow.start_span(
    name="RemoteSuperagent.search",
    attributes={
        "parent_trace_id": trace_context.trace_id,
        "parent_span_id": trace_context.span_id,
        ...
    }
) as agent_span:
    # Execute tools with nested spans
```

### Result

The Remote Superagent's spans include attributes linking them to the parent span, enabling trace viewers to display the proper hierarchy.

---

## Challenge 2: Single Trace for Multi-Turn Conversation

### Problem

The ADK runner creates a new trace for every execution, preventing a unified view of the conversation.

### Solution: Session-Based Trace Grouping

The solution uses **session ID-based grouping** with controlled trace creation:

1. **Disable Auto-Tracing**: First, we disable any automatic tracing:

```python
# In supervisor_agent.py
def _disable_auto_tracing(self):
    try:
        mlflow.autolog(disable=True)
    except Exception:
        pass
```

2. **Session Management**: Each conversation gets a unique session ID:

```python
# Create session at conversation start
session_id = supervisor.start_session()  # Returns UUID

# All turns use this session ID
response = supervisor.process_message(session_id, user_message)
```

3. **Consistent Session Attributes**: Every span includes the session ID:

```python
with mlflow.start_span(
    name=f"SupervisorAgent.process_turn_{turn_number}",
    attributes={
        "session_id": session_id,  # Same for all turns
        "turn_number": turn_number,
        ...
    }
) as root_span:
```

4. **Trace Grouping in MLflow**: Using MLflow's span grouping features, spans with the same session ID are logically grouped, enabling filtering and correlation in the MLflow UI.

### Alternative: True Single-Trace Approach

For stricter single-trace requirements, you can use the `SessionTraceManager`:

```python
# In mlflow_context.py
class SessionTraceManager:
    def get_or_create_session_trace(self, session_id: str):
        # Returns existing trace for session or creates new one
        # Stores trace_id for reuse across turns
```

---

## Key Components

### 1. TraceContext (mlflow_context.py)

Serializable context for cross-agent propagation:

```python
@dataclass
class TraceContext:
    trace_id: str      # Root trace identifier
    span_id: str       # Current span (parent for children)
    request_id: str    # Unique request ID
    session_id: str    # Conversation session ID
    
    def to_headers(self) -> Dict[str, str]: ...
    def from_headers(cls, headers) -> TraceContext: ...
```

### 2. A2AClient (a2a_protocol.py)

HTTP client with automatic context propagation:

```python
class A2AClient:
    def execute_task(self, task, trace_context):
        # Automatically includes trace context in request
        headers.update(trace_context.to_headers())
        message.trace_context = trace_context.to_dict()
```

### 3. SupervisorAgent (supervisor_agent.py)

Main orchestrator with tracing:

```python
class SupervisorAgent:
    def process_message(self, session_id, user_message):
        with mlflow.start_span(...) as root_span:
            context = TraceContext(...)  # Extract for propagation
            if needs_delegation:
                result = self._delegate_to_remote(message, context)
```

### 4. RemoteSuperagent (remote_superagent.py)

Flask server with nested span creation:

```python
@app.route("/execute")
def execute_task():
    trace_context = extract_trace_context_from_request(...)
    with mlflow.start_span(..., attributes={"parent_span_id": ...}):
        # Nested tool execution spans
```

---

## Bypassing ADK Auto-Tracing

If using a specific ADK that auto-traces, use these patterns:

### Pattern 1: Environment Variable Disable

```python
import os
os.environ["DISABLE_ADK_TRACING"] = "true"
```

### Pattern 2: Autolog Disable

```python
mlflow.autolog(disable=True)
```

### Pattern 3: Context Manager Override

```python
# Create your own tracing context before ADK execution
with mlflow.start_span("my_controlled_span"):
    # ADK execution here - spans become children of yours
    adk_runner.execute(...)
```

### Pattern 4: Trace Buffer Interception

For advanced cases, intercept the trace buffer:

```python
from mlflow.tracing.fluent import TRACE_BUFFER
# Access and modify trace behavior
```

---

## Verification Checklist

After running the demo, verify in MLflow UI:

- [ ] **Session Grouping**: All spans with same session_id are visible
- [ ] **Turn Numbers**: Each turn is numbered (turn_1, turn_2, turn_3)
- [ ] **Span Hierarchy**: Supervisor spans contain delegation spans
- [ ] **Remote Agent Spans**: RemoteSuperagent spans show parent_span_id
- [ ] **Tool Spans**: Tool execution spans are nested under agent spans
- [ ] **Attributes**: All spans have session_id, agent_name, etc.

---

## Extending the Solution

### Adding New Agents

1. Create agent class following `RemoteSuperagent` pattern
2. Use `extract_trace_context_from_request()` for incoming calls
3. Include trace context in all spans
4. Pass context to any downstream calls

### Adding New Tools

1. Add tool function to `DummyToolkit` class
2. Register in `RemoteSuperagent.tools` dictionary
3. Wrap execution with `mlflow.start_span(span_type=SpanType.TOOL)`

### Custom Span Types

MLflow supports these span types:
- `SpanType.AGENT` - For agent operations
- `SpanType.CHAIN` - For chained operations
- `SpanType.TOOL` - For tool executions
- `SpanType.LLM` - For LLM calls
- `SpanType.RETRIEVER` - For retrieval operations

---

## Troubleshooting

### Traces Not Appearing

1. Check MLflow tracking URI is correct
2. Ensure experiment exists: `mlflow.set_experiment("...")`
3. Verify no exceptions in span context managers

### Spans Not Nested

1. Verify trace context is being passed in A2A calls
2. Check `parent_span_id` attribute in remote spans
3. Ensure same session_id across all related spans

### Remote Agent Connection Failed

1. Check Remote Superagent is running on port 5001
2. Verify no firewall blocking localhost connections
3. Test health endpoint: `curl http://localhost:5001/health`

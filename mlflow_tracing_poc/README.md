# MLflow Multi-Agent Tracing — Deliverable (Single Trace)

> Note: The final deliverable is in `single_trace/`.

## Overview

This Proof of Concept (PoC) demonstrates a robust MLflow-based tracing solution for a multi-turn, multi-agent system. It directly addresses two core challenges:

1. **Challenge 1: Nested Tracing Across Agents** - Remote agent spans are correctly nested under the Supervisor Agent's spans
2. **Challenge 2: Single Trace for Multi-Turn Conversation** - All conversation turns are captured with proper grouping

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           MLflow Tracking Server                         │
│                              (localhost:5000)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │ Traces
                                      │
┌─────────────────────────────────────┴───────────────────────────────────┐
│                                                                          │
│  ┌───────────────────────────────┐      A2A Protocol     ┌─────────────────────────────────┐
│  │      Supervisor Agent         │ ─────────────────────>│      Remote Superagent          │
│  │       (Local Agent)           │   + Trace Context     │     (Flask Server :5001)        │
│  │                               │<───────────────────── │                                 │
│  │  • Receives user messages     │      Response         │  • Receives delegated tasks     │
│  │  • Creates root trace spans   │                       │  • Creates nested child spans   │
│  │  • Manages session lifecycle  │                       │  • Executes dummy tools         │
│  │  • Propagates trace context   │                       │  • Returns traced results       │
│  └───────────────────────────────┘                       └─────────────────────────────────┘
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```


## ▶️ How to run the demo 

1. Start remote agent (in `single-trace` folder):

```bash
python remote_agent.py
```

2. Run supervisor demo (same `single-trace` folder):

```bash
python supervisor_agent.py
```

3. Verify traces (option A - quick script):

```bash
python verify.py
```

4. View traces in MLflow UI (from `single-trace` folder):

```bash
mlflow ui --port 5002
# then open http://localhost:5002
```

## ▶️ Demo with Postman ✅

You can demo the supervisor endpoint using Postman (or curl):

1. Start the remote agent:

```bash
python single_trace/remote_agent.py
```

2. Start the supervisor server (default mode is HTTP server):

```bash
python single_trace/supervisor_agent.py
```

3. In Postman, create a POST request to `http://localhost:5000/ask` with headers:

- `Content-Type: application/json`

Body (raw JSON):

```json
{
  "question": "Search for Python machine learning libraries",
  "session_id": "optional-session-123"
}
```

4. The response JSON will include `session_id`, `turn_number`, `trace_id`, and `response`. To end a session you can either POST JSON or use a GET query string. Examples:

POST (body JSON):
```json
{ "session_id": "optional-session-123" }
```

GET with query parameter:

```
GET http://localhost:5000/end_session?session_id=optional-session-123
```

Note: If you see errors like "Missing parameter name" from your client, ensure you use a full URL including the protocol (e.g. `http://localhost:5000/end_session`) and do not feed the full URL into a router path field that expects only a path. If you're using Postman, put the full URL in the request URL field and use the method `POST` or `GET` as shown.
You can also run the CLI demo (multi-turn scripted demo) with:

```bash
python single_trace/supervisor_agent.py --demo
```

> Note: Demo currently writes traces to `./mlruns` (file backend). You can switch to a database by updating `mlflow.set_tracking_uri(...)`.

---

## Verification checks performed

- Single trace exists for the session (`trace_info` / `trace_id`).
- All spans belong to the same trace.
- Turn spans are direct children of the session root span.
- Remote work spans (e.g. `remote_web_search`) are children of `delegate_to_remote`.

You can run `verify.py` to reproduce the verification results (script prints a hierarchical tree and pass/fail checks).

---

## 🛠 Troubleshooting

- No traces in `mlruns/`? Check `mlflow.set_tracking_uri(...)` — if it points to `sqlite:///...` traces are stored in the DB instead.
- Remote agent debug: Hit `GET /health` on port `5001` to ensure remote agent is up.
- If you see multiple traces per session, ensure the session root span remains open across turns and that you use `parent_span=<LiveSpan>` when creating turn spans.

---

## Tips & Next Steps

- Consider exporting traces to a central tracing system for long-term storage and searchability.
- If you want remote agents to own their own spans (instead of supervisor logging them), implement a shared backend or use `TracingClient.log_spans()` with properly constructed OTel spans; this is more complex but possible.
- Add unit tests for `verify.py` checks.

---

## References

- MLflow tracing: `start_span_no_context()` and `LiveSpan` APIs
- W3C Trace Context (`traceparent`) format used for propagation

---

If you want, I can add this file to the project root or update existing README files to link to it. ✅

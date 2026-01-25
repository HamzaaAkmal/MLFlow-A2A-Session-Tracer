# Single-Trace Multi-Turn Tracing (MLflow)

> Folder: `single_trace/` — Simplified, deliverable-ready implementation.

This folder contains the final deliverable: the supervisor and remote agent scripts, session tracing utilities, a verification script, and a README describing how to run and verify the single-trace behavior.

🎯 **Goal**

- Ensure a single MLflow trace contains an entire multi-turn conversation and that remote agent operations are nested as child spans under the supervisor spans.

---

## ✅ Summary (What we accomplished)

- **Single trace per session:** All conversation turns and remote operations are recorded under a single MLflow trace.
- **Correct nesting:** `session -> turn -> delegate_to_remote -> remote_*` span hierarchy.
- **Approach:** Supervisor creates and manages session root span and turn spans using `mlflow.start_span_no_context(..., parent_span=...)`. Remote agent returns a work log (no direct spans) and the supervisor logs child spans describing remote work.

---

## 🔧 Key Design Choices

- Use `mlflow.start_span_no_context()` to create spans without attaching to global context and explicitly set `parent_span` to control relationships.
- Supervisor is the single trace owner: it creates the session root span and all child spans for turns and remote work. This avoids distributed span creation inconsistencies.
- Remote agent returns a `work_log` describing operations (operation name, duration, input/output). The supervisor converts these into child spans.

---

## 📁 Important Files

- `session_trace.py` — Core trace/session management and helpers for creating child spans and propagation headers.
- `supervisor_agent_v4.py` — Supervisor agent implementation and demo runner (creates session root, per-turn spans, logs remote work spans).
- `remote_agent_v4.py` — Remote agent; executes tasks and returns structured `work_log` (no direct spans).
- `verify_v4.py` — Verification script that inspects the MLflow backend and checks single-trace and nesting properties.
- `mlruns/` (or DB) — Where MLflow stores trace artifacts. V4 demo defaults to `file:./mlruns`.

---

## 📘 How it works (high level)

1. Supervisor calls `trace_manager.get_or_create_session(session_id)` → creates a session root span (kept open until session ends).
2. For each turn: Supervisor creates a turn span with `parent_span=session_root` using `start_span_no_context`.
3. Inside the turn, supervisor creates child spans (analysis, delegate_to_remote, synthesize_response) with `parent_span=turn_span`.
4. For remote work: Supervisor POSTs to remote `/execute` with trace headers (traceparent, X-Session-ID, X-Parent-Span-ID).
5. Remote agent performs tools and returns `work_log` describing operations. Supervisor iterates `work_log` and creates child spans (e.g. `remote_web_search`) under `delegate_to_remote`.
6. End session: Supervisor ends the session root span which finalizes the trace artifact.

---

## ▶️ How to run the demo (V4)

1. Start remote agent (in `v4` folder):

```bash
python remote_agent_v4.py
```

2. Run supervisor demo (same `v4` folder):

```bash
python supervisor_agent_v4.py
```

3. Verify traces (option A - quick script):

```bash
python verify_v4.py
```

4. View traces in MLflow UI (from `v4` folder):

```bash
mlflow ui --port 5002
# then open http://localhost:5002
```

> Note: Demo currently writes traces to `./mlruns` (file backend). You can switch to a database by updating `mlflow.set_tracking_uri(...)`.

---

## ✅ Verification checks performed

- Single trace exists for the session (`trace_info` / `trace_id`).
- All spans belong to the same trace.
- Turn spans are direct children of the session root span.
- Remote work spans (e.g. `remote_web_search`) are children of `delegate_to_remote`.

You can run `verify_v4.py` to reproduce the verification results (script prints a hierarchical tree and pass/fail checks).

---

## 🛠 Troubleshooting

- No traces in `mlruns/`? Check `mlflow.set_tracking_uri(...)` — if it points to `sqlite:///...` traces are stored in the DB instead.
- Remote agent debug: Hit `GET /health` on port `5001` to ensure remote agent is up.
- If you see multiple traces per session, ensure the session root span remains open across turns and that you use `parent_span=<LiveSpan>` when creating turn spans.

---

## 💡 Tips & Next Steps

- Consider exporting traces to a central tracing system for long-term storage and searchability.
- If you want remote agents to own their own spans (instead of supervisor logging them), implement a shared backend or use `TracingClient.log_spans()` with properly constructed OTel spans; this is more complex but possible.
- Add unit tests for `verify_v4.py` checks.

---

## References

- MLflow tracing: `start_span_no_context()` and `LiveSpan` APIs
- W3C Trace Context (`traceparent`) format used for propagation

---

If you want, I can add this file to the project root or update existing README files to link to it. ✅

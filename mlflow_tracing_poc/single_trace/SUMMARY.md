# Tracing Methods — What Worked / What Didn't

**Purpose:** concise record of all tracing approaches tried (V1→final), results, root causes, and recommendations.

---

## Quick Summary ✅/❌

| Version | Approach | Result |
|---|---|---|
| V1 | Basic MLflow spans (each process starts spans) | ❌ Remote spans in separate traces (no nesting) |
| V2 | OpenTelemetry W3C traceparent propagation | ❌ Propagated headers arrived, but `mlflow.start_span` did not attach to propagated OTel context → still separate traces |
| V3 | Supervisor *creates* remote-work spans (remote returns work_log) but used `start_span` per turn | ❌ Remote work nested correctly under delegate, but each turn created a separate trace (multiple traces) |
| Final | Use `mlflow.start_span_no_context(..., parent_span=...)` with a root session span kept open + remote returns work_log | ✅ SUCCESS — Single trace per session; proper nesting; verified with `verify.py` |

---

## Detailed Findings

### V1 — Baseline
- What: Naive use of `mlflow.start_span()` in both supervisor and remote agents.
- Why it failed: When used at top-level, `start_span()` creates a root span and logs the whole trace on end. Remote process created its own root independent trace.
- Result: Separate traces for remote agent work.

### V2 — Tried OpenTelemetry propagation
- What: Sent `traceparent` headers using `TraceContextTextMapPropagator` and attached OTel context on remote side.
- Why it failed: MLflow's `start_span()` does not pick up an external OTel context automatically (MLflow created new trace IDs anyway).
- Result: Trace propagation headers were present but MLflow spans were not nested under the supervisor spans.

### V3 — Supervisor logs remote work (work_log) but per-turn traces
- What: Supervisor created spans for remote work (using remote work_log), but used ordinary `mlflow.start_span()` for turns.
- Why it failed: Each turn's `start_span()` started a new root trace; session-level single-trace invariant not preserved.
- Partial win: Remote work became nested under the supervisor delegate span, but across turns traces were multiple.

### Final working solution
- What: Create a persistent session root span using `mlflow.start_span_no_context(...)` and keep it open until session end. For each turn, create a child span via `start_span_no_context(..., parent_span=root_span)`. Remote agent returns a structured `work_log` and the supervisor creates child spans for those operations under the `delegate_to_remote` span.
- Why it works: `start_span_no_context` accepts a `parent_span` parameter (a `LiveSpan`) so the supervisor explicitly controls parent-child relationships and keeps a single session trace alive across multiple turns.
- Verification: `verify.py` checks there is 1 trace, turn spans are children of session root, remote work spans are children of `delegate_to_remote`. Confirmed ✅

---

## Root Causes (Short)
- MLflow's default `start_span()` will create root traces when no active span exists in the process context (causing multiple traces if session root isn't preserved).
- OpenTelemetry propagation (traceparent header) alone does not guarantee MLflow will create child spans in a separate process—MLflow's `start_span` needs explicit parent control or special import of OTel ReadableSpan.

---

## Files & Commands (where to look & how to run)
- Key files:
  - `v4/session_trace.py` (session root span management) ✅
  - `v4/supervisor_agent_v4.py` (supervisor demo & logic) ✅
  - `v4/remote_agent_v4.py` (remote work_log responder) ✅
  - `v4/verify_v4.py` (verification script) ✅
  - `v4/README_V4.md` (explain how to run) ✅

- Quick demo commands:
  - Start remote agent: `python remote_agent_v4.py` (port 5001)
  - Run supervisor demo: `python supervisor_agent_v4.py`
  - Verify: `python verify_v4.py`
  - View in MLflow UI: `mlflow ui --port 5002` (open http://localhost:5002 → experiment `v4_single_trace_demo`)

---

## Recommendations & Next Steps
- If you want remote agents to *own* spans, consider creating OTel ReadableSpan objects and use `TracingClient.log_spans()` (advanced). Otherwise, the current V4 pattern is reliable and simpler: supervisor owns trace and logs remote work spans based on the remote `work_log`.
- Add tests for `verify_v4.py` and CI checks to ensure future refactors don't regress single-trace property.
- Optionally switch to a DB backend (sqlite/postgres) for production traces instead of `mlruns` filesystem (mlflow.set_tracking_uri).

---

## TL;DR
- V4 is the correct solution: keep a session root span, create turn spans as its children using `start_span_no_context(parent_span=...)`, and log remote work as child spans using the remote `work_log`. All verification checks pass.

---

If you want, I can add this file to the repository root or link it from `README.md` (quick change). Which do you prefer?
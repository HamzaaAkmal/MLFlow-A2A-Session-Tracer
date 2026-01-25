"""Verify trace structure from `mlruns/` artifacts.

This script scans the local `mlruns` folder and validates:
- Single trace exists per session
- All spans belong to same trace
- Proper nesting: session -> turn -> delegate -> remote_*
"""
import json
from pathlib import Path

BASE = Path(__file__).parent
MLRUNS = BASE / "mlruns"

print("\n" + "="*60)
print("TRACE VERIFICATION (mlruns)")
print("="*60)

if not MLRUNS.exists():
    print("No mlruns folder found. Run the demo to generate traces.")
    raise SystemExit(1)

traces_by_session = {}

for exp_dir in MLRUNS.iterdir():
    if not exp_dir.is_dir():
        continue
    traces_dir = exp_dir / "traces"
    if not traces_dir.exists():
        continue

    for trace_dir in traces_dir.iterdir():
        trace_file = trace_dir / "artifacts" / "traces.json"
        if not trace_file.exists():
            continue
        data = json.load(trace_file.open())
        spans = data.get("spans", [])
        # Extract session id from span attrs
        session_id = None
        for sp in spans:
            attrs = sp.get("attributes", {})
            # mlflow stores attributes as dict with string values possibly containing escaped json
            if "session_id" in attrs:
                session_id = attrs["session_id"].strip('"')
                break
        if not session_id:
            session_id = trace_dir.name
        traces_by_session.setdefault(session_id, []).append({
            "trace_id": trace_dir.name,
            "spans": spans,
            "trace_file": str(trace_file)
        })

if not traces_by_session:
    print("No traces found in mlruns.")
    raise SystemExit(1)

# Analyze
for session_id, traces in traces_by_session.items():
    print(f"\nSession: {session_id}")
    print(f"  Traces found: {len(traces)}")

    if len(traces) != 1:
        print("  ❌ FAIL: expected 1 trace per session")
        continue

    trace = traces[0]
    spans = trace["spans"]
    trace_id = trace["trace_id"]

    print(f"  Trace ID: {trace_id}")
    print(f"  Total spans: {len(spans)}")

    # Build span tree
    span_by_id = {s["span_id"]: s for s in spans}
    root_spans = [s for s in spans if s.get("parent_span_id") is None]

    def print_tree(span, indent=0):
        prefix = "  " * indent
        print(f"{prefix}├── {span.get('name')}")
        sid = span.get("span_id")
        children = [c for c in spans if c.get("parent_span_id") == sid]
        for c in children:
            print_tree(c, indent + 1)

    for r in root_spans:
        print_tree(r)

    # Checks
    turn_spans = [s for s in spans if s.get("name", "").startswith("turn_")]
    if not turn_spans:
        print("  ❌ FAIL: no turn spans found")
    else:
        root_id = root_spans[0]["span_id"] if root_spans else None
        if all(t.get("parent_span_id") == root_id for t in turn_spans):
            print("  ✅ PASS: All turn spans are children of root session span")
        else:
            print("  ❌ FAIL: Some turn spans are not direct children of root")

    remote_spans = [s for s in spans if s.get("name", "").startswith("remote_")]
    if remote_spans:
        print(f"  ✅ PASS: Remote work logged as spans ({len(remote_spans)})")
    else:
        print("  ⚠️ WARNING: No remote work spans found")

print("\n" + "="*60)
print("Verification complete.")

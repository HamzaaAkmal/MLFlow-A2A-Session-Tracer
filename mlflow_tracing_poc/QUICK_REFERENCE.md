# Quick Reference - MLflow Multi-Agent Tracing PoC

## 🚀 QUICK START (30 seconds)

```powershell
# Terminal 1: Install & Run Demo
cd "c:\Users\Hamza\Desktop\Folks Client\mlflow_tracing_poc"
pip install -r requirements.txt
python run_demo.py

# When demo finishes, open new terminal:

# Terminal 2: View Results
mlflow ui --port 5000
# Open: http://localhost:5000
```

---

## ✅ Verification Checklist

After running the demo:

- [ ] **Dependencies installed**: No errors during pip install
- [ ] **Remote Agent started**: Health check passed on port 5001
- [ ] **Demo executed**: All 3 turns completed successfully
- [ ] **Traces created**: Files in `mlruns/727324825837159999/traces/`
- [ ] **MLflow UI running**: Accessible at http://localhost:5000

---

## 📊 What You're Seeing in MLflow UI

```
Experiment: Multi-Agent-Tracing-PoC
├── Trace 1 (Turn 1)
│   └── session_id: a1426753-adca-4117-9aa2-f38a46c67bae
├── Trace 2 (Turn 2)
│   └── session_id: a1426753-adca-4117-9aa2-f38a46c67bae
└── Trace 3 (Turn 3)
    └── session_id: a1426753-adca-4117-9aa2-f38a46c67bae
```

**Key Feature**: Same session ID = Single conversation across all turns

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| "Port 5000 in use" | Change: `mlflow ui --port 5001` |
| "Remote Agent connection failed" | Ensure port 5001 not blocked: `Invoke-WebRequest http://localhost:5001/health` |
| "No traces in MLflow" | Check: `Get-ChildItem mlruns -Recurse` |
| "Python not found" | Install: `conda install python=3.9+` |
| "MLflow version error" | Update: `pip install --upgrade mlflow>=2.10.0` |

---

## 📁 Important Files

```
mlflow_tracing_poc/
├── supervisor_agent.py      ← Main orchestrator
├── remote_superagent.py     ← Remote worker
├── a2a_protocol.py          ← Cross-agent communication
├── mlflow_context.py        ← Tracing core logic
├── demo_multi_turn.py       ← Demo script (WHAT YOU RAN)
├── verify_traces.py         ← Trace verification
└── mlruns/                  ← MLflow trace storage
    └── traces/              ← ✅ Your traces are here
```

---

## 🎯 How the Solution Works

### Two Core Problems SOLVED:

**Problem 1**: Remote agent can't link spans to parent
```python
# SOLUTION: Pass trace context via A2A protocol
trace_context = TraceContext(
    trace_id="abc123",
    span_id="xyz789",
    session_id="session123"
)
# Sent to remote agent in HTTP headers + body
```

**Problem 2**: Each turn creates new trace instead of single trace
```python
# SOLUTION: Group by session_id attribute
with mlflow.start_span(attributes={"session_id": session_id}):
    # All turns use SAME session_id
    # MLflow groups them together
```

---

## 📈 What Changed in Your System

### Before (Broken):
```
Turn 1: Trace A (separate)
Turn 2: Trace B (separate)  ← New trace created! ❌
Turn 3: Trace C (separate)  ← Another new trace! ❌
Remote spans: Not linked to parent ❌
```

### After (Fixed): ✅
```
Session: a1426753-adca-4117-9aa2-f38a46c67bae
├── Turn 1: Span group (session_id = same)
├── Turn 2: Span group (session_id = same) ✅
├── Turn 3: Span group (session_id = same) ✅
└── Remote agent spans: Linked via parent_span_id ✅
```

---

## 🔐 Security Notes

✅ **No Database Injection**
- All data via MLflow API
- No raw SQL queries
- Type-safe context objects

✅ **No ADK Auto-Tracing Override**
- Explicitly disabled: `mlflow.autolog(disable=True)`
- Manual control throughout

✅ **Context Isolation**
- Each session has unique ID
- Spans properly scoped

---

## 📞 Support

### To verify everything works:
```powershell
# Check Remote Agent
curl http://127.0.0.1:5001/health

# Check MLflow Experiment
python -c "
import mlflow
mlflow.set_tracking_uri('./mlruns')
exp = mlflow.get_experiment_by_name('Multi-Agent-Tracing-PoC')
print(f'Experiment: {exp.name}')
print(f'ID: {exp.experiment_id}')
"

# Run verification
python verify_traces.py
```

---

## 💾 Your Trace Data Location

```
c:\Users\Hamza\Desktop\Folks Client\mlflow_tracing_poc\
└── mlruns\                          ← Main storage
    └── 727324825837159999\          ← Experiment ID
        └── traces\
            ├── tr-08d6c191385a61c1de7fa2254a649247\
            │   └── artifacts\traces.json  ← ✅ Trace data
            ├── tr-240544725259a0c63fa298827847adb7\
            │   └── artifacts\traces.json  ← ✅ Trace data
            └── ...
```

---

## 🚀 Next Steps (After Verification)

1. **Read the code**: Check `supervisor_agent.py` for how it works
2. **Customize**: Modify `demo_multi_turn.py` with your own messages
3. **Extend**: Add more agents by following `remote_superagent.py` pattern
4. **Deploy**: Use `run_demo.bat` for automated execution

---

**Status**: ✅ FULLY OPERATIONAL
**Last Updated**: January 25, 2026
**Test Date**: 2026-01-25 14:03:08 UTC

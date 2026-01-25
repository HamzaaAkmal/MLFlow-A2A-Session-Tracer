# MLflow Multi-Agent Tracing - Proof of Concept

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

## Project Structure

```
mlflow_tracing_poc/
├── README.md                   # This file
├── requirements.txt            # Python dependencies
├── config.py                   # Configuration settings
├── mlflow_context.py           # Core tracing utilities (Challenge 1 & 2)
├── enhanced_tracing.py         # Enhanced tracing with decorators
├── a2a_protocol.py             # Agent-to-Agent communication protocol
├── supervisor_agent.py         # Local Supervisor Agent
├── remote_superagent.py        # Remote Superagent (Flask server)
├── demo_multi_turn.py          # Multi-turn conversation demo
└── run_demo.py                 # Main entry point (runs everything)
```

---

## Quick Start Guide

### Prerequisites

- Python 3.9 or higher
- pip (Python package manager)

### Step 1: Install Dependencies

Open a terminal in the `mlflow_tracing_poc` directory:

```powershell
cd "c:\Users\Hamza\Desktop\Folks Client\mlflow_tracing_poc"
pip install -r requirements.txt
```

### Step 2: Run the Demo (Automated)

The easiest way to run the demo is using the automated script:

```powershell
python run_demo.py
```

This will:
1. Start the Remote Superagent on port 5001
2. Run a 3-turn conversation demo
3. Generate MLflow traces
4. Clean up when done

### Step 3: View Results in MLflow UI

After running the demo, start the MLflow UI:

```powershell
mlflow ui --port 5000
```

Open your browser to: **http://localhost:5000**

Navigate to the experiment: **Multi-Agent-Tracing-PoC**

---

## Manual Step-by-Step Guide

For more control, you can run each component separately:

### Terminal 1: Start the Remote Superagent

```powershell
cd "c:\Users\Hamza\Desktop\Folks Client\mlflow_tracing_poc"
python remote_superagent.py
```

You should see:
```
INFO - Starting Remote Superagent on 127.0.0.1:5001
 * Running on http://127.0.0.1:5001
```

### Terminal 2: Run the Demo

```powershell
cd "c:\Users\Hamza\Desktop\Folks Client\mlflow_tracing_poc"
python demo_multi_turn.py
```

### Terminal 3: Start MLflow UI

```powershell
cd "c:\Users\Hamza\Desktop\Folks Client\mlflow_tracing_poc"
mlflow ui --port 5000
```

---

## Expected Output

### Console Output

The demo will produce output like:

```
======================================================================
  MLflow Multi-Agent Tracing Demo
======================================================================

This demo will simulate a 3-turn conversation to demonstrate:
  1. Single trace for entire multi-turn conversation
  2. Nested spans from Remote Superagent

======================================================================
  Turn 1: Search request - will be delegated to Remote Superagent
======================================================================

User: Can you search for information about machine learning frameworks?
"""
Supervisor Agent - Single-Trace Multi-Turn Solution
===================================================

Uses `start_span_no_context` with `parent_span` to ensure:
1. All turns are children of the session root span
2. All child operations are properly nested
3. Remote agent work is logged as child spans

This achieves a single trace per session with correct nesting.
"""

import time
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

import mlflow
from mlflow.entities import SpanType

from session_trace import (
    trace_manager,
    turn_span,
    child_span_of,
    get_propagation_headers,
    SessionTrace
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure MLflow - using file-based storage (mlruns folder)
mlflow.set_tracking_uri("file:./mlruns")
mlflow.set_experiment("single_trace_demo")


class SupervisorAgent:
    """
    Supervisor agent with single-trace multi-turn capability.

    Key features:
    - One trace per session (all turns in same trace)
    - Proper span nesting (turn -> operations -> remote work)
    - Remote agent work logged as child spans
    """
    
    def __init__(self, remote_agent_url: str = "http://localhost:5001"):
        self.remote_agent_url = remote_agent_url
        self.name = "SupervisorAgent"
    
    def process_turn(
        self,
        session_id: str,
        user_message: str
    ) -> Dict[str, Any]:
        """
        Process a conversation turn.
        
        All spans created here are children of the session's root span,
        ensuring everything ends up in ONE trace.
        """
        with turn_span(session_id, user_message) as (turn, session):
            logger.info(f"Processing turn {session.turn_count} in trace {session.request_id}")
            
            # Step 1: Analyze the request
            with child_span_of(turn, "analyze_request", SpanType.CHAIN) as analyze:
                analysis = self._analyze_request(user_message)
                analyze.set_inputs({"message": user_message})
                analyze.set_outputs(analysis)
            
            # Step 2: Delegate to remote agent
            with child_span_of(turn, "delegate_to_remote", SpanType.AGENT, 
                             {"remote_agent": "RemoteSuperagent"}) as delegate:
                delegate.set_inputs({
                    "query": user_message,
                    "task_type": analysis.get("task_type", "general")
                })
                
                # Get propagation headers
                headers = get_propagation_headers(session, delegate)
                
                # Call remote agent
                remote_result = self._call_remote_agent(
                    query=user_message,
                    task_type=analysis.get("task_type", "general"),
                    headers=headers
                )
                
                delegate.set_outputs(remote_result)
                
                # Log remote work as child spans
                self._log_remote_work(delegate, remote_result)
            
            # Step 3: Synthesize response
            with child_span_of(turn, "synthesize_response", SpanType.CHAIN) as synth:
                response = self._synthesize_response(remote_result)
                synth.set_inputs({"remote_result": remote_result})
                synth.set_outputs({"response": response})
            
            # Set turn outputs
            result = {
                "turn_number": session.turn_count,
                "session_id": session_id,
                "trace_id": session.request_id,
                "response": response
            }
            turn.set_outputs(result)
            
            return result
    
    def _analyze_request(self, message: str) -> Dict[str, Any]:
        """Analyze user request to determine task type."""
        message_lower = message.lower()
        
        if "search" in message_lower or "find" in message_lower:
            task_type = "search"
        elif "analyze" in message_lower:
            task_type = "analyze"
        else:
            task_type = "general"
        
        return {
            "task_type": task_type,
            "complexity": "medium",
            "requires_remote": True
        }
    
    def _call_remote_agent(
        self,
        query: str,
        task_type: str,
        headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """Call remote agent with trace context propagation."""
        try:
            response = requests.post(
                f"{self.remote_agent_url}/execute",
                json={
                    "task_id": f"task_{int(time.time())}",
                    "sender": self.name,
                    "content": query,
                    "metadata": {"task_type": task_type}
                },
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Remote agent error: {e}")
            return {"error": str(e), "work_log": []}
    
    def _log_remote_work(self, parent_span, remote_result: Dict[str, Any]):
        """
        Log remote agent's work as child spans.
        
        The remote agent returns a work_log describing what it did,
        and we create child spans for each operation.
        """
        work_log = remote_result.get("work_log", [])
        
        for work_item in work_log:
            operation = work_item.get("operation", "unknown")
            work_type = work_item.get("type", "CHAIN")
            
            # Map type string to SpanType
            type_map = {
                "TOOL": SpanType.TOOL,
                "CHAIN": SpanType.CHAIN,
                "LLM": SpanType.LLM,
                "AGENT": SpanType.AGENT
            }
            span_type = type_map.get(work_type, SpanType.CHAIN)
            
            with child_span_of(
                parent_span,
                f"remote_{operation}",
                span_type,
                {
                    "agent": "RemoteSuperagent",
                    "duration_ms": work_item.get("duration_ms", 0)
                }
            ) as work_span:
                work_span.set_inputs(work_item.get("input", {}))
                work_span.set_outputs(work_item.get("output", {}))
    
    def _synthesize_response(self, remote_result: Dict[str, Any]) -> str:
        """Synthesize final response from remote results."""
        if "error" in remote_result:
            return f"I encountered an issue: {remote_result['error']}"
        
        result = remote_result.get("result", {})
        return f"Based on my analysis: {result}"
    
    def end_session(self, session_id: str):
        """End a conversation session and finalize its trace."""
        trace_manager.end_session(session_id)
        logger.info(f"Session {session_id} ended")


def demo():
    """Run a demo of the single-trace solution."""
    print("\n" + "="*70)
    print("SINGLE-TRACE MULTI-TURN DEMO")
    print("="*70)
    print("\nThis demo demonstrates:")
    print("  1. ALL turns in ONE trace (same trace_id)")
    print("  2. Proper span nesting: session -> turn -> operations")
    print("  3. Remote work logged as child spans")
    print()
    
    supervisor = SupervisorAgent()
    session_id = f"session_{int(time.time())}"
    
    # Multi-turn conversation
    turns = [
        "Search for Python machine learning libraries",
        "Analyze the key features of scikit-learn",
        "Find resources about neural networks"
    ]
    
    print(f"Session: {session_id}")
    print("="*70)
    
    trace_ids = []
    
    for i, user_input in enumerate(turns, 1):
        print(f"\n--- Turn {i} ---")
        print(f"User: {user_input}")
        
        result = supervisor.process_turn(session_id, user_input)
        trace_ids.append(result["trace_id"])
        
        print(f"Agent: {result['response'][:100]}...")
        print(f"Trace ID: {result['trace_id']}")
        
        time.sleep(0.3)
    
    # End the session
    supervisor.end_session(session_id)
    
    print("\n" + "="*70)
    print("VERIFICATION")
    print("="*70)
    
    # Verify all turns used the same trace
    unique_traces = set(trace_ids)
    
    if len(unique_traces) == 1:
        print(f"✅ SUCCESS: All {len(turns)} turns are in ONE trace!")
        print(f"   Trace ID: {trace_ids[0]}")
    else:
        print(f"❌ FAILED: Found {len(unique_traces)} different traces")
        for tid in unique_traces:
            print(f"   - {tid}")
    
    print("\nRun 'mlflow ui --port 5002' from the `single_trace` folder and open http://localhost:5002")
    print("="*70 + "\n")
    
    return len(unique_traces) == 1


if __name__ == "__main__":
    demo()

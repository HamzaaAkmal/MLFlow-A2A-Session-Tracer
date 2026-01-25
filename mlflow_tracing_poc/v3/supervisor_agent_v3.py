"""
Supervisor Agent V3 - TRUE Single Trace Solution
================================================

The key insight: The SUPERVISOR creates ALL spans.
When calling remote agents, the supervisor:
1. Creates a span for "delegate_to_remote"
2. Calls the remote agent (which does work but returns span metadata)
3. Creates child spans within its own trace to represent remote work

This ensures ALL spans are in ONE trace because they're all
created in the same process/trace context.
"""

import time
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

import mlflow
from mlflow.entities import SpanType

from single_trace import (
    SingleTraceContext,
    supervisor_span,
    child_span,
    session_store,
    generate_span_id
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure MLflow
mlflow.set_tracking_uri("file:./mlruns")
mlflow.set_experiment("v3_single_trace_demo")


@dataclass
class A2AMessage:
    """A2A protocol message."""
    task_id: str
    sender: str
    content: str
    metadata: Dict[str, Any] = None


class SupervisorAgentV3:
    """
    Supervisor agent that creates ALL spans in a single trace.
    
    This is the CORRECT approach for MLflow distributed tracing:
    - All spans are created by the supervisor
    - Remote agent work is represented as child spans
    - Remote agents return metadata that the supervisor logs
    """
    
    def __init__(self, remote_agent_url: str = "http://localhost:5001"):
        self.remote_agent_url = remote_agent_url
        self.name = "SupervisorAgent"
        self.tools = {
            "local_summarize": self._local_summarize,
            "local_format": self._local_format
        }
    
    def process_turn(
        self,
        session_id: str,
        user_message: str
    ) -> Dict[str, Any]:
        """
        Process a single turn in the conversation.
        
        All spans for this turn (including remote agent work)
        are created in the same trace.
        """
        with supervisor_span(
            session_id=session_id,
            name="process_turn",
            agent_name=self.name
        ) as (turn_span, trace_ctx):
            
            # Update session info in context
            trace_ctx.session_id = session_id
            
            logger.info(f"Processing turn {trace_ctx.turn_number} for session {session_id}")
            logger.info(f"Using trace_id from span: {trace_ctx.trace_id}")
            
            # Record the user message
            turn_span.set_inputs({"user_message": user_message})
            turn_span.set_attribute("session_id", session_id)
            
            # Step 1: Analyze the request
            with child_span("analyze_request", SpanType.CHAIN) as analyze_span:
                analysis = self._analyze_request(user_message)
                analyze_span.set_inputs({"message": user_message})
                analyze_span.set_outputs(analysis)
                
            # Step 2: Delegate to remote agent (with proper child spans)
            remote_results = self._delegate_to_remote_with_span(
                trace_ctx=trace_ctx,
                task_type=analysis.get("task_type", "search"),
                query=user_message
            )
            
            # Step 3: Process results locally
            with child_span("synthesize_response", SpanType.CHAIN) as synth_span:
                response = self._synthesize_response(remote_results)
                synth_span.set_inputs({"remote_results": remote_results})
                synth_span.set_outputs({"response": response})
            
            # Record final output
            result = {
                "turn_number": trace_ctx.turn_number,
                "session_id": session_id,
                "response": response,
                "remote_agent_work": remote_results
            }
            turn_span.set_outputs(result)
            
            return result
    
    def _analyze_request(self, message: str) -> Dict[str, Any]:
        """Analyze the user's request."""
        # Simple analysis - in real system would use LLM
        if "search" in message.lower() or "find" in message.lower():
            task_type = "search"
        elif "analyze" in message.lower():
            task_type = "analyze"
        else:
            task_type = "general"
        
        return {
            "task_type": task_type,
            "complexity": "medium",
            "requires_remote": True
        }
    
    def _delegate_to_remote_with_span(
        self,
        trace_ctx: SingleTraceContext,
        task_type: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Delegate work to remote agent and create spans for the work.
        
        The remote agent returns metadata about what it did,
        and we create child spans to represent that work in our trace.
        """
        with child_span(
            "delegate_to_remote",
            SpanType.AGENT,
            {"remote_agent": "RemoteSuperagent", "task_type": task_type}
        ) as delegate_span:
            
            delegate_span.set_inputs({
                "query": query,
                "task_type": task_type
            })
            
            # Get the current span's ID for propagation
            delegate_span_id = delegate_span.span_id
            
            # Call remote agent
            try:
                response = requests.post(
                    f"{self.remote_agent_url}/execute",
                    json={
                        "task_id": f"task_{time.time()}",
                        "sender": self.name,
                        "content": query,
                        "metadata": {
                            "task_type": task_type,
                            "trace_context": trace_ctx.to_headers()
                        }
                    },
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()
                
                # Create child spans to represent remote agent's work
                self._log_remote_work_as_spans(result)
                
                delegate_span.set_outputs(result)
                return result
                
            except Exception as e:
                logger.error(f"Remote agent error: {e}")
                delegate_span.set_attribute("error", str(e))
                return {"error": str(e)}
    
    def _log_remote_work_as_spans(self, remote_result: Dict[str, Any]):
        """
        Create child spans representing work done by the remote agent.
        
        This is how we ensure remote work appears in the same trace -
        the supervisor creates spans based on the remote agent's report.
        """
        work_log = remote_result.get("work_log", [])
        
        for work_item in work_log:
            work_name = work_item.get("operation", "remote_operation")
            work_type = work_item.get("type", "CHAIN")
            
            # Map string type to SpanType
            span_type_map = {
                "TOOL": SpanType.TOOL,
                "CHAIN": SpanType.CHAIN,
                "LLM": SpanType.LLM,
                "AGENT": SpanType.AGENT
            }
            span_type = span_type_map.get(work_type, SpanType.CHAIN)
            
            with child_span(
                f"remote_{work_name}",
                span_type,
                {
                    "remote_agent": remote_result.get("agent_name", "RemoteSuperagent"),
                    "execution_time_ms": work_item.get("duration_ms", 0)
                }
            ) as work_span:
                work_span.set_inputs(work_item.get("input", {}))
                work_span.set_outputs(work_item.get("output", {}))
    
    def _synthesize_response(self, remote_results: Dict[str, Any]) -> str:
        """Synthesize final response from remote results."""
        if "error" in remote_results:
            return f"I encountered an issue: {remote_results['error']}"
        
        result_data = remote_results.get("result", {})
        return f"Based on my analysis: {result_data}"
    
    def _local_summarize(self, text: str) -> str:
        """Local tool: summarize text."""
        return f"Summary: {text[:50]}..."
    
    def _local_format(self, data: Any) -> str:
        """Local tool: format data."""
        return f"Formatted: {data}"


def main():
    """Demo the V3 single-trace solution."""
    print("\n" + "="*60)
    print("V3 SINGLE-TRACE MULTI-AGENT DEMO")
    print("="*60 + "\n")
    
    supervisor = SupervisorAgentV3()
    session_id = f"session_{int(time.time())}"
    
    # Multi-turn conversation
    turns = [
        "Search for information about Python machine learning",
        "Analyze the search results in more detail",
        "Find additional resources on deep learning"
    ]
    
    print(f"Session ID: {session_id}\n")
    
    for i, user_input in enumerate(turns, 1):
        print(f"\n{'='*50}")
        print(f"TURN {i}: {user_input}")
        print("="*50)
        
        result = supervisor.process_turn(session_id, user_input)
        print(f"Response: {result['response']}")
        print(f"Turn number in trace: {result['turn_number']}")
        
        time.sleep(0.5)
    
    print("\n" + "="*60)
    print("Demo complete! Check MLflow UI: mlflow ui --port 5002")
    print("="*60)


if __name__ == "__main__":
    main()

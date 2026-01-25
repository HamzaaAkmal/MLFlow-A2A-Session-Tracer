"""
Supervisor Agent V2 - With Proper Distributed Tracing
=======================================================

This version uses OpenTelemetry's W3C Trace Context propagation
to pass trace context to remote agents.
"""

import uuid
import time
import requests
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import logging

import mlflow
from mlflow.entities import SpanType, SpanStatusCode

from distributed_tracing import (
    start_conversation_trace,
    create_child_span,
    create_session_id,
    get_current_traceparent
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# MLflow setup
mlflow.set_tracking_uri("./mlruns")
mlflow.set_experiment("Multi-Agent-Tracing-V2")

# Remote agent URL
REMOTE_AGENT_URL = "http://127.0.0.1:5001"


@dataclass
class Message:
    role: str
    content: str
    timestamp: float = None
    
    def __post_init__(self):
        self.timestamp = self.timestamp or time.time()


class SupervisorAgentV2:
    """
    Supervisor Agent with proper distributed tracing.
    
    Uses OpenTelemetry W3C Trace Context propagation to ensure
    remote agent spans are nested under this agent's spans.
    """
    
    def __init__(self):
        self.name = "SupervisorAgent"
        self.version = "2.0.0"
        self._conversations: Dict[str, List[Message]] = {}
        logger.info(f"SupervisorAgentV2 initialized")
    
    def start_session(self) -> str:
        """Start a new conversation session."""
        session_id = create_session_id()
        self._conversations[session_id] = []
        logger.info(f"Started session: {session_id}")
        return session_id
    
    def process_message(self, session_id: str, user_message: str) -> str:
        """
        Process a user message.
        
        Creates spans that are part of the session's trace,
        and propagates trace context to remote agents.
        """
        # Store message
        if session_id not in self._conversations:
            self._conversations[session_id] = []
        self._conversations[session_id].append(Message("user", user_message))
        
        # Start/continue conversation trace
        with start_conversation_trace(
            session_id=session_id,
            name="SupervisorAgent.process",
            agent_name=self.name
        ) as (root_span, dist_ctx):
            
            root_span.set_inputs({"user_message": user_message})
            
            try:
                # Analyze message
                with create_child_span("analyze_intent", SpanType.CHAIN) as analyze_span:
                    analyze_span.set_inputs({"message": user_message})
                    analysis = self._analyze(user_message)
                    analyze_span.set_outputs(analysis)
                
                # Delegate if needed
                if analysis["requires_delegation"]:
                    with create_child_span(
                        "delegate_to_remote",
                        SpanType.CHAIN,
                        {"remote_url": REMOTE_AGENT_URL}
                    ) as delegate_span:
                        
                        delegate_span.set_inputs({
                            "task_type": analysis["task_type"],
                            "trace_context": dist_ctx.to_headers()
                        })
                        
                        # Call remote agent WITH trace context
                        result = self._call_remote_agent(
                            user_message,
                            analysis,
                            dist_ctx.to_headers()
                        )
                        
                        delegate_span.set_outputs(result)
                        response = self._format_response(result)
                else:
                    with create_child_span("local_response", SpanType.CHAIN) as local_span:
                        response = f"I understood your message. How can I help further?"
                        local_span.set_outputs({"response": response})
                
                # Store response
                self._conversations[session_id].append(Message("assistant", response))
                
                root_span.set_outputs({"response": response})
                root_span.set_status(SpanStatusCode.OK)
                
                return response
                
            except Exception as e:
                logger.exception("Error processing message")
                root_span.set_status(SpanStatusCode.ERROR)
                raise
    
    def _analyze(self, message: str) -> Dict[str, Any]:
        """Analyze message intent."""
        msg_lower = message.lower()
        keywords = ["search", "find", "lookup", "calculate", "analyze", "research"]
        
        requires_delegation = any(kw in msg_lower for kw in keywords)
        
        if "search" in msg_lower or "find" in msg_lower:
            task_type = "search"
        elif "analyze" in msg_lower or "research" in msg_lower:
            task_type = "analyze"
        else:
            task_type = "general"
        
        return {
            "requires_delegation": requires_delegation,
            "task_type": task_type
        }
    
    def _call_remote_agent(
        self,
        message: str,
        analysis: Dict[str, Any],
        trace_headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Call the remote agent with trace context propagation.
        
        The trace_headers contain the 'traceparent' header that
        allows the remote agent to continue our trace.
        """
        payload = {
            "message_type": "task_request",
            "payload": {
                "task_id": str(uuid.uuid4()),
                "task_type": analysis["task_type"],
                "input_data": {"message": message}
            }
        }
        
        # Get current traceparent for propagation
        current_traceparent = get_current_traceparent()
        
        headers = {
            "Content-Type": "application/json",
            **trace_headers  # Include traceparent, X-Session-ID, etc.
        }
        
        # Ensure traceparent is current
        if current_traceparent:
            headers["traceparent"] = current_traceparent
        
        logger.info(f"Calling remote agent with traceparent: {headers.get('traceparent', 'NONE')}")
        
        try:
            response = requests.post(
                f"{REMOTE_AGENT_URL}/execute",
                json=payload,
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            return response.json().get("payload", {})
        except Exception as e:
            logger.error(f"Remote agent call failed: {e}")
            return {"status": "error", "error": str(e)}
    
    def _format_response(self, result: Dict[str, Any]) -> str:
        """Format the response."""
        if result.get("status") == "error":
            return f"Error: {result.get('error', 'Unknown error')}"
        
        data = result.get("result", {})
        return data.get("message", "Task completed.")


if __name__ == "__main__":
    agent = SupervisorAgentV2()
    session = agent.start_session()
    print(f"Session: {session}")

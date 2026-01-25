"""
Enhanced Supervisor Agent with Advanced Tracing
=================================================

This is an enhanced version of the Supervisor Agent that demonstrates
more advanced tracing patterns for production use cases.

Key Improvements:
1. Uses session-based trace grouping for true single-trace behavior
2. Implements retry logic with proper span nesting
3. Provides comprehensive trace metadata
"""

import uuid
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

import mlflow
from mlflow.entities import SpanType, SpanStatusCode

import config
from enhanced_tracing import (
    EnhancedTraceContext,
    traced_session,
    traced_child_span,
    trace_store,
    generate_session_id,
    end_session
)
from a2a_protocol import A2AClient, TaskRequest

logger = logging.getLogger(__name__)


@dataclass
class Message:
    role: str
    content: str
    timestamp: float = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        self.timestamp = self.timestamp or time.time()
        self.metadata = self.metadata or {}


class EnhancedSupervisorAgent:
    """
    Enhanced Supervisor Agent with advanced MLflow tracing.
    
    This implementation demonstrates:
    1. True session-based tracing with trace ID reuse
    2. Proper span nesting across agent boundaries
    3. Comprehensive error handling and status reporting
    """
    
    def __init__(self, remote_agent_url: str = None):
        self.name = config.SUPERVISOR_AGENT_NAME
        self.version = config.SUPERVISOR_AGENT_VERSION
        self.remote_agent_url = remote_agent_url or config.REMOTE_SUPERAGENT_URL
        
        # A2A client
        self.a2a_client = A2AClient(self.remote_agent_url)
        
        # Conversation storage
        self._conversations: Dict[str, List[Message]] = {}
        
        # Initialize MLflow
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
        
        # Disable auto-tracing
        self._disable_auto_tracing()
        
        logger.info(f"EnhancedSupervisorAgent initialized: {self.name} v{self.version}")
    
    def _disable_auto_tracing(self):
        """Disable any automatic tracing."""
        try:
            mlflow.autolog(disable=True)
        except Exception:
            pass
    
    def start_session(self) -> str:
        """Start a new conversation session."""
        session_id = generate_session_id()
        self._conversations[session_id] = []
        logger.info(f"Started session: {session_id}")
        return session_id
    
    def end_session(self, session_id: str):
        """End a conversation session."""
        end_session(session_id)
        self._conversations.pop(session_id, None)
        logger.info(f"Ended session: {session_id}")
    
    def process_message(self, session_id: str, user_message: str) -> str:
        """
        Process a user message within a session.
        
        This method creates properly nested MLflow spans for all operations.
        """
        # Store user message
        if session_id not in self._conversations:
            self._conversations[session_id] = []
        
        self._conversations[session_id].append(
            Message(role="user", content=user_message)
        )
        
        # Get turn number
        turn_number = len([m for m in self._conversations[session_id] if m.role == "user"])
        
        # Use session-based tracing
        with traced_session(
            session_id=session_id,
            name=f"Conversation.Turn_{turn_number}",
            agent_name=self.name
        ) as root_span:
            root_span.set_inputs({
                "user_message": user_message,
                "session_id": session_id,
                "turn_number": turn_number
            })
            
            try:
                # Create trace context for propagation
                context = root_span.create_context(session_id, turn_number)
                
                # Process the message
                response = self._process_with_tracing(
                    user_message, context, turn_number
                )
                
                # Store response
                self._conversations[session_id].append(
                    Message(role="assistant", content=response)
                )
                
                root_span.set_outputs({"response": response})
                root_span.set_status(SpanStatusCode.OK)
                
                return response
                
            except Exception as e:
                logger.error(f"Error in session {session_id}: {e}")
                root_span.set_status(SpanStatusCode.ERROR)
                root_span.set_attribute("error", str(e))
                raise
    
    def _process_with_tracing(
        self,
        message: str,
        context: EnhancedTraceContext,
        turn_number: int
    ) -> str:
        """
        Process message with full tracing.
        """
        # Analyze message
        with traced_child_span(
            name="analyze_intent",
            span_type=SpanType.CHAIN
        ) as span:
            span.set_inputs({"message": message})
            analysis = self._analyze_intent(message)
            span.set_outputs(analysis)
        
        # Route based on analysis
        if analysis["requires_delegation"]:
            with traced_child_span(
                name="delegate_to_remote",
                span_type=SpanType.CHAIN,
                attributes={
                    "task_type": analysis["task_type"],
                    "remote_url": self.remote_agent_url
                }
            ) as span:
                span.set_inputs({
                    "message": message,
                    "task_type": analysis["task_type"],
                    "trace_context": context.to_dict()
                })
                
                result = self._delegate_task(message, analysis, context)
                span.set_outputs(result)
                
                return self._format_response(result)
        else:
            with traced_child_span(
                name="local_response",
                span_type=SpanType.CHAIN
            ) as span:
                response = self._handle_locally(message, analysis)
                span.set_outputs({"response": response})
                return response
    
    def _analyze_intent(self, message: str) -> Dict[str, Any]:
        """Analyze message intent."""
        message_lower = message.lower()
        
        keywords = ["search", "find", "lookup", "calculate", "analyze", "research"]
        requires_delegation = any(kw in message_lower for kw in keywords)
        
        if "search" in message_lower or "find" in message_lower:
            task_type = "search"
        elif "calculate" in message_lower:
            task_type = "calculate"
        elif "analyze" in message_lower or "research" in message_lower:
            task_type = "analyze"
        else:
            task_type = "general"
        
        return {
            "requires_delegation": requires_delegation,
            "task_type": task_type,
            "detected_keywords": [k for k in keywords if k in message_lower]
        }
    
    def _delegate_task(
        self,
        message: str,
        analysis: Dict[str, Any],
        context: EnhancedTraceContext
    ) -> Dict[str, Any]:
        """Delegate task to remote agent."""
        task = TaskRequest(
            task_id=str(uuid.uuid4()),
            task_type=analysis["task_type"],
            input_data={
                "message": message,
                "analysis": analysis
            }
        )
        
        # Convert to TraceContext for A2A client
        from mlflow_context import TraceContext
        trace_ctx = TraceContext(
            trace_id=context.trace_id,
            span_id=context.parent_span_id,
            request_id=context.request_id,
            session_id=context.session_id
        )
        
        response = self.a2a_client.execute_task(task, trace_ctx)
        
        return {
            "status": response.status,
            "result": response.result,
            "error": response.error_message
        }
    
    def _handle_locally(self, message: str, analysis: Dict[str, Any]) -> str:
        """Handle message locally."""
        return f"I understood your message. How can I help you further?"
    
    def _format_response(self, result: Dict[str, Any]) -> str:
        """Format the final response."""
        if result.get("status") == "error":
            return f"Sorry, I encountered an issue: {result.get('error')}"
        
        data = result.get("result", {})
        if isinstance(data, dict) and "message" in data:
            return data["message"]
        
        return f"Task completed successfully."
    
    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get conversation history."""
        return [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in self._conversations.get(session_id, [])
        ]


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    agent = EnhancedSupervisorAgent()
    session = agent.start_session()
    
    print(f"Session: {session}")
    print(f"Remote Agent: {config.REMOTE_SUPERAGENT_URL}")
    print("\nNote: Ensure Remote Superagent is running before testing.")

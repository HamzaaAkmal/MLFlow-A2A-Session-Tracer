"""
Supervisor Agent (Local Agent)
===============================

This module implements the Supervisor Agent that:
1. Receives user messages
2. Creates and manages the MLflow trace for the conversation
3. Delegates tasks to the Remote Superagent via A2A protocol
4. Ensures proper span nesting by passing trace context

This agent demonstrates the solution to both challenges:
- Challenge 1: Passes trace context to remote agent for nested spans
- Challenge 2: Maintains single trace across multi-turn conversation
"""

import uuid
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import logging

import mlflow
from mlflow.entities import SpanType

import config
from mlflow_context import (
    TraceContext,
    AgentTracingContext,
    create_new_session,
    finalize_session
)
from a2a_protocol import A2AClient, TaskRequest, A2AMessage, A2AMessageType

logger = logging.getLogger(__name__)


@dataclass
class ConversationMessage:
    """A message in the conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class SupervisorAgent:
    """
    The Supervisor Agent that orchestrates the multi-agent system.
    
    Key Responsibilities:
    1. Create and maintain a single MLflow trace per conversation session
    2. Process user messages and determine if delegation is needed
    3. Call the Remote Superagent with proper trace context propagation
    4. Aggregate results and respond to the user
    
    The agent uses MLflow's Fluent API for tracing, with manual control
    over trace creation and span nesting.
    """
    
    def __init__(self, remote_agent_url: str = None):
        """
        Initialize the Supervisor Agent.
        
        Args:
            remote_agent_url: URL of the Remote Superagent (defaults to config)
        """
        self.name = config.SUPERVISOR_AGENT_NAME
        self.version = config.SUPERVISOR_AGENT_VERSION
        self.remote_agent_url = remote_agent_url or config.REMOTE_SUPERAGENT_URL
        
        # A2A client for communicating with remote agent
        self.a2a_client = A2AClient(self.remote_agent_url)
        
        # Conversation history per session
        self._conversations: Dict[str, List[ConversationMessage]] = {}
        
        # MLflow setup
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
        
        # Disable auto-tracing from any ADK if present
        # This is crucial for Challenge 2 - we control trace creation
        self._disable_auto_tracing()
        
        logger.info(f"SupervisorAgent initialized, will delegate to {self.remote_agent_url}")
    
    def _disable_auto_tracing(self):
        """
        Disable any automatic tracing that might interfere with our manual control.
        
        This addresses Challenge 2 by ensuring the ADK runner doesn't create
        new traces for each execution.
        """
        # If using specific ADK frameworks, disable their auto-tracing here
        # For example:
        # - LangChain: set LANGCHAIN_TRACING_V2=false
        # - LlamaIndex: disable callback manager
        
        # MLflow autolog can be disabled if it's causing issues
        try:
            mlflow.autolog(disable=True)
        except Exception:
            pass  # autolog might not be enabled
        
        logger.debug("Auto-tracing disabled for manual trace control")
    
    def start_session(self) -> str:
        """
        Start a new conversation session.
        
        Returns:
            The session ID for this conversation
        """
        session_id = create_new_session()
        self._conversations[session_id] = []
        logger.info(f"Started new session: {session_id}")
        return session_id
    
    def end_session(self, session_id: str):
        """
        End a conversation session and finalize the trace.
        
        Args:
            session_id: The session ID to end
        """
        finalize_session(session_id)
        if session_id in self._conversations:
            del self._conversations[session_id]
        logger.info(f"Ended session: {session_id}")
    
    def process_message(
        self,
        session_id: str,
        user_message: str
    ) -> str:
        """
        Process a user message within a conversation session.
        
        This method:
        1. Creates/continues the MLflow trace for this session
        2. Analyzes the message to determine needed actions
        3. Delegates to Remote Superagent if needed
        4. Returns the response
        
        Args:
            session_id: The conversation session ID
            user_message: The user's message
            
        Returns:
            The assistant's response
        """
        # Store user message
        if session_id not in self._conversations:
            self._conversations[session_id] = []
        self._conversations[session_id].append(
            ConversationMessage(role="user", content=user_message)
        )
        
        # Create tracing context for this session
        tracing_ctx = AgentTracingContext(session_id, self.name)
        
        # Get turn number for this conversation
        turn_number = len([m for m in self._conversations[session_id] if m.role == "user"])
        
        # Start/continue the trace for this session
        # This is the key to Challenge 2 - same session = same trace grouping
        with mlflow.start_span(
            name=f"SupervisorAgent.process_turn_{turn_number}",
            span_type=SpanType.AGENT,
            attributes={
                "session_id": session_id,
                "turn_number": turn_number,
                "agent_name": self.name,
                "agent_version": self.version,
                "user_message_length": len(user_message)
            }
        ) as root_span:
            # Log the input
            root_span.set_inputs({"user_message": user_message, "turn": turn_number})
            
            # Get trace context for propagation to remote agent
            trace_context = TraceContext(
                trace_id=root_span.request_id if hasattr(root_span, 'request_id') else str(uuid.uuid4()),
                span_id=root_span.span_id if hasattr(root_span, 'span_id') else str(uuid.uuid4()),
                request_id=str(uuid.uuid4()),
                session_id=session_id
            )
            
            try:
                # Analyze the message
                with mlflow.start_span(
                    name="analyze_message",
                    span_type=SpanType.CHAIN,
                    attributes={"operation": "message_analysis"}
                ) as analyze_span:
                    analysis = self._analyze_message(user_message)
                    analyze_span.set_inputs({"message": user_message})
                    analyze_span.set_outputs({"analysis": analysis})
                
                # Determine if we need to delegate to remote agent
                if analysis.get("requires_delegation", False):
                    # Call Remote Superagent with trace context
                    # This is the key to Challenge 1 - passing trace context
                    with mlflow.start_span(
                        name="delegate_to_remote_agent",
                        span_type=SpanType.CHAIN,
                        attributes={
                            "operation": "a2a_delegation",
                            "remote_agent_url": self.remote_agent_url
                        }
                    ) as delegate_span:
                        delegate_span.set_inputs({
                            "task_type": analysis.get("task_type"),
                            "trace_context": trace_context.to_dict()
                        })
                        
                        remote_result = self._delegate_to_remote(
                            user_message,
                            analysis,
                            trace_context
                        )
                        
                        delegate_span.set_outputs({"remote_result": remote_result})
                    
                    response = self._format_response(remote_result, analysis)
                else:
                    # Handle locally
                    with mlflow.start_span(
                        name="local_processing",
                        span_type=SpanType.CHAIN,
                        attributes={"operation": "local_response"}
                    ) as local_span:
                        response = self._handle_locally(user_message, analysis)
                        local_span.set_outputs({"response": response})
                
                # Store assistant response
                self._conversations[session_id].append(
                    ConversationMessage(role="assistant", content=response)
                )
                
                root_span.set_outputs({"response": response})
                root_span.set_status(mlflow.entities.SpanStatusCode.OK)
                
                return response
                
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                root_span.set_status(mlflow.entities.SpanStatusCode.ERROR)
                root_span.set_attribute("error", str(e))
                raise
    
    def _analyze_message(self, message: str) -> Dict[str, Any]:
        """
        Analyze the user message to determine what action is needed.
        
        In a real system, this would use an LLM for intent classification.
        For this PoC, we use simple keyword matching.
        """
        message_lower = message.lower()
        
        # Determine if delegation is needed based on keywords
        delegation_keywords = [
            "search", "lookup", "find", "calculate", "analyze",
            "fetch", "retrieve", "query", "process", "research"
        ]
        
        requires_delegation = any(kw in message_lower for kw in delegation_keywords)
        
        # Determine task type
        if "search" in message_lower or "find" in message_lower or "lookup" in message_lower:
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
            "keywords": [kw for kw in delegation_keywords if kw in message_lower],
            "message_summary": message[:100]
        }
    
    def _delegate_to_remote(
        self,
        message: str,
        analysis: Dict[str, Any],
        trace_context: TraceContext
    ) -> Dict[str, Any]:
        """
        Delegate a task to the Remote Superagent.
        
        This method passes the trace context to ensure proper span nesting.
        """
        task_request = TaskRequest(
            task_id=str(uuid.uuid4()),
            task_type=analysis.get("task_type", "general"),
            input_data={
                "message": message,
                "keywords": analysis.get("keywords", []),
                "context": {
                    "session_id": trace_context.session_id,
                    "analysis": analysis
                }
            }
        )
        
        logger.info(f"Delegating task {task_request.task_id} to remote agent")
        
        # Execute task with trace context propagation
        response = self.a2a_client.execute_task(task_request, trace_context)
        
        return {
            "task_id": response.task_id,
            "status": response.status,
            "result": response.result,
            "error": response.error_message
        }
    
    def _handle_locally(
        self,
        message: str,
        analysis: Dict[str, Any]
    ) -> str:
        """
        Handle a message locally without delegation.
        """
        return f"I understood your message about '{analysis.get('message_summary', message[:50])}'. How can I help you further?"
    
    def _format_response(
        self,
        remote_result: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> str:
        """
        Format the final response combining remote agent results.
        """
        if remote_result.get("status") == "error":
            return f"I encountered an issue while processing your request: {remote_result.get('error', 'Unknown error')}"
        
        result = remote_result.get("result", {})
        
        if isinstance(result, dict):
            if "message" in result:
                return result["message"]
            elif "data" in result:
                return f"Here's what I found: {result['data']}"
        
        return f"Task completed successfully. Result: {result}"
    
    def get_conversation_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Get the conversation history for a session."""
        messages = self._conversations.get(session_id, [])
        return [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp
            }
            for m in messages
        ]


# =============================================================================
# Convenience Function for Quick Testing
# =============================================================================

def create_supervisor_agent() -> SupervisorAgent:
    """Create a configured SupervisorAgent instance."""
    return SupervisorAgent()


if __name__ == "__main__":
    # Quick test
    logging.basicConfig(level=logging.INFO)
    
    agent = create_supervisor_agent()
    session = agent.start_session()
    
    print(f"Started session: {session}")
    print("Note: This test requires the Remote Superagent to be running.")
    print(f"Remote agent URL: {config.REMOTE_SUPERAGENT_URL}")

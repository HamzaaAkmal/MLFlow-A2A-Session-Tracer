"""
Agent-to-Agent (A2A) Protocol Implementation
=============================================

This module implements the A2A communication protocol between agents,
with built-in support for MLflow trace context propagation.

The protocol ensures that trace context is passed with every inter-agent
call, enabling proper span nesting across agent boundaries.
"""

import json
import requests
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional, List
from enum import Enum
import logging

import config
from mlflow_context import TraceContext

logger = logging.getLogger(__name__)


# =============================================================================
# A2A Message Types
# =============================================================================

class A2AMessageType(Enum):
    """Types of A2A messages."""
    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


@dataclass
class A2AMessage:
    """
    Standard A2A message format.
    
    All inter-agent communication uses this format to ensure
    consistent trace context propagation.
    """
    message_type: str
    payload: Dict[str, Any]
    trace_context: Optional[Dict[str, str]] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_type": self.message_type,
            "payload": self.payload,
            "trace_context": self.trace_context,
            "metadata": self.metadata or {}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "A2AMessage":
        return cls(
            message_type=data["message_type"],
            payload=data["payload"],
            trace_context=data.get("trace_context"),
            metadata=data.get("metadata", {})
        )
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "A2AMessage":
        return cls.from_dict(json.loads(json_str))


@dataclass
class TaskRequest:
    """Request to execute a task."""
    task_id: str
    task_type: str
    input_data: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TaskResponse:
    """Response from task execution."""
    task_id: str
    status: str  # "success", "error", "pending"
    result: Optional[Any] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# =============================================================================
# A2A Client - For Making Calls to Remote Agents
# =============================================================================

class A2AClient:
    """
    Client for making A2A calls to remote agents.
    
    This client automatically propagates MLflow trace context
    with every request, enabling proper span nesting.
    """
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
    
    def call_agent(
        self,
        endpoint: str,
        message: A2AMessage,
        trace_context: Optional[TraceContext] = None
    ) -> A2AMessage:
        """
        Make a call to a remote agent.
        
        Args:
            endpoint: The endpoint path (e.g., "/execute")
            message: The A2A message to send
            trace_context: Optional trace context for propagation
            
        Returns:
            The response A2A message
        """
        url = f"{self.base_url}{endpoint}"
        
        # Prepare headers with trace context
        headers = {
            "Content-Type": "application/json"
        }
        
        if trace_context:
            # Add trace context to both headers and message body
            headers.update(trace_context.to_headers())
            message.trace_context = trace_context.to_dict()
        
        logger.debug(f"A2A call to {url} with trace context: {trace_context}")
        
        try:
            response = self.session.post(
                url,
                json=message.to_dict(),
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            return A2AMessage.from_dict(response.json())
            
        except requests.exceptions.RequestException as e:
            logger.error(f"A2A call failed: {e}")
            return A2AMessage(
                message_type=A2AMessageType.ERROR.value,
                payload={"error": str(e)},
                trace_context=message.trace_context
            )
    
    def execute_task(
        self,
        task: TaskRequest,
        trace_context: Optional[TraceContext] = None
    ) -> TaskResponse:
        """
        Execute a task on the remote agent.
        
        This is a convenience method that wraps the task in an A2A message.
        """
        message = A2AMessage(
            message_type=A2AMessageType.TASK_REQUEST.value,
            payload=task.to_dict()
        )
        
        response = self.call_agent("/execute", message, trace_context)
        
        if response.message_type == A2AMessageType.ERROR.value:
            return TaskResponse(
                task_id=task.task_id,
                status="error",
                error_message=response.payload.get("error", "Unknown error")
            )
        
        return TaskResponse(
            task_id=task.task_id,
            status=response.payload.get("status", "success"),
            result=response.payload.get("result"),
            metadata=response.metadata
        )
    
    def call_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        trace_context: Optional[TraceContext] = None
    ) -> Dict[str, Any]:
        """
        Call a tool on the remote agent.
        """
        message = A2AMessage(
            message_type=A2AMessageType.TOOL_CALL.value,
            payload={
                "tool_name": tool_name,
                "tool_args": tool_args
            }
        )
        
        response = self.call_agent("/tool", message, trace_context)
        
        return response.payload


# =============================================================================
# A2A Protocol Helpers
# =============================================================================

def extract_trace_context_from_request(request_data: Dict[str, Any], headers: Dict[str, str]) -> Optional[TraceContext]:
    """
    Extract trace context from an incoming A2A request.
    
    Checks both the message body and headers for trace context.
    """
    # First try to get from message body
    if "trace_context" in request_data and request_data["trace_context"]:
        try:
            return TraceContext.from_dict(request_data["trace_context"])
        except (KeyError, TypeError):
            pass
    
    # Fall back to headers
    return TraceContext.from_headers(headers)


def create_task_message(
    task_id: str,
    task_type: str,
    input_data: Dict[str, Any],
    trace_context: Optional[TraceContext] = None
) -> A2AMessage:
    """
    Create a standardized task request message.
    """
    task = TaskRequest(
        task_id=task_id,
        task_type=task_type,
        input_data=input_data
    )
    
    return A2AMessage(
        message_type=A2AMessageType.TASK_REQUEST.value,
        payload=task.to_dict(),
        trace_context=trace_context.to_dict() if trace_context else None
    )


def create_response_message(
    status: str,
    result: Any,
    trace_context: Optional[TraceContext] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> A2AMessage:
    """
    Create a standardized response message.
    """
    return A2AMessage(
        message_type=A2AMessageType.TASK_RESPONSE.value,
        payload={
            "status": status,
            "result": result
        },
        trace_context=trace_context.to_dict() if trace_context else None,
        metadata=metadata
    )

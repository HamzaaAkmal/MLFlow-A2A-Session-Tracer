"""
Distributed Tracing Solution for Multi-Agent Systems
======================================================

This module implements TRUE distributed tracing using OpenTelemetry's
W3C Trace Context propagation to ensure:

1. ALL spans (local + remote) are in ONE SINGLE TRACE
2. Remote agent spans are NESTED under the supervisor's spans
3. Multi-turn conversations share the same trace context

Key: Uses OpenTelemetry's trace context propagation (traceparent header)
"""

import uuid
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager
import logging

from opentelemetry import trace
from opentelemetry.trace import SpanContext, TraceFlags, NonRecordingSpan
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.context import Context, attach, detach, set_value

import mlflow
from mlflow.entities import SpanType, SpanStatusCode

logger = logging.getLogger(__name__)


# =============================================================================
# W3C Trace Context Propagation
# =============================================================================

propagator = TraceContextTextMapPropagator()


@dataclass
class DistributedTraceContext:
    """
    Distributed trace context using W3C Trace Context format.
    
    This format is standardized and works across different tracing systems.
    The traceparent header format: {version}-{trace_id}-{span_id}-{flags}
    """
    traceparent: str  # W3C traceparent header value
    session_id: str
    turn_number: int = 0
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers for propagation."""
        return {
            "traceparent": self.traceparent,
            "X-Session-ID": self.session_id,
            "X-Turn-Number": str(self.turn_number)
        }
    
    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> Optional["DistributedTraceContext"]:
        """Extract from HTTP headers."""
        traceparent = headers.get("traceparent") or headers.get("Traceparent")
        session_id = headers.get("X-Session-ID") or headers.get("x-session-id")
        
        if traceparent and session_id:
            return cls(
                traceparent=traceparent,
                session_id=session_id,
                turn_number=int(headers.get("X-Turn-Number", "0"))
            )
        return None


def extract_trace_context(headers: Dict[str, str]) -> Tuple[Optional[Context], Optional[DistributedTraceContext]]:
    """
    Extract OpenTelemetry context from headers.
    
    Returns:
        Tuple of (OTel Context, DistributedTraceContext)
    """
    # Extract OTel context
    ctx = propagator.extract(carrier=headers)
    
    # Extract our custom context
    dist_ctx = DistributedTraceContext.from_headers(headers)
    
    return ctx, dist_ctx


def inject_trace_context(span) -> Dict[str, str]:
    """
    Inject current span's context into headers for propagation.
    
    Args:
        span: The current MLflow/OTel span
        
    Returns:
        Headers dict with traceparent
    """
    headers = {}
    propagator.inject(carrier=headers)
    return headers


# =============================================================================
# Session Manager for Multi-Turn Conversations
# =============================================================================

class ConversationTraceManager:
    """
    Manages traces for multi-turn conversations.
    
    Key feature: Maintains a single root span across all turns,
    with each turn creating child spans under that root.
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._sessions: Dict[str, Dict] = {}
        return cls._instance
    
    def get_or_create_session(self, session_id: str) -> Dict:
        """Get or create a session's trace info."""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "session_id": session_id,
                "turn_count": 0,
                "trace_id": None,
                "root_traceparent": None
            }
        return self._sessions[session_id]
    
    def increment_turn(self, session_id: str) -> int:
        """Increment and return turn count."""
        session = self.get_or_create_session(session_id)
        session["turn_count"] += 1
        return session["turn_count"]
    
    def store_traceparent(self, session_id: str, traceparent: str):
        """Store the root traceparent for a session."""
        session = self.get_or_create_session(session_id)
        if session["root_traceparent"] is None:
            session["root_traceparent"] = traceparent
    
    def get_traceparent(self, session_id: str) -> Optional[str]:
        """Get stored traceparent for a session."""
        session = self._sessions.get(session_id, {})
        return session.get("root_traceparent")


conversation_manager = ConversationTraceManager()


# =============================================================================
# Tracing Context Managers
# =============================================================================

@contextmanager
def start_conversation_trace(session_id: str, name: str, agent_name: str):
    """
    Start or continue a conversation trace.
    
    For the first turn: Creates a new trace
    For subsequent turns: Creates spans under the same logical conversation
    
    Args:
        session_id: Unique conversation session ID
        name: Name for the span
        agent_name: Name of the agent
    """
    turn_number = conversation_manager.increment_turn(session_id)
    
    with mlflow.start_span(
        name=f"{name}_turn_{turn_number}",
        span_type=SpanType.AGENT,
        attributes={
            "session_id": session_id,
            "turn_number": turn_number,
            "agent_name": agent_name
        }
    ) as span:
        # Get the traceparent for this span
        headers = {}
        propagator.inject(carrier=headers)
        traceparent = headers.get("traceparent", "")
        
        # Store for session tracking
        conversation_manager.store_traceparent(session_id, traceparent)
        
        # Create context for propagation to remote agents
        dist_ctx = DistributedTraceContext(
            traceparent=traceparent,
            session_id=session_id,
            turn_number=turn_number
        )
        
        yield span, dist_ctx


@contextmanager  
def continue_distributed_trace(headers: Dict[str, str], name: str, agent_name: str):
    """
    Continue a trace from a parent agent.
    
    This is THE KEY FUNCTION for distributed tracing.
    It extracts the parent's trace context and creates a child span
    that is PROPERLY NESTED under the parent.
    
    Args:
        headers: HTTP headers containing traceparent
        name: Name for the span
        agent_name: Name of this agent
    """
    # Extract the parent context
    parent_ctx, dist_ctx = extract_trace_context(headers)
    
    if parent_ctx and dist_ctx:
        # Attach the parent context - THIS LINKS OUR SPAN TO THE PARENT
        token = attach(parent_ctx)
        
        try:
            with mlflow.start_span(
                name=name,
                span_type=SpanType.AGENT,
                attributes={
                    "session_id": dist_ctx.session_id,
                    "turn_number": dist_ctx.turn_number,
                    "agent_name": agent_name,
                    "is_remote": True
                }
            ) as span:
                yield span, dist_ctx
        finally:
            # Detach the context
            detach(token)
    else:
        # No parent context - create standalone span
        logger.warning("No parent trace context found, creating standalone trace")
        with mlflow.start_span(
            name=name,
            span_type=SpanType.AGENT,
            attributes={"agent_name": agent_name}
        ) as span:
            yield span, None


@contextmanager
def create_child_span(name: str, span_type: SpanType = SpanType.CHAIN, attributes: Dict = None):
    """Create a child span under the current span."""
    with mlflow.start_span(
        name=name,
        span_type=span_type,
        attributes=attributes or {}
    ) as span:
        yield span


# =============================================================================
# Helper Functions
# =============================================================================

def create_session_id() -> str:
    """Create a new session ID."""
    return str(uuid.uuid4())


def get_current_traceparent() -> Optional[str]:
    """Get the traceparent header for the current span."""
    headers = {}
    propagator.inject(carrier=headers)
    return headers.get("traceparent")

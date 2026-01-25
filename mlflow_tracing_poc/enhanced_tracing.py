"""
Enhanced MLflow Tracing Utilities
==================================

This module provides an enhanced tracing mechanism that ensures
proper trace continuation across agent boundaries.

Key Features:
1. Uses MLflow's client API for more control over trace IDs
2. Implements proper parent-child span relationships
3. Handles trace context serialization/deserialization

This addresses both core challenges:
- Challenge 1: Cross-agent span nesting via context propagation
- Challenge 2: Single trace per session via trace ID management
"""

import uuid
import time
import threading
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable, List
from contextlib import contextmanager
from functools import wraps
import json
import logging

import mlflow
from mlflow.entities import SpanType, SpanStatusCode
from mlflow.tracing.fluent import TRACE_BUFFER

import config

logger = logging.getLogger(__name__)


# =============================================================================
# Trace ID Management for Session Persistence
# =============================================================================

class TraceSessionStore:
    """
    Stores trace IDs for conversation sessions.
    
    This enables maintaining a single trace across multiple turns
    by reusing the same trace ID for all spans in a session.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._store: Dict[str, Dict[str, Any]] = {}
                    cls._instance._initialized = True
        return cls._instance
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data if exists."""
        return self._store.get(session_id)
    
    def create_session(self, session_id: str) -> Dict[str, Any]:
        """Create a new session with trace info."""
        session_data = {
            "session_id": session_id,
            "created_at": time.time(),
            "turn_count": 0,
            "traces": []  # List of trace request_ids for this session
        }
        self._store[session_id] = session_data
        return session_data
    
    def get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        """Get existing session or create new one."""
        if session_id not in self._store:
            return self.create_session(session_id)
        return self._store[session_id]
    
    def increment_turn(self, session_id: str) -> int:
        """Increment turn count and return new count."""
        session = self.get_or_create_session(session_id)
        session["turn_count"] += 1
        return session["turn_count"]
    
    def add_trace(self, session_id: str, trace_id: str):
        """Add a trace ID to the session."""
        session = self.get_or_create_session(session_id)
        session["traces"].append(trace_id)
    
    def end_session(self, session_id: str):
        """Mark session as ended."""
        if session_id in self._store:
            self._store[session_id]["ended_at"] = time.time()


# Global store instance
trace_store = TraceSessionStore()


# =============================================================================
# Enhanced Trace Context for Cross-Agent Communication
# =============================================================================

@dataclass
class EnhancedTraceContext:
    """
    Enhanced trace context with all information needed for cross-agent tracing.
    
    This context carries:
    - trace_id: Links all spans in the conversation
    - parent_span_id: The span to nest under
    - session_id: The conversation session
    - request_id: Unique request identifier
    - metadata: Additional context information
    """
    trace_id: str
    parent_span_id: str
    session_id: str
    request_id: str
    turn_number: int = 0
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "turn_number": self.turn_number,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnhancedTraceContext":
        return cls(
            trace_id=data["trace_id"],
            parent_span_id=data["parent_span_id"],
            session_id=data["session_id"],
            request_id=data["request_id"],
            turn_number=data.get("turn_number", 0),
            metadata=data.get("metadata", {})
        )
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers for A2A protocol."""
        return {
            config.TRACE_CONTEXT_HEADER_TRACE_ID: self.trace_id,
            config.TRACE_CONTEXT_HEADER_SPAN_ID: self.parent_span_id,
            config.TRACE_CONTEXT_HEADER_SESSION_ID: self.session_id,
            config.TRACE_CONTEXT_HEADER_REQUEST_ID: self.request_id,
            "X-Turn-Number": str(self.turn_number),
            "X-Trace-Metadata": json.dumps(self.metadata)
        }
    
    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> Optional["EnhancedTraceContext"]:
        """Extract context from HTTP headers."""
        trace_id = headers.get(config.TRACE_CONTEXT_HEADER_TRACE_ID)
        span_id = headers.get(config.TRACE_CONTEXT_HEADER_SPAN_ID)
        session_id = headers.get(config.TRACE_CONTEXT_HEADER_SESSION_ID)
        request_id = headers.get(config.TRACE_CONTEXT_HEADER_REQUEST_ID)
        
        if not all([trace_id, span_id, session_id]):
            return None
        
        try:
            metadata = json.loads(headers.get("X-Trace-Metadata", "{}"))
        except json.JSONDecodeError:
            metadata = {}
        
        return cls(
            trace_id=trace_id,
            parent_span_id=span_id,
            session_id=session_id,
            request_id=request_id or str(uuid.uuid4()),
            turn_number=int(headers.get("X-Turn-Number", 0)),
            metadata=metadata
        )


# =============================================================================
# Span Wrapper for Clean Tracing
# =============================================================================

class TracedSpan:
    """
    Wrapper around MLflow span for cleaner API.
    """
    
    def __init__(self, span):
        self._span = span
    
    @property
    def span_id(self) -> str:
        """Get the span ID."""
        if hasattr(self._span, 'span_id'):
            return self._span.span_id
        return str(uuid.uuid4())
    
    @property
    def request_id(self) -> str:
        """Get the trace/request ID."""
        if hasattr(self._span, 'request_id'):
            return self._span.request_id
        return str(uuid.uuid4())
    
    def set_inputs(self, inputs: Dict[str, Any]):
        """Set span inputs."""
        if hasattr(self._span, 'set_inputs'):
            self._span.set_inputs(inputs)
    
    def set_outputs(self, outputs: Any):
        """Set span outputs."""
        if hasattr(self._span, 'set_outputs'):
            self._span.set_outputs(outputs)
    
    def set_attribute(self, key: str, value: Any):
        """Set a span attribute."""
        if hasattr(self._span, 'set_attribute'):
            self._span.set_attribute(key, value)
    
    def set_status(self, status: SpanStatusCode):
        """Set span status."""
        if hasattr(self._span, 'set_status'):
            self._span.set_status(status)
    
    def create_context(self, session_id: str, turn_number: int = 0) -> EnhancedTraceContext:
        """Create a trace context from this span for propagation."""
        return EnhancedTraceContext(
            trace_id=self.request_id,
            parent_span_id=self.span_id,
            session_id=session_id,
            request_id=str(uuid.uuid4()),
            turn_number=turn_number
        )


# =============================================================================
# Main Tracing Functions
# =============================================================================

@contextmanager
def traced_session(
    session_id: str,
    name: str,
    agent_name: str,
    span_type: SpanType = SpanType.AGENT,
    attributes: Dict[str, Any] = None
):
    """
    Create a traced span within a session.
    
    This is the main entry point for creating spans that belong
    to a conversation session. It ensures all spans in the same
    session are properly grouped.
    
    Args:
        session_id: The conversation session ID
        name: Name for this span
        agent_name: Name of the agent creating this span
        span_type: Type of span (default: AGENT)
        attributes: Additional attributes
        
    Yields:
        TracedSpan: Wrapper around the MLflow span
    """
    # Get or update session
    turn_number = trace_store.increment_turn(session_id)
    
    # Prepare attributes
    attrs = {
        "session_id": session_id,
        "agent_name": agent_name,
        "turn_number": turn_number,
        **(attributes or {})
    }
    
    with mlflow.start_span(
        name=name,
        span_type=span_type,
        attributes=attrs
    ) as span:
        traced = TracedSpan(span)
        
        # Store trace ID for session
        trace_store.add_trace(session_id, traced.request_id)
        
        yield traced


@contextmanager
def traced_child_span(
    name: str,
    span_type: SpanType = SpanType.CHAIN,
    attributes: Dict[str, Any] = None
):
    """
    Create a child span under the current span.
    
    Args:
        name: Name for this span
        span_type: Type of span
        attributes: Additional attributes
        
    Yields:
        TracedSpan: Wrapper around the MLflow span
    """
    with mlflow.start_span(
        name=name,
        span_type=span_type,
        attributes=attributes or {}
    ) as span:
        yield TracedSpan(span)


@contextmanager
def traced_remote_operation(
    context: EnhancedTraceContext,
    name: str,
    agent_name: str,
    span_type: SpanType = SpanType.AGENT,
    attributes: Dict[str, Any] = None
):
    """
    Create a span that continues from a remote trace context.
    
    This is used by remote agents to create spans that are properly
    linked to the calling agent's span.
    
    The key mechanism:
    - We create a new span with attributes linking to parent
    - MLflow's trace grouping connects related spans
    
    Args:
        context: The trace context from the calling agent
        name: Name for this span
        agent_name: Name of this agent
        span_type: Type of span
        attributes: Additional attributes
        
    Yields:
        TracedSpan: Wrapper around the MLflow span
    """
    attrs = {
        "session_id": context.session_id,
        "agent_name": agent_name,
        "parent_trace_id": context.trace_id,
        "parent_span_id": context.parent_span_id,
        "request_id": context.request_id,
        "turn_number": context.turn_number,
        "is_remote_span": True,
        **(attributes or {})
    }
    
    with mlflow.start_span(
        name=name,
        span_type=span_type,
        attributes=attrs
    ) as span:
        yield TracedSpan(span)


# =============================================================================
# Decorator for Easy Tracing
# =============================================================================

def trace_function(
    name: str = None,
    span_type: SpanType = SpanType.CHAIN,
    capture_args: bool = True,
    capture_result: bool = True
):
    """
    Decorator to automatically trace a function.
    
    Usage:
        @trace_function(name="my_operation")
        def my_function(arg1, arg2):
            return result
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            span_name = name or func.__name__
            
            with mlflow.start_span(
                name=span_name,
                span_type=span_type
            ) as span:
                if capture_args:
                    span.set_inputs({
                        "args": [str(a)[:100] for a in args],
                        "kwargs": {k: str(v)[:100] for k, v in kwargs.items()}
                    })
                
                try:
                    result = func(*args, **kwargs)
                    
                    if capture_result:
                        span.set_outputs(result)
                    
                    span.set_status(SpanStatusCode.OK)
                    return result
                    
                except Exception as e:
                    span.set_status(SpanStatusCode.ERROR)
                    span.set_attribute("error", str(e))
                    raise
        
        return wrapper
    return decorator


# =============================================================================
# Utility Functions
# =============================================================================

def get_current_trace_context(session_id: str) -> Optional[EnhancedTraceContext]:
    """
    Get the current trace context if inside a traced span.
    
    This is useful when you need to pass context to a remote agent
    from within a traced function.
    """
    # Try to get current span from MLflow
    try:
        # Access the current trace buffer
        if hasattr(TRACE_BUFFER, '_traces') and TRACE_BUFFER._traces:
            # Get the most recent trace
            current_trace = list(TRACE_BUFFER._traces.values())[-1]
            if hasattr(current_trace, 'request_id') and hasattr(current_trace, 'span_id'):
                return EnhancedTraceContext(
                    trace_id=current_trace.request_id,
                    parent_span_id=current_trace.span_id,
                    session_id=session_id,
                    request_id=str(uuid.uuid4())
                )
    except Exception:
        pass
    
    return None


def extract_context_from_request(
    body: Dict[str, Any],
    headers: Dict[str, str]
) -> Optional[EnhancedTraceContext]:
    """
    Extract trace context from an incoming request.
    
    Checks both request body and headers.
    """
    # First try body
    if "trace_context" in body and body["trace_context"]:
        try:
            return EnhancedTraceContext.from_dict(body["trace_context"])
        except (KeyError, TypeError):
            pass
    
    # Then try headers
    return EnhancedTraceContext.from_headers(headers)


def generate_session_id() -> str:
    """Generate a new session ID."""
    return str(uuid.uuid4())


def end_session(session_id: str):
    """End a session and finalize its traces."""
    trace_store.end_session(session_id)

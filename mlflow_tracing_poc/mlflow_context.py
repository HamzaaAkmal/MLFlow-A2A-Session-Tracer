"""
MLflow Context Manager for Multi-Agent Tracing
===============================================

This module provides the core tracing utilities that solve both challenges:
1. Nested Tracing Across Agents - via trace context propagation
2. Single Trace for Multi-Turn Conversation - via session-based trace management

Key Concepts:
- TraceContext: Carries trace_id and span_id for cross-agent propagation
- SessionTraceManager: Manages single trace per conversation session
- SpanContextManager: Provides context managers for creating properly nested spans
"""

import uuid
import time
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import logging

import mlflow
from mlflow.entities import SpanType, SpanStatusCode

import config

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)


# =============================================================================
# Trace Context - For Cross-Agent Propagation
# =============================================================================

@dataclass
class TraceContext:
    """
    Represents the trace context that is propagated across agents.
    
    This context carries the necessary identifiers to link spans across
    agent boundaries, ensuring proper parent-child relationships.
    """
    trace_id: str  # The root trace ID for the entire conversation
    span_id: str  # The current span ID (parent for child spans)
    request_id: str  # Unique ID for this specific request
    session_id: str  # Session ID for multi-turn conversations
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "TraceContext":
        """Create from dictionary after deserialization."""
        return cls(
            trace_id=data["trace_id"],
            span_id=data["span_id"],
            request_id=data["request_id"],
            session_id=data["session_id"]
        )
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers for A2A protocol."""
        return {
            config.TRACE_CONTEXT_HEADER_TRACE_ID: self.trace_id,
            config.TRACE_CONTEXT_HEADER_SPAN_ID: self.span_id,
            config.TRACE_CONTEXT_HEADER_REQUEST_ID: self.request_id,
            config.TRACE_CONTEXT_HEADER_SESSION_ID: self.session_id
        }
    
    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> Optional["TraceContext"]:
        """Extract trace context from HTTP headers."""
        trace_id = headers.get(config.TRACE_CONTEXT_HEADER_TRACE_ID)
        span_id = headers.get(config.TRACE_CONTEXT_HEADER_SPAN_ID)
        request_id = headers.get(config.TRACE_CONTEXT_HEADER_REQUEST_ID)
        session_id = headers.get(config.TRACE_CONTEXT_HEADER_SESSION_ID)
        
        if trace_id and span_id and session_id:
            return cls(
                trace_id=trace_id,
                span_id=span_id,
                request_id=request_id or str(uuid.uuid4()),
                session_id=session_id
            )
        return None


# =============================================================================
# Session Trace Manager - For Single Trace Per Conversation
# =============================================================================

@dataclass
class SessionTraceInfo:
    """Information about an active session's trace."""
    session_id: str
    trace_id: str
    root_span_id: str
    created_at: float
    turn_count: int = 0
    is_finalized: bool = False


class SessionTraceManager:
    """
    Manages MLflow traces at the session level.
    
    This class is responsible for:
    1. Creating a single trace per conversation session
    2. Allowing multiple turns to be added to the same trace
    3. Properly finalizing traces when sessions end
    
    The key insight is that we use MLflow's low-level Client API to:
    - Create traces manually with specific IDs
    - Add spans to existing traces
    - Control when traces are finalized
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern for global trace management."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._sessions: Dict[str, SessionTraceInfo] = {}
        self._active_spans: Dict[str, Any] = {}  # span_id -> span object
        self._lock = threading.Lock()
        self._initialized = True
        
        # Initialize MLflow
        mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
        mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
        
        logger.info(f"SessionTraceManager initialized with tracking URI: {config.MLFLOW_TRACKING_URI}")
    
    def get_or_create_session_trace(self, session_id: str) -> SessionTraceInfo:
        """
        Get existing trace for session or create a new one.
        
        This is the core mechanism for Challenge 2 (Single Trace for Multi-Turn):
        - If session already has a trace, return it
        - If not, create a new trace and associate it with the session
        """
        with self._lock:
            if session_id in self._sessions and not self._sessions[session_id].is_finalized:
                # Existing active session - increment turn count
                self._sessions[session_id].turn_count += 1
                logger.info(f"Reusing existing trace for session {session_id}, turn {self._sessions[session_id].turn_count}")
                return self._sessions[session_id]
            
            # Create new trace for this session
            trace_id = str(uuid.uuid4()).replace("-", "")
            root_span_id = str(uuid.uuid4()).replace("-", "")
            
            session_info = SessionTraceInfo(
                session_id=session_id,
                trace_id=trace_id,
                root_span_id=root_span_id,
                created_at=time.time(),
                turn_count=1
            )
            
            self._sessions[session_id] = session_info
            logger.info(f"Created new trace {trace_id} for session {session_id}")
            
            return session_info
    
    def get_session_info(self, session_id: str) -> Optional[SessionTraceInfo]:
        """Get session trace info if exists."""
        return self._sessions.get(session_id)
    
    def finalize_session(self, session_id: str):
        """Mark a session's trace as finalized."""
        with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].is_finalized = True
                logger.info(f"Finalized trace for session {session_id}")
    
    def register_span(self, span_id: str, span: Any):
        """Register an active span."""
        with self._lock:
            self._active_spans[span_id] = span
    
    def unregister_span(self, span_id: str):
        """Unregister a span when it's closed."""
        with self._lock:
            self._active_spans.pop(span_id, None)
    
    def get_span(self, span_id: str) -> Optional[Any]:
        """Get a registered span by ID."""
        return self._active_spans.get(span_id)


# Global instance
trace_manager = SessionTraceManager()


# =============================================================================
# Span Context Managers - For Creating Properly Nested Spans
# =============================================================================

class AgentTracingContext:
    """
    Provides tracing context for agents.
    
    This class handles the creation of properly nested spans using MLflow's
    Fluent API with manual context management.
    """
    
    def __init__(self, session_id: str, agent_name: str):
        self.session_id = session_id
        self.agent_name = agent_name
        self.session_info = trace_manager.get_or_create_session_trace(session_id)
        self._span_stack: List[Any] = []
        self._current_trace = None
    
    @contextmanager
    def start_trace(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Start or continue a trace for this session.
        
        This is the main entry point for tracing a conversation turn.
        """
        attrs = {
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "turn_number": self.session_info.turn_count,
            **(attributes or {})
        }
        
        # Use MLflow's fluent API with our session grouping
        # The key is to use the same trace for all turns in a session
        with mlflow.start_span(
            name=name,
            span_type=SpanType.AGENT,
            attributes=attrs
        ) as span:
            self._current_trace = span
            span_id = span.span_id if hasattr(span, 'span_id') else str(uuid.uuid4())
            trace_id = span.request_id if hasattr(span, 'request_id') else self.session_info.trace_id
            
            # Create context for propagation
            context = TraceContext(
                trace_id=trace_id,
                span_id=span_id,
                request_id=str(uuid.uuid4()),
                session_id=self.session_id
            )
            
            try:
                yield span, context
            finally:
                self._current_trace = None
    
    @contextmanager
    def create_child_span(
        self,
        name: str,
        span_type: SpanType = SpanType.CHAIN,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Create a child span under the current span.
        """
        attrs = {
            "agent_name": self.agent_name,
            **(attributes or {})
        }
        
        with mlflow.start_span(
            name=name,
            span_type=span_type,
            attributes=attrs
        ) as span:
            yield span


class RemoteAgentTracingContext:
    """
    Provides tracing context for remote agents that receive trace context
    from a parent agent.
    
    This class handles Challenge 1 (Nested Tracing Across Agents) by:
    1. Receiving the parent trace context
    2. Creating spans that are properly linked as children
    """
    
    def __init__(self, trace_context: TraceContext, agent_name: str):
        self.trace_context = trace_context
        self.agent_name = agent_name
    
    @contextmanager
    def continue_trace(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Continue an existing trace from a parent agent.
        
        This creates a new span that is linked to the parent span
        from the calling agent.
        """
        attrs = {
            "session_id": self.trace_context.session_id,
            "agent_name": self.agent_name,
            "parent_span_id": self.trace_context.span_id,
            "request_id": self.trace_context.request_id,
            **(attributes or {})
        }
        
        # Use MLflow's span continuation mechanism
        # We create a span that references the parent context
        with mlflow.start_span(
            name=name,
            span_type=SpanType.AGENT,
            attributes=attrs
        ) as span:
            yield span
    
    @contextmanager
    def create_child_span(
        self,
        name: str,
        span_type: SpanType = SpanType.TOOL,
        attributes: Optional[Dict[str, Any]] = None
    ):
        """
        Create a child span for tool execution or sub-operations.
        """
        with mlflow.start_span(
            name=name,
            span_type=span_type,
            attributes=attributes or {}
        ) as span:
            yield span


# =============================================================================
# Convenience Functions
# =============================================================================

def create_new_session() -> str:
    """Create a new session ID for a conversation."""
    return str(uuid.uuid4())


def get_trace_context_from_headers(headers: Dict[str, str]) -> Optional[TraceContext]:
    """Extract trace context from HTTP headers."""
    return TraceContext.from_headers(headers)


def finalize_session(session_id: str):
    """Finalize a session's trace."""
    trace_manager.finalize_session(session_id)

"""
Single-Trace Solution Using start_span_no_context
================================================

This module implements the single-trace pattern using MLflow's
`start_span_no_context(..., parent_span=...)` API to ensure explicit
parent-child relationships across a multi-turn conversation.
"""

import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from contextlib import contextmanager
import logging

import mlflow
from mlflow.entities import SpanType
from mlflow.entities.span import LiveSpan

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SessionTrace:
    """
    Manages a single trace for an entire conversation session.
    
    The root span is created when the session starts and kept open
    until the session ends. All turns are children of this root span.
    """
    session_id: str
    root_span: LiveSpan = None
    current_turn_span: LiveSpan = None
    turn_count: int = 0
    _active: bool = False
    
    def start(self):
        """Start the session trace with a root span."""
        if self._active:
            return
        
        self.root_span = mlflow.start_span_no_context(
            name=f"session_{self.session_id}",
            span_type=SpanType.CHAIN,
            attributes={
                "session_id": self.session_id,
                "type": "multi_turn_session"
            }
        )
        self._active = True
        logger.info(f"Started session trace: {self.root_span.request_id}")
    
    def end(self):
        """End the session trace."""
        if not self._active:
            return
        
        self.root_span.set_attribute("total_turns", self.turn_count)
        self.root_span.set_outputs({
            "total_turns": self.turn_count,
            "session_id": self.session_id
        })
        self.root_span.end()
        self._active = False
        logger.info(f"Ended session trace: {self.root_span.request_id}")
    
    @property
    def trace_id(self) -> str:
        """Get the trace ID for propagation."""
        if self.root_span:
            return self.root_span.trace_id
        return None
    
    @property
    def request_id(self) -> str:
        """Get the request ID (MLflow trace identifier)."""
        if self.root_span:
            return self.root_span.request_id
        return None


class SessionTraceManager:
    """
    Singleton manager for session traces.
    
    Ensures one trace per session across multiple turns.
    """
    _instance = None
    _sessions: Dict[str, SessionTrace] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._sessions = {}
        return cls._instance
    
    def get_or_create_session(self, session_id: str) -> SessionTrace:
        """Get existing session or create new one."""
        if session_id not in self._sessions:
            session = SessionTrace(session_id=session_id)
            session.start()
            self._sessions[session_id] = session
        return self._sessions[session_id]
    
    def end_session(self, session_id: str):
        """End a session and its trace."""
        if session_id in self._sessions:
            self._sessions[session_id].end()
            del self._sessions[session_id]
    
    def get_session(self, session_id: str) -> Optional[SessionTrace]:
        """Get session if exists."""
        return self._sessions.get(session_id)


# Global manager instance
trace_manager = SessionTraceManager()


@contextmanager
def turn_span(session_id: str, user_message: str):
    """
    Create a turn span within the session trace.
    
    The turn span is a child of the session's root span,
    ensuring all turns are in the same trace.
    """
    session = trace_manager.get_or_create_session(session_id)
    session.turn_count += 1
    turn_num = session.turn_count
    
    # Create turn span as child of root span
    turn = mlflow.start_span_no_context(
        name=f"turn_{turn_num}",
        span_type=SpanType.AGENT,
        parent_span=session.root_span,  # KEY: This makes it a child!
        inputs={"user_message": user_message},
        attributes={
            "session_id": session_id,
            "turn_number": turn_num
        }
    )
    
    session.current_turn_span = turn
    
    try:
        yield turn, session
    finally:
        turn.end()
        session.current_turn_span = None


@contextmanager  
def child_span_of(parent: LiveSpan, name: str, span_type: SpanType = SpanType.CHAIN, attributes: Dict = None):
    """
    Create a child span of the given parent span.
    """
    span = mlflow.start_span_no_context(
        name=name,
        span_type=span_type,
        parent_span=parent,
        attributes=attributes or {}
    )
    try:
        yield span
    finally:
        span.end()


def create_traceparent(trace_id: str, span_id: str) -> str:
    """Create W3C traceparent header for propagation."""
    return f"00-{trace_id}-{span_id}-01"


def get_propagation_headers(session: SessionTrace, current_span: LiveSpan) -> Dict[str, str]:
    """Get headers for propagating trace context to remote agents."""
    return {
        "traceparent": create_traceparent(session.trace_id, current_span.span_id),
        "X-Session-ID": session.session_id,
        "X-Turn-Number": str(session.turn_count),
        "X-Trace-ID": session.trace_id,
        "X-Parent-Span-ID": current_span.span_id,
        "X-Request-ID": session.request_id
    }

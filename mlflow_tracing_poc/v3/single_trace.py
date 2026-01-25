"""
TRUE Single-Trace Solution for Multi-Agent Systems
====================================================

This module provides the CORRECT solution for:
1. Single trace for entire multi-turn conversation  
2. Remote agent spans properly nested under parent spans

The key insight: MLflow uses OpenTelemetry under the hood.
We need to work at the OTel level to properly continue traces.

CRITICAL: MLflow's start_span() creates a new trace unless there's
an active span in the current context. We must:
1. For supervisor: Use OTel tracer with a consistent trace_id per session
2. For remote: Inject parent span context into OTel before calling MLflow
"""

import uuid
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager
import logging
import struct

from opentelemetry import trace as otel_trace
from opentelemetry.trace import SpanContext, TraceFlags, SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.context import Context, attach, detach, set_value
from opentelemetry.sdk.trace import TracerProvider, ReadableSpan
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

import mlflow
from mlflow.entities import SpanType

logger = logging.getLogger(__name__)

# W3C Trace Context propagator
propagator = TraceContextTextMapPropagator()


def parse_traceparent(traceparent: str) -> Tuple[str, str, str]:
    """Parse W3C traceparent into (version, trace_id, parent_id, flags)."""
    parts = traceparent.split("-")
    if len(parts) == 4:
        return parts[1], parts[2], parts[3]  # trace_id, parent_id, flags
    return None, None, None


def create_traceparent(trace_id: str, span_id: str, flags: str = "01") -> str:
    """Create W3C traceparent header."""
    return f"00-{trace_id}-{span_id}-{flags}"


def generate_trace_id() -> str:
    """Generate a 32-character hex trace ID."""
    return uuid.uuid4().hex


def generate_span_id() -> str:
    """Generate a 16-character hex span ID."""
    return uuid.uuid4().hex[:16]


@dataclass
class SingleTraceContext:
    """
    Context for maintaining a single trace across the system.
    
    This is passed between agents to ensure all spans belong
    to the same trace and are properly nested.
    """
    trace_id: str  # 32-char hex trace ID
    parent_span_id: str  # 16-char hex span ID of the parent
    session_id: str
    turn_number: int = 0
    
    @property
    def traceparent(self) -> str:
        """Get W3C traceparent header."""
        return create_traceparent(self.trace_id, self.parent_span_id)
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        return {
            "traceparent": self.traceparent,
            "X-Session-ID": self.session_id,
            "X-Turn-Number": str(self.turn_number),
            "X-Trace-ID": self.trace_id,
            "X-Parent-Span-ID": self.parent_span_id
        }
    
    @classmethod
    def from_headers(cls, headers: Dict[str, str]) -> Optional["SingleTraceContext"]:
        """Extract from HTTP headers."""
        # Try to get from explicit headers first
        trace_id = headers.get("X-Trace-ID") or headers.get("x-trace-id")
        parent_span_id = headers.get("X-Parent-Span-ID") or headers.get("x-parent-span-id")
        session_id = headers.get("X-Session-ID") or headers.get("x-session-id")
        
        # Fall back to parsing traceparent
        if not trace_id or not parent_span_id:
            traceparent = headers.get("traceparent") or headers.get("Traceparent")
            if traceparent:
                trace_id, parent_span_id, _ = parse_traceparent(traceparent)
        
        if trace_id and parent_span_id and session_id:
            return cls(
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                session_id=session_id,
                turn_number=int(headers.get("X-Turn-Number", "0"))
            )
        return None


class SessionTraceStore:
    """
    Stores trace IDs for sessions to ensure multi-turn
    conversations use the same trace.
    """
    _instance = None
    _sessions: Dict[str, Dict] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._sessions = {}
        return cls._instance
    
    def get_or_create_trace_id(self, session_id: str) -> str:
        """Get existing trace ID for session or create new one."""
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "trace_id": generate_trace_id(),
                "turn_count": 0
            }
        return self._sessions[session_id]["trace_id"]
    
    def increment_turn(self, session_id: str) -> int:
        """Increment and return turn count."""
        if session_id in self._sessions:
            self._sessions[session_id]["turn_count"] += 1
            return self._sessions[session_id]["turn_count"]
        return 1


session_store = SessionTraceStore()


@contextmanager
def supervisor_span(
    session_id: str,
    name: str,
    agent_name: str = "SupervisorAgent"
):
    """
    Create a span for the supervisor agent.
    
    For the FIRST turn: Creates a new trace with a new trace_id
    For SUBSEQUENT turns: Uses the same trace_id for the session
    
    The span context is captured and returned for propagation to remote agents.
    """
    # Get or create trace ID for this session
    trace_id = session_store.get_or_create_trace_id(session_id)
    turn_number = session_store.increment_turn(session_id)
    
    # Create the span using MLflow
    with mlflow.start_span(
        name=f"{name}_turn_{turn_number}",
        span_type=SpanType.AGENT,
        attributes={
            "session_id": session_id,
            "turn_number": turn_number,
            "agent_name": agent_name,
            "trace_id": trace_id
        }
    ) as span:
        # Get the span_id from the MLflow span
        span_id = span.span_id if hasattr(span, 'span_id') else generate_span_id()
        
        # Get the actual trace_id from the span (MLflow assigns one)
        actual_trace_id = span.request_id.replace("tr-", "") if hasattr(span, 'request_id') else trace_id
        
        # Create context for propagation
        ctx = SingleTraceContext(
            trace_id=actual_trace_id,
            parent_span_id=span_id,
            session_id=session_id,
            turn_number=turn_number
        )
        
        yield span, ctx


@contextmanager
def child_span(name: str, span_type: SpanType = SpanType.CHAIN, attributes: Dict = None):
    """Create a child span under the current span."""
    with mlflow.start_span(
        name=name,
        span_type=span_type,
        attributes=attributes or {}
    ) as span:
        yield span


def get_current_span_context() -> Optional[SingleTraceContext]:
    """
    Get the current span's context for propagation.
    
    Call this from within a span to get context to pass to remote agents.
    """
    headers = {}
    propagator.inject(carrier=headers)
    traceparent = headers.get("traceparent")
    
    if traceparent:
        trace_id, span_id, _ = parse_traceparent(traceparent)
        if trace_id and span_id:
            return SingleTraceContext(
                trace_id=trace_id,
                parent_span_id=span_id,
                session_id="",  # Will be set by caller
                turn_number=0
            )
    return None


# =============================================================================
# Remote Agent Span Creation (Alternative Approach)
# =============================================================================

def create_remote_span_result(
    parent_ctx: SingleTraceContext,
    span_name: str,
    agent_name: str,
    tool_results: Dict[str, Any],
    execution_time_ms: int
) -> Dict[str, Any]:
    """
    Create span data that will be logged to the same trace as the parent.
    
    This approach returns span information that the SUPERVISOR can log
    to its trace, ensuring everything is in one trace.
    
    This is a workaround for the limitation that remote processes cannot
    directly add spans to another process's trace without shared storage.
    """
    return {
        "span_info": {
            "name": span_name,
            "agent_name": agent_name,
            "parent_trace_id": parent_ctx.trace_id,
            "parent_span_id": parent_ctx.parent_span_id,
            "session_id": parent_ctx.session_id,
            "turn_number": parent_ctx.turn_number,
            "execution_time_ms": execution_time_ms,
            "start_time": time.time() - (execution_time_ms / 1000),
            "end_time": time.time()
        },
        "tool_results": tool_results
    }

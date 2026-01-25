"""
Configuration for MLflow Tracing PoC
=====================================

This module contains all configuration settings for the multi-agent
tracing solution.
"""

import os

# =============================================================================
# MLflow Configuration
# =============================================================================

# MLflow Tracking URI - defaults to local file store
# Change to your MLflow server URL if using a remote server
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "./mlruns")

# Experiment name for all traces
MLFLOW_EXPERIMENT_NAME = os.environ.get("MLFLOW_EXPERIMENT_NAME", "Multi-Agent-Tracing-PoC")

# =============================================================================
# Agent Configuration
# =============================================================================

# Supervisor Agent settings
SUPERVISOR_AGENT_NAME = "SupervisorAgent"
SUPERVISOR_AGENT_VERSION = "1.0.0"

# Remote Superagent settings
REMOTE_SUPERAGENT_NAME = "RemoteSuperagent"
REMOTE_SUPERAGENT_VERSION = "1.0.0"
REMOTE_SUPERAGENT_HOST = os.environ.get("REMOTE_AGENT_HOST", "127.0.0.1")
REMOTE_SUPERAGENT_PORT = int(os.environ.get("REMOTE_AGENT_PORT", "5001"))
REMOTE_SUPERAGENT_URL = f"http://{REMOTE_SUPERAGENT_HOST}:{REMOTE_SUPERAGENT_PORT}"

# =============================================================================
# A2A Protocol Configuration
# =============================================================================

# Header names for trace context propagation
TRACE_CONTEXT_HEADER_TRACE_ID = "X-MLflow-Trace-ID"
TRACE_CONTEXT_HEADER_SPAN_ID = "X-MLflow-Span-ID"
TRACE_CONTEXT_HEADER_REQUEST_ID = "X-MLflow-Request-ID"
TRACE_CONTEXT_HEADER_SESSION_ID = "X-Session-ID"

# =============================================================================
# Session Configuration
# =============================================================================

# Default session timeout in seconds (for cleanup purposes)
SESSION_TIMEOUT_SECONDS = 3600  # 1 hour

# =============================================================================
# Logging Configuration
# =============================================================================

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

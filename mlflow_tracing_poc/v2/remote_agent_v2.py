"""
Remote Superagent V2 - With Proper Distributed Tracing
========================================================

This version uses OpenTelemetry's W3C Trace Context propagation
to ensure spans are properly nested under the calling agent's span.
"""

import time
import uuid
import random
from typing import Dict, Any, Optional
import logging

from flask import Flask, request, jsonify
import mlflow
from mlflow.entities import SpanType, SpanStatusCode

from distributed_tracing import (
    continue_distributed_trace,
    create_child_span,
    DistributedTraceContext
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# MLflow setup
mlflow.set_tracking_uri("./mlruns")
mlflow.set_experiment("Multi-Agent-Tracing-V2")


# =============================================================================
# Dummy Tools
# =============================================================================

def search_tool(query: str) -> Dict[str, Any]:
    """Simulate search."""
    time.sleep(random.uniform(0.1, 0.2))
    return {
        "results": [
            {"title": f"Result 1 for '{query}'", "score": 0.95},
            {"title": f"Result 2 for '{query}'", "score": 0.87},
            {"title": f"Result 3 for '{query}'", "score": 0.76}
        ],
        "total_results": 3
    }


def analyze_tool(data: Any) -> Dict[str, Any]:
    """Simulate analysis."""
    time.sleep(random.uniform(0.2, 0.4))
    return {
        "summary": "Analysis complete",
        "insights": ["Insight 1", "Insight 2", "Insight 3"],
        "confidence": random.uniform(0.85, 0.99)
    }


# =============================================================================
# Flask Routes
# =============================================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "agent": "RemoteSuperagent", "version": "2.0.0"})


@app.route("/execute", methods=["POST"])
def execute():
    """
    Execute a task with distributed trace continuation.
    
    This endpoint extracts the parent trace context and creates
    spans that are properly nested under the caller's span.
    """
    try:
        data = request.get_json()
        headers = dict(request.headers)
        
        # Log received headers for debugging
        logger.info(f"Received headers: traceparent={headers.get('Traceparent', 'NONE')}")
        
        # Continue the distributed trace from parent
        with continue_distributed_trace(
            headers=headers,
            name="RemoteSuperagent.execute",
            agent_name="RemoteSuperagent"
        ) as (agent_span, dist_ctx):
            
            agent_span.set_inputs({"request": data})
            
            # Extract task info
            payload = data.get("payload", {})
            task_type = payload.get("task_type", "general")
            input_data = payload.get("input_data", {})
            message = input_data.get("message", "")
            
            # Execute appropriate tool with nested span
            with create_child_span(
                name=f"tool.{task_type}",
                span_type=SpanType.TOOL,
                attributes={"tool_name": task_type}
            ) as tool_span:
                tool_span.set_inputs({"message": message})
                
                if task_type == "search":
                    result = search_tool(message)
                elif task_type == "analyze":
                    result = analyze_tool(input_data)
                else:
                    result = {"processed": True, "message": message[:50]}
                
                tool_span.set_outputs(result)
            
            # Format response
            response = {
                "message_type": "task_response",
                "payload": {
                    "status": "success",
                    "result": {
                        "data": result,
                        "message": f"Task {task_type} completed successfully."
                    }
                }
            }
            
            agent_span.set_outputs(response)
            agent_span.set_status(SpanStatusCode.OK)
            
            return jsonify(response)
            
    except Exception as e:
        logger.exception("Error in /execute")
        return jsonify({
            "message_type": "error",
            "payload": {"error": str(e)}
        }), 500


if __name__ == "__main__":
    logger.info("Starting Remote Superagent V2 on port 5001")
    app.run(host="127.0.0.1", port=5001, debug=False, threaded=True)

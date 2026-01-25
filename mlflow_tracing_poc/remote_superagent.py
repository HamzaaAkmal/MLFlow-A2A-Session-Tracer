"""
Remote Superagent (Flask Server)
=================================

This module implements the Remote Superagent that:
1. Runs as a separate Flask server on a different port
2. Receives A2A requests with trace context
3. Creates child spans properly nested under the parent span
4. Executes dummy tools and returns results

This agent demonstrates Challenge 1 (Nested Tracing Across Agents) by:
- Extracting trace context from incoming requests
- Creating spans that are linked to the parent trace
"""

import time
import uuid
import random
from typing import Dict, Any, Optional
import logging

from flask import Flask, request, jsonify
import mlflow
from mlflow.entities import SpanType

import config
from mlflow_context import TraceContext, RemoteAgentTracingContext
from a2a_protocol import (
    A2AMessage,
    A2AMessageType,
    extract_trace_context_from_request,
    create_response_message
)

# Configure logging
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)

# MLflow setup
mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)


# =============================================================================
# Dummy Tools for Demonstration
# =============================================================================

class DummyToolkit:
    """
    A collection of dummy tools for demonstration purposes.
    
    In a real system, these would be actual tool implementations.
    """
    
    @staticmethod
    def search_tool(query: str, **kwargs) -> Dict[str, Any]:
        """Simulate a search operation."""
        time.sleep(random.uniform(0.1, 0.3))  # Simulate latency
        return {
            "results": [
                {"title": f"Result 1 for '{query}'", "score": 0.95},
                {"title": f"Result 2 for '{query}'", "score": 0.87},
                {"title": f"Result 3 for '{query}'", "score": 0.76}
            ],
            "total_results": 3,
            "query": query
        }
    
    @staticmethod
    def calculate_tool(expression: str, **kwargs) -> Dict[str, Any]:
        """Simulate a calculation operation."""
        time.sleep(random.uniform(0.05, 0.15))
        try:
            # Simple safe eval for demo (in production, use a proper parser)
            result = eval(expression, {"__builtins__": {}}, {})
            return {"result": result, "expression": expression}
        except Exception as e:
            return {"error": str(e), "expression": expression}
    
    @staticmethod
    def analyze_tool(data: Any, **kwargs) -> Dict[str, Any]:
        """Simulate an analysis operation."""
        time.sleep(random.uniform(0.2, 0.5))  # Analysis takes longer
        return {
            "summary": f"Analysis complete for input of type {type(data).__name__}",
            "insights": [
                "Insight 1: Data patterns detected",
                "Insight 2: Anomalies identified",
                "Insight 3: Recommendations generated"
            ],
            "confidence": random.uniform(0.85, 0.99)
        }
    
    @staticmethod
    def general_tool(input_data: Any, **kwargs) -> Dict[str, Any]:
        """Handle general tasks."""
        time.sleep(random.uniform(0.1, 0.2))
        return {
            "processed": True,
            "input_summary": str(input_data)[:100],
            "timestamp": time.time()
        }


toolkit = DummyToolkit()


# =============================================================================
# Remote Agent Core Logic
# =============================================================================

class RemoteSuperagent:
    """
    The Remote Superagent that processes delegated tasks.
    
    This agent receives trace context from the Supervisor Agent and
    creates properly nested spans for all its operations.
    """
    
    def __init__(self):
        self.name = config.REMOTE_SUPERAGENT_NAME
        self.version = config.REMOTE_SUPERAGENT_VERSION
        
        # Tool registry
        self.tools = {
            "search": toolkit.search_tool,
            "calculate": toolkit.calculate_tool,
            "analyze": toolkit.analyze_tool,
            "general": toolkit.general_tool
        }
        
        logger.info(f"RemoteSuperagent initialized: {self.name} v{self.version}")
    
    def process_task(
        self,
        task_id: str,
        task_type: str,
        input_data: Dict[str, Any],
        trace_context: Optional[TraceContext] = None
    ) -> Dict[str, Any]:
        """
        Process a delegated task with proper MLflow tracing.
        
        This method demonstrates Challenge 1 by:
        1. Using the received trace context
        2. Creating spans that link to the parent trace
        """
        logger.info(f"Processing task {task_id} of type {task_type}")
        
        # Log trace context for debugging
        if trace_context:
            logger.debug(f"Received trace context: {trace_context.to_dict()}")
        
        # Start a span for this remote agent's processing
        # The key is using the same trace context to ensure proper nesting
        with mlflow.start_span(
            name=f"RemoteSuperagent.{task_type}",
            span_type=SpanType.AGENT,
            attributes={
                "task_id": task_id,
                "task_type": task_type,
                "agent_name": self.name,
                "agent_version": self.version,
                "parent_trace_id": trace_context.trace_id if trace_context else None,
                "parent_span_id": trace_context.span_id if trace_context else None,
                "session_id": trace_context.session_id if trace_context else None
            }
        ) as agent_span:
            agent_span.set_inputs({
                "task_id": task_id,
                "task_type": task_type,
                "input_data": input_data
            })
            
            try:
                # Execute the appropriate tool
                with mlflow.start_span(
                    name=f"tool.{task_type}",
                    span_type=SpanType.TOOL,
                    attributes={
                        "tool_name": task_type,
                        "execution_id": str(uuid.uuid4())
                    }
                ) as tool_span:
                    tool_span.set_inputs(input_data)
                    
                    # Get the tool and execute
                    tool_func = self.tools.get(task_type, self.tools["general"])
                    
                    # Extract relevant args for the tool
                    if task_type == "search":
                        tool_result = tool_func(
                            query=input_data.get("message", ""),
                            **input_data
                        )
                    elif task_type == "calculate":
                        tool_result = tool_func(
                            expression=input_data.get("message", "1+1"),
                            **input_data
                        )
                    elif task_type == "analyze":
                        tool_result = tool_func(
                            data=input_data,
                            **input_data
                        )
                    else:
                        tool_result = tool_func(input_data=input_data)
                    
                    tool_span.set_outputs(tool_result)
                
                # Post-process the results
                with mlflow.start_span(
                    name="post_processing",
                    span_type=SpanType.CHAIN,
                    attributes={"operation": "result_formatting"}
                ) as post_span:
                    processed_result = self._post_process(tool_result, task_type)
                    post_span.set_outputs(processed_result)
                
                # Set final outputs
                result = {
                    "status": "success",
                    "task_id": task_id,
                    "data": processed_result,
                    "message": self._generate_response_message(processed_result, task_type)
                }
                
                agent_span.set_outputs(result)
                agent_span.set_status(mlflow.entities.SpanStatusCode.OK)
                
                return result
                
            except Exception as e:
                logger.error(f"Error processing task {task_id}: {e}")
                agent_span.set_status(mlflow.entities.SpanStatusCode.ERROR)
                agent_span.set_attribute("error", str(e))
                
                return {
                    "status": "error",
                    "task_id": task_id,
                    "error": str(e)
                }
    
    def _post_process(self, tool_result: Dict[str, Any], task_type: str) -> Dict[str, Any]:
        """Post-process tool results."""
        return {
            "raw_result": tool_result,
            "processed_at": time.time(),
            "task_type": task_type
        }
    
    def _generate_response_message(self, result: Dict[str, Any], task_type: str) -> str:
        """Generate a human-readable response message."""
        raw_result = result.get("raw_result", {})
        
        if task_type == "search":
            count = raw_result.get("total_results", 0)
            return f"Found {count} results for your search query."
        elif task_type == "calculate":
            calc_result = raw_result.get("result", "N/A")
            return f"Calculation result: {calc_result}"
        elif task_type == "analyze":
            insights = raw_result.get("insights", [])
            return f"Analysis complete with {len(insights)} insights generated."
        else:
            return "Task processed successfully."


# Create global agent instance
remote_agent = RemoteSuperagent()


# =============================================================================
# Flask Routes
# =============================================================================

@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "agent": remote_agent.name,
        "version": remote_agent.version
    })


@app.route("/execute", methods=["POST"])
def execute_task():
    """
    Execute a delegated task.
    
    This endpoint receives A2A messages and processes them with
    proper MLflow trace context propagation.
    """
    try:
        # Parse the incoming A2A message
        data = request.get_json()
        message = A2AMessage.from_dict(data)
        
        # Extract trace context from request
        # Check both message body and headers
        trace_context = extract_trace_context_from_request(
            data,
            dict(request.headers)
        )
        
        if trace_context:
            logger.info(f"Received request with trace context: session={trace_context.session_id}")
        else:
            logger.warning("Received request without trace context")
        
        # Extract task details from payload
        payload = message.payload
        task_id = payload.get("task_id", str(uuid.uuid4()))
        task_type = payload.get("task_type", "general")
        input_data = payload.get("input_data", {})
        
        # Process the task with tracing
        result = remote_agent.process_task(
            task_id=task_id,
            task_type=task_type,
            input_data=input_data,
            trace_context=trace_context
        )
        
        # Create response message
        response = create_response_message(
            status=result.get("status", "success"),
            result=result,
            trace_context=trace_context,
            metadata={
                "agent": remote_agent.name,
                "processed_at": time.time()
            }
        )
        
        return jsonify(response.to_dict())
        
    except Exception as e:
        logger.error(f"Error in /execute: {e}")
        error_response = A2AMessage(
            message_type=A2AMessageType.ERROR.value,
            payload={"error": str(e)}
        )
        return jsonify(error_response.to_dict()), 500


@app.route("/tool", methods=["POST"])
def call_tool():
    """
    Direct tool call endpoint.
    
    Allows calling individual tools with trace context.
    """
    try:
        data = request.get_json()
        message = A2AMessage.from_dict(data)
        
        # Extract trace context
        trace_context = extract_trace_context_from_request(
            data,
            dict(request.headers)
        )
        
        # Get tool details
        tool_name = message.payload.get("tool_name", "general")
        tool_args = message.payload.get("tool_args", {})
        
        # Execute tool with tracing
        with mlflow.start_span(
            name=f"direct_tool.{tool_name}",
            span_type=SpanType.TOOL,
            attributes={
                "tool_name": tool_name,
                "session_id": trace_context.session_id if trace_context else None
            }
        ) as span:
            span.set_inputs(tool_args)
            
            tool_func = remote_agent.tools.get(tool_name, remote_agent.tools["general"])
            result = tool_func(**tool_args)
            
            span.set_outputs(result)
        
        response = A2AMessage(
            message_type=A2AMessageType.TOOL_RESULT.value,
            payload={"result": result},
            trace_context=trace_context.to_dict() if trace_context else None
        )
        
        return jsonify(response.to_dict())
        
    except Exception as e:
        logger.error(f"Error in /tool: {e}")
        return jsonify({
            "message_type": "error",
            "payload": {"error": str(e)}
        }), 500


# =============================================================================
# Server Entry Point
# =============================================================================

def run_server(host: str = None, port: int = None, debug: bool = False):
    """Run the Remote Superagent server."""
    host = host or config.REMOTE_SUPERAGENT_HOST
    port = port or config.REMOTE_SUPERAGENT_PORT
    
    logger.info(f"Starting Remote Superagent on {host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    run_server(debug=True)

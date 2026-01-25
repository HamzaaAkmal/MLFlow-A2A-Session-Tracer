"""
V4 Remote Agent - Returns work log for supervisor to trace
===========================================================

The remote agent does its work but instead of creating spans directly,
it returns a structured work log that the supervisor uses to create
child spans in its own trace.

This pattern ensures all spans end up in the same trace because
they're all created in the supervisor's process.
"""

import time
from flask import Flask, request, jsonify
from typing import Dict, Any, List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


class RemoteSuperagent:
    """
    Remote agent that performs work and returns a work log.
    
    The work log is used by the supervisor to create spans,
    ensuring everything ends up in the same trace.
    """
    
    def __init__(self):
        self.name = "RemoteSuperagent"
        self.tools = {
            "web_search": self._web_search,
            "data_analysis": self._data_analysis,
            "knowledge_lookup": self._knowledge_lookup
        }
    
    def execute(self, query: str, task_type: str = "general") -> Dict[str, Any]:
        """
        Execute a task and return results with work log.
        
        The work log describes what operations were performed,
        which the supervisor will use to create child spans.
        """
        work_log = []
        results = {}
        
        # Determine which tools to use based on task type
        if task_type == "search":
            # Run web search
            start_time = time.time()
            search_result = self.tools["web_search"](query)
            duration_ms = int((time.time() - start_time) * 1000)
            
            work_log.append({
                "operation": "web_search",
                "type": "TOOL",
                "duration_ms": duration_ms,
                "input": {"query": query},
                "output": {"result_count": len(search_result)}
            })
            results["search_results"] = search_result
            
            # Also do knowledge lookup
            start_time = time.time()
            knowledge = self.tools["knowledge_lookup"](query)
            duration_ms = int((time.time() - start_time) * 1000)
            
            work_log.append({
                "operation": "knowledge_lookup",
                "type": "TOOL",
                "duration_ms": duration_ms,
                "input": {"topic": query},
                "output": {"found": knowledge.get("found", False)}
            })
            results["knowledge"] = knowledge
            
        elif task_type == "analyze":
            # Run analysis
            start_time = time.time()
            analysis = self.tools["data_analysis"](query)
            duration_ms = int((time.time() - start_time) * 1000)
            
            work_log.append({
                "operation": "data_analysis",
                "type": "TOOL",
                "duration_ms": duration_ms,
                "input": {"data": query},
                "output": {"analysis_complete": True}
            })
            results["analysis"] = analysis
            
        else:
            # General task - do search and analysis
            start_time = time.time()
            search_result = self.tools["web_search"](query)
            duration_ms = int((time.time() - start_time) * 1000)
            
            work_log.append({
                "operation": "web_search",
                "type": "TOOL",
                "duration_ms": duration_ms,
                "input": {"query": query},
                "output": {"result_count": len(search_result)}
            })
            results["search_results"] = search_result
        
        return {
            "agent_name": self.name,
            "task_type": task_type,
            "result": results,
            "work_log": work_log
        }
    
    def _web_search(self, query: str) -> List[Dict]:
        """Simulate web search tool."""
        time.sleep(0.1)  # Simulate latency
        return [
            {"title": f"Result 1 for: {query}", "url": "http://example.com/1", "score": 0.95},
            {"title": f"Result 2 for: {query}", "url": "http://example.com/2", "score": 0.87},
            {"title": f"Result 3 for: {query}", "url": "http://example.com/3", "score": 0.82}
        ]
    
    def _data_analysis(self, data: str) -> Dict:
        """Simulate data analysis tool."""
        time.sleep(0.15)  # Simulate latency
        return {
            "summary": f"Analysis of: {data[:50]}...",
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "confidence": 0.89
        }
    
    def _knowledge_lookup(self, topic: str) -> Dict:
        """Simulate knowledge base lookup."""
        time.sleep(0.08)  # Simulate latency
        return {
            "topic": topic,
            "found": True,
            "facts": [
                f"Fact about {topic}: It's important",
                f"Another fact about {topic}: It's widely used"
            ]
        }


# Create agent instance
agent = RemoteSuperagent()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "agent": "RemoteSuperagent",
        "version": "4.0.0"
    })


@app.route("/.well-known/agent.json", methods=["GET"])
def agent_card():
    """A2A protocol agent card."""
    return jsonify({
        "name": "RemoteSuperagent",
        "description": "A remote agent with search, analysis, and knowledge tools",
        "version": "4.0.0",
        "capabilities": ["search", "analyze", "knowledge"],
        "endpoints": {
            "execute": "/execute",
            "health": "/health"
        }
    })


@app.route("/execute", methods=["POST"])
def execute():
    """Execute a task."""
    data = request.json or {}
    
    query = data.get("content", "")
    metadata = data.get("metadata", {})
    task_type = metadata.get("task_type", "general")
    
    # Log received trace context (for debugging)
    trace_context = {
        "traceparent": request.headers.get("traceparent"),
        "x_session_id": request.headers.get("X-Session-ID"),
        "x_trace_id": request.headers.get("X-Trace-ID"),
        "x_parent_span_id": request.headers.get("X-Parent-Span-ID")
    }
    logger.info(f"Received request with trace context: {trace_context}")
    
    # Execute the task
    result = agent.execute(query, task_type)
    
    # Include trace context in response for verification
    result["received_trace_context"] = trace_context
    
    return jsonify(result)


def run_server(host: str = "0.0.0.0", port: int = 5001):
    """Run the remote agent server."""
    print("\n" + "="*60)
    print("REMOTE AGENT V4 SERVER")
    print("Pattern: Returns work log for supervisor to trace")
    print("="*60)
    print(f"\nEndpoints:")
    print(f"  - GET  /health")
    print(f"  - GET  /.well-known/agent.json")
    print(f"  - POST /execute")
    print(f"\nStarting server on http://localhost:{port}")
    print("="*60 + "\n")
    
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_server()

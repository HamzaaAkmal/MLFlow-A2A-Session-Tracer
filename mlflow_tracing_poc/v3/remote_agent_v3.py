"""
Remote Agent V3 - Returns Work Log for Supervisor to Trace
===========================================================

This remote agent performs work and returns a structured log
of what it did. The SUPERVISOR then creates spans representing
this work, ensuring everything is in one trace.

This is the pattern that works with MLflow's architecture:
- Remote agent does the actual work
- Remote agent returns metadata about what it did
- Supervisor creates spans in its own trace context
"""

import time
import json
from typing import Dict, Any, List
from dataclasses import dataclass, asdict
from flask import Flask, request, jsonify
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@dataclass
class WorkLogEntry:
    """Log entry for work performed by this agent."""
    operation: str
    type: str  # TOOL, CHAIN, LLM, etc.
    input: Dict[str, Any]
    output: Dict[str, Any]
    duration_ms: int
    timestamp: float


class RemoteSuperagentV3:
    """
    Remote agent that performs work and logs it for tracing.
    
    Instead of creating its own spans (which would be in a separate trace),
    this agent returns a work log that the supervisor uses to create spans.
    """
    
    def __init__(self):
        self.name = "RemoteSuperagent"
        self.tools = {
            "web_search": self._web_search,
            "data_analysis": self._data_analysis,
            "knowledge_lookup": self._knowledge_lookup
        }
        self._work_log: List[WorkLogEntry] = []
    
    def execute(
        self,
        content: str,
        task_type: str = "search",
        trace_context: Dict[str, str] = None
    ) -> Dict[str, Any]:
        """
        Execute the task and return results with work log.
        
        Args:
            content: The task content/query
            task_type: Type of task (search, analyze, etc.)
            trace_context: Trace context from supervisor (for logging purposes)
        
        Returns:
            Dict with result and work_log for supervisor to trace
        """
        self._work_log = []  # Reset work log
        
        logger.info(f"Executing task: {task_type}")
        if trace_context:
            logger.info(f"Received trace context: {trace_context}")
        
        start_time = time.time()
        
        # Execute appropriate tools based on task type
        if task_type == "search":
            result = self._execute_search(content)
        elif task_type == "analyze":
            result = self._execute_analysis(content)
        else:
            result = self._execute_general(content)
        
        total_time_ms = int((time.time() - start_time) * 1000)
        
        return {
            "agent_name": self.name,
            "result": result,
            "work_log": [asdict(entry) for entry in self._work_log],
            "total_execution_time_ms": total_time_ms,
            "trace_context_received": trace_context
        }
    
    def _log_work(
        self,
        operation: str,
        work_type: str,
        input_data: Dict,
        output_data: Dict,
        duration_ms: int
    ):
        """Log work performed for later tracing by supervisor."""
        self._work_log.append(WorkLogEntry(
            operation=operation,
            type=work_type,
            input=input_data,
            output=output_data,
            duration_ms=duration_ms,
            timestamp=time.time()
        ))
    
    def _execute_search(self, query: str) -> Dict[str, Any]:
        """Execute search workflow."""
        # Step 1: Web search
        start = time.time()
        search_results = self._web_search(query)
        duration = int((time.time() - start) * 1000)
        self._log_work(
            "web_search",
            "TOOL",
            {"query": query},
            {"results": search_results},
            duration
        )
        
        # Step 2: Knowledge lookup
        start = time.time()
        knowledge = self._knowledge_lookup(query)
        duration = int((time.time() - start) * 1000)
        self._log_work(
            "knowledge_lookup",
            "TOOL",
            {"query": query},
            {"knowledge": knowledge},
            duration
        )
        
        return {
            "search_results": search_results,
            "knowledge": knowledge
        }
    
    def _execute_analysis(self, content: str) -> Dict[str, Any]:
        """Execute analysis workflow."""
        # Step 1: Data analysis
        start = time.time()
        analysis = self._data_analysis(content)
        duration = int((time.time() - start) * 1000)
        self._log_work(
            "data_analysis",
            "TOOL",
            {"content": content},
            {"analysis": analysis},
            duration
        )
        
        return {"analysis": analysis}
    
    def _execute_general(self, content: str) -> Dict[str, Any]:
        """Execute general workflow."""
        start = time.time()
        result = self._knowledge_lookup(content)
        duration = int((time.time() - start) * 1000)
        self._log_work(
            "general_lookup",
            "TOOL",
            {"content": content},
            {"result": result},
            duration
        )
        
        return {"result": result}
    
    # Tool implementations
    def _web_search(self, query: str) -> List[Dict]:
        """Simulate web search."""
        time.sleep(0.1)  # Simulate latency
        return [
            {"title": f"Result 1 for: {query}", "url": "http://example.com/1", "score": 0.95},
            {"title": f"Result 2 for: {query}", "url": "http://example.com/2", "score": 0.87},
            {"title": f"Result 3 for: {query}", "url": "http://example.com/3", "score": 0.82}
        ]
    
    def _data_analysis(self, content: str) -> Dict[str, Any]:
        """Simulate data analysis."""
        time.sleep(0.15)  # Simulate processing
        return {
            "summary": f"Analysis of: {content[:50]}...",
            "key_points": ["Point 1", "Point 2", "Point 3"],
            "confidence": 0.89
        }
    
    def _knowledge_lookup(self, query: str) -> Dict[str, Any]:
        """Simulate knowledge base lookup."""
        time.sleep(0.08)  # Simulate lookup
        return {
            "found": True,
            "topic": query,
            "facts": [
                f"Fact about {query}: It's important",
                f"Another fact about {query}: It's widely used"
            ]
        }


# Flask routes
agent = RemoteSuperagentV3()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "agent": agent.name})


@app.route("/.well-known/agent.json", methods=["GET"])
def agent_card():
    """A2A Agent Card."""
    return jsonify({
        "name": agent.name,
        "description": "Remote superagent for search and analysis",
        "version": "3.0.0",
        "protocol": "A2A",
        "capabilities": {
            "tools": list(agent.tools.keys()),
            "tracing": "work_log_pattern"  # Indicates this agent uses work log pattern
        },
        "endpoints": {
            "execute": "/execute",
            "health": "/health"
        }
    })


@app.route("/execute", methods=["POST"])
def execute():
    """Execute a task and return results with work log."""
    try:
        data = request.json
        content = data.get("content", "")
        metadata = data.get("metadata", {})
        task_type = metadata.get("task_type", "search")
        trace_context = metadata.get("trace_context", {})
        
        logger.info(f"Received request - Task: {task_type}")
        logger.info(f"Trace context: {trace_context}")
        
        result = agent.execute(
            content=content,
            task_type=task_type,
            trace_context=trace_context
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Execution error: {e}")
        return jsonify({"error": str(e)}), 500


def main():
    """Run the remote agent server."""
    print("\n" + "="*60)
    print("REMOTE AGENT V3 SERVER")
    print("Pattern: Returns work log for supervisor to trace")
    print("="*60)
    print("\nEndpoints:")
    print("  - GET  /health")
    print("  - GET  /.well-known/agent.json")
    print("  - POST /execute")
    print("\nStarting server on http://localhost:5001")
    print("="*60 + "\n")
    
    app.run(host="0.0.0.0", port=5001, debug=False)


if __name__ == "__main__":
    main()

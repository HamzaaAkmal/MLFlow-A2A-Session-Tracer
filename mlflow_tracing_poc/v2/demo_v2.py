"""
Demo V2 - Testing Distributed Tracing
======================================

This demo tests that:
1. All conversation turns are in properly grouped traces
2. Remote agent spans are NESTED under supervisor spans
"""

import time
import sys
import requests
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_remote_agent():
    """Check if remote agent is running."""
    try:
        r = requests.get("http://127.0.0.1:5001/health", timeout=3)
        if r.status_code == 200:
            print("✓ Remote Superagent V2 is running")
            return True
    except:
        pass
    print("✗ Remote Superagent V2 is NOT running")
    print("  Start it with: python remote_agent_v2.py")
    return False


def run_demo():
    """Run the 3-turn conversation demo."""
    from supervisor_agent_v2 import SupervisorAgentV2
    
    print("\n" + "=" * 60)
    print("  MLflow Distributed Tracing Demo V2")
    print("=" * 60)
    print("\nThis demo tests:")
    print("  1. Multi-turn conversation tracing")
    print("  2. Remote agent spans NESTED under supervisor spans")
    print()
    
    # Create agent
    agent = SupervisorAgentV2()
    session = agent.start_session()
    print(f"Session ID: {session}")
    
    # Define conversation
    turns = [
        ("Can you search for information about Python?", "Search - delegated"),
        ("Now analyze the trends in machine learning", "Analyze - delegated"),
        ("Thanks, that's helpful!", "Simple - local")
    ]
    
    for i, (message, desc) in enumerate(turns, 1):
        print(f"\n{'=' * 60}")
        print(f"  Turn {i}: {desc}")
        print("=" * 60)
        print(f"\nUser: {message}")
        
        start = time.time()
        response = agent.process_message(session, message)
        elapsed = time.time() - start
        
        print(f"Assistant: {response}")
        print(f"[Processed in {elapsed:.2f}s]")
    
    print("\n" + "=" * 60)
    print("  Demo Complete!")
    print("=" * 60)
    print("\nNow verify in MLflow UI:")
    print("  1. Run: mlflow ui --port 5000")
    print("  2. Open: http://localhost:5000")
    print("  3. Look at experiment: Multi-Agent-Tracing-V2")
    print("\nYou should see:")
    print("  - Each turn creates a trace")
    print("  - Remote agent spans NESTED under 'delegate_to_remote' span")


if __name__ == "__main__":
    if not check_remote_agent():
        sys.exit(1)
    
    run_demo()

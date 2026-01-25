"""
V3 Demo - TRUE Single Trace Multi-Agent System
==============================================

This demo shows the CORRECT pattern for MLflow multi-agent tracing:
1. Supervisor creates ALL spans (including for remote work)
2. Remote agents return work logs instead of creating spans
3. Everything ends up in ONE trace per session

Run order:
1. Start remote agent: python remote_agent_v3.py
2. Run demo: python demo_v3.py
3. Verify: python verify_v3.py
4. View: mlflow ui --port 5002
"""

import os
import sys
import time
import subprocess
import requests
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supervisor_agent_v3 import SupervisorAgentV3


def check_remote_agent(url: str = "http://localhost:5001") -> bool:
    """Check if remote agent is running."""
    try:
        response = requests.get(f"{url}/health", timeout=2)
        return response.status_code == 200
    except:
        return False


def start_remote_agent() -> Optional[subprocess.Popen]:
    """Start the remote agent in a subprocess."""
    script_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "remote_agent_v3.py"
    )
    
    process = subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for it to start
    for _ in range(10):
        time.sleep(0.5)
        if check_remote_agent():
            return process
    
    process.terminate()
    return None


def run_demo():
    """Run the full demo."""
    print("\n" + "="*70)
    print("V3 SINGLE-TRACE MULTI-AGENT DEMO")
    print("="*70)
    print("\nThis demo demonstrates:")
    print("  1. Multi-turn conversation with SAME trace ID")
    print("  2. Remote agent work logged as child spans in supervisor's trace")
    print("  3. TRUE single trace per session\n")
    
    # Check/start remote agent
    remote_started = False
    if not check_remote_agent():
        print("Starting remote agent...")
        process = start_remote_agent()
        if process:
            print("Remote agent started successfully!")
            remote_started = True
        else:
            print("ERROR: Could not start remote agent.")
            print("Please start it manually: python remote_agent_v3.py")
            return
    else:
        print("Remote agent is already running.")
    
    print()
    
    # Create supervisor
    supervisor = SupervisorAgentV3()
    session_id = f"v3_session_{int(time.time())}"
    
    # Multi-turn conversation
    conversation = [
        ("Turn 1 - Search", "Search for information about Python machine learning libraries"),
        ("Turn 2 - Analyze", "Analyze the key differences between TensorFlow and PyTorch"),
        ("Turn 3 - Find More", "Find resources about neural network architectures")
    ]
    
    print(f"\nSession ID: {session_id}")
    print("="*70)
    
    all_results = []
    
    for turn_name, user_input in conversation:
        print(f"\n{'='*60}")
        print(f"{turn_name}")
        print(f"User: {user_input}")
        print("="*60)
        
        result = supervisor.process_turn(session_id, user_input)
        all_results.append(result)
        
        print(f"\nAgent: {result['response']}")
        print(f"Turn #{result['turn_number']} completed")
        
        # Show work log summary
        work_log = result.get("remote_agent_work", {}).get("work_log", [])
        if work_log:
            print(f"\nRemote agent performed {len(work_log)} operations:")
            for item in work_log:
                print(f"  - {item['operation']} ({item['type']}): {item['duration_ms']}ms")
        
        time.sleep(0.3)
    
    print("\n" + "="*70)
    print("DEMO COMPLETE")
    print("="*70)
    print(f"\nSession: {session_id}")
    print(f"Total turns: {len(all_results)}")
    print("\nNext steps:")
    print("  1. Run verify_v3.py to check trace structure")
    print("  2. Run 'mlflow ui --port 5002' to view traces")
    print("="*70 + "\n")
    
    return session_id


if __name__ == "__main__":
    session_id = run_demo()

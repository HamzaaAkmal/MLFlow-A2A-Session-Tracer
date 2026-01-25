"""
Main Entry Point for MLflow Tracing PoC
========================================

This script provides a convenient way to run the entire PoC,
including starting both agents and running the demo.
"""

import subprocess
import sys
import time
import threading
import signal
import os

import config


def start_remote_agent():
    """Start the Remote Superagent in a subprocess."""
    print("Starting Remote Superagent...")
    
    # Get the path to the remote_superagent.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    remote_agent_path = os.path.join(script_dir, "remote_superagent.py")
    
    # Start the subprocess
    process = subprocess.Popen(
        [sys.executable, remote_agent_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait a bit for it to start
    time.sleep(2)
    
    if process.poll() is None:
        print(f"✓ Remote Superagent started on port {config.REMOTE_SUPERAGENT_PORT}")
        return process
    else:
        stdout, stderr = process.communicate()
        print(f"✗ Failed to start Remote Superagent")
        print(f"  Error: {stderr}")
        return None


def run_demo():
    """Run the demo script."""
    print("\nRunning Multi-Turn Demo...")
    print("=" * 50)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    demo_path = os.path.join(script_dir, "demo_multi_turn.py")
    
    # Run the demo
    result = subprocess.run(
        [sys.executable, demo_path],
        text=True
    )
    
    return result.returncode == 0


def main():
    """Main entry point."""
    print("=" * 60)
    print("  MLflow Multi-Agent Tracing - Proof of Concept")
    print("=" * 60)
    print()
    print("This script will:")
    print("  1. Start the Remote Superagent server")
    print("  2. Run a 3-turn conversation demo")
    print("  3. Generate MLflow traces for verification")
    print()
    
    # Start the remote agent
    remote_process = start_remote_agent()
    
    if not remote_process:
        print("\nFailed to start Remote Superagent. Exiting.")
        sys.exit(1)
    
    try:
        # Run the demo
        success = run_demo()
        
        if success:
            print("\n" + "=" * 60)
            print("  Demo completed successfully!")
            print("=" * 60)
            print()
            print("Next steps:")
            print("  1. Start MLflow UI: mlflow ui --port 5000")
            print("  2. Open http://localhost:5000")
            print(f"  3. Check experiment: {config.MLFLOW_EXPERIMENT_NAME}")
            print()
        else:
            print("\nDemo encountered errors.")
            
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        
    finally:
        # Clean up: stop the remote agent
        print("\nStopping Remote Superagent...")
        remote_process.terminate()
        remote_process.wait(timeout=5)
        print("Done.")


if __name__ == "__main__":
    main()

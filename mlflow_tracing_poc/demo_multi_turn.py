"""
Multi-Turn Conversation Demo Script
====================================

This script demonstrates the MLflow tracing solution by simulating
a 3-turn conversation between a user and the multi-agent system.

The demo shows:
1. Single trace for the entire multi-turn conversation (Challenge 2)
2. Nested spans from the Remote Superagent (Challenge 1)
"""

import time
import sys
import logging

import mlflow

import config
from supervisor_agent import SupervisorAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def print_separator():
    print("\n" + "=" * 70 + "\n")


def print_header(text: str):
    print_separator()
    print(f"  {text}")
    print_separator()


def run_demo():
    """
    Run the multi-turn conversation demo.
    
    This demo simulates a 3-turn conversation where:
    - Turn 1: User asks for a search (triggers delegation)
    - Turn 2: User asks for analysis (triggers delegation)
    - Turn 3: User asks a simple question (handled locally)
    
    All turns should be captured in a single MLflow trace with
    properly nested spans.
    """
    print_header("MLflow Multi-Agent Tracing Demo")
    
    print("This demo will simulate a 3-turn conversation to demonstrate:")
    print("  1. Single trace for entire multi-turn conversation")
    print("  2. Nested spans from Remote Superagent")
    print()
    print(f"MLflow Tracking URI: {config.MLFLOW_TRACKING_URI}")
    print(f"Remote Agent URL: {config.REMOTE_SUPERAGENT_URL}")
    print()
    
    # Ensure MLflow is configured
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    mlflow.set_experiment(config.MLFLOW_EXPERIMENT_NAME)
    
    # Create the Supervisor Agent
    print("Initializing Supervisor Agent...")
    try:
        supervisor = SupervisorAgent()
    except Exception as e:
        print(f"Error initializing Supervisor Agent: {e}")
        return
    
    # Start a new conversation session
    session_id = supervisor.start_session()
    print(f"Started conversation session: {session_id}")
    
    # Define the conversation turns
    conversation = [
        {
            "turn": 1,
            "user_message": "Can you search for information about machine learning frameworks?",
            "description": "Search request - will be delegated to Remote Superagent"
        },
        {
            "turn": 2,
            "user_message": "Now analyze the trends in AI development for 2024",
            "description": "Analysis request - will be delegated to Remote Superagent"
        },
        {
            "turn": 3,
            "user_message": "Thank you, that's very helpful!",
            "description": "Simple acknowledgment - handled locally"
        }
    ]
    
    # Process each turn
    for turn_info in conversation:
        turn = turn_info["turn"]
        user_message = turn_info["user_message"]
        description = turn_info["description"]
        
        print_header(f"Turn {turn}: {description}")
        
        print(f"User: {user_message}")
        print()
        
        try:
            # Process the message
            start_time = time.time()
            response = supervisor.process_message(session_id, user_message)
            elapsed = time.time() - start_time
            
            print(f"Assistant: {response}")
            print(f"\n[Processed in {elapsed:.2f}s]")
            
        except Exception as e:
            print(f"Error processing message: {e}")
            logger.exception("Error in demo")
    
    # End the session
    print_header("Conversation Complete")
    
    print("Ending session and finalizing trace...")
    supervisor.end_session(session_id)
    
    print()
    print("=" * 70)
    print("  VERIFICATION INSTRUCTIONS")
    print("=" * 70)
    print()
    print("To verify the tracing solution, open the MLflow UI:")
    print()
    print("  1. Run: mlflow ui --port 5000")
    print(f"  2. Open: http://localhost:5000")
    print(f"  3. Navigate to experiment: {config.MLFLOW_EXPERIMENT_NAME}")
    print()
    print("You should see:")
    print("  - A single trace containing all 3 conversation turns")
    print("  - Nested spans showing Supervisor -> Remote Agent hierarchy")
    print("  - Tool execution spans within the Remote Agent spans")
    print()
    
    # Print conversation history
    print_header("Conversation History")
    history = supervisor.get_conversation_history(session_id)
    for msg in history:
        role = msg["role"].capitalize()
        content = msg["content"]
        print(f"{role}: {content}")
        print()


def check_remote_agent():
    """Check if the Remote Superagent is running."""
    import requests
    
    try:
        response = requests.get(
            f"{config.REMOTE_SUPERAGENT_URL}/health",
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Remote Superagent is running: {data.get('agent')} v{data.get('version')}")
            return True
    except requests.exceptions.ConnectionError:
        pass
    
    print("✗ Remote Superagent is NOT running!")
    print(f"  Please start it first: python remote_superagent.py")
    print(f"  Expected URL: {config.REMOTE_SUPERAGENT_URL}")
    return False


if __name__ == "__main__":
    print("\nMLflow Multi-Agent Tracing - Proof of Concept Demo")
    print("=" * 50)
    print()
    
    # Check if remote agent is running
    print("Checking Remote Superagent...")
    if not check_remote_agent():
        print("\nPlease start the Remote Superagent first!")
        print("In a separate terminal, run:")
        print("  cd mlflow_tracing_poc")
        print("  python remote_superagent.py")
        sys.exit(1)
    
    print()
    
    # Run the demo
    try:
        run_demo()
    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
    except Exception as e:
        logger.exception("Demo failed")
        print(f"\nDemo failed: {e}")
        sys.exit(1)

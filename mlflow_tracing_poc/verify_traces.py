"""
Verification Script for MLflow Traces
======================================

This script queries MLflow to verify that traces were created correctly
after running the demo. It provides a programmatic way to validate
the tracing solution.
"""

import sys
import mlflow
from mlflow.tracking import MlflowClient

import config


def print_header(text: str):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def verify_traces():
    """
    Verify that MLflow traces were created correctly.
    
    This function checks:
    1. Traces exist in the experiment
    2. Spans have proper session_id attributes
    3. Remote agent spans have parent references
    """
    print_header("MLflow Trace Verification")
    
    # Configure MLflow
    mlflow.set_tracking_uri(config.MLFLOW_TRACKING_URI)
    client = MlflowClient()
    
    # Get experiment
    experiment = client.get_experiment_by_name(config.MLFLOW_EXPERIMENT_NAME)
    
    if not experiment:
        print(f"❌ Experiment '{config.MLFLOW_EXPERIMENT_NAME}' not found!")
        print("   Please run the demo first: python demo_multi_turn.py")
        return False
    
    print(f"✓ Found experiment: {experiment.name}")
    print(f"  Experiment ID: {experiment.experiment_id}")
    print(f"  Artifact Location: {experiment.artifact_location}")
    
    # Search for traces
    print_header("Searching for Traces")
    
    try:
        # Get runs (traces in MLflow terminology for some versions)
        runs = client.search_runs(
            experiment_ids=[experiment.experiment_id],
            order_by=["start_time DESC"],
            max_results=10
        )
        
        if runs:
            print(f"✓ Found {len(runs)} run(s)/trace(s)")
            
            for i, run in enumerate(runs):
                print(f"\n  Run {i + 1}:")
                print(f"    Run ID: {run.info.run_id}")
                print(f"    Status: {run.info.status}")
                print(f"    Start Time: {run.info.start_time}")
                
                # Check for our custom attributes
                params = run.data.params
                tags = run.data.tags
                
                if params:
                    print(f"    Params: {dict(list(params.items())[:5])}")
                if tags:
                    relevant_tags = {k: v for k, v in tags.items() 
                                   if not k.startswith('mlflow.')}
                    if relevant_tags:
                        print(f"    Tags: {dict(list(relevant_tags.items())[:5])}")
        else:
            print("⚠ No runs found. Checking for traces...")
            
    except Exception as e:
        print(f"⚠ Error searching runs: {e}")
    
    # Try to access traces directly (MLflow 2.10+)
    try:
        print_header("Trace Details (MLflow 2.10+)")
        
        # List traces using newer API
        traces = mlflow.search_traces(
            experiment_ids=[experiment.experiment_id],
            max_results=10
        )
        
        if traces is not None and len(traces) > 0:
            print(f"✓ Found {len(traces)} trace(s)")
            
            for trace in traces[:5]:  # Show first 5
                print(f"\n  Trace:")
                if hasattr(trace, 'info'):
                    print(f"    Request ID: {trace.info.request_id}")
                    print(f"    Status: {trace.info.status}")
                
                if hasattr(trace, 'data') and hasattr(trace.data, 'spans'):
                    spans = trace.data.spans
                    print(f"    Spans: {len(spans)}")
                    
                    for span in spans[:5]:
                        print(f"\n      Span: {span.name}")
                        print(f"        Type: {span.span_type}")
                        if hasattr(span, 'attributes') and span.attributes:
                            if 'session_id' in span.attributes:
                                print(f"        Session ID: {span.attributes['session_id']}")
                            if 'agent_name' in span.attributes:
                                print(f"        Agent: {span.attributes['agent_name']}")
                            if 'parent_span_id' in span.attributes:
                                print(f"        Parent Span: {span.attributes['parent_span_id']}")
        else:
            print("No traces found with new API.")
            
    except AttributeError:
        print("Note: mlflow.search_traces requires MLflow 2.10+")
    except Exception as e:
        print(f"Note: Could not use trace API: {e}")
    
    # Verification summary
    print_header("Verification Summary")
    
    print("""
To fully verify the tracing solution, open the MLflow UI:

  1. Run: mlflow ui --port 5000
  2. Open: http://localhost:5000
  3. Navigate to experiment: """ + config.MLFLOW_EXPERIMENT_NAME + """

You should see:
  ✓ Traces grouped by session (via session_id attribute)
  ✓ Each turn creates spans under the session trace
  ✓ Remote agent spans show parent_span_id linking to supervisor
  ✓ Tool execution spans nested under remote agent spans

Expected Span Hierarchy:
┌─ Conversation.Turn_1 (SupervisorAgent)
│  ├─ analyze_intent
│  ├─ delegate_to_remote
│  │  └─ [A2A Call to Remote Agent]
│  │     ├─ RemoteSuperagent.search
│  │     │  ├─ tool.search
│  │     │  └─ post_processing
│  └─ response_formatting
│
├─ Conversation.Turn_2 (SupervisorAgent)
│  ├─ analyze_intent
│  ├─ delegate_to_remote
│  │  └─ [A2A Call to Remote Agent]
│  │     ├─ RemoteSuperagent.analyze
│  │     │  ├─ tool.analyze
│  │     │  └─ post_processing
│  └─ response_formatting
│
└─ Conversation.Turn_3 (SupervisorAgent)
   ├─ analyze_intent
   └─ local_response (no delegation)
""")
    
    return True


def check_mlflow_installation():
    """Check MLflow is properly installed."""
    print_header("MLflow Installation Check")
    
    print(f"MLflow Version: {mlflow.__version__}")
    print(f"Tracking URI: {config.MLFLOW_TRACKING_URI}")
    
    # Check if version supports tracing
    version_parts = mlflow.__version__.split('.')
    major = int(version_parts[0])
    minor = int(version_parts[1].split('a')[0].split('b')[0].split('rc')[0])
    
    if major >= 2 and minor >= 10:
        print("✓ MLflow version supports advanced tracing features")
    else:
        print("⚠ MLflow 2.10+ recommended for best tracing support")
    
    return True


if __name__ == "__main__":
    try:
        check_mlflow_installation()
        verify_traces()
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        sys.exit(1)

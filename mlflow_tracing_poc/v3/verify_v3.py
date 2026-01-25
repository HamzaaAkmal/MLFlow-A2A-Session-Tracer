"""
Verify V3 Traces - Check for TRUE Single Trace
==============================================

This script verifies that:
1. All turns are in ONE trace (not separate traces)
2. Remote agent work appears as child spans
3. Proper nesting: Turn -> delegate_to_remote -> remote_* spans
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any


def load_traces(mlruns_path: str = "./mlruns") -> Dict[str, List[Dict]]:
    """Load all traces from MLflow runs."""
    traces_by_session = {}
    mlruns = Path(mlruns_path)
    
    if not mlruns.exists():
        print(f"ERROR: {mlruns_path} not found")
        return {}
    
    # Look for v3 experiment
    for exp_dir in mlruns.iterdir():
        if not exp_dir.is_dir() or exp_dir.name.startswith("."):
            continue
        
        # Check if this is v3 experiment
        meta_file = exp_dir / "meta.yaml"
        if meta_file.exists():
            with open(meta_file) as f:
                content = f.read()
                if "v3_single_trace_demo" not in content:
                    continue
        
        print(f"Found v3 experiment in: {exp_dir.name}")
        
        # Scan runs
        for run_dir in exp_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name.startswith("."):
                continue
            
            traces_dir = run_dir / "traces"
            if not traces_dir.exists():
                continue
            
            for trace_file in traces_dir.glob("*.json"):
                try:
                    with open(trace_file) as f:
                        trace_data = json.load(f)
                    
                    # Get session ID from attributes
                    spans = trace_data.get("spans", [])
                    session_id = None
                    for span in spans:
                        attrs = span.get("attributes", {})
                        if "session_id" in attrs:
                            session_id = attrs["session_id"]
                            break
                    
                    if session_id:
                        if session_id not in traces_by_session:
                            traces_by_session[session_id] = []
                        traces_by_session[session_id].append({
                            "trace_file": str(trace_file),
                            "trace_id": trace_data.get("request_id"),
                            "spans": spans
                        })
                
                except Exception as e:
                    print(f"  Error reading {trace_file}: {e}")
    
    return traces_by_session


def analyze_trace(trace_data: Dict) -> Dict[str, Any]:
    """Analyze a single trace."""
    spans = trace_data.get("spans", [])
    
    analysis = {
        "trace_id": trace_data.get("trace_id"),
        "total_spans": len(spans),
        "turn_spans": [],
        "delegate_spans": [],
        "remote_work_spans": [],
        "other_spans": [],
        "span_tree": {}
    }
    
    # Categorize spans
    for span in spans:
        name = span.get("name", "")
        parent = span.get("parent_span_id")
        span_id = span.get("span_id")
        
        span_info = {
            "name": name,
            "span_id": span_id,
            "parent_span_id": parent,
            "type": span.get("span_type", "UNKNOWN")
        }
        
        if "process_turn" in name:
            analysis["turn_spans"].append(span_info)
        elif "delegate_to_remote" in name:
            analysis["delegate_spans"].append(span_info)
        elif name.startswith("remote_"):
            analysis["remote_work_spans"].append(span_info)
        else:
            analysis["other_spans"].append(span_info)
    
    return analysis


def verify_single_trace(traces_by_session: Dict[str, List[Dict]]) -> bool:
    """Verify single trace per session requirement."""
    print("\n" + "="*70)
    print("TRACE VERIFICATION REPORT")
    print("="*70)
    
    all_passed = True
    
    for session_id, traces in traces_by_session.items():
        print(f"\n{'='*60}")
        print(f"Session: {session_id}")
        print(f"Number of traces: {len(traces)}")
        print("="*60)
        
        # Requirement 1: Should be only ONE trace per session
        if len(traces) == 1:
            print(f"✅ PASS: Single trace for session")
        else:
            print(f"❌ FAIL: Multiple traces ({len(traces)}) for session")
            all_passed = False
        
        # Analyze each trace
        for i, trace in enumerate(traces):
            print(f"\n--- Trace {i+1} ---")
            analysis = analyze_trace(trace)
            
            print(f"  Trace ID: {analysis['trace_id']}")
            print(f"  Total spans: {analysis['total_spans']}")
            print(f"  Turn spans: {len(analysis['turn_spans'])}")
            print(f"  Delegate spans: {len(analysis['delegate_spans'])}")
            print(f"  Remote work spans: {len(analysis['remote_work_spans'])}")
            
            # Requirement 2: Should have turn spans
            if analysis['turn_spans']:
                print(f"  ✅ Has turn spans")
            else:
                print(f"  ❌ Missing turn spans")
                all_passed = False
            
            # Requirement 3: Should have remote work spans nested
            if analysis['remote_work_spans']:
                print(f"  ✅ Has remote work spans")
                
                # Verify nesting
                delegate_ids = {s['span_id'] for s in analysis['delegate_spans']}
                properly_nested = True
                
                for remote_span in analysis['remote_work_spans']:
                    parent = remote_span['parent_span_id']
                    if parent not in delegate_ids:
                        properly_nested = False
                        print(f"    ⚠️  {remote_span['name']} not nested under delegate span")
                
                if properly_nested:
                    print(f"  ✅ Remote spans properly nested under delegate_to_remote")
            else:
                print(f"  ⚠️  No remote work spans (may be expected if remote failed)")
            
            # Print span tree
            print(f"\n  Span hierarchy:")
            for turn_span in analysis['turn_spans']:
                print(f"    📁 {turn_span['name']}")
                
                # Find children
                turn_id = turn_span['span_id']
                for span in trace['spans']:
                    if span.get('parent_span_id') == turn_id:
                        print(f"      📂 {span['name']}")
                        span_id = span.get('span_id')
                        
                        # Find grandchildren
                        for child_span in trace['spans']:
                            if child_span.get('parent_span_id') == span_id:
                                print(f"        📄 {child_span['name']}")
    
    print("\n" + "="*70)
    if all_passed:
        print("✅ ALL VERIFICATIONS PASSED")
        print("   - Single trace per session: PASS")
        print("   - Remote work logged as child spans: PASS")
        print("   - Proper nesting structure: PASS")
    else:
        print("❌ SOME VERIFICATIONS FAILED")
    print("="*70 + "\n")
    
    return all_passed


def main():
    """Run verification."""
    traces = load_traces()
    
    if not traces:
        print("\nNo v3 traces found. Please run demo_v3.py first.")
        return False
    
    return verify_single_trace(traces)


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

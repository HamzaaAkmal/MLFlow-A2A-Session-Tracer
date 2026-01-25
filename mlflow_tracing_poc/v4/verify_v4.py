"""Verify V4 trace structure."""
import sqlite3

conn = sqlite3.connect('mlflow_v4.db')
cursor = conn.cursor()

print("\n" + "="*80)
print("V4 TRACE VERIFICATION")
print("="*80)

# Get all traces from trace_info table
print("\n=== TRACES ===")
cursor.execute('SELECT request_id, experiment_id FROM trace_info')
traces = cursor.fetchall()
print(f"Total traces: {len(traces)}")
for t in traces:
    print(f"  - {t[0]}")

# Get all spans
print("\n=== SPANS ===")
cursor.execute('''
    SELECT trace_id, span_id, parent_span_id, name 
    FROM spans 
    ORDER BY trace_id, start_time_unix_nano
''')
spans = cursor.fetchall()

print(f"Total spans: {len(spans)}")
print()

# Build span tree
span_map = {s[1]: s for s in spans}
root_spans = [s for s in spans if s[2] is None]

def print_span_tree(span, indent=0):
    prefix = "  " * indent
    print(f"{prefix}├── {span[3]}")
    # Find children
    children = [s for s in spans if s[2] == span[1]]
    for child in children:
        print_span_tree(child, indent + 1)

for root in root_spans:
    print(f"\n📁 Trace: {root[0]}")
    print_span_tree(root)

# Verify requirements
print("\n" + "="*80)
print("VERIFICATION RESULTS")
print("="*80)

# Requirement 1: Single trace
if len(traces) == 1:
    print("✅ PASS: Single trace for entire session")
else:
    print(f"❌ FAIL: {len(traces)} traces found (expected 1)")

# Requirement 2: All spans in same trace
unique_traces = set(s[0] for s in spans)
if len(unique_traces) == 1:
    print("✅ PASS: All spans belong to the same trace")
else:
    print(f"❌ FAIL: Spans spread across {len(unique_traces)} traces")

# Requirement 3: Proper nesting (turns have parent = root)
turn_spans = [s for s in spans if "turn_" in s[3]]
root_span_id = root_spans[0][1] if root_spans else None

if all(s[2] == root_span_id for s in turn_spans):
    print("✅ PASS: All turn spans are children of root session span")
else:
    print("❌ FAIL: Turn spans are not properly nested under root")

# Requirement 4: Remote work spans exist
remote_spans = [s for s in spans if s[3].startswith("remote_")]
if remote_spans:
    print(f"✅ PASS: Remote work logged as spans ({len(remote_spans)} remote operations)")
else:
    print("⚠️  WARNING: No remote work spans found")

print("\n" + "="*80)

conn.close()

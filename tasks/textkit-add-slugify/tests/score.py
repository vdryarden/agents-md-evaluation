"""Turn the junit report into {"correct": 0|1, "adherence": 0..1, "reward": 0|1}."""
import json
import sys
import xml.etree.ElementTree as ET

results = {}
for case in ET.parse(sys.argv[1]).iter("testcase"):
    failed = any(child.tag in ("failure", "error", "skipped") for child in case)
    results[case.get("name")] = not failed

correct = [ok for name, ok in results.items() if name.startswith("test_correct")]
adherence = [ok for name, ok in results.items() if name.startswith("test_adherence")]
is_correct = int(bool(correct) and all(correct))
print(json.dumps({
    "reward": is_correct,
    "correct": is_correct,
    "adherence": round(sum(adherence) / len(adherence), 3) if adherence else 0.0,
}))

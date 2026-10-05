"""重新生成 V3 标准测试用例 expected_action"""
import json
from pathlib import Path

src = Path(__file__).parent / "test_cases" / "test_cases_100.json"
dst = Path(__file__).parent / "test_cases" / "test_cases_v3_standard.json"

with open(src, encoding="utf-8") as f:
    cases = json.load(f)

fixed = []
for c in cases:
    score = c.get("expected_risk_score", 0.5)
    # V3 标准动作阈值
    if score >= 0.90:
        action = "BLOCK"
    elif score >= 0.60:
        action = "HUMAN_REVIEW"
    else:
        action = "ALLOW"
    c["expected_action"] = action
    c["v3_standard_action"] = True
    fixed.append(c)

with open(dst, "w", encoding="utf-8") as f:
    json.dump(fixed, f, ensure_ascii=False, indent=2)

print(f"Written {len(fixed)} cases to {dst}")
print("Summary:")
from collections import Counter
actions = Counter(c["expected_action"] for c in fixed)
for a, n in actions.most_common():
    print(f"  {a}: {n}")

import json
from collections import defaultdict

with open(r'D:\ZYY Project\AgentShield_V3\benchmark\benchmark_report.json', encoding='utf-8') as f:
    data = json.load(f)

failures = [r for r in data['results'] if not r['action_correct']]
print(f'Total failures: {len(failures)}\n')

by_cat = defaultdict(list)
for r in failures:
    by_cat[r['category']].append(r)

for cat, items in sorted(by_cat.items(), key=lambda x: -len(x[1])):
    print(f'=== {cat} ({len(items)} failures) ===')
    mismatch = defaultdict(list)
    for r in items:
        key = f'expected:{r["expected_action"]} -> actual:{r["actual_action"]}'
        mismatch[key].append(r['id'])
    for k, v in sorted(mismatch.items()):
        print(f'  {k}: {v}')
    print()

print('\n=== Score range analysis for failures ===')
for cat, items in sorted(by_cat.items()):
    print(f'{cat}:')
    for r in items:
        print(f'  {r["id"]}: score={r["actual_score"]:.2f}, expected={r["expected_action"]}, actual={r["actual_action"]}')

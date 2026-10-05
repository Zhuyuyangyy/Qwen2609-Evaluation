import json
import sys
sys.path.insert(0, r'D:\ZYY Project\AgentShield_V3\benchmark')
with open(r'D:\ZYY Project\AgentShield_V3\benchmark\test_cases\test_cases_100.json', encoding='utf-8') as f:
    cases = json.load(f)

# Show external_network_transfer and governance_bypass cases
target_cats = {'external_network_transfer', 'governance_bypass'}
for c in cases:
    if c['category'] in target_cats:
        print(f"{c['id']}  score={c['expected_risk_score']}  expected={c['expected_action']:15}  tool={c['tool_name']:25}  desc={c['description'][:60]}")

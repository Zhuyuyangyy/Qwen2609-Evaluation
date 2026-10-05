# AgentShield V3 API Examples

AgentShield V3 exposes two API entry points:

| Entry Point | Port | Prefix | Description |
|---|---|---|---|
| `backend/app/main.py` | 8011 | `/api/v3/` | Full V3 engine with behavior graph, branching, counterfactual analysis |
| `backend/app.py` | 8090 | `/api/` | Standalone deployment with rate limiting, session persistence, agent registry |

Both share the same underlying V3 engine. Choose the one that fits your deployment.

---

## Table of Contents

- [Standalone API (port 8090)](#standalone-api-port-8090)
  - [Health Check](#health-check)
  - [Evaluate Tool Call](#evaluate-tool-call)
  - [Agent Registry](#agent-registry)
  - [Behavior Chain Tracking](#behavior-chain-tracking)
  - [Intent Evaluation](#intent-evaluation)
  - [Session Management](#session-management)
- [Full V3 API (port 8011)](#full-v3-api-port-8011)
  - [Process Tool Call](#process-tool-call)
  - [Get Governance Status](#get-governance-status)
  - [Fork Branch (Manual Intervention)](#fork-branch-manual-intervention)
  - [Export Chain](#export-chain)
  - [Get Behavior Graph](#get-behavior-graph)
  - [Simulate Steps](#simulate-steps)
- [Python SDK Usage](#python-sdk-usage)

---

## Standalone API (port 8090)

Start with:
```bash
cd backend
python app.py
# or
./start.sh
```

### Health Check

```bash
# Basic health
curl http://localhost:8090/health

# Detailed health (includes session count)
curl http://localhost:8090/api/health_detailed
```

Response:
```json
{
  "status": "ok",
  "version": "3.0.0",
  "engine": "AgentShield_V3",
  "framework": "ASF-BGT",
  "port": 8090
}
```

### Evaluate Tool Call

The primary endpoint. Submit a tool call for risk evaluation. Returns a governance decision.

```bash
# Low-risk: allow
curl -X POST http://localhost:8090/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data_agent",
    "tool_name": "read_file",
    "params": {"path": "/data/report.txt"},
    "risk_score": 0.15,
    "session_id": "my-session-001"
  }'

# Medium-risk: review
curl -X POST http://localhost:8090/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "query_agent",
    "tool_name": "cursor.execute",
    "params": {"sql": "SELECT * FROM customers WHERE region = '\''CN'\''"},
    "risk_score": 0.65,
    "session_id": "my-session-001"
  }'

# High-risk: block
curl -X POST http://localhost:8090/api/evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "exfil_agent",
    "tool_name": "send_email",
    "params": {"to": "attacker@evil.com", "attachment": "db_dump.csv"},
    "risk_score": 0.95,
    "session_id": "my-session-001"
  }'
```

Response:
```json
{
  "session_id": "my-session-001",
  "decision": "block",
  "risk_level": "critical",
  "risk_score": 0.95,
  "reasoning": "risk_score 0.95 >= 0.90",
  "shield_version": "3.0.0"
}
```

Decision values: `"allow"`, `"review"`, `"block"`.

Risk levels: `"low"`, `"medium"`, `"high"`, `"critical"`.

### Agent Registry

List all registered agent types and their capabilities.

```bash
curl http://localhost:8090/api/agent/registry
```

Response:
```json
{
  "agents": [
    {"type": "Risk-Analysis", "description": "...", "capabilities": ["..."]},
    {"type": "TCM-Cognition", "description": "...", "capabilities": ["..."]}
  ],
  "total": 8
}
```

### Behavior Chain Tracking

Track a multi-agent behavior chain. Each agent step is evaluated for risk.

```bash
curl -X POST http://localhost:8090/api/agent/behavior_chain \
  -H "Content-Type: application/json" \
  -d '{
    "agents": [
      {"id": "planner", "action": "query", "target": "database", "input": {"sql": "SELECT * FROM orders"}},
      {"id": "processor", "action": "export", "target": "csv", "input": {"table": "orders"}},
      {"id": "sender", "action": "send_email", "target": "partner@external.com", "input": {"body": "report attached"}}
    ]
  }'
```

Response:
```json
{
  "chain_id": "uuid-here",
  "steps": [
    {"step_id": 1, "agent_id": "planner", "decision": "allow", "risk_score": 0.12},
    {"step_id": 2, "agent_id": "processor", "decision": "allow", "risk_score": 0.35},
    {"step_id": 3, "agent_id": "sender", "decision": "block", "risk_score": 0.88}
  ],
  "risk_score": 0.88,
  "verdict": "block",
  "violations": [{"step": 3, "reason": "send_email to partner@external.com risk=0.88"}]
}
```

### Intent Evaluation

Evaluate whether an agent's observed actions align with its stated goal (Theory of Mind).

```bash
curl -X POST http://localhost:8090/api/agent/evaluate_intent \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "analyst_agent",
    "stated_goal": "查询数据库中的客户信息并生成分析报告",
    "observed_actions": ["查询客户表", "分析数据", "生成报告"]
  }'
```

Response:
```json
{
  "agent_id": "analyst_agent",
  "stated_goal": "查询数据库中的客户信息并生成分析报告",
  "intent_alignment": 0.72,
  "deception_score": 0.05,
  "reasoning": "目标表述包含3个操作类关键词，观察到3个行动，其中0个存在风险"
}
```

### Session Management

```bash
# List recent sessions
curl http://localhost:8090/api/sessions?limit=10

# Get specific session
curl http://localhost:8090/api/session/my-session-001

# Get behavior graph for a session
curl http://localhost:8090/api/behavior_graph/my-session-001

# Delete a session
curl -X DELETE http://localhost:8090/api/session/my-session-001
```

---

## Full V3 API (port 8011)

Start with:
```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8011
# or on Windows:
start.bat
```

### Process Tool Call

Full V3 processing: behavior graph node creation, governance gate decision, future branch generation, and counterfactual what-if analysis.

```bash
# Low-risk tool call
curl -X POST http://localhost:8011/api/v3/process_call \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "data_agent",
    "tool_name": "read_file",
    "params": {"path": "/data/report.txt"},
    "risk_score": 0.2,
    "fuse_action": "allow",
    "session_id": "v3-session-001"
  }'

# High-risk with parent node (chained)
curl -X POST http://localhost:8011/api/v3/process_call \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "exfil_agent",
    "tool_name": "send_email",
    "params": {"to": "external@evil.com", "attachment": "data.csv"},
    "risk_score": 0.92,
    "fuse_action": "block",
    "session_id": "v3-session-001",
    "parent_node_id": "node_from_previous_call",
    "labels": ["exfiltration", "email"]
  }'
```

Response:
```json
{
  "call_id": "call_a1b2c3d4",
  "node_id": "node_e5f6g7h8",
  "session_id": "v3-session-001",
  "decision": "block",
  "risk_level": "critical",
  "risk_score": 0.92,
  "reasoning": "risk_score 0.92 >= 0.90",
  "behavior_graph_summary": {
    "session_id": "v3-session-001",
    "total_nodes": 2,
    "total_edges": 1,
    "risk_distribution": {"safe": 1, "low": 0, "medium": 0, "high": 0, "critical": 1},
    "critical_node_count": 0,
    "blocked_count": 1,
    "review_count": 0
  },
  "gate_result": {
    "action": "BLOCK",
    "reason": "risk_score 0.92 >= 0.90",
    "score": 0.92,
    "risk_level": "critical",
    "gate_name": "DefaultV3Gate"
  },
  "future_branches": [
    {
      "branch_id": "branch_xxxx",
      "label": "exfil_agent:send_email->candidate_1:external_delivery_receipt",
      "risk_score": 0.414,
      "governance_action": "ALLOW",
      "probability": 0.333
    }
  ],
  "whatif_result": {
    "scenario_id": "whatif_xxxx",
    "label": "block exfil_agent.send_email before execution",
    "baseline_action": "BLOCK",
    "risk_delta": -0.46,
    "projected_outcome": {
      "blocked": true,
      "baseline_risk": 0.92,
      "projected_risk": 0.46,
      "risk_reduced_by": 0.46
    }
  },
  "critical_nodes": []
}
```

### Get Governance Status

```bash
curl http://localhost:8011/api/v3/status/v3-session-001
```

Response:
```json
{
  "session_id": "v3-session-001",
  "engine_id": "v3engine_a1b2c3d4",
  "risk_threshold": 0.7,
  "branch_count": 3,
  "behavior_graph": {"session_id": "v3-session-001", "total_nodes": 2, "...": "..."},
  "gate_count": 2
}
```

### Fork Branch (Manual Intervention)

Create a manual intervention point in the behavior chain.

```bash
curl -X POST http://localhost:8011/api/v3/fork_branch \
  -H "Content-Type: application/json" \
  -d '{
    "branch_label": "human_override_block_email",
    "intervention": {
      "type": "block_tool_call",
      "tool_name": "send_email"
    },
    "session_id": "v3-session-001"
  }'
```

Intervention types:
- `block_tool_call` - Block a specific tool
- `rate_limit` - Rate-limit specific agents
- `escalate` - Escalate to human review

Response:
```json
{
  "branch_id": "branch_xxxx",
  "session_id": "v3-session-001",
  "message": "分支已创建: human_override_block_email"
}
```

### Export Chain

Export the full behavior chain for visualization or audit.

```bash
curl http://localhost:8011/api/v3/export_chain/v3-session-001
```

Response:
```json
{
  "session_id": "v3-session-001",
  "engine_id": "v3engine_xxxx",
  "behavior_graph": {"nodes": [...], "edges": [...], "critical_nodes": [...]},
  "branch_tree": {
    "root": "branch_xxxx",
    "active": "branch_yyyy",
    "total_branches": 3,
    "branch_points": [{"point_id": "bp_xxxx", "label": "future:agent.tool", "candidates": 3}]
  },
  "audit_chain": [{"record_id": "rec_xxxx", "event": "V3_ENGINE_INIT", "...": "..."}]
}
```

### Get Behavior Graph

Get just the behavior graph (nodes and edges).

```bash
curl http://localhost:8011/api/v3/behavior_graph/v3-session-001
```

### Simulate Steps

Run multiple simulated tool calls to project future risk.

```bash
curl -X POST "http://localhost:8011/api/v3/simulate_steps?session_id=v3-session-001&steps=5"
```

---

## Python SDK Usage

### Using httpx (recommended)

```python
import httpx

BASE_URL = "http://localhost:8090"  # Standalone API

# Evaluate a tool call
def evaluate_tool_call(
    agent_id: str,
    tool_name: str,
    params: dict,
    risk_score: float,
    session_id: str = "",
) -> dict:
    resp = httpx.post(
        f"{BASE_URL}/api/evaluate",
        json={
            "agent_id": agent_id,
            "tool_name": tool_name,
            "params": params,
            "risk_score": risk_score,
            "session_id": session_id,
        },
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


# Example usage
result = evaluate_tool_call(
    agent_id="my_agent",
    tool_name="cursor.execute",
    params={"sql": "SELECT * FROM users LIMIT 10"},
    risk_score=0.3,
    session_id="sdk-demo-001",
)

print(f"Decision: {result['decision']}")      # "allow"
print(f"Risk level: {result['risk_level']}")  # "low"
print(f"Risk score: {result['risk_score']}")  # 0.3
```

### Multi-step Chain Evaluation

```python
import httpx

BASE_URL = "http://localhost:8090"

def evaluate_chain(agents: list[dict]) -> dict:
    """Evaluate a multi-agent behavior chain."""
    resp = httpx.post(
        f"{BASE_URL}/api/agent/behavior_chain",
        json={"agents": agents},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()


# Define a realistic agent chain
chain = [
    {
        "id": "planner",
        "action": "query_database",
        "target": "orders_db",
        "input": {"sql": "SELECT * FROM orders WHERE date > '2026-01-01'"},
    },
    {
        "id": "analyzer",
        "action": "aggregate_data",
        "target": "orders_table",
        "input": {"operation": "group_by", "field": "customer_id"},
    },
    {
        "id": "reporter",
        "action": "send_email",
        "target": "manager@company.com",
        "input": {"subject": "Q1 Report", "body": "See attached"},
    },
]

result = evaluate_chain(chain)

print(f"Chain verdict: {result['verdict']}")
print(f"Overall risk: {result['risk_score']}")

if result["violations"]:
    print("Violations detected:")
    for v in result["violations"]:
        print(f"  Step {v['step']}: {v['reason']}")
```

### Full V3 Engine (port 8011)

```python
import httpx

V3_URL = "http://localhost:8011"


def process_call_v3(
    agent_id: str,
    tool_name: str,
    params: dict,
    risk_score: float,
    session_id: str,
    parent_node_id: str = None,
) -> dict:
    """Submit a tool call to the full V3 engine."""
    payload = {
        "agent_id": agent_id,
        "tool_name": tool_name,
        "params": params,
        "risk_score": risk_score,
        "fuse_action": "allow",
        "session_id": session_id,
    }
    if parent_node_id:
        payload["parent_node_id"] = parent_node_id

    resp = httpx.post(f"{V3_URL}/api/v3/process_call", json=payload, timeout=10.0)
    resp.raise_for_status()
    return resp.json()


# Build a chain
session = "python-sdk-chain-001"

r1 = process_call_v3(
    agent_id="reader",
    tool_name="cursor.execute",
    params={"sql": "SELECT name, email FROM customers"},
    risk_score=0.3,
    session_id=session,
)

r2 = process_call_v3(
    agent_id="exporter",
    tool_name="export_csv",
    params={"table": "customers"},
    risk_score=0.6,
    session_id=session,
    parent_node_id=r1["node_id"],
)

r3 = process_call_v3(
    agent_id="sender",
    tool_name="send_email",
    params={"to": "partner@external.com", "attachment": "customers.csv"},
    risk_score=0.9,
    session_id=session,
    parent_node_id=r2["node_id"],
)

# Check results
for i, r in enumerate([r1, r2, r3], 1):
    print(f"Step {i}: decision={r['decision']}, risk={r['risk_score']}")

# Get full chain export
export = httpx.get(f"{V3_URL}/api/v3/export_chain/{session}").json()
print(f"Total audit records: {len(export['audit_chain'])}")
print(f"Branch points: {len(export['branch_tree']['branch_points'])}")
```

### Async Usage

```python
import asyncio
import httpx

async def evaluate_async(agent_id: str, tool_name: str, params: dict, risk_score: float) -> dict:
    async with httpx.AsyncClient(base_url="http://localhost:8090") as client:
        resp = await client.post(
            "/api/evaluate",
            json={
                "agent_id": agent_id,
                "tool_name": tool_name,
                "params": params,
                "risk_score": risk_score,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()


# Run multiple evaluations concurrently
async def main():
    tasks = [
        evaluate_async("agent_1", "read_file", {"path": "/tmp/a"}, 0.1),
        evaluate_async("agent_2", "cursor.execute", {"sql": "SELECT 1"}, 0.4),
        evaluate_async("agent_3", "send_email", {"to": "x@y.com"}, 0.8),
    ]
    results = await asyncio.gather(*tasks)
    for r in results:
        print(f"{r['session_id']}: {r['decision']} (risk={r['risk_score']})")

asyncio.run(main())
```

---

## Risk Score Reference

| Score Range | Decision | Risk Level | Description |
|---|---|---|---|
| 0.00 - 0.39 | `allow` | `low` | Normal operation |
| 0.40 - 0.59 | `allow` | `medium` | Elevated attention |
| 0.60 - 0.89 | `review` | `high` | Requires human review |
| 0.90 - 1.00 | `block` | `critical` | Blocked immediately |

## Error Codes

| Code | Description |
|---|---|
| 200 | Success |
| 404 | Session not found |
| 422 | Invalid request body (missing required fields) |
| 429 | Rate limit exceeded (standalone API: 50 req/min for evaluate, 60 req/min for health) |
| 500 | Internal server error |

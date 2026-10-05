# AgentShield V3 User Guide

> Multi-Agent Behavior-Chain Risk Governance System

**Version**: 3.0 / 3.1 / 3.2
**Framework**: ASF-BGT (Agent Safety Framework - Behavior Graph Toolkit)
**Last Updated**: 2026-05-28

---

## Table of Contents

1. [Quick Start (5 Minutes)](#1-quick-start-5-minutes)
2. [Core Concepts](#2-core-concepts)
3. [SDK Usage Guide](#3-sdk-usage-guide)
4. [API Reference](#4-api-reference)
5. [Configuration](#5-configuration)
6. [Benchmark and Evaluation](#6-benchmark-and-evaluation)
7. [Frequently Asked Questions](#7-frequently-asked-questions)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Quick Start (5 Minutes)

### 1.1 Prerequisites

- Python 3.10 or later
- pip (Python package manager)
- Git (optional, for cloning the repository)

### 1.2 Installation

```bash
# Clone the repository
git clone <repository-url>
cd AgentShield_V3

# Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 1.3 Verify Installation

```bash
python -m pytest -q
```

Expected output: `242 passed, 1 skipped`

### 1.4 Start the API Server

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8011
```

On Windows, you can also double-click `start.bat`.

### 1.5 Send Your First Request

```bash
curl -X POST http://localhost:8011/api/v3/process_call \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my-first-session",
    "agent_id": "demo_agent",
    "tool_name": "execute_sql",
    "params": {"query": "SELECT name, email FROM customers"},
    "risk_score": 0.75,
    "fuse_action": "review"
  }'
```

The response contains:

- `decision`: The governance decision (`allow`, `review`, or `block`)
- `risk_level`: Risk classification (`low`, `medium`, `high`, `critical`)
- `gate_result`: Detailed gate evaluation with score and reason
- `future_branches`: Projected next-step risk branches (if risk is high)
- `whatif_result`: Counterfactual analysis (if risk >= threshold)

### 1.6 Explore the API

Open the interactive Swagger documentation:

```
http://localhost:8011/docs
```

---

## 2. Core Concepts

### 2.1 Behavior Chain

Traditional AI guardrails evaluate a single prompt, response, or tool call in isolation. AgentShield V3 focuses on the **behavior chain** -- the sequence of tool calls that multiple agents execute within a session.

```
V1: What did the AI say?
V2: What tool did the agent call?
V3: Why does this multi-agent behavior chain become risky?
```

Risk often emerges across multiple steps, not within a single call. Examples:

- **Data exfiltration chain**: query sensitive fields -> stage to local file -> compress -> send externally
- **Privilege escalation**: read config -> modify admin role -> execute privileged command
- **Audit bypass**: request callback -> disable audit logging -> perform unauthorized action
- **Bulk destructive operations**: single bulk DELETE with delayed impact
- **Multi-agent delegation risk**: Agent A delegates to Agent B -> Agent B queries sensitive data -> Agent C delivers externally

### 2.2 Behavior Graph

Every tool call in a session becomes a **node** in a directed graph. Edges represent relationships between calls:

- `calls`: Agent A invokes Agent B
- `data_flow`: Data flows from one node to another
- `delegation`: Task delegation between agents
- `returns`: Return value flow

Each `BehaviorNode` carries:

| Field | Description |
|-------|-------------|
| `node_id` | Unique identifier (auto-generated) |
| `agent_id` | The agent that made the call |
| `tool_name` | Name of the tool invoked |
| `params_summary` | Sanitized parameter summary |
| `fuse_action` | Governance decision for this node |
| `shadow_risk_score` | Risk score (0.0 - 1.0) |
| `risk_status` | Risk level enum (SAFE/LOW/MEDIUM/HIGH/CRITICAL) |
| `inherited_risk` | Risk propagated from upstream nodes |
| `downstream_risk_amplified` | Whether this node amplifies downstream risk |

### 2.3 Risk Propagation

Risk propagates through the behavior graph using a backward BFS algorithm:

1. Leaf nodes (no children) start with their local `shadow_risk_score`
2. Risk flows backward from leaves to root with a decay factor of 0.5
3. Each parent node's `inherited_risk` = max(current inherited_risk, child_risk * 0.5)
4. Nodes that propagate significant risk (inherited_risk > 0.1) are marked as `downstream_risk_amplified`

This mechanism identifies **risk amplifier nodes** -- nodes that may have a moderate local risk score but enable high-risk downstream actions.

### 2.4 Hard Gate (Governance Decision)

Every tool call passes through a governance gate that produces one of three decisions:

| Risk Score Range | Decision | Description |
|-----------------|----------|-------------|
| < 0.60 | `ALLOW` | Low risk, proceed normally |
| 0.60 - 0.89 | `HUMAN_REVIEW` | Medium risk, requires human review |
| >= 0.90 | `BLOCK` | Critical risk, automatically blocked |

Risk levels are further classified:

| Risk Score Range | Risk Level |
|-----------------|------------|
| < 0.20 | `low` |
| 0.20 - 0.39 | `medium` (low end) |
| 0.40 - 0.69 | `medium` |
| 0.70 - 0.89 | `high` |
| >= 0.90 | `critical` |

### 2.5 Future Branch Projection

When a tool call has risk_score >= the configured threshold (default 0.70), the engine generates **future branches** -- possible next-step scenarios based on the current tool type:

| Current Tool Pattern | Candidate Next Steps |
|---------------------|---------------------|
| email / smtp | external_delivery_receipt, audit_log_write, http_request |
| sql / cursor / database | export_csv, send_email, http_request, audit_log_write |
| http / upload / webhook | response_parse, file_write, send_email |
| Other | audit_log_write, http_request, cursor.execute |

Each branch carries a projected risk score and governance action.

### 2.6 Counterfactual What-If Analysis

When risk_score >= threshold and counterfactual analysis is enabled, the engine generates a **what-if scenario** that estimates the risk reduction if the current action were blocked:

```
projected_risk = baseline_risk * 0.5
risk_delta = projected_risk - baseline_risk (always negative)
```

This helps operators understand the value of early intervention.

### 2.7 Audit Chain

Every engine operation is logged to an append-only audit chain with SHA-256 hash linking:

- Each record contains: `record_id`, `event`, `session_id`, `data`, `timestamp`, `previous_hash`, `record_hash`
- The chain is tamper-evident: changing any record breaks the hash chain
- Chain integrity can be verified via `verify_chain()`

---

## 3. SDK Usage Guide

### 3.1 Python SDK (Direct Import)

The fastest way to integrate AgentShield into your Python application:

```python
from app.shield.v3_engine import V3ShieldEngine

# Create an engine instance
engine = V3ShieldEngine(
    session_id="my-session-001",
    risk_threshold=0.70,
    max_branches=5,
    enable_counterfactual=True,
)

# Process a tool call
result = engine.process_tool_call(
    agent_id="data_agent",
    tool_name="execute_sql",
    params={"query": "SELECT phone, id_card FROM customers"},
    risk_score=0.92,
    fuse_action="block",
)

# Check the decision
if result["gate_result"]["action"] == "BLOCK":
    print(f"BLOCKED: {result['reasoning']}")
elif result["gate_result"]["action"] == "HUMAN_REVIEW":
    print(f"REVIEW REQUIRED: {result['reasoning']}")
else:
    print(f"ALLOWED: {result['reasoning']}")

# Access what-if analysis
if result["whatif_result"]:
    wi = result["whatif_result"]
    print(f"What-if: risk reduced by {wi['projected_outcome']['risk_reduced_by']}")
```

### 3.2 Multi-Step Chain Example

```python
from app.shield.v3_engine import V3ShieldEngine

engine = V3ShieldEngine(session_id="chain-demo")

# Step 1: Agent A queries sensitive data
r1 = engine.process_tool_call(
    agent_id="agent_a",
    tool_name="cursor.execute",
    params={"sql": "SELECT ssn, credit_card FROM users"},
    risk_score=0.65,
    fuse_action="review",
)
node1_id = r1["node_id"]

# Step 2: Agent B exports data (linked to step 1)
r2 = engine.process_tool_call(
    agent_id="agent_b",
    tool_name="export_csv",
    params={"source": "users", "path": "/tmp/export.csv"},
    risk_score=0.88,
    fuse_action="block",
    parent_node_id=node1_id,  # Creates an edge in the behavior graph
)

# Check critical nodes
critical = engine.behavior_graph.get_critical_nodes(threshold=0.7)
print(f"Critical nodes: {[n.node_id for n in critical]}")

# Export the full chain for visualization
chain = engine.export_chain()
```

### 3.3 Manual Branch Intervention

```python
# Create a manual intervention branch
branch_id = engine.fork_branch(
    branch_label="manual_block_email",
    intervention={
        "type": "block_tool_call",
        "tool_name": "send_email",
    },
)

# Check governance status
status = engine.get_governance_status()
print(f"Total branches: {status['branch_count']}")
print(f"Gate evaluations: {status['gate_count']}")
```

### 3.4 REST API Client

```python
import httpx

BASE_URL = "http://localhost:8011"

# Process a tool call via API
response = httpx.post(f"{BASE_URL}/api/v3/process_call", json={
    "session_id": "api-demo",
    "agent_id": "my_agent",
    "tool_name": "http_request",
    "params": {"url": "https://external.example.com/upload"},
    "risk_score": 0.78,
    "fuse_action": "review",
})
result = response.json()

# Get session status
status = httpx.get(f"{BASE_URL}/api/v3/status/api-demo").json()

# Export behavior chain
chain = httpx.get(f"{BASE_URL}/api/v3/export_chain/api-demo").json()

# Get behavior graph
graph = httpx.get(f"{BASE_URL}/api/v3/behavior_graph/api-demo").json()
```

---

## 4. API Reference

### 4.1 Base Information

| Item | Value |
|------|-------|
| Base URL | `http://localhost:8011` |
| API Prefix | `/api/v3` |
| Content Type | `application/json` |
| Authentication | None (add middleware for production) |
| Rate Limit | Configurable (default: no limit) |
| Interactive Docs | `http://localhost:8011/docs` |

### 4.2 Endpoints

#### POST /api/v3/process_call

Process a single tool call through the behavior-chain governance pipeline.

**Request Body**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | string | Yes | Identifier of the calling agent |
| `tool_name` | string | Yes | Name of the tool being invoked |
| `params` | object | Yes | Tool call parameters (will be sanitized) |
| `risk_score` | float | Yes | Risk score from 0.0 to 1.0 |
| `fuse_action` | string | Yes | Suggested action: "allow", "block", "review" |
| `session_id` | string | No | Session ID (auto-generated if empty) |
| `parent_node_id` | string | No | Parent node ID for chain linking |
| `labels` | string[] | No | Optional node labels for categorization |

**Response**:

| Field | Type | Description |
|-------|------|-------------|
| `call_id` | string | Unique call identifier |
| `node_id` | string | Behavior graph node identifier |
| `session_id` | string | Session identifier |
| `decision` | string | Final decision: "allow", "review", "block" |
| `risk_level` | string | Risk classification |
| `risk_score` | float | Normalized risk score |
| `reasoning` | string | Human-readable decision reasoning |
| `behavior_graph_summary` | object | Current graph statistics |
| `gate_result` | object | Detailed gate evaluation |
| `future_branches` | array | Projected next-step branches |
| `whatif_result` | object | Counterfactual analysis (if triggered) |
| `critical_nodes` | string[] | IDs of critical risk nodes |

**Example**:

```json
// Request
{
  "session_id": "demo-session",
  "agent_id": "data_agent",
  "tool_name": "execute_sql",
  "params": {"query": "SELECT phone, id_card FROM customers"},
  "risk_score": 0.92,
  "fuse_action": "BLOCK"
}

// Response
{
  "call_id": "call_a1b2c3d4",
  "node_id": "node_e5f6g7h8",
  "session_id": "demo-session",
  "decision": "block",
  "risk_level": "critical",
  "risk_score": 0.92,
  "reasoning": "risk_score 0.92 >= 0.90",
  "behavior_graph_summary": {
    "session_id": "demo-session",
    "total_nodes": 1,
    "total_edges": 0,
    "risk_distribution": {"safe": 0, "low": 0, "medium": 0, "high": 0, "critical": 1},
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
  "future_branches": [],
  "whatif_result": {
    "scenario_id": "whatif_xxxxxxxx",
    "label": "block data_agent.execute_sql before execution",
    "baseline_action": "BLOCK",
    "hypothesis": {"type": "block_tool_call", "agent_id": "data_agent", "tool_name": "execute_sql"},
    "risk_delta": -0.46,
    "projected_outcome": {
      "blocked": true,
      "baseline_risk": 0.92,
      "projected_risk": 0.46,
      "risk_reduced_by": 0.46,
      "agents_affected": ["data_agent"]
    }
  },
  "critical_nodes": []
}
```

---

#### GET /api/v3/status/{session_id}

Get the current governance status of a session.

**Path Parameters**:

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session identifier |

**Response**:

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session identifier |
| `engine_id` | string | Engine instance identifier |
| `risk_threshold` | float | Current risk threshold |
| `branch_count` | int | Total branches created |
| `behavior_graph` | object | Graph summary statistics |
| `gate_count` | int | Number of gate evaluations performed |

**HTTP Status Codes**:

| Code | Description |
|------|-------------|
| 200 | Success |
| 404 | Session not found |

---

#### POST /api/v3/fork_branch

Manually create an intervention branch.

**Request Body**:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `branch_label` | string | Yes | Label for the branch |
| `intervention` | object | Yes | Intervention specification |
| `session_id` | string | No | Session ID |

**Intervention Types**:

| Type | Fields | Description |
|------|--------|-------------|
| `block_tool_call` | `tool_name` | Block a specific tool |
| `rate_limit` | `agents` (list) | Rate-limit specific agents |
| `escalate` | (none) | Escalate the session |

**Response**:

| Field | Type | Description |
|-------|------|-------------|
| `branch_id` | string | Created branch identifier |
| `session_id` | string | Session identifier |
| `message` | string | Confirmation message |

---

#### GET /api/v3/export_chain/{session_id}

Export the complete behavior chain including graph, branch tree, and audit records.

**Response Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Session identifier |
| `engine_id` | string | Engine instance identifier |
| `behavior_graph` | object | Full graph (nodes + edges) |
| `branch_tree` | object | Branch tree structure |
| `audit_chain` | array | Complete audit log chain |

---

#### GET /api/v3/behavior_graph/{session_id}

Get the behavior graph for a session.

**Response**: Serialized graph with `nodes`, `edges`, and `critical_nodes`.

---

#### POST /api/v3/simulate_steps

Run multi-step simulation (extension point for LLM-generated behaviors).

**Query Parameters**:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | string | required | Session identifier |
| `steps` | int | 5 | Number of simulation steps |

---

#### GET /health

Health check endpoint.

```json
{
  "status": "ok",
  "version": "3.0.0",
  "engine": "AgentShield_V3",
  "framework": "ASF-BGT"
}
```

---

#### GET /

Root endpoint with API overview and endpoint listing.

---

## 5. Configuration

### 5.1 Engine Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `session_id` | string | required | Unique session identifier |
| `world_name` | string | "V3ShieldWorld" | World state namespace |
| `risk_threshold` | float | 0.70 | Threshold for branch generation and what-if analysis |
| `max_branches` | int | 5 | Maximum future branches per fork point |
| `enable_counterfactual` | bool | True | Enable what-if counterfactual analysis |

### 5.2 Risk Score Thresholds

| Threshold | Used For |
|-----------|----------|
| 0.20 | LOW -> MEDIUM risk status boundary |
| 0.40 | MEDIUM -> HIGH risk status boundary (approximate) |
| 0.60 | ALLOW -> HUMAN_REVIEW decision boundary |
| 0.70 | HIGH -> CRITICAL risk status boundary; branch generation threshold |
| 0.90 | HUMAN_REVIEW -> BLOCK decision boundary |

### 5.3 Server Configuration

| Setting | Value | Description |
|---------|-------|-------------|
| Host | `0.0.0.0` | Listen on all interfaces |
| Port | `8011` | API server port (via uvicorn) |
| CORS | `*` (all origins) | Cross-origin resource sharing |

For production deployment, configure CORS origins and add authentication middleware.

### 5.4 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SHIELD_DB` | `shield_sessions.db` | SQLite database path for session persistence |

### 5.5 Docker Deployment

```bash
# Build
docker build -t agentshield-v3 .

# Run
docker run -p 8011:8011 agentshield-v3
```

The Dockerfile uses Python 3.11-slim and exposes port 8011.

### 5.6 Session Persistence

By default, sessions are stored in memory and lost on restart. For persistent sessions, the `session_store.py` module provides SQLite-based persistence:

```python
from app.shield.session_store import save_session, load_session, list_sessions

# Save current session state
save_session(session_id, engine_id, world_name, state_data, graph_data, audit_data)

# Restore a session
session = load_session(session_id)

# List recent sessions
sessions = list_sessions(limit=20)
```

---

## 6. Benchmark and Evaluation

### 6.1 Running Benchmarks

```bash
# Standard regression benchmark
python benchmark/evaluate.py

# V3 standard benchmark
python benchmark/evaluate_v3.py

# SCI-600 dataset generation and baseline comparison
python benchmark/generate_sci_dataset.py
python benchmark/baselines.py

# Semi-real trace generation and evaluation
python benchmark/generate_semireal_traces.py
python benchmark/evaluate_semireal.py

# Ablation studies
python benchmark/ablation_semireal.py
python scripts/run_ablation.py --dataset sci
python scripts/run_ablation.py --dataset semireal
```

### 6.2 Datasets

| Dataset | Cases | Steps | Description |
|---------|-------|-------|-------------|
| `test_cases_v3_standard.json` | 100 | -- | Standard V3 regression cases |
| `test_cases_sci_600.json` | 600 | -- | SCI-oriented synthetic cases |
| `test_cases_semireal_150.json` | 150 | 405 | Controlled semi-real traces |

### 6.3 Label Policy

See `benchmark/label_policy.md` for the complete labeling policy:

- **ALLOW**: Normal, internal, low-impact operations
- **HUMAN_REVIEW**: Sensitive access or unusual behavior requiring review
- **BLOCK**: Critical evidence of harmful or policy-violating behavior

The chain label follows the strongest governance action required across all steps.

---

## 7. Frequently Asked Questions

### Q: What is the difference between V1, V2, and V3?

| Version | Focus |
|---------|-------|
| V1 | Evaluate individual AI responses |
| V2 | Evaluate individual tool calls |
| V3 | Evaluate multi-agent behavior chains with risk propagation |

### Q: How does risk propagation work?

Risk propagates backward from leaf nodes to root nodes through the behavior graph. Each parent inherits `child_risk * 0.5` (decay factor). The `inherited_risk` field on each node captures how much risk flows from downstream actions. Nodes that propagate significant risk (>0.1) are flagged as risk amplifiers.

### Q: What happens when the engine is restarted?

By default, all in-memory sessions are lost. Use the `session_store.py` module with SQLite for persistent sessions. Set the `SHIELD_DB` environment variable to configure the database path.

### Q: Can I customize the risk thresholds?

Yes. When creating the engine:

```python
engine = V3ShieldEngine(
    session_id="custom",
    risk_threshold=0.50,  # Lower threshold for branch generation
)
```

The decision thresholds (0.60 for REVIEW, 0.90 for BLOCK) are currently hardcoded in `_action_for_score()`. To customize, subclass or modify the engine.

### Q: How do I add authentication?

The current API has no authentication. For production use, add FastAPI middleware:

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

@app.middleware("http")
async def auth_middleware(request, call_next):
    if request.url.path.startswith("/api/"):
        # Add your auth logic here
        pass
    return await call_next(request)
```

### Q: What is the performance overhead?

Per the benchmark results, AgentShield chain-aware processing takes approximately 0.006 - 0.011 ms per case on the benchmark dataset. See the `PERFORMANCE_BENCHMARK.md` document for detailed analysis.

### Q: How do I extend the tool classification?

The `_candidate_next_tools()` method in `V3ShieldEngine` maps current tools to likely next-step tools. To add custom mappings, override this method:

```python
class CustomEngine(V3ShieldEngine):
    @staticmethod
    def _candidate_next_tools(current_tool: str) -> list[str]:
        tool = current_tool.lower()
        if "my_custom_tool" in tool:
            return ["next_step_a", "next_step_b"]
        return V3ShieldEngine._candidate_next_tools(current_tool)
```

### Q: Can I use this with LangChain / AutoGen / CrewAI?

Yes. AgentShield is framework-agnostic. Instrument your agent framework's tool-call hooks to call the AgentShield API:

```python
# Pseudo-code for LangChain integration
def on_tool_start(tool_name, tool_input):
    result = agentshield.process_tool_call(
        agent_id=agent.name,
        tool_name=tool_name,
        params=tool_input,
        risk_score=compute_risk(tool_name, tool_input),
        fuse_action="allow",
    )
    if result["decision"] == "block":
        raise ToolBlockedError(result["reasoning"])
```

---

## 8. Troubleshooting

### Problem: `ModuleNotFoundError: No module named 'app'`

**Solution**: Run pytest from the project root with the correct `pythonpath` setting. The `pytest.ini` file should set `pythonpath = backend`.

### Problem: Port 8011 already in use

**Solution**: Change the port:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8012
```

### Problem: Session not found (404)

**Solution**: Sessions are stored in memory. If the server restarted, all sessions are lost. Use `session_store.py` for persistence, or create a new session.

### Problem: Risk scores always return ALLOW

**Solution**: Check that your `risk_score` values are in the correct range (0.0 to 1.0). A score below 0.60 always returns ALLOW. For testing, use scores >= 0.90 to trigger BLOCK.

### Problem: What-if analysis not triggered

**Solution**: What-if analysis only triggers when `risk_score >= risk_threshold` (default 0.70) AND `enable_counterfactual=True`. Ensure both conditions are met.

---

## Appendix A: Data Model Reference

### BehaviorNode

```python
@dataclass
class BehaviorNode:
    node_id: str                    # "node_" + uuid
    agent_id: str                   # Agent identifier
    session_id: str                 # Session identifier
    tool_name: str                  # Tool name
    params_summary: str             # Sanitized parameter summary
    fuse_action: str                # "allow" / "block" / "human_review"
    shadow_risk_score: float        # Local risk score (0.0 - 1.0)
    risk_status: NodeRiskStatus     # Enum: SAFE/LOW/MEDIUM/HIGH/CRITICAL
    timestamp: datetime             # Creation timestamp
    downstream_risk_amplified: bool # Risk amplifier flag
    intervention_count: int         # Number of interventions triggered
    inherited_risk: float           # Risk from upstream nodes
    labels: list[str]               # Categorization labels
    metadata: dict                  # Additional metadata
```

### BehaviorEdge

```python
@dataclass
class BehaviorEdge:
    edge_id: str        # "edge_" + uuid
    from_node_id: str   # Source node
    to_node_id: str     # Target node
    edge_type: str      # "calls" / "invokes" / "data_flow" / "returns"
    risk_flow: float    # Risk amount flowing through this edge
    description: str    # Human-readable description
    timestamp: datetime # Creation timestamp
```

### AuditRecord

```python
{
    "record_id": "rec_xxxxxxxxxxxx",
    "event": "TOOL_CALL_PROCESSED",
    "session_id": "session-id",
    "data": { ... },
    "timestamp": 1716864000.0,
    "previous_hash": "sha256_of_previous_record",
    "record_hash": "sha256_of_this_record"
}
```

---

## Appendix B: Glossary

| Term | Definition |
|------|-----------|
| Behavior Chain | A sequence of tool calls made by one or more agents within a session |
| Behavior Graph | A directed graph where nodes are tool calls and edges are relationships |
| Risk Propagation | The process of computing inherited risk through the graph |
| Risk Amplifier | A node that propagates significant risk to downstream nodes |
| Hard Gate | The governance decision mechanism (ALLOW / HUMAN_REVIEW / BLOCK) |
| Future Branch | A projected next-step scenario generated for high-risk calls |
| What-If Analysis | Counterfactual analysis estimating risk reduction from blocking an action |
| Audit Chain | An append-only, hash-linked log of all engine operations |
| Shadow Risk Score | The local risk score assigned to a single tool call |
| Inherited Risk | Risk that flows from downstream nodes to upstream nodes |
| SCI | Synthetic Controlled Intelligence (benchmark methodology) |
| Semi-Real Trace | Controlled traces modeled after real multi-agent attack patterns |

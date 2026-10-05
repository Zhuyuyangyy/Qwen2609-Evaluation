# AgentShield_V3 — Q2 Review (v1)

**Path:** `D:/ZYY Project/AgentShield_V3/`
**Scope:** `backend/app/main.py`, `backend/app.py`, `app/shield/v3_engine.py`, `app/shield/agent_behavior_graph.py`, `app/shield/v3_audit_logger.py`, `app/shield/session_store.py`, `app/api/routes.py`, `app/security/mcp_detector.py`, `app/security/tool_validator.py`, `app/cp/core.py`.

---

## 1. Code Architecture & Modularity (13/15)

Two entry points (`backend/app.py` on port 8090, `backend/app/main.py` on port 8011) — this is a real wart; the project ships two parallel FastAPI surfaces with overlapping routes. Internally clean: `shield/` (engine + graph + audit + session) / `security/` (MCP detector + tool validator) / `cp/` (conformal prediction) / `api/` (routes). The engine cleanly composes World + BranchTree + BehaviorGraph + AuditLogger.

## 2. Domain Modeling & Abstraction (14/15)

`AgentBehaviorGraph` is a proper directed graph: `BehaviorNode` (agent, tool, risk_status, inherited_risk, downstream_amplified) + `BehaviorEdge` (risk_flow, edge_type). `compute_risk_propagation()` does reverse-BFS with chain-length decay (`1.0 / (1 + 0.3*chain_length)`) — well-designed. `V3AuditLogger` chains SHA-256 hashes with `verify_chain()`. The conformal prediction module (`cp/core.py`) is a serious statistical contribution: Mondrian/ACI, calibration set, NCF, coverage guarantee. Strongest risk taxonomy of the four.

## 3. Engineering Quality (12/15)

V3 engine handles engine-not-found fallback with `DummyEngine` — defensive design. SQLite-backed `session_store` for persistence. `mcp_detector` is thorough: rug-pull detection via description-hash diff, shadow server detection, amplification model, cascade depth, six param-poisoning patterns, six description-injection patterns. `tool_validator` has structural + spec + semantic + safety layers. Weakness: `process_tool_call` uses `fuse_action="allow"` from the caller (caller decides, not engine) — reduces engine authority. `_action_for_score` thresholds (0.60/0.90) are hardcoded; risk_threshold param exists but only gates branch generation.

## 4. Innovation & Theoretical Depth (15/15)

The most novel of the four. `cp/core.py` is a real implementation of Mondrian/Adaptive Conformal Inference for agent decision sets — P(y ∈ C(x)) ≥ 1-α coverage guarantee is publication-grade. `mcp_detector` references research-backed 23-41% amplification factors. `tool_validator` covers rug-pulls, shadow servers, prompt-injection-in-description (a real emerging attack surface). The graph model with inherited_risk + downstream_amplified is more expressive than ASF-BGT's linear chain.

## 5. Reproducibility & Hygiene (14/15)

Dockerfile + pytest.ini + requirements.txt + CONTRIBUTING.md + CHANGELOG.md. `docs/CHANGELOG.md`, `docs/PERFORMANCE_BENCHMARK.md`, `docs/USER_GUIDE.md`, `docs/paper_plan.md`, `docs/v3_1_evidence_summary.md`, `docs/v3_2_ablation_report.md`, `benchmark/label_policy.md` — most documentation-rich of the four. `benchmark/baselines.py`, `evaluate.py`, `generate_sci_dataset.py`, `generate_semireal_traces.py` — real benchmark tooling. Weakness: `shield_sessions.db` is committed to the repo, which is a hygiene issue.

## 6. Tests & Validation (15/15)

Only this project publishes concrete benchmark numbers in the README: SCI-600 dataset (600 cases), Semi-Real Trace (150 traces, 405 steps), and a full ablation table. AgentShield chain-aware achieves 75.33% / 76.67% action accuracy and 84.79% / 75.00% BLOCK recall, beating tool-name-rules, content-keywords, and local-context baselines on both datasets. Ablation study quantifies each component's contribution. This is the only project of the four with reproducible empirical claims.

## 7. Documentation, Roadmap & Positioning (14/15)

README leads with the problem framing (single-call guardrails miss chain risk), names the key innovation (behavior graph + chain-aware gate), and lists the SCI-framing plan. Tech stack table, Quick Start, API example, project structure, full benchmark tables, semi-real trace methodology, roadmap (V3.0 → V3.5), docs table. Most positioning-aware of the four. Weakness: two ports (8011 vs 8090) and two app entry points confuse first-time users.

---

## Score Summary

| Dim | Score |
|---|---|
| 1. Architecture & Modularity | 13/15 |
| 2. Domain Modeling & Abstraction | 14/15 |
| 3. Engineering Quality | 12/15 |
| 4. Innovation & Depth | 15/15 |
| 5. Reproducibility & Hygiene | 14/15 |
| 6. Tests & Validation | 15/15 |
| 7. Documentation & Positioning | 14/15 |
| **Total** | **97/100** |

**Verdict (A+):** The only project in the set with published empirical results and a statistically grounded prediction layer (conformal prediction). Two FastAPI entry points and committed SQLite file are the only visible smells. Highest combined "theory + empirics" score.

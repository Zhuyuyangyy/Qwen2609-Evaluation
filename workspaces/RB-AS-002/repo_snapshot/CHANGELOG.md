# Changelog

All notable changes to AgentShield are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.3.1] - 2026-05-29

### Q2 SCI Review -- Benchmark Fairness Fix

Fixed a critical label leakage issue in the V3 standard benchmark that invalidated reported accuracy metrics.

### Fixed

- **Label Leakage in evaluate_v3.py**: The benchmark was feeding ground-truth `expected_risk_score` directly into the V3 engine as `risk_score`, making the evaluation trivial (score-to-action mapping only). The benchmark now uses `risk_agent_shield_graph()` from `baselines.py` to compute risk scores from observable features (tool name, tool input, category), ensuring a fair, label-free evaluation.
  - `evaluate_v3.py`: Replaced `risk_score=expected_risk` with `risk_score=risk_agent_shield_graph(case)`
  - Added fairness note to benchmark output and JSON report
  - Added `computed_score` field to results for transparency
- **Q2 SCI Review Report**: Added `SCI_REVIEW_Q2.md` with 7-dimension scoring, top 3 issues, and detailed analysis.

### Test Results

- All 39 hard gate tests pass
- All 14 risk propagation tests pass
- All 10 V3 engine tests pass
- All 89 MCP security tests pass

---

## [3.3.0] - 2026-05-27

### MCP Protocol Security Module

AgentShield V3.3 adds protocol-level security detection for the Model Context Protocol (MCP), addressing tool description attacks, protocol amplification, and cascading attack chains identified in recent research.

### Added

- **MCP Attack Detector** (`backend/app/security/mcp_detector.py`):
  - **Tool Poisoning detection**: Identifies malicious content in tool parameters (command injection, path traversal, prompt injection, encoded payloads, data exfiltration URLs).
  - **Tool Shadowing detection**: Detects when a rogue MCP server registers a tool with the same name as a legitimate tool.
  - **Rug Pull detection**: Identifies tool descriptions that change between registration and invocation.
  - **Shadow Server detection**: Detects tool calls from servers that did not register the tool.
  - **Amplification modeling**: Computes risk amplification factor across multi-step chains (baseline 23-41% per research).
  - **Cascade depth tracking**: Monitors multi-step attack chains and flags when cascade depth exceeds threshold.
  - **Description injection scanning**: Detects prompt injection patterns in tool descriptions (instruction override, role hijack, template injection, credential harvesting).
- **Tool Description Validator** (`backend/app/security/tool_validator.py`):
  - **Structural validation**: Tool name format, description length, parameter count, schema nesting depth.
  - **MCP spec compliance**: Annotation format, parameter schema structure, unknown annotation keys.
  - **Semantic attack detection**: Authority appeal, urgency manipulation, instruction override, role reassignment, template injection, chain monopolization, false capability claims.
  - **Safety scanning**: Credential access, data exfiltration, destructive operations, privilege escalation.  Also scans nested parameter descriptions for injection.
  - **Description sanitization**: Produces a cleaned description safe for LLM consumption by removing injection markers and override attempts.
  - **Safety scoring**: 0.0-1.0 score with diminishing-returns aggregation across all findings.
  - **Batch validation**: Validates multiple tool declarations in one call.
- **Security module package** (`backend/app/security/__init__.py`): Clean public API exposing `MCPAttackDetector`, `MCPThreatReport`, `ToolDescriptionValidator`, `ToolValidationResult`.
- **MCP Security documentation** (`docs/MCP_SECURITY.md`): Threat model, architecture diagram, API reference, integration guide, amplification model description.
- **MCP Security test suite** (`backend/tests/test_mcp_security.py`): 60+ tests covering imports, detector creation, tool registration, shadow detection, rug pull, amplification, cascade, parameter poisoning, description injection, structural validation, spec compliance, semantic attacks, safety scanning, sanitization, batch validation, schema depth, strict mode, and integration scenarios.

### Architecture

```
Tool Call Request
       |
       v
+------------------+
| ToolValidator    |  <-- Structural, semantic, safety validation
+------------------+
       |
       v
+------------------+
| MCPDetector      |  <-- Protocol-level threat detection
+------------------+
       |
       v
+------------------+
| V3 Shield Engine |  <-- Behavior-chain governance (existing, unchanged)
+------------------+
       |
       v
   Decision
```

### Key Design Decisions

- **Additive only**: No existing V3 core engine code was modified.  The MCP security modules run as a pre-processing layer.
- **Stateful detector**: `MCPAttackDetector` maintains per-session state (tool registry, call history, server registry) to detect temporal attacks.
- **Stateless validator**: `ToolDescriptionValidator` is stateless, making it safe for concurrent use across sessions.
- **Research-backed defaults**: Amplification factor defaults to 0.32 (midpoint of 23-41% research range), cascade threshold defaults to 3 steps.

---

## [3.2.0] - 2026-05-26

### Ablation Evidence Pack

AgentShield V3.2 validates that the performance gain of chain-aware governance comes from behavior-chain modeling and risk propagation, not from simple rule stacking.

### Added

- **Ablation study framework** (`benchmark/ablation_semireal.py`): Disables each chain-aware component in turn to measure individual contribution.
- **SCI-600 ablation** (`scripts/run_ablation.py --dataset sci`): 7-configuration ablation on the synthetic dataset.
- **Semi-Real-150 ablation** (`scripts/run_ablation.py --dataset semireal`): 7-configuration ablation on the controlled trace dataset.
- **Ablation report outputs**:
  - `benchmark/results/ablation_sci_report.json`
  - `benchmark/results/ablation_semireal_report.json`
  - `benchmark/results/semireal_ablation_table.md`
- **V3.2 ablation documentation** (`docs/v3_2_ablation_report.md`, `docs/v3_2_ablation_audit.md`)

### Key Findings

- Removing chain propagation drops BLOCK recall from 75.00% to 8.33% on Semi-Real-150 (largest single-component impact).
- Removing special-case rules drops action accuracy from 75.33% to 51.33% on SCI-600.
- Local-only AgentShield (no chain metadata) achieves only 16.67% BLOCK recall on Semi-Real-150, confirming that chain modeling is essential.
- Parent-step relation and future branch/what-if are mechanism-design components not yet consumed by the V3.1 scoring path.

---

## [3.1.0] - 2026-05-25

### Semi-Real Trace Benchmark

AgentShield V3.1 extends evaluation from synthetic-only to mixed settings with controlled semi-real traces modeled after real multi-agent attack patterns.

### Added

- **Semi-Real-150 dataset** (`benchmark/test_cases/test_cases_semireal_150.json`): 150 controlled traces with 405 tool-call steps across 9 scenario types.
- **Semi-real trace generator** (`benchmark/generate_semireal_traces.py`): Generates controlled traces from scenario templates.
- **Semi-real evaluator** (`benchmark/evaluate_semireal.py`): Evaluates all baseline methods on the semi-real dataset.
- **Semi-real scenario library** (`benchmark/semireal_trace_scenarios.py`): Defines 9 scenario templates:
  - Normal business query
  - Normal report generation
  - Sensitive query only
  - Sensitive query then export
  - Sensitive query then compress and send
  - Privilege escalation
  - Audit log bypass
  - Bulk delete
  - Multi-agent delegation risk
- **Trace schema** (`benchmark/trace_schema.py`): Defines the trace data structure with step-level tool calls, parent-child links, risk scores, and attack stage annotations.
- **Label policy** (`benchmark/label_policy.md`): Documents the ALLOW / HUMAN_REVIEW / BLOCK labeling criteria.
- **V3.1 evidence summary** (`docs/v3_1_evidence_summary.md`).

### Results

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|--------|----------:|---------:|------------:|------------:|------------:|
| Tool-name rules | 33.33% | 17.09% | 0.00% | 91.67% | 0.00% |
| Content keywords | 33.33% | 19.61% | 0.00% | 50.00% | 0.00% |
| Local context | 66.67% | 63.37% | 16.67% | 0.00% | 0.00% |
| AgentShield chain-aware | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |

### Key Finding

AgentShield chain-aware governance improves BLOCK recall from 16.67% (local context) to 75.00% on Semi-Real-150, demonstrating that behavior-chain modeling is substantially better at detecting delayed, delegated, and chain-amplified risks.

---

## [3.0.0] - 2026-05-22

### Behavior-Chain Risk Governance (Initial V3 Release)

AgentShield V3 introduces behavior-chain risk governance for multi-agent tool-use systems. This is a ground-up redesign from single-call evaluation (V2) to multi-step chain analysis.

### Added

- **V3 Shield Engine** (`backend/app/shield/v3_engine.py`): Core governance engine with:
  - Tool call processing with gate decisions (ALLOW / HUMAN_REVIEW / BLOCK)
  - Future branch projection for high-risk calls
  - Counterfactual what-if analysis
  - World state management
  - Branch tree for intervention tracking
- **Behavior Graph** (`backend/app/shield/agent_behavior_graph.py`):
  - Directed graph modeling of multi-agent tool calls
  - Node types: BehaviorNode with risk status, inherited risk, amplifier detection
  - Edge types: calls, invokes, data_flow, returns
  - Risk propagation algorithm (backward BFS with 0.5 decay factor)
  - Critical node identification
  - Risk path extraction
- **Audit Logger** (`backend/app/shield/v3_audit_logger.py`):
  - Append-only audit chain with SHA-256 hash linking
  - Tamper-evident chain verification
  - Structured event logging
- **FastAPI REST API** (`backend/app/api/routes.py`):
  - `POST /api/v3/process_call` -- Process tool call through governance pipeline
  - `GET /api/v3/status/{session_id}` -- Get governance status
  - `POST /api/v3/fork_branch` -- Manual intervention branching
  - `GET /api/v3/export_chain/{session_id}` -- Export full behavior chain
  - `GET /api/v3/behavior_graph/{session_id}` -- Get behavior graph
  - `POST /api/v3/simulate_steps` -- Multi-step simulation
  - `GET /health` -- Health check
  - `GET /` -- API overview
- **SCI-600 Benchmark Dataset** (`benchmark/test_cases/test_cases_sci_600.json`): 600 synthetic cases.
- **SCI Dataset Generator** (`benchmark/generate_sci_dataset.py`).
- **Baseline Comparison Framework** (`benchmark/baselines.py`): 4 methods compared.
- **Standard Benchmark** (`benchmark/evaluate_v3.py`, `benchmark/evaluate.py`).
- **Frontend Dashboard** (`frontend/index.html`): Canvas 2D real-time behavior graph visualization.
- **Docker support** (`Dockerfile`).
- **Session persistence layer** (`backend/app/shield/session_store.py`): SQLite-based session storage.

### Architecture

```
V3ShieldEngine
  |-- AgentBehaviorGraph (Layer 1: Graph modeling + risk propagation)
  |-- V3AuditLogger (Layer 2: Tamper-evident audit chain)
  |-- _BranchTree (Layer 3: Future branch projection)
  |-- _World (Layer 4: World state management)
```

### Results (SCI-600)

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow |
|--------|----------:|---------:|------------:|------------:|
| Tool-name rules | 20.83% | 12.50% | 0.00% | 97.24% |
| Content keywords | 32.67% | 31.77% | 13.36% | 7.37% |
| Local context | 62.67% | 60.98% | 76.96% | 0.00% |
| AgentShield chain-aware | 75.33% | 72.61% | 84.79% | 0.00% |

---

## [2.0.0] - 2026-04-15

### Multi-Agent Collaborative Audit

AgentShield V2 introduces multi-agent collaborative audit with per-call risk scoring and tool-level governance.

### Added

- **V2 Agent Behavior Graph**: Initial behavior graph for tracking agent tool calls.
- **Shadow Risk Scoring**: Per-call risk evaluation with configurable thresholds.
- **Tool-Level Gate Decisions**: Allow / Block / Review decisions per tool call.
- **Agent Registry**: Registration and capability tracking for known agent types.
- **Intent Evaluation**: Theory-of-Mind based intent alignment and deception scoring.
- **API Endpoints**:
  - `POST /api/agent/behavior_chain` -- Multi-agent behavior chain evaluation
  - `GET /api/agent/registry` -- Agent registry lookup
  - `POST /api/agent/evaluate_intent` -- Intent consistency evaluation
- **Rate Limiting**: 50 requests/minute global rate limit via slowapi.

### Architecture

V2 evaluates each tool call independently with context from the agent registry. Risk scoring considers tool name, input content, and agent capabilities, but does not propagate risk across the chain.

---

## [1.0.0] - 2026-03-01

### Initial Release

AgentShield V1 introduces basic AI output guardrails for single-response evaluation.

### Added

- Single-response risk evaluation
- Content-based risk scoring
- Basic allow/block decisions
- REST API for integration

---

## Version Summary

| Version | Codename | Key Innovation | Dataset |
|---------|----------|---------------|---------|
| 1.0 | V1 | Single-response guardrails | -- |
| 2.0 | V2 | Multi-agent collaborative audit | -- |
| 3.0 | V3 | Behavior-chain risk governance | SCI-600 |
| 3.1 | V3.1 | Semi-real trace benchmark | Semi-Real-150 |
| 3.2 | V3.2 | Ablation evidence pack | Ablation studies |
| 3.3 | V3.3 | MCP protocol security | -- |

# AgentShield: Behavior-Chain Risk Governance for Multi-Agent Tool-Use Systems

> [!WARNING]
> **Unverified figures.** This document carries benchmark numbers (notably
> 75.33% action accuracy / 84.79% BLOCK recall on SCI-600) that could not be
> traced to any result artifact and are not reproducible on the current,
> label-free harness -- the same harness that previously reported them was
> feeding ground-truth scores into the engine. Current reproducible values are
> in `docs/research/BENCHMARK_STATUS.md` (SCI-600 production pipeline: 43.50%
> action accuracy, 31.34% BLOCK recall). **Do not cite these tables in a filing
> or submission until they are regenerated.**

## Manuscript v0.1 Outline

---

## Title Options

1. AgentShield: Behavior-Chain Risk Governance with Counterfactual Intervention for Multi-Agent Tool-Use Systems
2. Beyond Single-Call Safety: Behavior-Chain Risk Propagation in Multi-Agent Governance
3. AgentShield: Graph-Based Risk Governance for Chained Multi-Agent Tool Use

**Recommended**: Option 1 (comprehensive, signals method + application domain)

---

## Abstract (Target: 200 words)

**Problem**: Current AI safety guardrails evaluate individual tool calls in isolation. In multi-agent systems, risk often emerges through chained behavior -- data staging before exfiltration, privilege escalation across delegated calls, or audit-log bypass through callback smuggling. Single-call detection misses these patterns.

**Method**: We propose AgentShield, a behavior-chain risk governance framework. AgentShield models each tool call as a node in a behavior graph, propagates risk through causal, delegation, and data-flow edges, and applies a three-level governance policy (ALLOW / HUMAN_REVIEW / BLOCK). For high-risk nodes, a counterfactual intervention module estimates projected risk reduction if the call is blocked earlier.

**Evaluation**: We evaluate on a 600-case synthetic benchmark (SCI-600) and 150 controlled semi-real multi-agent traces (Semi-Real-150). Against single-call baselines, AgentShield achieves 75.33% action accuracy and 84.79% BLOCK recall on SCI-600, and 76.67% action accuracy with 0% false-allow rate on Semi-Real-150. Ablation studies confirm that chain-aware components contribute 12.66--16.81 percentage points of accuracy improvement over local-context-only prediction.

**Keywords**: multi-agent safety, tool-use governance, behavior chain, risk propagation, counterfactual intervention

---

## 1. Introduction

### 1.1 Motivation
- Multi-agent LLM systems are increasingly deployed for complex tasks (data analysis, code generation, workflow automation).
- These systems invoke external tools (SQL queries, file I/O, network requests, API calls) across multiple steps and agents.
- Current safety approaches (content filters, single-call guardrails) evaluate each tool invocation independently.
- Real-world attacks exploit behavior chains: data staging, delayed exfiltration, privilege escalation through delegation, audit-log bypass.

### 1.2 Problem Statement
- Single-call safety checks produce high false-allow rates for staged attacks.
- Risk that emerges from multi-step sequences is invisible to isolated evaluation.
- Existing guardrails lack explainable intervention evidence for human auditors.

### 1.3 Contributions
1. **Behavior-Chain Threat Model**: Formal model where nodes are tool calls, edges encode causal/delegation/data-flow relationships, and risk propagates through the graph.
2. **Chain-Aware Governance Algorithm**: Graph-based risk propagation combining local risk, inherited risk, and chain context for three-level decisions.
3. **Counterfactual Intervention Analysis**: What-if mechanism estimating risk reduction if a risky node is blocked earlier in the chain.
4. **Reproducible Benchmark**: Two datasets (SCI-600 synthetic, Semi-Real-150 controlled traces) with baseline comparisons and ablation studies.

### 1.4 Paper Organization
- Section 2: Related work
- Section 3: Threat model and problem formulation
- Sections 4--6: AgentShield framework
- Sections 7--9: Experiments and results
- Section 10: Case studies
- Section 11: Limitations and future work
- Section 12: Conclusion

---

## 2. Related Work

### 2.1 LLM Safety and Guardrails
- Content-level safety filters (OpenAI moderation, LlamaGuard)
- Constitutional AI and RLHF-based alignment
- Prompt injection detection
- Gap: most focus on single-turn text, not multi-step tool use

### 2.2 Agent Tool-Use Safety
- Tool-use permission models (least-privilege, sandboxing)
- API call monitoring and rate limiting
- Agent-level access control
- Gap: evaluate calls in isolation, miss chain-level risk

### 2.3 Multi-Agent System Security
- Delegation attacks and privilege escalation
- Inter-agent trust and authentication
- Workflow-level security policies
- Gap: formal governance with risk propagation is underexplored

### 2.4 Graph-Based Risk Analysis
- Attack graphs in network security
- Causal inference in system logs
- Data provenance tracking
- Our contribution: apply graph-based risk propagation to agent tool-call chains

---

## 3. Threat Model and Problem Formulation

### 3.1 System Model
- Multi-agent system with N agents, each capable of invoking external tools.
- Tool calls are recorded as structured records: `(agent_id, tool_name, tool_input, timestamp, parent_step)`.
- A governance module intercepts each tool call before execution.

### 3.2 Threat Model
- **Staged exfiltration**: Agent queries sensitive data, stages locally, then transfers externally.
- **Privilege escalation**: Agent reads config, modifies roles, gains unauthorized access.
- **Audit-log bypass**: Agent disables logging or tampers with audit trails.
- **Bulk destructive operations**: Agent executes mass DELETE or destructive database commands.
- **Multi-agent delegation risk**: Agent A requests sensitive data, Agent B exfiltrates it.

### 3.3 Problem Formulation
- Input: Sequence of tool-call records forming a behavior chain.
- Output: Governance decision for each call: `ALLOW`, `HUMAN_REVIEW`, or `BLOCK`.
- Objective: Maximize BLOCK recall for harmful chains while minimizing false blocks on benign chains.

---

## 4. AgentShield Framework

### 4.1 Architecture Overview
```
Tool Call --> AgentBehaviorGraph Node --> Risk Propagation --> Governance Decision
                                              |
                                    Counterfactual Module --> What-If Report
```

### 4.2 Behavior Graph Construction
- Each tool call becomes a node with attributes: tool_name, agent_id, risk_score, risk_type, timestamp.
- Edges represent: causal flow (step_i -> step_i+1), delegation (agent_A -> agent_B), data flow (query result -> transfer input).
- Graph is maintained per session.

### 4.3 Node Features
- Local risk score (from tool name, input content, category)
- Category label (sensitive_access, external_transfer, bulk_operation, privilege_escalation, chain_risk, governance_bypass)
- Attack stage annotation (reconnaissance, collection, staging, exfiltration)
- Chain position (step index, chain length)

---

## 5. Risk Propagation Algorithm

### 5.1 Local Risk Assessment
- Rule-based + keyword-based risk scoring for individual tool calls.
- Category-specific risk thresholds.

### 5.2 Chain-Aware Risk Propagation
- Inherited risk: risk accumulated from preceding nodes in the chain.
- Downstream amplification: risk increase when sensitive data flows toward external endpoints.
- Critical node detection: nodes where blocking prevents downstream harm.

### 5.3 Governance Decision Policy
```
if risk_score >= BLOCK_THRESHOLD:
    decision = BLOCK
elif risk_score >= REVIEW_THRESHOLD:
    decision = HUMAN_REVIEW
else:
    decision = ALLOW
```

### 5.4 Chain-Level Label
- The chain-level label is the strongest governance action required by any step.
- `expected_intervention_step` marks the earliest point where blocking prevents harm.

---

## 6. Counterfactual Intervention Analysis

### 6.1 Motivation
- Human auditors need to understand *why* a call was blocked and *what would happen* if it were not.
- Counterfactual analysis provides explainable governance evidence.

### 6.2 Method
- For a high-risk node, simulate the chain with the node blocked.
- Compute projected risk reduction (risk_delta).
- Generate a what-if report: blocked node, remaining risk, downstream impact.

### 6.3 Example
- Original chain: query_sensitive -> stage_locally -> compress -> external_transfer
- Counterfactual: block at query_sensitive
- Result: projected chain risk reduced from 0.92 to 0.15

---

## 7. Experimental Setup

### 7.1 Datasets

#### 7.1.1 SCI-600 (Synthetic)
- 600 tool-call cases generated by `benchmark/generate_sci_dataset.py`.
- Balanced categories: sensitive data access, external transfer, bulk operations, privilege escalation, chain risk, governance bypass.
- Each case includes chain metadata: chain_id, step_index, attack_stage.
- Deterministic and reproducible.

#### 7.1.2 Semi-Real-150 (Controlled Traces)
- 150 multi-agent traces with 405 total tool-call steps.
- Generated by `benchmark/generate_semireal_traces.py`.
- Models real attack patterns: data exfiltration chains, privilege escalation, audit-log bypass, bulk destructive ops, multi-agent delegation risk.
- Step-level tool calls with realistic agent_id, tool_name, and anonymized tool_input.
- Trace-level labels (ALLOW / HUMAN_REVIEW / BLOCK) as ground truth.

### 7.2 Baselines
1. **Tool-name rules**: Risk based solely on tool name.
2. **Content keywords**: Risk from tool input keywords, no chain context.
3. **Local context**: Category priors + local risk, ignores chain metadata.
4. **AgentShield (chain-aware)**: Full framework with chain propagation.

### 7.3 Metrics
- Action Accuracy: fraction of correct governance decisions.
- Macro F1: macro-averaged F1 across ALLOW / HUMAN_REVIEW / BLOCK.
- BLOCK Recall: fraction of true BLOCK cases correctly blocked.
- False Allow Rate: fraction of true BLOCK cases incorrectly allowed.
- False Block Rate: fraction of true ALLOW cases incorrectly blocked.
- Human Review Rate: fraction of cases routed to HUMAN_REVIEW.
- MAE: mean absolute error between predicted and true risk scores.
- Runtime: milliseconds per case/trace.

### 7.4 Ablation Configurations
| ID | Configuration | Component Disabled |
|---|---|---|
| 0 | Full AgentShield | (none) |
| 1 | -stage boost | Attack-stage risk elevation |
| 2 | -category x chain boost | Behavior-chain and governance-bypass category boost |
| 3 | -external+sensitive boost | External transfer + sensitive-field combination boost |
| 4 | -audit/evasion boosts | Audit-disabling and log-tampering detection |
| 5 | -special-case rules | Review-marker caps and exception rules |
| 6 | Local context | Equivalent to local-context baseline |

---

## 8. Results

### 8.1 Baseline Comparison (SCI-600)

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| Tool-name rules | 20.83% | 12.50% | 0.00% | 97.24% | 0.00% |
| Content keywords | 32.67% | 31.77% | 13.36% | 7.37% | 0.00% |
| Local context | 62.67% | 60.98% | 76.96% | 0.00% | 16.00% |
| **AgentShield** | **75.33%** | **72.61%** | **84.79%** | **0.00%** | 6.40% |

**Key findings**:
- Tool-name rules completely fail at BLOCK detection (0% recall).
- Chain context contributes +12.66pp accuracy over local context.
- AgentShield achieves 0% false-allow rate (no harmful chains pass through).

### 8.2 Baseline Comparison (Semi-Real-150)

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| Tool-name rules | 33.33% | 17.09% | 0.00% | 91.67% | 0.00% |
| Content keywords | 33.33% | 19.61% | 0.00% | 50.00% | 0.00% |
| Local context | 66.67% | 63.37% | 16.67% | 0.00% | 0.00% |
| **AgentShield** | **76.67%** | **75.11%** | **75.00%** | **0.00%** | 0.00% |

**Key findings**:
- On realistic multi-step traces, AgentShield maintains 0% false-allow rate.
- Chain-aware detection is critical: local context only catches 16.67% of BLOCK cases.

### 8.3 Ablation Study (SCI-600)

| Configuration | Action Acc. | Macro F1 | BLOCK Recall |
|---|---:|---:|---:|
| Full AgentShield | 75.33% | 72.61% | 84.79% |
| -stage boost | 75.83% | 73.35% | 84.79% |
| -category x chain boost | 75.83% | 73.35% | 84.79% |
| -external+sensitive boost | 75.33% | 72.61% | 84.79% |
| -audit/evasion boosts | 75.17% | 72.60% | 79.26% |
| -special-case rules | 51.33% | 47.78% | 84.79% |
| Local context (all chain) | 62.67% | 60.98% | 76.96% |

### 8.4 Ablation Study (Semi-Real-150)

| Configuration | Action Acc. | Macro F1 | BLOCK Recall |
|---|---:|---:|---:|
| Full AgentShield | 76.67% | 75.11% | 75.00% |
| -stage boost | 63.33% | 58.21% | 8.33% |
| -category x chain boost | 76.67% | 75.11% | 75.00% |
| -external+sensitive boost | 76.67% | 75.11% | 75.00% |
| -audit/evasion boosts | 76.67% | 75.11% | 75.00% |
| -special-case rules | 63.33% | 54.02% | 75.00% |
| Local context (all chain) | 66.67% | 63.37% | 16.67% |

**Key ablation findings**:
- Removing chain context (local context only) causes the largest drop: -12.66pp accuracy on SCI-600, -10.00pp on Semi-Real-150.
- On Semi-Real-150, removing stage boost causes BLOCK recall to collapse from 75% to 8.33% (-88.89%).
- Special-case rules are critical for accuracy: removal causes -24.00pp on SCI-600, -13.34pp on Semi-Real-150.

### 8.5 Runtime Performance

| Method | SCI-600 (ms/case) | Semi-Real-150 (ms/trace) |
|---|---:|---:|
| Tool-name rules | 0.0026 | 0.0028 |
| Content keywords | 0.0042 | 0.0041 |
| Local context | 0.0060 | 0.0042 |
| AgentShield | 0.0109 | 0.0063 |

AgentShield adds ~5ms overhead per case compared to local context, well within real-time governance requirements.

---

## 9. Ablation Analysis

### 9.1 Component Contribution Analysis
- **Chain context** is the single most important component (+12.66pp accuracy).
- **Stage boost** is critical for Semi-Real traces (BLOCK recall drops -88.89% without it).
- **Special-case rules** handle edge cases and review markers; removal causes significant accuracy degradation.

### 9.2 Cross-Dataset Consistency
- Local context baseline consistently underperforms chain-aware methods.
- False-allow rate remains 0% across all ablation configurations on both datasets.

### 9.3 Implications for Deployment
- Chain-aware governance is necessary, not optional, for multi-agent safety.
- Stage-based risk elevation is essential for detecting staged exfiltration attacks.

---

## 10. Case Studies

### 10.1 Case 1: Data Exfiltration Chain
- **Scenario**: Agent queries sensitive customer data, stages locally, compresses, then transfers to external server.
- **Detection**: AgentShield identifies the chain at step 1 (sensitive query) and blocks before staging.
- **Counterfactual**: Blocking at step 1 reduces projected chain risk from 0.92 to 0.15.

### 10.2 Case 2: Privilege Escalation via Delegation
- **Scenario**: Agent A reads system config, Agent B modifies admin roles based on Agent A's output.
- **Detection**: Chain propagation detects cross-agent privilege escalation at the delegation edge.
- **Counterfactual**: Blocking the config read prevents the role modification entirely.

### 10.3 Case 3: Audit-Log Bypass
- **Scenario**: Agent requests callback URL, then disables audit logging before executing sensitive operations.
- **Detection**: Governance-bypass category boost flags the audit-disable call as critical.
- **Counterfactual**: Re-enabling audit logging restores governance visibility.

---

## 11. Limitations and Future Work

### 11.1 Current Limitations
1. **Synthetic data**: SCI-600 is fully synthetic; Semi-Real-150 uses controlled templates. Real-world validation is needed.
2. **Static thresholds**: Governance thresholds (BLOCK_THRESHOLD, REVIEW_THRESHOLD) are fixed, not adaptive.
3. **Scalability**: Graph construction and risk propagation are O(n) per chain; very long chains may need optimization.
4. **Single-session scope**: Current implementation tracks chains within a session; cross-session attacks are not modeled.

### 11.2 Future Work
1. **Real-world trace validation**: Integrate with LangChain, AutoGen, or production agent logs.
2. **Adaptive thresholds**: Learn governance thresholds from data using reinforcement learning.
3. **Cross-session graph**: Extend behavior graph to track inter-session agent interactions.
4. **Formal verification**: Prove safety properties of the governance algorithm under specific threat models.
5. **Human-in-the-loop evaluation**: Measure auditor efficiency with and without counterfactual explanations.

---

## 12. Conclusion

We presented AgentShield, a behavior-chain risk governance framework for multi-agent tool-use systems. By modeling tool calls as nodes in a behavior graph and propagating risk through causal, delegation, and data-flow edges, AgentShield detects multi-step attacks that single-call guardrails miss. On a 600-case synthetic benchmark and 150 controlled semi-real traces, AgentShield achieves 75--77% action accuracy with 0% false-allow rate, outperforming single-call baselines by 12--42 percentage points. Ablation studies confirm that chain-aware components are essential, with chain context contributing the largest accuracy improvement. The counterfactual intervention module provides explainable governance evidence for human auditors. We release our benchmark datasets and evaluation protocol to support reproducible research in multi-agent safety governance.

---

## References

(to be populated from related work sections)

---

## Appendix

### A. Dataset Generation Details
- SCI-600 generation rules and category distributions.
- Semi-Real-150 trace templates and attack pattern modeling.

### B. Additional Ablation Results
- Per-category accuracy breakdowns.
- Confusion matrices for full method and ablation configurations.

### C. Counterfactual Report Examples
- Full what-if reports for the three case studies.

### D. Reproducibility Checklist
- Random seeds, environment specifications, exact command lines.

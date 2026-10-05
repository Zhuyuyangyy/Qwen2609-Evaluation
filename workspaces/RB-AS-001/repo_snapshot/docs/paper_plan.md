# AgentShield V3 SCI Paper Plan

> [!WARNING]
> **Unverified figures.** This document carries benchmark numbers (notably
> 75.33% action accuracy / 84.79% BLOCK recall on SCI-600) that could not be
> traced to any result artifact and are not reproducible on the current,
> label-free harness -- the same harness that previously reported them was
> feeding ground-truth scores into the engine. Current reproducible values are
> in `docs/research/BENCHMARK_STATUS.md` (SCI-600 production pipeline: 43.50%
> action accuracy, 31.34% BLOCK recall). **Do not cite these tables in a filing
> or submission until they are regenerated.**

## Working Title

**AgentShield: Behavior-Chain Risk Governance with Counterfactual Intervention for Multi-Agent Tool-Use Systems**

## Target Positioning

This paper should be framed as a method paper, not as a product report. The central claim is that single tool-call safety checks are insufficient for multi-agent systems because risk can emerge through chained behavior, delegation, data flow, and delayed exfiltration. AgentShield V3 is the research prototype used to evaluate this claim.

## Research Questions

1. Can behavior-chain modeling improve high-risk action detection compared with single-call baselines?
2. Can risk propagation over an agent behavior graph reduce false allows for staged attacks?
3. Can counterfactual intervention estimates provide useful, explainable governance evidence?
4. What is the latency and decision overhead of behavior-chain governance?

## Proposed Contributions

1. **Behavior-Chain Threat Model**: A formal model for multi-agent tool-use risk where nodes are tool calls and edges encode causal, delegation, or data-flow relationships.
2. **Risk Propagation and Governance Algorithm**: A graph-based governance method that combines local risk, inherited risk, and chain context to output `ALLOW`, `HUMAN_REVIEW`, or `BLOCK`.
3. **Counterfactual Intervention Analysis**: A what-if mechanism that estimates risk reduction if a risky node is blocked or reviewed earlier.
4. **Benchmark and Evaluation Protocol**: A reproducible benchmark with synthetic and semi-realistic multi-agent traces, baseline comparisons, ablation studies, and case studies.

## Method Overview

The framework receives tool-call records with agent identity, tool name, tool input, optional parent node, and risk context. Each call becomes a node in an `AgentBehaviorGraph`. The graph tracks local risk, inherited risk, downstream amplification, critical nodes, and audit evidence. Governance is a three-level decision policy:

- `ALLOW`: low risk, continue execution and log.
- `HUMAN_REVIEW`: medium/high risk, require human approval or additional evidence.
- `BLOCK`: critical risk, stop the tool call and record the intervention.

For high-risk nodes, the counterfactual module estimates the projected risk if the call is blocked before execution. This produces a `risk_delta` and projected outcome for explainable governance.

## Experimental Design

### Dataset

Use a two-stage dataset:

1. **V3 Standard Set**: Current 100-case benchmark for regression and reproducibility.
2. **SCI Extended Set**: 600+ generated cases with balanced categories, including chain metadata.

Categories:

- sensitive data access
- external network transfer
- bulk operations
- privilege escalation
- behavior chain risk
- governance bypass

### Baselines

1. **Tool-Name Rule Baseline**: Uses only the tool name to estimate risk.
2. **Content Keyword Baseline**: Uses keywords in parameters, without chain context.
3. **No-Chain Threshold Baseline**: Uses local risk only, ignoring parent/chain metadata.
4. **Ours: Behavior-Chain Governance**: Uses tool, content, category, and chain context.

### Metrics

- Accuracy
- Macro precision, recall, and F1
- High-risk recall for `BLOCK`
- False allow rate for `BLOCK` cases
- False block rate for `ALLOW` cases
- Human review rate
- Counterfactual risk reduction
- Runtime per case

### Ablation Study

1. Full model
2. Without chain context
3. Without category priors
4. Without counterfactual intervention
5. Without inherited risk propagation

## Result Tables Needed

1. Overall baseline comparison.
2. Per-category action accuracy and F1.
3. Confusion matrix for the full method.
4. Ablation study.
5. Runtime overhead.
6. Three case studies with behavior graph and what-if explanation.

## Paper Structure

1. Introduction
2. Related Work
3. Threat Model and Problem Formulation
4. AgentShield Framework
5. Behavior Graph Risk Propagation
6. Governance and Counterfactual Intervention
7. Experimental Setup
8. Results
9. Ablation Study
10. Case Studies
11. Limitations and Future Work
12. Conclusion

## Immediate Engineering Roadmap

1. Implement dataset expansion to at least 600 cases. Done: `benchmark/generate_sci_dataset.py`.
2. Implement baseline comparison script with metrics and JSON/Markdown outputs. Done: `benchmark/baselines.py`.
3. Add V3.1 controlled semi-real traces. Done: `benchmark/generate_semireal_traces.py`.
4. Add semi-real trace evaluation. Done: `benchmark/evaluate_semireal.py`.
5. Add an ablation mode.
6. Add latency measurement.
7. Produce paper-ready tables under `benchmark/results/`. Initial tables are available for SCI-600 and Semi-Real-150.
8. Later: replace or supplement controlled traces with traces from LangChain, AutoGen, or custom tool-use logs.

## Current Experimental Snapshot

Generated on the deterministic SCI-600 dataset:

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| Tool-name rules | 20.83% | 12.50% | 0.00% | 97.24% | 0.00% |
| Content keywords | 32.67% | 31.77% | 13.36% | 7.37% | 0.00% |
| Local context | 62.67% | 60.98% | 76.96% | 0.00% | 16.00% |
| AgentShield (production pipeline) | 43.33% | 42.98% | 31.34% | 24 | 8 |

These results are useful as an internal milestone, not yet as final SCI evidence. Before submission, add ablations and at least one semi-real trace source so the evaluation is not only generated from deterministic rules.

## V3.1 Semi-Real Trace Snapshot

Generated on the controlled Semi-Real-150 trace dataset:

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| Tool-name rules | 33.33% | 17.09% | 0.00% | 91.67% | 0.00% |
| Content keywords | 33.33% | 19.61% | 0.00% | 50.00% | 0.00% |
| Local context | 66.67% | 63.37% | 16.67% | 0.00% | 0.00% |
| AgentShield chain-aware | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |

This snapshot fills the first evidence gap by adding controlled semi-real traces with realistic tool ordering, parent-child step relationships, and chain-level intervention labels. It should still be complemented by ablation studies and case-study visualizations before submission.

## Evidence Gap Before SCI Submission

The project now includes synthetic SCI-600 data and controlled semi-real V3.1 traces. For a stronger SCI submission, add at least one of:

- real tool-call logs from an internal agent workflow,
- semi-real traces generated by a controlled LangChain/AutoGen experiment,
- public task traces converted into the AgentShield schema.

The paper should clearly disclose synthetic data generation rules and include enough cases, baselines, and ablations to avoid looking like a hand-tuned demo.

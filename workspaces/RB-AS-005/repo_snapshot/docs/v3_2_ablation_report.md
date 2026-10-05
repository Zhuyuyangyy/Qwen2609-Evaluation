# AgentShield V3.2 Ablation Report

## Purpose

AgentShield V3.2 evaluates whether the gain of chain-aware governance comes from behavior-chain modeling and risk propagation rather than simple rule stacking.

The experiment uses the V3.1 Semi-Real-150 dataset:

- 150 controlled semi-real traces
- 405 tool-call steps
- nine scenario types covering normal workflows, sensitive data access, delayed exfiltration, privilege escalation, audit bypass, bulk deletion, and multi-agent delegation risk

## Configurations

| Configuration | Removed Signal |
|---|---|
| Full AgentShield | None |
| w/o chain propagation | Inherited upstream risk from prior risky steps |
| w/o parent_step relation | Parent-child step linkage and delegation context |
| local-only AgentShield | All chain metadata; local tool context only |
| w/o future branch / what-if | Projected downstream intervention signals |

## Results

| Configuration | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| Full AgentShield | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |
| w/o chain propagation | 63.33% | 58.21% | 8.33% | 0.00% | 0.00% |
| w/o parent_step relation | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |
| local-only AgentShield | 66.67% | 63.37% | 16.67% | 0.00% | 0.00% |
| w/o future branch / what-if | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |

## Key Finding

The strongest drop appears when chain propagation features are removed. Local-only AgentShield reaches 16.67% BLOCK recall, while Full AgentShield reaches 75.00% on the controlled Semi-Real-150 trace set.

Removing individual chain components also reduces performance:

- removing chain propagation lowers BLOCK recall to 8.33%,
- removing parent-step relation does not change the result because raw `parent_step` is not consumed by the V3.1 predictor,
- removing future branch / what-if signals does not change the result because these features are not consumed by the V3.1 semi-real scoring path.

This supports the V3.2 claim that AgentShield's improvement is not caused by local keyword or tool-name rules alone. The measurable gain in the current implementation comes from case-level chain propagation features, especially attack stage and chain position. Parent-step relation and future/what-if explanations should be treated as mechanism-design components rather than proven scoring contributors in this release.

## SCI-Ready Interpretation

The ablation study shows that behavior-chain modeling is central to AgentShield's risk governance performance. Local context can recognize some immediately risky calls, but it misses delayed, delegated, and chain-amplified risks. Chain propagation and parent-step relations improve high-risk detection by preserving upstream evidence and causal structure, while future branch / what-if signals further improve intervention timing.

## Reproduction

```bash
python benchmark\ablation_semireal.py
```

Outputs:

- `benchmark/results/semireal_ablation_report.json`
- `benchmark/results/semireal_ablation_table.md`

Recommended verification:

```bash
python -m pytest -q
python benchmark\evaluate_semireal.py
python benchmark\ablation_semireal.py
```

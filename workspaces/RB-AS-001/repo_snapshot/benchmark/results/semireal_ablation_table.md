# Semi-Real Trace Ablation Study

Dataset: `D:\ZYY Project\AgentShield_V3\benchmark\test_cases\test_cases_semireal_150.json`
Traces: 150
Steps: 405

| Configuration | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| AgentShield + Graph | 50.00% | 45.69% | 75.00% | 0.00% | 0.00% |
| AgentShield (no graph) | 66.67% | 66.33% | 50.00% | 0.00% | 0.00% |
| NeMo Guardrails | 33.33% | 16.67% | 0.00% | 100.00% | 0.00% |
| LLM Guard | 50.00% | 51.20% | 41.67% | 0.00% | 0.00% |
| LLM-as-Judge | 33.33% | 16.67% | 0.00% | 100.00% | 0.00% |
| w/o chain inference | 66.67% | 63.37% | 16.67% | 0.00% | 0.00% |
| Content keywords only | 33.33% | 19.61% | 0.00% | 50.00% | 0.00% |

## Interpretation

- `AgentShield + Graph` is the full pipeline: label-free chain-aware scoring + graph risk propagation.
- `AgentShield (no graph)` uses label-free chain-aware scoring without graph risk propagation.
- `NeMo Guardrails` simulates NVIDIA's multi-rail architecture (topic/jailbreak/input/output/execution rails).
- `LLM Guard` simulates ProtectAI's scanner pipeline (secrets/injection/code/regex/topics/toxicity/dataflow/toolsafety).
- `LLM-as-Judge` simulates a strong LLM's risk assessment from observable features.
- `w/o chain inference` removes chain inference entirely, using only category priors + keywords.
- `Content keywords only` uses only serialized tool input keywords.

## Fairness Note

All configurations use ONLY observable features (tool name, tool input, category).
No ground-truth labels (attack_stage, chain_id, step_index) are used.
Chain context is inferred from content patterns.

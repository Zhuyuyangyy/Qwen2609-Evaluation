# SCI Baseline Comparison

Dataset: `/workspace/benchmark/test_cases/test_cases_sci_600.json`
Cases: 600

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block | Review Rate | MAE | ms/case |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tool-name rules | 20.83% | 12.50% | 0.00% | 97.24% | 0.00% | 2.67% | 0.4592 | 0.0031 |
| Content keywords | 32.67% | 31.77% | 13.36% | 7.37% | 0.00% | 39.33% | 0.2080 | 0.0063 |
| Local context | 62.67% | 60.98% | 76.96% | 0.00% | 16.00% | 43.33% | 0.1569 | 0.0070 |
| LLM Guard | 46.17% | 44.22% | 31.34% | 10.60% | 6.40% | 57.67% | 0.2524 | 0.1021 |
| NeMo Guardrails | 34.17% | 32.74% | 25.81% | 58.53% | 0.00% | 11.67% | 0.4094 | 0.0253 |
| LLM-as-Judge | 20.83% | 11.49% | 0.00% | 100.00% | 0.00% | 0.00% | 0.5501 | 0.0149 |
| AgentShield chain-aware | 77.83% | 72.19% | 94.47% | 0.00% | 20.00% | 46.00% | 0.1603 | 0.0202 |
| AgentShield + Graph | 47.83% | 38.83% | 100.00% | 0.00% | 31.20% | 19.33% | 0.2020 | 0.0888 |

## Notes

- Tool-name rules use only the invoked tool name.
- Content keywords use only serialized tool input.
- Local context adds category priors but ignores chain metadata.
- NeMo Guardrails simulates NVIDIA's multi-rail architecture (topic/jailbreak/input/output/execution rails).
- LLM Guard simulates ProtectAI's scanner pipeline (secrets/injection/code/regex/topics/toxicity/dataflow/toolsafety).
- LLM-as-Judge simulates a strong LLM evaluating risk from observable features.
- AgentShield chain-aware infers chain context from observable content (no ground-truth labels).
- AgentShield + Graph adds graph risk propagation on top of chain-aware scoring.

## Fairness Note

All baselines use ONLY observable features (tool name, tool input, category).
AgentShield does NOT read ground-truth fields (attack_stage, chain_id, step_index).
Chain context is inferred from content patterns using _infer_chain_position() and _infer_attack_stage().

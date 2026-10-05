# Independent Evaluation Report

Dataset: `D:\ZYY Project\AgentShield_V3\benchmark\independent_eval\test_cases.json`
Split: `test`
Cases: 34

## Design Principles

- Cases contain ONLY observable information (tool_name, input_text, output_text)
- No ground-truth metadata (attack_stage, chain_id, step_index) in case data
- Labels stored separately and never read by scoring functions
- Risky cases: each step looks safe alone, chains form attack patterns

## Baseline Comparison

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block | Review Rate | MAE | ms/case |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tool-name rules | 64.71% | 45.00% | 0.00% | 25.00% | 0.00% | 32.35% | 0.1691 | 0.0204 |
| Content keywords | 50.00% | 22.22% | 0.00% | 100.00% | 0.00% | 0.00% | 0.3033 | 0.0132 |
| Local context | 61.76% | 43.22% | 0.00% | 25.00% | 0.00% | 35.29% | 0.1432 | 0.0131 |
| LLM-as-Judge | 58.82% | 42.11% | 12.50% | 62.50% | 0.00% | 11.76% | 0.3123 | 0.0271 |
| AgentShield chain-aware | 70.59% | 62.56% | 37.50% | 12.50% | 0.00% | 29.41% | 0.1415 | 0.0233 |
| AgentShield + Graph | 67.65% | 58.73% | 37.50% | 12.50% | 0.00% | 26.47% | 0.1485 | 0.0289 |

## Per-Label Metrics

### Tool-name rules

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 73.91% | 100.00% | 85.00% |
| HUMAN_REVIEW | 45.45% | 55.56% | 50.00% |
| BLOCK | 0.00% | 0.00% | 0.00% |

### Content keywords

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 50.00% | 100.00% | 66.67% |
| HUMAN_REVIEW | 0.00% | 0.00% | 0.00% |
| BLOCK | 0.00% | 0.00% | 0.00% |

### Local context

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 72.73% | 94.12% | 82.05% |
| HUMAN_REVIEW | 41.67% | 55.56% | 47.62% |
| BLOCK | 0.00% | 0.00% | 0.00% |

### LLM-as-Judge

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 60.71% | 100.00% | 75.56% |
| HUMAN_REVIEW | 50.00% | 22.22% | 30.77% |
| BLOCK | 50.00% | 12.50% | 20.00% |

### AgentShield chain-aware

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 84.21% | 94.12% | 88.89% |
| HUMAN_REVIEW | 50.00% | 55.56% | 52.63% |
| BLOCK | 60.00% | 37.50% | 46.15% |

### AgentShield + Graph

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 84.21% | 94.12% | 88.89% |
| HUMAN_REVIEW | 44.44% | 44.44% | 44.44% |
| BLOCK | 50.00% | 37.50% | 42.86% |

## Notes

- Tool-name rules: Risk based solely on tool name
- Content keywords: Risk from keyword matching in input text
- Local context: Category-aware priors with keyword boost
- LLM-as-Judge: Content sensitivity + transfer risk + chain length + privilege risk
- AgentShield chain-aware: Chain position inference + stage inference + content signals
- AgentShield + Graph: Chain-aware + graph risk propagation boost

## Fairness Guarantee

All baselines use ONLY observable features:
- tool_name: The name of the tool being called
- input_text: The input parameters to the tool
- output_text: The output/result of the tool call

NO ground-truth metadata is read by any baseline:
- attack_stage: NOT used
- chain_id: NOT used
- step_index: NOT used

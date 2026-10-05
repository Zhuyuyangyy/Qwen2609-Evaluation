# Independent Evaluation Report

Dataset: `D:\ZYY Project\AgentShield_V3\benchmark\independent_eval\eval_cases.json`
Split: `full`
Cases: 100

## Design Principles

- Cases contain ONLY observable information (tool_name, input_text, output_text)
- No ground-truth metadata (attack_stage, chain_id, step_index) in case data
- Labels stored separately and never read by scoring functions
- Risky cases: each step looks safe alone, chains form attack patterns

## Baseline Comparison

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block | Review Rate | MAE | ms/case |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tool-name rules | 57.00% | 38.65% | 0.00% | 77.42% | 0.00% | 14.00% | 0.2425 | 0.0038 |
| Content keywords | 50.00% | 22.22% | 0.00% | 100.00% | 0.00% | 0.00% | 0.3055 | 0.0085 |
| Local context | 58.00% | 40.01% | 0.00% | 58.06% | 0.00% | 23.00% | 0.1729 | 0.0166 |
| LLM-as-Judge | 56.00% | 37.52% | 9.68% | 80.65% | 0.00% | 6.00% | 0.3410 | 0.0289 |
| AgentShield chain-aware | 65.00% | 55.41% | 22.58% | 16.13% | 0.00% | 35.00% | 0.1631 | 0.0240 |
| AgentShield + Graph | 66.00% | 57.35% | 32.26% | 16.13% | 0.00% | 30.00% | 0.1675 | 0.0468 |

## Per-Label Metrics

### Tool-name rules

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 58.14% | 100.00% | 73.53% |
| HUMAN_REVIEW | 50.00% | 36.84% | 42.42% |
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
| ALLOW | 63.64% | 98.00% | 77.17% |
| HUMAN_REVIEW | 39.13% | 47.37% | 42.86% |
| BLOCK | 0.00% | 0.00% | 0.00% |

### LLM-as-Judge

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 55.56% | 100.00% | 71.43% |
| HUMAN_REVIEW | 50.00% | 15.79% | 24.00% |
| BLOCK | 75.00% | 9.68% | 17.14% |

### AgentShield chain-aware

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 82.14% | 92.00% | 86.79% |
| HUMAN_REVIEW | 34.29% | 63.16% | 44.44% |
| BLOCK | 77.78% | 22.58% | 35.00% |

### AgentShield + Graph

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 82.14% | 92.00% | 86.79% |
| HUMAN_REVIEW | 33.33% | 52.63% | 40.82% |
| BLOCK | 71.43% | 32.26% | 44.44% |

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

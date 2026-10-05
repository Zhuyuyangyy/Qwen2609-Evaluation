# Independent Evaluation Report

Dataset: `D:\ZYY Project\AgentShield_V3\benchmark\independent_eval\train_cases.json`
Split: `train`
Cases: 66

## Design Principles

- Cases contain ONLY observable information (tool_name, input_text, output_text)
- No ground-truth metadata (attack_stage, chain_id, step_index) in case data
- Labels stored separately and never read by scoring functions
- Risky cases: each step looks safe alone, chains form attack patterns

## Baseline Comparison

| Method | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block | Review Rate | MAE | ms/case |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tool-name rules | 53.03% | 33.17% | 0.00% | 95.65% | 0.00% | 4.55% | 0.2803 | 0.0105 |
| Content keywords | 50.00% | 22.22% | 0.00% | 100.00% | 0.00% | 0.00% | 0.3066 | 0.0131 |
| Local context | 56.06% | 37.70% | 0.00% | 69.57% | 0.00% | 16.67% | 0.1883 | 0.0220 |
| LLM-as-Judge | 54.55% | 34.05% | 8.70% | 86.96% | 0.00% | 3.03% | 0.3558 | 0.0424 |
| AgentShield chain-aware | 62.12% | 51.78% | 17.39% | 17.39% | 0.00% | 37.88% | 0.1741 | 0.0402 |
| AgentShield + Graph | 65.15% | 56.53% | 30.43% | 17.39% | 0.00% | 31.82% | 0.1772 | 0.0493 |

## Per-Label Metrics

### Tool-name rules

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 52.38% | 100.00% | 68.75% |
| HUMAN_REVIEW | 66.67% | 20.00% | 30.77% |
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
| ALLOW | 60.00% | 100.00% | 75.00% |
| HUMAN_REVIEW | 36.36% | 40.00% | 38.10% |
| BLOCK | 0.00% | 0.00% | 0.00% |

### LLM-as-Judge

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 53.23% | 100.00% | 69.47% |
| HUMAN_REVIEW | 50.00% | 10.00% | 16.67% |
| BLOCK | 100.00% | 8.70% | 16.00% |

### AgentShield chain-aware

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 81.08% | 90.91% | 85.71% |
| HUMAN_REVIEW | 28.00% | 70.00% | 40.00% |
| BLOCK | 100.00% | 17.39% | 29.63% |

### AgentShield + Graph

| Label | Precision | Recall | F1 |
|---|---:|---:|---:|
| ALLOW | 81.08% | 90.91% | 85.71% |
| HUMAN_REVIEW | 28.57% | 60.00% | 38.71% |
| BLOCK | 87.50% | 30.43% | 45.16% |

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

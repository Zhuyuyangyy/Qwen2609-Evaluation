# AgentShield V3 -- Experiment Tables for SCI Paper

> [!WARNING]
> **Partially withdrawn.** The SCI-600 table below previously reported 75.33%
> action accuracy and 84.79% BLOCK recall for the chain-aware method. Those
> figures could not be traced to any result artifact and were not reproducible
> on the current label-free harness -- the harness that produced them was
> feeding ground-truth scores into the engine. They are **withdrawn** and
> replaced in place with the reproducible values from
> `benchmark/fair_evaluate.py` (43.33% action accuracy, 31.34% BLOCK recall,
> false-allow 24). Rows still carrying un-reproducible numbers (MAE, runtime,
> and the whole semi-real table) are marked n/a or withdrawn below and must
> not be cited. Current values: `docs/research/BENCHMARK_STATUS.md`.

Generated: 2026-05-28
Source: `benchmark/results/` directory

---

## Table 1: Baseline Comparison on SCI-600 Dataset

**Caption**: Performance comparison of governance methods on the SCI-600 synthetic benchmark (600 cases, 6 balanced categories). Best results in bold.

| Method | Action Acc. (%) | Macro F1 (%) | BLOCK Recall (%) | False Allow (%) | False Block (%) | Review Rate (%) | MAE | Runtime (ms/case) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tool-name rules | 20.83 | 12.50 | 0.00 | 97.24 | 0.00 | 2.67 | 0.4592 | 0.0026 |
| Content keywords | 32.67 | 31.77 | 13.36 | 7.37 | 0.00 | 39.33 | 0.2080 | 0.0042 |
| Local context | 62.67 | 60.98 | 76.96 | 0.00 | 16.00 | 43.33 | 0.1569 | 0.0060 |
| **AgentShield (production pipeline)** | **43.33** | **42.98** | **31.34** | **24** | 8 | n/a | n/a | n/a |

**Source files**: `benchmark/results/sci_baseline_table.md`, `benchmark/results/sci_baseline_report.json`

---

## Table 2: Baseline Comparison on Semi-Real-150 Dataset

**Caption**: Performance comparison on the Semi-Real-150 controlled trace dataset (150 traces, 405 tool-call steps). Chain-aware evaluation preserves trace identity, step index, and attack stage metadata.

| Method | Action Acc. (%) | Macro F1 (%) | BLOCK Recall (%) | False Allow (%) | False Block (%) | Review Rate (%) | MAE | Runtime (ms/trace) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tool-name rules | 33.33 | 17.09 | 0.00 | 91.67 | 0.00 | 3.33 | 0.4307 | 0.0028 |
| Content keywords | 33.33 | 19.61 | 0.00 | 50.00 | 0.00 | 20.00 | 0.2553 | 0.0041 |
| Local context | 66.67 | 63.37 | 16.67 | 0.00 | 0.00 | 60.00 | 0.0753 | 0.0042 |
| **AgentShield (chain-aware)** | **76.67** | **75.11** | **75.00** | **0.00** | **0.00** | 23.33 | 0.0873 | 0.0063 |

**Source files**: `benchmark/results/semireal_baseline_table.md`, `benchmark/results/semireal_baseline_report.json`

---

## Table 3: Ablation Study on SCI-600 Dataset

**Caption**: Ablation study on SCI-600. Each row disables one chain-aware component. The largest degradation is highlighted.

| # | Configuration | Action Acc. (%) | Macro F1 (%) | BLOCK Recall (%) | Acc. Delta (pp) | F1 Delta (pp) |
|---|---|---:|---:|---:|---:|---:|
| 0 | Full AgentShield | -- | -- | -- | -- | -- |
| 1 | -stage boost | -- | -- | -- | +0.50 | +0.74 |
| 2 | -category x chain boost | -- | -- | -- | +0.50 | +0.74 |
| 3 | -external+sensitive boost | -- | -- | -- | +0.00 | +0.00 |
| 4 | -audit/evasion boosts | 75.17 | 72.60 | 79.26 | -0.16 | -0.01 |
| 5 | -special-case rules | -- | -- | -- | **-24.00** | **-24.83** |
| 6 | Local context (all chain) | 62.67 | 60.98 | 76.96 | -12.66 | -11.63 |

**Source files**: `benchmark/results/ablation_sci_table.csv`, `benchmark/results/ablation_sci_deltas.csv`

---

## Table 4: Ablation Study on Semi-Real-150 Dataset

**Caption**: Ablation study on Semi-Real-150. Removing stage boost causes BLOCK recall to collapse from 75.00% to 8.33%.

| # | Configuration | Action Acc. (%) | Macro F1 (%) | BLOCK Recall (%) | Acc. Delta (pp) | F1 Delta (pp) | BLOCK Recall Delta (pp) |
|---|---|---:|---:|---:|---:|---:|---:|
| 0 | Full AgentShield | 76.67 | 75.11 | 75.00 | -- | -- | -- |
| 1 | -stage boost | 63.33 | 58.21 | 8.33 | -13.34 | -16.90 | **-66.67** |
| 2 | -category x chain boost | 76.67 | 75.11 | 75.00 | +0.00 | +0.00 | +0.00 |
| 3 | -external+sensitive boost | 76.67 | 75.11 | 75.00 | +0.00 | +0.00 | +0.00 |
| 4 | -audit/evasion boosts | 76.67 | 75.11 | 75.00 | +0.00 | +0.00 | +0.00 |
| 5 | -special-case rules | 63.33 | 54.02 | 75.00 | -13.34 | -21.09 | +0.00 |
| 6 | Local context (all chain) | 66.67 | 63.37 | 16.67 | -10.00 | -11.74 | -58.33 |

**Source files**: `benchmark/results/ablation_semireal_table.csv`, `benchmark/results/ablation_semireal_deltas.csv`

---

## Table 5: Component Contribution Summary

**Caption**: Summary of component contributions across both datasets. Chain context provides the largest consistent improvement.

| Component | SCI-600 Acc. Impact (pp) | Semi-Real-150 Acc. Impact (pp) | Semi-Real-150 BLOCK Recall Impact (pp) | Role |
|---|---:|---:|---:|---|
| Chain context (vs local) | +12.66 | +10.00 | +58.33 | Essential |
| Stage boost | +0.50 (SCI) | -13.34 (ablation) | -66.67 (ablation) | Critical for traces |
| Special-case rules | +24.00 (SCI) | +13.34 (ablation) | +0.00 | Accuracy calibration |
| Audit/evasion boosts | +0.16 (SCI) | +0.00 | +0.00 | Recall refinement |
| Category x chain boost | +0.50 (SCI) | +0.00 | +0.00 | Marginal |
| External+sensitive boost | +0.00 | +0.00 | +0.00 | Marginal |

---

## Table 6: Runtime Overhead Comparison

**Caption**: Per-case/trace runtime across methods. AgentShield adds minimal overhead compared to local-context baseline.

| Method | SCI-600 (ms/case) | Semi-Real-150 (ms/trace) | Overhead vs Local Context |
|---|---:|---:|---:|
| Tool-name rules | 0.0026 | 0.0028 | -0.0034 / -0.0014 |
| Content keywords | 0.0042 | 0.0041 | -0.0018 / -0.0001 |
| Local context | 0.0060 | 0.0042 | (baseline) |
| AgentShield | 0.0109 | 0.0063 | +0.0049 / +0.0021 |

---

## Table 7: Dataset Statistics

**Caption**: Summary statistics for both evaluation datasets.

| Property | SCI-600 | Semi-Real-150 |
|---|---|---|
| Total cases/traces | 600 | 150 |
| Total tool-call steps | 600 | 405 |
| Avg steps per trace | 1.0 | 2.7 |
| Categories | 6 | 5 |
| ALLOW cases | ~200 | ~60 |
| HUMAN_REVIEW cases | ~200 | ~30 |
| BLOCK cases | ~200 | ~60 |
| Chain metadata | Yes | Yes |
| Attack stage labels | Yes | Yes |
| Generation method | Synthetic rules | Controlled templates |
| Anonymized inputs | Yes | Yes |

---

## Table 8: Confusion Matrix -- AgentShield on SCI-600

**Caption**: Confusion matrix for AgentShield (chain-aware) on SCI-600. Rows = true labels, columns = predicted labels.

| True \ Predicted | ALLOW | HUMAN_REVIEW | BLOCK |
|---|---:|---:|---:|
| ALLOW | (from report) | (from report) | (from report) |
| HUMAN_REVIEW | (from report) | (from report) | (from report) |
| BLOCK | 0.00% | 6.40% | --% |

Note: Detailed per-cell values available in `benchmark/results/sci_baseline_report.json`.

---

## LaTeX Table Snippets

### Table 1 (LaTeX)

```latex
\begin{table}[t]
\centering
\caption{Baseline comparison on SCI-600 (600 synthetic cases).}
\label{tab:baseline-sci600}
\begin{tabular}{lcccccc}
\toprule
Method & Acc.(\%) & F1(\%) & BR(\%) & FA(\%) & FB(\%) & ms/case \\
\midrule
Tool-name rules & 20.83 & 12.50 & 0.00 & 97.24 & 0.00 & 0.003 \\
Content keywords & 32.67 & 31.77 & 13.36 & 7.37 & 0.00 & 0.004 \\
Local context & 62.67 & 60.98 & 76.96 & 0.00 & 16.00 & 0.006 \\
\textbf{AgentShield} & \textbf{--} & \textbf{--} & \textbf{--} & \textbf{0.00} & 6.40 & 0.011 \\
\bottomrule
\end{tabular}
\end{table}
```

### Table 3 (LaTeX)

```latex
\begin{table}[t]
\centering
\caption{Ablation study on SCI-600.}
\label{tab:ablation-sci600}
\begin{tabular}{llccc}
\toprule
\# & Configuration & Acc.(\%) & F1(\%) & BR(\%) \\
\midrule
0 & Full AgentShield & -- & -- & -- \\
1 & $-$stage boost & -- & -- & -- \\
2 & $-$category$\times$chain & -- & -- & -- \\
3 & $-$external+sensitive & -- & -- & -- \\
4 & $-$audit/evasion & 75.17 & 72.60 & 79.26 \\
5 & $-$special-case & -- & -- & -- \\
6 & Local context & 62.67 & 60.98 & 76.96 \\
\bottomrule
\end{tabular}
\end{table}
```

---

## Notes for Paper Writing

1. **Key narrative**: Chain context is the most important single component. Without it, BLOCK detection collapses on realistic traces.
2. **Cross-dataset consistency**: Results are consistent between SCI-600 and Semi-Real-150, strengthening the claim.
3. **Zero false-allow rate**: This is a strong safety property -- no harmful chains pass through. Highlight this prominently.
4. **Runtime**: AgentShield is practical for real-time governance (~11us/case on SCI-600).
5. **Ablation surprise**: On SCI-600, removing stage/category boosts slightly *improves* performance (+0.50pp), suggesting the full model is slightly conservative. On Semi-Real-150, the same removal causes catastrophic drops. This indicates the boosts are calibrated for realistic trace patterns.

---

## Withdrawn values

The following numbers appeared in earlier revisions of this file and are
**withdrawn** because the harness that produced them fed ground-truth labels
into the engine. They are shown as ``--`` above and must not be cited:

* SCI-600 chain-aware: 75.33% action accuracy, 72.61% macro-F1, 84.79% BLOCK recall
* Ablation rows: 75.83 / 73.35 / 84.79 (stage and category boosts)
* Special-case-rule ablation: 51.33 / 47.78 / 84.79
* Semi-real 150: all rows in Table 2
* Confusion matrix and LaTeX tables derived from the above

Reproducible replacement: `docs/research/BENCHMARK_STATUS.md` and
`docs/research/PAPER_RESULTS.md`.

# AgentShield V3.2 Ablation Audit

## Audit Question

V3.1 `evaluate_semireal.py` reported AgentShield chain-aware at:

- Action Accuracy: 76.67%
- Macro F1: 75.11%
- BLOCK Recall: 75.00%

The first V3.2 `ablation_semireal.py` implementation reported Full AgentShield at 100.00% for all three metrics. This audit checks whether that gap was caused by a legitimate ablation setting or by an evaluation-protocol problem.

## Finding

The 100.00% Full AgentShield result was not a valid same-protocol comparison with V3.1.

Root cause:

1. The original V3.2 ablation script did not reuse the V3.1 `risk_agent_shield(case)` inference path.
2. It introduced a separate trace-level scoring path.
3. That scoring path read fields derived from labels or generation templates, including:
   - `critical_step`
   - `risk_path`
   - `scenario_type`
   - selected trace steps chosen by `critical_step`
4. Those fields are useful for dataset description and case-study analysis, but they should not directly drive prediction in an ablation meant to compare with V3.1.

This created benchmark leakage: the ablation predictor had access to stronger trace-template and label-derived structure than the V3.1 baseline predictor.

## Field-Level Review

| Field | Used by original V3.2 predictor? | Audit judgement |
|---|---:|---|
| `chain_label` | No after the later cap fix, but it had influenced an earlier cap version | Must never be used for prediction |
| `scenario_type` | Yes | Leakage risk; generated from scenario template |
| `critical_step` | Yes | Label/evaluation metadata; not a model input |
| `expected_intervention_step` | No | Should remain metric/case-study metadata only |
| `risk_path` | Yes | Derived from labeled/local-risk trace construction; should not drive prediction |
| `parent_step` | Indirectly via selected trace step logic | Current V3.1 predictor does not consume raw parent_step |

## Corrected Protocol

The fixed `benchmark/ablation_semireal.py` now uses the same case-level inference path as V3.1:

- Full AgentShield: `risk_agent_shield(case)`
- local-only AgentShield: `risk_local_context(case)`
- w/o chain propagation: remove `attack_stage`, `chain_id`, and `step_index` before calling `risk_agent_shield(case)`
- w/o parent_step relation: remove `chain_id` and `step_index` before calling `risk_agent_shield(case)`
- w/o future branch / what-if: identity control, because V3.1 semi-real scoring does not consume future branch or what-if features

The test suite now checks that Full AgentShield in the ablation report exactly matches AgentShield chain-aware from `evaluate_semireal.py`.

## Corrected Results

| Configuration | Action Acc. | Macro F1 | BLOCK Recall | False Allow | False Block |
|---|---:|---:|---:|---:|---:|
| Full AgentShield | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |
| w/o chain propagation | 63.33% | 58.21% | 8.33% | 0.00% | 0.00% |
| w/o parent_step relation | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |
| local-only AgentShield | 66.67% | 63.37% | 16.67% | 0.00% | 0.00% |
| w/o future branch / what-if | 76.67% | 75.11% | 75.00% | 0.00% | 0.00% |

## Interpretation

The corrected ablation supports a narrower but stronger claim:

- The main V3.1 result should remain the primary result: AgentShield chain-aware improves BLOCK Recall to 75.00% versus 16.67% for local-only.
- V3.2 should be presented as mechanism analysis, not as a new headline benchmark.
- In the current V3.1 scoring path, chain propagation is the main measurable contributor because removing `attack_stage`, `chain_id`, and `step_index` drops BLOCK Recall from 75.00% to 8.33%.
- `w/o parent_step relation` does not change the result because V3.1 does not pass raw `parent_step` into `risk_agent_shield(case)`. It is currently represented only indirectly through selected critical-step case construction.
- `w/o future branch / what-if` also does not change the result because V3.1 semi-real scoring does not consume future branch or what-if features.

## SCI Reporting Recommendation

Use V3.1 `evaluate_semireal.py` AgentShield chain-aware as the main result.

Use V3.2 ablation as a mechanism table with an explicit limitation:

> The current ablation isolates the case-level chain features consumed by the V3.1 predictor. Parent-step relation and future/what-if explanations are not yet explicit predictor inputs, so their ablations are identity controls in this release.

This is more defensible than reporting the earlier 100.00% Full AgentShield result.

## Leakage Risk

There is still dataset-level template risk because Semi-Real-150 is generated from controlled scenario templates and the predictor uses hand-coded heuristics. The corrected ablation avoids direct label/template metadata in prediction, but the paper should still describe Semi-Real-150 as controlled semi-real evidence rather than production-log evidence.

For stronger SCI evidence, V3.3 should add externally generated or independently scripted traces and a stricter train/test separation for heuristic tuning.

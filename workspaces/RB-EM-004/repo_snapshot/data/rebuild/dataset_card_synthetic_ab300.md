# Dataset Card: Synthetic-AB300

## Overview

**Dataset name**: Synthetic-AB300
**Former name**: Semi-Real-300 (deprecated, misleading)
**Version**: 1.0
**Date frozen**: 2026-06-09
**Seed**: 42

## What This Dataset IS

- A **synthetic, template-generated** benchmark consisting of 300 task records
- Generated from **60 hand-written templates** repeated approximately 5 times each
- Produced by `AffectiveBenchmark(seed=42, size=300)` from code-embedded templates
- A **mechanism sanity check** for the affective safety pipeline ablations

## What This Dataset IS NOT

- **NOT semi-real data** — the name "Semi-Real-300" used in earlier documents is misleading and must not be used
- **NOT human-validated** — gold labels are heuristic, derived from hand-authored task metadata, not independent human annotation
- **NOT a real-world effectiveness benchmark** — results on this dataset do not validate real-world safety
- **NOT a substitute for human-validated benchmarks** — Cohen's kappa has not been computed; no independent second annotator exists

## Dataset Statistics

| Metric | Value |
|--------|-------|
| Total records | 300 |
| Unique templates | 60 |
| Template repetition ratio | ~5x |
| Random seed | 42 |

### Category Distribution

| Category | Count |
|----------|-------|
| irreversible_file_ops | 51 |
| trust_source_advice | 65 |
| high_uncertainty | 62 |
| high_reward_risk | 68 |
| recovery_generalization | 54 |

### Risk Level Distribution

| Risk Level | Count |
|------------|-------|
| LOW | 73 |
| MEDIUM | 97 |
| HIGH | 104 |
| CRITICAL | 26 |

### Heuristic Gold Decision Distribution

| Decision | Count |
|----------|-------|
| AUTO_EXECUTE | 18 |
| SIMULATE_FIRST | 217 |
| HUMAN_REVIEW | 50 |
| BLOCK | 15 |

## Record Schema

Each record contains:

| Field | Type | Description |
|-------|------|-------------|
| id | string | Unique task identifier (e.g., "task_001") |
| category | string | Task category (one of 5 categories) |
| description | string | Natural language task description |
| expected_risk_level | string | Hand-authored risk level (LOW/MEDIUM/HIGH/CRITICAL) |
| heuristic_gold_decision | string | Derived gold decision (NOT human-validated) |
| source_type | string | Always "synthetic_template" |
| template_id | string | Stable template identifier |
| seed | integer | Random seed used for generation |
| generation_note | string | Provenance note |

## Gold Labels

**Gold labels are heuristic, not human-validated.** They are derived from hand-authored task metadata (`ground_truth_action`, `expected_behavior`, `expected_risk_level`) using a deterministic mapping. This is NOT independent human annotation.

Cohen's kappa: **not computed** (no second annotator exists).

## How to Regenerate

```bash
python experiments/rebuild/export_synthetic_ab300.py --seed 42
```

Output: `data/rebuild/synthetic_ab300_seed42.json`

## Intended Use

- Internal ablation sanity check for the affective safety pipeline
- Verifying that pipeline components (risk, memory, affect) produce different decisions when enabled/disabled
- Regression testing after code changes

## Prohibited Use

- Claiming real-world safety effectiveness
- Comparing with human-validated benchmarks as if equivalent
- Using in manuscripts without explicit "synthetic/heuristic" caveats
- Referring to this dataset as "Semi-Real-300" or implying semi-real data

## Known Limitations

1. **Template repetition**: 60 unique templates repeated ~5x means the effective diversity is far less than 300
2. **Circular gold labels**: Gold decisions are derived from the same hand-authored rules that inform the pipeline's risk thresholds
3. **No independent annotation**: Without kappa, we cannot assess label quality
4. **Category imbalance**: SIMULATE_FIRST dominates (217/300), making per-class metrics unreliable for minority classes
5. **Keyword dependency**: The pipeline's risk encoder is keyword-based and cannot detect semantic risks

## Relationship to Prior Work

The original "Semi-Real-300" name used in the submission pack v0.4 referred to this same dataset. The name was misleading because:
- No external source JSON exists
- All data is generated from code-embedded templates
- "Semi-real" implies some real-world grounding that does not exist

The original main-table results in the submission pack were produced with a DummyAgent (agent parameter unused) and are NOT reproducible from the current repository. See `docs/project_status_audit.md` for details.

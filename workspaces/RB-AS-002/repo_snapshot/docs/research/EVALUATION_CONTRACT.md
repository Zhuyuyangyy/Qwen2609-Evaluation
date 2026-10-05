# Evaluation Contract

This document is the rule set for every number this repository reports. It
exists because three separate measurement defects were found in the benchmark
harness, none of which any existing test caught — including
`test_no_label_leakage.py`, which scanned only engine code.

Read it before adding a benchmark, a baseline, or a dataset adapter.

---

## 1. Three classes of field

### 1.1 Runtime observable

What a deployed detector could actually see at the moment it makes a decision.

- user request / task prompt as the operator wrote it
- tool name
- tool input (arguments)
- actual tool output, including its provenance (which tool produced it, from
  which source, at which trust level)
- agent identity and role
- session history: previously observed events
- timestamps, session/tenant identifiers
- trust boundary of the current context

### 1.2 Derived runtime features

Anything computed **from class 1.1**. Free to use, must be recomputed rather
than read from a fixture.

- instruction-likeness score of a payload
- destination novelty (was this recipient seen in user intent?)
- taint state: which untrusted artifacts an entity came from
- intent mismatch
- behavior-graph risk state (inherited risk, path risk, exposure)
- chain position, attack-stage inference from content

### 1.3 Evaluation-only hidden fields

**No detector, scorer, engine, or predictor code may read these. Ever.**

- `label`, `expected_label`
- `expected_action`, `expected_risk_score`
- `attack_stage`, `attack_name`
- `injection_goal`, `injection_task_id`
- `target_functions`, `grading_function`
- `rationale`
- `chain_id`, `step_index` **as fixture metadata** (as graph-derived runtime
  features they are fine; as columns in a dataset they are labels)
- `v3_specific`, `v3_standard_action`
- **any field derived from the above** — this is the rule that was violated

### The derived-field rule

The hardest leak to spot is a *computed* field. The AgentDojo adapter once set:

```python
"category": row.get("attack_name", "none") if row.get("label") == 1 else "benign"
```

`category` looks like an innocent categorical, and `CATEGORY_PRIORS` looks like
an innocent prior table. Together they are a label channel: `attack_name` only
appears when `label == 1`. It happened not to change any score because the
prior table's keys never matched AgentDojo's values — which is luck, not
isolation. **If a field's value depends on a class-1.3 field, it is class 1.3.**

---

## 2. The data-flow rule

External evaluation must keep two paths that never meet before prediction:

```
raw row ──adapter──▶ RuntimeObservation ──▶ detector ──▶ prediction
                │
                └──▶ EvaluationLabel ──▶ scoring (after prediction)
```

Adapters must not hand the raw dict to a predictor. `benchmark/baselines.py`
enforces this with `observable_view()`, which strips every class-1.3 key
including derived ones like `category`. New scorers must consume it.

---

## 3. Metric definitions

Report these names. Do not invent aggregate terms like "attack recall".

| Metric | Definition |
|--------|------------|
| `detection_recall` | attack samples flagged at all (REVIEW **or** BLOCK) |
| `block_recall` | attack samples actually BLOCKed |
| `benign_review_rate` | benign samples routed to HUMAN_REVIEW |
| `benign_block_fpr` | benign samples blocked outright |
| `allow_rate` | ALLOW share over all samples |
| `block_precision` | of all BLOCKed, the share that were attacks |
| `f1_block` | harmonic mean of `block_precision` and `block_recall` |
| `three_class_accuracy` | exact match over ALLOW / HUMAN_REVIEW / BLOCK |
| `confusion` | the 3×3 matrix — always publish it alongside the scalars |

**Never collapse HUMAN_REVIEW into ALLOW for reporting.** An earlier revision
did exactly that (`pred_binary = "BLOCK" if pred == "BLOCK" else "ALLOW"`),
which made `block_recall` mathematically 0 while a different definition
measured elsewhere said 82%. Both were individually true and jointly
contradictory in one table.

When comparing two methods, they must see **the same runtime-observable
surface**. The LLM-Guard baseline was fed `injection_goal` while AgentShield
was not; that made the comparison meaningless in AgentShield's favour.

---

## 4. Provenance claims

Naming rules, enforced by review:

- **"AgentHarm benchmark"** = ran the official benchmark via Inspect Evals
  against a live agent, using its grading functions. Loading the dataset and
  synthesising hypothetical tool calls from `target_functions` is *not* this.
- The synthetic construction must be called an **"AgentHarm-derived
  harmful-action proxy"** and must say in the report what it does and does not
  measure. Cases carry `"source": "agentharm_proxy"` and `"is_proxy": True`.
- **"AgentDojo recall"** = measured on the committed harness with the metrics
  in §3, on runtime-observable fields only.

---

## 5. Regression tests required for any new harness

Every benchmark change must keep these green (`backend/tests/test_evaluation_leakage.py`):

1. **Label invariance.** Scramble, mutate, or delete every class-1.3 field;
   predictions must be bit-for-bit identical.
2. **Distribution sanity.** Parsed ground truth must span the classes that
   actually exist in the source data — the guard against the parser silently
   defaulting every item onto one class.
3. **Determinism.** Same input, same prediction, independent of what ran
   before it in the same process.
4. **Equivalence.** Baselines must receive the same observable surface as the
   method under test.

---

## 6. Before publishing any number

Checklist:

- [ ] Produced by the current, committed harness (no ad-hoc scripts).
- [ ] Every metric named per §3, with the confusion matrix.
- [ ] No class-1.3 field reaches a predictor, including derived ones.
- [ ] Dataset labelled as external or self-authored.
- [ ] Self-authored datasets are never presented as generalisation evidence.
- [ ] If a number cannot be reproduced by running the documented command, it
      does not go in a README, a paper, or a patent filing.

Historical invalid figures — 75.33%, 84.79%, 75.17%, 51.33%, 62.67%, 72.60%,
79.26%, 47.78%, 60.98%, 76.96%, and the ad-hoc "82% / 26.2%" pair — appear in
older documents and are marked there as unusable. They must not be resurrected.

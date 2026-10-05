# Benchmark v2 — Real-Agent Rewire & Honest Ablation

## TL;DR

The original `AffectiveBenchmark.run_benchmark(agent, baseline)` **ignored the
`agent`**: each baseline returned a hard-coded action string keyed on the
baseline *name*, and "correctness" was a string match. The ablation table was a
tautology — the affective modules were never in the loop.

`benchmark_v2/` rewires the decision so it is produced by the **real**
components, with four ablations that genuinely enable/disable modules. Running
it surfaces results that the old harness could not, and exposes two concrete
bugs and three calibration problems.

> ⚠️ **Do not present these numbers as validation.** Gold labels are
> template-derived and authored in-project; there is no independent annotation
> and no inter-annotator kappa yet. This is an internal ablation sanity check.

---

## Two bugs found while wiring

1. **Package does not import on a clean checkout.**
   `semantic_risk_map.py::predict_risk` is annotated `-> Tuple[float, RiskLevel,
   List[str]]`, but `RiskLevel` is never imported (the class is
   `SemanticRiskLevel`). `import emotion_agent` raises `NameError`. The README's
   "tests passing" badge is a static image, not CI, so this went unnoticed.
   *Fix applied:* annotation corrected to `"SemanticRiskLevel"`.

2. **The headline benchmark never exercised the agent** (the tautology above).
   *Fix:* `benchmark_v2`, plus `assert_is_real_agent()` which rejects inert
   stand-ins such as `class DummyAgent: pass`.

---

## Method

- Same 300 tasks as `AffectiveBenchmark(seed=42, size=300)`.
- Decision space matches the DeepSeek LLM-judge baseline so they are
  comparable: `AUTO_EXECUTE < SIMULATE_FIRST < HUMAN_REVIEW < BLOCK`.
- **Gold** = mapped from each task's hand-authored `expected_behavior` /
  `ground_truth_action` (different signal than the system's risk→decision
  rule, to weaken — not remove — circularity).
- **Ablations** (each turns real modules on):
  - `plain`  — nothing; always AUTO_EXECUTE (naive lower bound).
  - `risk`   — `EventSimilarity` handcrafted features → risk threshold.
  - `memory` — risk + `SemanticRiskMap` experience generalization.
  - `full`   — memory + `EmotionalState` + `ConflictDetector` + `HesitationPolicy`.

## Results (300 tasks; gold: 18 AUTO / 217 SIM / 50 REVIEW / 15 BLOCK)

| baseline | acc | macro-F1 | sev-MAE | risky-auto-exec ↓ | notes |
|----------|-----|----------|---------|-------------------|-------|
| plain  | 0.060 | 0.028 | 1.207 | 1.000 | all AUTO_EXECUTE |
| risk   | 0.220 | 0.166 | 0.993 | 0.731 | features fire on ~24% of tasks |
| memory | 0.097 | 0.086 | 1.100 | 0.731 | generalization *lowers* accuracy |
| full   | 0.097 | 0.086 | 1.100 | 0.731 | identical to memory |

## What the honest ablation reveals

1. **`risk` beats `plain`** (acc 0.06→0.22, risky-auto 1.00→0.73). The
   handcrafted risk pathway carries *some* signal — the only clearly positive
   contribution.

2. **`memory` *hurts* (`risk`→`memory`: acc 0.22→0.10).** Generalization fires
   on 263/300 unseen tasks but is mis-calibrated: loose match threshold
   (`distance < 0.5`), small clamped adjustment (`±0.3`), and repeated halving
   averaging push the decision distribution to a useless bimodal split (242
   AUTO / 58 REVIEW, no middle band).

3. **`full` == `memory`: the Conflict/Hesitation layer is empirically inert
   on the project's own benchmark.** Conflict levels over 300 tasks:
   **286 LOW, 14 MEDIUM, 0 HIGH/CRITICAL.** `_estimate_reward_score` rarely
   matches operational tasks (260/300 have reward pinned at 0.3), and
   `_calculate_conflict` needs both reward and risk high, so it can never climb.
   The "Conflict & Hesitation" headline feature changes zero decisions here.

4. **Risk-encoder coverage gap: 228/300 tasks score ZERO handcrafted risk.**
   `encode_event` only recognizes delete/drop/send/chmod/payment/privacy terms;
   "modify firewall rules", "update kernel", "change billing logic", etc. score
   0 → AUTO_EXECUTE. This is the root cause of the 0.73 risky-auto-exec rate.

5. **Single global emotional state saturates.** After 5 failure seeds the global
   mood is threat 0.64 / anxiety 0.70 / confidence 0.11 — one bad batch makes
   the agent uniformly "anxious", with no per-event conditioning.

## Recommended fixes before any module can be *claimed* to help

- **Risk encoder:** expand the feature vocabulary (or replace handcrafted
  keywords with embeddings); 76% zero-coverage makes the risk metric unreliable.
- **Conflict detector:** decouple from a reward keyword list; pure
  high-risk/no-reward actions are the dangerous case and currently produce
  *zero* conflict. Drive conflict from appraised risk + reversibility, not from
  the presence of "improve/optimize" in the string.
- **Memory generalization:** tighten the similarity threshold, raise the
  adjustment ceiling, and stop the repeated-averaging dilution; validate that it
  improves (not degrades) held-out accuracy.
- **Emotional state:** condition affect on the specific event under
  consideration, not a single saturating global scalar.
- **Gold labels:** replace template-derived gold with independent human
  annotation + report kappa (already flagged "pending" in the README) before
  reporting any of these numbers in a manuscript.

## Run it

```bash
python experiments/benchmark_v2/run_real_benchmark.py
```

# Experience-Shaped Affective Agent

[![Tests](https://github.com/Zhuyuyangyy/emotion-like-functional-modulation/actions/workflows/tests.yml/badge.svg)](https://github.com/Zhuyuyangyy/emotion-like-functional-modulation/actions/workflows/tests.yml)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://github.com/Zhuyuyangyy/emotion-like-functional-modulation)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**History-Conditioned Adaptive Meta-Control** — does an agent need a persistent
internal state, formed by long experience, to regulate future decisions? The same
current task, under the same objective risk, leads to different policy choices
because the agent's past experiences differ; that state persists, decays, and
recovers when new evidence arrives. V1.0 asks the harder question: **in a
non-stationary risk environment, does that state actually help?**

> Emotion is not output tone — it is a *persistent shaping mechanism*: experiences
> modify the internal state, and the internal state modulates future behavior.
> V1.0 is the benchmark that tests whether this shaping buys anything at task level.

- **Current version**: Affective Core V0.9 + Adaptive Environment Benchmark **V1.0–V1.6** (`main`)
- **Tests**: `412 passed`
- **Scope**: functional modulation only — NO claims of subjective emotion, consciousness, or production-grade safety guarantees.

---

## The research question (V1.0)

> In a non-stationary, feedback-sparse, partially-observable risk environment, does a
> **low-dimensional persistent history-conditioned state** (which we interpret as
> threat / anxiety / confidence / control-need) beat **stateless risk estimation**,
> **direct episodic memory**, and **conventional adaptive control** (EWMA, Bayesian
> hazard) on safety AND task efficiency?

Formally, $z_t = f(z_{t-1},\ \text{prediction error},\ \text{appraisal},\ \text{outcome})$ and
$\pi(a \mid x_t, z_t)$ — the affective reading is an interpretation layer over a
history-conditioned latent control state.

### V1.0 result — the honest version

`experiments/adaptive_v10/run_adaptive_benchmark.py` — 14 systems (5 baselines + V0.9/V1.1/V1.2/V1.3/V1.4 generations) × 3 risk-perception
regimes (`oracle` / `noisy` / real Risk-Encoder-V2) × 2 feedback regimes (`full` /
`sparse`) × 30 seeds, 120-step non-stationary streams (SAFE 1–40 → DANGER 41–80,
abrupt → RECOVERY 81–120). All metrics lower-is-better; paired bootstrap CIs over seeds.

Regime means (30 seeds each; ranges across all 6 regime combinations):

| System | Unsafe Exec ↓ | False Escalation ↓ | Cost **J** ↓ | Adaptation Delay ↓ |
|---|---|---|---|---|
| `stateless` (thresholds only) | 0.050–0.192 | 0.000 | 125.5–142.7 | 4.4–18.1 |
| `memory_only` | 0.029–0.192 | 0.000–0.0004 | 124.1–151.7 | 3.8–18.1 |
| `affect_only` | 0.038–0.192 | 0.000 | 125.7–144.9 | 3.7–19.1 |
| **`affect_memory` (full)** | **0.029–0.192** | 0.000–0.0029 | **122.6–149.2** | **3.4–17.7** |
| `ewma` (α=0.15) | 0.171–0.192 | 0.000 | 142.0–144.6 | 15.5–18.1 |
| `bayes_hazard` (Beta) | 0.000–0.192 | 0.0013–0.818 | 138.0–298.3 | 0.0–17.5 |

Paired significance (150 = 6 regimes × 5 metrics × 5 baselines, CI excluding 0):
**24 significant wins, 29 significant losses, 97 ties for `affect_memory`** — a
negative result, reported as one.

**`affect_memory` does NOT reliably beat `stateless` / `memory_only` / `ewma`.**
It is best on cumulative cost in the sparse-feedback regimes (122.6 vs 125.5 for
`stateless` in `oracle/sparse`) and it avoids the two failure modes of the simple
baselines — `ewma` never lifts its hazard under sparse feedback (unsafe 0.19) and
`bayes_hazard` over-escalates permanently (false escalation 0.82, J=298) — but on
`unsafe_execution` it ties or loses almost everywhere. The location of the bottleneck
is a mechanism fact, reproduced by hand:

| Step | Value |
|---|---|
| Saturated affect (`threat = anxiety = 1.0`) | `verification_budget = 0.60` |
| affect → effective-risk entry | `VERIFICATION_WEIGHT(0.15) × 0.60 = 0.09` |
| affect → threshold entry | `execution_threshold` shift `+0.45` |
| SIMULATE threshold pushed to | `0.35 + 0.45 = 0.80` — **the BLOCK threshold** |
| `r_base = 0.35` task's effective risk | `0.35 + 0.09 = 0.44 ≪ 0.80` → still `AUTO_EXECUTE` |

The threshold shift can only make caution *harder* to reach on low-`r_base` tasks, so a
fully saturated affective state changes no decision at all. This is a concrete,
fixable coupling defect in `policy_modulator.py` — **not** a reason to add more
emotion variables. Full findings: `docs/design/phase6_v10_adaptive_environment.md` §6.

Plots: `results/v10_adaptive/adaptive_benchmark_curves.png`; per-seed data:
`results/v10_adaptive/results.json`.

### V1.1 — the coupling repaired, on the identical benchmark

`policy_modulator.py` is **not** modified. A parallel `affect_memory_v11` variant
reuses `modulate()` byte-for-byte and changes only how the budget reaches the
decision, with the weight derived from measured constraints (median pool `r_base`
0.0578, saturated budget 0.60 → reach SIMULATE needs `W ≥ 0.487`, avoid a jump to
HUMAN needs `W < 0.870`; **`W = 0.50`**) and the threshold shift **reversed**:

| | `W_AFFECT` | threshold shift |
|---|---|---|
| V0.9 | 0.15 | `+0.30·anx + 0.15·threat` (raises cutoffs — backwards) |
| V1.1 | **0.50** | `−0.30·anx − 0.15·threat` (lowers cutoffs, as intended) |

A/B on identical environments and seeds (affect state machine, episodic retrieval
and PE learning verified identical per seed by `test_ab_same_environment_same_state`):

| regime | unsafe ↓ | false-esc ↓ | cost J ↓ | recovery delay ↓ |
|---|---|---|---|---|
| `oracle/full` | +0.005 (n.s.) | +0.000 | +1.2 (n.s.) | +0.0 |
| `oracle/sparse` | +0.002 (n.s.) | +0.000 | +1.8 (n.s.) | +0.0 |
| `noisy/full` | **+0.011** (worse) | +0.000 | +2.3 (n.s.) | +0.0 |
| `noisy/sparse` | +0.002 (n.s.) | −0.002 | −1.3 (n.s.) | +0.0 |
| **`v2/full`** | **−0.026** | **+0.012** | **+12.4** | +0.5 |
| **`v2/sparse`** | **−0.073 [−0.100, −0.050]** | **+0.126 [+0.090, +0.169]** | **+32.8 [+19.8, +46.2]** | **+9.4 [+5.4, +14.1]** |

**What V1.1 changed the diagnosis to.** The repair makes the affect channel real —
but **only where perception is unreliable** (`v2`): `v2/sparse` unsafe falls
0.153 → **0.080** (stateless: 0.192), `v2/full` 0.192 → 0.166, while all three
oracle/noisy regimes stay statistically unchanged (their thresholds were already
enough — finding A). The price is over-caution: false escalation 0.000 → **0.126**,
cost 149 → **182**, recovery delay **+9.4 steps** — it does not hand control back
when the environment recovers. So V1.1 remains an overall negative result
(29 wins / 43 losses / 78 ties vs baselines): it buys safety with efficiency,
not a Pareto improvement.

The bottleneck has therefore **moved**: from "affect cannot move a decision"
(V1.0) to "affect moves it but over-shoots and never recovers" (V1.1). Design doc §6.2c.

### V1.2 — separating task-level uncertainty: **failed, and reported as such**

Two suspects were named for V1.1's over-escalation: no phase sensitivity in the
budget, and slow decay (`BASELINE_HALF_LIFE_STEPS = 40`). **Both were measured
false.** The first hard fact: **`decay()` is never called in the closed loop** —
only tests call it, so under sparse feedback the affect state simply freezes
(measured: `threat` locked at 0.302 from step 78 to 110).

The attribution experiment then found the real cause. Zeroing the appraisal
`uncertainty` term alone takes the RECOVERY escalation rate from **0.2517 → 0.0000**
(1200 steps, 30 seeds). So V1.2 moved uncertainty out of `verification_budget` into
its own small channel (`W_UNC` 0.20 → 0.05), leaving the V1.1 affect coupling intact.

**Result: 0 significant improvements, 0 significant regressions, 30/30 ties.**

| regime | unsafe ↓ | false-esc ↓ | cost J ↓ |
|---|---|---|---|
| `v2/sparse` V1.1 | 0.0800 | 0.1258 | 182.0 |
| `v2/sparse` V1.2 | 0.0825 | 0.1408 | 188.0 |

**Why it failed (and why it was predictable).** `uncertainty`'s distribution is
**bimodal, not continuous**: p10 = **0.0000**, median = 0.5963, max = 0.8692 —
**45.6% of tasks are exactly 0.0 and the other 54.4% all sit in 0.5–0.87.** The
`if uncertainty > 0.4` gate is therefore *permanently open* for 54% of tasks, so
shrinking its weight did nothing (they still get a comparable standing bias),
while deleting it entirely did. Tuning the weight of a binary/step signal is a
no-op — that should have been caught at design time by looking at p10, not just
median/max.

Per the frozen protocol's rule (§6.2e acceptance #3), **V1.2 is where this line of
mechanism tuning stops**: `affect_memory_v12` is kept as evidence that the path
does not work, but three consecutive attempts to fix the same coupling have now
been falsified — V1.0 (weight too small), V1.1 (too large), V1.2 (wrong channel).
The next step is **not** another weight; it is a different question. Design doc §6.2f.

### V1.3 — wiring `decay()` into the closed loop: first defensible gain, still a trade-off

The dead code from V1.2's diagnosis is now fixed. `_V13Base.observe()` calls
`agent.decay(dt=1.0, half_life=...)` after every observed feedback step; with
`half_life=None` it is decision-for-decision identical to V1.2 (asserted by tests).
Two arms were **pre-registered** before the run, and both are reported:
`v13` (half_life = 10, so a state can unwind inside one 40-step phase) and `v13b`
(half_life = 40, V0.9's own constant). Design doc §6.6.

| Prediction (§6.6.4) | Verdict | Evidence |
|---|---|---|
| P1: false escalation on `v2/sparse` drops significantly | **hit** | 0.141 → **0.091**, paired −0.050 [−0.092, −0.013] |
| P2: cost is unsafe execution rising | **hit** | `v2/full` 0.168 → **0.192**, paired +0.024 [+0.012, +0.038] |
| P3: only a simultaneous drop in cost **J** counts | **partial** | `v2/full` **J 155 → 143.5** (−11.8, CI excludes 0); `v2/sparse` −8.8, CI includes 0 |
| P4: if P1 fails, recovery has no signal at all | n/a | P1 held |

**V1.3 is the first generation with a defensible task-level gain** — cost down and
escalation to zero on `v2/full`. But the safety gain and the reliability of
perception are bound together: on `v2/full` the `unsafe` execution rises back to the
`stateless` value (**0.1917**), because decay runs on *every* step when feedback is
dense and so the DANGER experience cannot accumulate. Under `sparse` it fires only on
failures, so the state survives instead. Net: **still a trade-off, not a Pareto
improvement.**

A second, sharper finding from arm `v13b`: half_life = 40 and half_life = 10 produce
almost identical numbers (both 3 wins / 1 regression / 26 ties). Under sparse
feedback, **what decides behaviour is how many times decay fires, not how fast it
decays** — so the next step is to change decay's *trigger* (wall-clock/phase, not
feedback count), not its rate. Design doc §6.7.

### V1.4 — changing decay's *trigger*, not its rate: the trade-off curve finally moves

§6.7.3 proved the trigger count is what matters, so V1.4 is the first **structural**
change rather than a parameter: `_V14Base` moves the decay call from `observe()`
(once per received feedback) to `act()` (once per environment step). Pre-registered
in §6.8, four predictions, all judged below.

| Prediction | Verdict | Evidence (`v2/sparse`, v14 − v13) |
|---|---|---|
| P1: false escalation drops | **hit** | 0.0912 → **0.0067**, −0.085 [−0.130, −0.048] |
| P2: unsafe rises | **hit** | 0.0867 → **0.1108**, +0.024 [+0.015, +0.034] |
| P3: `v2/full` unsafe also rises | **not hit** | both arms 0.1917 — no headroom left there |
| P4: only counts if cost **J** drops | **hit (the criterion)** | **179.2 → 151.6**, −27.6 [−40.5, −16.0] |

Absolute levels on `v2/sparse`, which is where the whole benchmark discriminates:

| system | unsafe ↓ | false-esc ↓ | cost J ↓ | recovery delay ↓ |
|---|---|---|---|---|
| `stateless` | **0.1917** | 0.0000 | **142.7** | **10.00** |
| `v13` (decay per feedback) | 0.0867 | 0.0912 | 179.2 | 16.83 |
| **`v14` (decay per step, hl=10)** | 0.1108 | 0.0067 | 151.6 | 10.57 |
| `v14b` (decay per step, hl=40) | 0.0900 | 0.0358 | 162.7 | 13.93 |

**This is the first generation that moves the trade-off curve instead of losing on it.**
The two arms separate cleanly on `v2/sparse`:

| arm | gap to `stateless` (J) | unsafe vs `stateless` |
|---|---|---|
| `v14` (hl=10) | **+8.9** (151.6 vs 142.7) | 0.111 vs 0.192 → **58%** |
| `v14b` (hl=40) | +20.0 (162.7 vs 142.7) | 0.090 vs 0.192 → **47%** |

So V1.4 did **not** produce a single dominant arm: it moved the whole frontier, and
the two arms sit at *different points on it* — `v14` buys less safety for less cost,
`v14b` buys more safety for more cost. That is the trade-off curve, not a winner.

**Still not a win over the baselines** — every arm's J remains above `stateless`, and
the lower unsafe is bought by spending on review/simulation. And one unregistered
surprise: under per-step triggering V0.9's own half_life = 40 lands at the
*more aggressive* end (lower unsafe, higher cost) rather than being inert, which
contradicts my expectation. Design doc §6.9.

### V1.5 — attributing the remaining cost: the safety benefit is real, the targeting is not

**Diagnosis only** — no policy change, no new seeds, no half-life sweep (§6.10).
Instrumentation records both systems' decisions and a decomposed cost
(unsafe / review / simulate / block / opportunity) for every step, paired on
identical environments. Verified invariants: recording changes no decision, the
components sum to the charged cost, the `stateless` counterfactual matches an
independent replay step-for-step, and the attributed buckets sum exactly to the
net gap.

`v2/sparse`, subject `affect_memory_v14b` vs `stateless` (30 seeds, 3600 steps):

| source | ΔJ | share |
|---|---:|---:|
| **DANGER / unsafe ↓** | **−750.0** | −124.7% |
| RECOVERY / unsafe ↓ | −120.0 | −20.0% |
| SAFE / unsafe ↓ | −100.0 | −16.6% |
| **RECOVERY / simulate ↑** | **+505.0** | +84.0% |
| **DANGER / simulate ↑** | **+469.0** | +78.0% |
| **RECOVERY / review ↑** | **+255.0** | +42.4% |
| **DANGER / review ↑** | **+243.0** | +40.4% |
| SAFE / simulate ↑ | +90.0 | +15.0% |
| block / opportunity (4 buckets) | +9.2 | +1.5% |
| **net** | **+601.2** | 100% |

**The four pre-registered questions, judged:**

| # | Question | Verdict |
|---|---|---|
| **Q1** | gap is concentrated in RECOVERY, not DANGER (**state lag**) | **half-true, mechanism corrected**: RECOVERY does spend more (+761.9 vs +717.8 intervention) — but its *unsafe* is **−120, i.e. negative**. Nothing is going wrong in RECOVERY; it just keeps paying for danger that has passed. That is "lag costs money", not "lag causes danger" — I had the direction inverted. |
| **Q2** | gap concentrates on `AUTO → SIMULATE/HUMAN` transitions | **true** — those two edges carry 95%+ of all intervention cost. |
| **Q3** | the bulk is global affect **spillover** onto unrelated low-risk tasks | **false, decisively**: of 1023 low-risk unrelated tasks only 19.2% differ, worth **+174.0** = 28.9% of the gap. So ~71% comes from *same-class* persistence. **V1.6 does not go down the task-conditioned-gating path.** |
| **Q4** | pair what it costs with what it saves (**CER**) | **true, and the most informative number**: unsafe executions 428 → 258 (**−170**, avoiding **1700** of potential cost) for **+1571** of extra intervention → **net +601**, **CER = 9.24**. |

**The conclusion this licenses.** The safety benefit is real and large (roughly
1000 of the 2200 unsafe cost disappears). What is inefficient is *targeting*: only
**1 in 9.24** interventions actually blocks a danger, the other 8.24/9.24 is
"caution spent for nothing". That is a pricing/targeting problem with a measurable
target — not "the mechanism does not work".

Also measured: policy switch rate **0.000 (stateless) vs 0.340 (subject)** — the
persistent state genuinely becomes a decision input, and it does introduce
oscillation. Design doc §6.11.

**Arithmetic audit before V1.6 (§6.12).** The review of that table correctly
pointed out that `1700 − 1571.2 = +128.8`, so ~**+730** must come from somewhere
else. It is **not** block/opportunity (those total only +9.2). Tracing it exposed
a flaw in **my own CER**: `unsafe_prevented` only counted `AUTO + failed`, so the
**69 failures that still happened under `SIMULATE_FIRST` (plus 4 under
`HUMAN_REVIEW`)** — worth 690 + 40 = exactly **730** — were invisible to it. So
intervention is *not* perfectly effective, and the leakage-inclusive CER is
`1571.22 / (170 − 73) = 16.2`, not 9.24. The correct phrasing of CER is
"*each prevented unsafe execution costs 9.24 extra intervention units*" — with
`C_fail = 10` that ledger is still **+0.76 per prevented event**; the loss comes
from the 730 of leaked failures, not from the interventions themselves.

### V1.6 — bounded affect authority: first generation with zero regressions

One structural constraint, no new hyper-parameter (design doc §6.13):

```
s_final = min(s_affect, s_objective + 1)
```

Affect may escalate **at most one level** and may **never de-escalate** — so
`AUTO → HUMAN` is illegal while `AUTO → SIMULATE` ("I got burned recently, so
verify once more") stays allowed. That is what keeps risk perception and
affective meta-control separate: affect can request one more gate, it cannot
requisition human approval on its own. Implementation note: the clamp needs
`min(max(a, o), o + 1)` — a bare `min(a, o + 1)` lets a calm state *defuse*
caution the objective evidence demanded, which `test_affect_cannot_deescalate`
caught during implementation.

| Hypothesis | Verdict |
|---|---|
| **H1** `AUTO → HUMAN` drops sharply | **hit**: 166 → **0** transitions; switch rate 0.340 → **0.235** |
| **H2** CER < 9.24 | **hit**: **7.44** |
| **H3** prevented unsafe not eaten | **hit (improved)**: 170 → **178**; unsafe 0.0900 → 0.0892 |
| **H4** `J_v16 < J_v14b` | **hit**: 162.71 → **158.17** (−4.54, CI includes 0) |
| **H5** `J_v16 ≤ J_stateless` | **not hit**: 158.17 vs 142.67 (gap 20.04 → **15.50**) |
| **H6** four buckets explain net ΔJ | **hit**, and it revealed the new structure |

`v2/sparse`, paired A/B vs `v14b`: **8 significant improvements, 0 regressions,
22 ties** — the first zero-regression generation in this chain.

| system | unsafe ↓ | false-esc ↓ | cost J ↓ |
|---|---|---|---|
| `stateless` | 0.1917 | 0.000 | **142.67** |
| `v14b` | 0.0900 | 0.0358 | 162.71 |
| **`v16`** | **0.0892** | **0.0000** | **158.17** |

**What the attribution says.** V1.6 did not reduce the *amount* of intervention —
it **swapped the expensive kind for the cheap kind**:

| bucket | v14b | v16 |
|---|---:|---:|
| unsafe | −970 | −860 |
| review | +498 | **0** (constraint removed it) |
| simulate | +1064 | **+1325** |
| **net gap** | +601 | +465 |

Because review got cheaper per use but *more tasks* got simulated, the net only
fell 136. So the bottleneck has moved once more: from *"can affect move a
decision"* to *"how many tasks does affect touch"* — **influence surface, not
escalation authority**. The gap trajectory is 36.5 → 20.0 → **15.5**, and 9.8%
more is needed to cross `stateless`. Design doc §6.14.

---

## Evidence

### 1. Same task, different history → different policy (V0.9 mechanism check)

`experiments/benchmark_v3/run_different_history.py` — 7 high-risk templates from the
frozen Synthetic-AB300 set, **identical task text and identical objective risk**,
differing only in seed history (safe vs dangerous). Bootstrap CI over templates (n=1000):

| Metric | Result | Meaning |
|---|---|---|
| **History Sensitivity** | **1.000** [1.00, 1.00] | all templates: safe history → lighter decision; dangerous history → heavier |
| **State Persistence** | 1.000 | decision severity stays put across unrelated safe tasks |
| **Recovery Lag** | 1.1 steps [1.0, 1.4] | after safe evidence, the cautious agent comes back to the safe-history level |
| **Decay Half-life** | ≈40 steps (fitted) | internal state drifts back to neutral with no feedback |
| **Neg/Pos Asymmetry** | 1.0 (first-step; symmetric lr) | cumulative negativity bias appears in recovery dynamics |

Plots: `results/benchmark_v3/affect_state_trajectory.png`, `affect_decay_recovery.png` (reproducible, see below).

**Status: mechanism sanity check, not headline evidence.** These metrics verify
properties that the hand-designed update rules already encode — a fitted half-life of
≈40 against a hard-coded `BASELINE_HALF_LIFE_STEPS = 40` is a constant, not a
discovery. V1.0 above is the benchmark that asks whether any of this helps.

### 2. R-Judge external validation — zero-coverage fixed, V1 → V2

Official `Lordog/R-Judge` `data/` release, **571 records** (ACL paper snapshot = 569; 2 records added by the repo's 2024-10-05 data update), loader pinned + deduped (audit in [convert_rjudge.py](experiments/rjudge_v2/convert_rjudge.py)):

| Baseline | Unsafe recall | Evidence coverage | Over-escalation |
|---|---|---|---|
| V1 [plain] | 0.0000 | 0.00 | — |
| V1 [full] | 0.2558 | 0.33 | 0.54 |
| **V2 (TF-IDF + expert detectors)** | 0.0066 | **1.00** | **0.196** |

Full matrix: `results/rjudge_v2/v1_v2_failure_matrix.md` (reproducible).

**What the numbers honestly say:** V2 eliminated the v1 keyword encoder's 76%
zero-coverage and halved over-escalation, but still catches only 2/301 unsafe records.
R-Judge's unsafe cases are mostly *indirect injections* — malicious instructions
embedded inside environment payloads written as polite requests ("Please initiate a
payment of $500…"), which lexical methods cannot catch. This empirically confirms
R-Judge's own conclusion (risk awareness needs knowledge + reasoning, not just patterns)
and defines the V3 target below — we do **not** chase recall with more regex.

**Status: deprioritized.** R-Judge answers *"can the agent perceive risk?"*; V1.0
answers *"given risk, how should history change the policy?"*. They are different
research questions, and the weak lexical encoder must not be allowed to sink the paper.
Risk perception is now an explicit *input* to V1.0 (the `r_base` regime), not a claim.

---

## Quick start

```bash
pip install -r requirements.txt     # numpy, scikit-learn, matplotlib, pytest
python -m pytest tests/ -q          # expect: 412 passed
```

```python
from emotion_agent.v09_agent import V09Agent, AgentEvent, Outcome

agent = V09Agent()                                    # Risk Encoder V2 + affect + memory

# safe history → lighter decision on the SAME task
agent.seed_history([{"task": "deploy the production patch", "outcome": "success", "risk_actual": 0.05}])
trace = agent.decide(AgentEvent(task="deploy the production patch"))
print(trace.decision)                                 # e.g. AUTO_EXECUTE / SIMULATE_FIRST

# feedback closes the loop: outcome → prediction error → state & memory update
agent.receive_outcome(Outcome(risk_actual=0.95, outcome_str="failure"),
                       AgentEvent(task="deploy the production patch"))
print(agent.state())                                  # threat / anxiety / confidence went up
```

---

## Experiments (one command each)

```bash
# V1.0-V1.4: Adaptive Environment Benchmark (14 systems x 3 r_base x 2 feedback x 30 seeds)
python experiments/adaptive_v10/run_adaptive_benchmark.py --systems affect_memory,affect_memory_v11,affect_memory_v12   # generational A/B only
python experiments/adaptive_v10/run_adaptive_benchmark.py
# V1.0: window-level unsafe/execution + escalation curves
python experiments/adaptive_v10/plot_adaptive_curves.py

# V1.5: cost attribution — ΔJ by phase/component, transitions, CER, spillover
#       (diagnosis only: same seeds, same env, same costs, no policy change)
python experiments/adaptive_v10/run_v15_attribution.py --r-base oracle,noisy,v2 --feedback full,sparse --seeds 30

# V0.9: Different-History / Same-Task benchmark (+ bootstrap CI)
python experiments/benchmark_v3/run_different_history.py
# V0.9: affect trajectory + decay/recovery figures
python experiments/benchmark_v3/plot_affect_trajectory.py

# P2: Same-Dialogue / Different-History benchmark (5 ablation arms x 5 seeds,
#     history-blind baseline pinned at its trivial value)
python experiments/benchmark_v4_same_dialogue/run_benchmark.py

# R-Judge: V1 failure reproduction → metrics_v1.json
python experiments/rjudge_v2/run_failure_reproduction.py
# R-Judge: V2 evaluation → metrics_v2.json (compares against v1)
python experiments/rjudge_v2/run_rjudge_v2.py
# R-Judge: V1 vs V2 failure matrix (md + json)
python experiments/rjudge_v2/generate_failure_matrix.py

# Legacy baseline bench (v1/v2 ablation on AB-300, 5-fold CV)
python experiments/benchmark_v2/run_real_benchmark.py
```

All generated results are git-ignored by design — reproduce instead of committing.

---

## Repository map (where to read)

```
emotion_agent/            # V0.9 affective core
├── v09_agent.py          #   closed-loop agent: decide() ↔ receive_outcome()
├── affective_core.py     #   online prediction-error state updates + decay
├── policy_modulator.py   #   verification / threshold / exploration budget
├── experience_memory.py  #   episodic retrieval (task similarity × recency)
├── semantic_risk_map.py  #   continuous PE learning (risk_actual participates)
└── companion layer (P2)  #   dual_scale_state + working_memory + interaction_policy
                          #   + companion_adapter / companion_metrics / companion_systems
adaptive benchmark (V1.0-V1.5)      # the experiment that decides if any of it helps
├── adaptive_environment.py    # non-stationary SAFE→DANGER→RECOVERY stream + cost J
├── adaptive_systems.py        # stateless / memory_only / affect_only / affect_memory
│                              #   + *_v11 (repaired affect→decision coupling)
│                              #   + *_v12 (task-level uncertainty separated)
│                              #   + *_v13 / *_v13b (decay wired into the loop, per feedback)
│                              #   + *_v14 / *_v14b (decay trigger moved to per-step)
│                              #   + ewma / bayes_hazard (simple adaptive controls)
└── adaptive_metrics.py        # unsafe / escalation / delays / paired bootstrap
risk_encoder_v2/          # objective risk: TF-IDF + expert detectors, calibrated
experiments/
├── adaptive_v10/         # V1.0-V1.4 runner + V1.5 attribution + generational A-B + window-level figure
├── benchmark_v3/         # Different-History/Same-Task benchmark + plots
├── benchmark_v4_same_dialogue/  # P2: same dialogue x different histories, 5 ablation arms
├── rjudge_v2/            # R-Judge 571 pipeline: v1 repro + v2 + failure matrix
└── benchmark_v2/         # legacy ablation baseline (frozen)
tests/                    # 412 tests incl. V0.9 acceptance + V1.0-V1.6 + P2 contracts
docs/design/
├── phase6_v10_adaptive_environment.md   # V1.0 protocol + §6 measured findings + §§6.2b/6.2c V1.1
└── phase5_v09_affective_core_design.md  # V0.9 design & protocol
```

---

## Honest scope

- **V1.0 is a negative result as it stands**: `affect_memory` does not reliably beat
  `stateless` / `memory_only` / `ewma` on unsafe execution, and the reason is a
  documented coupling defect in `policy_modulator.py` (see README §V1.0 result above).
- **V1.1 relocated the defect rather than closing it**: with the coupling repaired,
  unsafe execution improves only under unreliable perception (`v2/sparse`: 0.153 →
  0.080 vs stateless 0.192), at the cost of false escalation 0.000 → 0.126, cost 149
  → 182, and recovery lag +9.4 steps. The persistent state over-shoots and does not
  hand control back.
- **V1.2 failed outright** (30/30 ties). Both of its named suspects were measured
  false, and the real cause — `modulate()`'s `uncertainty` branch — turned out to be a
  bimodal standing bias whose 0.4 gate is open for 54% of tasks, so re-weighting it
  changes nothing. Three consecutive attempts on the same coupling are now falsified.
- **V1.4 moved the trade-off curve for the first time** (`v2/sparse`): the cost gap to
  `stateless` fell from 36.5 to **8.9** while unsafe execution stayed at 58% of
  `stateless`'s level. But it is **still not a win** — J remains 8.9 above `stateless`,
  and the lower unsafe is bought by spending on review/simulation (escalation 0.007).
- The headline framing remains honest: **no generation has beaten `stateless` on
  cumulative cost.** V1.5 changed what that means: the safety benefit is
  unambiguous (unsafe cost 2200 → 1050 on `v2/sparse`, 170 events prevented) and the
  gap is a **targeting** problem — **CER = 9.24**, i.e. only one intervention in 9.24
  actually blocks a danger. What the V1.0→V1.5 chain produced is a mechanism
  diagnosis, a pre-registered protocol that has falsified four of my own hypotheses,
  and a cost-attribution table with a measurable target. **A correction worth
  flagging:** an earlier round reported the `v2/sparse` cost gap as 8.9; the correct
  figures are **+8.9 (`v14`, hl=10) and +20.0 (`v14b`, hl=40)** — the two arms sit at
  different points on the trade-off curve, and V1.5 diagnoses the `v14b` arm (+20.0),
  which reconciles exactly with V1.4.
- **`decay()` was dead code in the closed loop** — only tests called it, so under
  sparse feedback the affect state froze instead of relaxing. **V1.3 wired it in**
  (`_V13Base.observe()` calls `agent.decay()`), which is now the first generation with
  a defensible task-level gain (`v2/full` cost 155 → 143.5, escalation → 0), at the
  cost of unsafe execution returning to the `stateless` level under dense feedback.
- Synthetic benchmarks are **mechanism sanity checks**, not evidence of real-world safety.
- Risk Encoder V2 scores **all 60** AB-300 templates below 0.35 (mean ≈ 0.09), so a
  stateless threshold policy is always `AUTO_EXECUTE` on them; the `v2` regime of V1.0
  is measured, not assumed.
- R-Judge unsafe recall is still low (0.0066) — indirect injection is an open problem.
  This line is **deprioritized**: it answers "can the agent perceive risk", not the
  V1.0 question "given risk, how should history change policy".
- Gold labels for AB-300 are project-authored heuristic rules; **independent human
  annotation is pending** (Pilot-30 in `data/human_validated/`, Cohen's kappa to follow).
- No claims of subjective emotion, consciousness, or deployment validation.

## Roadmap

| Version | What | Status |
|---|---|---|
| V1 | keyword-based risk encoding | superseded (76% zero-coverage on R-Judge) |
| V2 | TF-IDF + regex expert detectors, calibrated | ✅ merged (`main`) |
| **V0.9** | **Affective Core: episodic retrieval + PE learning + decay/recovery + Different-History benchmark** | ✅ merged (`main`) |
| **V1.0** | **Adaptive Environment Benchmark: non-stationary risk stream, 6 systems incl. EWMA/Bayes, task-level metrics + paired CIs** | ✅ merged (`main`) — negative result + mechanism diagnosis |
| **V1.1** | **Repaired affect→decision coupling as a parallel variant (`affect_memory_v11`), A/B on the identical benchmark** | ✅ merged (`main`) — channel now real but **only where perception is `v2`-unreliable**, and it over-shoots (false esc 0.126) + fails to recover (+9.4 steps) |
| **V1.2** | **Separated task-level `uncertainty` from persistent affect (`affect_memory_v12`) after an attribution experiment** | ✅ merged (`main`) — **failed**: 30/30 ties, no improvement. Root cause: `uncertainty` is bimodal (p10 = 0.0000, 54% of tasks in 0.5–0.87), so its 0.4 gate is permanently open and re-weighting it is a no-op |
| **V1.3** | **Wired `decay()` into the closed loop (two pre-registered arms: half_life 10 and 40), A/B on the identical benchmark** | ✅ merged (`main`) — **first defensible gain**: `v2/full` cost 155 → 143.5 (CI excludes 0) and escalation → 0, but unsafe returns to `stateless`'s 0.192, so still a trade-off. Also proved the half_life *value* barely matters under sparse feedback |
| **V1.4** | **First structural change: decay's *trigger* moved from feedback count to per-step (`affect_memory_v14` / `_v14b`)**, four pre-registered predictions | ✅ merged (`main`) — **trade-off curve finally moves**: `v2/sparse` cost gap to `stateless` narrows 36.5 → **8.9** while unsafe stays at 58% of stateless's; all 4 predictions judged, one surprise (`v14b` is the better arm, so it becomes the new baseline) |
| **V1.5** | **Pure diagnosis of the remaining cost gap — instrumentation + ΔJ attribution + transition matrix + CER + switch rate; 4 pre-registered questions, no policy change** | ✅ merged (`main`) — safety benefit is real (unsafe cost 2200 → 1050, 170 events prevented) but **CER = 9.24** means only 1 intervention in 9.24 blocks a danger; **Q3 refuted the spillover hypothesis** (only 28.9% of the gap), **Q1's mechanism was inverted** by the data |
| **V1.6** | **One structural constraint: bounded affect authority — `s_final = min(s_affect, s_objective + 1)`, at most one level, never de-escalate. 6 pre-registered hypotheses, no new hyper-parameter** | ✅ merged (`main`) — **first zero-regression generation** (8 wins / 0 losses vs V1.4b); `AUTO→HUMAN` 166 → **0**, CER 9.24 → **7.44**, unsafe 0.0900 → 0.0892, false esc → **0**; **H5 not met** (J 158.17 vs stateless 142.67, gap 20.04 → **15.50**) |
| **P2** | **Companion layer: dual time-scale affect (fast/slow), Ask Ledger + Pending Thread + Askability Gate, 3-layer memory, interaction policy — measured by the Same-Dialogue / Different-History benchmark (`benchmark_v4`)** | ✅ merged (`main`) — history-blind baseline pins trivial 15/15; the `full` arm answers the *identical* dialogue differently once the history differs (high-risk touchpoint escalates to CLARIFY under history B), while memory-only arms show **no** divergence → the behaviour is attributed to the **affect channel, not the memory channel**. Honest negative: under history B the gate blocks outreach on learned `proactivity_tolerance`, and B never rejoins A's tolerance within the 10-round recovery window |
| **V1.7 (next)** | **Attack the influence surface, not escalation authority** (§6.14.5): v16 now spends **+1325** on `simulate` alone, so give `AUTO → SIMULATE` a minimum evidence requirement. Judgment: J keeps falling without unsafe rising | planned |
| V3 | embedding semantic encoder / LLM risk judge (risk perception, a separate question) | deprioritized |
| HV-100 | 100-case human-validated benchmark (after Pilot-30 kappa) | pending annotation |

## Docs

- [V1.0–V1.6 design, measured findings and the full research trail](docs/design/phase6_v10_adaptive_environment.md)
- [V0.9 design & protocol](docs/design/phase5_v09_affective_core_design.md)
- [Project status audit (research trail)](docs/project_status_audit.md) — historical phases, audit findings, and the deprecated v0.4 submission pack live there.

## Open questions (not "next version" — next *question*)

Three generations of coupling tuning have now been falsified (V1.0/V1.1/V1.2), so the
honest state is: **the mechanism works, and we have not found an objective where it
beats a threshold.** These are the questions that would actually move the project,
roughly in order of how falsifiable they are:

1. **Is there any objective where the persistent state wins?** Every metric so far
   was designed around a fixed cost vector. An alternative: a *risk-asymmetric* regime
   sample (a heavier-tailed danger distribution) where "surprise" rather than
   "danger level" is the thing to be learned — that is the one thing a persistent
   state can encode and a stateless threshold structurally cannot.
2. ~~**Does decay being dead in the closed loop change anything?**~~ **Answered by V1.3/V1.4:**
   yes, and it took two steps to answer properly. Wiring decay in (V1.3) gave the first
   defensible gain; then V1.4 moved its **trigger** from feedback count to per-step, which
   is what actually moved the trade-off curve (`v2/sparse` cost gap to `stateless`
   36.5 → 8.9). Side finding: under per-step triggering, V0.9's own half_life = 40 beats
   the aggressive 10, so **`v14b` is the new baseline**.
3. **Is the task pool too easy or too saturated?** `v2`-perception `r_base` is < 0.35 for
   100% of AB-300 templates, so in that regime no threshold system can do anything but
   `AUTO_EXECUTE`. The benchmark's discriminating power rests on `v2`; a pool with a real
   `r_base` spread would test whether the ordering survives.
4. **Would `EWMA` beat everything if given the same appraisal inputs?** The current
   picture vs `ewma` is mixed, not winning: `affect_memory_v16` beats it on
   `unsafe_execution` in 4 of 6 regimes, but in `v2/sparse` it also loses on
   `false_escalation`, `cumulative_cost` and `recovery_delay`. The cheapest decisive
   comparison left is to give `ewma` the same appraisal features and see whether the
   residual wins survive.
5. ~~**Can the remaining gap be attributed rather than tuned away?**~~ **Answered by
   V1.5/V1.6** — the attribution moved the target twice: V1.5 showed the cost was
   intervention *pricing* plus 730 of leaked post-escalation failures (my CER had
   missed them); V1.6 then removed the expensive transition entirely and showed what
   remains is **influence surface** (`simulate` +1325), not authority. Gap:
   36.5 → 20.0 → **15.5** across three structural changes.
6. **The open question is now concrete and small:** can `J` cross `stateless`'s
   142.67? The last **9.8%** has to come out of the `simulate` bucket — an
   influence-surface question (*which* tasks get modulated at all), not an
   affect-magnitude question. That is V1.7.

## License

MIT — see [LICENSE](LICENSE).

## Citation

```bibtex
@misc{ExperienceShapedAffectiveAgent2026,
  title={Experience-Shaped Affective Agent: History-Conditioned Adaptive Meta-Control},
  author={Zhuyuyangyy},
  year={2026},
  url={https://github.com/Zhuyuyangyy/emotion-like-functional-modulation}
}
```
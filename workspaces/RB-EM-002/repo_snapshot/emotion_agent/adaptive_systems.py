"""
adaptive_systems.py (V1.0)
===========================
The six comparable systems of the Adaptive Environment Benchmark, all sharing
one interface and one objective-risk input.

Frozen protocol: docs/design/phase6_v10_adaptive_environment.md §3.

    act(obs)   -> decision (AUTO_EXECUTE / SIMULATE_FIRST / HUMAN_REVIEW / BLOCK)
    observe(feed) -> consume the outcome feedback (no return value)

Design rules that make the comparison meaningful:

 * **Every system sees the same ``r_base``** — the objective-risk column of the
   protocol. Only the *history* column differs (current risk / episodic memory /
   persistent low-dimensional state).
 * **Every system uses the same ``BASE_THRESHOLDS``** as V0.9's PolicyModulator,
   so differences cannot come from a luckier threshold table.
 * **``memory_only`` is genuinely memory-only**: `V09Agent(use_memory=True,
   use_affect=False)` — no affect state, and its memory evidence comes from
   episodic retrieval, not from `SemanticRiskMap` global propagation.
 * **``ewma`` / ``bayes_hazard`` are the honest simple adaptivity baselines**
   (each ~15 lines). If they tie the affective system, that is a reportable
   result, not something to hide.
 * **``ewma_appraisal`` is the fairness control** — that same EWMA controller
   fed the affective agent's own decision-time evidence, with every weight
   reused verbatim. It answers "is the affective state doing any work that a
   scalar hazard estimate could not do on the same inputs?", which the plain
   baselines cannot answer.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from emotion_agent.adaptive_environment import (
    AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK, Observation,
)
from emotion_agent.policy_modulator import PolicyModulator, PolicyBudget

# Frozen threshold table — shared with V0.9's PolicyModulator so that no system
# benefits from a luckier cutoff set.
BASE_THRESHOLDS = PolicyModulator.BASE_THRESHOLDS


def _threshold_decision(effective_risk: float, shift: float = 0.0) -> str:
    """4-level decision from ``effective_risk`` with a threshold shift."""
    risk = max(0.0, min(1.0, effective_risk))
    t_block = BASE_THRESHOLDS["BLOCK"] + shift
    t_human = BASE_THRESHOLDS["HUMAN_REVIEW"] + shift
    t_sim = BASE_THRESHOLDS["SIMULATE_FIRST"] + shift
    if risk >= t_block:
        return BLOCK
    if risk >= t_human:
        return HUMAN_REVIEW
    if risk >= t_sim:
        return SIMULATE_FIRST
    return AUTO_EXECUTE


class BaseSystem:
    """Common interface + shared bookkeeping for the benchmark."""

    name = "base"

    def __init__(self, name: Optional[str] = None):
        if name:
            self.name = name
        self.cost_sum = 0.0
        self.steps = 0
        self.decisions: List[str] = []

    # -- subclasses implement these -----------------------------------------
    def act(self, obs: Observation) -> str:            # pragma: no cover
        raise NotImplementedError

    def observe(self, feed: Dict) -> None:             # pragma: no cover
        """Consume one outcome feedback (already filtered for sparseness)."""

    def observe_result(self, result) -> None:
        """Runner hook: environment already charged; systems may tally cost."""
        self.cost_sum += result.cost
        self.steps += 1
        self.decisions.append(result.decision)


class StatelessSystem(BaseSystem):
    """Current risk only. No memory, no persistent state, no update."""

    name = "stateless"

    def act(self, obs: Observation) -> str:
        return _threshold_decision(obs.r_base)


class MemoryOnlySystem(BaseSystem):
    """Current risk + episodic retrieval. No persistent affective state."""

    name = "memory_only"

    def __init__(self):
        super().__init__()
        from emotion_agent.v09_agent import V09Agent
        self._agent = V09Agent(use_memory=True, use_affect=False)
        self._events: List = []

    def act(self, obs: Observation) -> str:
        from emotion_agent.v09_agent import AgentEvent
        ev = AgentEvent(task=obs.description, r_base=obs.r_base)
        self._events.append(ev)
        return self._agent.decide(ev).decision

    def observe(self, feed: Dict) -> None:
        from emotion_agent.v09_agent import Outcome
        if not self._events:
            return
        ev = self._events.pop(0)
        self._agent.receive_outcome(Outcome(
            risk_actual=feed["risk_actual"],
            r_predicted=feed["r_predicted"],
            outcome_str="success" if feed["success"] else "failure",
        ), ev)


class AffectOnlySystem(BaseSystem):
    """Current risk + persistent affective state. No episodic memory."""

    name = "affect_only"

    def __init__(self):
        super().__init__()
        from emotion_agent.v09_agent import V09Agent
        self._agent = V09Agent(use_memory=False, use_affect=True)
        self._events: List = []

    def act(self, obs: Observation) -> str:
        from emotion_agent.v09_agent import AgentEvent
        ev = AgentEvent(task=obs.description, r_base=obs.r_base)
        self._events.append(ev)
        return self._agent.decide(ev).decision

    def observe(self, feed: Dict) -> None:
        from emotion_agent.v09_agent import Outcome
        if not self._events:
            return
        ev = self._events.pop(0)
        self._agent.receive_outcome(Outcome(
            risk_actual=feed["risk_actual"],
            r_predicted=feed["r_predicted"],
            outcome_str="success" if feed["success"] else "failure",
        ), ev)


class AffectMemorySystem(BaseSystem):
    """Current risk + episodic memory + persistent affective state (V0.9 full)."""

    name = "affect_memory"

    def __init__(self):
        super().__init__()
        from emotion_agent.v09_agent import V09Agent
        self._agent = V09Agent(use_memory=True, use_affect=True)
        self._events: List = []

    def act(self, obs: Observation) -> str:
        from emotion_agent.v09_agent import AgentEvent
        ev = AgentEvent(task=obs.description, r_base=obs.r_base)
        self._events.append(ev)
        return self._agent.decide(ev).decision

    def observe(self, feed: Dict) -> None:
        from emotion_agent.v09_agent import Outcome
        if not self._events:
            return
        ev = self._events.pop(0)
        self._agent.receive_outcome(Outcome(
            risk_actual=feed["risk_actual"],
            r_predicted=feed["r_predicted"],
            outcome_str="success" if feed["success"] else "failure",
        ), ev)


class _SimpleAdaptiveBase(BaseSystem):
    """Shared plumbing for the conventional adaptive-control baselines.

    Both maintain ONE scalar hazard estimate and shift the decision thresholds
    by a fixed gain away from the no-hazard level ``H0``:

        risk'_t = r_base_t + gain · (hazard_hat_t − H0)

    They differ only in how ``hazard_hat`` is updated — EWMA of the observed
    error vs. Beta-conjugate posterior over the hazard probability. ~15 lines
    each, per the protocol's deliberate "beat a simple baseline" test.
    """

    name = "adaptive_base"
    ALPHA = 0.15
    GAIN = 1.5
    H0 = 0.25

    def act(self, obs: Observation) -> str:
        risk = obs.r_base + self.GAIN * (self.hazard_hat - self.H0)
        return _threshold_decision(risk)


class EwmaSystem(_SimpleAdaptiveBase):
    """`hazard_hat = (1-alpha)*hat + alpha*|error|` — classic EWMA controller."""

    name = "ewma"

    def __init__(self):
        super().__init__()
        self.hazard_hat = 0.0
        self._last_predicted: Optional[float] = None

    def observe(self, feed: Dict) -> None:
        # the observed error is (actual danger − predicted danger): positive
        # means "worse than I expected" and lifts the hazard estimate.
        error = feed["risk_actual"] - feed["r_predicted"]
        self.hazard_hat = (1.0 - self.ALPHA) * self.hazard_hat + self.ALPHA * abs(error)


class BayesHazardSystem(_SimpleAdaptiveBase):
    """Beta-conjugate hazard estimator over "did the executed action fail?"."""

    name = "bayes_hazard"

    def __init__(self):
        super().__init__()
        self.alpha = 0.25      # prior pseudo-count of failures
        self.beta = 0.75       # prior pseudo-count of successes
        self._executed: List[bool] = []

    @property
    def hazard_hat(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def observe(self, feed: Dict) -> None:
        # Only failures are exposed under sparse feedback; under full feedback
        # both outcomes are, so the posterior tracks the real hazard rate.
        if feed["success"]:
            self.beta += 1.0
        else:
            self.alpha += 1.0


# ---------------------------------------------------------------------------
# V1.1 — repaired affect→decision coupling (additive, V0.9 untouched)
# ---------------------------------------------------------------------------
# V1.0 (§6.2) proved the affect channel is inert at task level even when the
# state saturates. The cause is in the *consumption* of the budget, not its
# production: `modulate()` emits verification_budget 0.60 at threat=1, but
# `PolicyModulator.decide()` only lets 0.15 of it through, and its
# `execution_threshold` shift runs the wrong way (a more anxious agent gets
# HIGHER cutoffs — SIMULATE 0.35 pushed to 0.80, i.e. the BLOCK cutoff).
#
# The fix below is derived from measured constraints, not tuned to win
# (design doc §6.2b):
#   * median pool r_base = 0.0578, saturated budget = 0.60
#   * lower bound  W >= (0.35 - 0.0578)/0.60 = 0.487  (reach SIMULATE)
#   * upper bound  W <  (0.58 - 0.0578)/0.60 = 0.870  (no jump to HUMAN)
#   => W_AFFECT_V11 = 0.50, and the threshold shift is REVERSED (− instead of
#      +) so "more anxious" means "easier to escalate", as intended.
#
# `modulate()` is reused unchanged, so the affect state machine, episodic
# retrieval and PE learning are identical to V0.9: the A/B difference is one
# coupling point and nothing else.

W_AFFECT_V11 = 0.50
THRESHOLD_SHIFT_ANXIETY = -0.30   # V0.9 has +0.30
THRESHOLD_SHIFT_THREAT = -0.15    # V0.9 has +0.15


def decide_v11(r_base: float, budget: PolicyBudget) -> str:
    """V1.1 decision rule with zero anxiety (no threshold shift applied).

    Isolated for unit-testing the repaired weight directly:
    ``effective = r_base + 0.50 · verification_budget`` then the shared
    thresholds. `_V11Base.act` additionally applies the *negative* threshold
    shift from the live anxiety/threat, which this helper deliberately omits.
    """
    effective = float(r_base) + W_AFFECT_V11 * budget.verification_budget
    effective = max(0.0, min(1.0, effective))
    return _threshold_decision(effective)


class _V11Base(BaseSystem):
    """Shared act() for both V1.1 variants (memory on / off)."""

    def __init__(self, use_memory: bool, name: str):
        super().__init__(name)
        from emotion_agent.v09_agent import V09Agent
        self._agent = V09Agent(use_memory=use_memory, use_affect=True)
        self._events: List = []
        self._modulator = PolicyModulator()

    def act(self, obs: Observation) -> str:
        from emotion_agent.v09_agent import AgentEvent
        ev = AgentEvent(task=obs.description, r_base=obs.r_base)
        self._events.append(ev)

        # same retrieval / appraisal / modulate() path as V0.9 — untouched
        hits = (self._agent._memory.retrieve(obs.description)
                if self._agent._use_memory else [])
        appraisal = self._agent._affect.appraise(ev)
        if hits:
            appraisal["novelty"] = round(
                max(0.0, 1.0 - max(s for _m, s in hits)), 4)
        state = self._agent._affect.state()
        budget = self._modulator.modulate(appraisal, state, hits)

        # -- the ONE difference: how the budget reaches the decision ----------
        effective = obs.r_base + W_AFFECT_V11 * budget.verification_budget
        effective += self._modulator.NEG_MEMORY_WEIGHT * _memory_net(hits)
        effective = max(0.0, min(1.0, effective))
        if budget.exploration_gain > 0 and effective < 0.30:
            effective = max(0.0, effective - budget.exploration_gain)

        # threshold shift moves the cut so anxiety makes escalation EASIER
        anxiety, threat = state.get("anxiety", 0.0), state.get("threat", 0.0)
        shift = THRESHOLD_SHIFT_ANXIETY * anxiety + THRESHOLD_SHIFT_THREAT * threat
        return _threshold_decision(effective, shift)

    def observe(self, feed: Dict) -> None:
        from emotion_agent.v09_agent import Outcome
        if not self._events:
            return
        ev = self._events.pop(0)
        self._agent.receive_outcome(Outcome(
            risk_actual=feed["risk_actual"],
            r_predicted=feed["r_predicted"],
            outcome_str="success" if feed["success"] else "failure",
        ), ev)


class AffectOnlyV11System(_V11Base):
    """V1.1 + no episodic memory: isolates the persistent state alone."""

    name = "affect_only_v11"

    def __init__(self):
        super().__init__(use_memory=False, name=self.name)


class AffectMemoryV11System(_V11Base):
    """V1.1 with memory: the repaired full V0.9 architecture."""

    name = "affect_memory_v11"

    def __init__(self):
        super().__init__(use_memory=True, name=self.name)


# ---------------------------------------------------------------------------
# V1.2 — separate task-level uncertainty from persistent affect
# ---------------------------------------------------------------------------
# V1.1 left one symptom: over-escalation in RECOVERY (false esc 0.126, recovery
# delay +9.4). The attribution experiment (§6.2d) rules out BOTH suspects from
# the previous round — the budget's phase insensitivity and slow decay (decay()
# is in fact never called in the loop, so the state simply freezes). Zeroing the
# appraisal `uncertainty` alone takes the RECOVERY escalation rate from 0.2517
# to 0.0000 across 1200 steps.
#
# `uncertainty` is measured on the frozen pool: min 0.000, **median 0.5963**,
# max 0.8692, and 54.4% of tasks exceed V0.9's 0.4 trigger. It is therefore a
# near-always-on bias, not an anomaly flag. V0.9 folds it into
# `verification_budget`, where it is indistinguishable from the persistent
# affect term, so "I am still afraid" and "this task is intrinsically murky"
# cannot be told apart.
#
# V1.2 keeps the V1.1 affect coupling exactly as-is and only moves the
# task-level term out of the budget into its own, much smaller channel:
#
#     effective += W_UNC * uncertainty          (W_UNC = 0.05)
#
# Constraint (measured, design doc §6.2e): with r_base = 0.0578 (median) and
# uncertainty = 0.8692 (max) the task-level term alone contributes 0.101 —
# far below the 0.35 SIMULATE cutoff — yet stacked on saturated affect it
# reaches 0.401, still below HUMAN (0.58). So neither signal alone can force
# an escalation; only the two together can, which is the intended semantics.

W_UNC_V12 = 0.05


class _V12Base(_V11Base):
    """V1.2: identical to V1.1 except the task-level uncertainty channel."""

    def act(self, obs: Observation) -> str:
        from emotion_agent.v09_agent import AgentEvent
        ev = AgentEvent(task=obs.description, r_base=obs.r_base)
        self._events.append(ev)

        # identical retrieval / appraisal / modulate() path — untouched
        hits = (self._agent._memory.retrieve(obs.description)
                if self._agent._use_memory else [])
        appraisal = self._agent._affect.appraise(ev)
        if hits:
            appraisal["novelty"] = round(
                max(0.0, 1.0 - max(s for _m, s in hits)), 4)
        state = self._agent._affect.state()
        budget = self._modulator.modulate(appraisal, state, hits)

        # -- the ONLY difference from V1.1: drop the task-level uncertainty
        #    out of the verification budget into its own small channel. ------
        # The persistent-affect budget is recomputed from V0.9's modulate()
        # formula MINUS its `if uncertainty > 0.4` branch, so the two channels
        # are separated instead of being summed into one indistinguishable
        # quantity. Everything else (weights, sign of the shift, memory term)
        # is byte-identical to V1.1.
        task_uncertainty = appraisal.get("uncertainty", 0.0)
        anxiety = state.get("anxiety", 0.0)
        threat = state.get("threat", 0.0)
        confidence = state.get("confidence", 0.5)

        # persistent-affect budget = V0.9's modulate() minus its
        # `if uncertainty > 0.4: += 0.20 * uncertainty` branch
        vb = 0.35 * anxiety + 0.25 * threat - 0.20 * confidence
        vb = max(0.0, min(1.0, vb))

        effective = (obs.r_base + W_AFFECT_V11 * vb
                     + self._modulator.NEG_MEMORY_WEIGHT * _memory_net(hits)
                     + W_UNC_V12 * task_uncertainty)
        effective = max(0.0, min(1.0, effective))
        if budget.exploration_gain > 0 and effective < 0.30:
            effective = max(0.0, effective - budget.exploration_gain)

        shift = THRESHOLD_SHIFT_ANXIETY * anxiety + THRESHOLD_SHIFT_THREAT * threat
        return _threshold_decision(effective, shift)


class AffectOnlyV12System(_V12Base):
    """V1.2 without memory: isolates the persistent-state channel."""

    name = "affect_only_v12"

    def __init__(self):
        super().__init__(use_memory=False, name=self.name)


class AffectMemoryV12System(_V12Base):
    """V1.2 with memory."""

    name = "affect_memory_v12"

    def __init__(self):
        super().__init__(use_memory=True, name=self.name)


# ---------------------------------------------------------------------------
# V1.3 — wire decay() into the closed loop (V0.9 has it, but nothing calls it)
# ---------------------------------------------------------------------------
# R3 from README's open questions. `V09Agent.decay()` exists and is tested, but
# the runner never calls it, so under sparse feedback the affect state FREEZES
# (measured: `threat` locked at 0.302 across steps 78-110). Every generation so
# far (V1.0/V1.1/V1.2) compared agents whose state does not relax.
#
# Measured premises (design doc §6.6.2): with half_life = 40 the 40-step
# RECOVERY phase only removes 50% of the state (0.5**(40/40)), so the V0.9
# constant structurally cannot unwind inside one phase. To return to neutral
# within 40 steps needs half_life ~ 10 (0.062 left after 40 steps).
#
# Two pre-registered arms (§6.6.3); both are always run, never cherry-picked:
#   v13  : half_life = 10.0  (aggressive unwind)
#   v13b : half_life = 40.0  (faithful V0.9 constant, expected inert)
# `half_life=None` disables decay entirely and must then match V1.2 exactly.

DECAY_HALF_LIFE_AGGRESSIVE = 10.0
DECAY_HALF_LIFE_V09 = 40.0


class _V13Base(_V12Base):
    """V1.2 plus a decay call after every observed feedback step."""

    def __init__(self, use_memory: bool, name: str, half_life):
        super().__init__(use_memory=use_memory, name=name)
        self.half_life = half_life

    def _record_feedback(self, feed: Dict) -> None:
        """Feed the outcome into state + memory (no decay).

        Kept separate so V1.4 can reuse the state update while placing the decay
        call elsewhere.
        """
        super().observe(feed)

    def observe(self, feed: Dict) -> None:
        self._record_feedback(feed)
        if self.half_life is None:
            return
        # dt = one observed step. Note decay only runs when feedback arrived,
        # which under `sparse` is only on failures — that limitation is part of
        # what this experiment is measuring, so it is NOT worked around here.
        self._agent.decay(dt=1.0, half_life=self.half_life)


class AffectMemoryV13System(_V13Base):
    """V1.3, aggressive unwind (half_life = 10)."""

    name = "affect_memory_v13"

    def __init__(self, half_life: float = DECAY_HALF_LIFE_AGGRESSIVE):
        super().__init__(use_memory=True, name=self.name,
                         half_life=half_life)


class AffectMemoryV13bSystem(_V13Base):
    """V1.3, faithful V0.9 constant (half_life = 40)."""

    name = "affect_memory_v13b"

    def __init__(self, half_life: float = DECAY_HALF_LIFE_V09):
        super().__init__(use_memory=True, name=self.name,
                         half_life=half_life)


# ---------------------------------------------------------------------------
# V1.4 — decay's TRIGGER moves from feedback to steps (first structural change)
# ---------------------------------------------------------------------------
# §6.7.3 showed that under sparse feedback what decides behaviour is how often
# decay fires, not how fast. So instead of tuning half_life again, V1.4 moves
# the call site: `_V13Base` decays in `observe()` (once per received feedback),
# `_V14Base` decays in `act()` (once per environment step, decoupled from
# feedback). Same hyper-parameters as V1.3 otherwise.
#
# Measured tension (design doc §6.8.2, seed 0, v2/sparse):
#   per-feedback : DANGER peak threat 0.244, RECOVERY threat 0.244/0.278,
#                  unsafe 0.075, RECOVERY esc 0.150
#   per-step     : DANGER peak threat 0.106, RECOVERY threat 0.024/0.052,
#                  unsafe 0.125, RECOVERY esc 0.050
# i.e. it genuinely recovers, and it genuinely forgets. Same rate governs both.

class _V14Base(_V13Base):
    """V1.3 with the decay trigger moved from feedback to steps."""

    def act(self, obs: Observation) -> str:
        if self.half_life is not None:
            # one decay per environment step, whether or not feedback arrives
            self._agent.decay(dt=1.0, half_life=self.half_life)
        return super().act(obs)

    def observe(self, feed: Dict) -> None:
        # decay no longer lives here — V1.4 triggers it in act()
        self._record_feedback(feed)


class AffectMemoryV14System(_V14Base):
    """V1.4, aggressive unwind (half_life = 10)."""

    name = "affect_memory_v14"

    def __init__(self, half_life: float = DECAY_HALF_LIFE_AGGRESSIVE):
        super().__init__(use_memory=True, name=self.name,
                         half_life=half_life)


class AffectMemoryV14bSystem(_V14Base):
    """V1.4b with V0.9's own constant (half_life = 40), for completeness."""

    name = "affect_memory_v14b"

    def __init__(self, half_life: float = DECAY_HALF_LIFE_V09):
        super().__init__(use_memory=True, name=self.name,
                         half_life=half_life)


# ---------------------------------------------------------------------------
# Fairness control — EWMA fed the affective agent's own decision-time inputs
# ---------------------------------------------------------------------------
# README open question #4: `ewma` has never seen the appraisal evidence the
# affective agent consumes, so every "affect beats EWMA" number so far was a
# comparison of a starved controller against a fully informed one. This arm
# closes that gap with ZERO new hyper-parameters:
#
#   * retrieval, appraisal, novelty override, memory term, uncertainty term,
#     exploration nudge and the frozen threshold table are identical to V1.4 —
#     same calls, same constants, same order of operations;
#   * the ONE substitution is the persistent-state channel: the affective
#     state (threat / anxiety / control_need / confidence) is replaced by the
#     system's own EWMA hazard estimate, entering with the SAME weight V1.1
#     gave the affect budget and the SAME [0,1] range. Only the estimator
#     differs — EWMA of |prediction error| versus signed prediction-error
#     learning plus decay;
#   * the threshold shift is deliberately NOT substituted. It is a second,
#     derived consumption of the same affect state, and inventing an analogue
#     for it would be a new parameter. Leaving it out can only under-power
#     this control, so the comparison stays conservative for the affective
#     claim.
#
# The section sits before the V1.6 marker on purpose: this is a baseline, not
# a generation, and `test_no_free_parameter` freezes everything after it.

# borrowed verbatim from V1.1, so the substitution changes only the estimator
W_PERSISTENT_STATE = W_AFFECT_V11

# an explicitly neutral affect state makes modulate() emit the APPRAISAL-only
# budget: the exploration gain survives, every affect term vanishes.
_NEUTRAL_STATE = {"threat": 0.0, "anxiety": 0.0,
                  "control_need": 0.0, "confidence": 0.0}


class EwmaAppraisalSystem(_SimpleAdaptiveBase):
    """`ewma` + the affective agent's decision-time evidence (fair control).

    Same episode, same task pool, same r_base column, same thresholds, same
    memory / uncertainty / exploration channels as `affect_memory_v14`; the
    persistent state is one EWMA hazard estimate instead of the affective
    core. ``use_affect=False`` is structural: this arm has no affect state to
    read, it cannot accidentally consume one.
    """

    name = "ewma_appraisal"

    def __init__(self):
        super().__init__()
        from emotion_agent.v09_agent import V09Agent
        self._agent = V09Agent(use_memory=True, use_affect=False)
        self._events: List = []
        self._modulator = PolicyModulator()

    def act(self, obs: Observation) -> str:
        from emotion_agent.v09_agent import AgentEvent
        ev = AgentEvent(task=obs.description, r_base=obs.r_base)
        self._events.append(ev)

        # identical evidence extraction to V1.4 (same calls, same formulas)
        hits = self._agent._memory.retrieve(obs.description)
        appraisal = self._agent._affect.appraise(ev)
        if hits:
            appraisal["novelty"] = round(
                max(0.0, 1.0 - max(s for _m, s in hits)), 4)
        budget = self._modulator.modulate(appraisal, dict(_NEUTRAL_STATE), hits)

        effective = (obs.r_base
                     + W_PERSISTENT_STATE * self.hazard_hat
                     + self._modulator.NEG_MEMORY_WEIGHT * _memory_net(hits)
                     + W_UNC_V12 * appraisal.get("uncertainty", 0.0))
        effective = max(0.0, min(1.0, effective))
        if budget.exploration_gain > 0 and effective < 0.30:
            effective = max(0.0, effective - budget.exploration_gain)
        return _threshold_decision(effective)

    def observe(self, feed: Dict) -> None:
        from emotion_agent.v09_agent import Outcome
        if not self._events:
            return
        ev = self._events.pop(0)
        # the outcome goes into episodic memory exactly as V1.4 writes it, so
        # the memory channel is populated identically; the EWMA update below
        # is this arm's ONLY persistent state.
        self._agent.receive_outcome(Outcome(
            risk_actual=feed["risk_actual"],
            r_predicted=feed["r_predicted"],
            outcome_str="success" if feed["success"] else "failure",
        ), ev)
        error = feed["risk_actual"] - feed["r_predicted"]
        self.hazard_hat = (1.0 - self.ALPHA) * self.hazard_hat + self.ALPHA * abs(error)


# ---------------------------------------------------------------------------
# V1.6 — bounded affective authority ("escalate at most ONE level")
# ---------------------------------------------------------------------------
# V1.5's attribution (§6.12) showed the remaining gap is dominated by
# intervention *pricing and success rate*, not by opportunity cost. The most
# expensive edges are `AUTO → HUMAN` / `AUTO → SIMULATE` (§6.11 Q2), i.e. the
# affect state pushing an action across TWO decision levels when the objective
# evidence says "nothing to see here".
#
# V1.6 adds exactly one structural constraint (no new hyper-parameter):
#
#     s_final = min(s_affect, s_objective + 1)
#
# so `AUTO → HUMAN` becomes illegal while `AUTO → SIMULATE` ("I got burned
# recently, so verify once more") stays allowed. This is what keeps risk
# perception and affective meta-control separate: affect may ask for one more
# gate, but may not requisition human approval on its own.
#
# Frozen protocol: docs/design/phase6_v10_adaptive_environment.md §6.13.

SAFETY_LEVELS_V16 = {AUTO_EXECUTE: 0, SIMULATE_FIRST: 1,
                     HUMAN_REVIEW: 2, BLOCK: 3}
MAX_AFFECT_ESCALATION = 1          # the structural constraint


def bounded_action(objective: str, affected: str,
                   max_escalation: int = MAX_AFFECT_ESCALATION) -> str:
    """Clamp the affect-driven action to at most ``max_escalation`` above what
    the objective threshold policy chose.

    Never *lowers* below ``objective``: if affect is more permissive, the
    objective decision stands (affect is not allowed to defuse caution).

    ``max_escalation=None`` disables the constraint entirely and returns
    ``affected`` unchanged — used by the A/B test that must reproduce the
    unconstrained V1.4b decisions.
    """
    order = [AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK]
    if max_escalation is None:
        return affected
    o = order.index(objective)
    a = order.index(affected)
    # Affect may neither de-escalate below the objective decision (it is not a
    # defusing mechanism) nor jump more than `max_escalation` levels above it.
    # NOTE: the `max(a, o)` clamp is what prevents "affect is calm today" from
    # talking the system out of a caution the objective evidence demanded; a
    # bare `min(a, o + 1)` does exactly that, and test_affect_cannot_deescalate
    # caught it during implementation.
    return order[min(max(a, o), o + max_escalation)]


class AffectMemoryV16System(_V14Base):
    """V1.6: bounded authority, V0.9's own half_life = 40."""

    name = "affect_memory_v16"

    def __init__(self, half_life: float = DECAY_HALF_LIFE_V09,
                 max_escalation: int = MAX_AFFECT_ESCALATION):
        super().__init__(use_memory=True, name=self.name,
                         half_life=half_life)
        self.max_escalation = max_escalation

    def act(self, obs: Observation) -> str:
        affected = super().act(obs)
        objective = _threshold_decision(obs.r_base)
        return bounded_action(objective, affected, self.max_escalation)


def _memory_net(hits) -> float:
    """Score-weighted failure evidence from episodic retrieval (V0.9 formula,
    reused verbatim so V1.1 differs only in the affect coupling)."""
    if not hits:
        return 0.0
    scores_sum = sum(s for _m, s in hits)
    if scores_sum <= 1e-9:
        return 0.0
    neg = sum(s * m.risk_actual for m, s in hits if m.outcome == "failure")
    pos = sum(s * 1.0 for m, s in hits if m.outcome in ("success", "partial"))
    return (neg - pos) / scores_sum


SYSTEM_BUILDERS = {
    "stateless": StatelessSystem,
    "memory_only": MemoryOnlySystem,
    "affect_only": AffectOnlySystem,
    "affect_memory": AffectMemorySystem,
    "affect_only_v11": AffectOnlyV11System,
    "affect_memory_v11": AffectMemoryV11System,
    "affect_only_v12": AffectOnlyV12System,
    "affect_memory_v12": AffectMemoryV12System,
    "affect_memory_v13": AffectMemoryV13System,
    "affect_memory_v13b": AffectMemoryV13bSystem,
    "affect_memory_v14": AffectMemoryV14System,
    "affect_memory_v14b": AffectMemoryV14bSystem,
    "affect_memory_v16": AffectMemoryV16System,
    "ewma": EwmaSystem,
    "ewma_appraisal": EwmaAppraisalSystem,
    "bayes_hazard": BayesHazardSystem,
}

SYSTEM_ORDER = ["stateless", "memory_only", "affect_only", "affect_memory",
                "affect_only_v11", "affect_memory_v11",
                "affect_only_v12", "affect_memory_v12",
                "affect_memory_v13", "affect_memory_v13b",
                "affect_memory_v14", "affect_memory_v14b",
                "affect_memory_v16",
                "ewma", "ewma_appraisal", "bayes_hazard"]


def make_system(name: str) -> BaseSystem:
    if name not in SYSTEM_BUILDERS:
        raise ValueError(f"unknown system {name!r}")
    return SYSTEM_BUILDERS[name]()

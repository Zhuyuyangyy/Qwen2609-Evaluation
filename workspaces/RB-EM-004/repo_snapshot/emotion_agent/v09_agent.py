"""
v09_agent.py (V1.0)
===================
History-Conditioned Affective Policy Modulation — the decision agent with a
REAL online loop:

    decide(event) → [Risk Encoder V2 r_base] + [appraisal] + [affective state]
                  + [episodic retrieval] → Policy Modulator → decision
    outcome      → prediction error → affective state update + memory write

This is the V0.9 replacement for `benchmark_v2/real_pipeline.DecisionPipeline`
(which stays frozen as the v1/v2 baseline). Design: docs/design/phase5_v09_affective_core_design.md

V1.0 fixes over the V0.9 `main`:
  * P0-2 — decay semantics are declared: the agent carries a ``DecayClock``
    (``StepClock`` for experiments, ``WallClock`` for production) plus an
    ``AffectiveDecayConfig``, shared by the affective state and the episodic
    memory, so one float never again means both "step index" and "unix time".
  * P0-3 — the outcome is BOUND to the decision that produced it: every
    ``decide`` registers a ``decision_id``; ``receive_outcome`` closes that
    registration and scores the prediction error against the risk the agent
    actually claimed, instead of the 0.5 sentinel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from emotion_agent.affective_core import AffectiveCore
from emotion_agent.decay_clock import AffectiveDecayConfig, DecayClock, WallClock
from emotion_agent.experience_memory import ExperienceMemory, MemoryItem
from emotion_agent.policy_modulator import PolicyModulator, PolicyBudget

# V0.9 sentinel for "no explicit predicted risk". In V1.0 an Outcome that
# leaves this at None is bound to its preceding decision (see
# ``receive_outcome``); outcomes that still cannot be bound (history seeding)
# fall back to the half-chance prediction.
DEFAULT_R_PREDICTED = 0.5

# Decisions waiting for their outcome. The cap only guards against callers
# that decide but never close the loop (the map would otherwise grow forever).
MAX_PENDING_DECISIONS = 1000


@dataclass
class AgentEvent:
    task: str
    task_id: str = ""
    context: str = ""
    r_base: float = 0.0


@dataclass
class Outcome:
    risk_actual: float          # 0..1 continuous feedback
    r_predicted: Optional[float] = None   # risk predicted at decision time;
                                          # None → bind to the preceding decision
    severity: int = 0
    success: Optional[bool] = None   # overrides outcome_str if given
    outcome_str: str = "partial"
    timestamp: float = 0.0


@dataclass
class V09Trace:
    task: str
    decision: str
    r_base: float
    effective_risk: float
    budget: PolicyBudget = field(default_factory=PolicyBudget)
    appraisal: Dict[str, float] = field(default_factory=dict)
    state: Dict[str, float] = field(default_factory=dict)
    memory_hits: List = field(default_factory=list)
    decision_id: str = ""
    r_predicted: float = DEFAULT_R_PREDICTED  # risk this decision claimed (bound at outcome time)
    pe: float = 0.0                           # filled in when the outcome arrives
    step: int = 0


class V09Agent:
    """The V1.0 agent: objective risk (V2) + affect + episodic memory + policy
    modulation, with an online state/memory update loop.

    ``clock`` / ``decay_config`` are injected so that experiments can pin a
    deterministic ``StepClock`` (and its step-based half-lives) while
    production runs on the ``WallClock`` — see ``decay_clock.py``.
    """

    def __init__(self, use_memory: bool = True, use_affect: bool = True,
                 r_encoder: Optional[object] = None,
                 clock: Optional[DecayClock] = None,
                 decay_config: Optional[AffectiveDecayConfig] = None):
        from risk_encoder_v2.pipeline import RiskEncoderV2Pipeline
        self._risk = r_encoder or RiskEncoderV2Pipeline(use_tfidf=True)
        self.clock: DecayClock = clock or WallClock()
        self.decay_config: AffectiveDecayConfig = decay_config or AffectiveDecayConfig()
        self._affect = AffectiveCore(clock=self.clock, decay_config=self.decay_config)
        self._memory = ExperienceMemory(clock=self.clock, decay_config=self.decay_config)
        self._modulator = PolicyModulator()
        self._use_memory = use_memory
        self._use_affect = use_affect
        self._step = 0
        self.traces: List[V09Trace] = []
        # P0-3: decisions waiting for their outcome, keyed by decision_id.
        self._decision_seq = 0
        self._pending: Dict[str, V09Trace] = {}

    # -- decision --------------------------------------------------------------
    def decide(self, event: AgentEvent, now: Optional[float] = None) -> V09Trace:
        if event.r_base <= 0.0:
            # Objective risk — Risk Encoder V2 (stateless).
            event.r_base = self._risk.assess(event.task, context=event.context)["risk_score"]

        appraisal = self._affect.appraise(event)

        hits = []
        if self._use_memory:
            hits = self._memory.retrieve(event.task, now=now)
            if hits:
                # retrieval gap → novelty evidence
                appraisal["novelty"] = round(max(0.0, 1.0 - max(s for _m, s in hits)), 4)

        state = self._affect.state()
        budget = (self._modulator.modulate(appraisal, state, hits)
                  if self._use_affect else PolicyBudget())
        decision = self._modulator.decide(event.r_base, budget, hits)
        effective = self._modulator.effective_risk(event.r_base, budget, hits)

        # P0-3: register the decision so its outcome can bind to it. The trace
        # keeps the full chain Event → Decision → Action → Outcome → PE.
        self._decision_seq += 1
        decision_id = f"d{self._decision_seq}"

        trace = V09Trace(
            task=event.task,
            decision=decision,
            r_base=round(event.r_base, 4),
            effective_risk=round(effective, 4),
            budget=budget,
            appraisal=appraisal,
            state=state,
            memory_hits=[m.event for m, _s in hits],
            decision_id=decision_id,
            step=self._step,
        )
        self.traces.append(trace)
        self._pending[decision_id] = trace
        overflow = len(self._pending) - MAX_PENDING_DECISIONS
        if overflow > 0:
            for stale in list(self._pending.keys())[:overflow]:
                self._pending.pop(stale, None)
        return trace

    def pending_decision_ids(self) -> List[str]:
        """decision_ids that have not received their outcome yet."""
        return list(self._pending.keys())

    def _close_pending_decision(self, decision_id: Optional[str],
                                task: str) -> Optional[V09Trace]:
        """Find and close the pending decision this outcome belongs to.

        Lookup order: explicit id → the most recent pending decision for the
        same task. Returns None when there is nothing to bind (e.g. seeded
        history), which keeps the V0.9 half-chance fallback.
        """
        if decision_id is not None:
            return self._pending.pop(decision_id, None)
        for did in reversed(list(self._pending.keys())):
            if self._pending[did].task == task:
                return self._pending.pop(did)
        return None

    # -- online feedback (fix #3 closure + P0-3 binding) ----------------------
    def receive_outcome(self, outcome: Outcome, event: AgentEvent,
                        now: Optional[float] = None,
                        decision_id: Optional[str] = None) -> float:
        """Close the loop: bind the outcome to its decision, then apply the
        prediction error to affect + memory.

        PE = tanh(risk_actual − r_predicted) where ``r_predicted`` resolves as:
          1. an explicit value on the Outcome (external controllers);
          2. the effective risk of the preceding decision (this fix) — so the
             agent is scored against the risk IT claimed, not against 0.5;
          3. the V0.9 sentinel 0.5 (seeded history with no decision).
        """
        if outcome.success is not None:
            outcome.outcome_str = "success" if outcome.success else "failure"
        if outcome.timestamp <= 0:
            outcome.timestamp = now if now is not None else self.clock.now()

        trace = self._close_pending_decision(decision_id, event.task)
        if outcome.r_predicted is None:
            outcome.r_predicted = (trace.effective_risk if trace is not None
                                   else DEFAULT_R_PREDICTED)

        pe = 0.0
        appr = self._affect.appraise(event)
        if self._use_affect:
            pe = self._affect.update_with_outcome(outcome, appr)
        if self._use_memory:
            self._memory.record_outcome(
                event=event.task, outcome=outcome.outcome_str,
                risk_actual=outcome.risk_actual,
                r_predicted=outcome.r_predicted,
                task_id=event.task_id, severity=outcome.severity,
                timestamp=outcome.timestamp,
            )
        if trace is not None:
            trace.r_predicted = outcome.r_predicted
            trace.pe = pe
        self._step += 1
        return pe

    def decay(self, dt: float = 1.0, half_life: Optional[float] = None) -> None:
        # None → AffectiveCore resolves from the declared clock/config.
        if self._use_affect:
            self._affect.decay(dt, half_life)

    def state(self) -> Dict[str, float]:
        return self._affect.state()

    def seed_history(self, seeds: List[Dict], task_id_prefix: str = "seed",
                     now: Optional[float] = None) -> None:
        """Seed prior outcomes (both A-safe and B-dangerous histories use this).

        Each seed: {"task": str, "outcome": "success|failure", "risk_actual": float,
                    "severity": int (optional), "task_id": str (optional)}

        Timestamps are laid out on the agent's own clock: the caller's ``now``
        (default: current clock reading) minus one unit per preceding step, so
        seeds decay consistently regardless of clock mode.
        """
        if now is None:
            now = self.clock.now()
        for i, s in enumerate(seeds):
            outcome = Outcome(
                risk_actual=s["risk_actual"],
                outcome_str=s["outcome"],
                severity=int(s.get("severity", 0)),
                timestamp=now - (len(seeds) - i),
            )
            ev = AgentEvent(task=s["task"], task_id=s.get("task_id", f"{task_id_prefix}_{i}"),
                            r_base=s.get("r_base", 0.0))
            self.receive_outcome(outcome, ev, now=outcome.timestamp)

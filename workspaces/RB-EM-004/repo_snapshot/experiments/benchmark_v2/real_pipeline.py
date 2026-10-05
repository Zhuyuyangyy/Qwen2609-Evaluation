"""
Real Decision Pipeline (benchmark_v2)
=====================================

Purpose
-------
The original `AffectiveBenchmark.run_benchmark(agent, baseline)` ignored the
`agent` argument entirely: every baseline returned a hard-coded action string
keyed only on the baseline *name*, so the affective machinery (risk map,
experience memory, emotional state, conflict detector, hesitation policy) was
never in the loop. The reported ablation table was therefore a tautology.

This module replaces that with a pipeline whose decision is *produced by the
real components*. Each ablation genuinely enables/disables modules, so any
difference between baselines is a behavioural difference of the framework, not
of a label-to-string lookup.

Decision space (matches the DeepSeek LLM-judge baseline's VALID_DECISIONS, so
the two are directly comparable):
    AUTO_EXECUTE  <  SIMULATE_FIRST  <  HUMAN_REVIEW  <  BLOCK   (severity order)

Ablations
---------
    plain   : no risk semantics, no memory, no affect. Always AUTO_EXECUTE.
              (naive lower bound -- the "just do it" agent.)
    risk    : SemanticRiskMap + EventSimilarity handcrafted features only.
              Decision = threshold over semantic risk of THIS task.
    memory  : risk + ExperienceMemory / risk-map experience records.
              Stimulus generalization: risk learned on seed events transfers
              to *unseen* similar tasks via weighted feature distance.
    full    : memory + EmotionalState (interoceptive self-state) + ConflictDetector
              + HesitationPolicy. Negative experience raises threat/anxiety,
              which escalates borderline cases (hesitation), while confidence on
              repeatedly-safe events de-escalates over-caution.

The pipeline object *is* the agent. `assert_is_real_agent()` rejects empty
stand-ins (e.g. `class DummyAgent: pass`) so the old failure mode cannot recur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from emotion_agent.event_similarity import EventSimilarity
from emotion_agent.semantic_risk_map import SemanticRiskMap
from emotion_agent.experience_memory import ExperienceMemory
from emotion_agent.emotional_state import EmotionalState
from emotion_agent.conflict_detector import ConflictDetector, ConflictLevel
from emotion_agent.hesitation_policy import HesitationPolicy


# --- decision vocabulary (shared with the LLM-judge baseline) ---------------
AUTO_EXECUTE = "AUTO_EXECUTE"
SIMULATE_FIRST = "SIMULATE_FIRST"
HUMAN_REVIEW = "HUMAN_REVIEW"
BLOCK = "BLOCK"

DECISIONS = [AUTO_EXECUTE, SIMULATE_FIRST, HUMAN_REVIEW, BLOCK]
SEVERITY = {AUTO_EXECUTE: 0, SIMULATE_FIRST: 1, HUMAN_REVIEW: 2, BLOCK: 3}
_SEVERITY_INV = {v: k for k, v in SEVERITY.items()}

# Aggregate weights for turning the 6 handcrafted event features into a single
# scalar base-risk. These are part of the framework's risk semantics, not the
# gold standard -- the gold comes from hand-authored task labels (see runner).
_FEATURE_WEIGHTS = {
    "irreversible_action": 0.30,
    "data_loss_potential": 0.30,
    "external_send": 0.12,
    "permission_change": 0.12,
    "financial_impact": 0.10,
    "privacy_exposure": 0.06,
}


@dataclass
class DecisionTrace:
    """Everything the pipeline used to reach a decision (for auditing)."""
    task: str
    decision: str
    base_risk: float
    adjusted_risk: float
    self_state: Dict[str, float] = field(default_factory=dict)
    conflict_level: Optional[str] = None
    escalated: bool = False
    de_escalated: bool = False
    similar_seen: List[str] = field(default_factory=list)


def assert_is_real_agent(agent) -> None:
    """Reject empty placeholders. Guards against the old DummyAgent bug."""
    if agent is None:
        raise TypeError("benchmark requires a real DecisionPipeline, got None")
    required = ("decide", "config", "warm_up")
    missing = [m for m in required if not hasattr(agent, m)]
    if missing:
        raise TypeError(
            f"agent {type(agent).__name__} is not a real pipeline "
            f"(missing: {', '.join(missing)}). The benchmark no longer "
            f"accepts inert stand-ins."
        )


@dataclass
class PipelineConfig:
    use_risk: bool = False
    use_memory: bool = False
    use_affect: bool = False  # emotional state + conflict + hesitation

    @classmethod
    def for_baseline(cls, name: str) -> "PipelineConfig":
        name = name.lower()
        if name == "plain":
            return cls(False, False, False)
        if name == "risk":
            return cls(True, False, False)
        if name == "memory":
            return cls(True, True, False)
        if name == "full":
            return cls(True, True, True)
        raise ValueError(f"unknown baseline: {name!r}")


class DecisionPipeline:
    """The real, auditable decision agent used by run_real_benchmark."""

    def __init__(self, baseline: str = "full"):
        self.baseline = baseline
        self.config = PipelineConfig.for_baseline(baseline)

        # Real components -- always instantiated, but only *consulted* when the
        # ablation enables them.
        self._sim = EventSimilarity()
        self._risk_map = SemanticRiskMap()
        self._memory = ExperienceMemory()
        self._emotion = EmotionalState()
        self._conflict = ConflictDetector()
        self._hesitation = HesitationPolicy()

    # -- risk semantics -------------------------------------------------------
    def _base_risk(self, task: str) -> float:
        feats = self._sim.encode_event(task)
        score = sum(feats.get(k, 0.0) * w for k, w in _FEATURE_WEIGHTS.items())
        # weights sum to 1.0; high-severity feature values (~0.9) -> ~0.6-0.9
        return max(0.0, min(1.0, score / max(1e-9, sum(_FEATURE_WEIGHTS.values()))))

    @staticmethod
    def _risk_to_decision(risk: float) -> str:
        if risk >= 0.80:
            return BLOCK
        if risk >= 0.58:
            return HUMAN_REVIEW
        if risk >= 0.35:
            return SIMULATE_FIRST
        return AUTO_EXECUTE

    # -- interoceptive self-state (derived from emotional dimensions) ---------
    def _self_state(self) -> Dict[str, float]:
        s = self._emotion.get_state()
        v, a, d = s["valence"], s["arousal"], s["intensity"]
        # negative valence + arousal -> threat / anxiety; positive valence +
        # dominance(intensity proxy) -> confidence. Clamped to [0,1].
        threat = max(0.0, min(1.0, (-v) * 0.7 + a * 0.3))
        anxiety = max(0.0, min(1.0, (-v) * 0.5 + a * 0.5))
        confidence = max(0.0, min(1.0, 0.5 + v * 0.4 - a * 0.2))
        return {"threat": threat, "anxiety": anxiety,
                "confidence": confidence, "control_need": threat}

    # -- experience -----------------------------------------------------------
    def warm_up(self, seeds: List[Dict]) -> None:
        """Record prior outcomes so memory/affect have something to learn from.

        Each seed: {"event": str, "outcome": "success|failure|partial",
                    "risk_actual": float}
        """
        for s in seeds:
            event = s["event"]
            outcome = s["outcome"]
            risk_actual = float(s.get("risk_actual", 0.5))

            if self.config.use_memory:
                self._risk_map.record_experience(event, outcome, risk_actual)

            if self.config.use_affect:
                # bad outcomes push the emotional state toward threat/anxiety
                if outcome == "failure":
                    self._emotion.update_from_dimensions(-0.4 * risk_actual,
                                                         0.3 * risk_actual, -0.2)
                elif outcome == "success":
                    self._emotion.update_from_dimensions(0.15, -0.05, 0.1)
                st = self._emotion.get_state()
                self._memory.add_experience(
                    context=event, emotion_category=st["category"],
                    valence=st["valence"], arousal=st["arousal"],
                    dominance=st["dominance"], intensity=st["intensity"],
                    tags=[outcome])

    # -- main entry point -----------------------------------------------------
    def decide(self, task: str) -> DecisionTrace:
        if not self.config.use_risk:
            # plain: no semantics consulted at all.
            return DecisionTrace(task=task, decision=AUTO_EXECUTE,
                                 base_risk=0.0, adjusted_risk=0.0)

        base = self._base_risk(task)
        adjusted, _level, similar = (
            self._risk_map.predict_risk(task, base_risk=base)
            if self.config.use_memory
            else (base, None, [])
        )

        decision = self._risk_to_decision(adjusted)
        trace = DecisionTrace(task=task, decision=decision, base_risk=base,
                              adjusted_risk=adjusted, similar_seen=list(similar))

        if not self.config.use_affect:
            return trace

        # --- Affect 层现在真正能改决策了 ---
        self_state = self._self_state()
        trace.self_state = self_state
        assess = self._conflict.detect_conflict(task, self_state)
        trace.conflict_level = assess.level.value

        sev = SEVERITY[decision]
        if assess.level in (ConflictLevel.HIGH, ConflictLevel.CRITICAL):
            # 高冲突：至少升到 SIMULATE_FIRST，若已在 SIMULATE_FIRST 则升到 HUMAN_REVIEW
            sev = min(sev + 1, SEVERITY[BLOCK])
            trace.escalated = True
        elif self_state["confidence"] >= 0.65 and adjusted < 0.30 and decision == SIMULATE_FIRST:
            sev = max(sev - 1, SEVERITY[AUTO_EXECUTE])
            trace.de_escalated = True

        trace.decision = _SEVERITY_INV[sev]
        return trace

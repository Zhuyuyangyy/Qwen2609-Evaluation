"""
dual_scale_state.py (V1.0 - P1-a)
==================================
Fast / slow dual time-scale affective state.

Problem this fixes: the P0 affective core is a *fast* system — valence,
arousal, threat and confidence move within one interaction (half-life:
minutes to hours). But the roadmap also requires *stable* traits that
accumulate over days/weeks and must NOT be flipped by a single event:

  * interaction_trust      — does the human's feedback tend to match what
                             actually happened?  (rises on small |PE|)
  * uncertainty_baseline   — how surprising is this world, on average?
                             (rises on large |PE|)
  * proactivity_tolerance  — how much unsolicited outreach is tolerated?
                             (driven by accepted / ignored proactive moves)
  * control_preference     — how much human oversight does this human want?
                             (rises after failures / irreversible actions)

Dynamics (roadmap):

    fast_t+1 = α · fast_t + β · prediction_error
    slow_t+1 = γ · slow_t + δ · aggregated_experience      with α < γ , δ << β

Mapping choice: the fast scale IS the P0 :class:`AffectiveCore`
(β = LEARNING_RATE = 0.30, α = the declared decay clock).  This module
adds the slow scale and the evidence gate between them.  A raw additive
``slow += δ·E`` would integrate straight out of [0, 1], so the slow state
is implemented as an evidence-weighted *estimate* (a posterior) with the
same two parameters kept visible:

  * γ (GAMMA_SLOW) forgets old evidence on every aggregated update;
  * δ (DELTA_SLOW = 1 / PRIOR_WEIGHT) is the maximum per-event influence —
    a single "嗯" (one weak signal) can shift a slow dimension by at most
    DELTA_SLOW = 0.125, versus β = 0.30 for the fast scale (δ << β).

Evidence gating: a slow dimension only leaves its neutral baseline after
enough *accumulated* evidence (prior weight counts as the first
EVIDENCE_PER_UPDATE units), so no single interaction can rewrite the
agent's stable traits.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

from emotion_agent.affective_core import AffectiveCore
from emotion_agent.decay_clock import (
    AffectiveDecayConfig,
    DecayClock,
    WallClock,
)
from emotion_agent.emotional_state import EmotionalState


# Neutral baselines ([0, 1]) for every slow dimension.
NEUTRAL_SLOW = {
    "interaction_trust": 0.5,
    "uncertainty_baseline": 0.5,
    "proactivity_tolerance": 0.5,
    "control_preference": 0.5,
}

SLOW_DIMENSIONS: List[str] = list(NEUTRAL_SLOW)

# Prediction risk assumed when none was declared (kept in sync with the
# P0-3 fallback in affective_core / v09_agent).
R_PREDICTED_DEFAULT = 0.5


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Clamp a value into [low, high]."""
    return max(low, min(high, float(value)))


@dataclass(frozen=True)
class ExperienceSample:
    """One aggregated experience fed to the dual-scale state.

    Duck-type compatible with the ``Outcome`` accepted by
    :meth:`AffectiveCore.update_with_outcome` (``risk_actual`` /
    ``r_predicted`` / ``outcome_str``), so the same sample drives both
    scales without a second representation of the same event.
    """

    risk_actual: float
    r_predicted: Optional[float] = None
    outcome_str: str = "neutral"
    #: True when the event changed the world irreversibly (raises the
    #: demand for human oversight).
    irreversible: bool = False
    #: Optional interaction-level signal: did the human accept the last
    #: proactive outreach?  ``None`` = no proactive move happened, no
    #: proactivity evidence deposited.
    proactive_accepted: Optional[bool] = None
    #: Evidence weight; weak chatter ("嗯") should use < 1.0.
    weight: float = 1.0

    def prediction_error(self,
                         default_r: float = R_PREDICTED_DEFAULT) -> float:
        """Continuous prediction error, identical formula to the fast core."""
        r = self.r_predicted if self.r_predicted is not None else default_r
        return math.tanh(float(self.risk_actual) - float(r))


@dataclass(frozen=True)
class DualScaleDecayConfig(AffectiveDecayConfig):
    """Decay half-lives extended with the *slow* scale (days to weeks)."""

    slow_half_life_seconds: float = 14 * 86400.0   # 14 days, production
    slow_half_life_steps: float = 200.0            # 200 steps, experiments
    #: step-mode slow state must outlive the 40-step fast state by a wide
    #: margin (α < γ), otherwise the two scales collapse into one.

    def half_life(self, kind: str, mode: str) -> float:
        if kind == "slow":
            return (self.slow_half_life_steps if mode == "step"
                    else self.slow_half_life_seconds)
        return super().half_life(kind, mode)


@dataclass
class SlowState:
    """Stable traits — days/weeks scale, every field in [0, 1]."""

    interaction_trust: float = NEUTRAL_SLOW["interaction_trust"]
    uncertainty_baseline: float = NEUTRAL_SLOW["uncertainty_baseline"]
    proactivity_tolerance: float = NEUTRAL_SLOW["proactivity_tolerance"]
    control_preference: float = NEUTRAL_SLOW["control_preference"]

    def snapshot(self) -> Dict[str, float]:
        return {dim: round(getattr(self, dim), 4) for dim in SLOW_DIMENSIONS}

    def to_dict(self) -> Dict[str, float]:
        return {dim: _clamp(getattr(self, dim)) for dim in SLOW_DIMENSIONS}

    @classmethod
    def from_dict(cls, data: Dict[str, float]) -> "SlowState":
        known = {k: v for k, v in (data or {}).items() if k in NEUTRAL_SLOW}
        return cls(**{dim: _clamp(known.get(dim, NEUTRAL_SLOW[dim]))
                      for dim in SLOW_DIMENSIONS})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> "SlowState":
        return cls.from_dict(json.loads(json_str))


class DualScaleAffectiveState:
    """Fast (P0 affective core) + slow (stable traits) on one clock."""

    # Fast scale (mirrors the P0 core; kept here for documentation/audit).
    BETA_FAST = AffectiveCore.LEARNING_RATE      # 0.30
    # Slow scale (roadmap parameters).
    GAMMA_SLOW = 0.98                           # per aggregated update
    PRIOR_WEIGHT = 8.0                          # evidence needed to matter
    DELTA_SLOW = 1.0 / PRIOR_WEIGHT             # 0.125 << β (δ << β)
    SURPRISE_TOLERANCE = 0.25                   # |pe| counted as "surprising"

    def __init__(self,
                 clock: Optional[DecayClock] = None,
                 decay_config: Optional[DualScaleDecayConfig] = None,
                 fast_core: Optional[AffectiveCore] = None):
        self.clock: DecayClock = clock or WallClock()
        self.decay_config: DualScaleDecayConfig = decay_config or DualScaleDecayConfig()
        # Fast scale: the P0 core, sharing the declared clock and config.
        self.fast: AffectiveCore = fast_core or AffectiveCore(
            clock=self.clock, decay_config=self.decay_config)
        self.slow = SlowState()
        # Posterior weights per slow dimension (prior counts as evidence);
        # weighted signal sums normalized by these weights give the state.
        self._evidence: Dict[str, float] = {d: self.PRIOR_WEIGHT for d in SLOW_DIMENSIONS}
        self._signal: Dict[str, float] = {
            d: self.PRIOR_WEIGHT * NEUTRAL_SLOW[d] for d in SLOW_DIMENSIONS}
        self._slow_updates = 0
        self._last_update_clock: Optional[float] = None

    # -- evidence gate ---------------------------------------------------------
    def evidence_strength(self, dim: str) -> float:
        """How much evidence (vs. the prior) supports a slow dimension.

        ``1.0`` = never left the prior (no information); grows as real
        experience accumulates.  Used by tests and by the gate: slow state
        should only modulate behaviour for well-supported dimensions.
        """
        if dim not in self._evidence:
            raise ValueError(f"unknown slow dimension: {dim!r}")
        return self._evidence[dim] / self.PRIOR_WEIGHT

    # -- update ----------------------------------------------------------------
    def slow_signals(self, sample: ExperienceSample) -> Dict[str, Optional[float]]:
        """Evidence-implied level ([0, 1]) per slow dimension.

        ``None`` means "no evidence from this sample" (e.g. a non-proactive
        event says nothing about proactivity_tolerance).
        """
        pe = sample.prediction_error()
        failure = sample.outcome_str.strip().lower() in (
            "failure", "fail", "error", "rejected")
        signals: Dict[str, Optional[float]] = {
            # Human feedback that matches reality ("trustworthy world").
            "interaction_trust": _clamp(0.5 - pe),
            # How wrong the agent tends to be.
            "uncertainty_baseline": _clamp(abs(pe) / self.SURPRISE_TOLERANCE),
            # Bad news + irreversible acts => human wants more oversight.
            "control_preference": _clamp(
                0.5 + 0.5 * pe + (0.25 if failure else 0.0)
                + (0.15 if sample.irreversible else 0.0)),
            # Only explicit proactive outcomes carry proactivity evidence.
            "proactivity_tolerance": (
                (1.0 if sample.proactive_accepted else 0.0)
                if sample.proactive_accepted is not None else None),
        }
        return signals

    def observe(self,
                sample: ExperienceSample,
                appraisal: Optional[Dict[str, float]] = None) -> Dict[str, object]:
        """Apply one experience to BOTH scales; returns an audit dict.

        Fast scale: immediate PE update (β).
        Slow scale: deposits evidence into the posterior; the trait only
        moves once accumulated evidence outweighs the prior (δ << β), so
        one weak signal cannot rewrite a stable trait.
        """
        # -- fast scale (P0 core) --
        pe_fast = self.fast.update_with_outcome(sample, appraisal)

        # -- slow scale (evidence-gated posterior) --
        weight = max(0.0, float(sample.weight))
        if weight > 0.0:
            for dim, signal in self.slow_signals(sample).items():
                if signal is None:
                    continue
                # γ: older evidence gradually loses pull.
                self._evidence[dim] = self.GAMMA_SLOW * self._evidence[dim] + weight
                self._signal[dim] = self.GAMMA_SLOW * self._signal[dim] + weight * signal
                setattr(self.slow, dim,
                        _clamp(self._signal[dim] / self._evidence[dim]))
            self._slow_updates += 1
            self._last_update_clock = self.clock.now()

        return {
            "pe": round(pe_fast, 4),
            "fast": self.fast.state(),
            "slow": self.slow.snapshot(),
        }

    # -- decay -----------------------------------------------------------------
    def decay(self, dt: float = 1.0) -> None:
        """Drift both scales toward neutral on their own time scales.

        Fast state uses the P0 core's declared state half-life (40 steps /
        6 h).  Slow state relaxes toward its neutral baseline with the slow
        half-life (200 steps / 14 days), and accumulated evidence weakens
        with it — old beliefs fade instead of persisting forever.
        """
        self.fast.decay(dt)  # resolves the state half-life from the clock

        factor = 0.5 ** (float(dt) / max(
            1e-9, self.decay_config.half_life("slow", self.clock.mode)))
        for dim in SLOW_DIMENSIONS:
            neutral = NEUTRAL_SLOW[dim]
            # state relaxes toward neutral ...
            state = getattr(self.slow, dim)
            setattr(self.slow, dim, _clamp(neutral + (state - neutral) * factor))
            # ... and the evidence backing it decays toward the prior.
            ev = self._evidence[dim]
            self._evidence[dim] = self.PRIOR_WEIGHT + (ev - self.PRIOR_WEIGHT) * factor
            sig = self._signal[dim]
            target_sig = self.PRIOR_WEIGHT * neutral
            self._signal[dim] = target_sig + (sig - target_sig) * factor

    # -- audit -----------------------------------------------------------------
    def snapshot(self) -> Dict[str, object]:
        """Full dual-scale snapshot (benchmark / trajectory logging)."""
        return {
            "fast": self.fast.state(),
            "slow": self.slow.snapshot(),
            "evidence": {d: round(self.evidence_strength(d), 4)
                         for d in SLOW_DIMENSIONS},
            "slow_updates": self._slow_updates,
        }

    # -- persistence -------------------------------------------------------------
    def to_dict(self) -> Dict[str, object]:
        return {
            "slow": self.slow.to_dict(),
            "evidence": dict(self._evidence),
            "signal": dict(self._signal),
            "slow_updates": self._slow_updates,
            "fast": self.fast.raw_emotion().get_state(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object],
                  clock: Optional[DecayClock] = None,
                  decay_config: Optional[DualScaleDecayConfig] = None) -> "DualScaleAffectiveState":
        obj = cls(clock=clock, decay_config=decay_config)
        obj.slow = SlowState.from_dict(data.get("slow") or {})  # type: ignore[arg-type]
        for dim in SLOW_DIMENSIONS:
            obj._evidence[dim] = float((data.get("evidence") or {}).get(
                dim, obj.PRIOR_WEIGHT))
            obj._signal[dim] = float((data.get("signal") or {}).get(
                dim, obj.PRIOR_WEIGHT * NEUTRAL_SLOW[dim]))
        obj._slow_updates = int(data.get("slow_updates", 0))
        # Fast scale: only the dimension levels are stable enough to carry
        # across a restart; the arousal/threat component decays on its own.
        fast = data.get("fast") or {}
        if fast:
            target = obj.fast.raw_emotion()
            target.valence = float(fast.get("valence", 0.0))
            target.arousal = float(fast.get("arousal", 0.0))
            target.dominance = float(fast.get("dominance", 0.0))
            target.intensity = float(fast.get("intensity", 0.0))
        return obj

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, json_str: str,
                  clock: Optional[DecayClock] = None,
                  decay_config: Optional[DualScaleDecayConfig] = None) -> "DualScaleAffectiveState":
        return cls.from_dict(json.loads(json_str), clock=clock,
                             decay_config=decay_config)

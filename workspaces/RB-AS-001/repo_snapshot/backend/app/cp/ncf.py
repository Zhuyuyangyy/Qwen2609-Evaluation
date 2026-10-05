"""Nonconformity functions (NCF) for the AgentShield V3 conformal layer.

An NCF measures *how non-conforming* a candidate action is for a given tool
call.  Lower score = the action is more plausible given the observed risk
profile.  ``ConformalPredictor`` (see :mod:`app.cp.core`) calibrates a
threshold ``q`` on historical decisions and then outputs the *set* of actions
whose nonconformity score is ``<= q``::

    C(x) = { y : NCF(x, y) <= q_hat }

Because ``q`` is a finite-sample quantile of the calibration scores, the
resulting sets enjoy a distribution-free marginal coverage guarantee
``P(true_action in C(x)) >= 1 - alpha`` under exchangeability between the
calibration set and deployment traffic.

Three NCFs are provided, ordered by increasing richness:

``ScoreBasedNCF``
    Uses only the raw risk score.  Maps ALLOW/HUMAN_REVIEW/BLOCK onto the
    0/1/2 severity lattice and scores a candidate action by how far the
    observed risk sits from that action's reference risk band.
``BehaviorGraphNCF``
    Extends the score-based NCF with behavior-graph signals (inherited risk
    from upstream nodes, node degree, chain length).  This is the NCF that
    makes V3 *chain-aware*: risk inherited along a delegation chain pushes
    the conformal set towards stronger governance even when the local score
    is unremarkable.
``AdaptiveNCF``
    Wraps :class:`ScoreBasedNCF` with an online Adaptive Conformal
    Inference (ACI) update, so the effective significance level drifts to
    track distribution shift instead of staying fixed after calibration.
"""

from __future__ import annotations

import math
from typing import Any, ClassVar, Dict, List, Optional, Sequence

from app.cp.core import (
    ACTION_LABELS,
    CalibrationItem,
    NonconformityFunction,
)

# ─── Label lattice shared with app.cp.core ──────────────────────────────────
# Governance actions ordered by severity.  Re-exported so that callers can use
# ``app.cp`` as a single import surface.

#: Candidate action labels, ordered from least to most severe.
CROSS_ENTROPY_LABELS: List[str] = list(ACTION_LABELS)

#: Label -> severity index (ALLOW=0, HUMAN_REVIEW=1, BLOCK=2).
ACTION_LABEL_TO_IDX: Dict[str, int] = {a: i for i, a in enumerate(ACTION_LABELS)}

#: Severity index -> label.
IDX_TO_ACTION: Dict[int, str] = {i: a for i, a in enumerate(ACTION_LABELS)}

# Severity index of each action label (unknown labels map to the review
# position so they never silently collapse onto ALLOW).
_DEFAULT_LABEL_IDX = ACTION_LABEL_TO_IDX["HUMAN_REVIEW"]

# Score floor/ceiling used to keep nonconformity scores bounded.
_SCORE_FLOOR = 0.0
_SCORE_CEIL = 1.0


def _clamp(value: float, low: float = _SCORE_FLOOR, high: float = _SCORE_CEIL) -> float:
    """Clamp ``value`` into ``[low, high]`` mapping non-finite input to ``low``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    if not math.isfinite(number):
        return low
    return max(low, min(high, number))


def _label_idx(action: str) -> int:
    """Severity index of ``action`` (unknown labels fall back to HUMAN_REVIEW)."""
    return ACTION_LABEL_TO_IDX.get(str(action).strip().upper(), _DEFAULT_LABEL_IDX)


def _as_float(features: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """Read a numeric feature, tolerating missing keys and bad types."""
    if key not in features:
        return default
    return _clamp(features[key], low=-1.0, high=1.0e6)


class ScoreBasedNCF(NonconformityFunction):
    """Nonconformity driven purely by the observed risk score.

    Each governance action owns a reference risk band centre
    (:data:`_REFERENCE_RISK`).  The nonconformity of candidate action ``y`` is
    the normalised distance between the observed risk and that band::

        NCF(x, y) = | risk(x) - ref(y) | / scale

    ``scale`` is fitted from the calibration set (median absolute deviation of
    the residual scores, floored so a degenerate calibration set cannot make
    the NCF collapse).
    """

    name = "score_based"

    #: Reference risk centre for each action on the severity lattice.
    _REFERENCE_RISK: ClassVar[Dict[str, float]] = {
        "ALLOW": 0.15,
        "HUMAN_REVIEW": 0.65,
        "BLOCK": 0.95,
    }

    #: Residual scale used before calibration runs.
    _DEFAULT_SCALE = 0.30

    def __init__(self, scale: Optional[float] = None):
        self._scale = float(scale) if scale and scale > 0 else self._DEFAULT_SCALE
        self._calibrated = False
        self._calibration_size = 0

    # ── NonconformityFunction API ───────────────────────────────────────────

    def score(self, features: Dict[str, Any], action: str) -> float:
        risk = self._observed_risk(features)
        reference = self._REFERENCE_RISK.get(str(action).strip().upper(), 0.5)
        residual = abs(risk - reference)
        # Normalise by a constant so that scores stay O(1) and comparable
        # across calibration and prediction time.
        return _clamp(residual / self._scale, high=8.0)

    def calibrate(self, calibration_set: List[CalibrationItem]) -> None:
        """Fit ``scale`` from calibration residuals (robust MAD estimate)."""
        residuals: List[float] = []
        for item in calibration_set:
            if not isinstance(item, CalibrationItem):
                continue
            residuals.append(self.score(self._calibration_features(item), item.true_action))
        if not residuals:
            self._scale = self._DEFAULT_SCALE
            self._calibrated = False
            self._calibration_size = 0
            return

        residuals.sort()
        median = residuals[len(residuals) // 2]
        deviations = sorted(abs(r - median) for r in residuals)
        mad = deviations[len(deviations) // 2]
        # 1.4826 rescales MAD to a sigma-equivalent; floored so that a
        # perfectly uniform calibration set keeps a usable spread.
        self._scale = max(1.4826 * mad, self._DEFAULT_SCALE * 0.5)
        self._calibrated = True
        self._calibration_size = len(residuals)

    def feature_vector(self, features: Dict[str, Any]) -> List[float]:
        return [self._observed_risk(features)]

    # ── helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _observed_risk(features: Dict[str, Any]) -> float:
        """Observed risk: prefer the harness-injected key, fall back to raw."""
        raw = features.get("_risk_score", features.get("risk_score", 0.5))
        return _clamp(raw)

    @staticmethod
    def _calibration_features(item: CalibrationItem) -> Dict[str, Any]:
        """Mirror the feature enrichment performed by ConformalPredictor."""
        features = dict(item.features)
        features["_risk_score"] = item.risk_score
        features["_inherited_risk"] = item.inherited_risk
        features["_graph_degree"] = item.graph_degree
        features["_chain_length"] = item.chain_length
        return features


class BehaviorGraphNCF(ScoreBasedNCF):
    """Score-based NCF extended with behavior-chain signals.

    The effective risk used for scoring is::

        risk_eff = risk * (1 + CHAIN_GAIN * chain_length)
                 + INHERIT_GAIN * inherited_risk
                 + DEGREE_GAIN * graph_degree

    Rationale: a tool call whose local score is unremarkable can still be
    non-conforming for a weak action if it sits at the end of a long
    delegation chain, inherits risk from upstream nodes, or has high fan-out
    (an amplifier).  Feeding ``risk_eff`` into the same band-distance metric
    keeps the calibration semantics of :class:`ScoreBasedNCF` intact.
    """

    name = "behavior_graph"

    #: Per-hop amplification applied to the local risk score.
    CHAIN_GAIN = 0.15
    #: Weight of risk inherited from upstream nodes.
    INHERIT_GAIN = 0.50
    #: Weight of node fan-out (amplification indicator).
    DEGREE_GAIN = 0.02

    # Upstream risk amplification saturates beyond this many chain hops.
    _MAX_CHAIN_HOPS = 6
    # Fan-out contribution saturates beyond this degree.
    _MAX_DEGREE = 10

    def _observed_risk(self, features: Dict[str, Any]) -> float:  # type: ignore[override]
        base = super()._observed_risk(features)
        chain = min(_as_float(features, "_chain_length"), float(self._MAX_CHAIN_HOPS))
        inherited = _as_float(features, "_inherited_risk")
        degree = min(_as_float(features, "_graph_degree"), float(self._MAX_DEGREE))

        effective = base * (1.0 + self.CHAIN_GAIN * chain)
        effective += self.INHERIT_GAIN * inherited
        effective += self.DEGREE_GAIN * degree
        return _clamp(effective)

    def feature_vector(self, features: Dict[str, Any]) -> List[float]:
        return [
            self._observed_risk(features),
            _as_float(features, "_inherited_risk"),
            _as_float(features, "_graph_degree"),
            _as_float(features, "_chain_length"),
        ]


class AdaptiveNCF(ScoreBasedNCF):
    """Score-based NCF with an online Adaptive Conformal Inference update.

    Standard conformal calibration yields a *fixed* threshold.  Under
    distribution shift the empirical coverage drifts away from ``1 - alpha``.
    ACI (Gibbs & Candes, 2021) instead tracks coverage online by adapting the
    effective level on every observed outcome::

        alpha_{t+1} = alpha_t + gamma * (1 - alpha_target - covered_t)

    ``covered_t`` is 1 when the true action fell inside the predicted set.
    A miscovered sample raises ``alpha_t`` (tighter sets); an over-covered one
    lowers it (larger sets).  The adapted level is exposed via :meth:`update`
    so the owning predictor/report can widen or narrow its quantile.
    """

    name = "adaptive"

    #: Step size of the online update.  Larger = faster tracking, noisier.
    DEFAULT_GAMMA = 0.05

    def __init__(self, gamma: Optional[float] = None, alpha: float = 0.1):
        super().__init__()
        self.gamma = float(gamma) if gamma and gamma > 0 else self.DEFAULT_GAMMA
        self.alpha = _clamp(float(alpha), low=0.01, high=0.50)
        self.n_updates = 0
        self.empirical_coverage: List[float] = []

    # ── NonconformityFunction API ───────────────────────────────────────────

    def calibrate(self, calibration_set: List[CalibrationItem]) -> None:
        super().calibrate(calibration_set)
        self.n_updates = 0
        self.empirical_coverage = []

    def update(self, features: Dict[str, Any], true_action: str, predicted_set: Sequence[str]) -> float:
        """Feed one realised outcome back into the coverage controller.

        Returns the updated effective alpha, so callers can log/monitor drift.
        Note this NCF does not mutate its own scoring; widening the conformal
        sets is the caller's decision (calibrate a looser alpha on the
        predictor, or re-fit ``scale``).
        """
        covered = 1.0 if str(true_action) in tuple(predicted_set) else 0.0
        target = 1.0 - self.alpha
        self.alpha = _clamp(self.alpha + self.gamma * (target - covered), low=0.01, high=0.50)
        self.n_updates += 1
        self.empirical_coverage.append(covered)
        return self.alpha


__all__ = [
    "ACTION_LABEL_TO_IDX",
    "CROSS_ENTROPY_LABELS",
    "IDX_TO_ACTION",
    "AdaptiveNCF",
    "BehaviorGraphNCF",
    "ScoreBasedNCF",
]

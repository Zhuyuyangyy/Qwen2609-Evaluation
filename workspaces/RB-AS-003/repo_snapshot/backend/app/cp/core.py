"""
Conformal Prediction Core Engine
================================
Implements the Mondrian/Adaptive Conformal Prediction framework
for multi-class agent decision prediction.

Key concepts:
- Nonconformity Score (NCF): measures how "non-conforming" a prediction is
- Calibration set: historical (x_i, y_i) pairs used to compute quantiles
- Prediction set: C(x) = { y : NCF(x, y) ≤ q̂ }
- Coverage guarantee: P(y ∈ C(x)) ≥ 1 - α (under exchangeability)

For agent decisions (ALLOW=0, HUMAN_REVIEW=1, BLOCK=2):
- We predict SETS of actions, not single actions
- Low risk → {ALLOW}
- Boundary risk → {ALLOW, HUMAN_REVIEW} or {HUMAN_REVIEW, BLOCK}
- High risk → {BLOCK}
- Uncertain → {ALLOW, HUMAN_REVIEW, BLOCK}
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional

import numpy as np


class ActionLabel(IntEnum):
    """Actions indexed for NCF computation"""
    ALLOW = 0
    HUMAN_REVIEW = 1
    BLOCK = 2


ACTION_LABELS = ["ALLOW", "HUMAN_REVIEW", "BLOCK"]
ACTION_LABEL_TO_IDX = {a: i for i, a in enumerate(ACTION_LABELS)}
IDX_TO_ACTION = {i: a for i, a in enumerate(ACTION_LABELS)}


@dataclass
class CalibrationItem:
    """A single calibration example: (features, true_label)"""
    case_id: str
    features: Dict[str, Any]       # Feature vector (risk_score, tool_type, etc.)
    true_action: str                # Ground truth action label
    risk_score: float               # Raw risk score
    inherited_risk: float = 0.0     # From behavior graph
    graph_degree: int = 0           # Node connectivity
    chain_length: int = 0           # Steps in behavior chain
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NCFResult:
    """Nonconformity scores for all candidate labels"""
    scores: Dict[str, float]  # action → NCF score
    most_conforming: str      # argmin action


@dataclass
class PredictionSet:
    """Conformal prediction set output"""
    actions: List[str]                    # Predicted set of actions
    most_likely: str                      # argmax confidence
    coverage_level: float                 # 1 - α
    quantile: float                       # The calibrated quantile
    ncf_used: str                         # NCF class name
    decision_reason: str                  # Human-readable explanation
    set_size: int = field(init=False)

    def __post_init__(self):
        self.set_size = len(self.actions)


@dataclass
class CalibrationStats:
    """Statistics from calibration procedure"""
    n_calibration: int
    n_classes: int
    alpha: float
    coverage_target: float
    quantile: float
    empirical_coverage: Optional[float] = None
    mean_set_size: Optional[float] = None
    per_class_coverage: Dict[str, float] = field(default_factory=dict)


class NonconformityFunction:
    """
    Base class for nonconformity functions.
    An NCF measures how "non-conforming" a prediction (x, y) is.
    Lower scores = more conformal (more likely correct).
    """

    name: str = "base"

    def score(self, features: Dict[str, Any], action: str) -> float:
        """
        Compute nonconformity score: NCF(x, y)

        Args:
            features: Feature dictionary for the test case
            action: Candidate action label

        Returns:
            Nonconformity score (lower = more conformal)
        """
        raise NotImplementedError

    def calibrate(
        self,
        calibration_set: List[CalibrationItem]
    ) -> None:
        """
        Optional: fit any parameters of the NCF using calibration data.
        Called once before prediction.
        """
        pass

    def feature_vector(self, features: Dict[str, Any]) -> List[float]:
        """
        Extract numerical feature vector for this NCF.
        Used for visualization and debugging.
        """
        return []


class ConformalPredictor:
    """
    Conformal Prediction predictor for agent decisions.

    Uses the Sampsons/Adaptive Conformal Inference (ACI) approach
    with Mondrian categorization for proper coverage across risk levels.

    Workflow:
      1. calibrate() → fit NCF on calibration set
      2. compute_quantile() → find 1-α quantile of calibration scores
      3. predict() → generate prediction set for new input

    The key guarantee:
      P(true_action ∈ predict_set) ≥ 1 - α

    This holds under the assumption that calibration and test data
    are exchangeable (no distribution shift).
    """

    def __init__(
        self,
        ncf: NonconformityFunction,
        alpha: float = 0.1,
        use_adaptive: bool = True,
    ):
        """
        Args:
            ncf: Nonconformity function to use
            alpha: Significance level (coverage = 1 - alpha)
            use_adaptive: Use adaptive/Conditional ACI instead of standard CP
        """
        self.ncf = ncf
        self.alpha = alpha
        self.use_adaptive = use_adaptive

        self._calibration_set: List[CalibrationItem] = []
        self._quantile: Optional[float] = None
        self._is_calibrated: bool = False
        self._stats: Optional[CalibrationStats] = None

    def calibrate(
        self,
        calibration_data: List[Dict[str, Any]],
        fit_ncf: bool = True,
    ) -> CalibrationStats:
        """
        Calibrate the predictor on historical agent decisions.

        Args:
            calibration_data: List of dicts with keys:
                - case_id, features, true_action, risk_score
                - optionally: inherited_risk, graph_degree, chain_length
            fit_ncf: Whether to call ncf.calibrate() on the data

        Returns:
            CalibrationStats with quantile and coverage info
        """
        # Parse into CalibrationItems
        self._calibration_set = []
        for item in calibration_data:
            cal_item = CalibrationItem(
                case_id=item.get("case_id", f"cal_{len(self._calibration_set)}"),
                features=item.get("features", {}),
                true_action=item.get("true_action", "ALLOW"),
                risk_score=item.get("risk_score", 0.5),
                inherited_risk=item.get("inherited_risk", 0.0),
                graph_degree=item.get("graph_degree", 0),
                chain_length=item.get("chain_length", 0),
                metadata=item.get("metadata", {}),
            )
            self._calibration_set.append(cal_item)

        # Optionally fit NCF parameters
        if fit_ncf:
            self.ncf.calibrate(self._calibration_set)

        # Compute quantile
        self._quantile = self.compute_quantile()

        # Compute statistics
        self._stats = self._compute_stats()
        self._is_calibrated = True

        return self._stats

    def compute_quantile(self) -> float:
        """
        Compute the 1-α quantile of calibration nonconformity scores.

        Uses the standard CP quantile formula:
            q̂ = ceil((n+1)(1-α)) / n

        Returns:
            The calibrated quantile threshold
        """
        n = len(self._calibration_set)
        if n == 0:
            raise ValueError("No calibration data. Call calibrate() first.")

        # Compute nonconformity for each calibration item
        scores = []
        for cal_item in self._calibration_set:
            # NCF score for the TRUE label (conformal = low score)
            score = self.ncf.score(
                self._ncf_features(cal_item),
                cal_item.true_action,
            )
            scores.append(score)

        scores = np.array(sorted(scores))

        # Quantile formula: (n+1)(1-α) with rounding up
        q_level = (n + 1) * (1 - self.alpha)

        # Two approaches:
        # 1. Standard CP: use ceil
        # 2. Adaptive (ACI): use exact quantile
        if self.use_adaptive:
            # Linear interpolation for smooth quantile
            q_idx = q_level - 1
            lo = max(0, math.floor(q_idx))
            hi = min(n - 1, math.ceil(q_idx))
            if lo == hi:
                q = scores[lo]
            else:
                frac = q_idx - lo
                q = scores[lo] * (1 - frac) + scores[hi] * frac
        else:
            # Standard Mondrian CP
            k = math.ceil(q_level)
            k = max(1, min(n, k))
            q = scores[k - 1]  # 1-indexed → 0-indexed

        return float(q)

    def predict(
        self,
        features: Dict[str, Any],
        return_details: bool = False,
    ) -> PredictionSet:
        """
        Generate a conformal prediction set for a new input.

        Args:
            features: Feature dictionary for the test case
            return_details: Include full debugging info

        Returns:
            PredictionSet with guaranteed coverage
        """
        if not self._is_calibrated:
            raise ValueError("Must call calibrate() before predict()")

        q = self._quantile

        # Score all three candidate actions
        scores = {}
        for action in ACTION_LABELS:
            scores[action] = self.ncf.score(features, action)

        # Prediction set: all actions with NCF ≤ q̂
        predicted_set = [a for a, s in scores.items() if s <= q]

        # Fallback: if set is empty (no action below quantile),
        # use the most conforming one (deterministic fallback)
        if not predicted_set:
            best_action = min(scores, key=scores.get)
            predicted_set = [best_action]

        # Most likely action (lowest NCF)
        most_likely = min(scores, key=scores.get)

        # Decision reason
        if len(predicted_set) == 1:
            reason = f"Single-action prediction: {predicted_set[0]} (NCF={scores[predicted_set[0]]:.3f} ≤ q={q:.3f})"
        elif len(predicted_set) == 3:
            reason = f"High uncertainty: all actions valid. q={q:.3f} too high for any exclusion"
        else:
            reason = f"Set of {len(predicted_set)} actions: {predicted_set}"

        result = PredictionSet(
            actions=predicted_set,
            most_likely=most_likely,
            coverage_level=1 - self.alpha,
            quantile=q,
            ncf_used=self.ncf.name,
            decision_reason=reason,
        )

        if return_details:
            result.decision_reason += f"\nAll scores: { {a: f'{s:.3f}' for a, s in scores.items()} }"

        return result

    def evaluate_coverage(
        self,
        test_data: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Evaluate empirical coverage on held-out test data.

        Args:
            test_data: List of test cases (same format as calibrate())

        Returns:
            Coverage evaluation metrics
        """
        n_test = len(test_data)
        covered = 0
        set_sizes = []
        per_class_covered: Dict[str, int] = {a: 0 for a in ACTION_LABELS}
        per_class_total: Dict[str, int] = {a: 0 for a in ACTION_LABELS}

        for item in test_data:
            features = item.get("features", {})
            true_action = item.get("true_action", "ALLOW")

            pred_set = self.predict(features)
            in_set = true_action in pred_set.actions

            covered += int(in_set)
            set_sizes.append(pred_set.set_size)
            per_class_total[true_action] = per_class_total.get(true_action, 0) + 1
            if in_set:
                per_class_covered[true_action] = per_class_covered.get(true_action, 0) + 1

        emp_coverage = covered / n_test if n_test > 0 else 0.0
        mean_set_size = sum(set_sizes) / n_test if n_test > 0 else 0.0

        # Per-class coverage
        per_class_rate = {
            a: per_class_covered[a] / per_class_total[a]
            if per_class_total[a] > 0 else 0.0
            for a in ACTION_LABELS
        }

        return {
            "n_test": n_test,
            "empirical_coverage": round(emp_coverage, 4),
            "target_coverage": 1 - self.alpha,
            "coverage_gap": round(emp_coverage - (1 - self.alpha), 4),
            "mean_set_size": round(mean_set_size, 3),
            "coverage_adequate": emp_coverage >= (1 - self.alpha - 0.05),  # 5% slack
            "per_class_coverage": {a: round(r, 4) for a, r in per_class_rate.items()},
        }

    def _ncf_features(self, item: CalibrationItem) -> Dict[str, Any]:
        """Build the feature dict for NCF scoring from a calibration item."""
        f = dict(item.features)
        f["_risk_score"] = item.risk_score
        f["_inherited_risk"] = item.inherited_risk
        f["_graph_degree"] = item.graph_degree
        f["_chain_length"] = item.chain_length
        return f

    def _compute_stats(self) -> CalibrationStats:
        """Compute calibration statistics."""
        n = len(self._calibration_set)
        return CalibrationStats(
            n_calibration=n,
            n_classes=len(ACTION_LABELS),
            alpha=self.alpha,
            coverage_target=1 - self.alpha,
            quantile=self._quantile,
        )

    def export_calibration(self, path: str) -> None:
        """Export calibration data to JSON for reproducibility."""
        data = {
            "alpha": self.alpha,
            "use_adaptive": self.use_adaptive,
            "ncf_name": self.ncf.name,
            "quantile": self._quantile,
            "n_calibration": len(self._calibration_set),
            "calibration_items": [
                {
                    "case_id": item.case_id,
                    "features": item.features,
                    "true_action": item.true_action,
                    "risk_score": item.risk_score,
                }
                for item in self._calibration_set
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def summary(self) -> Dict[str, Any]:
        """Get a summary of the predictor state."""
        return {
            "is_calibrated": self._is_calibrated,
            "alpha": self.alpha,
            "ncf_name": self.ncf.name,
            "use_adaptive": self.use_adaptive,
            "n_calibration": len(self._calibration_set),
            "quantile": round(self._quantile, 4) if self._quantile else None,
            "coverage_target": 1 - self.alpha,
        }

"""Unit tests for the conformal prediction layer.

Covers the three nonconformity functions in ``app.cp.ncf`` and their
integration with ``ConformalPredictor``.  These tests replace the previous
``try/except ImportError -> pytest.skip`` guard in ``test_smoke.py``, which was
masking the fact that ``app.cp`` could not be imported at all.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


class TestLabelLattice:
    """Shared label constants must match the action lattice in core.py."""

    def test_labels_cover_all_actions(self):
        from app.cp import CROSS_ENTROPY_LABELS
        from app.cp.core import ACTION_LABELS

        assert CROSS_ENTROPY_LABELS == ACTION_LABELS
        assert CROSS_ENTROPY_LABELS == ["ALLOW", "HUMAN_REVIEW", "BLOCK"]

    def test_label_index_roundtrip(self):
        from app.cp import ACTION_LABEL_TO_IDX, CROSS_ENTROPY_LABELS, IDX_TO_ACTION

        for label in CROSS_ENTROPY_LABELS:
            assert IDX_TO_ACTION[ACTION_LABEL_TO_IDX[label]] == label

    def test_severity_is_monotonic(self):
        from app.cp import ACTION_LABEL_TO_IDX

        assert (
            ACTION_LABEL_TO_IDX["ALLOW"]
            < ACTION_LABEL_TO_IDX["HUMAN_REVIEW"]
            < ACTION_LABEL_TO_IDX["BLOCK"]
        )


def _calibration_set(n_per_action: int = 12):
    """Build a calibration set where risk scores track the true action."""
    from app.cp.core import CalibrationItem

    plan = [
        ("ALLOW", 0.08),
        ("ALLOW", 0.22),
        ("HUMAN_REVIEW", 0.58),
        ("HUMAN_REVIEW", 0.72),
        ("BLOCK", 0.93),
        ("BLOCK", 0.98),
    ]
    items = []
    for i in range(n_per_action):
        action, risk = plan[i % len(plan)]
        jitter = (i // len(plan)) * 0.005
        items.append(
            CalibrationItem(
                case_id=f"cal_{i}",
                features={"tool_type": "sql"},
                true_action=action,
                risk_score=min(1.0, risk + jitter),
                inherited_risk=0.0,
                graph_degree=1,
                chain_length=0,
            )
        )
    return items


class TestScoreBasedNCF:
    def test_allowed_call_is_most_conforming_for_allow(self):
        from app.cp.ncf import ScoreBasedNCF

        ncf = ScoreBasedNCF()
        low_risk = {"risk_score": 0.05}
        assert ncf.score(low_risk, "ALLOW") < ncf.score(low_risk, "BLOCK")

    def test_blocked_call_is_most_conforming_for_block(self):
        from app.cp.ncf import ScoreBasedNCF

        ncf = ScoreBasedNCF()
        high_risk = {"risk_score": 0.97}
        assert ncf.score(high_risk, "BLOCK") < ncf.score(high_risk, "ALLOW")

    def test_scores_are_finite_and_bounded(self):
        from app.cp.ncf import ScoreBasedNCF

        ncf = ScoreBasedNCF()
        for risk in (0.0, 0.5, 1.0):
            for action in ("ALLOW", "HUMAN_REVIEW", "BLOCK"):
                score = ncf.score({"risk_score": risk}, action)
                assert 0.0 <= score <= 8.0

    def test_malformed_features_fall_back_to_default(self):
        from app.cp.ncf import ScoreBasedNCF

        ncf = ScoreBasedNCF()
        assert ncf.score({}, "ALLOW") == pytest.approx(ncf.score({}, "ALLOW"))
        assert ncf.score({"risk_score": "not-a-number"}, "ALLOW") >= 0.0

    def test_calibration_adjusts_scale(self):
        from app.cp.ncf import ScoreBasedNCF

        ncf = ScoreBasedNCF()
        before = ncf.score({"risk_score": 0.6}, "ALLOW")
        ncf.calibrate(_calibration_set())
        after = ncf.score({"risk_score": 0.6}, "ALLOW")
        assert ncf._calibrated is True
        assert ncf._calibration_size == len(_calibration_set())
        assert after != before

    def test_empty_calibration_keeps_default_scale(self):
        from app.cp.ncf import ScoreBasedNCF

        ncf = ScoreBasedNCF()
        ncf.calibrate([])
        assert ncf._calibrated is False
        assert ncf._scale == ScoreBasedNCF._DEFAULT_SCALE


class TestBehaviorGraphNCF:
    def test_name_differs_from_parent(self):
        from app.cp.ncf import BehaviorGraphNCF, ScoreBasedNCF

        assert BehaviorGraphNCF.name != ScoreBasedNCF.name
        assert BehaviorGraphNCF.name == "behavior_graph"

    def test_inherited_risk_shifts_score_towards_stronger_governance(self):
        from app.cp.ncf import BehaviorGraphNCF

        ncf = BehaviorGraphNCF()
        clean = {"risk_score": 0.2, "_inherited_risk": 0.0}
        contaminated = {"risk_score": 0.2, "_inherited_risk": 0.8}
        # Same local risk: inheriting upstream risk makes ALLOW less conformal.
        assert ncf.score(clean, "ALLOW") < ncf.score(contaminated, "ALLOW")
        # ... and BLOCK more conformal.
        assert ncf.score(contaminated, "BLOCK") < ncf.score(clean, "BLOCK")

    def test_chain_length_amplifies_effective_risk(self):
        from app.cp.ncf import BehaviorGraphNCF

        ncf = BehaviorGraphNCF()
        short = {"risk_score": 0.3, "_chain_length": 0}
        long_chain = {"risk_score": 0.3, "_chain_length": 5}
        assert ncf.score(short, "ALLOW") < ncf.score(long_chain, "ALLOW")

    def test_effective_risk_saturates(self):
        from app.cp.ncf import BehaviorGraphNCF

        ncf = BehaviorGraphNCF()
        big = {"risk_score": 0.9, "_inherited_risk": 1.0, "_graph_degree": 10, "_chain_length": 99}
        assert 0.0 <= ncf._observed_risk(big) <= 1.0

    def test_feature_vector_includes_graph_signals(self):
        from app.cp.ncf import BehaviorGraphNCF

        ncf = BehaviorGraphNCF()
        vec = ncf.feature_vector(
            {"risk_score": 0.5, "_inherited_risk": 0.2, "_graph_degree": 3, "_chain_length": 2}
        )
        assert len(vec) == 4


class TestAdaptiveNCF:
    def test_update_required_before_predict(self):
        from app.cp.ncf import AdaptiveNCF

        ncf = AdaptiveNCF(alpha=0.1)
        alpha = ncf.update(
            {"risk_score": 0.9}, true_action="BLOCK", predicted_set=["BLOCK"]
        )
        # Covered sample -> alpha is pushed down (larger sets next round).
        assert alpha < 0.1
        assert ncf.n_updates == 1

    def test_misscoverage_raises_effective_alpha(self):
        from app.cp.ncf import AdaptiveNCF

        ncf = AdaptiveNCF(alpha=0.1)
        alpha = ncf.update({"risk_score": 0.6}, true_action="BLOCK", predicted_set=["ALLOW"])
        # Miscoverage widens the conformal sets by raising the level.
        assert alpha > 0.1
        assert ncf.empirical_coverage == [0.0]

    def test_overcoverage_lowers_effective_alpha(self):
        from app.cp.ncf import AdaptiveNCF

        ncf = AdaptiveNCF(alpha=0.1)
        # A 3-action set trivially covers: level should be pushed down.
        alpha = ncf.update(
            {"risk_score": 0.5},
            true_action="BLOCK",
            predicted_set=["ALLOW", "HUMAN_REVIEW", "BLOCK"],
        )
        assert alpha < 0.1
        assert ncf.empirical_coverage == [1.0]

    def test_scores_are_unchanged_by_controller(self):
        """update() must not silently distort the conformal scores."""
        from app.cp.ncf import AdaptiveNCF

        ncf = AdaptiveNCF(alpha=0.1)
        features, action = {"risk_score": 0.6}, "ALLOW"
        base = ncf.score(features, action)
        for _ in range(5):
            ncf.update(features, true_action="BLOCK", predicted_set=["ALLOW"])
        assert ncf.score(features, action) == base

    def test_alpha_stays_bounded_over_many_updates(self):
        from app.cp.ncf import AdaptiveNCF

        ncf = AdaptiveNCF(alpha=0.1, gamma=0.5)
        rng = random.Random(7)
        for _ in range(200):
            ncf.update(
                {"risk_score": rng.random()},
                true_action=rng.choice(["ALLOW", "HUMAN_REVIEW", "BLOCK"]),
                predicted_set=["BLOCK"],
            )
        assert 0.01 <= ncf.alpha <= 0.50

    def test_calibration_resets_controller(self):
        from app.cp.ncf import AdaptiveNCF

        ncf = AdaptiveNCF()
        ncf.update({"risk_score": 0.5}, "BLOCK", ["ALLOW"])
        assert ncf.n_updates == 1
        drifted_alpha = ncf.alpha
        assert drifted_alpha != 0.1

        ncf.calibrate(_calibration_set())
        # Online bookkeeping is cleared; the drift itself is *not* rolled back
        # (recalibration re-fits scale but alpha keeps adapting afterwards).
        assert ncf.n_updates == 0
        assert ncf.empirical_coverage == []
        assert ncf._calibrated is True
        assert ncf.alpha == drifted_alpha


def _predictor_data(n: int = 60):
    """Synthetic decisions with a clean risk -> action mapping.

    ``ConformalPredictor.evaluate_coverage`` scores each test item from its
    ``features`` dict, so the numeric signals must live there (not only at the
    top level of the item).
    """
    rng = random.Random(11)
    data = []
    for i in range(n):
        action = rng.choice(["ALLOW", "HUMAN_REVIEW", "BLOCK"])
        base = {"ALLOW": 0.15, "HUMAN_REVIEW": 0.65, "BLOCK": 0.95}[action]
        risk = max(0.0, min(1.0, base + rng.uniform(-0.12, 0.12)))
        inherited = round(rng.uniform(0, 0.3), 3)
        degree = rng.randint(1, 4)
        chain = rng.randint(0, 3)
        data.append(
            {
                "case_id": f"case_{i}",
                "features": {
                    "tool_type": rng.choice(["sql", "http", "shell"]),
                    "risk_score": risk,
                    "inherited_risk": inherited,
                    "graph_degree": degree,
                    "chain_length": chain,
                    # Mirrors the enrichment ConformalPredictor does internally.
                    "_risk_score": risk,
                    "_inherited_risk": inherited,
                    "_graph_degree": degree,
                    "_chain_length": chain,
                },
                "true_action": action,
                "risk_score": risk,
                "inherited_risk": inherited,
                "graph_degree": degree,
                "chain_length": chain,
            }
        )
    return data


class TestConformalIntegration:
    """The NCFs must work through the real ConformalPredictor pipeline."""

    def test_predict_before_calibrate_raises(self):
        from app.cp.core import ConformalPredictor
        from app.cp.ncf import ScoreBasedNCF

        predictor = ConformalPredictor(ncf=ScoreBasedNCF())
        with pytest.raises(ValueError):
            predictor.predict({"risk_score": 0.5})

    def test_predict_returns_prediction_set(self):
        from app.cp.core import ConformalPredictor
        from app.cp.ncf import ScoreBasedNCF

        predictor = ConformalPredictor(ncf=ScoreBasedNCF(), alpha=0.1)
        predictor.calibrate(_predictor_data(), fit_ncf=True)
        result = predictor.predict({"risk_score": 0.15, "_chain_length": 0})
        assert result.ncf_used == "score_based"
        assert 1 <= result.set_size <= 3
        assert result.set_size == len(result.actions)
        assert result.coverage_level == pytest.approx(0.9)

    def test_quantile_is_calibrated_from_scores(self):
        from app.cp.core import ConformalPredictor
        from app.cp.ncf import ScoreBasedNCF

        predictor = ConformalPredictor(ncf=ScoreBasedNCF(), alpha=0.1)
        stats = predictor.calibrate(_predictor_data())
        assert stats.n_calibration == len(_predictor_data())
        assert stats.quantile == predictor.compute_quantile()

    def test_high_risk_block_is_conforming(self):
        from app.cp.core import ConformalPredictor
        from app.cp.ncf import BehaviorGraphNCF

        predictor = ConformalPredictor(ncf=BehaviorGraphNCF(), alpha=0.1)
        predictor.calibrate(_predictor_data(), fit_ncf=True)
        result = predictor.predict({"risk_score": 0.97, "_chain_length": 0})
        assert result.most_likely == "BLOCK"

    def test_empirical_coverage_meets_target_on_held_out_data(self):
        from app.cp.core import ConformalPredictor
        from app.cp.ncf import BehaviorGraphNCF

        data = _predictor_data(n=120)
        train, test = data[:90], data[90:]

        predictor = ConformalPredictor(ncf=BehaviorGraphNCF(), alpha=0.1)
        predictor.calibrate(train, fit_ncf=True)
        metrics = predictor.evaluate_coverage(test)

        assert metrics["n_test"] == len(test)
        # Allow the same 5% slack the engine itself uses as "adequate".
        assert metrics["coverage_adequate"] is True
        assert metrics["mean_set_size"] >= 1.0

    def test_adaptive_ncf_predicts_through_pipeline(self):
        from app.cp.core import ConformalPredictor
        from app.cp.ncf import AdaptiveNCF

        predictor = ConformalPredictor(ncf=AdaptiveNCF(), alpha=0.1)
        predictor.calibrate(_predictor_data(), fit_ncf=True)
        result = predictor.predict({"risk_score": 0.2})
        assert result.actions
        # ACI controller is reachable and usable after calibration.
        predictor.ncf.update(
            {"risk_score": 0.2}, true_action=result.most_likely, predicted_set=result.actions
        )
        assert predictor.ncf.n_updates == 1

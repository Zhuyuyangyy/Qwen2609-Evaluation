"""
Conformal Prediction Layer for AgentShield V3
==============================================
Provides statistically rigorous uncertainty quantification for agent decisions.

Core contribution: Instead of point predictions (ALLOW/BLOCK/HUMAN_REVIEW),
we output PREDICTION SETS with guaranteed coverage:
  P(true_action ∈ prediction_set) ≥ 1 - α

This is the first application of Conformal Prediction to multi-agent
behavior chain governance, providing distribution-free, model-agnostic
coverage guarantees that hold regardless of the underlying risk scorer.

Key papers:
- Vovk et al. (2005): Conformal Predictive Distributions
- Shafer & Vovk (2008): A Tutorial on Conformal Prediction
"""

from app.cp.core import ConformalPredictor, NonconformityFunction
from app.cp.ncf import (
    ACTION_LABEL_TO_IDX,
    CROSS_ENTROPY_LABELS,
    IDX_TO_ACTION,
    AdaptiveNCF,
    BehaviorGraphNCF,
    ScoreBasedNCF,
)

__all__ = [
    "ACTION_LABEL_TO_IDX",
    "CROSS_ENTROPY_LABELS",
    "IDX_TO_ACTION",
    "AdaptiveNCF",
    "BehaviorGraphNCF",
    "ConformalPredictor",
    "NonconformityFunction",
    "ScoreBasedNCF",
]

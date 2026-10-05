"""
context_aggregator.py
=====================
Aggregate risk signals from all detectors with conversation context weighting.

Multi-turn conversations contain risk cues distributed across turns.
This aggregator combines:
  - Semantic risk score (from SemanticRiskEncoder)
  - Injection score (from InjectionDetector)
  - Social engineering score (from SocialEngineeringDetector)
  - Privacy leakage score (from PrivacyLeakageDetector)

Context weighting: user messages that precede agent actions carry more
risk signal than the actions themselves, because injection and SE
attacks originate from user messages.
"""

from __future__ import annotations

from typing import Dict, List, Optional


class ContextAggregator:
    """Aggregate risk signals from multiple detectors with context weighting."""

    # Detector weights — how much each detector contributes to the composite score
    DETECTOR_WEIGHTS = {
        "semantic_risk": 0.25,
        "injection": 0.30,
        "social_engineering": 0.20,
        "privacy_leakage": 0.25,
    }

    # Context role weights — how much weight to give text by role
    ROLE_WEIGHTS = {
        "user": 1.3,        # User messages carry injection/SE risk
        "agent": 0.8,       # Agent actions carry direct risk
        "environment": 0.5, # Environment feedback is lower risk
        "system": 1.0,      # System messages are neutral
        "default": 1.0,
    }

    def __init__(self):
        pass

    def aggregate(
        self,
        semantic_risk_score: float,
        injection_score: float,
        se_score: float,
        privacy_score: float,
        context_weight: float = 1.0,
        max_semantic_category_score: float = 0.0,
    ) -> Dict:
        """
        Aggregate all detector scores into a composite risk assessment.

        Args:
            semantic_risk_score: Score from SemanticRiskEncoder [0, 1]
            injection_score: Score from InjectionDetector [0, 1]
            se_score: Score from SocialEngineeringDetector [0, 1]
            privacy_score: Score from PrivacyLeakageDetector [0, 1]
            context_weight: Multiplicative weight based on context importance
            max_semantic_category_score: Max individual category score from
                SemanticRiskEncoder. If a single category scores very high
                (e.g., irreversible_action=1.0), this should boost the
                composite even if the weighted aggregate is low.

        Returns dict with:
          - composite_score: weighted aggregate [0, 1]
          - max_detector_score: highest individual detector score
          - dominant_risk: which detector contributes most
          - score_breakdown: dict of individual scores
        """
        scores = {
            "semantic_risk": semantic_risk_score,
            "injection": injection_score,
            "social_engineering": se_score,
            "privacy_leakage": privacy_score,
        }

        # Weighted composite
        composite = sum(
            scores[k] * self.DETECTOR_WEIGHTS[k]
            for k in self.DETECTOR_WEIGHTS
        )

        # Boost: if a single semantic category fires strongly, boost composite
        # This prevents the aggregator from diluting a clear high-risk signal
        # e.g., irreversible_action=1.0 should not become composite=0.083
        if max_semantic_category_score > 0.5:
            boost = max_semantic_category_score * 0.3
            composite = max(composite, composite + boost)
            composite = min(1.0, composite)

        # Apply context weight
        composite = min(1.0, composite * context_weight)

        # Find dominant risk
        max_score = 0.0
        dominant = "none"
        for k, v in scores.items():
            if v > max_score:
                max_score = v
                dominant = k

        return {
            "composite_score": round(composite, 4),
            "max_detector_score": round(max_score, 4),
            "dominant_risk": dominant,
            "score_breakdown": {k: round(v, 4) for k, v in scores.items()},
        }

    def compute_context_weight(self, role: str) -> float:
        """Compute context weight based on the role of the message source."""
        return self.ROLE_WEIGHTS.get(role, self.ROLE_WEIGHTS["default"])

    def aggregate_multi_turn(
        self,
        turn_results: List[Dict],
    ) -> Dict:
        """
        Aggregate results across multiple conversation turns.

        Takes the worst-case (maximum) composite score across all turns,
        because a single risky turn is sufficient to flag the conversation.

        Args:
            turn_results: List of per-turn aggregation results

        Returns:
            Worst-case aggregation across all turns
        """
        if not turn_results:
            return {
                "composite_score": 0.0,
                "max_detector_score": 0.0,
                "dominant_risk": "none",
                "score_breakdown": {},
                "n_turns": 0,
            }

        # Take the worst composite score across turns
        worst = max(turn_results, key=lambda r: r["composite_score"])

        # Accumulate risk types across all turns
        all_risks = set()
        for r in turn_results:
            if r["dominant_risk"] != "none":
                all_risks.add(r["dominant_risk"])

        result = dict(worst)
        result["all_risk_types"] = sorted(all_risks)
        result["n_turns"] = len(turn_results)

        return result

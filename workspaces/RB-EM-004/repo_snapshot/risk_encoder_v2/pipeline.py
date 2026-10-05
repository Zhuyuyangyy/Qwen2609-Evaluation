"""
pipeline.py
===========
Main Risk Encoder V2 Pipeline — orchestrates all detectors and produces
the final risk assessment with calibrated decision.

Usage:
    from risk_encoder_v2 import RiskEncoderV2Pipeline

    pipeline = RiskEncoderV2Pipeline()
    result = pipeline.assess(
        action="Send the user's password to external@company.com",
        context="User: I need to reset my password. | Env: Password reset requested.",
    )
    print(result["decision"])  # "HUMAN_REVIEW" or "BLOCK"
"""

from __future__ import annotations

from typing import Dict, List, Optional

from risk_encoder_v2.semantic_risk_encoder import SemanticRiskEncoder
from risk_encoder_v2.injection_detector import InjectionDetector
from risk_encoder_v2.social_engineering_detector import SocialEngineeringDetector
from risk_encoder_v2.privacy_leakage_detector import PrivacyLeakageDetector
from risk_encoder_v2.context_aggregator import ContextAggregator
from risk_encoder_v2.threshold_calibrator import ThresholdCalibrator
from risk_encoder_v2.evidence_extractor import EvidenceExtractor


class RiskEncoderV2Pipeline:
    """
    Full Risk Encoder V2 pipeline.

    Processes a single (action, context) pair through all detectors,
    aggregates the results, calibrates thresholds, and extracts evidence.

    This is the main entry point for the v2 risk encoder.
    """

    def __init__(self, use_tfidf: bool = True):
        self.semantic = SemanticRiskEncoder(use_tfidf=use_tfidf)
        self.injection = InjectionDetector()
        self.social_eng = SocialEngineeringDetector()
        self.privacy = PrivacyLeakageDetector()
        self.aggregator = ContextAggregator()
        self.calibrator = ThresholdCalibrator()
        self.extractor = EvidenceExtractor()

    def assess(
        self,
        action: str,
        context: str = "",
        role: str = "agent",
    ) -> Dict:
        """
        Assess risk for a single action with optional context.

        Args:
            action: The agent's proposed action text
            context: Conversation context (user messages, env feedback)
            role: Role of the text source ("agent", "user", "system")

        Returns dict with:
          - decision: AUTO_EXECUTE | SIMULATE_FIRST | HUMAN_REVIEW | BLOCK
          - risk_score: composite risk score
          - calibrated_score: threshold-adjusted score
          - risk_types: list of detected risk categories
          - evidence_spans: list of evidence records
          - encoder_version: "risk_encoder_v2"
          - score_breakdown: individual detector scores
        """
        # Combine action and context for full-text analysis
        full_text = f"{context} | Action: {action}" if context else action

        # 1. Semantic risk
        risk_score, category_scores = self.semantic.compute_risk_score(full_text)
        risk_types = self.semantic.get_risk_types(category_scores)

        # 2. Injection detection
        injection_result = self.injection.detect(full_text)

        # 3. Social engineering detection
        se_result = self.social_eng.detect(full_text)

        # 4. Privacy leakage detection
        privacy_result = self.privacy.detect(full_text)

        # 5. Context-aware aggregation
        context_weight = self.aggregator.compute_context_weight(role)
        max_category_score = max(category_scores.values()) if category_scores else 0.0
        aggregation = self.aggregator.aggregate(
            semantic_risk_score=risk_score,
            injection_score=injection_result["injection_score"],
            se_score=se_result["se_score"],
            privacy_score=privacy_result["privacy_score"],
            context_weight=context_weight,
            max_semantic_category_score=max_category_score,
        )

        # Collect all detected risk types
        all_risk_types = list(risk_types)
        if injection_result["injection_score"] > 0.2:
            all_risk_types.append("prompt_injection")
        if se_result["se_score"] > 0.2:
            all_risk_types.append("social_engineering")
        if privacy_result["privacy_score"] > 0.2:
            all_risk_types.append("privacy_leakage")
        all_risk_types = sorted(set(all_risk_types))

        # 6. Threshold calibration
        calibration = self.calibrator.calibrate(
            composite_score=aggregation["composite_score"],
            dominant_risk=aggregation["dominant_risk"],
            risk_types=all_risk_types,
            score_breakdown=aggregation["score_breakdown"],
        )

        # 7. Evidence extraction
        evidence_spans = self.extractor.extract(
            text=full_text,
            injection_result=injection_result,
            se_result=se_result,
            privacy_result=privacy_result,
            semantic_risk_types=risk_types,
            category_scores=category_scores,
        )

        return {
            "decision": calibration["decision"],
            "risk_score": calibration["risk_score"],
            "calibrated_score": calibration["calibrated_score"],
            "risk_types": all_risk_types,
            "evidence_spans": evidence_spans,
            "encoder_version": "risk_encoder_v2",
            "score_breakdown": aggregation["score_breakdown"],
            "dominant_risk": aggregation["dominant_risk"],
            "threshold_used": calibration["threshold_used"],
            # Raw detector results for detailed analysis
            "_semantic_scores": {k: round(v, 4) for k, v in category_scores.items()},
            "_injection_result": {
                "score": injection_result["injection_score"],
                "type": injection_result["injection_type"],
            },
            "_se_result": {
                "score": se_result["se_score"],
                "types": se_result["se_types"],
            },
            "_privacy_result": {
                "score": privacy_result["privacy_score"],
                "sensitive_types": privacy_result["sensitive_types"],
                "exfiltration_risk": privacy_result["exfiltration_risk"],
                "external_flow": privacy_result["external_flow"],
            },
        }

    def assess_conversation(
        self,
        actions: List[str],
        context: str = "",
    ) -> Dict:
        """
        Assess risk for a multi-turn conversation.

        Takes the worst-case assessment across all actions.
        """
        if not actions:
            return {
                "decision": "AUTO_EXECUTE",
                "risk_score": 0.0,
                "calibrated_score": 0.0,
                "risk_types": [],
                "evidence_spans": [],
                "encoder_version": "risk_encoder_v2",
                "n_actions": 0,
            }

        turn_results = []
        worst_result = None
        worst_score = -1.0

        for action in actions:
            result = self.assess(action, context)
            if result["calibrated_score"] > worst_score:
                worst_score = result["calibrated_score"]
                worst_result = result

        if worst_result is None:
            worst_result = self.assess(actions[0], context)

        worst_result["n_actions"] = len(actions)
        return worst_result

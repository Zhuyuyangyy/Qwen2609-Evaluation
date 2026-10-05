"""
Risk Encoder V2
===============

Semantic, context-aware risk detection replacing the keyword-based v1 encoder.

Architecture:
  1. Semantic risk encoder — TF-IDF + cosine similarity to known risk patterns
  2. Prompt injection detector — pattern matching for injection indicators
  3. Social engineering detector — authority/urgency pattern recognition
  4. Privacy leakage detector — sensitive data pattern detection
  5. Context aggregator — combine per-turn risks with conversation context
  6. Threshold calibrator — map composite risk to calibrated decision

Key difference from v1:
  - v1 uses 6 keyword features (irreversible_action, data_loss_potential, etc.)
    with exact string matching → 76% zero-coverage on synthetic, ~100% on R-Judge
  - v2 uses semantic similarity to curated risk patterns + specialized detectors
    for injection/social-engineering/privacy → non-zero coverage on all risk types
"""

from risk_encoder_v2.semantic_risk_encoder import SemanticRiskEncoder
from risk_encoder_v2.injection_detector import InjectionDetector
from risk_encoder_v2.social_engineering_detector import SocialEngineeringDetector
from risk_encoder_v2.privacy_leakage_detector import PrivacyLeakageDetector
from risk_encoder_v2.context_aggregator import ContextAggregator
from risk_encoder_v2.threshold_calibrator import ThresholdCalibrator
from risk_encoder_v2.evidence_extractor import EvidenceExtractor
from risk_encoder_v2.pipeline import RiskEncoderV2Pipeline

__all__ = [
    "SemanticRiskEncoder",
    "InjectionDetector",
    "SocialEngineeringDetector",
    "PrivacyLeakageDetector",
    "ContextAggregator",
    "ThresholdCalibrator",
    "EvidenceExtractor",
    "RiskEncoderV2Pipeline",
]

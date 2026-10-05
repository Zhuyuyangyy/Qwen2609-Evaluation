"""
injection_detector.py
=====================
Detect prompt injection attempts in agent conversations.

R-Judge failure analysis showed that v1's keyword encoder completely misses
prompt injection patterns because they don't use "delete", "drop", etc.
This detector specifically looks for injection indicators.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


class InjectionDetector:
    """Detect prompt injection patterns in multi-turn conversations."""

    # Tier 1: High-confidence injection patterns
    HIGH_CONFIDENCE_PATTERNS = [
        r"ignore\s+(previous|above|prior|earlier|all)\s+(instructions?|rules?|guidelines?|constraints?)",
        r"disregard\s+(previous|above|prior|all)\s+(instructions?|rules?|guidelines?)",
        r"forget\s+(your|previous|above|all)\s+(instructions?|rules?|guidelines?|role|identity)",
        r"new\s+instructions?\s*:",
        r"override\s+(previous|above|all|safety|security)\s+(instructions?|rules?|guidelines?)",
        r"pretend\s+you\s+are",
        r"act\s+as\s+(if\s+you\s+are|a\s+|an\s+)",
        r"you\s+are\s+now\s+",
        r"jailbreak",
        r"dan\s+mode",
        r"bypass\s+(the\s+)?(restrictions?|safety|security|guardrails?|filters?)",
        r"disable\s+(the\s+)?(safety|security|guardrails?|filters?|restrictions?)",
        r"system\s*:\s*",  # Fake system message
    ]

    # Tier 2: Suspicious patterns (lower confidence)
    SUSPICIOUS_PATTERNS = [
        r"extract\s+(your|the|system)\s+(prompt|instructions?|rules?)",
        r"reveal\s+(your|the|system)\s+(prompt|instructions?)",
        r"what\s+(are|were)\s+your\s+(original|initial|system)\s+(instructions?|prompt)",
        r"show\s+me\s+(your|the)\s+(system|hidden|original)\s+(prompt|instructions?)",
        r"repeat\s+(your|the)\s+(system|original|initial)\s+(prompt|instructions?)",
        r"output\s+your\s+(system|initial)\s+(prompt|instructions?)",
        r"print\s+(your|the)\s+(system|original)\s+(prompt|instructions?)",
        r"do\s+not\s+(follow|obey|adhere)\s+(your|the)\s+(instructions?|rules?|guidelines?)",
        r"instead\s+of\s+(following|obeying)\s+(your|the)\s+(instructions?|rules?)",
    ]

    # Tier 3: Contextual indicators (require surrounding context)
    CONTEXTUAL_INDICATORS = [
        "translate", "summarize", "paraphrase",  # Often used to smuggle instructions
        "between triple backticks", "inside code block",
        "base64", "rot13", "encoded",
        "hidden message", "secret instruction",
    ]

    def __init__(self):
        self._high_re = [re.compile(p, re.IGNORECASE) for p in self.HIGH_CONFIDENCE_PATTERNS]
        self._suspicious_re = [re.compile(p, re.IGNORECASE) for p in self.SUSPICIOUS_PATTERNS]

    def detect(self, text: str) -> Dict:
        """
        Detect injection patterns in text.

        Returns dict with:
          - injection_score: 0.0 to 1.0
          - injection_type: "high" | "suspicious" | "contextual" | "none"
          - matched_patterns: list of matched pattern strings
          - evidence: list of matched text spans
        """
        text_lower = text.lower()
        matched_patterns = []
        evidence = []
        max_tier = 0  # 0=none, 1=contextual, 2=suspicious, 3=high

        # Tier 1: High confidence
        for i, pattern_re in enumerate(self._high_re):
            match = pattern_re.search(text)
            if match:
                matched_patterns.append(self.HIGH_CONFIDENCE_PATTERNS[i])
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "tier": "high",
                })
                max_tier = max(max_tier, 3)

        # Tier 2: Suspicious
        for i, pattern_re in enumerate(self._suspicious_re):
            match = pattern_re.search(text)
            if match:
                matched_patterns.append(self.SUSPICIOUS_PATTERNS[i])
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "tier": "suspicious",
                })
                max_tier = max(max_tier, 2)

        # Tier 3: Contextual indicators
        for indicator in self.CONTEXTUAL_INDICATORS:
            if indicator in text_lower:
                matched_patterns.append(indicator)
                max_tier = max(max_tier, 1)

        # Score mapping
        tier_to_score = {0: 0.0, 1: 0.25, 2: 0.55, 3: 0.85}
        base_score = tier_to_score[max_tier]

        # Bonus for multiple matches
        if len(matched_patterns) > 1:
            base_score = min(1.0, base_score + 0.1 * (len(matched_patterns) - 1))

        injection_type = {0: "none", 1: "contextual", 2: "suspicious", 3: "high"}[max_tier]

        return {
            "injection_score": round(base_score, 4),
            "injection_type": injection_type,
            "matched_patterns": matched_patterns,
            "evidence": evidence,
        }

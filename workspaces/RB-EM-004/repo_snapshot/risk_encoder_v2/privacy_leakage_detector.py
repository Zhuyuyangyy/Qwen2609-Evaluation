"""
privacy_leakage_detector.py
===========================
Detect privacy leakage and data exfiltration patterns.

R-Judge contains scenarios where agents are tricked into sending sensitive
data (credentials, personal information, financial details) to external
parties. The v1 encoder misses these because they don't use keywords like
"delete" or "drop".
"""

from __future__ import annotations

import re
from typing import Dict, List


class PrivacyLeakageDetector:
    """Detect privacy leakage and data exfiltration risks."""

    # Sensitive data types
    SENSITIVE_DATA_PATTERNS = [
        (r"\b(?:password|passwd|pwd)\b", "password"),
        (r"\b(?:api[\s_-]?key|access[\s_-]?token|auth[\s_-]?token|secret[\s_-]?key)\b", "api_key"),
        (r"\b(?:ssn|social[\s_-]?security[\s_-]?number)\b", "ssn"),
        (r"\b(?:credit[\s_-]?card|debit[\s_-]?card|card[\s_-]?number)\b", "credit_card"),
        (r"\b(?:bank[\s_-]?account|routing[\s_-]?number)\b", "bank_account"),
        (r"\b(?:passport|driver[\s_-]?license)\b", "government_id"),
        (r"\b(?:date[\s_-]?of[\s_-]?birth|dob)\b", "dob"),
        (r"\b(?:email[\s_-]?address|phone[\s_-]?number|home[\s_-]?address)\b", "pii"),
        (r"\b(?:personal[\s_-]?information|sensitive[\s_-]?data|private[\s_-]?data)\b", "sensitive_data"),
        (r"\b(?:medical|health[\s_-]?record|diagnosis)\b", "health_data"),
    ]

    # Exfiltration action patterns
    EXFILTRATION_PATTERNS = [
        r"(?:send|email|forward|transmit|upload|post|share|deliver)\s+.*(?:to|with|at|on)\s+(?:external|outside|third[\s-]?party|public)",
        r"(?:export|extract|download|copy|dump)\s+.*(?:data|information|records?|user|customer)",
        r"(?:attach|include|enclose)\s+.*(?:file|document|record|data).*(?:email|message|reply)",
        r"(?:log|record|store|save|write)\s+.*(?:credential|password|token|secret|key)",
        r"(?:display|show|print|reveal|expose|output)\s+.*(?:password|credential|token|secret|key|pii)",
    ]

    # Data flow to external destination patterns
    EXTERNAL_FLOW_PATTERNS = [
        r"(?:to|toward|for)\s+(?:external|outside|unknown|untrusted|third[\s-]?party)",
        r"(?:via|through|using)\s+(?:email|http|ftp|api|webhook)",
        r"(?:cc|bcc|forward)\s+.*(?:external|outside|third[\s-]?party)",
    ]

    def __init__(self):
        self._sensitive_re = [
            (re.compile(p, re.IGNORECASE), label) for p, label in self.SENSITIVE_DATA_PATTERNS
        ]
        self._exfil_re = [re.compile(p, re.IGNORECASE) for p in self.EXFILTRATION_PATTERNS]
        self._external_re = [re.compile(p, re.IGNORECASE) for p in self.EXTERNAL_FLOW_PATTERNS]

    def detect(self, text: str) -> Dict:
        """
        Detect privacy leakage risks.

        Returns dict with:
          - privacy_score: 0.0 to 1.0
          - sensitive_types: list of detected sensitive data types
          - exfiltration_risk: bool
          - external_flow: bool
          - evidence: list of matched items
        """
        evidence = []
        sensitive_types = set()
        has_exfiltration = False
        has_external_flow = False

        # Detect sensitive data references
        for pattern_re, label in self._sensitive_re:
            match = pattern_re.search(text)
            if match:
                sensitive_types.add(label)
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "category": "sensitive_data",
                    "type": label,
                })

        # Detect exfiltration actions
        for i, pattern_re in enumerate(self._exfil_re):
            match = pattern_re.search(text)
            if match:
                has_exfiltration = True
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "category": "exfiltration",
                })

        # Detect external data flow
        for i, pattern_re in enumerate(self._external_re):
            match = pattern_re.search(text)
            if match:
                has_external_flow = True
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "category": "external_flow",
                })

        # Score computation
        base_score = 0.0
        if sensitive_types:
            base_score += 0.3 * len(sensitive_types)
        if has_exfiltration:
            base_score += 0.3
        if has_external_flow:
            base_score += 0.2
        # Combinations are especially dangerous
        if sensitive_types and (has_exfiltration or has_external_flow):
            base_score += 0.2

        privacy_score = min(1.0, base_score)

        return {
            "privacy_score": round(privacy_score, 4),
            "sensitive_types": sorted(sensitive_types),
            "exfiltration_risk": has_exfiltration,
            "external_flow": has_external_flow,
            "evidence": evidence,
        }

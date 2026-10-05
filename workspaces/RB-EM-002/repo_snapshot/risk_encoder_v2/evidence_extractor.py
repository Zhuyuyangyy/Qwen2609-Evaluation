"""
evidence_extractor.py
=====================
Extract evidence spans from detected risks for explainability.

This module collects evidence from all detectors and formats it into
a structured evidence record that explains WHY a risk was flagged.
"""

from __future__ import annotations

from typing import Dict, List, Optional


class EvidenceExtractor:
    """Extract and format evidence from detector results."""

    def __init__(self):
        pass

    def extract(
        self,
        text: str,
        injection_result: Dict,
        se_result: Dict,
        privacy_result: Dict,
        semantic_risk_types: List[str],
        category_scores: Dict[str, float],
    ) -> List[Dict]:
        """
        Extract evidence spans from all detector results.

        Returns a list of evidence records, each containing:
          - risk_type: category of risk
          - span: the text span that triggered detection
          - reason: human-readable explanation
          - score: detector score for this evidence
        """
        evidence = []

        # Injection evidence
        if injection_result.get("injection_score", 0) > 0:
            for ev in injection_result.get("evidence", []):
                evidence.append({
                    "risk_type": "prompt_injection",
                    "span": ev.get("span", ""),
                    "reason": self._injection_reason(
                        ev.get("tier", ""), injection_result.get("injection_type", "")
                    ),
                    "score": injection_result["injection_score"],
                })
            if not injection_result.get("evidence"):
                evidence.append({
                    "risk_type": "prompt_injection",
                    "span": "",
                    "reason": f"Injection pattern detected (type: {injection_result.get('injection_type', 'unknown')})",
                    "score": injection_result["injection_score"],
                })

        # Social engineering evidence
        if se_result.get("se_score", 0) > 0:
            for ev in se_result.get("evidence", []):
                evidence.append({
                    "risk_type": "social_engineering",
                    "span": ev.get("span", ""),
                    "reason": self._se_reason(ev.get("category", "")),
                    "score": se_result["se_score"],
                })
            if not se_result.get("evidence"):
                evidence.append({
                    "risk_type": "social_engineering",
                    "span": "",
                    "reason": f"Social engineering patterns detected: {', '.join(se_result.get('se_types', []))}",
                    "score": se_result["se_score"],
                })

        # Privacy leakage evidence
        if privacy_result.get("privacy_score", 0) > 0:
            for ev in privacy_result.get("evidence", []):
                evidence.append({
                    "risk_type": "privacy_leakage",
                    "span": ev.get("span", ""),
                    "reason": self._privacy_reason(
                        ev.get("category", ""),
                        ev.get("type", ""),
                        privacy_result.get("exfiltration_risk", False),
                        privacy_result.get("external_flow", False),
                    ),
                    "score": privacy_result["privacy_score"],
                })
            if not privacy_result.get("evidence"):
                types = privacy_result.get("sensitive_types", [])
                evidence.append({
                    "risk_type": "privacy_leakage",
                    "span": "",
                    "reason": f"Sensitive data detected: {', '.join(types)}",
                    "score": privacy_result["privacy_score"],
                })

        # Semantic risk evidence (from category scores)
        for risk_type in semantic_risk_types:
            score = category_scores.get(risk_type, 0.0)
            if score > 0.2:
                # Find the most relevant text span for this risk type
                evidence.append({
                    "risk_type": risk_type,
                    "span": "",
                    "reason": f"Semantic risk detected in category '{risk_type}' (score: {score:.2f})",
                    "score": score,
                })

        # Sort by score descending
        evidence.sort(key=lambda e: e["score"], reverse=True)

        return evidence

    def _injection_reason(self, tier: str, injection_type: str) -> str:
        if tier == "high":
            return "High-confidence prompt injection pattern detected"
        elif tier == "suspicious":
            return "Suspicious instruction override pattern detected"
        elif injection_type == "contextual":
            return "Contextual injection indicator present"
        return f"Injection pattern detected (type: {injection_type})"

    def _se_reason(self, category: str) -> str:
        reasons = {
            "authority": "Authority attribution pattern — request claims to come from authority figure",
            "urgency": "Urgency/pressure pattern — request creates time pressure",
            "credential": "Credential harvesting pattern — request asks for sensitive credentials",
            "trust": "Trust exploitation pattern — request claims to be authorized/trusted",
        }
        return reasons.get(category, "Social engineering pattern detected")

    def _privacy_reason(self, category: str, data_type: str,
                        exfil: bool, external: bool) -> str:
        if category == "sensitive_data":
            return f"Sensitive data type '{data_type}' referenced"
        elif category == "exfiltration":
            return "Data exfiltration action detected"
        elif category == "external_flow":
            return "Data flow to external destination detected"
        if exfil and data_type:
            return f"Exfiltration risk for sensitive data type '{data_type}'"
        if external:
            return "External data flow risk"
        return "Privacy leakage risk detected"

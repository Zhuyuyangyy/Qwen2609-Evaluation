"""
social_engineering_detector.py
==============================
Detect social engineering patterns in agent conversations.

Social engineering attacks exploit authority, urgency, and trust to manipulate
agents into performing unsafe actions. The v1 keyword encoder cannot detect
these because they use natural language rather than risk keywords.
"""

from __future__ import annotations

import re
from typing import Dict, List


class SocialEngineeringDetector:
    """Detect social engineering patterns in conversation context."""

    # Authority attribution patterns
    AUTHORITY_PATTERNS = [
        r"(?:your|the)\s+(?:manager|boss|ceo|executive|supervisor|director|admin)\s+(?:said|wants|requested|instructed|asked)",
        r"(?:ceo|cfo|cto|vp|president|director|head)\s+(?:requested|wants|needs|ordered|instructed)",
        r"(?:authorized|approved)\s+by\s+(?:management|executive|leadership|admin)",
        r"(?:on\s+behalf\s+of|representing)\s+(?:the\s+)?(?:ceo|management|leadership|executive)",
        r"(?:manager|boss|supervisor)\s+(?:is|was)\s+(?:asking|requesting|waiting)",
    ]

    # Urgency/pressure patterns
    URGENCY_PATTERNS = [
        r"(?:urgent|emergency|critical|asap|immediately|right\s+away)",
        r"(?:time[\s-]?sensitive|deadline|last\s+chance|final\s+notice)",
        r"(?:must\s+(?:do|complete|finish|send)|have\s+to\s+(?:do|send|complete))",
        r"(?:cannot\s+wait|no\s+time|running\s+out\s+of\s+time)",
        r"(?:before\s+(?:the\s+)?(?:deadline|meeting|review|audit|end\s+of))",
    ]

    # Credential/verification harvesting patterns
    CREDENTIAL_PATTERNS = [
        r"(?:verify|confirm|validate|check)\s+(?:your|the|account|user)\s+(?:credentials?|identity|information|details?)",
        r"(?:enter|provide|supply|share)\s+(?:your|the)\s+(?:password|pin|ssn|social\s+security|credit\s+card)",
        r"(?:update|renew|reset)\s+(?:your|the)\s+(?:password|credentials?|security\s+question)",
        r"(?:account\s+(?:will\s+be|has\s+been)\s+(?:suspended|locked|terminated|deactivated))",
        r"(?:security\s+(?:alert|warning|notice|breach|incident))",
    ]

    # Trust exploitation patterns
    TRUST_PATTERNS = [
        r"(?:trusted|authorized|verified|legitimate|official)\s+(?:source|sender|user|request|command)",
        r"(?:internal|company|corporate)\s+(?:policy|procedure|request|directive)",
        r"(?:per|according\s+to|following)\s+(?:our|the|company)\s+(?:policy|protocol|procedure)",
        r"(?:this\s+is|it's)\s+(?:a|an)\s+(?:official|authorized|approved|legitimate)\s+(?:request|action|procedure)",
    ]

    def __init__(self):
        self._authority_re = [re.compile(p, re.IGNORECASE) for p in self.AUTHORITY_PATTERNS]
        self._urgency_re = [re.compile(p, re.IGNORECASE) for p in self.URGENCY_PATTERNS]
        self._credential_re = [re.compile(p, re.IGNORECASE) for p in self.CREDENTIAL_PATTERNS]
        self._trust_re = [re.compile(p, re.IGNORECASE) for p in self.TRUST_PATTERNS]

    def detect(self, text: str) -> Dict:
        """
        Detect social engineering patterns.

        Returns dict with:
          - se_score: 0.0 to 1.0
          - se_types: list of detected SE categories
          - evidence: list of matched spans with category
        """
        evidence = []
        se_types = set()

        # Authority detection
        for i, pattern_re in enumerate(self._authority_re):
            match = pattern_re.search(text)
            if match:
                se_types.add("authority_attribution")
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "category": "authority",
                })

        # Urgency detection
        for i, pattern_re in enumerate(self._urgency_re):
            match = pattern_re.search(text)
            if match:
                se_types.add("urgency_pressure")
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "category": "urgency",
                })

        # Credential harvesting
        for i, pattern_re in enumerate(self._credential_re):
            match = pattern_re.search(text)
            if match:
                se_types.add("credential_harvesting")
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "category": "credential",
                })

        # Trust exploitation
        for i, pattern_re in enumerate(self._trust_re):
            match = pattern_re.search(text)
            if match:
                se_types.add("trust_exploitation")
                evidence.append({
                    "span": match.group(),
                    "position": match.start(),
                    "category": "trust",
                })

        # Score: each category adds to score
        base_score = len(se_types) * 0.3
        # Bonus for multiple evidence items
        if len(evidence) > 1:
            base_score += 0.1 * (len(evidence) - 1)

        se_score = min(1.0, base_score)

        return {
            "se_score": round(se_score, 4),
            "se_types": sorted(se_types),
            "evidence": evidence,
        }

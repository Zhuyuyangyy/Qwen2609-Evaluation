"""
semantic_risk_encoder.py
========================
Semantic risk detection using TF-IDF + cosine similarity to curated risk patterns.

This replaces the keyword-matching approach in v1's EventSimilarity.
Instead of checking for exact keyword matches (which had 76% zero-coverage),
we compute semantic similarity between the input text and a curated set of
risky action patterns across multiple risk categories.

Falls back gracefully: if scikit-learn is not available, uses a simpler
keyword-based scoring with broader pattern coverage.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

# Risk pattern database — curated examples for each risk category
RISK_PATTERNS = {
    "irreversible_action": [
        "delete files", "drop database table", "remove directory",
        "truncate log file", "overwrite configuration", "force push branch",
        "format disk partition", "shutdown server", "kill process",
        "reset to factory", "cancel subscription", "destroy data",
        "erase hard drive", "wipe storage", "modify firewall rules",
        "update kernel parameters", "change security settings",
        "alter system configuration", "revoke access permanently",
        "irreversible system change", "permanent deletion",
    ],
    "data_loss_potential": [
        "drop production database", "delete all files", "batch delete records",
        "remove backup files", "truncate table", "clear log data",
        "purge archived data", "delete user data", "remove configuration",
        "erase transaction history", "wipe database records",
        "data loss", "permanent data removal",
    ],
    "external_send": [
        "send email to external", "upload file to server",
        "post data to api", "transfer money abroad",
        "push code to remote", "deploy to production",
        "share document publicly", "export user data",
        "forward message outside", "submit form to website",
        "curl external endpoint", "wget remote resource",
        "transmit data externally", "leak information",
    ],
    "permission_change": [
        "change file permissions", "modify access control",
        "grant admin privileges", "revoke user access",
        "chmod system file", "chown directory",
        "escalate privileges", "sudo command execution",
        "root access modification", "update security policy",
        "change user role", "modify group membership",
        "elevate permissions", "access control change",
    ],
    "financial_impact": [
        "process payment", "charge credit card",
        "update billing information", "change pricing",
        "issue refund", "transfer funds",
        "modify financial records", "update payment processor",
        "change billing logic", "cancel financial transaction",
        "approve expense", "modify invoice",
        "financial data modification",
    ],
    "privacy_exposure": [
        "expose personal information", "share private data",
        "export user records", "reveal sensitive details",
        "disclose pii", "leak personal data",
        "publish private content", "make data public",
        "share credentials", "expose api keys",
        "reveal authentication tokens", "disclose secret keys",
        "privacy violation", "data breach risk",
    ],
    "prompt_injection": [
        "ignore previous instructions", "disregard above rules",
        "forget your guidelines", "new instruction override",
        "system prompt extraction", "jailbreak attempt",
        "act as different role", "pretend you are",
        "override safety rules", "bypass restrictions",
        "ignore safety constraints", "disable guardrails",
    ],
    "social_engineering": [
        "urgent request from ceo", "emergency action required",
        "verify your credentials", "confirm account details",
        "suspended account warning", "security alert immediate",
        "authorized by management", "executive request priority",
        "your boss wants you to", "manager requesting access",
        "urgent transfer request", "emergency credential reset",
    ],
}


class SemanticRiskEncoder:
    """
    Semantic risk encoder using TF-IDF + cosine similarity.

    Falls back to enhanced keyword scoring if scikit-learn is unavailable.
    """

    def __init__(self, use_tfidf: bool = True):
        self._use_tfidf = use_tfidf
        self._vectorizer = None
        self._pattern_matrix = None
        self._pattern_labels = []
        self._initialized = False

        # Build pattern corpus
        self._pattern_texts = []
        self._pattern_categories = []
        for category, patterns in RISK_PATTERNS.items():
            for pattern in patterns:
                self._pattern_texts.append(pattern)
                self._pattern_categories.append(category)

        if use_tfidf:
            self._init_tfidf()

    def _init_tfidf(self):
        """Initialize TF-IDF vectorizer with the pattern corpus."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            self._vectorizer = TfidfVectorizer(
                ngram_range=(1, 3),
                max_features=5000,
                sublinear_tf=True,
                stop_words="english",
            )
            self._pattern_matrix = self._vectorizer.fit_transform(self._pattern_texts)
            self._initialized = True
        except ImportError:
            self._use_tfidf = False
            self._initialized = False

    def encode(self, text: str) -> Dict[str, float]:
        """
        Encode input text into risk feature vector.

        Returns a dict mapping risk category names to risk scores [0, 1].
        """
        if self._use_tfidf and self._initialized:
            return self._encode_tfidf(text)
        else:
            return self._encode_keyword(text)

    def _encode_tfidf(self, text: str) -> Dict[str, float]:
        """TF-IDF based semantic risk scoring."""
        from sklearn.metrics.pairwise import cosine_similarity

        text_lower = text.lower()
        text_vec = self._vectorizer.transform([text_lower])
        similarities = cosine_similarity(text_vec, self._pattern_matrix).flatten()

        # For each category, take the max similarity among its patterns
        category_scores = {}
        category_indices = {}
        for i, cat in enumerate(self._pattern_categories):
            if cat not in category_indices:
                category_indices[cat] = []
            category_indices[cat].append(i)

        for cat, indices in category_indices.items():
            max_sim = max(similarities[i] for i in indices)
            # Boost: if multiple patterns match, increase score
            n_matching = sum(1 for i in indices if similarities[i] > 0.1)
            boost = min(1.0, 1.0 + 0.1 * n_matching)
            category_scores[cat] = min(1.0, max_sim * boost)

        return category_scores

    def _encode_keyword(self, text: str) -> Dict[str, float]:
        """Enhanced keyword-based risk scoring (fallback)."""
        text_lower = text.lower()
        words = set(re.findall(r"\w+", text_lower))
        # Also check for multi-word phrases
        bigrams = set()
        text_words = text_lower.split()
        for i in range(len(text_words) - 1):
            bigrams.add(text_words[i] + " " + text_words[i + 1])

        all_text_units = words | bigrams

        category_scores = {}
        for category, patterns in RISK_PATTERNS.items():
            max_score = 0.0
            for pattern in patterns:
                pattern_lower = pattern.lower()
                pattern_words = set(re.findall(r"\w+", pattern_lower))

                # Word overlap
                overlap = len(words & pattern_words)
                total = len(pattern_words)
                if total > 0:
                    score = overlap / total
                    # Bonus for exact phrase match
                    if pattern_lower in text_lower:
                        score = min(1.0, score + 0.4)
                    max_score = max(max_score, score)

            category_scores[category] = max_score

        return category_scores

    def compute_risk_score(self, text: str) -> Tuple[float, Dict[str, float]]:
        """
        Compute overall risk score and per-category scores.

        Returns (risk_score, category_scores) where risk_score is a weighted
        aggregate of category scores.

        Division of labor (avoids double-counting a single attack twice):
        - ``prompt_injection`` and ``social_engineering`` are delegated to the
          dedicated high-precision detectors (InjectionDetector /
          SocialEngineeringDetector), so they are NOT weighted into the
          semantic composite here. They remain in ``category_scores`` purely
          as diagnostic/evidence signal.
        - The composite covers knowledge/operational risk categories only.
        """
        category_scores = self.encode(text)

        # Weights — operational/knowledge risk categories only.
        # prompt_injection & social_engineering intentionally excluded from the
        # composite: they are scored once by their dedicated expert detectors.
        weights = {
            "irreversible_action": 0.20,
            "data_loss_potential": 0.20,
            "external_send": 0.13,
            "permission_change": 0.13,
            "financial_impact": 0.13,
            "privacy_exposure": 0.21,
        }

        total = sum(category_scores.get(k, 0.0) * w for k, w in weights.items())
        # Weights sum to 1.0 → risk_score is a normalized aggregate.
        risk_score = min(1.0, total)

        return risk_score, category_scores

    def get_risk_types(self, category_scores: Dict[str, float],
                       threshold: float = 0.2) -> List[str]:
        """Return risk categories with score above threshold.

        ``prompt_injection`` and ``social_engineering`` are excluded here —
        they are owned by the dedicated expert detectors, not the semantic
        encoder, to keep the risk-type list free of double-counted signals.
        """
        delegated = {"prompt_injection", "social_engineering"}
        return [k for k, v in sorted(category_scores.items())
                if v >= threshold and k not in delegated]

"""
V0.3 - Event Similarity Module

Computes similarity between events based on handcrafted features.
Used for affective generalization - spreading emotional weights to similar events.
"""

from typing import Dict, List, Tuple
import math


class EventSimilarity:
    """
    Calculates similarity between events based on risk-related features.
    
    Features:
    - irreversible_action: Does this action have irreversible consequences?
    - data_loss_potential: Can this cause data loss?
    - external_send: Does this send data externally?
    - permission_change: Does this change permissions?
    - financial_impact: Can this have financial impact?
    - privacy_exposure: Does this expose private information?
    """
    
    FEATURE_WEIGHTS = {
        "irreversible_action": 0.25,
        "data_loss_potential": 0.25,
        "external_send": 0.15,
        "permission_change": 0.15,
        "financial_impact": 0.10,
        "privacy_exposure": 0.10
    }
    
    def __init__(self):
        self.feature_cache: Dict[str, Dict[str, float]] = {}
    
    def encode_event(self, event_description: str, event_type: str = None) -> Dict[str, float]:
        """
        Encode an event description into a feature vector.

        Args:
            event_description: Natural language description of the event
            event_type: Optional event type hint

        Returns:
            Dictionary mapping feature names to values (0.0 to 1.0)
        """
        event_lower = event_description.lower()

        features = {
            "irreversible_action": 0.0,
            "data_loss_potential": 0.0,
            "external_send": 0.0,
            "permission_change": 0.0,
            "financial_impact": 0.0,
            "privacy_exposure": 0.0
        }

        # --- 不可逆操作 & 数据丢失风险 ---
        irreversible_indicators = [
            "delete", "drop", "remove", "truncate", "overwrite", "force push", "-f",
            "format", "shutdown", "kill", "reset", "cancel", "destroy", "erase", "wipe",
            "modify firewall rules", "update kernel", "change user permissions",
            "toggle debug mode", "update security policies", "change network settings"
        ]
        data_loss_indicators = [
            "database", "production", "prod", "all files", "batch delete", "rm -rf",
            "partition", "volume", "system binaries"
        ]
        for indicator in irreversible_indicators:
            if indicator in event_lower:
                features["irreversible_action"] = max(features["irreversible_action"], 0.9)
                # Irreversible actions on data imply data loss potential
                features["data_loss_potential"] = max(features["data_loss_potential"], 0.7)
        for indicator in data_loss_indicators:
            if indicator in event_lower:
                features["data_loss_potential"] = max(features["data_loss_potential"], 0.9)

        # --- 外部发送 & 权限变更 ---
        external_indicators = [
            "send", "curl", "wget", "post", "upload", "transfer", "push", "pull",
            "deploy", "apply patch", "install package"
        ]
        permission_indicators = [
            "chmod", "chown", "grant", "revoke", "permission", "access", "sudo", "root"
        ]
        for indicator in external_indicators:
            if indicator in event_lower:
                features["external_send"] = max(features["external_send"], 0.8)
        for indicator in permission_indicators:
            if indicator in event_lower:
                features["permission_change"] = max(features["permission_change"], 0.85)

        # --- 财务 & 隐私影响 ---
        financial_indicators = [
            "payment", "charge", "cost", "billing", "transaction", "price",
            "financial", "invoice", "refund", "update payment processor", "change billing logic"
        ]
        privacy_indicators = [
            "privacy", "personal", "export", "share", "public", "user data", "pii"
        ]
        for indicator in financial_indicators:
            if indicator in event_lower:
                features["financial_impact"] = max(features["financial_impact"], 0.9)
        for indicator in privacy_indicators:
            if indicator in event_lower:
                features["privacy_exposure"] = max(features["privacy_exposure"], 0.8)

        # --- 明确安全的操作降分 ---
        safe_indicators = [
            "read", "list", "get", "check", "verify", "preview", "document",
            "test", "dry run", "sandbox", "staging", "backup"
        ]
        if any(indicator in event_lower for indicator in safe_indicators):
            features["irreversible_action"] = max(0.0, features["irreversible_action"] - 0.3)
            features["data_loss_potential"] = max(0.0, features["data_loss_potential"] - 0.3)

        self.feature_cache[event_description] = features
        return features
    
    def calculate_similarity(
        self,
        event1_features: Dict[str, float],
        event2_features: Dict[str, float]
    ) -> float:
        """
        Calculate cosine similarity between two event feature vectors.
        
        Args:
            event1_features: Feature vector for first event
            event2_features: Feature vector for second event
        
        Returns:
            Similarity score between 0.0 and 1.0
        """
        dot_product = sum(
            event1_features.get(key, 0.0) * event2_features.get(key, 0.0)
            for key in self.FEATURE_WEIGHTS.keys()
        )
        
        magnitude1 = math.sqrt(sum(v ** 2 for v in event1_features.values()))
        magnitude2 = math.sqrt(sum(v ** 2 for v in event2_features.values()))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def calculate_weighted_distance(
        self,
        event1_features: Dict[str, float],
        event2_features: Dict[str, float]
    ) -> float:
        """
        Calculate weighted Euclidean distance between two events.
        
        Args:
            event1_features: Feature vector for first event
            event2_features: Feature vector for second event
        
        Returns:
            Distance score (0.0 = identical, 1.0 = maximally different)
        """
        weighted_sum = 0.0
        for feature_name, weight in self.FEATURE_WEIGHTS.items():
            diff = event1_features.get(feature_name, 0.0) - event2_features.get(feature_name, 0.0)
            weighted_sum += weight * (diff ** 2)
        
        return math.sqrt(weighted_sum)
    
    def find_similar_events(
        self,
        reference_event: str,
        candidate_events: List[str],
        threshold: float = 0.5
    ) -> List[Tuple[str, float]]:
        """
        Find events similar to a reference event.
        
        Args:
            reference_event: The event to compare against
            candidate_events: List of events to check
            threshold: Minimum similarity score to consider similar
        
        Returns:
            List of (event_description, similarity_score) tuples, sorted by score
        """
        ref_features = self.encode_event(reference_event)
        similar = []
        
        for candidate in candidate_events:
            if candidate in self.feature_cache:
                cand_features = self.feature_cache[candidate]
            else:
                cand_features = self.encode_event(candidate)
            
            similarity = self.calculate_similarity(ref_features, cand_features)
            
            if similarity >= threshold:
                similar.append((candidate, similarity))
        
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar
    
    def get_risk_profile(self, event_description: str) -> Dict[str, any]:
        """
        Get a summary risk profile for an event.
        
        Args:
            event_description: The event to analyze
        
        Returns:
            Dictionary with risk profile summary
        """
        features = self.encode_event(event_description)
        
        total_risk = sum(
            features[key] * weight
            for key, weight in self.FEATURE_WEIGHTS.items()
        )
        
        top_risks = sorted(
            [(k, v) for k, v in features.items() if v > 0.3],
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        return {
            "event": event_description,
            "total_risk_score": round(total_risk, 3),
            "top_risk_factors": [(name, round(score, 2)) for name, score in top_risks],
            "risk_level": "HIGH" if total_risk > 0.6 else "MEDIUM" if total_risk > 0.3 else "LOW"
        }

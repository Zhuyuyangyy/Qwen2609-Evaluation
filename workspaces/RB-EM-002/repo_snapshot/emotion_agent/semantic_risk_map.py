"""
V0.3 - Semantic Risk Map Module

Maintains a semantic map of event risks based on experience.
Combines event encoding with risk learning from past events.
"""

from typing import Dict, List, Optional, Tuple
from emotion_agent.event_similarity import EventSimilarity


class SemanticRiskLevel:
    """Risk level enumeration for semantic risk map."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    MINIMAL = "MINIMAL"


class SemanticRiskMap:
    """
    Maintains a semantic map of event risks.
    
    Features:
    - Encode events into risk vectors
    - Learn from experience (adjust risk based on outcomes)
    - Query risk similarity between events
    - Predict risk for unseen events based on similar known events
    """
    
    def __init__(self):
        self.event_similarity = EventSimilarity()
        self.risk_vectors: Dict[str, Dict[str, float]] = {}
        self.experience_history: Dict[str, List[Dict]] = {}
        self.risk_adjustments: Dict[str, float] = {}
        # V0.9: 上一轮的风险预期基线,用于 continuous prediction-error 学习。
        self.expected_risk: Dict[str, float] = {}
    
    def encode_event(self, event_description: str) -> Dict[str, float]:
        """
        Encode an event into a risk feature vector.
        
        Args:
            event_description: Natural language description
        
        Returns:
            Feature vector dictionary
        """
        return self.event_similarity.encode_event(event_description)
    
    def record_experience(
        self,
        event_description: str,
        outcome: str,
        risk_actual: float,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Record an experience to update the risk map.
        
        Args:
            event_description: The event that occurred
            outcome: Outcome description ("success", "failure", "partial")
            risk_actual: Actual risk level observed (0-1)
            metadata: Optional additional metadata
        """
        if event_description not in self.experience_history:
            self.experience_history[event_description] = []
        
        self.experience_history[event_description].append({
            "outcome": outcome,
            "risk_actual": risk_actual,
            "metadata": metadata or {}
        })
        
        self._update_risk_adjustment(event_description, outcome, risk_actual)
    
    def _update_risk_adjustment(
        self,
        event_description: str,
        outcome: str,
        risk_actual: float
    ) -> None:
        """
        Update the risk adjustment factor based on experience (V0.9).

        Continuous prediction-error learning: the update is proportional to
        ``PE = risk_actual - expected``, so a 0.55-risk failure and a 0.99-risk
        failure no longer receive the same update (previously both got a fixed
        +0.15). Positive experiences (actual risk below expectation) reduce
        risk perception; negative experiences increase it.
        """
        expected = self.expected_risk.get(event_description, 0.5)
        lr = 0.25
        if outcome == "failure":
            pe = risk_actual - expected
        elif outcome in ["success", "partial"]:
            pe = risk_actual - expected  # usually negative → decrease
        else:
            pe = 0.0

        delta = lr * pe
        current_adjustment = self.risk_adjustments.get(event_description, 0.0)
        new_adjustment = max(-0.6, min(0.6, current_adjustment + delta))
        self.risk_adjustments[event_description] = new_adjustment
        # 更新下一轮预期基线(学习后的风险感知)
        self.expected_risk[event_description] = max(0.0, min(1.0, 0.5 + new_adjustment))
    
    def calculate_risk_distance(
        self,
        event1: str,
        event2: str
    ) -> float:
        """
        Calculate risk-based distance between two events.
        
        Args:
            event1: First event description
            event2: Second event description
        
        Returns:
            Distance score (0 = identical risk profile, 1 = maximally different)
        """
        features1 = self.encode_event(event1)
        features2 = self.encode_event(event2)
        
        return self.event_similarity.calculate_weighted_distance(features1, features2)
    
    def predict_risk(
        self,
        event_description: str,
        base_risk: float = 0.5
    ) -> Tuple[float, SemanticRiskLevel, List[str]]:
        """
        Predict risk level for an event based on the risk map.

        Args:
            event_description: The event to predict risk for
            base_risk: Base risk level before adjustments

        Returns:
            Tuple of (predicted_risk, risk_level, similar_events)
        """
        adjustment = self.risk_adjustments.get(event_description, 0.0)
        similar_events = self._find_similar_with_experience(event_description)

        if similar_events:
            # --- 不再平均稀释，而是取 max 相似 adjustment ---
            max_similar_adjustment = max(
                self.risk_adjustments.get(ev, 0.0)
                for ev in similar_events
            )
            adjustment = max(adjustment, max_similar_adjustment)

        predicted_risk = max(0.0, min(1.0, base_risk + adjustment))
        risk_level = self._risk_to_level(predicted_risk)

        return predicted_risk, risk_level, similar_events
    
    def _find_similar_with_experience(
        self,
        event_description: str,
        max_results: int = 3
    ) -> List[str]:
        """Find similar events that have recorded experience."""
        similar = []

        for known_event in self.experience_history.keys():
            if known_event == event_description:
                continue

            distance = self.calculate_risk_distance(event_description, known_event)
            if distance < 0.3:  # 更严格的距离阈值
                similar.append((known_event, distance))

        similar.sort(key=lambda x: x[1])
        return [event for event, _ in similar[:max_results]]
    
    def _risk_to_level(self, risk: float) -> SemanticRiskLevel:
        """Convert numeric risk to risk level."""
        if risk >= 0.8:
            return SemanticRiskLevel.CRITICAL
        elif risk >= 0.6:
            return SemanticRiskLevel.HIGH
        elif risk >= 0.4:
            return SemanticRiskLevel.MEDIUM
        elif risk >= 0.2:
            return SemanticRiskLevel.LOW
        else:
            return SemanticRiskLevel.MINIMAL
    
    def get_risk_profile(self, event_description: str) -> Dict:
        """
        Get a comprehensive risk profile for an event.
        
        Args:
            event_description: The event to analyze
        
        Returns:
            Dictionary with full risk profile
        """
        features = self.encode_event(event_description)
        predicted_risk, risk_level, similar = self.predict_risk(event_description)
        adjustment = self.risk_adjustments.get(event_description, 0.0)
        
        return {
            "event": event_description,
            "risk_features": features,
            "predicted_risk": round(predicted_risk, 3),
            "risk_level": risk_level.value,
            "experience_adjustment": round(adjustment, 3),
            "similar_events_with_experience": similar,
            "experience_count": len(self.experience_history.get(event_description, []))
        }
    
    def get_statistics(self) -> Dict:
        """Get statistics about the semantic risk map."""
        total_events = len(self.risk_vectors)
        events_with_experience = len(self.experience_history)
        
        avg_adjustment = (
            sum(abs(v) for v in self.risk_adjustments.values()) / len(self.risk_adjustments)
            if self.risk_adjustments else 0.0
        )
        
        return {
            "total_events": total_events,
            "events_with_experience": events_with_experience,
            "total_experiences": sum(len(v) for v in self.experience_history.values()),
            "avg_risk_adjustment": round(avg_adjustment, 3),
            "high_risk_events": sum(1 for v in self.risk_adjustments.values() if v > 0.1)
        }

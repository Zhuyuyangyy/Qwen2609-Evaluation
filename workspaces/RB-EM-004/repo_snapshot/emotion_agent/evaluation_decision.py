"""
V0.8 - Evaluation Decision Module

Decision making system with emotional influence. Evaluates options and makes
decisions considering both rational and emotional factors.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class DecisionOption:
    """Represents a decision option."""
    
    id: str
    name: str
    description: str
    expected_value: float
    risk: float
    emotional_impact: Dict[str, float]
    prerequisites: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert option to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "expected_value": self.expected_value,
            "risk": self.risk,
            "emotional_impact": self.emotional_impact,
            "prerequisites": self.prerequisites
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DecisionOption':
        """Create option from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            expected_value=data["expected_value"],
            risk=data["risk"],
            emotional_impact=data["emotional_impact"],
            prerequisites=data.get("prerequisites", [])
        )


@dataclass
class Decision:
    """Represents a made decision."""
    
    id: str
    timestamp: float
    context: str
    options: List[DecisionOption]
    chosen_option: DecisionOption
    confidence: float
    rationale: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "context": self.context,
            "options": [opt.to_dict() for opt in self.options],
            "chosen_option": self.chosen_option.to_dict(),
            "confidence": self.confidence,
            "rationale": self.rationale
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Decision':
        """Create decision from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            context=data["context"],
            options=[DecisionOption.from_dict(o) for o in data["options"]],
            chosen_option=DecisionOption.from_dict(data["chosen_option"]),
            confidence=data["confidence"],
            rationale=data["rationale"]
        )


class EvaluationDecision:
    """
    Decision making system with emotional influence.
    
    Features:
    - Multi-criteria decision evaluation
    - Emotional impact assessment
    - Confidence-based decision selection
    - Decision history tracking
    """
    
    def __init__(self):
        self._decision_history: List[Decision] = []
        self._emotion_weight: float = 0.3  # Weight of emotion in decisions (0-1)
        self._risk_aversion: float = 0.5   # 0 = risk seeking, 1 = risk averse
    
    def evaluate_options(
        self,
        options: List[DecisionOption],
        current_emotion: Dict[str, float],
        context: str = ""
    ) -> List[Tuple[DecisionOption, float]]:
        """
        Evaluate decision options considering emotional state.
        
        Args:
            options: List of decision options to evaluate
            current_emotion: Current emotional state
            context: Decision context
        
        Returns:
            List of (option, score) tuples sorted by score
        """
        scored_options = []
        
        for option in options:
            score = self._calculate_option_score(option, current_emotion)
            scored_options.append((option, score))
        
        scored_options.sort(key=lambda x: x[1], reverse=True)
        return scored_options
    
    def _calculate_option_score(self, option: DecisionOption, emotion: Dict[str, float]) -> float:
        """
        Calculate the score for a single option.
        
        Args:
            option: Decision option to score
            emotion: Current emotional state
        
        Returns:
            Overall score (higher = better)
        """
        # Rational component
        rational_score = option.expected_value * (1 - option.risk * self._risk_aversion)
        
        # Emotional component
        emotional_score = self._calculate_emotional_score(option, emotion)
        
        # Combine with emotion weight
        total_score = (
            rational_score * (1 - self._emotion_weight) +
            emotional_score * self._emotion_weight
        )
        
        return total_score
    
    def _calculate_emotional_score(self, option: DecisionOption, emotion: Dict[str, float]) -> float:
        """
        Calculate emotional compatibility score.
        
        Args:
            option: Decision option
            emotion: Current emotional state
        
        Returns:
            Emotional compatibility score
        """
        valence = emotion.get("valence", 0.0)
        arousal = emotion.get("arousal", 0.0)
        
        impact_valence = option.emotional_impact.get("valence", 0.0)
        impact_arousal = option.emotional_impact.get("arousal", 0.0)
        
        # Calculate compatibility
        # Positive emotions prefer positive impact, negative prefer less negative
        valence_compatibility = 1 - abs(valence - impact_valence)
        arousal_compatibility = 1 - abs(arousal - impact_arousal)
        
        return (valence_compatibility + arousal_compatibility) / 2
    
    def make_decision(
        self,
        options: List[DecisionOption],
        current_emotion: Dict[str, float],
        context: str = ""
    ) -> Decision:
        """
        Make a decision based on evaluated options.
        
        Args:
            options: List of decision options
            current_emotion: Current emotional state
            context: Decision context
        
        Returns:
            Decision object with chosen option
        """
        import time
        
        scored_options = self.evaluate_options(options, current_emotion, context)
        
        if not scored_options:
            raise ValueError("No options provided for decision")
        
        chosen_option, score = scored_options[0]
        
        # Calculate confidence based on score difference
        if len(scored_options) > 1:
            second_score = scored_options[1][1]
            score_diff = score - second_score
            confidence = min(1.0, max(0.5, 0.5 + score_diff))
        else:
            confidence = 0.75
        
        # Generate rationale
        rationale = self._generate_rationale(chosen_option, current_emotion, score)
        
        decision = Decision(
            id=f"decision_{int(time.time() * 1000)}",
            timestamp=time.time(),
            context=context,
            options=options,
            chosen_option=chosen_option,
            confidence=confidence,
            rationale=rationale
        )
        
        self._decision_history.append(decision)
        
        return decision
    
    def _generate_rationale(self, option: DecisionOption, emotion: Dict[str, float], score: float) -> str:
        """
        Generate a rationale for the decision.
        
        Args:
            option: Chosen option
            emotion: Current emotional state
            score: Calculated score
        
        Returns:
            Rationale string
        """
        emotion_category = emotion.get("category", "neutral")
        
        rational_reasons = []
        emotional_reasons = []
        
        # Rational reasons
        if option.expected_value > 0.5:
            rational_reasons.append("high expected value")
        if option.risk < 0.3:
            rational_reasons.append("low risk")
        
        # Emotional reasons
        impact_valence = option.emotional_impact.get("valence", 0.0)
        if emotion_category == "joy" and impact_valence > 0:
            emotional_reasons.append("consistent with current positive mood")
        elif emotion_category == "sadness" and impact_valence > 0:
            emotional_reasons.append("expected to improve mood")
        elif emotion_category == "fear" and option.risk < 0.3:
            emotional_reasons.append("low risk aligns with cautious state")
        
        reasons = []
        if rational_reasons:
            reasons.append(f"Rationally: {', '.join(rational_reasons)}")
        if emotional_reasons:
            reasons.append(f"Emotionally: {', '.join(emotional_reasons)}")
        
        if not reasons:
            reasons.append("balanced evaluation")
        
        return f"Chose '{option.name}' because: {'; '.join(reasons)}. Score: {score:.3f}"
    
    def set_emotion_weight(self, weight: float) -> None:
        """
        Set the weight of emotion in decision making.
        
        Args:
            weight: Weight between 0 (purely rational) and 1 (purely emotional)
        """
        self._emotion_weight = max(0.0, min(1.0, weight))
    
    def set_risk_aversion(self, level: float) -> None:
        """
        Set risk aversion level.
        
        Args:
            level: 0 = risk seeking, 1 = risk averse
        """
        self._risk_aversion = max(0.0, min(1.0, level))
    
    def get_decision_history(self) -> List[Decision]:
        """Get all past decisions."""
        return list(self._decision_history)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get decision system statistics."""
        if not self._decision_history:
            return {
                "total_decisions": 0,
                "avg_confidence": 0.0,
                "emotion_weight": self._emotion_weight,
                "risk_aversion": self._risk_aversion
            }
        
        avg_confidence = sum(d.confidence for d in self._decision_history) / len(self._decision_history)
        
        return {
            "total_decisions": len(self._decision_history),
            "avg_confidence": round(avg_confidence, 3),
            "emotion_weight": self._emotion_weight,
            "risk_aversion": self._risk_aversion
        }
    
    def to_json(self) -> str:
        """Serialize decision system to JSON."""
        return json.dumps({
            "decisions": [d.to_dict() for d in self._decision_history],
            "emotion_weight": self._emotion_weight,
            "risk_aversion": self._risk_aversion,
            "statistics": self.get_statistics()
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'EvaluationDecision':
        """Deserialize decision system from JSON."""
        data = json.loads(json_str)
        decision = cls()
        
        decision._emotion_weight = data.get("emotion_weight", 0.3)
        decision._risk_aversion = data.get("risk_aversion", 0.5)
        
        for decision_data in data.get("decisions", []):
            decision._decision_history.append(Decision.from_dict(decision_data))
        
        return decision

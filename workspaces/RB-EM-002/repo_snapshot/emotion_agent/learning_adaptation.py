"""
V0.6 - Learning Adaptation Module

Experience-based learning system. Enables the agent to learn from past
experiences and adapt behavior accordingly.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class LearnedRule:
    """Represents a learned rule from experience."""
    
    id: str
    condition: Dict[str, Any]
    action: str
    confidence: float
    experience_count: int
    last_used: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert learned rule to dictionary."""
        return {
            "id": self.id,
            "condition": self.condition,
            "action": self.action,
            "confidence": self.confidence,
            "experience_count": self.experience_count,
            "last_used": self.last_used
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LearnedRule':
        """Create learned rule from dictionary."""
        return cls(
            id=data["id"],
            condition=data["condition"],
            action=data["action"],
            confidence=data["confidence"],
            experience_count=data["experience_count"],
            last_used=data.get("last_used", 0.0)
        )


class LearningAdaptation:
    """
    Experience-based learning system.
    
    Features:
    - Rule learning from experience
    - Confidence-based rule updating
    - Behavioral adaptation
    - Generalization across similar experiences
    """
    
    def __init__(self):
        self._rules: List[LearnedRule] = []
        self._learning_rate: float = 0.1
        self._generalization_threshold: float = 0.7
    
    def learn_from_experience(
        self,
        context: str,
        emotion_category: str,
        valence: float,
        arousal: float,
        outcome: str,
        outcome_valence: float
    ) -> None:
        """
        Learn from an experience by updating or creating rules.
        
        Args:
            context: Context of the experience
            emotion_category: Emotion during the experience
            valence: Valence at the time
            arousal: Arousal at the time
            outcome: Description of the outcome
            outcome_valence: Valence of the outcome (-1 to +1)
        """
        # Check for existing similar rules
        similar_rule = self._find_similar_rule(context, emotion_category)
        
        if similar_rule:
            # Update existing rule
            self._update_rule(similar_rule, outcome, outcome_valence)
        else:
            # Create new rule
            self._create_rule(context, emotion_category, valence, arousal, outcome, outcome_valence)
    
    def _find_similar_rule(self, context: str, emotion_category: str) -> Optional[LearnedRule]:
        """Find a rule with similar context and emotion."""
        for rule in self._rules:
            cond = rule.condition
            if cond.get("emotion_category") == emotion_category:
                # Check context similarity
                context_sim = self._context_similarity(context, cond.get("context", ""))
                if context_sim >= self._generalization_threshold:
                    return rule
        return None
    
    def _context_similarity(self, context1: str, context2: str) -> float:
        """Calculate similarity between two context strings."""
        words1 = set(context1.lower().split())
        words2 = set(context2.lower().split())
        
        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def _update_rule(self, rule: LearnedRule, outcome: str, outcome_valence: float) -> None:
        """Update an existing rule based on new outcome."""
        rule.experience_count += 1
        
        # Update confidence based on outcome valence
        # Positive outcomes increase confidence, negative decrease
        confidence_delta = outcome_valence * self._learning_rate
        rule.confidence = min(1.0, max(0.0, rule.confidence + confidence_delta))
        
        # Update last used timestamp
        rule.last_used = 0  # Simplified: just mark as used
    
    def _create_rule(
        self,
        context: str,
        emotion_category: str,
        valence: float,
        arousal: float,
        outcome: str,
        outcome_valence: float
    ) -> None:
        """Create a new learned rule."""
        rule_id = f"rule_{len(self._rules) + 1}"
        initial_confidence = 0.5 + (outcome_valence * 0.3)
        
        rule = LearnedRule(
            id=rule_id,
            condition={
                "context": context,
                "emotion_category": emotion_category,
                "valence_range": [valence - 0.2, valence + 0.2],
                "arousal_range": [arousal - 0.2, arousal + 0.2]
            },
            action=outcome,
            confidence=min(1.0, max(0.0, initial_confidence)),
            experience_count=1,
            last_used=0.0
        )
        
        self._rules.append(rule)
    
    def get_applicable_rules(self, context: str, emotion_category: str, 
                           valence: float, arousal: float) -> List[LearnedRule]:
        """
        Get rules applicable to the current context and emotional state.
        
        Args:
            context: Current context
            emotion_category: Current emotion category
            valence: Current valence
            arousal: Current arousal
        
        Returns:
            List of applicable rules sorted by confidence
        """
        applicable = []
        
        for rule in self._rules:
            cond = rule.condition
            
            # Check emotion category
            if cond.get("emotion_category") != emotion_category:
                continue
            
            # Check valence range
            val_range = cond.get("valence_range", [-1.0, 1.0])
            if not (val_range[0] <= valence <= val_range[1]):
                continue
            
            # Check arousal range
            arr_range = cond.get("arousal_range", [-1.0, 1.0])
            if not (arr_range[0] <= arousal <= arr_range[1]):
                continue
            
            # Check context similarity
            context_sim = self._context_similarity(context, cond.get("context", ""))
            if context_sim >= 0.5:
                applicable.append((rule, context_sim))
        
        # Sort by confidence and context similarity
        applicable.sort(key=lambda x: (x[0].confidence, x[1]), reverse=True)
        
        return [rule for rule, _ in applicable]
    
    def predict_outcome(self, context: str, emotion_category: str, 
                       valence: float, arousal: float) -> Optional[str]:
        """
        Predict the outcome of an action based on learned rules.
        
        Args:
            context: Current context
            emotion_category: Current emotion category
            valence: Current valence
            arousal: Current arousal
        
        Returns:
            Predicted outcome string, or None if no rules apply
        """
        applicable_rules = self.get_applicable_rules(context, emotion_category, valence, arousal)
        
        if not applicable_rules:
            return None
        
        # Return the action from the highest confidence rule
        return applicable_rules[0].action
    
    def adapt_behavior(self, current_state: Dict[str, float]) -> Dict[str, Any]:
        """
        Generate behavioral adaptation suggestions.
        
        Args:
            current_state: Current emotional and contextual state
        
        Returns:
            Dictionary with adaptation suggestions
        """
        context = current_state.get("context", "")
        emotion_category = current_state.get("category", "neutral")
        valence = current_state.get("valence", 0.0)
        arousal = current_state.get("arousal", 0.0)
        
        rules = self.get_applicable_rules(context, emotion_category, valence, arousal)
        
        if not rules:
            return {"suggestion": "No learned behavior available", "confidence": 0.0}
        
        top_rule = rules[0]
        
        return {
            "suggestion": f"Based on experience: {top_rule.action}",
            "confidence": top_rule.confidence,
            "rule_id": top_rule.id,
            "experience_count": top_rule.experience_count
        }
    
    def forget_low_confidence_rules(self, threshold: float = 0.2) -> int:
        """
        Remove rules with confidence below threshold.
        
        Args:
            threshold: Confidence threshold for forgetting
        
        Returns:
            Number of rules removed
        """
        initial_count = len(self._rules)
        self._rules = [rule for rule in self._rules if rule.confidence >= threshold]
        return initial_count - len(self._rules)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get learning system statistics."""
        if not self._rules:
            return {"total_rules": 0, "avg_confidence": 0.0}
        
        avg_confidence = sum(r.confidence for r in self._rules) / len(self._rules)
        
        return {
            "total_rules": len(self._rules),
            "avg_confidence": round(avg_confidence, 3),
            "learning_rate": self._learning_rate,
            "generalization_threshold": self._generalization_threshold
        }
    
    def to_json(self) -> str:
        """Serialize learning system to JSON."""
        return json.dumps({
            "rules": [rule.to_dict() for rule in self._rules],
            "learning_rate": self._learning_rate,
            "generalization_threshold": self._generalization_threshold,
            "statistics": self.get_statistics()
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'LearningAdaptation':
        """Deserialize learning system from JSON."""
        data = json.loads(json_str)
        learning = cls()
        
        learning._learning_rate = data.get("learning_rate", 0.1)
        learning._generalization_threshold = data.get("generalization_threshold", 0.7)
        
        for rule_data in data.get("rules", []):
            learning._rules.append(LearnedRule.from_dict(rule_data))
        
        return learning

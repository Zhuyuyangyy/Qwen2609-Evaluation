"""Tests for V0.6 Learning Adaptation Module"""

import pytest
import json
from emotion_agent.learning_adaptation import LearningAdaptation, LearnedRule


class TestLearningAdaptation:
    """Test suite for LearningAdaptation class."""
    
    def test_learn_from_experience(self):
        """Test learning from experience."""
        learning = LearningAdaptation()
        learning.learn_from_experience(
            context="Test context",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            outcome="Positive outcome",
            outcome_valence=0.5
        )
        
        stats = learning.get_statistics()
        assert stats["total_rules"] == 1
    
    def test_update_existing_rule(self):
        """Test updating existing rule."""
        learning = LearningAdaptation()
        
        # Learn same context twice
        learning.learn_from_experience(
            context="Same context",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            outcome="Good",
            outcome_valence=0.5
        )
        learning.learn_from_experience(
            context="Same context",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            outcome="Good again",
            outcome_valence=0.5
        )
        
        stats = learning.get_statistics()
        # Should still have 1 rule (updated)
        assert stats["total_rules"] == 1
    
    def test_predict_outcome(self):
        """Test predicting outcome."""
        learning = LearningAdaptation()
        learning.learn_from_experience(
            context="Test",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            outcome="Success",
            outcome_valence=0.5
        )
        
        prediction = learning.predict_outcome("Test", "joy", 0.8, 0.6)
        assert prediction is not None
        assert "Success" in prediction
    
    def test_adapt_behavior(self):
        """Test behavioral adaptation."""
        learning = LearningAdaptation()
        learning.learn_from_experience(
            context="Test",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            outcome="Do X",
            outcome_valence=0.5
        )
        
        state = {"context": "Test", "category": "joy", "valence": 0.8, "arousal": 0.6}
        adaptation = learning.adapt_behavior(state)
        
        assert "suggestion" in adaptation
        assert adaptation["confidence"] > 0
    
    def test_forget_low_confidence_rules(self):
        """Test forgetting low confidence rules."""
        learning = LearningAdaptation()
        learning.learn_from_experience(
            context="Test",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            outcome="Bad",
            outcome_valence=-0.9
        )
        
        # Rule should have low confidence after negative outcome
        initial_count = learning.get_statistics()["total_rules"]
        removed = learning.forget_low_confidence_rules(threshold=0.3)
        
        assert removed == initial_count
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        learning = LearningAdaptation()
        
        stats = learning.get_statistics()
        assert "total_rules" in stats
        assert "avg_confidence" in stats
    
    def test_serialization(self):
        """Test JSON serialization."""
        learning = LearningAdaptation()
        learning.learn_from_experience(
            context="Test",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            outcome="Success",
            outcome_valence=0.5
        )
        
        json_str = learning.to_json()
        restored = LearningAdaptation.from_json(json_str)
        
        stats = restored.get_statistics()
        assert stats["total_rules"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

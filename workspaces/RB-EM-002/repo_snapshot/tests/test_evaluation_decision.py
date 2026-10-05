"""Tests for V0.8 Evaluation Decision Module"""

import pytest
import json
from emotion_agent.evaluation_decision import EvaluationDecision, DecisionOption, Decision


class TestEvaluationDecision:
    """Test suite for EvaluationDecision class."""
    
    def test_make_decision(self):
        """Test making a decision."""
        decision = EvaluationDecision()
        
        options = [
            DecisionOption(
                id="opt1",
                name="Option A",
                description="High value, low risk",
                expected_value=0.8,
                risk=0.2,
                emotional_impact={"valence": 0.5},
                prerequisites=[]
            ),
            DecisionOption(
                id="opt2",
                name="Option B",
                description="Low value, high risk",
                expected_value=0.3,
                risk=0.7,
                emotional_impact={"valence": -0.3},
                prerequisites=[]
            )
        ]
        
        emotion = {"valence": 0.5, "arousal": 0.3, "category": "joy"}
        result = decision.make_decision(options, emotion)
        
        assert result is not None
        assert result.chosen_option.name == "Option A"
    
    def test_evaluate_options(self):
        """Test option evaluation."""
        decision = EvaluationDecision()
        
        options = [
            DecisionOption(
                id="opt1",
                name="Good",
                description="Good option",
                expected_value=0.9,
                risk=0.1,
                emotional_impact={},
                prerequisites=[]
            ),
            DecisionOption(
                id="opt2",
                name="Bad",
                description="Bad option",
                expected_value=0.1,
                risk=0.9,
                emotional_impact={},
                prerequisites=[]
            )
        ]
        
        emotion = {"valence": 0.0, "arousal": 0.0}
        scored = decision.evaluate_options(options, emotion)
        
        assert len(scored) == 2
        assert scored[0][0].name == "Good"
    
    def test_emotion_influence(self):
        """Test emotional influence on decisions."""
        decision = EvaluationDecision()
        decision.set_emotion_weight(0.8)  # High emotion weight
        
        options = [
            DecisionOption(
                id="opt1",
                name="Positive",
                description="Positive impact",
                expected_value=0.5,
                risk=0.5,
                emotional_impact={"valence": 0.8},
                prerequisites=[]
            ),
            DecisionOption(
                id="opt2",
                name="Negative",
                description="Negative impact",
                expected_value=0.7,
                risk=0.3,
                emotional_impact={"valence": -0.8},
                prerequisites=[]
            )
        ]
        
        emotion = {"valence": 0.5, "arousal": 0.3, "category": "joy"}
        result = decision.make_decision(options, emotion)
        
        # With high emotion weight, should prefer positive emotional impact
        assert result.chosen_option.name == "Positive"
    
    def test_set_emotion_weight(self):
        """Test setting emotion weight."""
        decision = EvaluationDecision()
        
        decision.set_emotion_weight(0.7)
        stats = decision.get_statistics()
        
        assert stats["emotion_weight"] == 0.7
    
    def test_set_risk_aversion(self):
        """Test setting risk aversion."""
        decision = EvaluationDecision()
        
        decision.set_risk_aversion(0.8)
        stats = decision.get_statistics()
        
        assert stats["risk_aversion"] == 0.8
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        decision = EvaluationDecision()
        
        stats = decision.get_statistics()
        assert "total_decisions" in stats
        assert "avg_confidence" in stats
        assert "emotion_weight" in stats
    
    def test_serialization(self):
        """Test JSON serialization."""
        decision = EvaluationDecision()
        
        options = [
            DecisionOption(
                id="opt1",
                name="Test",
                description="Test",
                expected_value=0.7,
                risk=0.3,
                emotional_impact={},
                prerequisites=[]
            )
        ]
        
        emotion = {"valence": 0.0, "arousal": 0.0}
        decision.make_decision(options, emotion)
        
        json_str = decision.to_json()
        restored = EvaluationDecision.from_json(json_str)
        
        stats = restored.get_statistics()
        assert stats["total_decisions"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

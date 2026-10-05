"""Tests for V0.4 Conflict & Hesitation Modules"""

import pytest
from emotion_agent.conflict_detector import ConflictDetector, ConflictLevel
from emotion_agent.hesitation_policy import HesitationPolicy, ActionType
from emotion_agent.counterfactual_simulator import CounterfactualSimulator, OutcomeType


class TestConflictDetector:
    """Test suite for ConflictDetector class."""
    
    def test_detect_no_conflict(self):
        """Test detecting no conflict scenario."""
        detector = ConflictDetector()
        assessment = detector.detect_conflict(
            "read log file",
            {"threat": 0.1, "confidence": 0.8}
        )
        
        assert assessment.level == ConflictLevel.NONE
    
    def test_detect_high_conflict(self):
        """Test detecting high conflict scenario."""
        detector = ConflictDetector()
        assessment = detector.detect_conflict(
            "batch delete production database",
            {"threat": 0.7, "confidence": 0.4}
        )
        
        assert assessment.level in [ConflictLevel.LOW, ConflictLevel.MEDIUM, ConflictLevel.HIGH, ConflictLevel.CRITICAL]
        assert len(assessment.recommendations) > 0
    
    def test_conflict_recommendations(self):
        """Test conflict recommendations."""
        detector = ConflictDetector()
        assessment = detector.detect_conflict(
            "force push to main",
            {"anxiety": 0.6, "control_need": 0.7}
        )
        
        assert "backup" in str(assessment.recommendations).lower()


class TestHesitationPolicy:
    """Test suite for HesitationPolicy class."""
    
    def test_generate_no_actions_for_none(self):
        """Test no actions for no conflict."""
        policy = HesitationPolicy()
        actions = policy.generate_intermediate_actions(
            ConflictLevel.NONE,
            "read file"
        )
        
        assert len(actions) == 0
    
    def test_generate_actions_for_high_conflict(self):
        """Test generating actions for high conflict."""
        policy = HesitationPolicy()
        actions = policy.generate_intermediate_actions(
            ConflictLevel.HIGH,
            "batch delete files",
            {"control_need": 0.7}
        )
        
        assert len(actions) > 0
        assert any(a.action_type == ActionType.BACKUP for a in actions)
    
    def test_should_proceed(self):
        """Test should proceed decision."""
        policy = HesitationPolicy()
        actions = policy.generate_intermediate_actions(
            ConflictLevel.MEDIUM,
            "delete file"
        )
        
        completed = [ActionType.BACKUP]
        decision = policy.should_proceed(actions, completed)
        
        assert "should_proceed" in decision


class TestCounterfactualSimulator:
    """Test suite for CounterfactualSimulator class."""
    
    def test_simulate_outcomes(self):
        """Test simulating outcomes."""
        sim = CounterfactualSimulator()
        outcomes = sim.simulate_outcomes("delete file")
        
        assert len(outcomes) > 0
        assert any(o.outcome_type == OutcomeType.SUCCESS for o in outcomes)
    
    def test_simulate_dangerous_action(self):
        """Test simulating dangerous action."""
        sim = CounterfactualSimulator()
        outcomes = sim.simulate_outcomes("batch delete production database")
        
        assert any(o.outcome_type == OutcomeType.CATASTROPHIC for o in outcomes)
    
    def test_generate_risk_explanation(self):
        """Test generating risk explanation."""
        sim = CounterfactualSimulator()
        explanation = sim.generate_risk_explanation("delete file")
        
        assert len(explanation.main_risks) > 0
        assert len(explanation.mitigation_suggestions) > 0
    
    def test_what_if_analysis(self):
        """Test what-if analysis."""
        sim = CounterfactualSimulator()
        analysis = sim.what_if_analysis(
            "delete file",
            "if backup exists"
        )
        
        assert "adjusted_outcomes" in analysis
        assert "expected_impact" in analysis


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

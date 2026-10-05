"""Tests for Main AffectiveAgent Class"""

import pytest
import json
from emotion_agent.agent import AffectiveAgent


class TestAffectiveAgent:
    """Test suite for AffectiveAgent class."""
    
    def test_initialization(self):
        """Test agent initialization."""
        agent = AffectiveAgent(agent_id="test_agent")
        
        assert agent._agent_id == "test_agent"
        state = agent.get_state()
        assert state["agent_id"] == "test_agent"
        assert state["cycle_count"] == 0
    
    def test_perceive(self):
        """Test perceiving an event."""
        agent = AffectiveAgent()
        
        agent.perceive("Happy event", valence_delta=0.5, arousal_delta=0.3)
        
        state = agent.get_state()
        assert state["emotional_state"]["valence"] == 0.5
        assert state["emotional_state"]["arousal"] == 0.3
    
    def test_feel(self):
        """Test feeling an emotion."""
        agent = AffectiveAgent()
        
        agent.feel("joy", intensity=1.0)
        
        state = agent.get_state()
        assert state["emotional_state"]["category"] == "joy"
    
    def test_respond(self):
        """Test generating a response."""
        agent = AffectiveAgent()
        agent.feel("joy")
        
        response = agent.respond()
        
        assert "text" in response
        assert "nonverbal_cues" in response
        assert "action_tendency" in response
    
    def test_add_goal(self):
        """Test adding a goal."""
        agent = AffectiveAgent()
        
        goal_id = agent.add_goal("Learn Python", "Master Python programming", priority=0.8)
        
        assert goal_id is not None
        priority_goal = agent.get_priority_goal()
        assert priority_goal is not None
        assert priority_goal["name"] == "Learn Python"
    
    def test_update_goal_progress(self):
        """Test updating goal progress."""
        agent = AffectiveAgent()
        goal_id = agent.add_goal("Test Goal", "Test")
        
        result = agent.update_goal_progress(goal_id, 0.5)
        
        assert result is True
    
    def test_add_social_entity(self):
        """Test adding a social entity."""
        agent = AffectiveAgent()
        
        agent.add_social_entity("user1", "Alice", "friend")
        
        state = agent.get_state()
        assert state["social_statistics"]["total_entities"] == 1
    
    def test_interact(self):
        """Test social interaction."""
        agent = AffectiveAgent()
        agent.add_social_entity("user1", "Alice", "friend")
        agent.feel("joy")
        
        result = agent.interact("user1", cue="smile")
        
        assert "social_response" in result
        assert "empathy" in result
    
    def test_learn(self):
        """Test learning from experience."""
        agent = AffectiveAgent()
        agent.feel("joy")
        
        agent.learn("Test context", "Good outcome", 0.5)
        
        state = agent.get_state()
        assert state["learning_statistics"]["total_rules"] >= 1
    
    def test_adapt(self):
        """Test behavioral adaptation."""
        agent = AffectiveAgent()
        agent.feel("joy")
        agent.learn("Test", "Do X", 0.5)
        
        adaptation = agent.adapt()
        
        assert "suggestion" in adaptation
    
    def test_regulate(self):
        """Test emotional regulation."""
        agent = AffectiveAgent()
        # Set high arousal state
        agent.perceive("Scary event", valence_delta=-0.5, arousal_delta=0.9)
        
        result = agent.regulate()
        
        assert "before" in result
        assert "after" in result
    
    def test_decide(self):
        """Test decision making."""
        agent = AffectiveAgent()
        
        options = [
            {"name": "Option A", "expected_value": 0.8, "risk": 0.2},
            {"name": "Option B", "expected_value": 0.3, "risk": 0.7}
        ]
        
        result = agent.decide(options)
        
        assert "chosen_option" in result
        assert "confidence" in result
        assert "rationale" in result
    
    def test_update_cycle(self):
        """Test update cycle."""
        agent = AffectiveAgent()
        
        result = agent.update()
        
        assert "cycle" in result
        assert result["cycle"] == 1
        assert "emotional_state" in result
    
    def test_reset(self):
        """Test resetting the agent."""
        agent = AffectiveAgent()
        agent.feel("joy")
        agent.add_goal("Test", "Test")
        
        agent.reset()
        
        state = agent.get_state()
        assert state["cycle_count"] == 0
        assert state["emotional_state"]["category"] == "neutral"
    
    def test_to_json(self):
        """Test JSON serialization."""
        agent = AffectiveAgent()
        agent.feel("joy")
        
        json_str = agent.to_json()
        
        assert isinstance(json_str, str)
        # Parse to verify valid JSON
        data = json.loads(json_str)
        assert "agent_id" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for V0.3 Affective Response Module"""

import pytest
from emotion_agent.affective_response import AffectiveResponse


class TestAffectiveResponse:
    """Test suite for AffectiveResponse class."""
    
    def test_generate_response_joy(self):
        """Test generating response for joy emotion."""
        response = AffectiveResponse(seed=42)
        result = response.generate_response("joy", 0.8, context="Good news!")
        
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_generate_response_deterministic(self):
        """Test that responses are deterministic given same input."""
        response1 = AffectiveResponse(seed=42)
        response2 = AffectiveResponse(seed=42)
        
        result1 = response1.generate_response("sadness", 0.6, context="Bad day")
        result2 = response2.generate_response("sadness", 0.6, context="Bad day")
        
        assert result1 == result2
    
    def test_generate_response_intensity(self):
        """Test that intensity affects response selection."""
        response = AffectiveResponse(seed=42)
        
        low_intensity = response.generate_response("anger", 0.1)
        high_intensity = response.generate_response("anger", 0.9)
        
        # Different intensity should give different responses
        assert low_intensity != high_intensity
    
    def test_generate_nonverbal_cues(self):
        """Test generating nonverbal cues."""
        response = AffectiveResponse()
        cues = response.generate_nonverbal_cues("joy", 0.7)
        
        assert "facial_expression" in cues
        assert "posture" in cues
        assert "tone" in cues
        assert cues["facial_expression"] == "smile"
    
    def test_generate_action_tendency(self):
        """Test generating action tendency."""
        response = AffectiveResponse()
        
        tendency = response.generate_action_tendency("fear")
        assert "avoid" in tendency
        
        tendency = response.generate_action_tendency("joy")
        assert "approach" in tendency
    
    def test_unknown_emotion(self):
        """Test handling unknown emotion category."""
        response = AffectiveResponse()
        result = response.generate_response("unknown_emotion", 0.5)
        
        assert isinstance(result, str)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

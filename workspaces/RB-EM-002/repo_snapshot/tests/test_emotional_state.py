"""Tests for V0.1 Emotional State Module"""

import pytest
import json
from emotion_agent.emotional_state import EmotionalState


class TestEmotionalState:
    """Test suite for EmotionalState class."""
    
    def test_initial_state(self):
        """Test initial state is neutral."""
        state = EmotionalState()
        assert state.valence == 0.0
        assert state.arousal == 0.0
        assert state.dominance == 0.0
        assert state.intensity == 0.0
        assert state.category == "neutral"
    
    def test_update_from_dimensions(self):
        """Test updating emotional state from dimensions."""
        state = EmotionalState()
        state.update_from_dimensions(0.5, 0.3, 0.2)
        
        assert state.valence == 0.5
        assert state.arousal == 0.3
        assert state.dominance == 0.2
        assert state.intensity > 0.0
    
    def test_update_from_category_joy(self):
        """Test updating to joy emotion."""
        state = EmotionalState()
        state.update_from_category("joy", intensity=1.0)
        
        assert state.valence > 0
        assert state.arousal > 0
        assert state.category == "joy"
    
    def test_clamp_values(self):
        """Test that values are clamped between -1 and 1."""
        state = EmotionalState()
        state.update_from_dimensions(2.0, -2.0, 1.5)
        
        assert state.valence == 1.0
        assert state.arousal == -1.0
        assert state.dominance == 1.0
    
    def test_update_category(self):
        """Test automatic category update."""
        state = EmotionalState()
        state.update_from_dimensions(-0.7, 0.7, 0.5)
        
        assert state.category == "anger"
    
    def test_get_state(self):
        """Test get_state method returns correct dictionary."""
        state = EmotionalState()
        state.update_from_category("sadness")
        
        result = state.get_state()
        assert "valence" in result
        assert "arousal" in result
        assert "dominance" in result
        assert "intensity" in result
        assert "category" in result
        assert result["category"] == "sadness"
    
    def test_history(self):
        """Test history recording."""
        state = EmotionalState()
        state.update_from_dimensions(0.3, 0.2, 0.1)
        state.update_from_dimensions(-0.2, 0.1, -0.1)
        
        history = state.get_history()
        assert len(history) == 2
    
    def test_reset(self):
        """Test reset method."""
        state = EmotionalState()
        state.update_from_category("anger")
        state.reset()
        
        assert state.valence == 0.0
        assert state.arousal == 0.0
        assert state.dominance == 0.0
        assert state.category == "neutral"
    
    def test_serialization(self):
        """Test JSON serialization and deserialization."""
        state = EmotionalState()
        state.update_from_category("joy")
        
        json_str = state.to_json()
        assert isinstance(json_str, str)
        
        restored = EmotionalState.from_json(json_str)
        assert restored.category == "joy"
        assert abs(restored.valence - state.valence) < 0.001
    
    def test_invalid_emotion_category(self):
        """Test handling of invalid emotion category."""
        state = EmotionalState()
        with pytest.raises(ValueError):
            state.update_from_category("invalid_emotion")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

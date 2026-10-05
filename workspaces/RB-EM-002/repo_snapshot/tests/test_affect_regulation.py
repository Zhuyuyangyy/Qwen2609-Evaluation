"""Tests for V0.7 Affect Regulation Module"""

import pytest
import json
from emotion_agent.affect_regulation import AffectRegulation, RegulationStrategy


class TestAffectRegulation:
    """Test suite for AffectRegulation class."""
    
    def test_initialization(self):
        """Test initial state."""
        regulation = AffectRegulation()
        
        assert regulation.get_statistics()["energy_level"] == 1.0
        assert regulation.get_statistics()["auto_regulate_enabled"] is True
    
    def test_select_strategy(self):
        """Test strategy selection."""
        regulation = AffectRegulation()
        
        strategy = regulation.select_strategy("anger", 0.7)
        assert strategy is not None
        assert "anger" in strategy.target_emotions or "all" in strategy.target_emotions
    
    def test_apply_strategy(self):
        """Test applying a regulation strategy."""
        regulation = AffectRegulation()
        current_state = {"valence": -0.7, "arousal": 0.8, "dominance": 0.5}
        
        strategy = regulation.select_strategy("anger", 0.8)
        new_state = regulation.apply_strategy(strategy.id, current_state)
        
        # Arousal should decrease
        assert new_state["arousal"] < current_state["arousal"]
    
    def test_auto_regulate(self):
        """Test automatic regulation."""
        regulation = AffectRegulation()
        
        # Create a state that needs regulation (high arousal)
        high_arousal_state = {
            "valence": 0.5,
            "arousal": 0.9,
            "dominance": 0.3,
            "intensity": 0.9,
            "category": "fear"
        }
        
        regulated_state = regulation.auto_regulate(high_arousal_state)
        
        # Should have applied regulation
        assert regulated_state["arousal"] < 0.9
    
    def test_energy_consumption(self):
        """Test energy consumption when applying strategies."""
        regulation = AffectRegulation(energy_level=1.0)
        current_state = {"valence": -0.7, "arousal": 0.8, "dominance": 0.5}
        
        strategy = regulation.select_strategy("anger", 0.8)
        regulation.apply_strategy(strategy.id, current_state)
        
        stats = regulation.get_statistics()
        assert stats["energy_level"] < 1.0
    
    def test_replenish_energy(self):
        """Test energy replenishment."""
        regulation = AffectRegulation(energy_level=0.5)
        
        regulation.replenish_energy(0.3)
        stats = regulation.get_statistics()
        
        assert stats["energy_level"] == 0.8
    
    def test_disable_auto_regulate(self):
        """Test disabling automatic regulation."""
        regulation = AffectRegulation()
        regulation.set_auto_regulate(False)
        
        high_arousal_state = {
            "valence": 0.5,
            "arousal": 0.9,
            "dominance": 0.3,
            "intensity": 0.9,
            "category": "fear"
        }
        
        regulated_state = regulation.auto_regulate(high_arousal_state)
        
        # Should not have changed
        assert regulated_state == high_arousal_state
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        regulation = AffectRegulation()
        
        stats = regulation.get_statistics()
        assert "energy_level" in stats
        assert "auto_regulate_enabled" in stats
        assert "total_strategies" in stats
    
    def test_serialization(self):
        """Test JSON serialization."""
        regulation = AffectRegulation()
        current_state = {"valence": -0.7, "arousal": 0.8, "dominance": 0.5}
        strategy = regulation.select_strategy("anger", 0.8)
        regulation.apply_strategy(strategy.id, current_state)
        
        json_str = regulation.to_json()
        restored = AffectRegulation.from_json(json_str)
        
        stats = restored.get_statistics()
        assert stats["regulation_attempts"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

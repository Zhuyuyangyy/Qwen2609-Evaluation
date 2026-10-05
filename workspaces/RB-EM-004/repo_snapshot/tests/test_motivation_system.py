"""Tests for V0.4 Motivation System Module"""

import pytest
import json
from emotion_agent.motivation_system import MotivationSystem, Goal, Drive


class TestMotivationSystem:
    """Test suite for MotivationSystem class."""
    
    def test_initialization(self):
        """Test initial state has default drives."""
        system = MotivationSystem()
        drives = system.get_drives()
        
        assert "exploration" in drives
        assert "social" in drives
        assert "achievement" in drives
        assert "safety" in drives
        assert "curiosity" in drives
    
    def test_add_goal(self):
        """Test adding a goal."""
        system = MotivationSystem()
        goal_id = system.add_goal(
            name="Test Goal",
            description="Test description",
            priority=0.8
        )
        
        assert goal_id is not None
        goals = system.get_all_goals()
        assert len(goals) == 1
        assert goals[0].name == "Test Goal"
    
    def test_update_goal_progress(self):
        """Test updating goal progress."""
        system = MotivationSystem()
        goal_id = system.add_goal("Test Goal", "Test")
        
        result = system.update_goal_progress(goal_id, 0.5)
        assert result is True
        
        goals = system.get_all_goals()
        assert goals[0].progress == 0.5
    
    def test_remove_goal(self):
        """Test removing a goal."""
        system = MotivationSystem()
        goal_id = system.add_goal("Test Goal", "Test")
        
        result = system.remove_goal(goal_id)
        assert result is True
        
        goals = system.get_all_goals()
        assert len(goals) == 0
    
    def test_update_drive_level(self):
        """Test updating drive level."""
        system = MotivationSystem()
        
        system.update_drive_level("exploration", 0.3)
        drives = system.get_drives()
        
        assert drives["exploration"].level == 0.8  # 0.5 + 0.3
    
    def test_decay_drives(self):
        """Test drive decay."""
        system = MotivationSystem()
        
        initial_level = system.get_drives()["exploration"].level
        system.decay_drives()
        new_level = system.get_drives()["exploration"].level
        
        assert new_level < initial_level
    
    def test_generate_goals_from_drives(self):
        """Test goal generation from drives."""
        system = MotivationSystem()
        
        # Boost drive above threshold
        system.update_drive_level("exploration", 0.3)  # 0.5 + 0.3 = 0.8 > 0.7 threshold
        
        new_goals = system.generate_goals_from_drives()
        
        assert len(new_goals) >= 1
    
    def test_get_priority_goal(self):
        """Test getting priority goal."""
        system = MotivationSystem()
        system.add_goal("High Priority", "Desc", priority=0.9)
        system.add_goal("Low Priority", "Desc", priority=0.1)
        
        priority_goal = system.get_priority_goal({})
        assert priority_goal is not None
        assert priority_goal.name == "High Priority"
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        system = MotivationSystem()
        system.add_goal("Test", "Desc")
        
        stats = system.get_statistics()
        assert "total_goals" in stats
        assert "active_goals" in stats
        assert stats["total_goals"] == 1
    
    def test_serialization(self):
        """Test JSON serialization."""
        system = MotivationSystem()
        system.add_goal("Test", "Desc")
        
        json_str = system.to_json()
        restored = MotivationSystem.from_json(json_str)
        
        goals = restored.get_all_goals()
        assert len(goals) == 1
        assert goals[0].name == "Test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

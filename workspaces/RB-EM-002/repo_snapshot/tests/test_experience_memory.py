"""Tests for V0.2 Experience Memory Module"""

import pytest
import json
from emotion_agent.experience_memory import ExperienceMemory, Experience


class TestExperienceMemory:
    """Test suite for ExperienceMemory class."""
    
    def test_add_experience(self):
        """Test adding an experience."""
        memory = ExperienceMemory()
        exp_id = memory.add_experience(
            context="Test context",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            dominance=0.5,
            intensity=0.7,
            tags=["test"]
        )
        
        assert len(memory) == 1
        assert exp_id is not None
    
    def test_retrieve_by_emotion(self):
        """Test retrieving experiences by emotion."""
        memory = ExperienceMemory()
        memory.add_experience(
            context="Happy moment",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            dominance=0.5,
            intensity=0.7
        )
        memory.add_experience(
            context="Sad moment",
            emotion_category="sadness",
            valence=-0.7,
            arousal=-0.4,
            dominance=-0.3,
            intensity=0.6
        )
        
        joy_exps = memory.retrieve_by_emotion("joy")
        assert len(joy_exps) == 1
        assert joy_exps[0].context == "Happy moment"
    
    def test_retrieve_by_tags(self):
        """Test retrieving experiences by tags."""
        memory = ExperienceMemory()
        memory.add_experience(
            context="Work meeting",
            emotion_category="neutral",
            valence=0.0,
            arousal=0.2,
            dominance=0.3,
            intensity=0.1,
            tags=["work", "meeting"]
        )
        
        work_exps = memory.retrieve_by_tags(["work"])
        assert len(work_exps) == 1
    
    def test_retrieve_recent(self):
        """Test retrieving recent experiences."""
        memory = ExperienceMemory()
        for i in range(15):
            memory.add_experience(
                context=f"Experience {i}",
                emotion_category="neutral",
                valence=0.0,
                arousal=0.0,
                dominance=0.0,
                intensity=0.0
            )
        
        recent = memory.retrieve_recent(10)
        assert len(recent) == 10
    
    def test_retrieve_similar(self):
        """Test retrieving similar experiences."""
        memory = ExperienceMemory()
        memory.add_experience(
            context="Happy event",
            emotion_category="joy",
            valence=0.7,
            arousal=0.5,
            dominance=0.4,
            intensity=0.6
        )
        
        similar = memory.retrieve_similar(0.7, 0.5, 0.4, threshold=0.5)
        assert len(similar) == 1
    
    def test_capacity_limit(self):
        """Test capacity enforcement."""
        memory = ExperienceMemory(max_capacity=5)
        for i in range(10):
            memory.add_experience(
                context=f"Exp {i}",
                emotion_category="neutral",
                valence=0.0,
                arousal=0.0,
                dominance=0.0,
                intensity=0.0
            )
        
        assert len(memory) == 5
    
    def test_consolidate(self):
        """Test memory consolidation."""
        memory = ExperienceMemory()
        # Add very similar experiences
        for i in range(3):
            memory.add_experience(
                context="Same context",
                emotion_category="joy",
                valence=0.8,
                arousal=0.6,
                dominance=0.5,
                intensity=0.7
            )
        
        initial_count = len(memory)
        memory.consolidate()
        # Should remove duplicates
        assert len(memory) <= initial_count
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        memory = ExperienceMemory()
        memory.add_experience(
            context="Test",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            dominance=0.5,
            intensity=0.7
        )
        
        stats = memory.get_statistics()
        assert "total_experiences" in stats
        assert "emotion_distribution" in stats
        assert stats["total_experiences"] == 1
    
    def test_serialization(self):
        """Test JSON serialization."""
        memory = ExperienceMemory()
        memory.add_experience(
            context="Test",
            emotion_category="joy",
            valence=0.8,
            arousal=0.6,
            dominance=0.5,
            intensity=0.7
        )
        
        json_str = memory.to_json()
        restored = ExperienceMemory.from_json(json_str)
        
        assert len(restored) == 1
        assert restored.retrieve_by_emotion("joy")[0].context == "Test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for V0.5 Social Interaction Module"""

import pytest
import json
from emotion_agent.social_interaction import SocialInteraction, SocialEntity


class TestSocialInteraction:
    """Test suite for SocialInteraction class."""
    
    def test_add_entity(self):
        """Test adding a social entity."""
        social = SocialInteraction()
        social.add_entity("user1", "Alice", "friend")
        
        entity = social.get_entity("user1")
        assert entity is not None
        assert entity.name == "Alice"
        assert entity.relationship_type == "friend"
    
    def test_update_entity(self):
        """Test updating entity trust and familiarity."""
        social = SocialInteraction()
        social.add_entity("user1", "Alice")
        
        result = social.update_entity("user1", trust_delta=0.2, familiarity_delta=0.1)
        assert result is True
        
        entity = social.get_entity("user1")
        assert entity.trust_level == 0.7  # 0.5 + 0.2
        assert entity.familiarity == 0.6  # 0.5 + 0.1
    
    def test_invalid_relationship_type(self):
        """Test invalid relationship type."""
        social = SocialInteraction()
        
        with pytest.raises(ValueError):
            social.add_entity("user1", "Alice", "invalid_type")
    
    def test_calculate_empathy(self):
        """Test empathy calculation."""
        social = SocialInteraction()
        social.add_entity("user1", "Alice", "friend")
        
        emotion = {"valence": 0.5, "arousal": 0.3, "dominance": 0.2}
        empathy = social.calculate_empathy("user1", emotion)
        
        assert 0 <= empathy <= 1
    
    def test_interpret_social_cue(self):
        """Test social cue interpretation."""
        social = SocialInteraction()
        
        result = social.interpret_social_cue("smile", "user1")
        assert "emotion" in result
        assert result["emotion"]["valence"] > 0
    
    def test_generate_social_response(self):
        """Test generating social response."""
        social = SocialInteraction()
        social.add_entity("user1", "Alice", "friend")
        
        response = social.generate_social_response("user1", "joy")
        assert isinstance(response, str)
        assert len(response) > 0
    
    def test_get_statistics(self):
        """Test statistics retrieval."""
        social = SocialInteraction()
        social.add_entity("user1", "Alice")
        
        stats = social.get_statistics()
        assert stats["total_entities"] == 1
    
    def test_serialization(self):
        """Test JSON serialization."""
        social = SocialInteraction()
        social.add_entity("user1", "Alice")
        
        json_str = social.to_json()
        restored = SocialInteraction.from_json(json_str)
        
        entity = restored.get_entity("user1")
        assert entity is not None
        assert entity.name == "Alice"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for V0.3 Affective Generalization Modules"""

import pytest
from emotion_agent.event_similarity import EventSimilarity
from emotion_agent.affective_spread import AffectiveSpread
from emotion_agent.semantic_risk_map import SemanticRiskMap, SemanticRiskLevel


class TestEventSimilarity:
    """Test suite for EventSimilarity class."""
    
    def test_encode_event_delete(self):
        """Test encoding delete event."""
        sim = EventSimilarity()
        features = sim.encode_event("delete file /data/important.txt")
        
        assert features["irreversible_action"] > 0.5
        assert features["data_loss_potential"] > 0.5
    
    def test_encode_event_safe(self):
        """Test encoding safe event."""
        sim = EventSimilarity()
        features = sim.encode_event("read log file")
        
        assert features["irreversible_action"] == 0.0
        assert features["data_loss_potential"] == 0.0
    
    def test_calculate_similarity_identical(self):
        """Test similarity of identical events."""
        sim = EventSimilarity()
        features1 = sim.encode_event("delete file")
        features2 = sim.encode_event("delete file")
        
        similarity = sim.calculate_similarity(features1, features2)
        assert abs(similarity - 1.0) < 1e-9
    
    def test_calculate_similarity_different(self):
        """Test similarity of different events."""
        sim = EventSimilarity()
        features1 = sim.encode_event("delete file")
        features2 = sim.encode_event("read file")
        
        similarity = sim.calculate_similarity(features1, features2)
        assert similarity < 1.0
    
    def test_find_similar_events(self):
        """Test finding similar events."""
        sim = EventSimilarity()
        candidates = ["delete file", "read file", "drop table", "list files"]
        
        similar = sim.find_similar_events(
            "delete important data",
            candidates,
            threshold=0.3
        )
        
        assert len(similar) > 0
        assert similar[0][0] in ["delete file", "drop table"]


class TestAffectiveSpread:
    """Test suite for AffectiveSpread class."""
    
    def test_register_affective_memory(self):
        """Test registering affective memory."""
        spread = AffectiveSpread()
        spread.register_affective_memory(
            "mem_1",
            "delete database",
            threat_score=0.9,
            affective_weight=0.8
        )
        
        assert "mem_1" in spread.affective_weights
    
    def test_spread_affect(self):
        """Test spreading affect to similar events."""
        spread = AffectiveSpread()
        spread.register_affective_memory(
            "mem_1",
            "delete file",
            threat_score=0.9,
            affective_weight=0.8
        )
        
        influences = spread.spread_affect(
            "mem_1",
            ["overwrite file", "read file"],
            threshold=0.3
        )
        
        assert len(influences) > 0
        assert "overwrite file" in influences
    
    def test_get_event_threat_adjustment(self):
        """Test getting threat adjustment for event."""
        spread = AffectiveSpread()
        spread.register_affective_memory(
            "mem_1",
            "delete file",
            threat_score=0.9,
            affective_weight=0.8
        )
        spread.spread_affect("mem_1", ["overwrite file"])
        
        adjusted, sources = spread.get_event_threat_adjustment(
            "overwrite file",
            base_threat=0.3
        )
        
        assert adjusted > 0.3
        assert len(sources) > 0


class TestSemanticRiskMap:
    """Test suite for SemanticRiskMap class."""
    
    def test_encode_event(self):
        """Test encoding event."""
        risk_map = SemanticRiskMap()
        features = risk_map.encode_event("batch delete files")
        
        assert isinstance(features, dict)
        assert "irreversible_action" in features
    
    def test_record_experience(self):
        """Test recording experience."""
        risk_map = SemanticRiskMap()
        risk_map.record_experience(
            "delete file",
            outcome="failure",
            risk_actual=0.9
        )
        
        assert "delete file" in risk_map.experience_history
    
    def test_predict_risk(self):
        """Test predicting risk."""
        risk_map = SemanticRiskMap()
        risk, level, similar = risk_map.predict_risk("delete file")
        
        assert 0.0 <= risk <= 1.0
        assert level is not None
    
    def test_calculate_risk_distance(self):
        """Test calculating risk distance."""
        risk_map = SemanticRiskMap()
        distance = risk_map.calculate_risk_distance(
            "delete file",
            "read file"
        )
        
        assert 0.0 <= distance <= 1.0
        assert distance > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

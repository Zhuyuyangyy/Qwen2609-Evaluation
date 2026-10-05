"""
V0.5 - Social Interaction Module

Social context processing system. Handles social cues, relationship management,
and social behavior generation.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class SocialEntity:
    """Represents a social entity (person, group, etc.)."""
    
    id: str
    name: str
    relationship_type: str
    trust_level: float
    familiarity: float
    emotional_history: List[Dict[str, float]]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert social entity to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "relationship_type": self.relationship_type,
            "trust_level": self.trust_level,
            "familiarity": self.familiarity,
            "emotional_history": self.emotional_history
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SocialEntity':
        """Create social entity from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            relationship_type=data["relationship_type"],
            trust_level=data["trust_level"],
            familiarity=data["familiarity"],
            emotional_history=data["emotional_history"]
        )


class SocialInteraction:
    """
    Social context processing system.
    
    Features:
    - Social entity management
    - Relationship tracking
    - Social cue interpretation
    - Empathy calculation
    """
    
    RELATIONSHIP_TYPES = ["stranger", "acquaintance", "friend", "family", "colleague", "enemy"]
    
    def __init__(self):
        self._entities: Dict[str, SocialEntity] = {}
        self._current_context: str = "neutral"
    
    def add_entity(
        self,
        entity_id: str,
        name: str,
        relationship_type: str = "acquaintance",
        trust_level: float = 0.5,
        familiarity: float = 0.5
    ) -> None:
        """
        Add a new social entity.
        
        Args:
            entity_id: Unique identifier for the entity
            name: Name of the entity
            relationship_type: Type of relationship (stranger, acquaintance, friend, etc.)
            trust_level: Initial trust level (0-1)
            familiarity: Initial familiarity level (0-1)
        """
        if relationship_type not in self.RELATIONSHIP_TYPES:
            raise ValueError(f"Unknown relationship type: {relationship_type}")
        
        entity = SocialEntity(
            id=entity_id,
            name=name,
            relationship_type=relationship_type,
            trust_level=min(1.0, max(0.0, trust_level)),
            familiarity=min(1.0, max(0.0, familiarity)),
            emotional_history=[]
        )
        self._entities[entity_id] = entity
    
    def update_entity(
        self,
        entity_id: str,
        trust_delta: float = 0.0,
        familiarity_delta: float = 0.0,
        emotion_record: Optional[Dict[str, float]] = None
    ) -> bool:
        """
        Update an existing social entity.
        
        Args:
            entity_id: ID of the entity to update
            trust_delta: Change in trust level (-1 to +1)
            familiarity_delta: Change in familiarity (-1 to +1)
            emotion_record: Optional emotional state to record
        
        Returns:
            True if entity was found and updated
        """
        if entity_id not in self._entities:
            return False
        
        entity = self._entities[entity_id]
        entity.trust_level = min(1.0, max(0.0, entity.trust_level + trust_delta))
        entity.familiarity = min(1.0, max(0.0, entity.familiarity + familiarity_delta))
        
        if emotion_record:
            entity.emotional_history.append(emotion_record)
        
        return True
    
    def get_entity(self, entity_id: str) -> Optional[SocialEntity]:
        """Get a social entity by ID."""
        return self._entities.get(entity_id)
    
    def get_all_entities(self) -> List[SocialEntity]:
        """Get all social entities."""
        return list(self._entities.values())
    
    def calculate_empathy(self, entity_id: str, current_emotion: Dict[str, float]) -> float:
        """
        Calculate empathy level towards a social entity.
        
        Args:
            entity_id: ID of the target entity
            current_emotion: Current emotional state of the agent
        
        Returns:
            Empathy level (0-1)
        """
        entity = self._entities.get(entity_id)
        if not entity:
            return 0.0
        
        # Base empathy based on relationship
        relationship_multiplier = {
            "stranger": 0.2,
            "acquaintance": 0.4,
            "colleague": 0.5,
            "friend": 0.8,
            "family": 0.95,
            "enemy": 0.1
        }.get(entity.relationship_type, 0.4)
        
        # Factor in trust and familiarity
        trust_factor = entity.trust_level
        familiarity_factor = entity.familiarity
        
        # Emotional similarity factor
        if entity.emotional_history:
            recent_emotion = entity.emotional_history[-1]
            similarity = self._emotional_similarity(current_emotion, recent_emotion)
        else:
            similarity = 0.5
        
        # Combine factors
        empathy = (relationship_multiplier * 0.4 + 
                   trust_factor * 0.3 + 
                   familiarity_factor * 0.2 + 
                   similarity * 0.1)
        
        return empathy
    
    def _emotional_similarity(self, emotion1: Dict[str, float], emotion2: Dict[str, float]) -> float:
        """Calculate similarity between two emotional states."""
        keys = ["valence", "arousal", "dominance"]
        vec1 = [emotion1.get(k, 0.0) for k in keys]
        vec2 = [emotion2.get(k, 0.0) for k in keys]
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a ** 2 for a in vec1) ** 0.5
        magnitude2 = sum(b ** 2 for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def interpret_social_cue(self, cue: str, entity_id: str) -> Dict[str, float]:
        """
        Interpret a social cue from an entity.
        
        Args:
            cue: Social cue string (e.g., "smile", "frown", "hug", "crossed arms")
            entity_id: ID of the entity providing the cue
        
        Returns:
            Dictionary with emotional interpretation and trust/familiarity deltas
        """
        cue_interpretations = {
            "smile": {"emotion": {"valence": 0.5, "arousal": 0.2}, "trust_delta": 0.05, "familiarity_delta": 0.02},
            "frown": {"emotion": {"valence": -0.5, "arousal": 0.1}, "trust_delta": -0.05, "familiarity_delta": -0.02},
            "hug": {"emotion": {"valence": 0.7, "arousal": 0.3}, "trust_delta": 0.1, "familiarity_delta": 0.05},
            "crossed arms": {"emotion": {"valence": -0.2, "arousal": 0.3}, "trust_delta": -0.05, "familiarity_delta": 0.0},
            "nodding": {"emotion": {"valence": 0.3, "arousal": 0.1}, "trust_delta": 0.03, "familiarity_delta": 0.01},
            "eye contact": {"emotion": {"valence": 0.2, "arousal": 0.2}, "trust_delta": 0.05, "familiarity_delta": 0.03},
            "avoiding eye contact": {"emotion": {"valence": -0.2, "arousal": 0.3}, "trust_delta": -0.03, "familiarity_delta": -0.02},
            "laughing": {"emotion": {"valence": 0.6, "arousal": 0.4}, "trust_delta": 0.08, "familiarity_delta": 0.04},
            "sigh": {"emotion": {"valence": -0.4, "arousal": -0.2}, "trust_delta": -0.03, "familiarity_delta": -0.01},
            "handshake": {"emotion": {"valence": 0.3, "arousal": 0.1}, "trust_delta": 0.05, "familiarity_delta": 0.03}
        }
        
        return cue_interpretations.get(cue.lower(), {
            "emotion": {"valence": 0.0, "arousal": 0.0},
            "trust_delta": 0.0,
            "familiarity_delta": 0.0
        })
    
    def generate_social_response(self, entity_id: str, agent_emotion: str) -> str:
        """
        Generate a socially appropriate response.
        
        Args:
            entity_id: ID of the target entity
            agent_emotion: Current emotion category of the agent
        
        Returns:
            Social response string
        """
        entity = self._entities.get(entity_id)
        if not entity:
            return "I don't know this person."
        
        response_templates = {
            "joy": {
                "stranger": "I'm happy to meet you!",
                "acquaintance": "Great to see you! You look happy.",
                "friend": "Hey! You seem happy - want to share?",
                "family": "Hi! What's making you smile?",
                "colleague": "Good to see you in a good mood!",
                "enemy": "Interesting... you seem happy."
            },
            "sadness": {
                "stranger": "Are you okay?",
                "acquaintance": "I'm sorry to hear that.",
                "friend": "Oh no, what's wrong? I'm here for you.",
                "family": "I'm worried about you. Want to talk?",
                "colleague": "Is everything alright?",
                "enemy": "Tough day?"
            },
            "anger": {
                "stranger": "Let's calm down.",
                "acquaintance": "I sense you're upset.",
                "friend": "What's got you so angry?",
                "family": "Hey, let's talk this out.",
                "colleague": "Is there something I can help with?",
                "enemy": "Calm down, it's not worth it."
            },
            "neutral": {
                "stranger": "Nice to meet you.",
                "acquaintance": "How are you doing?",
                "friend": "What's up?",
                "family": "Hi there!",
                "colleague": "How's work going?",
                "enemy": "..."
            }
        }
        
        emotion_key = agent_emotion.lower()
        if emotion_key not in response_templates:
            emotion_key = "neutral"
        
        return response_templates[emotion_key].get(entity.relationship_type, "Hello.")
    
    def set_context(self, context: str) -> None:
        """Set current social context."""
        self._current_context = context
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get social interaction statistics."""
        if not self._entities:
            return {"total_entities": 0, "avg_trust": 0.0, "avg_familiarity": 0.0}
        
        avg_trust = sum(e.trust_level for e in self._entities.values()) / len(self._entities)
        avg_familiarity = sum(e.familiarity for e in self._entities.values()) / len(self._entities)
        
        return {
            "total_entities": len(self._entities),
            "avg_trust": round(avg_trust, 3),
            "avg_familiarity": round(avg_familiarity, 3),
            "current_context": self._current_context
        }
    
    def to_json(self) -> str:
        """Serialize social interaction data to JSON."""
        return json.dumps({
            "entities": {id: entity.to_dict() for id, entity in self._entities.items()},
            "current_context": self._current_context,
            "statistics": self.get_statistics()
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'SocialInteraction':
        """Deserialize social interaction data from JSON."""
        data = json.loads(json_str)
        social = cls()
        
        for entity_id, entity_data in data.get("entities", {}).items():
            social._entities[entity_id] = SocialEntity.from_dict(entity_data)
        
        social._current_context = data.get("current_context", "neutral")
        
        return social

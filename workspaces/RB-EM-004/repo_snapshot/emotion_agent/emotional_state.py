"""
V0.1 - Emotional State Module

Core emotional state representation with dimensional and categorical models.
Implements the circumplex model of affect (Russell, 1980) with valence and arousal.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, List


@dataclass
class EmotionalState:
    """
    Represents the agent's emotional state using dimensional affect model.
    
    Valence: -1 (negative) to +1 (positive)
    Arousal: -1 (calm) to +1 (excited)
    Dominance: -1 (submissive) to +1 (dominant)
    
    Also includes categorical emotion labels for interpretability.
    """
    
    valence: float = 0.0
    arousal: float = 0.0
    dominance: float = 0.0
    intensity: float = 0.0
    category: str = "neutral"
    
    _history: List[Tuple[float, float, float, float, str]] = field(default_factory=list)
    
    EMOTION_CATEGORIES = {
        "joy": {"valence": 0.8, "arousal": 0.6, "dominance": 0.5},
        "sadness": {"valence": -0.7, "arousal": -0.4, "dominance": -0.3},
        "anger": {"valence": -0.8, "arousal": 0.7, "dominance": 0.6},
        "fear": {"valence": -0.8, "arousal": 0.8, "dominance": -0.7},
        "disgust": {"valence": -0.7, "arousal": 0.2, "dominance": -0.2},
        "surprise": {"valence": 0.0, "arousal": 0.9, "dominance": 0.0},
        "trust": {"valence": 0.6, "arousal": -0.1, "dominance": 0.3},
        "anticipation": {"valence": 0.5, "arousal": 0.4, "dominance": 0.4},
        "neutral": {"valence": 0.0, "arousal": 0.0, "dominance": 0.0},
    }
    
    def _clamp(self, value: float, min_val: float = -1.0, max_val: float = 1.0) -> float:
        """Clamp value between min and max."""
        return max(min_val, min(max_val, value))
    
    def update_from_dimensions(self, valence_delta: float, arousal_delta: float, dominance_delta: float) -> None:
        """
        Update emotional state from dimensional deltas.
        
        Args:
            valence_delta: Change in valence (-1 to +1)
            arousal_delta: Change in arousal (-1 to +1)
            dominance_delta: Change in dominance (-1 to +1)
        """
        self.valence = self._clamp(self.valence + valence_delta)
        self.arousal = self._clamp(self.arousal + arousal_delta)
        self.dominance = self._clamp(self.dominance + dominance_delta)
        
        self._update_category()
        self._update_intensity()
        self._record_history()
    
    def update_from_category(self, emotion: str, intensity: float = 1.0) -> None:
        """
        Update emotional state from a categorical emotion label.
        
        Args:
            emotion: Emotion category name (e.g., "joy", "sadness")
            intensity: Strength of the emotion (0 to 1)
        """
        if emotion not in self.EMOTION_CATEGORIES:
            raise ValueError(f"Unknown emotion category: {emotion}")
        
        target = self.EMOTION_CATEGORIES[emotion]
        valence_delta = (target["valence"] - self.valence) * intensity
        arousal_delta = (target["arousal"] - self.arousal) * intensity
        dominance_delta = (target["dominance"] - self.dominance) * intensity
        
        self.update_from_dimensions(valence_delta, arousal_delta, dominance_delta)
    
    def _update_category(self) -> None:
        """Determine the closest emotion category based on current dimensions."""
        min_distance = float('inf')
        closest_category = "neutral"
        
        for category, dimensions in self.EMOTION_CATEGORIES.items():
            distance = (
                (self.valence - dimensions["valence"]) ** 2 +
                (self.arousal - dimensions["arousal"]) ** 2 +
                (self.dominance - dimensions["dominance"]) ** 2
            ) ** 0.5
            
            if distance < min_distance:
                min_distance = distance
                closest_category = category
        
        self.category = closest_category
    
    def _update_intensity(self) -> None:
        """Calculate overall emotional intensity."""
        self.intensity = (self.valence ** 2 + self.arousal ** 2 + self.dominance ** 2) ** 0.5
    
    def _record_history(self) -> None:
        """Record current state in history."""
        self._history.append((
            self.valence,
            self.arousal,
            self.dominance,
            self.intensity,
            self.category
        ))
    
    def get_state(self) -> Dict[str, float]:
        """Get current emotional state as a dictionary."""
        return {
            "valence": round(self.valence, 3),
            "arousal": round(self.arousal, 3),
            "dominance": round(self.dominance, 3),
            "intensity": round(self.intensity, 3),
            "category": self.category
        }
    
    def get_history(self) -> List[Dict[str, float]]:
        """Get historical emotional states."""
        return [{
            "valence": h[0],
            "arousal": h[1],
            "dominance": h[2],
            "intensity": h[3],
            "category": h[4]
        } for h in self._history]
    
    def reset(self) -> None:
        """Reset emotional state to neutral."""
        self.valence = 0.0
        self.arousal = 0.0
        self.dominance = 0.0
        self.intensity = 0.0
        self.category = "neutral"
        self._history = []
    
    def to_json(self) -> str:
        """Serialize state to JSON."""
        return json.dumps({
            "current": self.get_state(),
            "history": self.get_history()
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'EmotionalState':
        """Deserialize state from JSON."""
        data = json.loads(json_str)
        state = cls()
        state.valence = data["current"]["valence"]
        state.arousal = data["current"]["arousal"]
        state.dominance = data["current"]["dominance"]
        state.intensity = data["current"]["intensity"]
        state.category = data["current"]["category"]
        return state
    
    def __repr__(self) -> str:
        return f"EmotionalState(valence={self.valence:.3f}, arousal={self.arousal:.3f}, " \
               f"dominance={self.dominance:.3f}, category='{self.category}', intensity={self.intensity:.3f})"

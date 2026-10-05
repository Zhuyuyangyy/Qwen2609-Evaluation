"""
V0.7 - Affect Regulation Module

Emotional self-regulation system. Enables the agent to manage and regulate
its emotional state to achieve desired affective goals.
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class RegulationStrategy:
    """Represents an emotion regulation strategy."""
    
    id: str
    name: str
    description: str
    target_emotions: List[str]
    effect: Dict[str, float]
    cost: float
    success_rate: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert strategy to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target_emotions": self.target_emotions,
            "effect": self.effect,
            "cost": self.cost,
            "success_rate": self.success_rate
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RegulationStrategy':
        """Create strategy from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            target_emotions=data["target_emotions"],
            effect=data["effect"],
            cost=data["cost"],
            success_rate=data["success_rate"]
        )


class AffectRegulation:
    """
    Emotional self-regulation system.
    
    Features:
    - Strategy-based emotion regulation
    - Automatic regulation when emotions exceed thresholds
    - Energy-based cost system
    - Regulation effectiveness tracking
    """
    
    DEFAULT_STRATEGIES = [
        {
            "id": "s1",
            "name": "deep_breathing",
            "description": "Slow, deep breathing exercises",
            "target_emotions": ["fear", "anger", "anxiety"],
            "effect": {"valence": 0.1, "arousal": -0.3, "dominance": 0.1},
            "cost": 0.05,
            "success_rate": 0.85
        },
        {
            "id": "s2",
            "name": "positive_reframing",
            "description": "Reinterpreting situation in positive light",
            "target_emotions": ["sadness", "anger", "disgust"],
            "effect": {"valence": 0.3, "arousal": -0.1, "dominance": 0.2},
            "cost": 0.1,
            "success_rate": 0.7
        },
        {
            "id": "s3",
            "name": "distraction",
            "description": "Focusing on neutral or positive stimuli",
            "target_emotions": ["sadness", "fear", "anger"],
            "effect": {"valence": 0.15, "arousal": -0.2, "dominance": 0.0},
            "cost": 0.08,
            "success_rate": 0.75
        },
        {
            "id": "s4",
            "name": "self_compassion",
            "description": "Treating oneself with kindness",
            "target_emotions": ["sadness", "shame", "guilt"],
            "effect": {"valence": 0.25, "arousal": -0.15, "dominance": 0.15},
            "cost": 0.12,
            "success_rate": 0.72
        },
        {
            "id": "s5",
            "name": "expression",
            "description": "Expressing emotions outwardly",
            "target_emotions": ["anger", "sadness", "joy"],
            "effect": {"valence": 0.0, "arousal": 0.1, "dominance": 0.2},
            "cost": 0.06,
            "success_rate": 0.65
        },
        {
            "id": "s6",
            "name": "acceptance",
            "description": "Accepting current emotional state",
            "target_emotions": ["all"],
            "effect": {"valence": 0.05, "arousal": -0.2, "dominance": 0.1},
            "cost": 0.04,
            "success_rate": 0.8
        }
    ]
    
    def __init__(self, energy_level: float = 1.0):
        self._strategies: Dict[str, RegulationStrategy] = {}
        self._initialize_default_strategies()
        self._energy_level = max(0.0, min(1.0, energy_level))
        self._regulation_history: List[Dict[str, Any]] = []
        self._auto_regulate = True
        
        # Thresholds for automatic regulation
        self._high_arousal_threshold = 0.7
        self._low_arousal_threshold = -0.7
        self._high_valence_threshold = 0.9
        self._low_valence_threshold = -0.9
    
    def _initialize_default_strategies(self) -> None:
        """Initialize default regulation strategies."""
        for strategy_data in self.DEFAULT_STRATEGIES:
            strategy = RegulationStrategy.from_dict(strategy_data)
            self._strategies[strategy.id] = strategy
    
    def add_strategy(self, strategy: RegulationStrategy) -> None:
        """Add a new regulation strategy."""
        self._strategies[strategy.id] = strategy
    
    def get_strategy(self, strategy_id: str) -> Optional[RegulationStrategy]:
        """Get a strategy by ID."""
        return self._strategies.get(strategy_id)
    
    def get_all_strategies(self) -> List[RegulationStrategy]:
        """Get all regulation strategies."""
        return list(self._strategies.values())
    
    def select_strategy(self, emotion_category: str, intensity: float) -> Optional[RegulationStrategy]:
        """
        Select the best strategy for a given emotional state.
        
        Args:
            emotion_category: Current emotion category
            intensity: Emotional intensity (0-1)
        
        Returns:
            The best regulation strategy, or None if none applicable
        """
        applicable = []
        
        for strategy in self._strategies.values():
            # Check if strategy targets this emotion
            if emotion_category not in strategy.target_emotions and "all" not in strategy.target_emotions:
                continue
            
            # Check if we have enough energy
            if strategy.cost > self._energy_level:
                continue
            
            applicable.append(strategy)
        
        if not applicable:
            return None
        
        # Select based on success rate and cost
        applicable.sort(key=lambda s: (s.success_rate, -s.cost), reverse=True)
        
        return applicable[0]
    
    def apply_strategy(self, strategy_id: str, current_state: Dict[str, float]) -> Dict[str, float]:
        """
        Apply a regulation strategy to the current emotional state.
        
        Args:
            strategy_id: ID of the strategy to apply
            current_state: Current emotional state
        
        Returns:
            New emotional state after applying strategy
        """
        strategy = self._strategies.get(strategy_id)
        if not strategy:
            return current_state
        
        # Check energy
        if strategy.cost > self._energy_level:
            return current_state
        
        # Apply strategy effect
        new_state = current_state.copy()
        effect = strategy.effect
        
        for key in ["valence", "arousal", "dominance"]:
            if key in effect and key in new_state:
                new_state[key] = max(-1.0, min(1.0, new_state[key] + effect[key]))
        
        # Consume energy
        self._energy_level = max(0.0, self._energy_level - strategy.cost)
        
        # Record history
        self._regulation_history.append({
            "strategy_id": strategy_id,
            "strategy_name": strategy.name,
            "before": current_state,
            "after": new_state,
            "energy_used": strategy.cost
        })
        
        return new_state
    
    def auto_regulate(self, current_state: Dict[str, float]) -> Dict[str, float]:
        """
        Automatically apply regulation if emotional state exceeds thresholds.
        
        Args:
            current_state: Current emotional state
        
        Returns:
            Potentially modified emotional state
        """
        if not self._auto_regulate:
            return current_state
        
        emotion_category = current_state.get("category", "neutral")
        intensity = current_state.get("intensity", 0.0)
        valence = current_state.get("valence", 0.0)
        arousal = current_state.get("arousal", 0.0)
        
        # Check if regulation is needed
        needs_regulation = (
            arousal > self._high_arousal_threshold or
            arousal < self._low_arousal_threshold or
            valence < self._low_valence_threshold or
            valence > self._high_valence_threshold or
            intensity > 0.8
        )
        
        if not needs_regulation:
            return current_state
        
        # Select and apply strategy
        strategy = self.select_strategy(emotion_category, intensity)
        if strategy:
            return self.apply_strategy(strategy.id, current_state)
        
        return current_state
    
    def set_auto_regulate(self, enabled: bool) -> None:
        """Enable or disable automatic regulation."""
        self._auto_regulate = enabled
    
    def replenish_energy(self, amount: float) -> None:
        """
        Replenish energy.
        
        Args:
            amount: Amount to add (0-1)
        """
        self._energy_level = min(1.0, self._energy_level + amount)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get regulation statistics."""
        return {
            "energy_level": round(self._energy_level, 3),
            "auto_regulate_enabled": self._auto_regulate,
            "total_strategies": len(self._strategies),
            "regulation_attempts": len(self._regulation_history),
            "high_arousal_threshold": self._high_arousal_threshold,
            "low_valence_threshold": self._low_valence_threshold
        }
    
    def to_json(self) -> str:
        """Serialize regulation system to JSON."""
        return json.dumps({
            "strategies": {id: strategy.to_dict() for id, strategy in self._strategies.items()},
            "energy_level": self._energy_level,
            "auto_regulate": self._auto_regulate,
            "regulation_history": self._regulation_history,
            "statistics": self.get_statistics()
        }, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'AffectRegulation':
        """Deserialize regulation system from JSON."""
        data = json.loads(json_str)
        regulation = cls(energy_level=data.get("energy_level", 1.0))
        
        regulation._strategies = {}
        for strategy_id, strategy_data in data.get("strategies", {}).items():
            regulation._strategies[strategy_id] = RegulationStrategy.from_dict(strategy_data)
        
        regulation._auto_regulate = data.get("auto_regulate", True)
        regulation._regulation_history = data.get("regulation_history", [])
        
        return regulation

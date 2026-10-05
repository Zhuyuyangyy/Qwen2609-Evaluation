"""
V0.3 - Affective Spread Module

Spreads emotional weights from experienced events to similar unseen events.
Implements stimulus generalization - the psychological principle where 
learning about one stimulus transfers to similar stimuli.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from emotion_agent.event_similarity import EventSimilarity


@dataclass
class AffectiveWeight:
    """Represents the emotional weight of a memory."""
    memory_id: str
    event_description: str
    threat_score: float
    affective_weight: float
    source: Optional[str] = None


class AffectiveSpread:
    """
    Spreads affective influence from experienced events to similar events.
    
    This implements a simplified model of stimulus generalization from 
    learning psychology. When an agent has a negative experience with an 
    event type, similar events should also be treated with caution.
    """
    
    DEFAULT_SPREAD_THRESHOLD = 0.4
    DEFAULT_SPREAD_DECAY = 0.8
    
    def __init__(self):
        self.event_similarity = EventSimilarity()
        self.spread_map: Dict[str, Dict[str, float]] = {}
        self.affective_weights: Dict[str, AffectiveWeight] = {}
        self.spread_history: List[Dict] = []
    
    def register_affective_memory(
        self,
        memory_id: str,
        event_description: str,
        threat_score: float,
        affective_weight: float,
        source: Optional[str] = None
    ) -> None:
        """
        Register an affective memory that can spread to similar events.
        
        Args:
            memory_id: Unique identifier for this memory
            event_description: Description of the event
            threat_score: The threat level associated with this event (0-1)
            affective_weight: Overall emotional intensity (0-1)
            source: Optional source identifier (e.g., "source_A")
        """
        self.affective_weights[memory_id] = AffectiveWeight(
            memory_id=memory_id,
            event_description=event_description,
            threat_score=threat_score,
            affective_weight=affective_weight,
            source=source
        )
        
        self.event_similarity.encode_event(event_description)
    
    def spread_affect(
        self,
        source_memory_id: str,
        target_events: List[str],
        threshold: float = None,
        decay_factor: float = None
    ) -> Dict[str, float]:
        """
        Spread affective influence from source memory to target events.
        
        Args:
            source_memory_id: ID of the memory to spread from
            target_events: List of events to potentially spread to
            threshold: Minimum similarity to spread (default: 0.4)
            decay_factor: How much to decay the effect (default: 0.8)
        
        Returns:
            Dictionary mapping target event to influence score
        """
        if source_memory_id not in self.affective_weights:
            return {}
        
        if threshold is None:
            threshold = self.DEFAULT_SPREAD_THRESHOLD
        if decay_factor is None:
            decay_factor = self.DEFAULT_SPREAD_DECAY
        
        source = self.affective_weights[source_memory_id]
        source_features = self.event_similarity.encode_event(source.event_description)
        
        influences = {}
        
        for target_event in target_events:
            if target_event == source.event_description:
                continue
            
            target_features = self.event_similarity.encode_event(target_event)
            similarity = self.event_similarity.calculate_similarity(source_features, target_features)
            
            if similarity >= threshold:
                influence = source.affective_weight * similarity * decay_factor
                influences[target_event] = influence
                
                if target_event not in self.spread_map:
                    self.spread_map[target_event] = {}
                self.spread_map[target_event][source_memory_id] = influence
        
        self.spread_history.append({
            "source_memory": source_memory_id,
            "target_count": len(influences),
            "max_influence": max(influences.values()) if influences else 0.0
        })
        
        return influences
    
    def get_spread_map(self) -> Dict[str, List[Tuple[str, float]]]:
        """
        Get the current spread map showing all affective influences.
        
        Returns:
            Dictionary mapping events to list of (source_memory_id, influence) tuples
        """
        result = {}
        for target_event, influences in self.spread_map.items():
            sorted_influences = sorted(
                influences.items(),
                key=lambda x: x[1],
                reverse=True
            )
            result[target_event] = sorted_influences
        return result
    
    def get_event_threat_adjustment(
        self,
        event_description: str,
        base_threat: float
    ) -> Tuple[float, List[str]]:
        """
        Calculate adjusted threat level for an event based on spread influence.
        
        Args:
            event_description: The event to evaluate
            base_threat: The base threat level without affective spread
        
        Returns:
            Tuple of (adjusted_threat, list_of_influencing_memories)
        """
        if event_description not in self.spread_map:
            return base_threat, []
        
        influences = self.spread_map[event_description]
        
        if not influences:
            return base_threat, []
        
        max_influence = max(influences.values())
        memory_ids = list(influences.keys())
        
        adjustment = max_influence * 0.5
        
        adjusted_threat = min(1.0, base_threat + adjustment)
        
        return adjusted_threat, memory_ids
    
    def clear_spread_map(self) -> None:
        """Clear all spread mappings."""
        self.spread_map.clear()
        self.spread_history.clear()
    
    def get_statistics(self) -> Dict:
        """Get statistics about the affective spread system."""
        return {
            "total_memories": len(self.affective_weights),
            "total_spread_targets": len(self.spread_map),
            "total_spread_events": len(self.spread_history),
            "avg_influence_per_event": (
                sum(sum(v.values()) for v in self.spread_map.values()) / len(self.spread_map)
                if self.spread_map else 0.0
            )
        }

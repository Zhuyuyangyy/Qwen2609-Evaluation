"""
V0.2 - Experience Memory Module

Experience storage and retrieval system. Maintains a memory of past experiences
with emotional tags for recall and pattern matching.
"""

import json
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from emotion_agent.decay_clock import AffectiveDecayConfig, DecayClock, WallClock


@dataclass
class Experience:
    """Represents a single experience with emotional context."""
    
    id: str
    timestamp: float
    context: str
    emotion_category: str
    valence: float
    arousal: float
    dominance: float
    intensity: float
    tags: List[str]
    summary: str
    duration: float = 0.0
    task_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert experience to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "context": self.context,
            "emotion_category": self.emotion_category,
            "valence": self.valence,
            "arousal": self.arousal,
            "dominance": self.dominance,
            "intensity": self.intensity,
            "tags": self.tags,
            "summary": self.summary,
            "duration": self.duration,
            "task_id": self.task_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Experience':
        """Create experience from dictionary."""
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            context=data["context"],
            emotion_category=data["emotion_category"],
            valence=data["valence"],
            arousal=data["arousal"],
            dominance=data["dominance"],
            intensity=data["intensity"],
            tags=data["tags"],
            summary=data["summary"],
            duration=data.get("duration", 0.0),
            task_id=data.get("task_id", "")
        )


@dataclass
class MemoryItem:
    """V0.9 structured outcome memory (for episodic retrieval in the decision
    loop). Kept separate from the emotion-annotated Experience: it stores the
    outcome signal (success / risk_actual / predicted risk / severity) that the
    Policy Modulator needs, instead of only an emotion tag.

    P1-d: the roadmap episodic record also carries the affective context of
    the decision — how the agent felt *before* acting and *after* seeing the
    outcome, plus the prediction error that drove the update.  All three are
    optional so pre-P1 serialized episodes keep loading."""
    event: str
    outcome: str                 # "success" | "failure" | "partial"
    risk_actual: float           # 0..1 continuous feedback
    r_predicted: float           # risk predicted at decision time
    timestamp: float
    task_id: str = ""
    severity: int = 0            # 0=none .. 3=severe
    id: str = ""
    affect_before: Optional[Dict[str, float]] = None   # fast state before acting
    affect_after: Optional[Dict[str, float]] = None    # fast state after outcome
    pe: Optional[float] = None                         # prediction error

    def to_dict(self) -> Dict[str, Any]:
        """Convert memory item to dictionary."""
        return {
            "id": self.id,
            "event": self.event,
            "outcome": self.outcome,
            "risk_actual": self.risk_actual,
            "r_predicted": self.r_predicted,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "severity": self.severity,
            "affect_before": self.affect_before,
            "affect_after": self.affect_after,
            "pe": self.pe,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryItem':
        """Create memory item from dictionary."""
        return cls(
            id=data.get("id", ""),
            event=data["event"],
            outcome=data["outcome"],
            risk_actual=float(data["risk_actual"]),
            r_predicted=float(data.get("r_predicted", 0.5)),
            timestamp=float(data["timestamp"]),
            task_id=data.get("task_id", ""),
            severity=int(data.get("severity", 0)),
            affect_before=data.get("affect_before"),
            affect_after=data.get("affect_after"),
            pe=(float(data["pe"]) if data.get("pe") is not None else None),
        )


class ExperienceMemory:
    """
    Memory system for storing and retrieving experiences.
    
    Features:
    - Episodic memory storage
    - Emotional context indexing
    - Pattern matching for recall
    - Memory consolidation over time
    """
    
    def __init__(self, max_capacity: int = 1000,
                 clock: Optional[DecayClock] = None,
                 decay_config: Optional[AffectiveDecayConfig] = None):
        self._experiences: List[Experience] = []
        self._max_capacity = max_capacity
        self._tag_index: Dict[str, List[str]] = {}
        self._emotion_index: Dict[str, List[str]] = {}
        # V0.9: structured outcome memory for episodic retrieval in the
        # decision loop (independent of the emotion-annotated experiences).
        self._outcomes: List[MemoryItem] = []
        self._outcome_seq = 0
        # Decay semantics are declared, not implicit: production runs on the
        # WallClock (seconds; ~7-day episodic half-life), experiments on a
        # StepClock (steps; 40-step half-life). See emotion_agent/decay_clock.py.
        self.clock: DecayClock = clock or WallClock()
        self.decay_config: AffectiveDecayConfig = decay_config or AffectiveDecayConfig()
    
    def _generate_id(self) -> str:
        """Generate a unique experience ID."""
        return f"exp_{int(time.time() * 1000)}_{len(self._experiences)}"
    
    def add_experience(
        self,
        context: str,
        emotion_category: str,
        valence: float,
        arousal: float,
        dominance: float,
        intensity: float,
        tags: Optional[List[str]] = None,
        summary: str = "",
        duration: float = 0.0
    ) -> str:
        """
        Add a new experience to memory.
        
        Args:
            context: Description of the experience
            emotion_category: Emotion associated with this experience
            valence: Valence dimension (-1 to +1)
            arousal: Arousal dimension (-1 to +1)
            dominance: Dominance dimension (-1 to +1)
            intensity: Emotional intensity (0 to 1)
            tags: Optional tags for categorization
            summary: Brief summary of the experience
            duration: Duration of the experience in seconds
        
        Returns:
            The ID of the added experience
        """
        experience_id = self._generate_id()
        experience = Experience(
            id=experience_id,
            timestamp=time.time(),
            context=context,
            emotion_category=emotion_category,
            valence=valence,
            arousal=arousal,
            dominance=dominance,
            intensity=intensity,
            tags=tags or [],
            summary=summary,
            duration=duration
        )
        
        self._experiences.append(experience)
        
        # Update indexes
        for tag in experience.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            self._tag_index[tag].append(experience_id)
        
        if emotion_category not in self._emotion_index:
            self._emotion_index[emotion_category] = []
        self._emotion_index[emotion_category].append(experience_id)
        
        # Enforce capacity limit
        self._enforce_capacity()
        
        return experience_id
    
    def _enforce_capacity(self) -> None:
        """Remove oldest items if capacity is exceeded (both stores)."""
        while len(self._experiences) > self._max_capacity:
            oldest = self._experiences.pop(0)
            # Remove from indexes
            for tag in oldest.tags:
                if tag in self._tag_index and oldest.id in self._tag_index[tag]:
                    self._tag_index[tag].remove(oldest.id)
            if oldest.emotion_category in self._emotion_index:
                if oldest.id in self._emotion_index[oldest.emotion_category]:
                    self._emotion_index[oldest.emotion_category].remove(oldest.id)
        # V1.0 fix: the structured outcome store used to be unbounded, so a
        # long-running agent leaked memory forever. Keep the most recent ones.
        if len(self._outcomes) > self._max_capacity:
            self._outcomes = self._outcomes[-self._max_capacity:]
    
    def retrieve_by_emotion(self, emotion_category: str) -> List[Experience]:
        """Retrieve all experiences with a specific emotion category."""
        if emotion_category not in self._emotion_index:
            return []
        
        result = []
        for exp_id in self._emotion_index[emotion_category]:
            exp = self._get_experience_by_id(exp_id)
            if exp:
                result.append(exp)
        return result
    
    def retrieve_by_tags(self, tags: List[str]) -> List[Experience]:
        """Retrieve experiences matching any of the given tags."""
        matched_ids = set()
        for tag in tags:
            if tag in self._tag_index:
                matched_ids.update(self._tag_index[tag])
        
        result = []
        for exp_id in matched_ids:
            exp = self._get_experience_by_id(exp_id)
            if exp:
                result.append(exp)
        return result
    
    def retrieve_recent(self, limit: int = 10) -> List[Experience]:
        """Retrieve most recent experiences."""
        return list(reversed(self._experiences[-limit:]))

    # -- V0.9: structured outcome memory + task-similarity retrieval ---------
    def record_outcome(
        self,
        event: str,
        outcome: str,
        risk_actual: float,
        r_predicted: float = 0.5,
        task_id: str = "",
        severity: int = 0,
        timestamp: Optional[float] = None,
        affect_before: Optional[Dict[str, float]] = None,
        affect_after: Optional[Dict[str, float]] = None,
        pe: Optional[float] = None,
    ) -> str:
        """Record a structured outcome memory (the online-loop write side).

        ``pe`` defaults to the continuous prediction error
        ``tanh(risk_actual − r_predicted)`` (same formula as the P0 core),
        so episodes recorded without an explicit PE still carry the signal
        the consolidation pass needs.
        """
        if pe is None:
            pe = math.tanh(float(risk_actual) - float(r_predicted))
        item = MemoryItem(
            id=f"mem_{self._outcome_seq}",
            event=event,
            outcome=outcome,
            risk_actual=float(risk_actual),
            r_predicted=float(r_predicted),
            timestamp=timestamp if timestamp is not None else self.clock.now(),
            task_id=task_id,
            severity=int(severity),
            affect_before=affect_before,
            affect_after=affect_after,
            pe=round(float(pe), 4),
        )
        self._outcome_seq += 1
        self._outcomes.append(item)
        self._enforce_capacity()
        return item.id

    def retrieve(
        self,
        query: str,
        k: int = 5,
        min_sim: float = 0.3,
        half_life: Optional[float] = None,
        now: Optional[float] = None,
    ) -> List[Tuple[MemoryItem, float]]:
        """
        V0.9 episodic retrieval: fetch outcome memories by task semantic
        similarity, re-ranked by recency.

        Score of a memory = similarity * decay_weight, where similarity uses
        ``EventSimilarity.calculate_weighted_distance`` (1 - distance; the
        default V0.9 implementation — may be swapped for an embedding
        similarity in V3 without changing the protocol) and
        ``decay_weight = 0.5 ** (age / half_life)``.

        ``half_life`` is expressed in this memory's clock units (see
        ``decay_clock.py``); when omitted it resolves from the declared
        clock mode (40 steps under ``StepClock``, 7 days under ``WallClock``).
        ``now`` likewise defaults to the clock reading.

        Returns [(MemoryItem, score)] sorted descending; empty if nothing
        exceeds ``min_sim``.
        """
        from emotion_agent.event_similarity import EventSimilarity

        sim = EventSimilarity()
        query_feats = sim.encode_event(query)
        now = now if now is not None else self.clock.now()
        if half_life is None:
            half_life = self.decay_config.half_life("episodic", self.clock.mode)
        scored = []
        for item in self._outcomes:
            distance = sim.calculate_weighted_distance(query_feats, sim.encode_event(item.event))
            similarity = max(0.0, 1.0 - distance)
            if similarity < min_sim:
                continue
            age = max(0.0, now - item.timestamp)
            decay = 0.5 ** (age / max(1e-9, half_life))
            scored.append((item, similarity * decay))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def outcome_items(self) -> List[MemoryItem]:
        """Read-only view of the structured outcome store (P1-d reads it
        for the consolidation pass without touching privates)."""
        return list(self._outcomes)

    def outcome_statistics(self) -> Dict[str, Any]:
        """Aggregate statistics over structured outcome memories."""
        outcomes = [m.outcome for m in self._outcomes]
        failures = [m for m in self._outcomes if m.outcome == "failure"]
        return {
            "total": len(self._outcomes),
            "outcome_distribution": {o: outcomes.count(o) for o in set(outcomes)},
            "mean_risk_actual": (
                sum(m.risk_actual for m in self._outcomes) / len(self._outcomes)
                if self._outcomes else 0.0
            ),
            "n_failures": len(failures),
        }
    
    def _get_experience_by_id(self, exp_id: str) -> Optional[Experience]:
        """Find experience by ID."""
        for exp in self._experiences:
            if exp.id == exp_id:
                return exp
        return None
    
    def retrieve_similar(self, valence: float, arousal: float, dominance: float, 
                        threshold: float = 0.5) -> List[Tuple[Experience, float]]:
        """
        Retrieve experiences with similar emotional state.
        
        Args:
            valence: Target valence
            arousal: Target arousal
            dominance: Target dominance
            threshold: Similarity threshold (0-1, higher = more similar)
        
        Returns:
            List of (experience, similarity_score) tuples
        """
        results = []
        for exp in self._experiences:
            similarity = self._emotional_similarity(
                (valence, arousal, dominance),
                (exp.valence, exp.arousal, exp.dominance)
            )
            if similarity >= threshold:
                results.append((exp, similarity))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def _emotional_similarity(self, vec1: Tuple[float, float, float], 
                             vec2: Tuple[float, float, float]) -> float:
        """Calculate cosine similarity between two emotional state vectors."""
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = sum(a ** 2 for a in vec1) ** 0.5
        magnitude2 = sum(b ** 2 for b in vec2) ** 0.5
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def consolidate(self) -> None:
        """
        Consolidate memories - reduce redundant memories and strengthen important ones.
        This is a simplified version that removes very similar recent experiences.
        """
        if len(self._experiences) < 2:
            return
        
        to_remove = set()
        recent = self._experiences[-50:]  # Check last 50 experiences
        
        for i, exp1 in enumerate(recent):
            for j, exp2 in enumerate(recent[i+1:], start=i+1):
                if exp1.id == exp2.id:
                    continue
                similarity = self._emotional_similarity(
                    (exp1.valence, exp1.arousal, exp1.dominance),
                    (exp2.valence, exp2.arousal, exp2.dominance)
                )
                if similarity > 0.9 and exp1.context == exp2.context:
                    to_remove.add(exp2.id)
        
        self._experiences = [exp for exp in self._experiences if exp.id not in to_remove]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics."""
        emotion_counts = {}
        for exp in self._experiences:
            emotion_counts[exp.emotion_category] = emotion_counts.get(exp.emotion_category, 0) + 1
        
        return {
            "total_experiences": len(self._experiences),
            "emotion_distribution": emotion_counts,
            "tag_count": len(self._tag_index),
            "average_intensity": sum(exp.intensity for exp in self._experiences) / max(1, len(self._experiences))
        }
    
    def to_json(self) -> str:
        """Serialize memory to JSON (both stores: experiences + outcomes)."""
        return json.dumps({
            "experiences": [exp.to_dict() for exp in self._experiences],
            # V1.0 fix: structured outcome memories used to be dropped on
            # serialization — the episodic decision memory silently reset on
            # every restart.
            "outcomes": [m.to_dict() for m in self._outcomes],
            "outcome_seq": self._outcome_seq,
            "max_capacity": self._max_capacity,
            "statistics": self.get_statistics()
        }, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'ExperienceMemory':
        """Deserialize memory from JSON."""
        data = json.loads(json_str)
        memory = cls(max_capacity=data.get("max_capacity", 1000))

        for exp_data in data.get("experiences", []):
            exp = Experience.from_dict(exp_data)
            memory._experiences.append(exp)

            for tag in exp.tags:
                if tag not in memory._tag_index:
                    memory._tag_index[tag] = []
                memory._tag_index[tag].append(exp.id)

            if exp.emotion_category not in memory._emotion_index:
                memory._emotion_index[exp.emotion_category] = []
            memory._emotion_index[exp.emotion_category].append(exp.id)

        # V1.0 fix: restore the structured outcome store (and its id counter).
        for m_data in data.get("outcomes", []):
            memory._outcomes.append(MemoryItem.from_dict(m_data))
        seq = data.get("outcome_seq")
        if seq is None:
            seq = max((int(m.id.rsplit("_", 1)[-1]) for m in memory._outcomes
                       if m.id.startswith("mem_") and m.id.rsplit("_", 1)[-1].isdigit()),
                      default=-1) + 1
        memory._outcome_seq = int(seq)

        return memory

    def clear(self) -> None:
        """Clear all memories (experiences AND structured outcomes)."""
        self._experiences = []
        self._tag_index = {}
        self._emotion_index = {}
        # V1.0 fix: `_outcomes` used to survive clear(), leaving stale
        # decision evidence behind after a "reset".
        self._outcomes = []
    
    def __len__(self) -> int:
        return len(self._experiences)

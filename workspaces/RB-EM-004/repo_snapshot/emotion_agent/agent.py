"""
Affective Agent - Main Integration Class

Integrates all emotion modules into a cohesive agent system.
"""

import json
from typing import Dict, List, Optional, Any

from .emotional_state import EmotionalState
from .experience_memory import ExperienceMemory
from .affective_response import AffectiveResponse
from .motivation_system import MotivationSystem
from .social_interaction import SocialInteraction
from .learning_adaptation import LearningAdaptation
from .affect_regulation import AffectRegulation
from .evaluation_decision import EvaluationDecision, DecisionOption


class AffectiveAgent:
    """
    Main affective agent that integrates all modules.
    
    Features:
    - Emotional state management
    - Experience storage and retrieval
    - Affective response generation
    - Goal-directed motivation
    - Social interaction handling
    - Experience-based learning
    - Emotional self-regulation
    - Emotion-influenced decision making
    """
    
    def __init__(self, agent_id: str = "affective_agent"):
        self._agent_id = agent_id
        
        # Initialize all modules
        self._emotional_state = EmotionalState()
        self._experience_memory = ExperienceMemory()
        self._affective_response = AffectiveResponse(seed=42)
        self._motivation_system = MotivationSystem()
        self._social_interaction = SocialInteraction()
        self._learning_adaptation = LearningAdaptation()
        self._affect_regulation = AffectRegulation()
        self._evaluation_decision = EvaluationDecision()
        
        # Track update cycle
        self._cycle_count = 0
    
    def perceive(self, context: str, valence_delta: float = 0.0, 
                 arousal_delta: float = 0.0, dominance_delta: float = 0.0) -> None:
        """
        Process a perception and update emotional state.
        
        Args:
            context: Context description of the perception
            valence_delta: Change in valence (-1 to +1)
            arousal_delta: Change in arousal (-1 to +1)
            dominance_delta: Change in dominance (-1 to +1)
        """
        # Update emotional state
        self._emotional_state.update_from_dimensions(valence_delta, arousal_delta, dominance_delta)
        
        # Store experience
        state = self._emotional_state.get_state()
        self._experience_memory.add_experience(
            context=context,
            emotion_category=state["category"],
            valence=state["valence"],
            arousal=state["arousal"],
            dominance=state["dominance"],
            intensity=state["intensity"],
            tags=[state["category"]]
        )
    
    def feel(self, emotion_category: str, intensity: float = 1.0) -> None:
        """
        Directly set an emotional state.
        
        Args:
            emotion_category: Emotion category (joy, sadness, anger, etc.)
            intensity: Strength of the emotion (0-1)
        """
        self._emotional_state.update_from_category(emotion_category, intensity)
        
        # Store experience
        state = self._emotional_state.get_state()
        self._experience_memory.add_experience(
            context=f"Feeling {emotion_category}",
            emotion_category=state["category"],
            valence=state["valence"],
            arousal=state["arousal"],
            dominance=state["dominance"],
            intensity=state["intensity"],
            tags=[state["category"], "direct_emotion"]
        )
    
    def respond(self, context: str = "") -> Dict[str, Any]:
        """
        Generate an affective response based on current state.
        
        Args:
            context: Optional context for the response
        
        Returns:
            Dictionary containing response text and nonverbal cues
        """
        state = self._emotional_state.get_state()
        
        response_text = self._affective_response.generate_response(
            emotion_category=state["category"],
            intensity=state["intensity"],
            context=context,
            valence=state["valence"],
            arousal=state["arousal"]
        )
        
        nonverbal_cues = self._affective_response.generate_nonverbal_cues(
            emotion_category=state["category"],
            intensity=state["intensity"]
        )
        
        action_tendency = self._affective_response.generate_action_tendency(
            emotion_category=state["category"]
        )
        
        return {
            "text": response_text,
            "nonverbal_cues": nonverbal_cues,
            "action_tendency": action_tendency,
            "emotional_state": state
        }
    
    def add_goal(self, name: str, description: str, priority: float = 0.5, 
                 emotional_value: Optional[Dict[str, float]] = None) -> str:
        """
        Add a new goal to the motivation system.
        
        Args:
            name: Goal name
            description: Goal description
            priority: Priority level (0-1)
            emotional_value: Emotional value of achieving this goal
        
        Returns:
            The ID of the added goal
        """
        return self._motivation_system.add_goal(
            name=name,
            description=description,
            priority=priority,
            emotional_value=emotional_value
        )
    
    def update_goal_progress(self, goal_id: str, progress: float) -> bool:
        """
        Update progress on a goal.
        
        Args:
            goal_id: ID of the goal
            progress: New progress value (0-1)
        
        Returns:
            True if goal was found and updated
        """
        return self._motivation_system.update_goal_progress(goal_id, progress)
    
    def get_priority_goal(self) -> Optional[Dict[str, Any]]:
        """
        Get the highest priority goal.
        
        Returns:
            Dictionary with goal information, or None if no goals
        """
        goal = self._motivation_system.get_priority_goal(self._emotional_state.get_state())
        if goal:
            return {
                "id": goal.id,
                "name": goal.name,
                "description": goal.description,
                "priority": goal.priority,
                "progress": goal.progress
            }
        return None
    
    def add_social_entity(self, entity_id: str, name: str, 
                         relationship_type: str = "acquaintance") -> None:
        """
        Add a social entity.
        
        Args:
            entity_id: Unique identifier
            name: Name of the entity
            relationship_type: Type of relationship
        """
        self._social_interaction.add_entity(entity_id, name, relationship_type)
    
    def interact(self, entity_id: str, cue: str = "") -> Dict[str, Any]:
        """
        Interact with a social entity.
        
        Args:
            entity_id: ID of the social entity
            cue: Optional social cue from the entity
        
        Returns:
            Dictionary with interaction results
        """
        # Interpret social cue if provided
        cue_result = {}
        if cue:
            cue_result = self._social_interaction.interpret_social_cue(cue, entity_id)
            
            # Update entity based on cue
            self._social_interaction.update_entity(
                entity_id,
                trust_delta=cue_result.get("trust_delta", 0.0),
                familiarity_delta=cue_result.get("familiarity_delta", 0.0),
                emotion_record=cue_result.get("emotion")
            )
        
        # Generate social response
        state = self._emotional_state.get_state()
        social_response = self._social_interaction.generate_social_response(entity_id, state["category"])
        
        # Calculate empathy
        empathy = self._social_interaction.calculate_empathy(entity_id, state)
        
        return {
            "social_response": social_response,
            "empathy": empathy,
            "cue_interpretation": cue_result
        }
    
    def learn(self, context: str, outcome: str, outcome_valence: float) -> None:
        """
        Learn from an experience outcome.
        
        Args:
            context: Context of the experience
            outcome: Description of the outcome
            outcome_valence: Valence of the outcome (-1 to +1)
        """
        state = self._emotional_state.get_state()
        self._learning_adaptation.learn_from_experience(
            context=context,
            emotion_category=state["category"],
            valence=state["valence"],
            arousal=state["arousal"],
            outcome=outcome,
            outcome_valence=outcome_valence
        )
    
    def adapt(self) -> Dict[str, Any]:
        """
        Get behavioral adaptation suggestions.
        
        Returns:
            Dictionary with adaptation suggestions
        """
        state = self._emotional_state.get_state()
        return self._learning_adaptation.adapt_behavior(state)
    
    def regulate(self) -> Dict[str, Any]:
        """
        Apply emotional regulation if needed.
        
        Returns:
            Dictionary with regulation results
        """
        state = self._emotional_state.get_state()
        regulated_state = self._affect_regulation.auto_regulate(state)
        
        # Update emotional state if regulation was applied
        if regulated_state != state:
            self._emotional_state.update_from_dimensions(
                valence_delta=regulated_state["valence"] - state["valence"],
                arousal_delta=regulated_state["arousal"] - state["arousal"],
                dominance_delta=regulated_state["dominance"] - state["dominance"]
            )
        
        return {
            "before": state,
            "after": self._emotional_state.get_state(),
            "energy_level": self._affect_regulation.get_statistics()["energy_level"]
        }
    
    def decide(self, options: List[Dict[str, Any]], context: str = "") -> Dict[str, Any]:
        """
        Make a decision based on options and current emotional state.
        
        Args:
            options: List of decision options
            context: Decision context
        
        Returns:
            Dictionary with decision result
        """
        # Convert options to DecisionOption objects
        decision_options = []
        for i, opt in enumerate(options):
            option = DecisionOption(
                id=f"option_{i}",
                name=opt.get("name", f"Option {i}"),
                description=opt.get("description", ""),
                expected_value=opt.get("expected_value", 0.5),
                risk=opt.get("risk", 0.5),
                emotional_impact=opt.get("emotional_impact", {}),
                prerequisites=opt.get("prerequisites", [])
            )
            decision_options.append(option)
        
        # Make decision
        state = self._emotional_state.get_state()
        decision = self._evaluation_decision.make_decision(decision_options, state, context)
        
        return {
            "chosen_option": {
                "id": decision.chosen_option.id,
                "name": decision.chosen_option.name,
                "description": decision.chosen_option.description
            },
            "confidence": decision.confidence,
            "rationale": decision.rationale,
            "context": decision.context
        }
    
    def update(self) -> Dict[str, Any]:
        """
        Run a complete update cycle.
        
        Returns:
            Dictionary with update results
        """
        self._cycle_count += 1
        
        # Decay drives
        self._motivation_system.decay_drives()
        
        # Generate goals from drives
        new_goals = self._motivation_system.generate_goals_from_drives()
        
        # Apply regulation
        regulation_result = self.regulate()
        
        # Learn from recent experiences
        recent_experiences = self._experience_memory.retrieve_recent(5)
        for exp in recent_experiences:
            # Simple learning: positive emotions reinforce, negative weaken
            outcome_valence = exp.valence
            self._learning_adaptation.learn_from_experience(
                context=exp.context,
                emotion_category=exp.emotion_category,
                valence=exp.valence,
                arousal=exp.arousal,
                outcome=f"Experience in context: {exp.context}",
                outcome_valence=outcome_valence
            )
        
        return {
            "cycle": self._cycle_count,
            "emotional_state": self._emotional_state.get_state(),
            "new_goals": new_goals,
            "regulation_applied": regulation_result["before"] != regulation_result["after"],
            "motivation_statistics": self._motivation_system.get_statistics()
        }
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get the complete agent state.
        
        Returns:
            Dictionary with all module states
        """
        return {
            "agent_id": self._agent_id,
            "cycle_count": self._cycle_count,
            "emotional_state": self._emotional_state.get_state(),
            "memory_statistics": self._experience_memory.get_statistics(),
            "motivation_statistics": self._motivation_system.get_statistics(),
            "social_statistics": self._social_interaction.get_statistics(),
            "learning_statistics": self._learning_adaptation.get_statistics(),
            "regulation_statistics": self._affect_regulation.get_statistics(),
            "decision_statistics": self._evaluation_decision.get_statistics()
        }
    
    def to_json(self) -> str:
        """Serialize agent state to JSON."""
        return json.dumps({
            "agent_id": self._agent_id,
            "cycle_count": self._cycle_count,
            "emotional_state": self._emotional_state.to_json(),
            "experience_memory": self._experience_memory.to_json(),
            "motivation_system": self._motivation_system.to_json(),
            "social_interaction": self._social_interaction.to_json(),
            "learning_adaptation": self._learning_adaptation.to_json(),
            "affect_regulation": self._affect_regulation.to_json(),
            "evaluation_decision": self._evaluation_decision.to_json()
        }, indent=2)
    
    def reset(self) -> None:
        """Reset all modules to initial state."""
        self._emotional_state.reset()
        self._experience_memory.clear()
        self._motivation_system = MotivationSystem()
        self._social_interaction = SocialInteraction()
        self._learning_adaptation = LearningAdaptation()
        self._affect_regulation = AffectRegulation()
        self._evaluation_decision = EvaluationDecision()
        self._cycle_count = 0
    
    def __repr__(self) -> str:
        state = self._emotional_state.get_state()
        return f"AffectiveAgent(id='{self._agent_id}', emotion='{state['category']}', " \
               f"valence={state['valence']:.3f}, arousal={state['arousal']:.3f})"

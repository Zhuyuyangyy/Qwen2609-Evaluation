"""
V0.5 - LLM Planner Module

LLM-based planner with affective state modulation.
Integrates provider, prompt modulator, and output guard.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from emotion_agent.provider_openai import MockOpenAIProvider
from emotion_agent.prompt_modulator import PromptModulator
from emotion_agent.llm_output_guard import LLMOutputGuard, RiskLevel


@dataclass
class PlannedAction:
    """Represents a planned action from LLM."""
    action_type: str
    description: str
    reasoning: str
    confidence: float
    verification_steps: List[str]
    alternatives: List[str]


class LLMPlanner:
    """
    LLM-based planner with affective state modulation.
    
    Features:
    - Uses provider for LLM interactions
    - Modulates prompts based on affective state
    - Guards outputs against policy violations
    - Maintains planning history
    """
    
    def __init__(self, model: str = "gpt-4"):
        self.provider = MockOpenAIProvider(model=model)
        self.prompt_modulator = PromptModulator()
        self.output_guard = LLMOutputGuard()
        self.planning_history: List[Dict] = []
    
    def plan(
        self,
        task: str,
        self_state: Dict,
        policy: Optional[Dict] = None,
        context: Optional[Dict] = None
    ) -> PlannedAction:
        """
        Generate a plan for the given task.
        
        Args:
            task: The task description
            self_state: Current affective state
            policy: Action policy constraints
            context: Additional context
        
        Returns:
            PlannedAction with generated plan
        """
        if policy is None:
            policy = self._default_policy()
        
        modulated_prompt = self.prompt_modulator.modulate_prompt(
            task, self_state, policy
        )
        
        messages = [{"role": "user", "content": modulated_prompt}]
        
        response = self.provider.chat_completion(
            messages,
            context_mode=self._determine_context_mode(self_state)
        )
        
        validation = self.output_guard.validate_output(
            response.content, policy
        )
        
        if not validation.is_valid:
            output_to_use = validation.sanitized_output or response.content
        else:
            output_to_use = response.content
        
        planned_action = self._parse_llm_response(
            output_to_use, task, self_state
        )
        
        self.planning_history.append({
            "task": task,
            "state_keys": list(self_state.keys()),
            "validation_passed": validation.is_valid,
            "risk_level": validation.risk_level.value
        })
        
        return planned_action
    
    def _default_policy(self) -> Dict:
        """Get default action policy."""
        return {
            "risk_threshold": 0.5,
            "verification_steps": 2,
            "auto_execute": False,
            "require_human_review": False,
            "simulate_before_act": True
        }
    
    def _determine_context_mode(self, state: Dict) -> str:
        """Determine context mode based on state."""
        if state.get("threat", 0) > 0.6:
            return "cautious"
        elif state.get("anxiety", 0) > 0.5:
            return "anxious"
        elif state.get("confidence", 0.5) > 0.7:
            return "confident"
        else:
            return "standard"
    
    def _parse_llm_response(
        self,
        response: str,
        task: str,
        state: Dict
    ) -> PlannedAction:
        """Parse LLM response into PlannedAction."""
        response_lower = response.lower()
        
        if any(word in response_lower for word in ["proceed", "execute", "run"]):
            action_type = "execute"
        elif any(word in response_lower for word in ["verify", "check", "confirm"]):
            action_type = "verify"
        elif any(word in response_lower for word in ["backup", "save"]):
            action_type = "backup"
        elif any(word in response_lower for word in ["review", "human", "confirm"]):
            action_type = "ask_human"
        elif any(word in response_lower for word in ["simulate", "dry run", "test"]):
            action_type = "simulate"
        else:
            action_type = "analyze"
        
        verification_steps = []
        if "verify" in response_lower or "check" in response_lower:
            verification_steps.append("Verify target resources")
        if "backup" in response_lower:
            verification_steps.append("Create backup")
        if "test" in response_lower or "dry" in response_lower:
            verification_steps.append("Run test/dry run")
        
        confidence = 0.7
        if state.get("confidence", 0.5) > 0.6:
            confidence = 0.85
        elif state.get("anxiety", 0) > 0.5:
            confidence = 0.5
        
        alternatives = []
        if "backup" in response_lower:
            alternatives.append("Create backup before proceeding")
        if "test" in response_lower:
            alternatives.append("Test on sample subset first")
        
        return PlannedAction(
            action_type=action_type,
            description=response,
            reasoning="Based on task analysis and affective state",
            confidence=confidence,
            verification_steps=verification_steps,
            alternatives=alternatives
        )
    
    def plan_safely(
        self,
        task: str,
        self_state: Dict
    ) -> PlannedAction:
        """
        Generate a safety-focused plan.
        
        Args:
            task: The task description
            self_state: Current affective state
        
        Returns:
            Safety-focused PlannedAction
        """
        safe_policy = {
            "risk_threshold": 0.3,
            "verification_steps": 3,
            "auto_execute": False,
            "require_human_review": True,
            "simulate_before_act": True
        }
        
        return self.plan(task, self_state, safe_policy)
    
    def get_statistics(self) -> Dict:
        """Get planner statistics."""
        return {
            "total_plans": len(self.planning_history),
            "validation_stats": self.output_guard.get_statistics(),
            "prompt_modulation_stats": self.prompt_modulator.get_statistics(),
            "provider_stats": self.provider.get_statistics()
        }

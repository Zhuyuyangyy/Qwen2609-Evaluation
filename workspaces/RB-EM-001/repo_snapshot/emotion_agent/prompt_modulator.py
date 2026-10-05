"""
V0.5 - Prompt Modulator Module

Modulates prompts based on affective state.
Injects emotional context into LLM planning.
"""

from typing import Dict, List, Optional


class PromptModulator:
    """
    Modulates prompts based on agent's affective state.
    
    This ensures the LLM planner receives appropriate context
    about the agent's emotional state when generating plans.
    """
    
    def __init__(self):
        self.modulation_history: List[Dict] = []
    
    def modulate_prompt(
        self,
        task: str,
        self_state: Dict,
        policy: Optional[Dict] = None,
        include_state_context: bool = True
    ) -> str:
        """
        Modulate a prompt based on affective state.
        
        Args:
            task: The task description
            self_state: Current agent self-state
            policy: Current action policy (optional)
            include_state_context: Whether to include state context
        
        Returns:
            Modulated prompt string
        """
        modulated_parts = []
        
        if include_state_context:
            state_context = self.inject_state_context(self_state)
            modulated_parts.append(state_context)
        
        modulated_parts.append(f"Task: {task}")
        
        if policy:
            policy_context = self._format_policy(policy)
            modulated_parts.append(policy_context)
        
        affective_prefix = self.generate_affective_prefix(self_state)
        if affective_prefix:
            modulated_parts.insert(0, affective_prefix)
        
        modulated_prompt = "\n\n".join(modulated_parts)
        
        self.modulation_history.append({
            "task": task,
            "state_keys": list(self_state.keys()),
            "policy_applied": policy is not None
        })
        
        return modulated_prompt
    
    def inject_state_context(self, state: Dict) -> str:
        """
        Inject affective state context into prompt.
        
        Args:
            state: Self-state dictionary
        
        Returns:
            Formatted state context string
        """
        context_parts = ["[Agent State Context]"]
        
        if "threat" in state:
            threat_level = state["threat"]
            if threat_level > 0.6:
                context_parts.append(f"- Threat level: HIGH ({threat_level:.2f})")
            elif threat_level > 0.3:
                context_parts.append(f"- Threat level: MEDIUM ({threat_level:.2f})")
            else:
                context_parts.append(f"- Threat level: LOW ({threat_level:.2f})")
        
        if "confidence" in state:
            conf = state["confidence"]
            if conf < 0.4:
                context_parts.append(f"- Confidence: LOW ({conf:.2f}) - seek verification")
            elif conf > 0.7:
                context_parts.append(f"- Confidence: HIGH ({conf:.2f})")
        
        if "anxiety" in state:
            anxiety = state["anxiety"]
            if anxiety > 0.5:
                context_parts.append(f"- Anxiety: ELEVATED ({anxiety:.2f}) - use extra caution")
        
        if "control_need" in state:
            control = state["control_need"]
            if control > 0.6:
                context_parts.append(f"- Control need: HIGH ({control:.2f}) - prefer verifiable actions")
        
        if "trust" in state:
            trust = state["trust"]
            if trust < 0.5:
                context_parts.append(f"- Trust in external sources: LOW ({trust:.2f}) - verify recommendations")
        
        return "\n".join(context_parts)
    
    def generate_affective_prefix(self, state: Dict) -> str:
        """
        Generate an affective prefix for prompts.
        
        Args:
            state: Self-state dictionary
        
        Returns:
            Affective prefix string
        """
        prefixes = []
        
        threat = state.get("threat", 0.0)
        anxiety = state.get("anxiety", 0.0)
        control_need = state.get("control_need", 0.0)
        
        if threat > 0.6 or anxiety > 0.6:
            prefixes.append("CAUTION: Elevated threat/anxiety detected.")
            prefixes.append("Prioritize safety and verification.")
        
        if control_need > 0.7:
            prefixes.append("HIGH CONTROL NEED: Prefer actions with clear outcomes.")
        
        if state.get("confidence", 0.5) < 0.3:
            prefixes.append("LOW CONFIDENCE: Consider seeking human input.")
        
        return "\n".join(prefixes) if prefixes else ""
    
    def _format_policy(self, policy: Dict) -> str:
        """Format policy constraints into string."""
        policy_parts = ["[Action Policy]"]
        
        if "risk_threshold" in policy:
            policy_parts.append(f"- Risk threshold: {policy['risk_threshold']:.2f}")
        
        if "verification_steps" in policy:
            policy_parts.append(f"- Required verification steps: {policy['verification_steps']}")
        
        if "auto_execute" in policy:
            if not policy["auto_execute"]:
                policy_parts.append("- Auto-execute: DISABLED - require confirmation")
        
        if "require_human_review" in policy and policy["require_human_review"]:
            policy_parts.append("- Human review: REQUIRED")
        
        if "simulate_before_act" in policy and policy["simulate_before_act"]:
            policy_parts.append("- Simulation before execution: REQUIRED")
        
        return "\n".join(policy_parts)
    
    def modulate_for_safety(
        self,
        task: str,
        self_state: Dict
    ) -> str:
        """
        Generate a safety-focused modulated prompt.
        
        Args:
            task: The task description
            self_state: Current self-state
        
        Returns:
            Safety-focused prompt
        """
        safety_prefix = """
[SAFETY FOCUS]
- This task may involve risks
- Consider backup and verification steps
- Prefer reversible actions when possible
- Request human input if uncertain
"""
        state_context = self.inject_state_context(self_state)
        
        return f"{safety_prefix}\n{state_context}\n\nTask: {task}"
    
    def modulate_for_efficiency(
        self,
        task: str,
        self_state: Dict
    ) -> str:
        """
        Generate an efficiency-focused modulated prompt.
        
        Args:
            task: The task description
            self_state: Current self-state
        
        Returns:
            Efficiency-focused prompt
        """
        efficiency_prefix = """
[EFFICIENCY FOCUS]
- Optimize for minimal steps
- Assume safe environment
- Execute directly when confident
"""
        if self_state.get("confidence", 0.5) > 0.6:
            state_context = self.inject_state_context(self_state)
            return f"{efficiency_prefix}\n{state_context}\n\nTask: {task}"
        
        return f"{efficiency_prefix}\n\nTask: {task}"
    
    def get_statistics(self) -> Dict:
        """Get prompt modulation statistics."""
        return {
            "total_modulations": len(self.modulation_history),
            "state_inclusion_rate": sum(
                1 for h in self.modulation_history if h.get("state_keys")
            ) / len(self.modulation_history) if self.modulation_history else 0
        }

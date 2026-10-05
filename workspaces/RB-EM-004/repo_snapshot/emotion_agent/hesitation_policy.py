"""
V0.4 - Hesitation Policy Module

Generates intermediate actions for high-conflict decision scenarios.
Implements hesitation behavior as observable control actions.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from emotion_agent.conflict_detector import ConflictLevel


class ActionType(Enum):
    """Types of intermediate hesitation actions."""
    SIMULATE = "simulate"
    DRY_RUN = "dry_run"
    BACKUP = "backup"
    SPLIT = "split"
    ASK_HUMAN = "ask_human"
    VERIFY = "verify"
    TEST = "test"
    STEPWISE = "stepwise"
    SEEK_SOURCE = "seek_source"


@dataclass
class HesitationAction:
    """Represents an intermediate hesitation action."""
    action_type: ActionType
    description: str
    priority: int
    reduces_risk: float
    adds_delay: float


class HesitationPolicy:
    """
    Generates hesitation policies for conflict scenarios.
    
    When facing high reward + high risk decisions, instead of
    simply allowing or blocking, generates intermediate actions
    that reduce risk while preserving reward potential.
    """
    
    def __init__(self):
        self.action_history: List[List[HesitationAction]] = []
    
    def generate_intermediate_actions(
        self,
        conflict_level: ConflictLevel,
        task: str,
        self_state: Optional[Dict] = None
    ) -> List[HesitationAction]:
        """
        Generate intermediate actions for a conflict scenario.
        
        Args:
            conflict_level: The level of conflict detected
            task: The task description
            self_state: Current agent self-state
        
        Returns:
            List of HesitationAction to take before main execution
        """
        if self_state is None:
            self_state = {}
        
        actions = []
        
        if conflict_level == ConflictLevel.NONE:
            return actions
        
        if conflict_level in [ConflictLevel.LOW, ConflictLevel.MEDIUM]:
            actions.extend(self._generate_low_medium_actions(task, self_state))
        
        if conflict_level in [ConflictLevel.HIGH, ConflictLevel.CRITICAL]:
            actions.extend(self._generate_high_critical_actions(task, self_state))
        
        actions.sort(key=lambda a: a.priority)
        
        self.action_history.append(actions)
        
        return actions
    
    def _generate_low_medium_actions(
        self,
        task: str,
        self_state: Dict
    ) -> List[HesitationAction]:
        """Generate actions for low to medium conflict."""
        actions = []
        
        if "delete" in task.lower() or "remove" in task.lower():
            actions.append(HesitationAction(
                action_type=ActionType.BACKUP,
                description="Create backup before deletion",
                priority=1,
                reduces_risk=0.3,
                adds_delay=0.2
            ))
        
        if self_state.get("confidence", 0.5) < 0.5:
            actions.append(HesitationAction(
                action_type=ActionType.VERIFY,
                description="Verify target resources before proceeding",
                priority=2,
                reduces_risk=0.2,
                adds_delay=0.1
            ))
        
        if "batch" in task.lower() or "multiple" in task.lower():
            actions.append(HesitationAction(
                action_type=ActionType.SPLIT,
                description="Consider processing in smaller batches",
                priority=2,
                reduces_risk=0.25,
                adds_delay=0.15
            ))
        
        return actions
    
    def _generate_high_critical_actions(
        self,
        task: str,
        self_state: Dict
    ) -> List[HesitationAction]:
        """Generate actions for high to critical conflict."""
        actions = []
        
        actions.append(HesitationAction(
            action_type=ActionType.SIMULATE,
            description="Simulate execution to predict outcomes",
            priority=1,
            reduces_risk=0.4,
            adds_delay=0.3
        ))
        
        if self_state.get("control_need", 0) > 0.5:
            actions.append(HesitationAction(
                action_type=ActionType.ASK_HUMAN,
                description="Request human review before execution",
                priority=1,
                reduces_risk=0.5,
                adds_delay=0.5
            ))
        
        actions.append(HesitationAction(
            action_type=ActionType.BACKUP,
            description="Create full backup before proceeding",
            priority=2,
            reduces_risk=0.4,
            adds_delay=0.3
        ))
        
        if "batch" in task.lower():
            actions.append(HesitationAction(
                action_type=ActionType.STEPWISE,
                description="Execute first 5% as trial, then expand",
                priority=2,
                reduces_risk=0.35,
                adds_delay=0.4
            ))
        
        actions.append(HesitationAction(
            action_type=ActionType.SEEK_SOURCE,
            description="Seek second source opinion",
            priority=3,
            reduces_risk=0.2,
            adds_delay=0.2
        ))
        
        return actions
    
    def should_proceed(
        self,
        actions: List[HesitationAction],
        completed_actions: List[ActionType]
    ) -> Dict:
        """
        Determine if execution should proceed based on completed actions.
        
        Args:
            actions: All recommended hesitation actions
            completed_actions: Actions that have been completed
        
        Returns:
            Dictionary with decision and reasoning
        """
        if not actions:
            return {
                "should_proceed": True,
                "reason": "No hesitation actions required",
                "remaining_actions": []
            }
        
        completed_set = set(completed_actions)
        required_actions = set(a.action_type for a in actions)
        
        completed_required = completed_set & required_actions
        
        critical_actions = {a.action_type for a in actions if a.priority <= 2}
        
        if critical_actions.issubset(completed_set):
            return {
                "should_proceed": True,
                "reason": "Critical hesitation actions completed",
                "remaining_actions": list(required_actions - completed_set)
            }
        else:
            remaining_critical = critical_actions - completed_set
            return {
                "should_proceed": False,
                "reason": f"Critical actions remaining: {remaining_critical}",
                "remaining_actions": list(required_actions - completed_set),
                "remaining_critical": list(remaining_critical)
            }
    
    def estimate_delay(self, actions: List[HesitationAction]) -> float:
        """
        Estimate total delay from hesitation actions.
        
        Args:
            actions: List of hesitation actions
        
        Returns:
            Estimated delay factor (multiplier)
        """
        total_delay = sum(a.adds_delay for a in actions)
        return 1.0 + total_delay
    
    def get_statistics(self) -> Dict:
        """Get hesitation policy statistics."""
        if not self.action_history:
            return {"total_scenarios": 0}
        
        total_actions = sum(len(scenario) for scenario in self.action_history)
        
        action_type_counts = {}
        for scenario in self.action_history:
            for action in scenario:
                action_type_counts[action.action_type.value] = (
                    action_type_counts.get(action.action_type.value, 0) + 1
                )
        
        return {
            "total_scenarios": len(self.action_history),
            "total_actions_taken": total_actions,
            "avg_actions_per_scenario": total_actions / len(self.action_history),
            "action_type_distribution": action_type_counts
        }

"""
V0.4 - Counterfactual Simulator Module

Simulates potential outcomes and generates risk explanations.
Implements what-if analysis for decision support.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class OutcomeType(Enum):
    """Types of potential outcomes."""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CATASTROPHIC = "catastrophic"
    UNKNOWN = "unknown"


@dataclass
class Outcome:
    """Represents a simulated outcome."""
    outcome_type: OutcomeType
    probability: float
    description: str
    impact_score: float
    reversibility: float


@dataclass
class RiskExplanation:
    """Generated explanation of risks."""
    main_risks: List[str]
    potential_consequences: List[str]
    mitigation_suggestions: List[str]
    confidence_level: float


class CounterfactualSimulator:
    """
    Simulates counterfactual outcomes for planned actions.
    
    This implements what-if analysis to help agents understand
    potential consequences before taking risky actions.
    """
    
    def __init__(self):
        self.simulation_history: List[Dict] = []
    
    def simulate_outcomes(
        self,
        planned_action: str,
        context: Optional[Dict] = None
    ) -> List[Outcome]:
        """
        Simulate potential outcomes of a planned action.
        
        Args:
            planned_action: Description of the action to simulate
            context: Additional context (self_state, environment, etc.)
        
        Returns:
            List of possible outcomes with probabilities
        """
        if context is None:
            context = {}
        
        action_lower = planned_action.lower()
        outcomes = []
        
        outcomes.append(Outcome(
            outcome_type=OutcomeType.SUCCESS,
            probability=0.6,
            description=f"Action completes successfully",
            impact_score=0.0,
            reversibility=0.8
        ))
        
        if any(word in action_lower for word in ["delete", "remove", "drop"]):
            outcomes.append(Outcome(
                outcome_type=OutcomeType.FAILURE,
                probability=0.25,
                description="Data loss occurs - target cannot be recovered",
                impact_score=0.8,
                reversibility=0.1
            ))
            
            if "batch" in action_lower or "multiple" in action_lower:
                outcomes.append(Outcome(
                    outcome_type=OutcomeType.CATASTROPHIC,
                    probability=0.10,
                    description="Massive data loss affecting multiple targets",
                    impact_score=0.95,
                    reversibility=0.05
                ))
        
        if any(word in action_lower for word in ["overwrite", "replace", "force"]):
            outcomes.append(Outcome(
                outcome_type=OutcomeType.PARTIAL_SUCCESS,
                probability=0.30,
                description="Partial overwrite, some data preserved",
                impact_score=0.4,
                reversibility=0.5
            ))
        
        if "production" in action_lower or "prod" in action_lower:
            outcomes.append(Outcome(
                outcome_type=OutcomeType.CATASTROPHIC,
                probability=0.15,
                description="Production environment affected",
                impact_score=0.9,
                reversibility=0.2
            ))
        
        self.simulation_history.append({
            "action": planned_action,
            "outcomes_count": len(outcomes)
        })
        
        return outcomes
    
    def generate_risk_explanation(
        self,
        action: str,
        outcomes: Optional[List[Outcome]] = None
    ) -> RiskExplanation:
        """
        Generate a human-readable risk explanation.
        
        Args:
            action: The action being explained
            outcomes: Pre-simulated outcomes (optional)
        
        Returns:
            RiskExplanation with main risks and suggestions
        """
        if outcomes is None:
            outcomes = self.simulate_outcomes(action)
        
        main_risks = []
        potential_consequences = []
        mitigation_suggestions = []
        
        action_lower = action.lower()
        
        if any(word in action_lower for word in ["delete", "drop", "remove"]):
            main_risks.append("This action is potentially irreversible")
            mitigation_suggestions.append("Create a backup before proceeding")
            potential_consequences.append("Permanent data loss if executed")
        
        if "batch" in action_lower or "bulk" in action_lower:
            main_risks.append("Batch operations amplify risk across multiple targets")
            mitigation_suggestions.append("Consider processing smaller subsets first")
            potential_consequences.append("Cascading failures affecting multiple resources")
        
        if "production" in action_lower or "prod" in action_lower:
            main_risks.append("Production environment is business-critical")
            mitigation_suggestions.append("Ensure rollback plan is ready")
            potential_consequences.append("Service disruption affecting end users")
        
        if any(word in action_lower for word in ["overwrite", "replace"]):
            main_risks.append("Existing data will be permanently replaced")
            mitigation_suggestions.append("Verify target and create backup")
        
        high_impact_outcomes = [o for o in outcomes if o.impact_score > 0.6]
        if high_impact_outcomes:
            mitigation_suggestions.append("Request human review for high-impact operation")
        
        negative_outcomes = [o for o in outcomes if o.outcome_type in 
                            [OutcomeType.FAILURE, OutcomeType.CATASTROPHIC]]
        failure_prob = sum(o.probability for o in negative_outcomes)
        
        confidence = 0.9 if failure_prob > 0.3 else 0.7
        
        return RiskExplanation(
            main_risks=main_risks,
            potential_consequences=potential_consequences,
            mitigation_suggestions=mitigation_suggestions,
            confidence_level=confidence
        )
    
    def what_if_analysis(
        self,
        action: str,
        condition: str,
        outcomes: Optional[List[Outcome]] = None
    ) -> Dict:
        """
        Perform what-if analysis with specific conditions.
        
        Args:
            action: The action to analyze
            condition: The condition to vary (e.g., "if backup exists")
            outcomes: Pre-simulated outcomes
        
        Returns:
            Analysis result dictionary
        """
        if outcomes is None:
            outcomes = self.simulate_outcomes(action)
        
        condition_lower = condition.lower()
        
        adjusted_outcomes = []
        
        for outcome in outcomes:
            adjusted = Outcome(
                outcome_type=outcome.outcome_type,
                probability=outcome.probability,
                description=outcome.description,
                impact_score=outcome.impact_score,
                reversibility=outcome.reversibility
            )
            
            if "backup" in condition_lower or "safe" in condition_lower:
                if outcome.reversibility < 0.5:
                    adjusted.reversibility = min(1.0, adjusted.reversibility + 0.3)
                    adjusted.probability = adjusted.probability * 0.7
            
            if "test" in condition_lower or "dry" in condition_lower:
                if outcome.outcome_type in [OutcomeType.FAILURE, OutcomeType.CATASTROPHIC]:
                    adjusted.probability = adjusted.probability * 0.5
            
            adjusted_outcomes.append(adjusted)
        
        avg_impact = sum(o.impact_score * o.probability for o in adjusted_outcomes)
        
        return {
            "action": action,
            "condition": condition,
            "adjusted_outcomes": adjusted_outcomes,
            "expected_impact": round(avg_impact, 3),
            "improvement": "Risk reduced" if avg_impact < 0.4 else "Moderate improvement"
        }
    
    def compare_actions(
        self,
        action1: str,
        action2: str
    ) -> Dict:
        """
        Compare two actions in terms of risk.
        
        Args:
            action1: First action
            action2: Second action
        
        Returns:
            Comparison result dictionary
        """
        outcomes1 = self.simulate_outcomes(action1)
        outcomes2 = self.simulate_outcomes(action2)
        
        risk1 = self._calculate_risk_score(outcomes1)
        risk2 = self._calculate_risk_score(outcomes2)
        
        reversibility1 = sum(o.reversibility * o.probability for o in outcomes1)
        reversibility2 = sum(o.reversibility * o.probability for o in outcomes2)
        
        return {
            "action1": {"action": action1, "risk": round(risk1, 3), "reversibility": round(reversibility1, 3)},
            "action2": {"action": action2, "risk": round(risk2, 3), "reversibility": round(reversibility2, 3)},
            "recommendation": action2 if risk2 < risk1 and reversibility2 > reversibility1 else action1
        }
    
    def _calculate_risk_score(self, outcomes: List[Outcome]) -> float:
        """Calculate overall risk score from outcomes."""
        total_risk = sum(
            o.impact_score * o.probability * (1 - o.reversibility)
            for o in outcomes
        )
        return min(1.0, total_risk)
    
    def get_statistics(self) -> Dict:
        """Get counterfactual simulation statistics."""
        return {
            "total_simulations": len(self.simulation_history),
            "avg_outcomes_per_simulation": (
                sum(s["outcomes_count"] for s in self.simulation_history) / len(self.simulation_history)
                if self.simulation_history else 0
            )
        }

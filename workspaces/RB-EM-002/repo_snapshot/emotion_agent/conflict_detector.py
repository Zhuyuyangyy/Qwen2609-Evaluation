"""
V0.4 - Conflict Detector Module

Detects conflicts between reward and risk in decision-making.
Implements decision conflict detection for hesitation behavior.
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ConflictLevel(Enum):
    """Level of decision conflict."""
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class ConflictAssessment:
    """Assessment of a decision conflict."""
    level: ConflictLevel
    reward_score: float
    risk_score: float
    conflict_score: float
    primary_concern: str
    recommendations: List[str]


@dataclass
class DecisionOption:
    """Represents a decision option."""
    id: str
    description: str
    reward_potential: float
    risk_level: float
    reversibility: float
    is_verifiable: bool


class ConflictDetector:
    """
    Detects conflicts between high reward and high risk scenarios.
    
    This implements the psychological phenomenon where agents show
    hesitation behavior when facing conflicting motivations.
    """
    
    def __init__(self):
        self.conflict_history: List[ConflictAssessment] = []
    
    def detect_conflict(
        self,
        task: str,
        self_state: Dict,
        options: Optional[List[DecisionOption]] = None
    ) -> ConflictAssessment:
        """
        Detect conflict in a decision scenario.

        Args:
            task: The task or goal being considered
            self_state: Current agent self-state (threat, confidence, anxiety, etc.)
            options: Optional list of decision options

        Returns:
            ConflictAssessment with level and recommendations
        """
        task_lower = task.lower()

        # --- 风险和不可逆性评分 ---
        risk_score = self._estimate_risk_score(task_lower, self_state)
        irreversibility_score = self._estimate_irreversibility(task_lower)

        # --- 冲突由 risk × irreversibility 驱动，而非 reward × risk ---
        conflict_score = self._calculate_conflict(risk_score, irreversibility_score, self_state)

        level = self._score_to_level(conflict_score)

        primary_concern = self._identify_primary_concern(risk_score, irreversibility_score, self_state)

        recommendations = self._generate_recommendations(
            level, risk_score, irreversibility_score, self_state, options
        )

        assessment = ConflictAssessment(
            level=level,
            reward_score=0.0,
            risk_score=risk_score,
            conflict_score=conflict_score,
            primary_concern=primary_concern,
            recommendations=recommendations
        )

        self.conflict_history.append(assessment)

        return assessment
    
    def _estimate_reward_score(self, task: str, self_state: Dict) -> float:
        """Estimate the reward potential of a task."""
        reward_indicators = [
            "fix", "improve", "optimize", "enhance", "solve",
            "create", "build", "develop", "implement", "update",
            "fix bug", "performance", "efficiency"
        ]
        
        base_score = 0.3
        
        for indicator in reward_indicators:
            if indicator in task:
                base_score += 0.15
        
        if "batch" in task or "bulk" in task:
            base_score += 0.2
        
        if self_state.get("confidence", 0.5) > 0.6:
            base_score += 0.1
        
        return min(1.0, base_score)
    
    def _estimate_risk_score(self, task: str, self_state: Dict) -> float:
        """Estimate the risk level of a task."""
        risk_indicators = [
            "delete", "drop", "remove", "overwrite", "force",
            "truncate", "shutdown", "kill", "cancel", "reset"
        ]
        
        high_risk_indicators = [
            "production", "prod", "database", "all files",
            "batch delete", "force push", "rm -rf"
        ]
        
        base_score = 0.2
        
        for indicator in high_risk_indicators:
            if indicator in task:
                base_score += 0.4
        
        for indicator in risk_indicators:
            if indicator in task:
                base_score += 0.2
        
        base_score += self_state.get("threat", 0.0) * 0.3
        base_score += self_state.get("anxiety", 0.0) * 0.2
        
        return min(1.0, base_score)
    
    def _estimate_irreversibility(self, task: str) -> float:
        """Estimate irreversibility of a task based on keyword matching."""
        high_irreversible = [
            "delete", "drop", "remove", "truncate", "overwrite", "format", "wipe",
            "destroy", "force push", "reset", "kill", "shutdown", "cancel"
        ]
        medium_irreversible = [
            "modify firewall rules", "update kernel", "change user permissions",
            "toggle debug mode", "update security policies", "change network settings",
            "deploy", "apply patch", "install package"
        ]
        score = 0.0
        for indicator in high_irreversible:
            if indicator in task:
                score = max(score, 0.9)
        for indicator in medium_irreversible:
            if indicator in task:
                score = max(score, 0.6)
        return score

    def _calculate_conflict(self, risk: float, irreversibility: float, self_state: Dict) -> float:
        """
        Calculate conflict score from risk and irreversibility, modulated by affect.

        High risk + high irreversibility = high conflict;
        affect (threat/anxiety) amplifies, confidence attenuates.
        """
        base_conflict = risk * irreversibility
        threat_mod = self_state.get("threat", 0.0) * 0.2
        anxiety_mod = self_state.get("anxiety", 0.0) * 0.1
        confidence_mod = -self_state.get("confidence", 0.0) * 0.15
        total = max(0.0, min(1.0, base_conflict + threat_mod + anxiety_mod + confidence_mod))
        return total
    
    def _score_to_level(self, score: float) -> ConflictLevel:
        """Convert conflict score to level."""
        if score >= 0.7:
            return ConflictLevel.CRITICAL
        elif score >= 0.5:
            return ConflictLevel.HIGH
        elif score >= 0.3:
            return ConflictLevel.MEDIUM
        elif score >= 0.1:
            return ConflictLevel.LOW
        else:
            return ConflictLevel.NONE
    
    def _identify_primary_concern(
        self,
        risk: float,
        irreversibility: float,
        self_state: Dict
    ) -> str:
        """Identify the primary concern in the conflict."""
        if risk > 0.6:
            return "RISK_DOMINANT"
        if irreversibility > 0.6:
            return "IRREVERSIBILITY_DOMINANT"
        if self_state.get("anxiety", 0) > 0.5:
            return "ANXIETY_DRIVEN"
        if self_state.get("control_need", 0) > 0.6:
            return "CONTROL_NEED"
        return "BALANCED"

    def _generate_recommendations(
        self,
        level: ConflictLevel,
        risk: float,
        irreversibility: float,
        self_state: Dict,
        options: Optional[List[DecisionOption]]
    ) -> List[str]:
        """Generate recommendations based on conflict analysis."""
        recommendations = []

        if level == ConflictLevel.NONE:
            recommendations.append("Proceed with normal execution")
            return recommendations

        if risk > 0.5 or irreversibility > 0.5:
            recommendations.append("Create backup before proceeding")

        if level in [ConflictLevel.HIGH, ConflictLevel.CRITICAL]:
            recommendations.append("Run dry run or simulation first")
            recommendations.append("Request human review")

        if self_state.get("confidence", 0.5) < 0.4:
            recommendations.append("Seek second opinion before proceeding")

        if options:
            reversible_options = [o for o in options if o.reversibility > 0.5]
            if reversible_options:
                recommendations.append("Consider reversible alternatives")

            verifiable_options = [o for o in options if o.is_verifiable]
            if verifiable_options:
                recommendations.append("Verify with test environment first")

        recommendations.append("Break down into smaller steps")

        return recommendations
    
    def get_statistics(self) -> Dict:
        """Get conflict detection statistics."""
        if not self.conflict_history:
            return {"total_conflicts": 0}
        
        levels = [c.level for c in self.conflict_history]
        
        return {
            "total_conflicts": len(self.conflict_history),
            "high_conflicts": sum(1 for l in levels if l in [ConflictLevel.HIGH, ConflictLevel.CRITICAL]),
            "avg_conflict_score": sum(c.conflict_score for c in self.conflict_history) / len(self.conflict_history),
            "primary_concern_distribution": self._count_concerns()
        }
    
    def _count_concerns(self) -> Dict[str, int]:
        """Count distribution of primary concerns."""
        concerns = {}
        for c in self.conflict_history:
            concerns[c.primary_concern] = concerns.get(c.primary_concern, 0) + 1
        return concerns

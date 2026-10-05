"""
V0.7 - Phoenix-Evo / AgentShield Integration Module

Integration interfaces for Phoenix-Evo and AgentShield signals.
Provides bidirectional synchronization between external systems.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TaskTrajectory:
    """Phoenix-Evo task trajectory data."""
    task_id: str
    steps: List[Dict]
    outcome: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class FailureAttribution:
    """Phoenix-Evo failure attribution data."""
    task_id: str
    failed_step: int
    failure_type: str
    root_cause: str
    responsible_component: str


@dataclass
class SkillReplayData:
    """Phoenix-Evo skill replay data."""
    skill_id: str
    replay_count: int
    success_rate: float
    avg_execution_time: float


@dataclass
class RiskPropagationChain:
    """AgentShield risk propagation chain."""
    chain_id: str
    steps: List[Dict]
    risk_score: float
    propagation_path: List[str]


@dataclass
class WhatIfAnalysis:
    """AgentShield what-if analysis data."""
    condition: str
    predicted_outcome: str
    risk_change: float
    confidence: float


@dataclass
class ExternalState:
    """External system state to sync from/to."""
    phoenix_state: Optional[Dict] = None
    shield_state: Optional[Dict] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class PhoenixIntegration:
    """
    Integration interface for Phoenix-Evo signals.
    
    Processes Phoenix-Evo experience signals:
    - Task trajectories
    - Failure attributions
    - Skill replay data
    
    Updates agent's affective state accordingly.
    """
    
    def __init__(self):
        self.trajectories: List[TaskTrajectory] = []
        self.attributions: List[FailureAttribution] = []
        self.replays: List[SkillReplayData] = []
    
    def process_task_trajectory(
        self,
        trajectory: TaskTrajectory
    ) -> Dict[str, float]:
        """
        Process a task trajectory from Phoenix-Evo.
        
        Args:
            trajectory: Task trajectory data
        
        Returns:
            Affective state updates
        """
        self.trajectories.append(trajectory)
        
        updates = {}
        
        if trajectory.outcome == "success":
            updates["confidence"] = 0.1
            updates["threat"] = -0.05
        elif trajectory.outcome == "failure":
            updates["confidence"] = -0.15
            updates["threat"] = 0.1
            updates["anxiety"] = 0.05
        elif trajectory.outcome == "partial":
            updates["confidence"] = 0.05
            updates["anxiety"] = 0.05
        
        return updates
    
    def process_failure_attribution(
        self,
        attribution: FailureAttribution
    ) -> Dict[str, float]:
        """
        Process failure attribution from Phoenix-Evo.
        
        Args:
            attribution: Failure attribution data
        
        Returns:
            Affective state updates
        """
        self.attributions.append(attribution)
        
        updates = {}
        
        if attribution.failure_type == "irreversible":
            updates["threat"] = 0.15
            updates["control_need"] = 0.1
        elif attribution.failure_type == "recoverable":
            updates["threat"] = 0.05
        elif attribution.failure_type == "external":
            updates["trust"] = -0.1
        
        return updates
    
    def process_skill_replay(
        self,
        replay: SkillReplayData
    ) -> Dict[str, float]:
        """
        Process skill replay data from Phoenix-Evo.
        
        Args:
            replay: Skill replay data
        
        Returns:
            Affective state updates
        """
        self.replays.append(replay)
        
        updates = {}
        
        if replay.success_rate > 0.8:
            updates["confidence"] = 0.1
            updates["curiosity"] = 0.05
        elif replay.success_rate < 0.4:
            updates["confidence"] = -0.15
            updates["frustration"] = 0.1
        
        return updates
    
    def get_learning_insights(self) -> Dict:
        """Get learning insights from Phoenix-Evo data."""
        if not self.trajectories:
            return {"message": "No trajectories available"}
        
        success_count = sum(1 for t in self.trajectories if t.outcome == "success")
        failure_count = sum(1 for t in self.trajectories if t.outcome == "failure")
        
        return {
            "total_trajectories": len(self.trajectories),
            "success_rate": success_count / len(self.trajectories),
            "failure_rate": failure_count / len(self.trajectories),
            "total_attributions": len(self.attributions),
            "total_replays": len(self.replays)
        }


class AgentShieldIntegration:
    """
    Integration interface for AgentShield signals.
    
    Processes AgentShield risk signals:
    - Risk propagation chains
    - What-if analyses
    
    Updates agent's anxiety-like state accordingly.
    """
    
    def __init__(self):
        self.risk_chains: List[RiskPropagationChain] = []
        self.whatif_analyses: List[WhatIfAnalysis] = []
    
    def process_risk_propagation(
        self,
        chain: RiskPropagationChain
    ) -> Dict[str, float]:
        """
        Process risk propagation chain from AgentShield.
        
        Args:
            chain: Risk propagation chain data
        
        Returns:
            Affective state updates
        """
        self.risk_chains.append(chain)
        
        updates = {}
        
        if chain.risk_score > 0.7:
            updates["anxiety"] = 0.15
            updates["control_need"] = 0.2
            updates["threat"] = 0.1
        elif chain.risk_score > 0.4:
            updates["anxiety"] = 0.1
            updates["control_need"] = 0.1
        else:
            updates["anxiety"] = 0.05
        
        return updates
    
    def process_whatif_analysis(
        self,
        analysis: WhatIfAnalysis
    ) -> Dict[str, float]:
        """
        Process what-if analysis from AgentShield.
        
        Args:
            analysis: What-if analysis data
        
        Returns:
            Affective state updates
        """
        self.whatif_analyses.append(analysis)
        
        updates = {}
        
        if analysis.risk_change > 0.3:
            updates["anxiety"] = 0.1
            updates["threat"] = 0.1
        elif analysis.risk_change < -0.2:
            updates["confidence"] = 0.1
        
        return updates
    
    def get_risk_insights(self) -> Dict:
        """Get risk insights from AgentShield data."""
        if not self.risk_chains:
            return {"message": "No risk chains available"}
        
        avg_risk = sum(c.risk_score for c in self.risk_chains) / len(self.risk_chains)
        
        return {
            "total_chains": len(self.risk_chains),
            "avg_risk_score": round(avg_risk, 3),
            "high_risk_chains": sum(1 for c in self.risk_chains if c.risk_score > 0.7),
            "whatif_analyses": len(self.whatif_analyses)
        }


class AffectiveStateSync:
    """
    Bidirectional synchronization between external systems and affective state.
    
    Coordinates updates between:
    - Phoenix-Evo experience signals
    - AgentShield risk signals
    - Agent's internal affective state
    """
    
    def __init__(self):
        self.phoenix = PhoenixIntegration()
        self.shield = AgentShieldIntegration()
        self.sync_history: List[Dict] = []
    
    def sync_from_external(
        self,
        external_state: ExternalState
    ) -> Dict[str, float]:
        """
        Sync affective state from external systems.
        
        Args:
            external_state: State from external systems
        
        Returns:
            Aggregated affective state updates
        """
        updates = {}
        
        if external_state.phoenix_state:
            phoenix_updates = self._process_phoenix_state(external_state.phoenix_state)
            updates.update(phoenix_updates)
        
        if external_state.shield_state:
            shield_updates = self._process_shield_state(external_state.shield_state)
            updates.update(shield_updates)
        
        self.sync_history.append({
            "timestamp": external_state.timestamp,
            "updates": updates,
            "source": "external"
        })
        
        return updates
    
    def sync_to_external(self) -> ExternalState:
        """
        Export current state to external systems.
        
        Returns:
            ExternalState with current data
        """
        return ExternalState(
            phoenix_state=self.phoenix.get_learning_insights(),
            shield_state=self.shield.get_risk_insights()
        )
    
    def _process_phoenix_state(self, state: Dict) -> Dict[str, float]:
        """Process Phoenix-Evo state."""
        updates = {}
        
        if "trajectory_outcome" in state:
            if state["trajectory_outcome"] == "success":
                updates["confidence"] = 0.1
            elif state["trajectory_outcome"] == "failure":
                updates["confidence"] = -0.15
        
        if "failure_type" in state:
            if state["failure_type"] == "irreversible":
                updates["threat"] = 0.15
        
        return updates
    
    def _process_shield_state(self, state: Dict) -> Dict[str, float]:
        """Process AgentShield state."""
        updates = {}
        
        if "risk_score" in state:
            if state["risk_score"] > 0.7:
                updates["anxiety"] = 0.15
        
        return updates
    
    def get_integration_statistics(self) -> Dict:
        """Get integration statistics."""
        return {
            "phoenix": self.phoenix.get_learning_insights(),
            "shield": self.shield.get_risk_insights(),
            "total_syncs": len(self.sync_history)
        }

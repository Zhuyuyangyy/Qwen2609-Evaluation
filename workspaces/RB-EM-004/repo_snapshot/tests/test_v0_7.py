"""Tests for V0.7 Phoenix/AgentShield Integration Modules"""

import pytest
from emotion_agent.phoenix_agent_shield import (
    PhoenixIntegration, AgentShieldIntegration, AffectiveStateSync,
    TaskTrajectory, FailureAttribution, SkillReplayData,
    RiskPropagationChain, WhatIfAnalysis, ExternalState
)


class TestPhoenixIntegration:
    """Test suite for PhoenixIntegration class."""
    
    def test_process_task_trajectory_success(self):
        """Test processing successful trajectory."""
        phoenix = PhoenixIntegration()
        trajectory = TaskTrajectory(
            task_id="task_1",
            steps=[{"action": "read"}],
            outcome="success"
        )
        
        updates = phoenix.process_task_trajectory(trajectory)
        
        assert "confidence" in updates
        assert updates["confidence"] > 0
    
    def test_process_task_trajectory_failure(self):
        """Test processing failed trajectory."""
        phoenix = PhoenixIntegration()
        trajectory = TaskTrajectory(
            task_id="task_2",
            steps=[{"action": "delete"}],
            outcome="failure"
        )
        
        updates = phoenix.process_task_trajectory(trajectory)
        
        assert "confidence" in updates
        assert updates["confidence"] < 0
    
    def test_process_failure_attribution(self):
        """Test processing failure attribution."""
        phoenix = PhoenixIntegration()
        attribution = FailureAttribution(
            task_id="task_1",
            failed_step=1,
            failure_type="irreversible",
            root_cause="user error",
            responsible_component="executor"
        )
        
        updates = phoenix.process_failure_attribution(attribution)
        
        assert "threat" in updates


class TestAgentShieldIntegration:
    """Test suite for AgentShieldIntegration class."""
    
    def test_process_risk_propagation(self):
        """Test processing risk propagation."""
        shield = AgentShieldIntegration()
        chain = RiskPropagationChain(
            chain_id="chain_1",
            steps=[{"action": "delete"}],
            risk_score=0.8,
            propagation_path=["executor"]
        )
        
        updates = shield.process_risk_propagation(chain)
        
        assert "anxiety" in updates
        assert updates["anxiety"] > 0
    
    def test_process_whatif_analysis(self):
        """Test processing what-if analysis."""
        shield = AgentShieldIntegration()
        analysis = WhatIfAnalysis(
            condition="if backup exists",
            predicted_outcome="safe",
            risk_change=-0.3,
            confidence=0.9
        )
        
        updates = shield.process_whatif_analysis(analysis)
        
        assert isinstance(updates, dict)


class TestAffectiveStateSync:
    """Test suite for AffectiveStateSync class."""
    
    def test_sync_from_external_phoenix(self):
        """Test syncing from Phoenix state."""
        sync = AffectiveStateSync()
        external = ExternalState(
            phoenix_state={"trajectory_outcome": "success"}
        )
        
        updates = sync.sync_from_external(external)
        
        assert "confidence" in updates
    
    def test_sync_from_external_shield(self):
        """Test syncing from Shield state."""
        sync = AffectiveStateSync()
        external = ExternalState(
            shield_state={"risk_score": 0.8}
        )
        
        updates = sync.sync_from_external(external)
        
        assert "anxiety" in updates
    
    def test_sync_to_external(self):
        """Test syncing to external."""
        sync = AffectiveStateSync()
        external_state = sync.sync_to_external()
        
        assert isinstance(external_state, ExternalState)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

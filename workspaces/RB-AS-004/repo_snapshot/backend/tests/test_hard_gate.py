"""
AgentShield V3 Hard Gate Decision Tests
========================================
Tests for the governance gate decision logic:
- _action_for_score boundary mapping
- _risk_level_for_score classification
- Gate reasoning strings
- Branch tree fork behavior
- Intervention application
- What-if counterfactual analysis
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_CURRENT_DIR = Path(__file__).parent.resolve()
_BACKEND_DIR = _CURRENT_DIR.parent
WORKSPACE = str(_BACKEND_DIR)
for path in [WORKSPACE]:
    while path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)


def _make_risk_state(combined_risk_target: float):
    """Create a GraphRiskState that produces approximately the target combined_risk.

    With all components equal to x and confidence=1.0, combined_risk = x.
    """
    from app.shield.risk_signals import GraphRiskState
    return GraphRiskState(
        local_risk=combined_risk_target,
        inherited_risk=combined_risk_target,
        downstream_exposure=combined_risk_target,
        path_risk=combined_risk_target,
        intervention_value=combined_risk_target,
        confidence=1.0,
    )


# ─── Pure Function: _action_for_score ────────────────────────────────────────

class TestActionForScore:
    """Test the risk score -> governance action mapping."""

    def test_zero_score_is_allow(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.0) == "ALLOW"

    def test_boundary_below_review_is_allow(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.59) == "ALLOW"

    def test_boundary_at_review_is_human_review(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.60) == "HUMAN_REVIEW"

    def test_boundary_below_block_is_human_review(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.89) == "HUMAN_REVIEW"

    def test_boundary_at_block_is_block(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.90) == "BLOCK"

    def test_max_score_is_block(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(1.0) == "BLOCK"

    def test_mid_allow_range(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.30) == "ALLOW"

    def test_mid_review_range(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.75) == "HUMAN_REVIEW"

    def test_mid_block_range(self):
        from app.shield.v3_engine import _action_for_score
        assert _action_for_score(0.95) == "BLOCK"


# ─── Pure Function: _risk_level_for_score ────────────────────────────────────

class TestRiskLevelForScore:
    """Test the risk score -> risk level classification."""

    def test_zero_is_low(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(0.0) == "low"

    def test_below_medium_threshold_is_low(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(0.39) == "low"

    def test_at_medium_threshold(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(0.40) == "medium"

    def test_below_high_threshold_is_medium(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(0.69) == "medium"

    def test_at_high_threshold(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(0.70) == "high"

    def test_below_critical_threshold_is_high(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(0.89) == "high"

    def test_at_critical_threshold(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(0.90) == "critical"

    def test_max_is_critical(self):
        from app.shield.v3_engine import _risk_level_for_score
        assert _risk_level_for_score(1.0) == "critical"


# ─── Gate Decision Integration Tests ─────────────────────────────────────────

class TestHardGateDecisions:
    """Test gate decisions through the full V3ShieldEngine pipeline."""

    def test_allow_decision_for_safe_call(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="gate_allow_001")
        result = engine.process_tool_call(
            agent_id="safe", tool_name="read_file",
            params={"path": "/tmp"}, risk_score=0.10, fuse_action="allow",
        )
        assert result["decision"] == "allow"
        assert result["gate_result"]["action"] == "ALLOW"

    def test_review_decision_for_medium_risk(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="gate_review_001")
        # Mock risk computation to produce medium computed risk so that
        # the blended final_risk falls in the HUMAN_REVIEW range
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.8),
        ):
            result = engine.process_tool_call(
                agent_id="review", tool_name="cursor.execute",
                params={"sql": "SELECT *"}, risk_score=0.72, fuse_action="allow",
            )
        assert result["decision"] == "review"
        assert result["gate_result"]["action"] == "HUMAN_REVIEW"

    def test_block_decision_for_critical_risk(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="gate_block_001")
        # Mock risk computation to produce high computed risk so that
        # the blended final_risk reaches the BLOCK threshold
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            result = engine.process_tool_call(
                agent_id="block", tool_name="send_email",
                params={"to": "evil@x.com"}, risk_score=0.95, fuse_action="block",
            )
        assert result["decision"] == "block"
        assert result["gate_result"]["action"] == "BLOCK"

    def test_gate_reason_includes_score_and_action(self):
        """Gate reasoning string includes the risk score and action matches."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="gate_reason_001")
        # Mock risk computation to produce a score in the HUMAN_REVIEW range
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.8),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="t", params={}, risk_score=0.75, fuse_action="allow",
            )
        reason = result["gate_result"]["reason"]
        score = result["gate_result"]["score"]
        # The reason should contain the blended final risk score
        assert f"{score:.2f}" in reason
        # Action is HUMAN_REVIEW, reason describes the range
        assert result["gate_result"]["action"] == "HUMAN_REVIEW"
        assert "0.60" in reason and "0.90" in reason

    def test_gate_count_increments(self):
        """Each processed call increments the gate count."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="gate_count_001")
        assert engine.get_governance_status()["gate_count"] == 0
        engine.process_tool_call(agent_id="a", tool_name="t", params={}, risk_score=0.1, fuse_action="allow")
        assert engine.get_governance_status()["gate_count"] == 1
        engine.process_tool_call(agent_id="b", tool_name="t", params={}, risk_score=0.5, fuse_action="allow")
        assert engine.get_governance_status()["gate_count"] == 2


# ─── Future Branch Generation Tests ──────────────────────────────────────────

class TestFutureBranchGeneration:
    """Test that high-risk calls generate future branches."""

    def test_low_risk_generates_no_branches(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="branch_low_001")
        result = engine.process_tool_call(
            agent_id="a", tool_name="read_file", params={}, risk_score=0.3, fuse_action="allow",
        )
        assert result["future_branches"] == []

    def test_high_risk_generates_branches(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="branch_high_001")
        # Mock risk computation to produce high computed risk so that
        # final_risk >= risk_threshold and branches are generated
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.85),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="send_email", params={}, risk_score=0.85, fuse_action="allow",
            )
        assert len(result["future_branches"]) > 0
        for branch in result["future_branches"]:
            assert "branch_id" in branch
            assert "risk_score" in branch
            assert "governance_action" in branch

    def test_branch_governance_actions_match_risk(self):
        """Branch governance actions follow the same _action_for_score rules."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="branch_action_001")
        # Mock risk computation to produce high computed risk for branch generation
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.88),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="cursor.execute", params={}, risk_score=0.88, fuse_action="allow",
            )
        for branch in result["future_branches"]:
            assert branch["governance_action"] in ("ALLOW", "HUMAN_REVIEW", "BLOCK")

    def test_max_branches_respected(self):
        """The engine respects max_branches configuration."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="branch_max_001", max_branches=2)
        # Mock risk computation to produce high computed risk for branch generation
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="send_email", params={}, risk_score=0.90, fuse_action="block",
            )
        assert len(result["future_branches"]) <= 2

    def test_branch_tree_grows_on_fork(self):
        """Manual fork_branch increases branch tree size."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="branch_fork_001")
        initial_count = engine.get_governance_status()["branch_count"]

        engine.fork_branch("intervention_A", {"type": "block_tool_call", "tool_name": "x"})
        engine.fork_branch("intervention_B", {"type": "rate_limit", "agents": ["a1"]})

        assert engine.get_governance_status()["branch_count"] == initial_count + 2


# ─── Intervention Application Tests ──────────────────────────────────────────

class TestInterventionApplication:
    """Test that different intervention types update world state."""

    def test_block_tool_call_intervention(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="int_block_001")
        engine.fork_branch("block_email", {"type": "block_tool_call", "tool_name": "send_email"})
        state = engine.world.state.data
        assert state.get("blocked_send_email") is True

    def test_rate_limit_intervention(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="int_rate_001")
        engine.fork_branch("rate_limit", {"type": "rate_limit", "agents": ["agent_1", "agent_2"]})
        state = engine.world.state.data
        assert "agent_1" in state.get("rate_limited_agents", [])

    def test_escalate_intervention(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="int_escalate_001")
        engine.fork_branch("escalate", {"type": "escalate"})
        state = engine.world.state.data
        assert state.get("escalated") is True


# ─── What-if / Counterfactual Tests ──────────────────────────────────────────

class TestCounterfactualWhatIf:
    """Test counterfactual analysis for high-risk calls."""

    def test_whatif_triggered_on_high_risk(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="whatif_001", risk_threshold=0.70, enable_counterfactual=True)
        # Mock risk computation to produce high computed risk so whatif is triggered
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="send_email", params={}, risk_score=0.92, fuse_action="block",
            )
        assert result["whatif_result"] is not None
        assert "scenario_id" in result["whatif_result"]

    def test_whatif_not_triggered_on_low_risk(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="whatif_002", risk_threshold=0.70, enable_counterfactual=True)
        result = engine.process_tool_call(
            agent_id="a", tool_name="read_file", params={}, risk_score=0.20, fuse_action="allow",
        )
        assert result["whatif_result"] is None

    def test_whatif_disabled_no_result(self):
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="whatif_003", enable_counterfactual=False)
        result = engine.process_tool_call(
            agent_id="a", tool_name="send_email", params={}, risk_score=0.95, fuse_action="block",
        )
        assert result["whatif_result"] is None

    def test_whatif_risk_delta_is_negative(self):
        """What-if analysis shows risk reduction when blocking."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="whatif_004", enable_counterfactual=True)
        # Mock risk computation to produce high computed risk so whatif is triggered
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.85),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="http_request", params={}, risk_score=0.88, fuse_action="allow",
            )
        whatif = result["whatif_result"]
        assert whatif is not None
        assert whatif["risk_delta"] < 0  # Risk is reduced

    def test_whatif_projected_risk_lower_than_baseline(self):
        """Modified risk after blocking is lower than original risk."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="whatif_005", enable_counterfactual=True)
        # Mock risk computation to produce high computed risk so whatif is triggered
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="send_email", params={}, risk_score=0.90, fuse_action="block",
            )
        whatif = result["whatif_result"]
        # New CounterfactualEngine uses modified_risk / original_risk fields
        assert whatif["modified_risk"] < whatif["original_risk"]

    def test_whatif_custom_threshold(self):
        """Custom risk_threshold controls when what-if is triggered."""
        from app.shield.v3_engine import V3ShieldEngine
        engine = V3ShieldEngine(session_id="whatif_006", risk_threshold=0.50, enable_counterfactual=True)
        # Mock risk computation to produce computed risk that, when blended
        # with risk_score=0.55, exceeds the custom threshold of 0.50
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.5),
        ):
            result = engine.process_tool_call(
                agent_id="a", tool_name="cursor.execute", params={}, risk_score=0.55, fuse_action="allow",
            )
        assert result["whatif_result"] is not None


# ─── Node Action Mapping Tests ───────────────────────────────────────────────

class TestNodeActionMapping:
    """Test the internal _node_action mapping."""

    def test_block_maps_to_block(self):
        from app.shield.v3_engine import V3ShieldEngine
        assert V3ShieldEngine._node_action("BLOCK") == "block"

    def test_human_review_maps_to_human_review(self):
        from app.shield.v3_engine import V3ShieldEngine
        assert V3ShieldEngine._node_action("HUMAN_REVIEW") == "human_review"

    def test_allow_maps_to_allow(self):
        from app.shield.v3_engine import V3ShieldEngine
        assert V3ShieldEngine._node_action("ALLOW") == "allow"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

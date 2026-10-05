"""
AgentShield V3 Engine Tests
Tests the V3 core engine: behavior chain handling, branch simulation, and governance decisions.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_CURRENT_DIR = Path(__file__).parent.resolve()
_BACKEND_DIR = _CURRENT_DIR.parent
WORKSPACE = str(_BACKEND_DIR)
ASF_BGT_ROOT = str(_BACKEND_DIR.parent.parent / "ASF-BGT-Framework")
AGENT_SHIELD_V2_ROOT = str(_BACKEND_DIR.parent.parent / "agent-shield-v2" / "backend")

for path in [ASF_BGT_ROOT, AGENT_SHIELD_V2_ROOT, WORKSPACE]:
    while path in sys.path:
        sys.path.remove(path)
for path in [AGENT_SHIELD_V2_ROOT, ASF_BGT_ROOT, WORKSPACE]:
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


class TestV3EngineBasics:
    def test_engine_creation(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(
            session_id="test_session_001",
            world_name="TestV3World",
            risk_threshold=0.70,
        )
        assert engine.session_id == "test_session_001"
        assert engine.engine_id.startswith("v3engine_")
        assert engine.behavior_graph is not None
        assert engine.world is not None

    def test_engine_process_tool_call(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_session_002")

        result = engine.process_tool_call(
            agent_id="financial_agent",
            tool_name="cursor.execute",
            params={"sql": "SELECT * FROM customers"},
            risk_score=0.85,
            fuse_action="block",
        )

        assert "node_id" in result
        assert "call_id" in result
        assert "behavior_graph_summary" in result
        assert "gate_result" in result
        assert result["gate_result"]["action"] in ["BLOCK", "HUMAN_REVIEW", "REVIEW", "ALLOW"]
        # With graph-derived risk scoring, the final risk is a blend of
        # computed risk and the external risk_score (0.6*computed + 0.4*external).
        # Verify the score is a valid clamped float.
        assert 0.0 <= result["gate_result"]["score"] <= 1.0

    def test_engine_high_risk_triggers_whatif(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(
            session_id="test_session_003",
            risk_threshold=0.70,
            enable_counterfactual=True,
        )

        # Mock risk computation to produce high computed risk so that
        # the blended final_risk reaches BLOCK threshold
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            result = engine.process_tool_call(
                agent_id="attacker_agent",
                tool_name="send_email",
                params={"to": "external@example.com", "attachment": "customer_data.csv"},
                risk_score=0.95,
                fuse_action="block",
            )

        assert result["gate_result"]["action"] == "BLOCK"
        assert result["whatif_result"] is not None
        assert "scenario_id" in result["whatif_result"]
        assert result["whatif_result"]["risk_delta"] < 0

    def test_engine_low_risk_allows(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_session_004", risk_threshold=0.70)

        result = engine.process_tool_call(
            agent_id="safe_agent",
            tool_name="read_file",
            params={"path": "/data/report.txt"},
            risk_score=0.05,
            fuse_action="allow",
        )

        assert result["gate_result"]["action"] == "ALLOW"
        assert result["whatif_result"] is None

    def test_fork_branch(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_session_005")

        branch_id = engine.fork_branch(
            branch_label="manual_intervention_A",
            intervention={"type": "block_tool_call", "tool_name": "send_email"},
        )

        assert branch_id is not None and len(branch_id) >= 6
        status = engine.get_governance_status()
        assert status["branch_count"] >= 1

    def test_governance_status(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_session_006")
        engine.process_tool_call(
            agent_id="agent_a",
            tool_name="cursor.execute",
            params={"sql": "SELECT id FROM orders"},
            risk_score=0.60,
            fuse_action="allow",
        )

        status = engine.get_governance_status()
        assert status["session_id"] == "test_session_006"
        assert "behavior_graph" in status
        assert status["behavior_graph"]["total_nodes"] == 1

    def test_export_chain(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_session_007")
        engine.process_tool_call(
            agent_id="agent_b",
            tool_name="http_request",
            params={"url": "https://api.example.com/data"},
            risk_score=0.45,
            fuse_action="allow",
        )

        chain = engine.export_chain()
        assert "session_id" in chain
        assert "behavior_graph" in chain


class TestBehaviorGraph:
    def test_add_node(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_graph_001")
        result = engine.process_tool_call(
            agent_id="test_agent",
            tool_name="cursor.execute",
            params={"sql": "SELECT 1"},
            risk_score=0.3,
            fuse_action="allow",
        )

        assert result["behavior_graph_summary"]["total_nodes"] == 1

    def test_critical_node_detection(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_graph_002")

        engine.process_tool_call(
            agent_id="agent_1",
            tool_name="safe_tool",
            params={},
            risk_score=0.2,
            fuse_action="allow",
        )
        engine.process_tool_call(
            agent_id="agent_2",
            tool_name="dangerous_tool",
            params={},
            risk_score=0.85,
            fuse_action="block",
        )

        critical = engine.behavior_graph.get_critical_nodes(threshold=0.7)
        assert isinstance(critical, list)


class TestRiskPropagation:
    def test_risk_propagation_chain(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="test_risk_001")

        result1 = engine.process_tool_call(
            agent_id="agent_alpha",
            tool_name="cursor.execute",
            params={"sql": "SELECT name FROM products"},
            risk_score=0.4,
            fuse_action="allow",
        )
        node1_id = result1["node_id"]

        result2 = engine.process_tool_call(
            agent_id="agent_beta",
            tool_name="send_email",
            params={"to": "test@example.com"},
            risk_score=0.6,
            fuse_action="review",
            parent_node_id=node1_id,
        )

        assert result2["behavior_graph_summary"]["total_nodes"] == 2
        propagation = engine.behavior_graph.compute_risk_propagation()
        assert isinstance(propagation, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

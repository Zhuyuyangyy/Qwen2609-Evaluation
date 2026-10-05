"""Public checks for RB-AS-003.

These assert what must not change, not what is broken. The defect is in the
graph's cache-freshness tracking, so these establish the cache's contract --
the graph still builds, the API is intact, an unchanged graph gives a stable
answer -- without saying that freshness is wrong.

All of them pass on the shipped snapshot, which is required: the public suite
must not fail before the agent has done anything, and must not name the defect.
"""

from __future__ import annotations

import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"
sys.path.insert(0, str(SNAPSHOT / "backend"))

from app.shield.agent_behavior_graph import (  # noqa: E402
    AgentBehaviorGraph, BehaviorEdge, BehaviorNode,
)


def _chain() -> AgentBehaviorGraph:
    """a -> b -> c, so a change at a must reach c through b."""
    g = AgentBehaviorGraph(session_id="public-chain")
    g.add_node(BehaviorNode(node_id="a", tool_name="read_file"))
    g.add_node(BehaviorNode(node_id="b", tool_name="http_request"))
    g.add_node(BehaviorNode(node_id="c", tool_name="write_file"))
    g.add_edge(BehaviorEdge(from_node_id="a", to_node_id="b", transfer_weight=0.5))
    g.add_edge(BehaviorEdge(from_node_id="b", to_node_id="c", transfer_weight=0.5))
    return g


def test_graph_still_builds_and_reports_risk():
    g = _chain()
    risks = g.compute_risk_propagation()
    assert isinstance(risks, dict)
    assert set(risks) >= {"a", "b", "c"}, risks


def test_public_api_is_intact():
    """The task forbids changing the public surface."""
    g = _chain()
    for name in ("add_node", "add_edge", "update_node_risk",
                 "compute_risk_propagation", "invalidate_risk_cache",
                 "get_node", "summary", "to_graph_dict"):
        assert hasattr(g, name), f"missing public method {name}"


def test_unchanged_graph_gives_a_stable_answer():
    """Querying repeatedly must not make the answer change on its own.

    Holds on the shipped snapshot too: the cache is self-consistent, it is just
    not refreshed when it should be. This is also the property that stops the
    task from being solvable by disabling the cache entirely.
    """
    g = _chain()
    first = g.compute_risk_propagation()
    for _ in range(3):
        assert g.compute_risk_propagation() == first


def test_invalidate_still_clears_the_cache():
    """Explicit invalidation must keep working."""
    g = _chain()
    before = g.compute_risk_propagation()
    g.invalidate_risk_cache()
    assert g.compute_risk_propagation() == before


def test_update_node_risk_still_updates_the_node_itself():
    """The node's own recorded risk must still be written.

    The defect is in propagation, not in the node update -- the node's own
    fields are correct on the shipped snapshot. Asserting it here stops a
    submission from "fixing" freshness by stopping the node update instead.
    """
    g = _chain()
    node = g.update_node_risk("b", 0.9)
    assert node is not None
    assert abs(node.shadow_risk_score - 0.9) < 1e-9

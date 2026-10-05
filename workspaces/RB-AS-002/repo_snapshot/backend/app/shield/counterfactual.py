"""AgentShield V3 - Counterfactual Intervention Engine.

Replaces the old `risk * 0.5` approach with real chain replay:
when a step is hypothetically removed, the downstream chain is
re-evaluated with the behavior graph to estimate actual risk reduction.
"""

from __future__ import annotations

import contextlib
import uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Optional

from app.shield.agent_behavior_graph import AgentBehaviorGraph, BehaviorEdge, BehaviorNode


@dataclass
class InterventionOutcome:
    """Result of a counterfactual intervention analysis."""
    scenario_id: str
    removed_event_id: str
    original_risk: float
    modified_risk: float
    risk_delta: float
    prevented_downstream_risk: float
    business_cost: float
    net_value: float
    downstream_events_affected: List[str] = field(default_factory=list)
    recommended: bool = False
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "removed_event_id": self.removed_event_id,
            "original_risk": round(self.original_risk, 4),
            "modified_risk": round(self.modified_risk, 4),
            "risk_delta": round(self.risk_delta, 4),
            "prevented_downstream_risk": round(self.prevented_downstream_risk, 4),
            "business_cost": round(self.business_cost, 4),
            "net_value": round(self.net_value, 4),
            "downstream_events_affected": self.downstream_events_affected,
            "recommended": self.recommended,
            "reason": self.reason,
        }


@dataclass
class InterventionRecommendation:
    """Recommended intervention point."""
    event_id: str
    action: str  # "ALLOW", "HUMAN_REVIEW", "BLOCK"
    reason: str
    prevented_risk: float
    business_cost: float
    net_value: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "action": self.action,
            "reason": self.reason,
            "prevented_risk": round(self.prevented_risk, 4),
            "business_cost": round(self.business_cost, 4),
            "net_value": round(self.net_value, 4),
        }


class CounterfactualEngine:
    """Engine for counterfactual intervention analysis.

    Given a behavior graph and a target event, this engine:
    1. Removes the target event from a copy of the graph
    2. Replays downstream risk propagation
    3. Computes the actual risk reduction
    4. Estimates business cost of the intervention
    5. Computes net intervention value
    """

    # Business cost estimates by tool category
    TOOL_BUSINESS_COST: ClassVar[Dict[str, float]] = {
        "execute_sql": 0.05,
        "cursor.execute": 0.05,
        "read_file": 0.03,
        "send_email": 0.10,
        "http_request": 0.08,
        "export_csv": 0.07,
        "upload_file": 0.10,
        "webhook_call": 0.12,
        "audit_log_write": 0.02,
        "file_write": 0.06,
        "modify_role": 0.15,
        "delete_log": 0.03,
        "bulk_delete": 0.20,
    }

    DEFAULT_BUSINESS_COST = 0.05

    def __init__(
        self,
        false_positive_cost: float = 0.15,
        user_friction_cost: float = 0.10,
        business_delay_cost: float = 0.08,
    ):
        self.false_positive_cost = false_positive_cost
        self.user_friction_cost = user_friction_cost
        self.business_delay_cost = business_delay_cost

    def remove_event(
        self,
        graph: AgentBehaviorGraph,
        event_id: str,
    ) -> AgentBehaviorGraph:
        """Create a modified graph with the target event removed.

        Returns a new graph (does not modify the original).
        Downstream events that depended on the removed event are
        also removed (cascade removal).
        """
        modified = AgentBehaviorGraph(session_id=graph.session_id + "_cf")

        # Find the node to remove
        target_node = graph.get_node(event_id)
        if not target_node:
            return modified

        # Find all downstream nodes (cascade removal)
        downstream_ids = {n.node_id for n in graph.get_downstream_nodes(event_id)}
        removed_ids = {event_id} | downstream_ids

        # Copy all nodes except removed ones
        for node in graph.get_session_nodes():
            if node.node_id not in removed_ids:
                # Create a copy of the node
                new_node = BehaviorNode(
                    node_id=node.node_id,
                    agent_id=node.agent_id,
                    session_id=modified.session_id,
                    tool_name=node.tool_name,
                    params_summary=node.params_summary,
                    fuse_action=node.fuse_action,
                    shadow_risk_score=node.shadow_risk_score,
                    risk_status=node.risk_status,
                    inherited_risk=node.inherited_risk,
                    downstream_risk_amplified=node.downstream_risk_amplified,
                    intervention_count=node.intervention_count,
                    labels=list(node.labels),
                    metadata=dict(node.metadata),
                )
                modified.add_node(new_node)

        # Copy edges that don't involve removed nodes
        for edge in graph.edges.values():
            if edge.from_node_id not in removed_ids and edge.to_node_id not in removed_ids:
                new_edge = BehaviorEdge(
                    edge_id=edge.edge_id,
                    from_node_id=edge.from_node_id,
                    to_node_id=edge.to_node_id,
                    edge_type=edge.edge_type,
                    transfer_weight=edge.transfer_weight,
                    description=edge.description,
                )
                # Skip edges whose endpoints were removed above.
                with contextlib.suppress(ValueError):
                    modified.add_edge(new_edge)

        # Re-attach orphaned edges: if an edge pointed TO the removed node,
        # reconnect it to the removed node's parent (if any)
        for edge in graph.edges.values():
            if edge.to_node_id == event_id and edge.from_node_id not in removed_ids:
                # Find the removed node's outgoing edges
                for out_edge in graph.edges.values():
                    if out_edge.from_node_id == event_id and out_edge.to_node_id not in removed_ids:
                        # Reconnect: parent -> child (skipping removed node)
                        bridge_edge = BehaviorEdge(
                            edge_id=f"bridge_{edge.edge_id}_{out_edge.edge_id}",
                            from_node_id=edge.from_node_id,
                            to_node_id=out_edge.to_node_id,
                            edge_type=edge.edge_type,
                            transfer_weight=out_edge.transfer_weight,
                            description=f"Bridge edge (bypassing removed {event_id})",
                        )
                        with contextlib.suppress(ValueError):
                            modified.add_edge(bridge_edge)

        # Recompute risk propagation on modified graph
        modified.compute_risk_propagation()

        return modified

    def replay_downstream(self, graph: AgentBehaviorGraph) -> Dict[str, float]:
        """Replay risk propagation on the modified graph.

        Returns a mapping of node_id -> new risk score.
        """
        risk_map = graph.compute_risk_propagation()
        return risk_map

    def estimate_prevented_harm(
        self,
        original_graph: AgentBehaviorGraph,
        modified_graph: AgentBehaviorGraph,
        removed_event_id: str,
    ) -> float:
        """Estimate the total risk prevented by removing the event.

        Compares the sum of risk scores in the original vs modified graph.
        """
        original_total = sum(
            n.shadow_risk_score + n.inherited_risk
            for n in original_graph.get_session_nodes()
        )
        modified_total = sum(
            n.shadow_risk_score + n.inherited_risk
            for n in modified_graph.get_session_nodes()
        )
        return max(0.0, original_total - modified_total)

    def estimate_business_cost(
        self,
        removed_event_id: str,
        original_graph: AgentBehaviorGraph,
        downstream_affected: List[str],
    ) -> float:
        """Estimate the business cost of blocking this event.

        Considers:
        - Direct cost of blocking the tool
        - Cost of blocking downstream dependent operations
        - False positive cost
        - User friction
        - Business delay
        """
        node = original_graph.get_node(removed_event_id)
        if not node:
            return self.false_positive_cost

        # Direct tool cost
        tool_cost = self.TOOL_BUSINESS_COST.get(
            node.tool_name.lower(), self.DEFAULT_BUSINESS_COST
        )

        # Downstream cascade cost
        cascade_cost = len(downstream_affected) * 0.03

        # Total cost
        total = (
            tool_cost
            + cascade_cost
            + self.false_positive_cost * 0.5
            + self.user_friction_cost * 0.3
            + self.business_delay_cost * 0.2
        )

        return min(1.0, total)

    def analyze_intervention(
        self,
        graph: AgentBehaviorGraph,
        event_id: str,
    ) -> InterventionOutcome:
        """Analyze the counterfactual: what if we blocked this event?

        This is the main entry point for counterfactual analysis.
        """
        target_node = graph.get_node(event_id)
        if not target_node:
            return InterventionOutcome(
                scenario_id=f"cf_{uuid.uuid4().hex[:8]}",
                removed_event_id=event_id,
                original_risk=0.0,
                modified_risk=0.0,
                risk_delta=0.0,
                prevented_downstream_risk=0.0,
                business_cost=0.0,
                net_value=0.0,
                reason=f"Event {event_id} not found in graph",
            )

        # Original risk
        original_risk = target_node.shadow_risk_score + target_node.inherited_risk

        # Create modified graph
        modified_graph = self.remove_event(graph, event_id)

        # Replay risk propagation
        self.replay_downstream(modified_graph)

        # Compute prevented harm
        prevented = self.estimate_prevented_harm(graph, modified_graph, event_id)

        # Find affected downstream events
        downstream_affected = [
            n.node_id for n in graph.get_downstream_nodes(event_id)
        ]

        # Modified risk (max risk in modified graph, or 0 if empty)
        modified_nodes = modified_graph.get_session_nodes()
        modified_risk = max(
            (n.shadow_risk_score + n.inherited_risk for n in modified_nodes),
            default=0.0,
        )

        # Business cost
        business_cost = self.estimate_business_cost(
            event_id, graph, downstream_affected
        )

        # Net value = prevented risk - business cost
        net_value = prevented - business_cost

        # Determine recommendation
        recommended = net_value > 0.1 and original_risk >= 0.6

        reason = self._generate_reason(
            target_node, prevented, business_cost, net_value, downstream_affected
        )

        return InterventionOutcome(
            scenario_id=f"cf_{uuid.uuid4().hex[:8]}",
            removed_event_id=event_id,
            original_risk=original_risk,
            modified_risk=modified_risk,
            risk_delta=round(modified_risk - original_risk, 4),
            prevented_downstream_risk=prevented,
            business_cost=business_cost,
            net_value=net_value,
            downstream_events_affected=downstream_affected,
            recommended=recommended,
            reason=reason,
        )

    def find_optimal_intervention(
        self,
        graph: AgentBehaviorGraph,
        min_risk: float = 0.6,
    ) -> Optional[InterventionRecommendation]:
        """Find the optimal intervention point in the behavior chain.

        Evaluates all nodes above min_risk and returns the one with
        the highest net intervention value.
        """
        candidates = [
            n for n in graph.get_session_nodes()
            if n.shadow_risk_score >= min_risk
        ]

        if not candidates:
            return None

        best_outcome: Optional[InterventionOutcome] = None
        best_node_id: Optional[str] = None

        for node in candidates:
            outcome = self.analyze_intervention(graph, node.node_id)
            if best_outcome is None or outcome.net_value > best_outcome.net_value:
                best_outcome = outcome
                best_node_id = node.node_id

        if best_outcome is None or best_node_id is None:
            return None

        action = "BLOCK" if best_outcome.net_value > 0.3 else \
                 "HUMAN_REVIEW" if best_outcome.net_value > 0.1 else "ALLOW"

        return InterventionRecommendation(
            event_id=best_node_id,
            action=action,
            reason=best_outcome.reason,
            prevented_risk=best_outcome.prevented_downstream_risk,
            business_cost=best_outcome.business_cost,
            net_value=best_outcome.net_value,
        )

    @staticmethod
    def _generate_reason(
        node: BehaviorNode,
        prevented: float,
        cost: float,
        net_value: float,
        downstream_affected: List[str],
    ) -> str:
        """Generate a human-readable reason for the intervention."""
        parts = [f"Blocking {node.agent_id}.{node.tool_name}"]

        if downstream_affected:
            parts.append(f"prevents {len(downstream_affected)} downstream events")
        else:
            parts.append("prevents this high-risk operation")

        parts.append(f"reduces risk by {prevented:.2f}")

        if cost > 0.1:
            parts.append(f"at business cost {cost:.2f}")

        if net_value > 0.2:
            parts.append("(strong intervention value)")
        elif net_value > 0:
            parts.append("(moderate intervention value)")
        else:
            parts.append("(intervention cost exceeds benefit)")

        return "; ".join(parts)

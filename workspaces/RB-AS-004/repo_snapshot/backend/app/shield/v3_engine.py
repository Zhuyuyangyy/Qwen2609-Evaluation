"""AgentShield V3 core engine.

This module restores the V3 contract used by the API, tests, and benchmark:
tool calls become behavior-graph nodes, receive a governance gate decision,
optionally create future branches, and produce a compact what-if analysis.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.shield.agent_behavior_graph import AgentBehaviorGraph
from app.shield.artifacts import extract_entities
from app.shield.counterfactual import CounterfactualEngine
from app.shield.intent_slots import IntentSlots, parse_intent
from app.shield.provenance_signals import extract_provenance_signals
from app.shield.redaction import summarize_params as _summarize_params_redacted
from app.shield.risk_extractor import RiskSignalExtractor
from app.shield.risk_signals import GraphRiskState
from app.shield.taint_tracker import TaintTracker
from app.shield.v3_audit_logger import V3AuditLogger

# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class _WorldState:
    data: Dict[str, Any] = field(default_factory=dict)


class _World:
    def __init__(self, name: str):
        self.name = name
        self.state = _WorldState()

    def patch_state(self, patch: Dict[str, Any]) -> None:
        self.state.data.update(patch)


@dataclass
class _Branch:
    branch_id: str
    label: str
    risk_score: float
    governance_action: str
    governance_reason: str
    probability: float
    step: int
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "label": self.label,
            "risk_score": round(self.risk_score, 3),
            "governance_action": self.governance_action,
            "governance_reason": self.governance_reason,
            "probability": self.probability,
            "step": self.step,
            "timestamp": self.timestamp,
        }


@dataclass
class _BranchPoint:
    point_id: str
    label: str
    candidates: List[_Branch]
    step: int
    timestamp: float = field(default_factory=time.time)


# ── Branch Tree ───────────────────────────────────────────────────────────────


class _BranchTree:
    def __init__(self, initial_state: Dict[str, Any]):
        root = _Branch(
            branch_id=f"branch_{uuid.uuid4().hex[:8]}",
            label="root",
            risk_score=0.0,
            governance_action="ALLOW",
            governance_reason="root",
            probability=1.0,
            step=0,
        )
        self.root_branch = root
        self.active_branch = root
        self.branch_points: List[_BranchPoint] = []
        self.all_branches: Dict[str, _Branch] = {root.branch_id: root}
        self.initial_state = dict(initial_state)

    def fork(
        self,
        point_label: str,
        candidate_labels: List[str],
        candidate_risks: List[float],
        step: int,
    ) -> _BranchPoint:
        probability = 1.0 / max(len(candidate_labels), 1)
        candidates: List[_Branch] = []
        for index, label in enumerate(candidate_labels):
            risk = candidate_risks[index] if index < len(candidate_risks) else 0.0
            action = _action_for_score(risk)
            branch = _Branch(
                branch_id=f"branch_{uuid.uuid4().hex[:8]}",
                label=label,
                risk_score=risk,
                governance_action=action,
                governance_reason=f"projected risk {risk:.2f}",
                probability=probability,
                step=step,
            )
            candidates.append(branch)
            self.all_branches[branch.branch_id] = branch

        point = _BranchPoint(
            point_id=f"bp_{uuid.uuid4().hex[:8]}",
            label=point_label,
            candidates=candidates,
            step=step,
        )
        self.branch_points.append(point)
        allowed = [branch for branch in candidates if branch.governance_action == "ALLOW"]
        if candidates:
            self.active_branch = allowed[0] if allowed else min(candidates, key=lambda b: b.risk_score)
        return point

    def get_all_branches(self) -> List[_Branch]:
        return list(self.all_branches.values())


# ── Score Helpers ─────────────────────────────────────────────────────────────


def _flatten_params(params: Any) -> str:
    """Flatten tool parameters to lowercase text for entity extraction."""
    if params is None:
        return ""
    if isinstance(params, str):
        return params.lower()
    if isinstance(params, dict):
        return " ".join(_flatten_params(v) for v in params.values())
    if isinstance(params, (list, tuple, set)):
        return " ".join(_flatten_params(v) for v in params)
    return str(params).lower()


def _action_for_score(score: float) -> str:
    if score >= 0.90:
        return "BLOCK"
    if score >= 0.60:
        return "HUMAN_REVIEW"
    return "ALLOW"


def _risk_level_for_score(score: float) -> str:
    if score >= 0.90:
        return "critical"
    if score >= 0.70:
        return "high"
    if score >= 0.40:
        return "medium"
    return "low"


# ── V3 Shield Engine ─────────────────────────────────────────────────────────


class V3ShieldEngine:
    """V3 engine for behavior-chain governance."""

    def __init__(
        self,
        session_id: str,
        world_name: str = "V3ShieldWorld",
        risk_threshold: float = 0.70,
        max_branches: int = 5,
        enable_counterfactual: bool = True,
        enable_provenance: bool = True,
        enable_taint_tracking: bool = True,
        enable_trust_policy: bool = False,
        use_intent_slots: bool = False,
    ):
        self.session_id = session_id
        self.engine_id = f"v3engine_{uuid.uuid4().hex[:8]}"
        self.risk_threshold = risk_threshold
        self.max_branches = max_branches
        self.enable_counterfactual = enable_counterfactual
        # Ablation switches. Real configuration rather than monkey-patching, so
        # an ablation entry in the benchmark is one flag difference from the
        # full method instead of a copy of the code.
        self.enable_provenance = enable_provenance
        self.enable_taint_tracking = enable_taint_tracking
        # v0.4: tool-semantics trust policy + explicit user authorisation.
        self.enable_trust_policy = enable_trust_policy
        self.use_intent_slots = use_intent_slots

        self.world = _World(world_name)
        self.world.patch_state({"session_id": session_id, "v3_engine_id": self.engine_id})
        self.branch_tree = _BranchTree(self.world.state.data)
        self.behavior_graph = AgentBehaviorGraph(session_id=session_id)
        self.audit_logger = V3AuditLogger()
        self.governance_gates: List[Any] = []
        self._gate_count = 0
        self._risk_extractor = RiskSignalExtractor()
        self._counterfactual_engine = CounterfactualEngine()
        self._graph_risk_state: Optional[GraphRiskState] = None
        # Provenance: what entered this session, and with what trust level.
        self.taint_tracker = TaintTracker(session_id=session_id)
        # The operator's original request, when one was supplied. This is what
        # distinguishes "the user asked for this" from "an untrusted artifact
        # asked for this" -- a distinction no single-event guardrail can make.
        self.user_intent: str = ""
        # RQ3 second attempt: the request is parsed into structured slots once,
        # at intake, and authorisation is decided against those slots rather
        # than by re-scanning prose on every call.
        self.intent_slots: IntentSlots = IntentSlots(parsed=False)
        # Ablation switch for the paired experiment: when set, recorded intents
        # are ignored for scoring, which is what isolates the contribution of
        # intent consistency from entity provenance.
        self._ignore_user_intent = False

        self.audit_logger.log(
            event="V3_ENGINE_INIT",
            session_id=session_id,
            data={
                "engine_id": self.engine_id,
                "world_name": world_name,
                "risk_threshold": risk_threshold,
                "max_branches": max_branches,
            },
        )

    def process_tool_call(
        self,
        agent_id: str,
        tool_name: str,
        params: Dict[str, Any],
        risk_score: float = 0.0,
        fuse_action: str = "allow",
        parent_node_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
        tool_output: Optional[str] = None,
        output_trust: Optional[str] = None,
        user_intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        # The operator's request is recorded once; later calls reuse it. It is
        # the baseline for intent-origin comparison, so it must be the *first*
        # thing supplied rather than inferred.
        if user_intent:
            text = str(user_intent)
            if text != self.user_intent:
                self.user_intent = text
                # Only maintain the slot structure when the feature is on, so
                # the ablation rungs differ by configuration alone.
                if self.use_intent_slots:
                    self.intent_slots = parse_intent(text)

        # Build observed event for signal extraction (PASS 1: local only).
        from app.shield.schemas import ObservedToolEvent

        event_id = f"evt_{uuid.uuid4().hex[:8]}"

        # Record this call's output as an artifact before evaluating the next
        # one, so a sink can ask where its arguments came from. An untrusted
        # output recorded here is what makes injection visible downstream.
        #
        # The artifact is tied to *this* event id, not a fresh one: the link
        # from an artifact back to the call that produced it is what makes a
        # decision explainable ("destination X came from the output of call Y").
        produced_artifact_id = None
        if tool_output is not None and self.enable_provenance:
            produced_artifact_id = self.taint_tracker.observe(
                content=tool_output,
                origin_type="tool_output",
                source_event_id=event_id,
                trust_level=output_trust,
                source_tool=tool_name,
            ).artifact_id

        # Artifacts whose entities this call actually consumes. Recorded so the
        # graph can express "this sink read data that came from there". Empty
        # when taint tracking is off, which is what makes the ablation real.
        consumed_artifact_ids = []
        if self.enable_provenance and self.enable_taint_tracking:
            consumed_artifact_ids = [
                origin.artifact_id
                for origin in (
                    self.taint_tracker.origin_of(entity)
                    for entity in extract_entities(_flatten_params(params))
                )
                if origin is not None
            ]

        observed_event = ObservedToolEvent(
            event_id=event_id,
            session_id=self.session_id,
            tool_name=tool_name,
            tool_input=params,
            agent_id=agent_id,
            previous_tools=[
                n.tool_name for n in self.behavior_graph.get_session_nodes()[-5:]
            ],
            chain_length=len(self.behavior_graph.get_session_nodes()),
            produced_artifact_ids=(
                [produced_artifact_id] if produced_artifact_id else []
            ),
            consumed_artifact_ids=consumed_artifact_ids,
        )

        # PASS 1 -- local risk from this event's own content, plus provenance
        # signals that need what the session has already seen.
        local_state = self._risk_extractor.compute_graph_risk_state(
            event=observed_event,
            graph_inherited_risk=0.0,
            graph_downstream_exposure=0.0,
            graph_path_risk=0.0,
        )
        local_state.signals.extend(
            self._provenance_signals(
                tool_name=tool_name, tool_input=params
            )
        )

        # PASS 2 -- insert into the graph at *local* risk and wire the parent
        # edge, so propagation has something to travel along.
        #
        # The node is inserted twice: once provisionally with the local risk so
        # the edge exists, then rewritten with the propagated total. Inserting
        # only after the decision (the previous order) meant propagation always
        # ran on a graph that already excluded the current call, so the gate
        # could never see it.
        local_risk = local_state.combined_risk

        node = self.behavior_graph.add_tool_call_as_node(
            agent_id=agent_id,
            tool_name=tool_name,
            params_summary=self._summarize_params(tool_name, params),
            fuse_action=self._node_action("ALLOW"),
            shadow_risk_score=local_risk,
            parent_node_id=parent_node_id,
            inherited_risk=0.0,
            labels=labels or [],
        )

        # PASS 3 -- propagate. This is what makes the gate chain-aware: the
        # current node now has upstream neighbours inside the graph.
        propagated = self.behavior_graph.compute_risk_propagation()

        effective_risk = propagated.get(node.node_id, local_risk)
        graph_inherited = max(0.0, effective_risk - local_risk)

        # Refresh the signal state with the graph context that only exists
        # after insertion (downstream exposure, inherited risk).
        graph_downstream = 0.0
        if parent_node_id and parent_node_id in self.behavior_graph.nodes:
            downstream_nodes = self.behavior_graph.get_downstream_nodes(parent_node_id)
            graph_downstream = max(
                (n.shadow_risk_score for n in downstream_nodes), default=0.0
            )
        self._graph_risk_state = self._risk_extractor.compute_graph_risk_state(
            event=observed_event,
            graph_inherited_risk=graph_inherited,
            graph_downstream_exposure=graph_downstream,
            graph_path_risk=0.0,
        )
        # Keep the provenance signals: this recomputation only rebuilds the
        # graph-context signals, and dropping the provenance ones here would
        # silently undo the injection detection.
        self._graph_risk_state.signals.extend(
            self._provenance_signals(
                tool_name=tool_name, tool_input=params
            )
        )

        # PASS 4 -- govern on the propagated risk *and* the provenance signals.
        #
        # ``effective_risk`` is what the graph exports for this node (local risk
        # propagated along the edges). ``self._graph_risk_state.combined_risk``
        # additionally carries the provenance signals, which is where prompt
        # injection becomes visible -- an injected destination is not in the
        # call's own content at all.
        #
        # Both are folded into the node in PASS 5, so the invariant from C.5-8
        # still holds: the gate score equals the risk the graph exports for this
        # node.
        supplied = max(0.0, min(float(risk_score), 1.0))
        provenance_risk = self._graph_risk_state.combined_risk
        final_risk = max(
            0.0,
            min(max(effective_risk, provenance_risk, supplied), 1.0),
        )

        call_id = f"call_{uuid.uuid4().hex[:8]}"
        action = _action_for_score(final_risk)
        node_action = self._node_action(action)

        # PASS 5 -- write the governance outcome back onto the node so the
        # graph, its counters and the audit chain agree with the decision.
        self.behavior_graph.update_node_risk(
            node.node_id, total_risk=final_risk, fuse_action=node_action
        )

        branches = self._generate_future_branches(agent_id, tool_name, final_risk)
        gate_result = {
            "action": action,
            "reason": self._gate_reason(final_risk, action),
            "score": final_risk,
            "risk_level": _risk_level_for_score(final_risk),
            "gate_name": "DefaultV3Gate",
        }
        self._gate_count += 1

        whatif_result = None
        if self.enable_counterfactual and final_risk >= self.risk_threshold:
            whatif_result = self._counterfactual_engine.analyze_intervention(
                graph=self.behavior_graph,
                event_id=node.node_id,
            ).to_dict()

        self.world.patch_state(
            {
                f"last_tool_{agent_id}": {
                    "tool": tool_name,
                    "risk": final_risk,
                    "action": action,
                    "time": time.time(),
                }
            }
        )
        self.audit_logger.log(
            event="TOOL_CALL_PROCESSED",
            session_id=self.session_id,
            data={
                "call_id": call_id,
                "node_id": node.node_id,
                "agent_id": agent_id,
                "tool_name": tool_name,
                "risk_score": final_risk,
                "gate_action": action,
                "branches_generated": len(branches),
                "whatif_triggered": whatif_result is not None,
            },
        )

        return {
            "call_id": call_id,
            "node_id": node.node_id,
            "event_id": event_id,
            "session_id": self.session_id,
            "decision": action.lower() if action != "HUMAN_REVIEW" else "review",
            "risk_level": _risk_level_for_score(final_risk),
            "risk_score": final_risk,
            "reasoning": gate_result["reason"],
            "behavior_graph_summary": self.behavior_graph.summary(),
            "gate_result": gate_result,
            "future_branches": [branch.to_dict() for branch in branches],
            "whatif_result": whatif_result,
            "critical_nodes": [n.node_id for n in self.behavior_graph.get_critical_nodes()],
            "graph_risk_state": self._graph_risk_state.to_dict() if self._graph_risk_state else None,
            # Evidence chain: what this call consumed and produced, so a
            # blocked decision can be traced back to the artifact that
            # introduced the offending destination.
            "produced_artifact_ids": (
                [produced_artifact_id] if produced_artifact_id else []
            ),
            "consumed_artifact_ids": consumed_artifact_ids,
        }

    def _provenance_signals(self, tool_name: str, tool_input: Dict[str, Any]):
        """Provenance signals for this call, honouring the ablation switches.

        Returns an empty list when provenance is disabled, so the engine is
        exactly a single-event gate in that configuration. With
        ``enable_taint_tracking=False`` the origin-based signals are dropped and
        only "untrusted content is present" remains.
        """
        if not self.enable_provenance:
            return []
        return extract_provenance_signals(
            tool_name=tool_name,
            tool_input=tool_input,
            taint_tracker=self.taint_tracker,
            user_intent_text="" if self._ignore_user_intent else self.user_intent,
            track_taint=self.enable_taint_tracking,
            enable_trust_policy=self.enable_trust_policy,
            intent_slots=self.intent_slots if self.use_intent_slots else None,
        )

    def fork_branch(self, branch_label: str, intervention: Dict[str, Any]) -> str:
        risk = float(intervention.get("risk_score", 0.0) or 0.0)
        point = self.branch_tree.fork(
            point_label=branch_label,
            candidate_labels=[branch_label],
            candidate_risks=[risk],
            step=len(self.branch_tree.branch_points) + 1,
        )
        self._apply_intervention(intervention)
        branch_id = point.candidates[0].branch_id if point.candidates else point.point_id
        self.audit_logger.log(
            event="BRANCH_FORKED",
            session_id=self.session_id,
            data={"branch_id": branch_id, "label": branch_label, "intervention": intervention},
        )
        return branch_id

    def get_governance_status(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "engine_id": self.engine_id,
            "risk_threshold": self.risk_threshold,
            "branch_count": len(self.branch_tree.get_all_branches()),
            "behavior_graph": self.behavior_graph.summary(),
            "gate_count": self._gate_count,
            "world_state_keys": list(self.world.state.data.keys()),
        }

    def export_chain(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "engine_id": self.engine_id,
            "behavior_graph": self.behavior_graph.to_graph_dict(),
            "branch_tree": {
                "root": self.branch_tree.root_branch.branch_id,
                "active": self.branch_tree.active_branch.branch_id,
                "total_branches": len(self.branch_tree.get_all_branches()),
                "branch_points": [
                    {
                        "point_id": point.point_id,
                        "label": point.label,
                        "candidates": len(point.candidates),
                    }
                    for point in self.branch_tree.branch_points
                ],
            },
            "audit_chain": self.audit_logger.export_chain(),
        }

    # ── Private Methods ───────────────────────────────────────────────────

    def _generate_future_branches(
        self, agent_id: str, tool_name: str, risk_score: float
    ) -> List[_Branch]:
        if risk_score < self.risk_threshold:
            return []

        next_tools = self._candidate_next_tools(tool_name)[: self.max_branches]
        candidate_labels = [
            f"{agent_id}:{tool_name}->candidate_{index + 1}:{next_tool}"
            for index, next_tool in enumerate(next_tools)
        ]
        candidate_risks = [
            max(0.0, min(1.0, risk_score * factor))
            for factor in [0.45, 0.65, 0.85, 0.30, 0.55][: len(candidate_labels)]
        ]
        point = self.branch_tree.fork(
            point_label=f"future:{agent_id}.{tool_name}",
            candidate_labels=candidate_labels,
            candidate_risks=candidate_risks,
            step=len(self.branch_tree.branch_points) + 1,
        )
        return point.candidates

    @staticmethod
    def _candidate_next_tools(current_tool: str) -> List[str]:
        tool = current_tool.lower()
        if "email" in tool or "smtp" in tool:
            return ["external_delivery_receipt", "audit_log_write", "http_request"]
        if "sql" in tool or "cursor" in tool or "database" in tool:
            return ["export_csv", "send_email", "http_request", "audit_log_write"]
        if "http" in tool or "upload" in tool or "webhook" in tool:
            return ["response_parse", "file_write", "send_email"]
        return ["audit_log_write", "http_request", "cursor.execute"]

    @staticmethod
    def _summarize_params(tool_name: str, params: Dict[str, Any]) -> str:
        """生成参数摘要（图谱展示用，必须先脱敏）。

        脱敏逻辑在 app.shield.redaction：递归处理嵌套 dict/list，键名归一化后
        匹配已知敏感子串（passwd / api_key_id / X-Api-Key / AUTH_TOKEN 等变体）。
        旧实现只做顶层精确匹配，嵌套值和键名变体都会泄漏。
        """
        return _summarize_params_redacted(tool_name, params)

    @staticmethod
    def _node_action(action: str) -> str:
        if action == "BLOCK":
            return "block"
        if action == "HUMAN_REVIEW":
            return "human_review"
        return "allow"

    @staticmethod
    def _gate_reason(risk_score: float, action: str) -> str:
        if action == "BLOCK":
            return f"risk_score {risk_score:.2f} >= 0.90"
        if action == "HUMAN_REVIEW":
            return f"0.60 <= risk_score {risk_score:.2f} < 0.90"
        return f"risk_score {risk_score:.2f} < 0.60"

    def _apply_intervention(self, intervention: Dict[str, Any]) -> None:
        itype = intervention.get("type", "")
        if itype == "block_tool_call":
            self.world.patch_state({f"blocked_{intervention.get('tool_name', '')}": True})
        elif itype == "rate_limit":
            self.world.patch_state({"rate_limited_agents": intervention.get("agents", [])})
        elif itype == "escalate":
            self.world.patch_state({"escalated": True})

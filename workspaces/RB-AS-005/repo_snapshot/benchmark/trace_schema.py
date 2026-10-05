"""Schema helpers for controlled semi-real AgentShield traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TraceLabel(str, Enum):
    ALLOW = "ALLOW"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    BLOCK = "BLOCK"


class ScenarioType(str, Enum):
    NORMAL_BUSINESS_QUERY = "normal_business_query"
    NORMAL_REPORT_GENERATION = "normal_report_generation"
    SENSITIVE_QUERY_ONLY = "sensitive_query_only"
    SENSITIVE_QUERY_THEN_EXPORT = "sensitive_query_then_export"
    SENSITIVE_QUERY_THEN_COMPRESS_AND_SEND = "sensitive_query_then_compress_and_send"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    AUDIT_LOG_BYPASS = "audit_log_bypass"
    BULK_DELETE = "bulk_delete"
    MULTI_AGENT_DELEGATION_RISK = "multi_agent_delegation_risk"


@dataclass(frozen=True)
class ToolCallStep:
    trace_id: str
    session_id: str
    agent_id: str
    step: int
    parent_step: Optional[int]
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output_summary: str
    timestamp: str
    local_risk_type: str
    local_risk_score: float
    label: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorTrace:
    trace_id: str
    scenario_type: str
    chain_label: str
    risk_path: List[int]
    critical_step: int
    expected_intervention_step: int
    source: str
    human_reviewed: bool
    steps: List[ToolCallStep] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.to_dict() for step in self.steps]
        return data


REQUIRED_TRACE_KEYS = {
    "trace_id",
    "scenario_type",
    "chain_label",
    "risk_path",
    "critical_step",
    "expected_intervention_step",
    "source",
    "human_reviewed",
    "steps",
}

REQUIRED_STEP_KEYS = {
    "trace_id",
    "session_id",
    "agent_id",
    "step",
    "parent_step",
    "tool_name",
    "tool_input",
    "tool_output_summary",
    "timestamp",
    "local_risk_type",
    "local_risk_score",
    "label",
}


def validate_trace(trace: Dict[str, Any]) -> None:
    missing = REQUIRED_TRACE_KEYS - set(trace)
    if missing:
        raise ValueError(f"Trace missing keys: {sorted(missing)}")
    if trace["chain_label"] not in {label.value for label in TraceLabel}:
        raise ValueError(f"Invalid chain label: {trace['chain_label']}")
    if not isinstance(trace["steps"], list) or not trace["steps"]:
        raise ValueError("Trace must contain at least one step")

    for step in trace["steps"]:
        step_missing = REQUIRED_STEP_KEYS - set(step)
        if step_missing:
            raise ValueError(f"Step missing keys: {sorted(step_missing)}")
        if step["trace_id"] != trace["trace_id"]:
            raise ValueError("Step trace_id must match parent trace")
        if step["label"] not in {label.value for label in TraceLabel}:
            raise ValueError(f"Invalid step label: {step['label']}")
        score = float(step["local_risk_score"])
        if score < 0.0 or score > 1.0:
            raise ValueError("local_risk_score must be between 0 and 1")

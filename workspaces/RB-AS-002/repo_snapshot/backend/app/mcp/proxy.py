"""AgentShield V3 - MCP Shield Proxy.

Intercepts MCP tool invocations to provide:
- Tool descriptor scanning
- Tool invocation risk scoring
- Token scope checking
- Tool output leakage detection
- Cross-server risk propagation
- Tool poisoning detection
- Rug-pull detection
- Per-client consent tracking
- Audit chain export

Architecture:
    MCP Client → AgentShield MCP Proxy → MCP Server
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from app.security.mcp_detector import MCPAttackDetector, MCPThreatReport
from app.shield.risk_extractor import RiskSignalExtractor
from app.shield.schemas import ObservedToolEvent

# ─── MCP Event Schema ────────────────────────────────────────────────────────

@dataclass
class MCPToolInvocation:
    """Schema for an MCP tool invocation event."""
    client_id: str
    server_id: str
    tool_name: str
    tool_descriptor_hash: str = ""
    input_schema_hash: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    user_context: Dict[str, Any] = field(default_factory=dict)
    auth_scope: List[str] = field(default_factory=list)
    invocation_id: str = field(default_factory=lambda: f"mcp_inv_{uuid.uuid4().hex[:8]}")
    timestamp: float = field(default_factory=time.time)


@dataclass
class MCPToolDescriptor:
    """Schema for an MCP tool descriptor."""
    tool_name: str
    server_id: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    annotations: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = field(default_factory=time.time)


@dataclass
class MCPProxyDecision:
    """Decision from the MCP proxy for a tool invocation."""
    invocation_id: str
    tool_name: str
    server_id: str
    decision: str  # "allow", "review", "block"
    risk_score: float
    risk_level: str
    threat_report: Optional[MCPThreatReport] = None
    graph_risk_state: Optional[Dict[str, Any]] = None
    consent_required: bool = False
    reason: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "invocation_id": self.invocation_id,
            "tool_name": self.tool_name,
            "server_id": self.server_id,
            "decision": self.decision,
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level,
            "consent_required": self.consent_required,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }
        if self.threat_report:
            result["threat_report"] = self.threat_report.to_dict()
        if self.graph_risk_state:
            result["graph_risk_state"] = self.graph_risk_state
        return result


@dataclass
class ClientConsentRecord:
    """Record of client consent for tool usage."""
    client_id: str
    tool_name: str
    server_id: str
    granted: bool
    scope: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


# ─── MCP Shield Proxy ────────────────────────────────────────────────────────

class MCPShieldProxy:
    """Proxy layer that intercepts and governs MCP tool invocations.

    This is the core integration point between MCP protocol security
    and AgentShield's behavior-chain risk governance.
    """

    def __init__(
        self,
        session_id: str = "",
        enable_protocol_security: bool = True,
        enable_behavior_chain: bool = True,
        enable_consent_tracking: bool = True,
    ):
        self.session_id = session_id or f"mcp_session_{uuid.uuid4().hex[:8]}"

        # Protocol-level security detector
        self._mcp_detector = MCPAttackDetector(
            session_id=self.session_id,
        ) if enable_protocol_security else None

        # Behavior-chain risk extractor
        self._risk_extractor = RiskSignalExtractor() if enable_behavior_chain else None

        # Tool descriptor registry
        self._tool_descriptors: Dict[str, MCPToolDescriptor] = {}

        # Client consent records
        self._consent_records: List[ClientConsentRecord] = []
        self._enable_consent = enable_consent_tracking

        # Invocation history (for cross-server risk propagation)
        self._invocation_history: List[MCPToolInvocation] = []

        # Scope mapping: server_id -> set of allowed scopes
        self._server_scopes: Dict[str, Set[str]] = {}

    def register_tool(self, descriptor: MCPToolDescriptor) -> MCPProxyDecision:
        """Register a tool descriptor from an MCP server.

        Scans for protocol-level threats (shadow servers, description injection).
        """
        self._tool_descriptors[f"{descriptor.server_id}:{descriptor.tool_name}"] = descriptor

        # Protocol security check
        threat_report = None
        if self._mcp_detector:
            threat_report = self._mcp_detector.register_tool(
                tool_name=descriptor.tool_name,
                tool_description=descriptor.description,
                server_id=descriptor.server_id,
            )

        risk_score = threat_report.threat_score if threat_report else 0.0
        decision = "block" if risk_score >= 0.7 else "review" if risk_score >= 0.4 else "allow"

        return MCPProxyDecision(
            invocation_id=f"reg_{uuid.uuid4().hex[:8]}",
            tool_name=descriptor.tool_name,
            server_id=descriptor.server_id,
            decision=decision,
            risk_score=risk_score,
            risk_level=self._risk_level(risk_score),
            threat_report=threat_report,
            reason="Tool registered" if decision == "allow" else f"Security concern: {threat_report.indicators[0].description if threat_report and threat_report.indicators else 'unknown'}",
        )

    def evaluate_invocation(self, invocation: MCPToolInvocation) -> MCPProxyDecision:
        """Evaluate an MCP tool invocation before it reaches the server.

        This is the main entry point for the proxy.
        """
        self._invocation_history.append(invocation)

        # 1. Protocol-level security check
        threat_report = None
        if self._mcp_detector:
            chain_context = [inv.tool_name for inv in self._invocation_history[-10:]]
            threat_report = self._mcp_detector.analyze_tool_call(
                tool_name=invocation.tool_name,
                tool_description=self._get_descriptor_description(invocation),
                params=invocation.arguments,
                server_id=invocation.server_id,
                chain_context=chain_context,
            )

        # 2. Behavior-chain risk assessment
        graph_risk_state = None
        if self._risk_extractor:
            observed = ObservedToolEvent(
                event_id=invocation.invocation_id,
                session_id=self.session_id,
                agent_id=invocation.client_id,
                tool_name=invocation.tool_name,
                tool_input=invocation.arguments,
                previous_tools=[inv.tool_name for inv in self._invocation_history[-5:]],
                chain_length=len(self._invocation_history),
            )
            risk_state = self._risk_extractor.compute_graph_risk_state(observed)
            graph_risk_state = risk_state.to_dict()

        # 3. Token scope check
        scope_violation = self._check_scope(invocation)

        # 4. Output leakage detection (pre-check based on tool + args)
        leakage_risk = self._check_output_leakage(invocation)

        # 5. Consent check
        consent_required = self._check_consent_required(invocation)

        # 6. Combine scores
        protocol_risk = threat_report.threat_score if threat_report else 0.0
        behavior_risk = graph_risk_state.get("combined_risk", 0.0) if graph_risk_state else 0.0
        scope_risk = 0.5 if scope_violation else 0.0
        leakage_score = leakage_risk

        combined_risk = min(1.0, protocol_risk * 0.35 + behavior_risk * 0.35 + scope_risk * 0.15 + leakage_score * 0.15)

        # 7. Decision
        if combined_risk >= 0.9 or (threat_report and threat_report.is_threat and threat_report.recommended_action == "block"):
            decision = "block"
        elif combined_risk >= 0.6 or consent_required:
            decision = "review"
        else:
            decision = "allow"

        reason = self._build_decision_reason(
            decision, threat_report, scope_violation, leakage_risk, consent_required
        )

        return MCPProxyDecision(
            invocation_id=invocation.invocation_id,
            tool_name=invocation.tool_name,
            server_id=invocation.server_id,
            decision=decision,
            risk_score=combined_risk,
            risk_level=self._risk_level(combined_risk),
            threat_report=threat_report,
            graph_risk_state=graph_risk_state,
            consent_required=consent_required,
            reason=reason,
        )

    def record_consent(
        self,
        client_id: str,
        tool_name: str,
        server_id: str,
        granted: bool,
        scope: Optional[List[str]] = None,
    ) -> None:
        """Record a client's consent decision."""
        self._consent_records.append(ClientConsentRecord(
            client_id=client_id,
            tool_name=tool_name,
            server_id=server_id,
            granted=granted,
            scope=scope or [],
        ))

    def get_invocation_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent invocation history."""
        return [
            {
                "invocation_id": inv.invocation_id,
                "client_id": inv.client_id,
                "server_id": inv.server_id,
                "tool_name": inv.tool_name,
                "timestamp": inv.timestamp,
            }
            for inv in self._invocation_history[-limit:]
        ]

    # ─── Private Methods ──────────────────────────────────────────────────────

    def _get_descriptor_description(self, invocation: MCPToolInvocation) -> str:
        """Get tool description from registry."""
        key = f"{invocation.server_id}:{invocation.tool_name}"
        descriptor = self._tool_descriptors.get(key)
        return descriptor.description if descriptor else ""

    def _check_scope(self, invocation: MCPToolInvocation) -> bool:
        """Check if the invocation violates token scope."""
        if not invocation.auth_scope:
            return False
        allowed = self._server_scopes.get(invocation.server_id, set())
        if not allowed:
            return False
        # Any scope outside the server's allow-list is an escalation attempt.
        return any(scope not in allowed for scope in invocation.auth_scope)

    def _check_output_leakage(self, invocation: MCPToolInvocation) -> float:
        """Pre-check for potential output leakage."""
        tool = invocation.tool_name.lower()
        args_str = json.dumps(invocation.arguments, ensure_ascii=False).lower()

        risk = 0.0

        # External-facing tools with sensitive args
        external_tools = {"send_email", "http_request", "upload_file", "webhook_call"}
        if any(t in tool for t in external_tools):
            sensitive_patterns = ["password", "secret", "token", "ssn", "credit_card", "api_key"]
            for p in sensitive_patterns:
                if p in args_str:
                    risk += 0.3
                    break
            risk += 0.1  # Base risk for external tools

        return min(1.0, risk)

    def _check_consent_required(self, invocation: MCPToolInvocation) -> bool:
        """Check if client consent is required for this invocation."""
        if not self._enable_consent:
            return False

        # Check if there's a prior consent record
        for record in reversed(self._consent_records):
            if (record.client_id == invocation.client_id
                    and record.tool_name == invocation.tool_name
                    and record.server_id == invocation.server_id
                    and record.granted):
                return False

        # High-risk tools require consent
        high_risk_tools = {"bulk_delete", "modify_role", "disable_audit", "drop_table"}
        if any(t in invocation.tool_name.lower() for t in high_risk_tools):
            return True

        return False

    @staticmethod
    def _risk_level(score: float) -> str:
        if score >= 0.9:
            return "critical"
        if score >= 0.7:
            return "high"
        if score >= 0.4:
            return "medium"
        return "low"

    @staticmethod
    def _build_decision_reason(
        decision: str,
        threat_report: Optional[MCPThreatReport],
        scope_violation: bool,
        leakage_risk: float,
        consent_required: bool,
    ) -> str:
        parts = []
        if threat_report and threat_report.indicators:
            top = threat_report.indicators[0]
            parts.append(f"MCP threat: {top.attack_type.value} ({top.severity.value})")
        if scope_violation:
            parts.append("token scope violation")
        if leakage_risk > 0.2:
            parts.append(f"output leakage risk ({leakage_risk:.0%})")
        if consent_required:
            parts.append("client consent required")
        if not parts:
            parts.append("no risk indicators")
        return f"{decision.upper()}: " + "; ".join(parts)

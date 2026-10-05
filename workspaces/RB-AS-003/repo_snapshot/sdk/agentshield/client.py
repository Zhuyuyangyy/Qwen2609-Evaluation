"""AgentShield SDK - Client implementation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


class SecurityException(Exception):
    """Raised when a tool call is blocked by AgentShield."""

    def __init__(self, reason: str, decision: Optional["ShieldDecision"] = None):
        super().__init__(reason)
        self.reason = reason
        self.decision = decision


@dataclass
class ShieldDecision:
    """Result of a governance decision from AgentShield."""

    call_id: str = ""
    node_id: str = ""
    session_id: str = ""
    decision: str = "allow"  # "allow", "review", "block"
    risk_level: str = "low"
    risk_score: float = 0.0
    reasoning: str = ""
    gate_result: Dict[str, Any] = field(default_factory=dict)
    future_branches: List[Dict[str, Any]] = field(default_factory=list)
    whatif_result: Optional[Dict[str, Any]] = None
    graph_risk_state: Optional[Dict[str, Any]] = None
    critical_nodes: List[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.decision == "block"

    @property
    def needs_review(self) -> bool:
        return self.decision == "review"

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShieldDecision":
        return cls(
            call_id=data.get("call_id", ""),
            node_id=data.get("node_id", ""),
            session_id=data.get("session_id", ""),
            decision=data.get("decision", "allow"),
            risk_level=data.get("risk_level", "low"),
            risk_score=data.get("risk_score", 0.0),
            reasoning=data.get("reasoning", ""),
            gate_result=data.get("gate_result", {}),
            future_branches=data.get("future_branches", []),
            whatif_result=data.get("whatif_result"),
            graph_risk_state=data.get("graph_risk_state"),
            critical_nodes=data.get("critical_nodes", []),
        )


class Shield:
    """AgentShield governance client.

    Usage:
        shield = Shield(
            project="finance-agent",
            base_url="http://localhost:8011",
            api_key="ash_your_key_here",
        )

        decision = shield.evaluate_tool_call(
            agent_id="analyst_agent",
            tool_name="send_email",
            arguments={"to": "external@example.com"},
        )

        if decision.blocked:
            raise SecurityException(decision.reason, decision)
    """

    def __init__(
        self,
        project: str = "default",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        risk_threshold: float = 0.70,
        auto_session: bool = True,
    ):
        self.project = project
        self.base_url = base_url or os.environ.get(
            "AGENTSHIELD_URL", "http://localhost:8011"
        )
        self.api_key = api_key or os.environ.get("AGENTSHIELD_API_KEY", "")
        self.session_id = session_id or (f"sdk_{uuid.uuid4().hex[:8]}" if auto_session else "")
        self.risk_threshold = risk_threshold
        self._history: List[ShieldDecision] = []

    def evaluate_tool_call(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_score: float = 0.0,
        parent_event_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
    ) -> ShieldDecision:
        """Evaluate a tool call through the AgentShield governance pipeline.

        Args:
            agent_id: Identifier of the calling agent
            tool_name: Name of the tool being invoked
            arguments: Tool call arguments/parameters
            risk_score: Optional pre-computed risk score (0.0-1.0)
            parent_event_id: Optional parent event ID for chain linking
            labels: Optional categorization labels

        Returns:
            ShieldDecision with governance result
        """
        payload = {
            "session_id": self.session_id,
            "agent_id": agent_id,
            "tool_name": tool_name,
            "params": arguments,
            "risk_score": risk_score,
            "fuse_action": "allow",
        }
        if parent_event_id:
            payload["parent_node_id"] = parent_event_id
        if labels:
            payload["labels"] = labels

        response_data = self._post("/api/v3/process_call", payload)
        decision = ShieldDecision.from_dict(response_data)
        self._history.append(decision)
        return decision

    def get_session_status(self) -> Dict[str, Any]:
        """Get the current session's governance status."""
        return self._get(f"/api/v3/status/{self.session_id}")

    def export_chain(self) -> Dict[str, Any]:
        """Export the full behavior chain for the current session."""
        return self._get(f"/api/v3/export_chain/{self.session_id}")

    def get_behavior_graph(self) -> Dict[str, Any]:
        """Get the behavior graph for the current session."""
        return self._get(f"/api/v3/behavior_graph/{self.session_id}")

    def fork_branch(
        self,
        branch_label: str,
        intervention: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a manual intervention branch."""
        return self._post("/api/v3/fork_branch", {
            "session_id": self.session_id,
            "branch_label": branch_label,
            "intervention": intervention,
        })

    def evaluate_mcp_tool(
        self,
        client_id: str,
        server_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        auth_scope: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Evaluate an MCP tool invocation through the proxy."""
        return self._post("/api/mcp/invoke", {
            "client_id": client_id,
            "server_id": server_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "auth_scope": auth_scope or [],
            "session_id": self.session_id,
        })

    @property
    def history(self) -> List[ShieldDecision]:
        """Get the decision history for this session."""
        return list(self._history)

    @property
    def blocked_count(self) -> int:
        """Number of blocked calls in this session."""
        return sum(1 for d in self._history if d.blocked)

    @property
    def review_count(self) -> int:
        """Number of calls requiring review in this session."""
        return sum(1 for d in self._history if d.needs_review)

    # ─── HTTP Methods ──────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _post(self, path: str, data: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        if _HAS_HTTPX:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=data, headers=self._headers())
                response.raise_for_status()
                return response.json()
        else:
            import urllib.request
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode(),
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        if _HAS_HTTPX:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=self._headers())
                response.raise_for_status()
                return response.json()
        else:
            import urllib.request
            req = urllib.request.Request(url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())

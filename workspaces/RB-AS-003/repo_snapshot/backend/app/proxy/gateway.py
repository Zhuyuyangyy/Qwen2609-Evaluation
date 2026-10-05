"""AgentShield V3 - Policy Gateway Proxy.

Sits between agent applications and tools/MCP servers,
intercepting all tool calls for governance evaluation.

Architecture:
    Agent App → AgentShield Proxy → Tools / MCP Servers

Usage:
    from app.proxy.gateway import PolicyGateway

    gateway = PolicyGateway(base_url="http://localhost:8011")

    # Intercept a tool call
    decision = gateway.intercept(
        agent_id="analyst",
        tool_name="send_email",
        arguments={"to": "external@example.com"},
    )

    if decision.allowed:
        result = execute_tool(...)
    else:
        raise SecurityException(decision.reason)
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional


@dataclass
class ProxyDecision:
    """Decision from the policy gateway."""
    allowed: bool
    decision: str  # "allow", "review", "block"
    reason: str
    risk_score: float
    risk_level: str
    call_id: str = ""
    session_id: str = ""
    node_id: str = ""

    @property
    def blocked(self) -> bool:
        return self.decision == "block"

    @property
    def needs_review(self) -> bool:
        return self.decision == "review"


class PolicyGateway:
    """Policy gateway that intercepts tool calls for governance.

    This can be used as a transparent proxy between agent frameworks
    and their tools, requiring no changes to agent code.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8011",
        api_key: Optional[str] = None,
        session_id: Optional[str] = None,
        project: str = "default",
        on_block: Optional[Callable[[ProxyDecision], None]] = None,
        on_review: Optional[Callable[[ProxyDecision], None]] = None,
    ):
        self.base_url = base_url
        self.api_key = api_key or os.environ.get("AGENTSHIELD_API_KEY", "")
        self.session_id = session_id or f"proxy_{uuid.uuid4().hex[:8]}"
        self.project = project
        self.on_block = on_block
        self.on_review = on_review
        self._intercept_count = 0

    def intercept(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        risk_score: float = 0.0,
        parent_event_id: Optional[str] = None,
    ) -> ProxyDecision:
        """Intercept a tool call and return a governance decision.

        This is the main entry point for the proxy.
        """
        self._intercept_count += 1

        try:
            result = self._evaluate(
                agent_id=agent_id,
                tool_name=tool_name,
                arguments=arguments,
                risk_score=risk_score,
                parent_event_id=parent_event_id,
            )

            decision = ProxyDecision(
                allowed=result.get("decision") == "allow",
                decision=result.get("decision", "allow"),
                reason=result.get("reasoning", ""),
                risk_score=result.get("risk_score", 0.0),
                risk_level=result.get("risk_level", "low"),
                call_id=result.get("call_id", ""),
                session_id=result.get("session_id", ""),
                node_id=result.get("node_id", ""),
            )
        except Exception as e:
            # Fail-closed: if we can't evaluate, block
            decision = ProxyDecision(
                allowed=False,
                decision="block",
                reason=f"Governance evaluation failed: {e}",
                risk_score=1.0,
                risk_level="critical",
            )

        # Callbacks
        if decision.blocked and self.on_block:
            self.on_block(decision)
        elif decision.needs_review and self.on_review:
            self.on_review(decision)

        return decision

    def wrap_tool(self, tool_func: Callable, agent_id: str, tool_name: Optional[str] = None):
        """Wrap a tool function with governance interception.

        Usage:
            @gateway.wrap_tool
            def send_email(to, body):
                ...

            # Or with explicit naming:
            @gateway.wrap_tool(agent_id="email_agent", tool_name="send_email")
            def my_email_func(to, body):
                ...
        """
        name = tool_name or tool_func.__name__

        def wrapper(*args, **kwargs):
            arguments = {"args": list(args), "kwargs": dict(kwargs)}
            decision = self.intercept(
                agent_id=agent_id,
                tool_name=name,
                arguments=arguments,
            )
            if decision.blocked:
                raise SecurityException(decision.reason, decision)
            return tool_func(*args, **kwargs)

        wrapper.__name__ = tool_func.__name__
        wrapper.__doc__ = tool_func.__doc__
        return wrapper

    @property
    def intercept_count(self) -> int:
        return self._intercept_count

    def _evaluate(self, **kwargs) -> Dict[str, Any]:
        """Call the AgentShield API for evaluation."""
        try:
            import httpx
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{self.base_url}/api/v3/process_call",
                    json={
                        "session_id": self.session_id,
                        "agent_id": kwargs["agent_id"],
                        "tool_name": kwargs["tool_name"],
                        "params": kwargs["arguments"],
                        "risk_score": kwargs.get("risk_score", 0.0),
                        "fuse_action": "allow",
                        "parent_node_id": kwargs.get("parent_event_id"),
                    },
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()
        except ImportError:
            # Fallback without httpx
            import urllib.request
            data = json.dumps({
                "session_id": self.session_id,
                "agent_id": kwargs["agent_id"],
                "tool_name": kwargs["tool_name"],
                "params": kwargs["arguments"],
                "risk_score": kwargs.get("risk_score", 0.0),
                "fuse_action": "allow",
            }).encode()
            req = urllib.request.Request(
                f"{self.base_url}/api/v3/process_call",
                data=data,
                headers=self._headers(),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers


class SecurityException(Exception):
    """Raised when a tool call is blocked by the policy gateway."""

    def __init__(self, reason: str, decision: Optional[ProxyDecision] = None):
        super().__init__(reason)
        self.reason = reason
        self.decision = decision

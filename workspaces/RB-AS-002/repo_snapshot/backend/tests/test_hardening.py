"""Tests for cross-cutting hardening added to AgentShield V3.

Covers the gaps that had no regression protection:

* credential redaction in behavior-graph parameter summaries
  (nested dicts, key variants, list payloads)
* CORS configuration (wildcard + credentials was silently broken)
* rate limiting (``/health`` must stay unlimited for probes; ``/api/evaluate``
  must be limited; the key must honour ``X-Forwarded-For``)
* risk-weighted path extraction and downstream traversal
* audit-chain hash verification
* deterministic behavior-chain risk scoring
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _load_standalone_app():
    """Load backend/app.py as a module without polluting ``app`` package."""
    app_py = _BACKEND_DIR / "app.py"
    spec = importlib.util.spec_from_file_location("app_standalone_hardening", str(app_py))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["app_standalone_hardening"] = mod
    return mod


@pytest.fixture
def standalone_app():
    return _load_standalone_app().app


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── Credential redaction ───────────────────────────────────────────────────

class TestCredentialRedaction:
    """Parameter summaries must never leak credentials."""

    @staticmethod
    def _summ(params):
        from app.shield.v3_engine import V3ShieldEngine

        return V3ShieldEngine._summarize_params("tool", params)

    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "passwd",
            "pwd",
            "token",
            "secret",
            "api_key",
            "api_key_id",
            "authorization",
            "credential",
            "private_key",
            "session_key",
            "cookie",
            "signature",
            "cvv",
            "card_number",
        ],
    )
    def test_top_level_sensitive_keys_are_masked(self, key):
        summary = self._summ({key: "SUPER-SECRET-VALUE"})
        assert "SUPER-SECRET-VALUE" not in summary
        assert "***" in summary

    @pytest.mark.parametrize(
        "key",
        ["X-Api-Key", "AUTH_TOKEN", "Passwd", "API-KEY", "Client_Secret"],
    )
    def test_key_variants_are_masked(self, key):
        summary = self._summ({key: "SUPER-SECRET-VALUE"})
        assert "SUPER-SECRET-VALUE" not in summary

    def test_nested_dict_values_are_masked(self):
        summary = self._summ({"db": {"password": "hunter2", "host": "db.internal"}})
        assert "hunter2" not in summary
        # Non-sensitive siblings survive for debugging.
        assert "db.internal" in summary

    def test_deeply_nested_values_are_masked(self):
        summary = self._summ({"a": {"b": {"c": {"private_key": "K"}}}})
        assert "K" not in summary

    def test_values_inside_lists_are_masked(self):
        summary = self._summ({"creds": [{"secret": "s3cr3t"}, {"ok": 1}]})
        assert "s3cr3t" not in summary

    def test_non_sensitive_params_are_preserved(self):
        summary = self._summ({"query": "SELECT 1", "limit": 10})
        assert "SELECT 1" in summary
        assert "limit=10" in summary
        assert "***" not in summary

    def test_empty_params(self):
        assert self._summ({}) == "tool()"

    def test_depth_is_bounded(self):
        """Pathological nesting must not blow up or leak past the cap."""
        payload = current = {}
        for _ in range(30):
            current["child"] = {}
            current = current["child"]
        current["password"] = "deep-secret"
        summary = self._summ({"root": payload})
        assert "deep-secret" not in summary


# ─── CORS ───────────────────────────────────────────────────────────────────

class TestCORSConfiguration:
    """Wildcard origin + credentials is rejected by browsers."""

    def test_no_credentials_without_configured_origins(self, standalone_app):
        from app.factory import allowed_origins

        assert allowed_origins() == []

    @pytest.mark.anyio
    async def test_unlisted_origin_gets_no_allow_header(self, standalone_app):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            resp = await client.get("/health", headers={"Origin": "http://evil.example"})
        assert resp.headers.get("access-control-allow-origin") is None

    @pytest.mark.anyio
    async def test_plain_request_still_works(self, standalone_app):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200


# ─── Rate limiting ──────────────────────────────────────────────────────────

class TestRateLimiting:
    def test_health_is_not_rate_limited(self):
        """/health must stay unlimited for Docker/K8s probes."""
        mod = _load_standalone_app()
        for route in mod.app.routes:
            if getattr(route, "path", None) == "/health":
                endpoint = route.endpoint
                # slowapi attaches a __wrapped__/limit metadata attribute.
                assert not hasattr(endpoint, "__wrapped__") or not _has_limits(endpoint)
                return
        pytest.fail("/health route not found")

    def test_rate_limit_key_prefers_forwarded_for(self):
        from app.standalone_routes import _rate_limit_key
        from fastapi import Request

        scope = {
            "type": "http",
            "headers": [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
            "client": ("10.0.0.1", 1234),
        }
        assert _rate_limit_key(Request(scope)) == "203.0.113.9"

    def test_rate_limit_key_falls_back_to_socket(self):
        from app.standalone_routes import _rate_limit_key
        from fastapi import Request

        scope = {"type": "http", "headers": [], "client": ("198.51.100.7", 999)}
        assert _rate_limit_key(Request(scope)) == "198.51.100.7"

    def test_rate_limit_key_survives_missing_client(self):
        from app.standalone_routes import _rate_limit_key
        from fastapi import Request

        scope = {"type": "http", "headers": [], "client": None}
        assert _rate_limit_key(Request(scope)) == "unknown"


def _has_limits(endpoint) -> bool:
    """True if a slowapi limit decorator was applied to ``endpoint``."""
    for attr in ("__wrapped__", "__self__"):
        inner = getattr(endpoint, attr, None)
        if inner is None:
            continue
        if getattr(inner, "__slowapi_limits__", None):
            return True
    return bool(getattr(endpoint, "__slowapi_limits__", None))


# ─── Graph traversal ────────────────────────────────────────────────────────

class TestRiskWeightedPath:
    @staticmethod
    def _two_path_graph():
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        g = AgentBehaviorGraph(session_id="path")
        a = g.add_tool_call_as_node(
            agent_id="a", tool_name="A", params_summary="",
            fuse_action="allow", shadow_risk_score=0.1,
        )
        b = g.add_tool_call_as_node(
            agent_id="a", tool_name="B", params_summary="",
            fuse_action="allow", shadow_risk_score=0.1, parent_node_id=a.node_id,
        )
        c = g.add_tool_call_as_node(
            agent_id="a", tool_name="C", params_summary="",
            fuse_action="allow", shadow_risk_score=0.9, parent_node_id=a.node_id,
        )
        d = g.add_tool_call_as_node(
            agent_id="a", tool_name="D", params_summary="",
            fuse_action="allow", shadow_risk_score=0.9, parent_node_id=c.node_id,
        )
        e = g.add_tool_call_as_node(
            agent_id="a", tool_name="E", params_summary="",
            fuse_action="allow", shadow_risk_score=0.1, parent_node_id=b.node_id,
        )
        return g, a, b, c, d, e

    def test_picks_high_risk_path_not_shortest(self):
        g, a, b, c, d, e = self._two_path_graph()
        from app.shield.agent_behavior_graph import BehaviorEdge

        g.add_edge(BehaviorEdge(from_node_id=d.node_id, to_node_id=e.node_id, transfer_weight=0.9))
        path = g.get_risk_path(a.node_id, e.node_id)
        names = [n.tool_name for n in path]
        assert names == ["A", "C", "D", "E"]
        assert sum(n.shadow_risk_score for n in path) == pytest.approx(2.0)

    def test_unreachable_returns_empty(self):
        g, a, b, c, d, e = self._two_path_graph()
        assert g.get_risk_path(e.node_id, a.node_id) == []

    def test_same_start_and_end(self):
        g, a, b, c, d, e = self._two_path_graph()
        assert [n.tool_name for n in g.get_risk_path(a.node_id, a.node_id)] == ["A"]

    def test_unknown_node_returns_empty(self):
        g, a, b, c, d, e = self._two_path_graph()
        assert g.get_risk_path("nope", a.node_id) == []


class TestDownstreamTraversal:
    def test_returns_transitive_descendants(self):
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        g = AgentBehaviorGraph(session_id="down")
        a = g.add_tool_call_as_node(
            agent_id="a", tool_name="A", params_summary="",
            fuse_action="allow", shadow_risk_score=0.5,
        )
        b = g.add_tool_call_as_node(
            agent_id="a", tool_name="B", params_summary="",
            fuse_action="allow", shadow_risk_score=0.5, parent_node_id=a.node_id,
        )
        c = g.add_tool_call_as_node(
            agent_id="a", tool_name="C", params_summary="",
            fuse_action="allow", shadow_risk_score=0.5, parent_node_id=b.node_id,
        )
        names = {n.tool_name for n in g.get_downstream_nodes(a.node_id)}
        assert names == {"B", "C"}
        assert g.get_downstream_nodes(c.node_id) == []

    def test_cycle_does_not_hang(self):
        from app.shield.agent_behavior_graph import AgentBehaviorGraph, BehaviorEdge

        g = AgentBehaviorGraph(session_id="cyc")
        a = g.add_tool_call_as_node(
            agent_id="a", tool_name="A", params_summary="",
            fuse_action="allow", shadow_risk_score=0.5,
        )
        b = g.add_tool_call_as_node(
            agent_id="a", tool_name="B", params_summary="",
            fuse_action="allow", shadow_risk_score=0.5, parent_node_id=a.node_id,
        )
        g.add_edge(BehaviorEdge(from_node_id=b.node_id, to_node_id=a.node_id, transfer_weight=0.5))
        # Must terminate rather than loop forever. In a cycle A is reachable
        # from itself, so both nodes appear exactly once.
        downstream = g.get_downstream_nodes(a.node_id)
        names = [n.tool_name for n in downstream]
        assert sorted(names) == ["A", "B"]
        assert len(names) == len(set(names))  # no duplicates


# ─── Audit chain integrity ──────────────────────────────────────────────────

class TestAuditChainVerification:
    def test_intact_chain_verifies(self):
        from app.shield.v3_audit_logger import V3AuditLogger

        logger = V3AuditLogger()
        for i in range(5):
            logger.log(event="E", session_id="s", data={"i": i})
        assert logger.verify_chain() is True

    def test_tampered_record_fails_verification(self):
        from app.shield.v3_audit_logger import V3AuditLogger

        logger = V3AuditLogger()
        logger.log(event="E", session_id="s", data={"i": 0})
        logger.log(event="E", session_id="s", data={"i": 1})
        # Rewrite history without fixing the hash chain.
        logger.records[0]["data"]["i"] = 999
        assert logger.verify_chain() is False

    def test_empty_chain_verifies(self):
        from app.shield.v3_audit_logger import V3AuditLogger

        assert V3AuditLogger().verify_chain() is True


# ─── Deterministic behavior-chain scoring ───────────────────────────────────

class TestBehaviorChainIsDeterministic:
    @pytest.mark.anyio
    async def test_identical_input_yields_identical_risk(self, standalone_app):
        from httpx import ASGITransport, AsyncClient

        payload = {
            "agents": [
                {"id": "a1", "action": "read_file", "target": "local", "input": {"p": 1}},
                {"id": "a2", "action": "send_email", "target": "external", "input": {}},
            ]
        }
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            first = (await client.post("/api/agent/behavior_chain", json=payload)).json()
            second = (await client.post("/api/agent/behavior_chain", json=payload)).json()

        assert [s["risk_score"] for s in first["steps"]] == [
            s["risk_score"] for s in second["steps"]
        ]
        assert first["verdict"] == second["verdict"]

    @pytest.mark.anyio
    async def test_explicit_risk_score_influences_result(self, standalone_app):
        """An explicit risk_score moves the blended risk, deterministically.

        The engine blends an externally supplied score with its own
        graph-derived signal (0.6 * computed + 0.4 * supplied), so the value is
        not echoed verbatim -- but it must shift the outcome, and the same
        input must always give the same number.
        """
        from httpx import ASGITransport, AsyncClient

        low = {"agents": [{"id": "a", "action": "noop", "target": "", "input": {}, "risk_score": 0.05}]}
        high = {"agents": [{"id": "a", "action": "noop", "target": "", "input": {}, "risk_score": 0.95}]}
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            body_low = (await client.post("/api/agent/behavior_chain", json=low)).json()
            body_high = (await client.post("/api/agent/behavior_chain", json=high)).json()
            repeat = (await client.post("/api/agent/behavior_chain", json=low)).json()

        assert body_low["steps"][0]["risk_score"] < body_high["steps"][0]["risk_score"]
        # Deterministic: identical input, identical output.
        assert body_low["steps"][0]["risk_score"] == repeat["steps"][0]["risk_score"]

    @pytest.mark.anyio
    async def test_risk_rises_monotonically_with_supplied_score(self, standalone_app):
        """Supplied risk_score raises the blended risk, deterministically.

        The engine blends the caller's score with its own signal-derived risk
        (0.6 * computed + 0.4 * supplied), so a high supplied score is not an
        automatic BLOCK -- what must hold is that it moves the number up and
        that identical input always yields identical output.
        """
        from httpx import ASGITransport, AsyncClient

        def payload(score):
            return {
                "agents": [
                    {"id": "a", "action": "delete", "target": "production", "input": {}, "risk_score": score}
                ]
            }

        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            low = (await client.post("/api/agent/behavior_chain", json=payload(0.1))).json()
            mid = (await client.post("/api/agent/behavior_chain", json=payload(0.5))).json()
            high = (await client.post("/api/agent/behavior_chain", json=payload(0.99))).json()
            repeat = (await client.post("/api/agent/behavior_chain", json=payload(0.99))).json()

        risks = [
            low["steps"][0]["risk_score"],
            mid["steps"][0]["risk_score"],
            high["steps"][0]["risk_score"],
        ]
        assert risks[0] < risks[1] < risks[2]
        # Deterministic.
        assert high["steps"][0]["risk_score"] == repeat["steps"][0]["risk_score"]

    @pytest.mark.anyio
    async def test_empty_chain(self, standalone_app):
        from httpx import ASGITransport, AsyncClient

        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            body = (await client.post("/api/agent/behavior_chain", json={"agents": []})).json()
        assert body["steps"] == []
        assert body["verdict"] == "allow"
        assert body["risk_score"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

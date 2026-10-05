"""
AgentShield V3 Smoke Tests
==========================
Fast import and configuration sanity checks.
These tests verify the project is correctly installed and configured
before running the full test suite.
"""

from pathlib import Path

import pytest

# ─── Import Tests ────────────────────────────────────────────────────────────

class TestImports:
    """Verify all critical modules can be imported."""

    def test_import_main_app(self):
        from app.main import app
        assert app is not None
        assert app.title == "AgentShield V3"

    def test_import_v3_engine(self):
        from app.shield.v3_engine import V3ShieldEngine
        assert V3ShieldEngine is not None

    def test_import_behavior_graph(self):
        from app.shield.agent_behavior_graph import AgentBehaviorGraph
        assert AgentBehaviorGraph is not None

    def test_import_behavior_graph_node_types(self):
        from app.shield.agent_behavior_graph import (
            BehaviorEdge,
            BehaviorNode,
            NodeRiskStatus,
        )
        assert BehaviorNode is not None
        assert BehaviorEdge is not None
        assert NodeRiskStatus.SAFE.value == "safe"
        assert NodeRiskStatus.CRITICAL.value == "critical"

    def test_import_audit_logger(self):
        from app.shield.v3_audit_logger import V3AuditLogger
        assert V3AuditLogger is not None

    def test_import_session_store(self):
        from app.shield.session_store import init_db, list_sessions, load_session, save_session
        assert callable(init_db)
        assert callable(save_session)
        assert callable(load_session)
        assert callable(list_sessions)

    def test_import_routes(self):
        from app.api.routes import router
        assert router is not None
        assert router.prefix == "/api/v3"

    def test_import_routes_request_models(self):
        from app.api.routes import (
            ForkBranchRequest,
            GovernanceStatusResponse,
            ProcessCallRequest,
        )
        assert ProcessCallRequest is not None
        assert ForkBranchRequest is not None
        assert GovernanceStatusResponse is not None

    def test_import_standalone_app(self):
        """The standalone app.py entry point (port 8090) should be loadable."""
        import importlib.util
        app_py = Path(__file__).resolve().parents[1] / "app.py"
        assert app_py.exists(), f"app.py not found at {app_py}"
        spec = importlib.util.spec_from_file_location("app_standalone", str(app_py))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "app")


# ─── Configuration Tests ─────────────────────────────────────────────────────

class TestConfiguration:
    """Verify project configuration is consistent."""

    def test_pytest_ini_exists(self):
        ini = Path(__file__).resolve().parents[2] / "pytest.ini"
        assert ini.exists(), f"pytest.ini not found at {ini}"

    def test_pytest_ini_testpaths(self):
        ini = Path(__file__).resolve().parents[2] / "pytest.ini"
        content = ini.read_text(encoding="utf-8")
        assert "backend/tests" in content

    def test_requirements_txt_exists(self):
        req = Path(__file__).resolve().parents[2] / "requirements.txt"
        assert req.exists(), f"requirements.txt not found at {req}"

    def test_requirements_include_fastapi(self):
        req = Path(__file__).resolve().parents[2] / "requirements.txt"
        content = req.read_text(encoding="utf-8")
        assert "fastapi" in content.lower()

    def test_requirements_include_pytest(self):
        req = Path(__file__).resolve().parents[2] / "requirements.txt"
        content = req.read_text(encoding="utf-8")
        assert "pytest" in content.lower()

    def test_dockerfile_exists(self):
        dockerfile = Path(__file__).resolve().parents[2] / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile not found"

    def test_engine_default_risk_threshold(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="config_test_001")
        assert engine.risk_threshold == pytest.approx(0.70)

    def test_engine_default_max_branches(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="config_test_002")
        assert engine.max_branches == 5

    def test_engine_counterfactual_enabled_by_default(self):
        from app.shield.v3_engine import V3ShieldEngine

        engine = V3ShieldEngine(session_id="config_test_003")
        assert engine.enable_counterfactual is True

    def test_session_store_db_initialized(self):
        """session_store.init_db() should not raise."""
        from app.shield.session_store import init_db
        init_db()  # Should be idempotent

    def test_action_for_score_boundaries(self):
        """Verify the risk score -> action mapping boundaries."""
        from app.shield.v3_engine import _action_for_score

        assert _action_for_score(0.0) == "ALLOW"
        assert _action_for_score(0.59) == "ALLOW"
        assert _action_for_score(0.60) == "HUMAN_REVIEW"
        assert _action_for_score(0.89) == "HUMAN_REVIEW"
        assert _action_for_score(0.90) == "BLOCK"
        assert _action_for_score(1.0) == "BLOCK"

    def test_risk_level_boundaries(self):
        """Verify the risk score -> risk level mapping."""
        from app.shield.v3_engine import _risk_level_for_score

        assert _risk_level_for_score(0.0) == "low"
        assert _risk_level_for_score(0.39) == "low"
        assert _risk_level_for_score(0.40) == "medium"
        assert _risk_level_for_score(0.69) == "medium"
        assert _risk_level_for_score(0.70) == "high"
        assert _risk_level_for_score(0.89) == "high"
        assert _risk_level_for_score(0.90) == "critical"
        assert _risk_level_for_score(1.0) == "critical"


# ─── Health / Sanity ─────────────────────────────────────────────────────────

class TestSanity:
    """Quick sanity checks on core objects."""

    def test_engine_creates_unique_ids(self):
        from app.shield.v3_engine import V3ShieldEngine

        e1 = V3ShieldEngine(session_id="sanity_001")
        e2 = V3ShieldEngine(session_id="sanity_002")
        assert e1.engine_id != e2.engine_id

    def test_audit_logger_hash_chain(self):
        from app.shield.v3_audit_logger import V3AuditLogger

        logger = V3AuditLogger()
        logger.log(event="TEST_A", session_id="s1", data={"x": 1})
        logger.log(event="TEST_B", session_id="s1", data={"x": 2})
        assert logger.verify_chain() is True
        assert len(logger.get_records()) == 2

    def test_behavior_graph_empty_summary(self):
        from app.shield.agent_behavior_graph import AgentBehaviorGraph

        graph = AgentBehaviorGraph(session_id="empty_test")
        summary = graph.summary()
        assert summary["total_nodes"] == 0
        assert summary["total_edges"] == 0

    def test_conformal_predictor_importable(self):
        """CP core module and its NCFs must be importable.

        This previously wrapped the import in ``try/except ImportError ->
        skip``, which hid a genuinely broken ``app.cp``.  The layer is a
        declared dependency in requirements.txt, so failure here is a real
        regression and must not be quietly skipped.
        """
        from app.cp import (
            CROSS_ENTROPY_LABELS,
            AdaptiveNCF,
            BehaviorGraphNCF,
            ScoreBasedNCF,
        )
        from app.cp.core import ConformalPredictor, PredictionSet

        assert ConformalPredictor is not None
        assert PredictionSet is not None
        assert CROSS_ENTROPY_LABELS == ["ALLOW", "HUMAN_REVIEW", "BLOCK"]
        for ncf_cls in (ScoreBasedNCF, BehaviorGraphNCF, AdaptiveNCF):
            assert ncf_cls().name

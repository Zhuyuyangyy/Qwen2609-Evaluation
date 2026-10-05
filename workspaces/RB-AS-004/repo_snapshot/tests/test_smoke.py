"""
AgentShield V3 - Top-level Smoke Tests
========================================
Fast sanity checks that the backend package is importable and configured.
Run from project root: python -m pytest tests/test_smoke.py -v
"""

import sys
import importlib.util
from pathlib import Path

import pytest

# Ensure backend is importable
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


class TestBackendImports:
    """Verify all critical backend modules load without errors."""

    def test_import_v3_engine(self):
        from app.shield.v3_engine import V3ShieldEngine
        assert V3ShieldEngine is not None

    def test_import_behavior_graph(self):
        from app.shield.agent_behavior_graph import AgentBehaviorGraph
        assert AgentBehaviorGraph is not None

    def test_import_session_store(self):
        from app.shield.session_store import init_db, save_session, load_session
        assert callable(init_db)

    def test_import_audit_logger(self):
        from app.shield.v3_audit_logger import V3AuditLogger
        assert V3AuditLogger is not None

    def test_import_api_routes(self):
        from app.api.routes import router
        assert router.prefix == "/api/v3"

    def test_import_main_app(self):
        from app.main import app
        assert app.title == "AgentShield V3"


class TestStandaloneApp:
    """Verify the standalone app.py entry point loads correctly."""

    def test_standalone_app_importable(self):
        app_py = _BACKEND_DIR / "app.py"
        assert app_py.exists(), f"app.py not found at {app_py}"
        spec = importlib.util.spec_from_file_location("app_standalone", str(app_py))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "app")


class TestProjectFiles:
    """Verify essential project files exist."""

    def test_requirements_txt(self):
        assert (Path(__file__).resolve().parent.parent / "requirements.txt").exists()

    def test_dockerfile(self):
        assert (Path(__file__).resolve().parent.parent / "Dockerfile").exists()

    def test_pytest_ini(self):
        assert (Path(__file__).resolve().parent.parent / "pytest.ini").exists()

    def test_ci_workflow(self):
        assert (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml").exists()

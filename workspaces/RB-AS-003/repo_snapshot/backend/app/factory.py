"""Single FastAPI application factory for AgentShield V3.

Historically the project had **two independent FastAPI instances**:

* ``backend/app.py``      -- the standalone surface on port 8090
  (``/api/evaluate``, ``/api/agent/*``, ``/api/session*``), and
* ``backend/app/main.py`` -- the ``/api/v3/*`` router on port 8011.

Each kept its own middleware, CORS policy and (before the shared registry
landed) its own engine store, so a fix applied to one silently missed the
other.  Both files now build the *same* application through
:func:`build_app`, which means:

* one place for CORS, rate limiting and exception handling;
* one app object exposing both route surfaces at once;
* either entry point can be served on either port without losing routes.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import router as v3_router
from app.standalone_routes import limiter, standalone_router

# Cached application instance.  Both entry points (backend/app.py on 8090 and
# backend/app/main.py on 8011) call build_app(), and without this cache they
# would each construct a separate app object.
_APP: List[FastAPI] = []


def allowed_origins() -> List[str]:
    """CORS origins from ``ALLOWED_ORIGINS`` (comma-separated).

    ``allow_origins=["*"]`` combined with ``allow_credentials=True`` is
    rejected by browsers, so credentials silently never worked.  When unset
    we allow no cross-origin access rather than a broken wildcard.
    """
    return [
        origin.strip()
        for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]


def root_index() -> Dict[str, Any]:
    """Service index: version plus the available endpoint groups."""
    return {
        "message": "AgentShield V3 API",
        "docs": "/docs",
        "endpoints": {
            "process_call": "POST /api/v3/process_call",
            "status": "GET /api/v3/status/{session_id}",
            "fork_branch": "POST /api/v3/fork_branch",
            "export_chain": "GET /api/v3/export_chain/{session_id}",
            "behavior_graph": "GET /api/v3/behavior_graph/{session_id}",
            "simulate_steps": "POST /api/v3/simulate_steps",
            "evaluate": "POST /api/evaluate",
            "behavior_chain": "POST /api/agent/behavior_chain",
        },
    }


def health() -> Dict[str, Any]:
    """Liveness probe. Never rate limited (see app/standalone_routes.py)."""
    return {
        "status": "ok",
        "version": "3.0.0",
        "engine": "AgentShield_V3",
        "framework": "ASF-BGT",
        "port": 8090,
    }


def build_app() -> FastAPI:
    """Build (once) and return the unified AgentShield V3 application.

    The result is cached so ``backend/app.py`` and ``backend/app/main.py``
    share a single app object rather than each constructing their own.
    """
    if _APP:
        return _APP[0]

    application = FastAPI(
        title="AgentShield V3",
        description="多主体行为链风险治理系统 - ASF-BGT Framework",
        version="3.0.0",
    )

    application.state.limiter = limiter
    application.add_exception_handler(
        RateLimitExceeded, _rate_limit_exceeded_handler
    )

    origins = allowed_origins()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Credentials are only meaningful with an explicit origin list.
        allow_credentials=bool(origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared, un-prefixed routes.
    application.add_api_route("/", root_index, methods=["GET"])
    application.add_api_route("/health", health, methods=["GET"])

    # Both route surfaces on one app.
    application.include_router(standalone_router)
    application.include_router(v3_router)

    _APP.append(application)
    return application

"""
AgentShield V3 - FastAPI 主入口
端口：8011
继承 ASF-BGT Framework + V2 AgentBehaviorGraph
"""

import os
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import _ttl_manager
from app.api.routes import router as v3_router
from app.console.routes import router as console_router
from app.mcp.routes import router as mcp_router
from app.security.tenant import extract_tenant_from_request, set_current_tenant


def get_cors_origins() -> list[str]:
    """Get CORS origins from environment variable."""
    origins_str = os.environ.get("AGENTSHIELD_CORS_ORIGINS", "*")
    if origins_str == "*":
        return ["*"]
    return [o.strip() for o in origins_str.split(",") if o.strip()]


def cors_allows_credentials() -> bool:
    """Whether to send ``Access-Control-Allow-Credentials``.

    ``allow_origins=["*"]`` combined with ``allow_credentials=True`` is
    rejected by browsers, so credentials silently never worked.  They are only
    enabled when the origin list is explicit.
    """
    return "*" not in get_cors_origins()


app = FastAPI(
    title="AgentShield V3",
    description="多主体行为链风险治理系统 - 基于 ASF-BGT Framework",
    version="3.0.0",
)

# CORS - configurable via environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=cors_allows_credentials(),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Tenant context middleware
@app.middleware("http")
async def tenant_context_middleware(request: Request, call_next):
    """Extract and set tenant context for each request."""
    tenant_id = extract_tenant_from_request(request)
    set_current_tenant(tenant_id)
    response = await call_next(request)
    return response


# 注册 V3 路由
app.include_router(v3_router)

# 注册 Enterprise Console 路由
app.include_router(console_router)

# 注册 MCP Shield Proxy 路由
app.include_router(mcp_router)


@app.on_event("startup")
async def startup_event():
    """Run startup tasks."""
    # Initial TTL cleanup
    _ttl_manager.maybe_cleanup()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0.0",
        "engine": "AgentShield_V3",
        "framework": "ASF-BGT",
        "storage": os.environ.get("AGENTSHIELD_STORAGE", "memory"),
        "ttl_stats": _ttl_manager.get_stats(),
    }


@app.get("/")
async def root():
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
            "audit_records": "GET /api/v3/audit/records",
            "list_sessions": "GET /api/v3/sessions",
            "delete_session": "DELETE /api/v3/sessions/{session_id}",
        },
    }

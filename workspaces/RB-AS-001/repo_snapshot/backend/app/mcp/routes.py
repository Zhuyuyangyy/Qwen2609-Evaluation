"""AgentShield V3 - MCP Shield Proxy API Routes."""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.mcp.proxy import MCPShieldProxy, MCPToolDescriptor, MCPToolInvocation
from app.security.auth import verify_api_key

# ─── Request/Response Models ─────────────────────────────────────────────────

class RegisterToolRequest(BaseModel):
    server_id: str
    tool_name: str
    description: str
    input_schema: Dict[str, Any] = {}
    output_schema: Dict[str, Any] = {}
    annotations: Dict[str, Any] = {}


class InvokeToolRequest(BaseModel):
    client_id: str
    server_id: str
    tool_name: str
    arguments: Dict[str, Any] = {}
    auth_scope: List[str] = []
    user_context: Dict[str, Any] = {}
    session_id: str = ""


class ConsentRequest(BaseModel):
    client_id: str
    tool_name: str
    server_id: str
    granted: bool
    scope: List[str] = []


# ─── Proxy Store ──────────────────────────────────────────────────────────────

_proxy_store: Dict[str, MCPShieldProxy] = {}


def get_or_create_proxy(session_id: str) -> MCPShieldProxy:
    if session_id not in _proxy_store:
        _proxy_store[session_id] = MCPShieldProxy(session_id=session_id)
    return _proxy_store[session_id]


# ─── Router ───────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/mcp", tags=["MCP Shield Proxy"])


@router.post("/register_tool")
async def register_tool(
    req: RegisterToolRequest,
    identity: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Register an MCP tool descriptor for security scanning."""
    proxy = get_or_create_proxy("default")
    descriptor = MCPToolDescriptor(
        tool_name=req.tool_name,
        server_id=req.server_id,
        description=req.description,
        input_schema=req.input_schema,
        output_schema=req.output_schema,
        annotations=req.annotations,
    )
    decision = proxy.register_tool(descriptor)
    return decision.to_dict()


@router.post("/invoke")
async def invoke_tool(
    req: InvokeToolRequest,
    identity: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Evaluate an MCP tool invocation through the security proxy."""
    session_id = req.session_id or "default"
    proxy = get_or_create_proxy(session_id)

    invocation = MCPToolInvocation(
        client_id=req.client_id,
        server_id=req.server_id,
        tool_name=req.tool_name,
        arguments=req.arguments,
        auth_scope=req.auth_scope,
        user_context=req.user_context,
    )
    decision = proxy.evaluate_invocation(invocation)
    return decision.to_dict()


@router.post("/consent")
async def record_consent(
    req: ConsentRequest,
    identity: str = Depends(verify_api_key),
) -> Dict[str, str]:
    """Record a client's consent decision."""
    proxy = get_or_create_proxy("default")
    proxy.record_consent(
        client_id=req.client_id,
        tool_name=req.tool_name,
        server_id=req.server_id,
        granted=req.granted,
        scope=req.scope,
    )
    return {"status": "recorded"}


@router.get("/history/{session_id}")
async def get_invocation_history(
    session_id: str,
    limit: int = 50,
    identity: str = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get recent MCP invocation history."""
    if session_id not in _proxy_store:
        raise HTTPException(status_code=404, detail="Session not found")
    proxy = _proxy_store[session_id]
    return {
        "session_id": session_id,
        "invocations": proxy.get_invocation_history(limit=limit),
    }

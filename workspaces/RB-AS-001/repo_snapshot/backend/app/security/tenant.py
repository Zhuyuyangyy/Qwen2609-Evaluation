"""AgentShield V3 - Tenant Isolation.

Provides multi-tenant support for enterprise deployments.
Each tenant's sessions, policies, and data are isolated.

Configuration:
- AGENTSHIELD_TENANT_HEADER: Header name for tenant ID (default: X-Tenant-ID)
- AGENTSHIELD_DEFAULT_TENANT: Default tenant ID (default: default)
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Optional

from fastapi import Request

# Context variable for current tenant
_current_tenant: ContextVar[str] = ContextVar("current_tenant", default="default")

TENANT_HEADER = os.environ.get("AGENTSHIELD_TENANT_HEADER", "X-Tenant-ID")
DEFAULT_TENANT = os.environ.get("AGENTSHIELD_DEFAULT_TENANT", "default")


def get_current_tenant() -> str:
    """Get the current tenant ID from context."""
    return _current_tenant.get()


def set_current_tenant(tenant_id: str) -> None:
    """Set the current tenant ID in context."""
    _current_tenant.set(tenant_id)


def extract_tenant_from_request(request: Request) -> str:
    """Extract tenant ID from request headers."""
    tenant_id = request.headers.get(TENANT_HEADER, DEFAULT_TENANT)
    # Sanitize: only allow alphanumeric + hyphens + underscores
    sanitized = "".join(c for c in tenant_id if c.isalnum() or c in "-_")
    return sanitized if sanitized else DEFAULT_TENANT


class TenantContext:
    """Context manager for tenant-scoped operations."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self._token = None

    def __enter__(self):
        self._token = _current_tenant.set(self.tenant_id)
        return self

    def __exit__(self, *args):
        if self._token:
            _current_tenant.reset(self._token)


def tenant_scoped_key(session_id: str, tenant_id: Optional[str] = None) -> str:
    """Create a tenant-scoped key for storage.

    Format: tenant:{tenant_id}:session:{session_id}
    """
    tid = tenant_id or get_current_tenant()
    return f"tenant:{tid}:session:{session_id}"

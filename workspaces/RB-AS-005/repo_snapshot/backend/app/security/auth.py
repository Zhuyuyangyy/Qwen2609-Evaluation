"""AgentShield V3 - Authentication Middleware.

Supports:
- API Key authentication
- OAuth2 Bearer token (stub)
- mTLS (stub)

Configuration via environment variables:
- AGENTSHIELD_API_KEYS: Comma-separated list of valid API keys
- AGENTSHIELD_AUTH_DISABLED: Set to "true" to disable auth (dev only)
"""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

# ─── API Key Authentication ──────────────────────────────────────────────────

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
BEARER_SECURITY = HTTPBearer(auto_error=False)


def get_valid_api_keys() -> set[str]:
    """Get valid API keys from environment."""
    keys_str = os.environ.get("AGENTSHIELD_API_KEYS", "")
    if not keys_str:
        return set()
    return {k.strip() for k in keys_str.split(",") if k.strip()}


def is_auth_disabled() -> bool:
    """Check if authentication is disabled (development mode)."""
    return os.environ.get("AGENTSHIELD_AUTH_DISABLED", "").lower() == "true"


async def verify_api_key(
    request: Request,
    api_key: Optional[str] = Security(API_KEY_HEADER),
    bearer: Optional[HTTPAuthorizationCredentials] = Security(BEARER_SECURITY),
) -> str:
    """Verify API key or Bearer token.

    Returns the authenticated identity (API key prefix or token subject).

    Raises HTTPException 401 if authentication fails.
    """
    if is_auth_disabled():
        return "anonymous"

    valid_keys = get_valid_api_keys()

    # If no keys configured, allow all (backward compatible)
    if not valid_keys:
        return "anonymous"

    # Check API key header
    if api_key:
        if api_key in valid_keys:
            return f"key:{api_key[:8]}***"
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check Bearer token
    if bearer:
        # TODO: Implement proper OAuth2/JWT validation
        if bearer.credentials in valid_keys:
            return f"token:{bearer.credentials[:8]}***"
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    raise HTTPException(status_code=401, detail="Authentication required")


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"ash_{secrets.token_urlsafe(32)}"

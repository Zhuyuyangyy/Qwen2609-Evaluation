"""AgentShield V3 - Rate Limiting Configuration.

Per-tenant, per-agent, and per-tool rate limiting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    # Global limits
    global_rpm: int = 600  # requests per minute
    global_rph: int = 10000  # requests per hour

    # Per-tenant limits
    tenant_rpm: int = 200
    tenant_rph: int = 5000

    # Per-agent limits
    agent_rpm: int = 60
    agent_rph: int = 2000

    # Per-tool limits (tool_name -> rpm)
    tool_limits: Dict[str, int] = field(default_factory=lambda: {
        "send_email": 30,
        "http_request": 60,
        "execute_sql": 100,
        "export_csv": 20,
        "bulk_delete": 5,
    })

    # Review queue limits
    review_rpm: int = 30


def get_rate_limit_config() -> RateLimitConfig:
    """Load rate limit config from environment variables."""
    return RateLimitConfig(
        global_rpm=int(os.environ.get("AGENTSHIELD_GLOBAL_RPM", "600")),
        global_rph=int(os.environ.get("AGENTSHIELD_GLOBAL_RPH", "10000")),
        tenant_rpm=int(os.environ.get("AGENTSHIELD_TENANT_RPM", "200")),
        tenant_rph=int(os.environ.get("AGENTSHIELD_TENANT_RPH", "5000")),
        agent_rpm=int(os.environ.get("AGENTSHIELD_AGENT_RPM", "60")),
        agent_rph=int(os.environ.get("AGENTSHIELD_AGENT_RPH", "2000")),
    )

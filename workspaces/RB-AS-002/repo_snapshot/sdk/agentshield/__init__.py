"""AgentShield SDK - Python client for the AgentShield V3 governance API.

Usage:
    from agentshield import Shield

    shield = Shield(project="finance-agent")

    decision = shield.evaluate_tool_call(
        agent_id="analyst_agent",
        tool_name="send_email",
        arguments={"to": "external@example.com", "body": "..."},
    )

    if decision.blocked:
        raise SecurityException(decision.reason)
"""

from agentshield.client import Shield, ShieldDecision, SecurityException

__version__ = "0.3.0"
__all__ = ["Shield", "ShieldDecision", "SecurityException"]

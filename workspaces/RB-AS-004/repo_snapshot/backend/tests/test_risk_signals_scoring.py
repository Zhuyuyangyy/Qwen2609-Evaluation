"""Regression tests for signal-derived risk scoring.

These pin the governance behaviour that regressed when the engine moved to
signal-derived risk: destructive operations must be blocked, ordinary traffic
must be allowed, and the score must not depend on how much other traffic shares
the session.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


def _assess(tool_name: str, params: dict, supplied: float = 0.0):
    """Run one tool call through a fresh engine and return the gate result."""
    from app.shield.v3_engine import V3ShieldEngine

    engine = V3ShieldEngine(session_id=f"sig_{tool_name}_{len(params)}")
    result = engine.process_tool_call(
        agent_id="agent",
        tool_name=tool_name,
        params=params,
        risk_score=supplied,
        fuse_action="allow",
    )
    return result, engine


class TestDestructiveOperationsAreBlocked:
    @pytest.mark.parametrize(
        "tool_name,params",
        [
            ("shell", {"cmd": "rm -rf / --no-preserve-root"}),
            ("execute_sql", {"query": "DROP TABLE customers"}),
            ("execute_sql", {"query": "DROP DATABASE production"}),
            ("execute_sql", {"query": "DELETE FROM customers"}),
            ("execute_sql", {"query": "DELETE FROM audit_log"}),
            ("shell", {"cmd": "truncate -s 0 /var/log/syslog"}),
        ],
    )
    def test_unbounded_destruction_blocks(self, tool_name, params):
        result, _ = _assess(tool_name, params)
        assert result["gate_result"]["action"] == "BLOCK"
        assert result["gate_result"]["score"] >= 0.90


class TestOrdinaryOperationsAreAllowed:
    @pytest.mark.parametrize(
        "tool_name,params",
        [
            ("execute_sql", {"query": "SELECT 1"}),
            ("read_file", {"path": "/tmp/notes.txt"}),
            ("send_email", {"to": "team@internal.com", "body": "weekly report"}),
            ("generate_reports", {"report_type": "quarterly_financial", "count": 500}),
        ],
    )
    def test_benign_traffic_allows(self, tool_name, params):
        result, _ = _assess(tool_name, params)
        assert result["gate_result"]["action"] == "ALLOW"


class TestSensitiveAccessIsReviewed:
    @pytest.mark.parametrize(
        "tool_name,params",
        [
            ("execute_sql", {"query": "SELECT phone FROM customers"}),
            ("execute_sql", {"query": "SELECT name, phone, id_card FROM customers"}),
            ("read_file", {"path": "/etc/passwd"}),
            ("send_email", {"to": "evil@gmail.com", "body": "customer data"}),
        ],
    )
    def test_sensitive_access_is_not_allowed(self, tool_name, params):
        result, _ = _assess(tool_name, params)
        assert result["gate_result"]["action"] != "ALLOW"


class TestInternalVersusExternalRecipients:
    def test_internal_recipient_is_not_an_external_sink(self):
        from app.shield.risk_extractor import RiskSignalExtractor

        assert RiskSignalExtractor._looks_internal_only(
            str({"to": "team@internal.com"}).lower()
        )

    def test_consumer_mail_is_external(self):
        from app.shield.risk_extractor import RiskSignalExtractor

        assert not RiskSignalExtractor._looks_internal_only(
            str({"to": "someone@gmail.com"}).lower()
        )

    def test_no_recipient_is_not_assumed_safe(self):
        from app.shield.risk_extractor import RiskSignalExtractor

        assert not RiskSignalExtractor._looks_internal_only(str({"cmd": "curl x"}).lower())


class TestCombinedRiskProperties:
    def test_equal_components_return_that_value(self):
        """The invariant test_api_routes._make_risk_state relies on."""
        from app.shield.risk_signals import GraphRiskState

        for x in (0.0, 0.3, 0.6, 0.9, 1.0):
            state = GraphRiskState(
                local_risk=x,
                inherited_risk=x,
                path_risk=x,
                downstream_exposure=x,
                intervention_value=x,
                confidence=1.0,
            )
            assert state.combined_risk == pytest.approx(x)

    def test_no_signals_means_zero(self):
        from app.shield.risk_signals import GraphRiskState

        state = GraphRiskState(confidence=0.0)
        assert state.combined_risk == 0.0

    def test_single_decisive_signal_is_not_diluted(self):
        """A strong signal with all other components zero keeps its value."""
        from app.shield.risk_signals import GraphRiskState

        state = GraphRiskState(local_risk=0.9, confidence=0.6)
        assert state.combined_risk == pytest.approx(0.9)

    def test_confidence_does_not_reduce_score(self):
        from app.shield.risk_signals import GraphRiskState

        high = GraphRiskState(local_risk=0.8, confidence=1.0)
        low = GraphRiskState(local_risk=0.8, confidence=0.5)
        assert high.combined_risk == low.combined_risk


class TestExternalScoreCannotDilute:
    def test_supplied_score_only_raises_the_result(self):
        result, _ = _assess("execute_sql", {"query": "SELECT 1"}, supplied=0.95)
        assert result["gate_result"]["score"] >= 0.90
        assert result["gate_result"]["action"] == "BLOCK"

    def test_signal_can_exceed_supplied_score(self):
        result, _ = _assess("shell", {"cmd": "rm -rf /"}, supplied=0.1)
        assert result["gate_result"]["score"] >= 0.90


class TestSessionIsolation:
    def test_prior_traffic_does_not_change_a_later_verdict(self):
        """A benign call must score the same whether or not it follows abuse."""
        from app.shield.v3_engine import V3ShieldEngine

        # Fresh session.
        alone = V3ShieldEngine(session_id="iso_alone")
        solo = alone.process_tool_call(
            agent_id="a", tool_name="execute_sql",
            params={"query": "SELECT 1"}, risk_score=0.0, fuse_action="allow",
        )

        # Same call after a destructive one in the same session.
        shared = V3ShieldEngine(session_id="iso_shared")
        shared.process_tool_call(
            agent_id="a", tool_name="shell",
            params={"cmd": "rm -rf /"}, risk_score=0.0, fuse_action="allow",
        )
        after = shared.process_tool_call(
            agent_id="a", tool_name="execute_sql",
            params={"query": "SELECT 1"}, risk_score=0.0, fuse_action="allow",
        )

        assert after["gate_result"]["action"] == solo["gate_result"]["action"] == "ALLOW"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

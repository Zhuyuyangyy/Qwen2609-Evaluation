"""Public checks for RB-AS-002.

No answer here. What is public is the contract that must survive a fix:

* a session registers and reports its metadata,
* the recorded TTL is what the expiry check consults,
* omitting the TTL still yields the manager default, and
* explicitly passing the default still behaves like omitting it.

All of them hold on the shipped snapshot -- the defect only shows up when a
caller passes an explicit non-default TTL, which is exactly what the hidden
checks exercise.
"""

from __future__ import annotations

import sys
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parents[1] / "repo_snapshot"
sys.path.insert(0, str(SNAPSHOT / "backend"))

from app.shield.session_ttl import SessionTTLManager  # noqa: E402


def test_register_returns_metadata_for_the_session():
    m = SessionTTLManager(default_ttl=100)
    meta = m.register_session("s1")
    assert meta is not None
    assert meta.session_id == "s1"
    assert meta.ttl_seconds > 0


def test_recorded_ttl_matches_the_default_when_none_given():
    m = SessionTTLManager(default_ttl=123)
    meta = m.register_session("s1")
    assert meta.ttl_seconds == 123


def test_expiry_uses_the_recorded_ttl():
    """The recorded value is the one the expiry check must consult.

    Asserted on the metadata/expiry agreement rather than on a specific
    propagation path, so a fix that restructures how the value is stored is
    still acceptable as long as the two agree.
    """
    m = SessionTTLManager(default_ttl=50)
    meta = m.register_session("s1")
    remaining = meta.remaining_seconds
    assert 0.0 <= remaining <= 50.0
    assert (remaining > 0) == (not meta.is_expired)


def test_explicit_default_equals_omitted():
    """Passing the default explicitly is the same as passing nothing."""
    a = SessionTTLManager(default_ttl=200).register_session("s", ttl_seconds=None)
    b = SessionTTLManager(default_ttl=200).register_session("s", ttl_seconds=200)
    assert a.ttl_seconds == b.ttl_seconds


def test_public_api_is_intact():
    m = SessionTTLManager()
    for name in ("register_session", "touch_session", "get_session",
                 "remove_session", "get_expired_sessions", "maybe_cleanup"):
        assert hasattr(m, name), f"missing public method {name}"


def test_environment_default_still_applies():
    """The documented env-var default must keep working."""
    assert SessionTTLManager.DEFAULT_TTL > 0
    m = SessionTTLManager()
    meta = m.register_session("s-env")
    assert meta.ttl_seconds == SessionTTLManager.DEFAULT_TTL

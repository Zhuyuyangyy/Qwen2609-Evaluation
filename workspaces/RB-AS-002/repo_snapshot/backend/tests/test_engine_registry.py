"""Tests for the shared V3 engine registry.

The registry is the single source of truth for session -> engine mappings and
is shared by both API entry points.  These tests cover its lifecycle
guarantees: one engine per session, restoration, drop, and the eviction
policy (TTL + LRU capacity cap) that keeps it from leaking memory.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@pytest.fixture(autouse=True)
def _clean_registry():
    """Isolate registry state and env between tests."""
    from app import engine_registry as er

    er.reset_registry()
    saved = (er.SESSION_TTL_SECONDS, er.MAX_ACTIVE_SESSIONS)
    er.SESSION_TTL_SECONDS = 0
    er.MAX_ACTIVE_SESSIONS = 0
    yield er
    er.reset_registry()
    er.SESSION_TTL_SECONDS, er.MAX_ACTIVE_SESSIONS = saved


class TestEngineIdentity:
    def test_same_session_returns_same_engine(self, _clean_registry):
        er = _clean_registry
        first = er.get_or_create_engine("s1")
        second = er.get_or_create_engine("s1")
        assert first is second

    def test_distinct_sessions_get_distinct_engines(self, _clean_registry):
        er = _clean_registry
        assert er.get_or_create_engine("a") is not er.get_or_create_engine("b")

    def test_engines_carry_their_session_id(self, _clean_registry):
        er = _clean_registry
        assert er.get_or_create_engine("s1").session_id == "s1"

    def test_drop_removes_session(self, _clean_registry):
        er = _clean_registry
        er.get_or_create_engine("s1")
        assert er.drop_engine("s1") is True
        assert er.get_existing_engine("s1") is None
        # Dropping twice is a no-op, not an error.
        assert er.drop_engine("s1") is False


class TestLookupDoesNotCreate:
    """Read-only lookups must not materialise or restore engines."""

    def test_missing_session_returns_none(self, _clean_registry):
        er = _clean_registry
        assert er.get_existing_engine("nope") is None

    def test_lookup_does_not_create(self, _clean_registry):
        er = _clean_registry
        er.get_existing_engine("ghost")
        assert er.active_session_count() == 0

    def test_lookup_refreshes_recency(self, _clean_registry):
        er = _clean_registry
        er.get_or_create_engine("a")
        before = er._last_access["a"]
        time.sleep(0.05)
        er.get_existing_engine("a")
        assert er._last_access["a"] > before


class TestEviction:
    def test_capacity_cap_is_enforced(self, _clean_registry):
        er = _clean_registry
        er.MAX_ACTIVE_SESSIONS = 3
        for i in range(10):
            er.get_or_create_engine(f"s{i}")
        assert er.active_session_count() == 3

    def test_capacity_evicts_least_recently_used(self, _clean_registry):
        er = _clean_registry
        er.MAX_ACTIVE_SESSIONS = 3
        for name in ("a", "b", "c"):
            er.get_or_create_engine(name)
        # A real gap so monotonic timestamps differ measurably.
        time.sleep(0.05)
        # Touch "a" so that "b" becomes the least-recently-used.
        er.get_existing_engine("a")
        er.get_or_create_engine("d")

        assert er.get_existing_engine("b") is None   # evicted (LRU)
        assert er.get_existing_engine("a") is not None  # refreshed, kept
        assert er.get_existing_engine("d") is not None  # newest, kept

    def test_zero_capacity_disables_eviction(self, _clean_registry):
        er = _clean_registry
        er.MAX_ACTIVE_SESSIONS = 0
        for i in range(20):
            er.get_or_create_engine(f"s{i}")
        assert er.active_session_count() == 20

    def test_ttl_expires_idle_sessions(self, _clean_registry):
        er = _clean_registry
        er.SESSION_TTL_SECONDS = 0.05
        er.get_or_create_engine("ttl")
        assert er.active_session_count() == 1

        time.sleep(0.12)
        er._evict_if_needed()
        assert er.active_session_count() == 0

    def test_ttl_does_not_expire_active_sessions(self, _clean_registry):
        er = _clean_registry
        er.SESSION_TTL_SECONDS = 0.08
        er.get_or_create_engine("live")
        for _ in range(6):
            time.sleep(0.03)
            er.get_existing_engine("live")  # keeps it alive
        er._evict_if_needed()
        assert er.get_existing_engine("live") is not None

    def test_zero_ttl_disables_expiry(self, _clean_registry):
        er = _clean_registry
        er.SESSION_TTL_SECONDS = 0
        er.get_or_create_engine("forever")
        time.sleep(0.05)
        er._evict_if_needed()
        assert er.get_existing_engine("forever") is not None


class TestRegistryStats:
    def test_stats_reflect_configuration(self, _clean_registry):
        er = _clean_registry
        er.MAX_ACTIVE_SESSIONS = 7
        er.SESSION_TTL_SECONDS = 123.0
        stats = er.registry_stats()
        assert stats == {
            "active_sessions": 0,
            "ttl_seconds": 123.0,
            "max_sessions": 7,
        }

    def test_stats_count_matches_active(self, _clean_registry):
        er = _clean_registry
        er.get_or_create_engine("a")
        er.get_or_create_engine("b")
        assert er.registry_stats()["active_sessions"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

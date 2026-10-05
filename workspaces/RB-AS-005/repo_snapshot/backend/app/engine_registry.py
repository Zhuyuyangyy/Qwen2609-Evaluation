"""Shared V3 engine registry.

Single source of truth for session -> engine mapping.  Previously the
standalone app (``backend/app.py``) and the ``/api/v3/*`` router
(``app/api/routes.py``) each kept their own ``_engine_store``, which meant the
same ``session_id`` resolved to two independent engines depending on which
entry point handled the request -- silently splitting behavior graphs and
audit chains for one logical session.

Both entry points now delegate here, so a session has exactly one engine
regardless of which API surface touches it first.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# session_id -> V3ShieldEngine.  Guarded by ``_registry_lock`` because FastAPI
# serves requests concurrently on the event loop, and the TTL sweep may run on
# a background thread.
_engine_store: Dict[str, Any] = {}
# session_id -> last-touched monotonic timestamp.
_last_access: Dict[str, float] = {}
_registry_lock = threading.Lock()

# Defaults kept in one place so both entry points behave identically.
DEFAULT_RISK_THRESHOLD = 0.70
DEFAULT_MAX_BRANCHES = 5
DEFAULT_ENABLE_COUNTERFACTUAL = True

# ─── Eviction policy ────────────────────────────────────────────────────────
# Every engine holds its whole behavior graph plus audit chain in memory.  An
# unbounded registry is therefore a slow memory leak: each new session_id
# (including random UUIDs from clients that never reuse them) pins memory
# forever.  Two guards:
#   * TTL      -- sessions idle for longer than this are dropped.
#   * capacity -- when full, the least-recently-used session is dropped.
# Both are configurable; TTL <= 0 disables expiry.
SESSION_TTL_SECONDS = float(os.environ.get("SHIELD_SESSION_TTL", "1800"))
MAX_ACTIVE_SESSIONS = int(os.environ.get("SHIELD_MAX_SESSIONS", "256"))


def _world_name(session_id: str) -> str:
    return f"V3Shield_{session_id[:8]}"


def _build_engine(session_id: str, **overrides: Any) -> Any:
    """Instantiate a V3ShieldEngine, tolerating a missing engine module."""
    from app.shield.v3_engine import V3ShieldEngine

    return V3ShieldEngine(
        session_id=session_id,
        world_name=_world_name(session_id),
        risk_threshold=overrides.get("risk_threshold", DEFAULT_RISK_THRESHOLD),
        max_branches=overrides.get("max_branches", DEFAULT_MAX_BRANCHES),
        enable_counterfactual=overrides.get(
            "enable_counterfactual", DEFAULT_ENABLE_COUNTERFACTUAL
        ),
    )


def _dummy_engine(session_id: str) -> Any:
    """Fail-closed stand-in used when the real engine cannot be imported."""

    class DummyEngine:
        def __init__(self, session_id: str):
            self.session_id = session_id
            self.behavior_graph = self

        def process_tool_call(self, **kwargs):
            return {
                "node_id": str(uuid.uuid4()),
                "session_id": session_id,
                "decision": "block",
                "risk_level": "high",
                "risk_score": 0.9,
                "reasoning": "DummyEngine fallback (v3_engine not found)",
            }

        def get_governance_status(self):
            return {
                "session_id": self.session_id,
                "engine_id": "DummyEngine",
                "risk_threshold": DEFAULT_RISK_THRESHOLD,
                "branch_count": 0,
                "gate_count": 0,
                "behavior_graph": {},
            }

    return DummyEngine(session_id)


def _restore_from_db(session_id: str) -> Optional[Any]:
    """Rebuild an engine from the SQLite snapshot, if one exists."""
    try:
        from app.shield.session_store import load_session

        saved = load_session(session_id)
    except Exception:
        logger.debug("Session restore failed for %s", session_id, exc_info=True)
        return None

    if not saved:
        return None

    state = saved.get("state_data") or {}
    try:
        engine = _build_engine(
            session_id=session_id,
            risk_threshold=state.get("risk_threshold", DEFAULT_RISK_THRESHOLD),
            max_branches=state.get("max_branches", DEFAULT_MAX_BRANCHES),
            enable_counterfactual=state.get(
                "enable_counterfactual", DEFAULT_ENABLE_COUNTERFACTUAL
            ),
        )
    except ImportError:
        return None

    if isinstance(saved.get("world_name"), str) and saved["world_name"]:
        engine.world.name = saved["world_name"]
    return engine


def get_or_create_engine(session_id: str) -> Any:
    """Return the single engine for ``session_id``, restoring or creating it."""
    with _registry_lock:
        engine = _engine_store.get(session_id)
        if engine is not None:
            _last_access[session_id] = time.monotonic()
            return engine

    engine = _restore_from_db(session_id)
    if engine is None:
        try:
            engine = _build_engine(session_id=session_id)
        except ImportError:
            logger.warning("v3_engine unavailable; using fail-closed fallback")
            engine = _dummy_engine(session_id)

    with _registry_lock:
        _engine_store[session_id] = engine
        _last_access[session_id] = time.monotonic()
        # Enforce the cap *after* inserting, otherwise the newest session can
        # push the registry one over its limit.
        _evict_locked()
    return engine


def get_existing_engine(session_id: str) -> Optional[Any]:
    """Look up an already-live engine without creating or restoring one."""
    with _registry_lock:
        engine = _engine_store.get(session_id)
        if engine is not None:
            _last_access[session_id] = time.monotonic()
        return engine


def drop_engine(session_id: str) -> bool:
    """Remove a session from the in-memory registry."""
    with _registry_lock:
        existed = _engine_store.pop(session_id, None) is not None
        _last_access.pop(session_id, None)
        return existed


def active_session_count() -> int:
    """Number of engines currently held in memory."""
    with _registry_lock:
        return len(_engine_store)


# ─── Eviction ───────────────────────────────────────────────────────────────

def _evict_if_needed() -> None:
    """Drop idle sessions, then enforce the capacity cap (LRU)."""
    with _registry_lock:
        _evict_locked()


def _evict_locked() -> None:
    """Eviction logic; caller must already hold ``_registry_lock``."""
    now = time.monotonic()

    if SESSION_TTL_SECONDS > 0:
        expired = [
            sid
            for sid, seen in _last_access.items()
            if now - seen > SESSION_TTL_SECONDS
        ]
        for sid in expired:
            _engine_store.pop(sid, None)
            _last_access.pop(sid, None)
        if expired:
            logger.debug("Evicted %d idle session(s) past TTL", len(expired))

    if MAX_ACTIVE_SESSIONS > 0 and len(_engine_store) > MAX_ACTIVE_SESSIONS:
        # Least-recently-used first.
        victims = sorted(_last_access.items(), key=lambda kv: kv[1])
        excess = len(_engine_store) - MAX_ACTIVE_SESSIONS
        for sid, _ in victims[:excess]:
            _engine_store.pop(sid, None)
            _last_access.pop(sid, None)
        logger.debug(
            "Evicted %d session(s) over capacity %d", excess, MAX_ACTIVE_SESSIONS
        )


def registry_stats() -> Dict[str, Any]:
    """Introspection for /health_detailed and tests."""
    with _registry_lock:
        return {
            "active_sessions": len(_engine_store),
            "ttl_seconds": SESSION_TTL_SECONDS,
            "max_sessions": MAX_ACTIVE_SESSIONS,
        }


def reset_registry() -> None:
    """Clear all in-memory state (used by tests)."""
    with _registry_lock:
        _engine_store.clear()
        _last_access.clear()

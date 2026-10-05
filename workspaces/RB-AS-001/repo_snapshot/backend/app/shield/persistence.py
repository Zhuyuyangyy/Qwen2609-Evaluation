"""Non-blocking SQLite persistence for V3 engine sessions.

Every ``process_tool_call`` used to serialise the full behavior graph plus the
whole audit chain and write it to SQLite *synchronously on the event loop*.
That blocked the loop for the duration of the write and grew with session
length.

This module makes persistence:

* **debounced** -- concurrent requests for one session collapse into a single
  write of the latest snapshot, and a write in flight is followed by one
  catch-up write if newer state arrived meanwhile;
* **off-loop** -- the actual ``sqlite3`` calls run on a small thread pool;
* **best-effort** -- a failed write never fails the request.

Both API entry points (``backend/app.py`` on port 8090 and the ``/api/v3/*``
router) import this module.  It deliberately lives outside ``app.py`` because
``app`` is a package name and importing a sibling module from it is ambiguous.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# session_id -> [engine, version].  The version counter increments on every
# request so a completed write can tell whether newer state arrived while it
# was running.
_pending_saves: Dict[str, list] = {}
# session_id -> version that has been successfully persisted.
_saved_version: Dict[str, int] = {}
# Sessions with a write currently in flight (never two writers per session).
_inflight_saves: set[str] = set()
_registry_lock = threading.Lock()

# sqlite3 is synchronous; keep it off the event loop.
_DB_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="shield-db")


def save_engine_state(session_id: str, engine: Any) -> None:
    """Persist ``engine`` for ``session_id`` without blocking the caller.

    In an async context the write is scheduled on a thread pool; elsewhere it
    happens synchronously.  Repeated calls for the same session are debounced.
    """
    with _registry_lock:
        version = _pending_saves[session_id][1] + 1 if session_id in _pending_saves else 1
        _pending_saves[session_id] = [engine, version]

        if session_id in _inflight_saves:
            return  # a write is running; its completion callback catches up
        _inflight_saves.add(session_id)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Synchronous context (e.g. tests): write inline.
        _flush(session_id)
        return

    try:
        loop.run_in_executor(_DB_EXECUTOR, _flush, session_id).add_done_callback(
            _make_save_callback(session_id)
        )
    except Exception:
        logger.warning("Could not schedule session save for %s", session_id, exc_info=True)
        with _registry_lock:
            _inflight_saves.discard(session_id)


def _make_save_callback(session_id: str):
    """Build the completion callback for a session save.

    A named factory rather than an inline lambda: mypy cannot infer the
    parameter types of a lambda passed straight to ``add_done_callback``.
    """

    def _callback(fut) -> None:
        _on_flush_done(fut, session_id)

    return _callback


def _on_flush_done(fut, session_id: str) -> None:
    """A write finished: clean up, then catch up if newer state arrived.

    Runs on the executor thread where there is no running event loop, so the
    catch-up write is performed inline (still off the loop) rather than being
    resubmitted to the executor.
    """
    with _registry_lock:
        _inflight_saves.discard(session_id)
        try:
            fut.result()
        except Exception:
            logger.warning("SQLite session save failed for %s", session_id, exc_info=True)

    # Outside the lock: drain until the persisted version matches the newest
    # requested one.  Normally this is zero or one extra write.
    while True:
        with _registry_lock:
            pending_version = _pending_saves.get(session_id, [None, None])[1]
            if pending_version is None or pending_version == _saved_version.get(session_id):
                _pending_saves.pop(session_id, None)
                _inflight_saves.discard(session_id)
                return
            _inflight_saves.add(session_id)
        _flush(session_id)


def _flush(session_id: str) -> None:
    """Actual SQLite write; runs on the thread pool."""
    with _registry_lock:
        entry = _pending_saves.get(session_id)
    if entry is None:
        return
    engine, version = entry

    try:
        from app.shield.session_store import save_session

        state_data = {
            "risk_threshold": getattr(engine, "risk_threshold", 0.70),
            "max_branches": getattr(engine, "max_branches", 5),
            "enable_counterfactual": getattr(engine, "enable_counterfactual", True),
            "engine_id": getattr(engine, "engine_id", ""),
            "gate_count": getattr(engine, "_gate_count", 0),
        }

        graph_data = {}
        graph = getattr(engine, "behavior_graph", None)
        if graph is not None and hasattr(graph, "to_graph_dict"):
            graph_data = graph.to_graph_dict()

        audit_data: List[Any] = []
        audit = getattr(engine, "audit_logger", None)
        if audit is not None and hasattr(audit, "export_chain"):
            audit_data = audit.export_chain()

        save_session(
            session_id=session_id,
            engine_id=getattr(engine, "engine_id", "unknown"),
            world_name=getattr(engine, "world_name", "V3Shield"),
            state_data=state_data,
            graph_data=graph_data,
            audit_data=audit_data,
        )
        with _registry_lock:
            _saved_version[session_id] = version
    except Exception:
        logger.warning("SQLite session save failed for %s", session_id, exc_info=True)


async def drain_async(timeout: float = 10.0) -> None:
    """Await until queued writes settle.

    ``add_done_callback`` continuations only run when the event loop gets
    control, so an async caller must ``await`` this instead of sleeping.
    """
    import time as _time

    deadline = _time.monotonic() + timeout
    while _time.monotonic() < deadline:
        if not inflight_count() and not pending_count():
            return
        await asyncio.sleep(0.01)
    _drain_blocking()


def drain() -> None:
    """Wait until queued writes settle (sync callers and shutdown).

    Async code should prefer :func:`drain_async`, which yields to the loop so
    the write-completion callbacks can actually run.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        _drain_blocking()
        return
    # A loop is running: we cannot block it here.  Queue state is drained by
    # the callbacks themselves; callers that must guarantee completion should
    # await drain_async() instead.
    return


def _drain_blocking() -> None:
    import time as _time

    for _ in range(500):
        with _registry_lock:
            if not _inflight_saves and not _pending_saves:
                return
        _time.sleep(0.02)


def pending_count() -> int:
    """Number of sessions with state not yet persisted."""
    with _registry_lock:
        return len(_pending_saves)


def inflight_count() -> int:
    """Number of writes currently running."""
    with _registry_lock:
        return len(_inflight_saves)


def reset() -> None:
    """Clear all queue state (used by tests)."""
    with _registry_lock:
        _pending_saves.clear()
        _saved_version.clear()
        _inflight_saves.clear()

"""AgentShield V3 - Session TTL Manager.

Manages session lifecycle with automatic expiration and cleanup.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SessionMetadata:
    """Metadata for tracking session lifecycle."""
    session_id: str
    tenant_id: str
    created_at: float
    last_accessed: float
    ttl_seconds: int
    engine_id: str = ""

    @property
    def is_expired(self) -> bool:
        return time.time() - self.last_accessed > self.ttl_seconds

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.ttl_seconds - (time.time() - self.last_accessed))


class SessionTTLManager:
    """Manages session TTL and cleanup.

    Sessions that exceed their TTL are automatically cleaned up.
    """

    DEFAULT_TTL = int(os.environ.get("AGENTSHIELD_SESSION_TTL", "86400"))  # 24 hours
    CLEANUP_INTERVAL = int(os.environ.get("AGENTSHIELD_CLEANUP_INTERVAL", "300"))  # 5 minutes

    def __init__(
        self,
        default_ttl: Optional[int] = None,
        cleanup_callback: Optional[Callable[[str], None]] = None,
    ):
        self.default_ttl = default_ttl or self.DEFAULT_TTL
        self.cleanup_callback = cleanup_callback
        self._sessions: Dict[str, SessionMetadata] = {}
        self._last_cleanup = time.time()

    def register_session(
        self,
        session_id: str,
        tenant_id: str = "default",
        ttl_seconds: Optional[int] = None,
        engine_id: str = "",
    ) -> SessionMetadata:
        """Register a new session for TTL tracking."""
        now = time.time()
        meta = SessionMetadata(
            session_id=session_id,
            tenant_id=tenant_id,
            created_at=now,
            last_accessed=now,
            ttl_seconds=ttl_seconds or self.default_ttl,
            engine_id=engine_id,
        )
        self._sessions[session_id] = meta
        return meta

    def touch_session(self, session_id: str) -> Optional[SessionMetadata]:
        """Update last accessed time for a session."""
        meta = self._sessions.get(session_id)
        if meta:
            meta.last_accessed = time.time()
        return meta

    def get_session(self, session_id: str) -> Optional[SessionMetadata]:
        """Get session metadata, checking for expiration."""
        meta = self._sessions.get(session_id)
        if meta and meta.is_expired:
            self._cleanup_session(session_id)
            return None
        return meta

    def remove_session(self, session_id: str) -> bool:
        """Remove a session from tracking."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def get_expired_sessions(self) -> List[SessionMetadata]:
        """Get all expired sessions."""
        return [m for m in self._sessions.values() if m.is_expired]

    def maybe_cleanup(self) -> int:
        """Run cleanup if interval has elapsed. Returns number of cleaned sessions."""
        now = time.time()
        if now - self._last_cleanup < self.CLEANUP_INTERVAL:
            return 0

        self._last_cleanup = now
        expired = self.get_expired_sessions()
        for meta in expired:
            self._cleanup_session(meta.session_id)
        return len(expired)

    def _cleanup_session(self, session_id: str) -> None:
        """Clean up a single expired session."""
        self._sessions.pop(session_id, None)
        if self.cleanup_callback:
            try:
                self.cleanup_callback(session_id)
            except Exception:
                # A failing cleanup callback must not abort the whole sweep,
                # but silently swallowing it hides broken cleanup. Log and move
                # on to the next session.
                logger.exception("Session cleanup callback failed for %s", session_id)

    def get_active_count(self) -> int:
        """Get number of active (non-expired) sessions."""
        return len([m for m in self._sessions.values() if not m.is_expired])

    def get_stats(self) -> Dict[str, int]:
        """Get session statistics."""
        total = len(self._sessions)
        active = len([m for m in self._sessions.values() if not m.is_expired])
        expired = total - active
        return {"total": total, "active": active, "expired": expired}

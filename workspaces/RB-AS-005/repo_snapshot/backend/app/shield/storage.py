"""AgentShield V3 - Production Storage Backend.

Replaces the in-memory _engine_store dict with a proper storage layer
that supports multiple backends (memory, Redis, PostgreSQL).

Usage:
    store = get_storage()  # Auto-detect from environment
    store.save_session(session_id, engine_state)
    store.load_session(session_id)
    store.list_sessions()
    store.delete_session(session_id)
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def save_session(self, session_id: str, state: Dict[str, Any]) -> None:
        ...

    @abstractmethod
    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        ...

    @abstractmethod
    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        ...

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        ...

    @abstractmethod
    def session_exists(self, session_id: str) -> bool:
        ...


class MemoryStorage(StorageBackend):
    """In-memory storage (for development and testing)."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def save_session(self, session_id: str, state: Dict[str, Any]) -> None:
        state["_updated_at"] = time.time()
        self._store[session_id] = state

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(session_id)

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        sessions = sorted(
            self._store.values(),
            key=lambda s: s.get("_updated_at", 0),
            reverse=True,
        )
        return sessions[:limit]

    def delete_session(self, session_id: str) -> bool:
        if session_id in self._store:
            del self._store[session_id]
            return True
        return False

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._store


class SQLiteStorage(StorageBackend):
    """SQLite-based persistent storage."""

    def __init__(self, db_path: str = "agentshield_sessions.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                tenant_id TEXT DEFAULT 'default'
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_updated
            ON sessions(updated_at DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_tenant
            ON sessions(tenant_id)
        """)
        conn.commit()
        conn.close()

    def save_session(self, session_id: str, state: Dict[str, Any]) -> None:
        import sqlite3
        state_json = json.dumps(state, default=str, ensure_ascii=False)
        now = time.time()
        tenant_id = state.get("tenant_id", "default")

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO sessions (session_id, state_json, created_at, updated_at, tenant_id)
            VALUES (?, ?, COALESCE((SELECT created_at FROM sessions WHERE session_id = ?), ?), ?, ?)
        """, (session_id, state_json, session_id, now, now, tenant_id))
        conn.commit()
        conn.close()

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?", (session_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
        return None

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT state_json FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        results = [json.loads(row[0]) for row in cursor.fetchall()]
        conn.close()
        return results

    def delete_session(self, session_id: str) -> bool:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "DELETE FROM sessions WHERE session_id = ?", (session_id,)
        )
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def session_exists(self, session_id: str) -> bool:
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        )
        exists = cursor.fetchone() is not None
        conn.close()
        return exists


class RedisStorage(StorageBackend):
    """Redis-based storage (for production)."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        prefix: str = "agentshield:session:",
        ttl: int = 86400,  # 24 hours default TTL
    ):
        self.redis_url = redis_url
        self.prefix = prefix
        self.ttl = ttl
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import redis
                self._client = redis.from_url(self.redis_url)
            except ImportError as err:
                raise ImportError(
                    "Redis storage requires the 'redis' package. "
                    "Install with: pip install redis"
                ) from err
        return self._client

    def _key(self, session_id: str) -> str:
        return f"{self.prefix}{session_id}"

    def save_session(self, session_id: str, state: Dict[str, Any]) -> None:
        state_json = json.dumps(state, default=str, ensure_ascii=False)
        self.client.setex(self._key(session_id), self.ttl, state_json)

    def load_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        data = self.client.get(self._key(session_id))
        if data:
            return json.loads(data)
        return None

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        keys = self.client.keys(f"{self.prefix}*")
        results = []
        for key in keys[:limit]:
            data = self.client.get(key)
            if data:
                results.append(json.loads(data))
        return results

    def delete_session(self, session_id: str) -> bool:
        return bool(self.client.delete(self._key(session_id)))

    def session_exists(self, session_id: str) -> bool:
        return bool(self.client.exists(self._key(session_id)))


def get_storage() -> StorageBackend:
    """Auto-detect storage backend from environment variables.

    AGENTSHIELD_STORAGE: memory | sqlite | redis (default: memory)
    AGENTSHIELD_DB_PATH: SQLite database path (default: agentshield_sessions.db)
    AGENTSHIELD_REDIS_URL: Redis connection URL
    """
    storage_type = os.environ.get("AGENTSHIELD_STORAGE", "memory").lower()

    if storage_type == "sqlite":
        db_path = os.environ.get("AGENTSHIELD_DB_PATH", "agentshield_sessions.db")
        return SQLiteStorage(db_path)
    elif storage_type == "redis":
        redis_url = os.environ.get("AGENTSHIELD_REDIS_URL", "redis://localhost:6379")
        return RedisStorage(redis_url)
    else:
        return MemoryStorage()

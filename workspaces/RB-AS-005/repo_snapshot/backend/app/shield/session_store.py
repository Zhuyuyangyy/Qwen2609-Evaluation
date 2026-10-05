# AgentShield_V3 - SQLite Session Persistence Layer
# 自动保存/恢复 session 状态，重启后不丢失

import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, Optional

_SHIELD_DB = os.environ.get("SHIELD_DB", str(Path(__file__).parent.parent.parent / "shield_sessions.db"))

def init_db():
    """初始化 SQLite 表"""
    conn = sqlite3.connect(_SHIELD_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            engine_id TEXT,
            world_name TEXT,
            created_at REAL,
            updated_at REAL,
            state_json TEXT,
            graph_json TEXT,
            audit_json TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_updated ON sessions(updated_at)
    """)
    conn.commit()
    conn.close()

def save_session(session_id: str, engine_id: str, world_name: str,
                 state_data: Dict, graph_data: Dict, audit_data: list):
    """保存 session 到 SQLite"""
    conn = sqlite3.connect(_SHIELD_DB)
    import time
    now = time.time()
    conn.execute("""
        INSERT OR REPLACE INTO sessions
        (session_id, engine_id, world_name, created_at, updated_at, state_json, graph_json, audit_json)
        VALUES (?, ?, ?, COALESCE((SELECT created_at FROM sessions WHERE session_id=?), ?), ?, ?, ?, ?)
    """, (session_id, engine_id, world_name, session_id, now, now,
          json.dumps(state_data), json.dumps(graph_data), json.dumps(audit_data)))
    conn.commit()
    conn.close()

def load_session(session_id: str) -> Optional[Dict]:
    """从 SQLite 恢复 session"""
    conn = sqlite3.connect(_SHIELD_DB)
    row = conn.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "session_id": row[0],
        "engine_id": row[1],
        "world_name": row[2],
        "created_at": row[3],
        "updated_at": row[4],
        "state_data": json.loads(row[5]),
        "graph_data": json.loads(row[6]),
        "audit_data": json.loads(row[7]),
    }

def delete_session_db(session_id: str) -> bool:
    """从 SQLite 删除 session 记录"""
    conn = sqlite3.connect(_SHIELD_DB)
    cur = conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# 对外保留 delete_session 名称（API 层使用）
delete_session = delete_session_db


def list_sessions(limit: int = 20):
    """列出最近的 sessions"""
    conn = sqlite3.connect(_SHIELD_DB)
    rows = conn.execute(
        "SELECT session_id, engine_id, world_name, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [{"session_id": r[0], "engine_id": r[1], "world_name": r[2], "updated_at": r[3]} for r in rows]

# 初始化
init_db()

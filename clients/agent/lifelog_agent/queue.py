from __future__ import annotations
import os
import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import CONFIG_DIR

DB_PATH = CONFIG_DIR / "queue.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS queue (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
"""

class OfflineQueue:
    def __init__(self, max_mb: int = 50):
        self.max_bytes = max_mb * 1024 * 1024
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._ensure_db()

    def _ensure_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    def _size(self) -> int:
        return DB_PATH.stat().st_size if DB_PATH.exists() else 0

    def _evict_if_needed(self):
        if self._size() <= self.max_bytes:
            return
        # Evict oldest rows until under threshold
        with sqlite3.connect(DB_PATH) as conn:
            while self._size() > self.max_bytes and conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0] > 0:
                conn.execute("DELETE FROM queue WHERE id IN (SELECT id FROM queue ORDER BY id ASC LIMIT 100)")
                conn.commit()

    def enqueue(self, kind: str, payload: Dict[str, Any]):
        item = json.dumps(payload)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("INSERT INTO queue(kind, payload, created_at) VALUES (?, ?, ?)", (kind, item, int(time.time())))
            conn.commit()
        self._evict_if_needed()

    def peek_batch(self, limit: int = 50) -> List[Tuple[int, str, Dict[str, Any]]]:
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT id, kind, payload FROM queue ORDER BY id ASC LIMIT ?", (limit,)).fetchall()
        out: List[Tuple[int, str, Dict[str, Any]]] = []
        for rid, kind, pl in rows:
            try:
                out.append((rid, kind, json.loads(pl)))
            except Exception:
                out.append((rid, kind, {"_error": "invalid_json"}))
        return out

    def delete_ids(self, ids: List[int]):
        if not ids:
            return
        with sqlite3.connect(DB_PATH) as conn:
            q_marks = ",".join(["?"] * len(ids))
            conn.execute(f"DELETE FROM queue WHERE id IN ({q_marks})", ids)
            conn.commit()

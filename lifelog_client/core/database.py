import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

DB_PATH = Path.home() / ".lifelog" / "buffer.db"

class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS buffer_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    extension_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def push(self, extension_id: str, payload: Dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO buffer_queue (extension_id, payload_json) VALUES (?, ?)",
                (extension_id, json.dumps(payload))
            )
            conn.commit()

    def pop_batch(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, extension_id, payload_json, created_at FROM buffer_queue ORDER BY created_at ASC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                result.append({
                    "id": row["id"],
                    "extension_id": row["extension_id"],
                    "payload": json.loads(row["payload_json"]),
                    "created_at": row["created_at"]
                })
            return result

    def delete_batch(self, ids: List[int]):
        if not ids:
            return
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            placeholders = ",".join("?" * len(ids))
            cursor.execute(f"DELETE FROM buffer_queue WHERE id IN ({placeholders})", ids)
            conn.commit()

db_manager = DatabaseManager()
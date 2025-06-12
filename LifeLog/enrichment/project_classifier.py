from __future__ import annotations

import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from LifeLog.config import Settings
from LifeLog.database import get_connection

log = logging.getLogger(__name__)


class ProjectMemory:
    def __init__(self, path: Path, n_features: int = 128, use_db: bool = False) -> None:
        self.path = path
        self.vectorizer = HashingVectorizer(n_features=n_features, alternate_sign=False)
        self.entries: Dict[str, Dict[str, Sequence[float]]] = {}
        self.use_db = use_db
        self.db_available = use_db
        
        if not use_db:
            self._load()
        else:
            try:
                self._load_from_db()
            except Exception as e:
                log.error(f"Failed to load from database, falling back to file: {e}")
                self.db_available = False
                self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text())
            except Exception as e:
                log.error(f"Failed to load project memory {self.path}: {e}")
                self.entries = {}

    def _load_from_db(self) -> None:
        """Load project memory from database."""
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT project_name, embedding, count FROM project_memory")
                rows = cur.fetchall()
                self.entries = {}
                for row in rows:
                    project_name, embedding_json, count = row
                    self.entries[project_name] = {
                        "embedding": json.loads(embedding_json),
                        "count": count
                    }
                log.debug(f"Loaded {len(self.entries)} project memory entries from database")
        except Exception as e:
            log.error(f"Failed to load project memory from database: {e}")
            self.db_available = False
            raise

    def save(self) -> None:
        if self.use_db and self.db_available:
            try:
                self._save_to_db()
            except Exception as e:
                log.error(f"Failed to save to database, falling back to file: {e}")
                self.db_available = False
                self._save_to_file()
        else:
            self._save_to_file()

    def _save_to_file(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.entries))
        except Exception as e:
            log.error(f"Failed to save project memory {self.path}: {e}")

    def _save_to_db(self) -> None:
        """Save project memory to database."""
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                # Clear existing data and re-insert (simple approach)
                cur.execute("DELETE FROM project_memory")
                for project_name, data in self.entries.items():
                    cur.execute(
                        """
                        INSERT INTO project_memory (project_name, embedding, count)
                        VALUES (?, ?, ?)
                        """,
                        (project_name, json.dumps(data["embedding"]), data["count"])
                    )
                conn.commit()
                log.debug(f"Saved {len(self.entries)} project memory entries to database")
        except Exception as e:
            log.error(f"Failed to save project memory to database: {e}")
            self.db_available = False
            raise

    def update(self, name: str, vec: np.ndarray) -> None:
        info = self.entries.get(name)
        if info:
            count = info.get("count", 1)
            prev = np.array(info["embedding"])
            new_vec = ((prev * count) + vec) / (count + 1)
            self.entries[name] = {"embedding": new_vec.tolist(), "count": count + 1}
        else:
            self.entries[name] = {"embedding": vec.tolist(), "count": 1}
        
        # Update database immediately if using DB and it's available
        if self.use_db and self.db_available:
            try:
                with get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute(
                        """
                        INSERT OR REPLACE INTO project_memory (project_name, embedding, count)
                        VALUES (?, ?, ?)
                        """,
                        (name, json.dumps(self.entries[name]["embedding"]), self.entries[name]["count"])
                    )
                    conn.commit()
            except Exception as e:
                log.error(f"Failed to update project memory in database: {e}")
                self.db_available = False
                # Fall back to file save
                self._save_to_file()
        elif not self.use_db:
            # Only auto-save to file if not using database
            self.save()

    def vectorize(self, text: str) -> np.ndarray:
        vec = self.vectorizer.transform([text])
        return vec.toarray()[0]

    def best_match(self, vec: np.ndarray) -> Tuple[Optional[str], float]:
        if not self.entries:
            return None, 0.0
        best_name = None
        best_score = 0.0
        for name, data in self.entries.items():
            mem_vec = np.array(data["embedding"])
            score = float(np.dot(vec, mem_vec) / (np.linalg.norm(vec) * np.linalg.norm(mem_vec) + 1e-8))
            if score > best_score:
                best_name = name
                best_score = score
        return best_name, best_score


class ProjectResolver:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.project_aliases: Dict[str, str] = settings.project_aliases or {}
        # Use database storage if enabled and available
        use_db = getattr(settings, 'project_memory_use_db', False) and getattr(settings, 'use_database', True)
        self.memory = ProjectMemory(
            settings.project_memory_path, 
            use_db=use_db
        )
        self.threshold = settings.project_similarity_threshold
        self.continuity_gap_s = settings.project_continuity_gap_s
        self.last_project: Optional[str] = None
        self.last_end: Optional[datetime] = None
        self.last_confidence: float = 0.0
        self.enable_fallback = getattr(settings, 'enable_database_fallback', True)

    def resolve(
        self,
        project_name: Optional[str],
        activity_text: str,
        notes_text: Optional[str],
        start: datetime,
    ) -> Optional[str]:
        # Only assign a project if there is a strong, explicit signal
        text = activity_text + (" " + notes_text if notes_text else "")
        
        try:
            vec = self.memory.vectorize(text)
        except Exception as e:
            log.error(f"Failed to vectorize text for project classification: {e}")
            if self.enable_fallback:
                return project_name  # Return original project name as fallback
            raise

        # 1. Explicit project name provided
        if project_name:
            canonical = self.project_aliases.get(project_name.lower(), project_name)
            try:
                self.memory.update(canonical, vec)
            except Exception as e:
                log.error(f"Failed to update project memory for {canonical}: {e}")
                if not self.enable_fallback:
                    raise
            self.last_project = canonical
            self.last_end = start
            self.last_confidence = 1.0
            return canonical

        # 2. Alias found in text
        lowered = text.lower()
        for alias, canonical in self.project_aliases.items():
            if alias.lower() in lowered:
                try:
                    self.memory.update(canonical, vec)
                except Exception as e:
                    log.error(f"Failed to update project memory for alias {canonical}: {e}")
                    if not self.enable_fallback:
                        raise
                self.last_project = canonical
                self.last_end = start
                self.last_confidence = 1.0
                return canonical

        # 3. Strong match in memory
        try:
            name, score = self.memory.best_match(vec)
            if name and score >= self.threshold:
                try:
                    self.memory.update(name, vec)
                except Exception as e:
                    log.error(f"Failed to update project memory for match {name}: {e}")
                    if not self.enable_fallback:
                        raise
                self.last_project = name
                self.last_end = start
                self.last_confidence = score
                return name
        except Exception as e:
            log.error(f"Failed to find best match in project memory: {e}")
            if not self.enable_fallback:
                raise

        # Otherwise, do not assign a project (no fallback to inferred)
        self.last_project = None
        self.last_end = start
        self.last_confidence = 0.0
        return None

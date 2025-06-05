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

log = logging.getLogger(__name__)


class ProjectMemory:
    def __init__(self, path: Path, n_features: int = 128) -> None:
        self.path = path
        self.vectorizer = HashingVectorizer(n_features=n_features, alternate_sign=False)
        self.entries: Dict[str, Dict[str, Sequence[float]]] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text())
            except Exception as e:
                log.error(f"Failed to load project memory {self.path}: {e}")
                self.entries = {}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.entries))
        except Exception as e:
            log.error(f"Failed to save project memory {self.path}: {e}")

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

    def update(self, name: str, vec: np.ndarray) -> None:
        info = self.entries.get(name)
        if info:
            count = info.get("count", 1)
            prev = np.array(info["embedding"])
            new_vec = ((prev * count) + vec) / (count + 1)
            self.entries[name] = {"embedding": new_vec.tolist(), "count": count + 1}
        else:
            self.entries[name] = {"embedding": vec.tolist(), "count": 1}
        self.save()


class ProjectResolver:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.project_aliases: Dict[str, str] = settings.project_aliases or {}
        self.memory = ProjectMemory(settings.project_memory_path)
        self.threshold = settings.project_similarity_threshold
        self.continuity_gap_s = settings.project_continuity_gap_s
        self.last_project: Optional[str] = None
        self.last_end: Optional[datetime] = None
        self.last_confidence: float = 0.0

    def resolve(
        self,
        project_name: Optional[str],
        activity_text: str,
        notes_text: Optional[str],
        start: datetime,
    ) -> Optional[str]:
        text = activity_text + (" " + notes_text if notes_text else "")
        vec = self.memory.vectorize(text)

        if project_name:
            canonical = self.project_aliases.get(project_name.lower(), project_name)
            self.memory.update(canonical, vec)
            self.last_project = canonical
            self.last_end = start
            self.last_confidence = 1.0
            return canonical

        if self.last_project and self.last_end:
            gap = (start - self.last_end).total_seconds()
            if gap <= self.continuity_gap_s and self.last_confidence >= self.threshold:
                self.memory.update(self.last_project, vec)
                self.last_end = start
                return self.last_project

        lowered = text.lower()
        for alias, canonical in self.project_aliases.items():
            if alias.lower() in lowered:
                self.memory.update(canonical, vec)
                self.last_project = canonical
                self.last_end = start
                self.last_confidence = 1.0
                return canonical

        name, score = self.memory.best_match(vec)
        if name and score >= self.threshold:
            self.memory.update(name, vec)
            self.last_project = name
            self.last_end = start
            self.last_confidence = score
            return name

        new_name = f"Inferred-{hashlib.sha1(text.encode()).hexdigest()[:8]}"
        self.memory.update(new_name, vec)
        self.last_project = new_name
        self.last_end = start
        self.last_confidence = 0.5
        return new_name

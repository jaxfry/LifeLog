"""
Fully-automatic project-name resolution for Layer 1b
----------------------------------------------------
* deterministic aliasing first  (exact, file-stem)
* then MiniLM embedding similarity
* persistent alias map in JSON (`LifeLog/data/project_aliases.json`)
"""

from __future__ import annotations
import json, re, pathlib, logging
from typing import Dict, Tuple

from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)
MODEL = SentenceTransformer("sentence-transformers/paraphrase-MiniLM-L6-v2", device="cpu")

DATA_DIR   = pathlib.Path("LifeLog/data")
ALIAS_FILE = DATA_DIR / "project_aliases.json"
SIM_AUTO_THRESHOLD   = 0.90  # auto-merge above this
SIM_CANDIDATE_LOWER  = 0.80  # log for review if in (0.80-0.90)

class ProjectResolver:
    def __init__(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.alias: Dict[str, str] = (
            json.loads(ALIAS_FILE.read_text()) if ALIAS_FILE.exists() else {}
        )

    # --------------- public API -------------------------------------------
    def resolve(self, raw_name: str | None, context: str | None = None) -> str | None:
        if not raw_name:
            return None
        norm = self._normalize(raw_name)
        # 1) fast path – already known
        if norm in self.alias:
            return self.alias[norm]

        # 2) deterministic file-stem
        stem = self._file_stem(norm)
        if stem in self.alias:
            self._learn(norm, self.alias[stem])
            return self.alias[stem]

        # 3) embedding similarity
        canon, score = self._best_match(norm, context)
        if score >= SIM_AUTO_THRESHOLD:
            self._learn(norm, canon)
            log.debug("AUTO-MERGE  %.3f   %-20s -> %s", score, norm, canon)
            return canon
        if SIM_CANDIDATE_LOWER <= score < SIM_AUTO_THRESHOLD:
            log.debug("CANDIDATE   %.3f   %-20s ?  %s", score, norm, canon)

        # 4) treat as new canonical
        self._learn(norm, norm, learn_alias=False)
        return norm

    # --------------- helpers ---------------------------------------------
    @staticmethod
    def _normalize(s: str) -> str:
        s = s.lower()
        s = re.sub(r"[^\w\s.-]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _file_stem(s: str) -> str:
        return re.sub(r"\.[a-z0-9]{2,4}$", "", s)

    def _best_match(self, name: str, ctx: str | None) -> Tuple[str, float]:
        if not self.alias:
            return name, 0.0
        # candidate canonical names
        canon_list = sorted(set(self.alias.values()))
        texts = [name if not ctx else f"{name} {ctx}"] + canon_list
        embs  = MODEL.encode(texts, normalize_embeddings=True)
        sims  = (embs[0] @ embs[1:].T)
        idx   = int(sims.argmax())
        return canon_list[idx], float(sims[idx])

    # --------------- persistence -----------------------------------------
    def _learn(self, alias: str, canon: str, *, learn_alias: bool = True) -> None:
        if learn_alias:
            self.alias[alias] = canon
            ALIAS_FILE.write_text(json.dumps(self.alias, indent=2, sort_keys=True))

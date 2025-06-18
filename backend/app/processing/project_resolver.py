import logging
import numpy as np
import duckdb
from sklearn.feature_extraction.text import HashingVectorizer

from backend.app.core.settings import Settings

log = logging.getLogger(__name__)

class ProjectResolver:
    def __init__(self, con: duckdb.DuckDBPyConnection, settings: Settings):
        self.con = con
        self.settings = settings
        self.vectorizer = HashingVectorizer(
            n_features=settings.PROJECT_EMBEDDING_SIZE, 
            alternate_sign=False
        )

    def _vectorize(self, text: str) -> np.ndarray:
        vec = self.vectorizer.transform([text])
        return np.asarray(vec.todense())[0]

    def learn(self, project_name: str, text_context: str):
        """Updates a project's embedding or creates a new one."""
        log.info(f"Learning project '{project_name}'")
        vec = self._vectorize(text_context)
        
        # Check if project exists
        existing = self.con.execute("SELECT id, embedding FROM projects WHERE lower(name) = lower(?)", [project_name]).fetchone()
        
        if existing:
            proj_id, old_vec_list = existing
            old_vec = np.array(old_vec_list)
            # Simple moving average to update the embedding
            new_vec = ((old_vec * 3) + vec) / 4 
            self.con.execute("UPDATE projects SET embedding = ? WHERE id = ?", [new_vec.tolist(), proj_id])
        else:
            self.con.execute(
                "INSERT INTO projects (id, name, embedding) VALUES (gen_random_uuid(), ?, ?)",
                [project_name, vec.tolist()]
            )

    def resolve(self, text_context: str) -> str | None:
        """Finds the best matching project for a given text context."""
        vec = self._vectorize(text_context)
        
        # Query using vector similarity search
        result = self.con.execute(
            """
            SELECT name, embedding <-> list_value(CAST(? AS FLOAT[])) AS distance
            FROM projects
            ORDER BY distance ASC
            LIMIT 1;
            """,
            [vec.astype(np.float32).tolist()]  # Ensure float32 type
        ).fetchone()
        
        if result:
            name, distance = result
            if 1 - distance >= self.settings.PROJECT_SIMILARITY_THRESHOLD:
                log.debug(f"Resolved project '{name}' with similarity {1-distance:.2f}")
                return name
        return None
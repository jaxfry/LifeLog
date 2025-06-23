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
        
        # Convert numpy array to Python list of floats (ensure float32 for DuckDB FLOAT type)
        vec_list = [float(np.float32(x)) for x in vec]
        
        # Query using DuckDB's array_cosine_similarity function with explicit cast
        result = self.con.execute(
            """
            SELECT name, array_cosine_similarity(embedding, CAST(? AS FLOAT[128])) AS similarity
            FROM projects
            ORDER BY similarity DESC
            LIMIT 1;
            """,
            [vec_list]
        ).fetchone()
        
        if result:
            name, similarity = result
            if similarity >= self.settings.PROJECT_SIMILARITY_THRESHOLD:
                log.debug(f"Resolved project '{name}' with similarity {similarity:.2f}")
                return name
        return None
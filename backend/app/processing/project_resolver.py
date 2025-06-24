import logging
from typing import Optional, List
import uuid

import numpy as np
import duckdb
from sklearn.feature_extraction.text import HashingVectorizer

from backend.app.core.settings import Settings
from backend.app.core.utils import with_db_write_retry

logger = logging.getLogger(__name__)

class VectorizationService:
    """Handles text vectorization for project matching."""
    
    def __init__(self, embedding_size: int):
        self.vectorizer = HashingVectorizer(
            n_features=embedding_size, 
            alternate_sign=False
        )
    
    def vectorize_text(self, text: str) -> np.ndarray:
        """Convert text to vector representation."""
        vector_matrix = self.vectorizer.transform([text])
        return np.asarray(vector_matrix.todense())[0]

class ProjectEmbeddingRepository:
    """Handles database operations for project embeddings."""
    
    def __init__(self, db_connection: duckdb.DuckDBPyConnection):
        self.db = db_connection
    
    def find_project_by_name(self, project_name: str) -> Optional[tuple]:
        """Find existing project by name (case-insensitive)."""
        return self.db.execute(
            "SELECT id, embedding FROM projects WHERE lower(name) = lower(?)", 
            [project_name]
        ).fetchone()
    
    @with_db_write_retry()
    def create_project_with_embedding(self, project_name: str, embedding: List[float]) -> None:
        """Create a new project with its embedding."""
        self.db.execute(
            "INSERT INTO projects (id, name, embedding) VALUES (gen_random_uuid(), ?, ?)",
            [project_name, embedding]
        )
    
    @with_db_write_retry()
    def update_project_embedding(self, project_id: str, new_embedding: List[float]) -> None:
        """Update an existing project's embedding."""
        self.db.execute(
            "UPDATE projects SET embedding = ? WHERE id = ?", 
            [new_embedding, project_id]
        )
    
    def find_best_matching_project(self, query_vector: List[float]) -> Optional[tuple]:
        """Find the project with highest similarity to the query vector."""
        return self.db.execute(
            """
            SELECT name, array_cosine_similarity(embedding, CAST(? AS FLOAT[128])) AS similarity
            FROM projects
            ORDER BY similarity DESC
            LIMIT 1;
            """,
            [query_vector]
        ).fetchone()

class EmbeddingUpdater:
    """Handles embedding update strategies."""
    
    @staticmethod
    def update_with_moving_average(old_embedding: np.ndarray, new_embedding: np.ndarray, weight: float = 0.25) -> np.ndarray:
        """Update embedding using moving average with specified weight for new data."""
        return ((old_embedding * (1 - weight)) + (new_embedding * weight))

class ProjectResolver:
    """Resolves text context to project names using embeddings."""
    
    def __init__(self, con: duckdb.DuckDBPyConnection, settings: Settings):
        self.settings = settings
        self.vectorizer = VectorizationService(settings.PROJECT_EMBEDDING_SIZE)
        self.repository = ProjectEmbeddingRepository(con)
        self.embedding_updater = EmbeddingUpdater()

    def learn(self, project_name: str, text_context: str) -> None:
        """
        Updates a project's embedding or creates a new one.
        
        Args:
            project_name: Name of the project to learn
            text_context: Text context to learn from
        """
        logger.info(f"Learning project '{project_name}'")
        
        new_vector = self.vectorizer.vectorize_text(text_context)
        existing_project = self.repository.find_project_by_name(project_name)
        
        if existing_project:
            self._update_existing_project(existing_project, new_vector)
        else:
            self._create_new_project(project_name, new_vector)

    def resolve(self, text_context: str) -> Optional[str]:
        """
        Finds the best matching project for a given text context.
        
        Args:
            text_context: Text to match against known projects
            
        Returns:
            Project name if match found above threshold, None otherwise
        """
        query_vector = self.vectorizer.vectorize_text(text_context)
        query_vector_list = self._convert_to_float_list(query_vector)
        
        result = self.repository.find_best_matching_project(query_vector_list)
        
        if result:
            project_name, similarity = result
            if similarity >= self.settings.PROJECT_SIMILARITY_THRESHOLD:
                logger.debug(f"Resolved project '{project_name}' with similarity {similarity:.2f}")
                return project_name
        
        return None
    
    def _update_existing_project(self, existing_project: tuple, new_vector: np.ndarray) -> None:
        """Update an existing project's embedding."""
        project_id, old_vector_list = existing_project
        old_vector = np.array(old_vector_list)
        updated_vector = self.embedding_updater.update_with_moving_average(old_vector, new_vector)
        self.repository.update_project_embedding(project_id, updated_vector.tolist())
    
    def _create_new_project(self, project_name: str, vector: np.ndarray) -> None:
        """Create a new project with its embedding."""
        vector_list = self._convert_to_float_list(vector)
        self.repository.create_project_with_embedding(project_name, vector_list)
    
    def _convert_to_float_list(self, vector: np.ndarray) -> List[float]:
        """Convert numpy array to list of floats for DuckDB compatibility."""
        return [float(np.float32(x)) for x in vector]
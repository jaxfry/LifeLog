# central_server/processing_service/logic/project_resolver.py

import logging
import uuid
from typing import Optional, List, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from central_server.processing_service.db_models import Project as ProjectOrm, PGVECTOR_AVAILABLE
from central_server.processing_service.logic.embeddings import get_embedding_service
from central_server.processing_service.logic.settings import settings as service_settings
import numpy as np

logger = logging.getLogger(__name__)

class ProjectResolver:
    """
    Async resolver for project names using normalization, exact match, and embedding similarity.
    Handles creation and deduplication of projects.
    """
    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = get_embedding_service()
        self.similarity_threshold = getattr(service_settings, 'PROJECT_SIMILARITY_THRESHOLD', 0.75)
        self._project_cache: Dict[str, ProjectOrm] = {}

    async def get_all_project_names(self) -> List[str]:
        """
        Retrieves a list of all project names from the database.

        Returns:
            A list of all project names.
        """
        stmt = select(ProjectOrm.name).order_by(ProjectOrm.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _normalize_project_name(self, project_name: str) -> str:
        """
        Normalize project names to handle LLM inconsistencies.
        Splits on common delimiters, sorts, title-cases, rejoins.
        """
        if not project_name:
            return project_name
        delimiters = [' / ', ' & ', ' - ', ' + ', ' | ']
        delimiter_used = None
        for delimiter in delimiters:
            if delimiter in project_name:
                delimiter_used = delimiter
                break
        if delimiter_used:
            parts = [part.strip() for part in project_name.split(delimiter_used)]
            parts = [part for part in parts if part]
            parts = [part.title() for part in parts]
            parts.sort()
            return ' / '.join(parts)
        else:
            return project_name.title()

    async def get_or_create_project_by_name(self, project_name: Optional[str]) -> Optional[ProjectOrm]:
        """
        Retrieves a project by its name or creates a new one if it doesn't exist.
        Uses embeddings to find similar projects and merge duplicates.
        Returns None if project_name is None or empty.
        """
        if not project_name:
            return None
        normalized_name = self._normalize_project_name(project_name)
        # 1. Try exact (case-insensitive) match
        stmt = select(ProjectOrm).where(ProjectOrm.name.ilike(normalized_name))
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()
        if project:
            return project
        # 2. Embedding similarity check
        embedding_service = self.embedding_service
        if embedding_service and embedding_service.model:
            new_embedding = embedding_service.generate_project_embedding(normalized_name)
            stmt = select(ProjectOrm)
            result = await self.session.execute(stmt)
            all_projects = result.scalars().all()
            best_match = None
            best_score = 0.0
            for existing_project in all_projects:
                # Ensure we get the actual value, not the column object
                project_name_val = getattr(existing_project, 'name', None)
                embedding_val = getattr(existing_project, 'embedding', None)
                existing_embedding = None
                if embedding_val is not None:
                    # Convert to list of floats if needed
                    import numpy as np  # Always import numpy here to avoid unbound errors
                    if isinstance(embedding_val, np.ndarray):
                        existing_embedding = embedding_val.tolist()
                    elif isinstance(embedding_val, list):
                        existing_embedding = embedding_val
                    elif isinstance(embedding_val, (bytes, bytearray)):
                        try:
                            existing_embedding = np.frombuffer(embedding_val, dtype=np.float32).tolist()
                        except Exception:
                            continue
                    else:
                        continue
                    similarity = embedding_service.compute_similarity(new_embedding, existing_embedding)
                    if similarity >= self.similarity_threshold and similarity > best_score:
                        best_match = existing_project
                        best_score = similarity
                else:
                    # Generate embedding for existing project if missing
                    if project_name_val is None:
                        continue
                    name_str = str(project_name_val)
                    existing_embedding = embedding_service.generate_project_embedding(name_str)
                    # Assign as list of floats for pgvector, or bytes for LargeBinary
                    try:
                        if hasattr(existing_project, 'embedding'):
                            if PGVECTOR_AVAILABLE:
                                existing_project.embedding = list(existing_embedding)  # type: ignore
                            else:
                                import numpy as np
                                existing_project.embedding = np.array(existing_embedding, dtype=np.float32).tobytes()  # type: ignore
                            self.session.add(existing_project)
                    except Exception:
                        pass
                    similarity = embedding_service.compute_similarity(new_embedding, existing_embedding)
                    if similarity >= self.similarity_threshold and similarity > best_score:
                        best_match = existing_project
                        best_score = similarity
            if best_match:
                logger.info(f"Project '{normalized_name}' is highly similar to existing project '{best_match.name}' (score={best_score:.2f}), reusing existing.")
                return best_match
        # 3. If no similar project, create it
        logger.info(f"Project '{normalized_name}' not found, creating new one.")
        try:
            new_project = ProjectOrm(
                id=uuid.uuid4(),
                name=normalized_name,
                embedding=embedding_service.generate_project_embedding(normalized_name) if embedding_service and embedding_service.model else None
            )
            self.session.add(new_project)
            await self.session.flush()
            await self.session.refresh(new_project)
            logger.info(f"Created project '{normalized_name}' with embedding")
            return new_project
        except IntegrityError:
            # In case of a race condition where another process created it
            await self.session.rollback()
            stmt = select(ProjectOrm).where(ProjectOrm.name.ilike(normalized_name))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()
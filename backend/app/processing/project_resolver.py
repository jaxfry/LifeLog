import logging
from typing import Optional, List
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.app.models import Project
from backend.app.core.embeddings import get_embedding_service

logger = logging.getLogger(__name__)


class ProjectResolver:
    """
    Handles fetching and creating projects.
    The main project resolution logic is now handled by the LLMProcessor.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all_project_names(self) -> List[str]:
        """Fetches all existing project names."""
        stmt = select(Project.name).order_by(Project.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_or_create_project_by_name(
        self, project_name: Optional[str]
    ) -> Optional[Project]:
        """
        Retrieves a project by its name or creates a new one if it doesn't exist.
        Returns None if project_name is None or empty.
        Uses embeddings to find similar projects and merge duplicates.
        """
        if not project_name:
            return None

        # Normalize the project name first
        normalized_name = self._normalize_project_name(project_name)

        # First, try to find the existing project (case-insensitive)
        stmt = select(Project).where(Project.name.ilike(normalized_name))
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()

        if project:
            return project

        # --- Embedding similarity check ---
        embedding_service = get_embedding_service()
        new_embedding = embedding_service.generate_project_embedding(normalized_name)
        
        # Fetch all existing projects and their embeddings
        stmt = select(Project)
        result = await self.session.execute(stmt)
        all_projects = result.scalars().all()
        
        # Use a lower threshold for better matching of similar projects
        high_confidence_threshold = 0.75
        best_match = None
        best_score = 0.0

        for existing_project in all_projects:
            if existing_project.embedding:
                similarity = embedding_service.compute_similarity(new_embedding, existing_project.embedding)
                if similarity >= high_confidence_threshold and similarity > best_score:
                    best_match = existing_project
                    best_score = similarity
            else:
                # Generate embedding for existing project if it doesn't have one
                existing_embedding = embedding_service.generate_project_embedding(existing_project.name)
                existing_project.embedding = existing_embedding
                self.session.add(existing_project)
                
                similarity = embedding_service.compute_similarity(new_embedding, existing_embedding)
                if similarity >= high_confidence_threshold and similarity > best_score:
                    best_match = existing_project
                    best_score = similarity

        if best_match:
            logger.info(f"Project '{normalized_name}' is highly similar to existing project '{best_match.name}' (score={best_score:.2f}), reusing existing.")
            return best_match

        # If no similar project, create it
        logger.info(f"Project '{normalized_name}' not found, creating new one.")
        try:
            new_project = Project(
                id=uuid.uuid4(),
                name=normalized_name,
                embedding=new_embedding
            )
            self.session.add(new_project)
            await self.session.flush()
            await self.session.refresh(new_project)
            logger.info(f"Created project '{normalized_name}' with embedding")
            return new_project
        except IntegrityError:
            # In case of a race condition where another process created it
            await self.session.rollback()
            stmt = select(Project).where(Project.name.ilike(normalized_name))
            result = await self.session.execute(stmt)
            return result.scalar_one_or_none()

    def _normalize_project_name(self, project_name: str) -> str:
        """
        Normalize project names to handle LLM inconsistencies.
        """
        if not project_name:
            return project_name
        
        # Common delimiters used by LLMs
        delimiters = [' / ', ' & ', ' - ', ' + ', ' | ']
        
        # Find which delimiter is used (if any)
        delimiter_used = None
        for delimiter in delimiters:
            if delimiter in project_name:
                delimiter_used = delimiter
                break
        
        if delimiter_used:
            # Split by delimiter, normalize each part, sort, and rejoin
            parts = [part.strip() for part in project_name.split(delimiter_used)]
            # Remove empty parts
            parts = [part for part in parts if part]
            # Normalize each part (title case)
            parts = [part.title() for part in parts]
            # Sort alphabetically for consistency
            parts.sort()
            # Use standard delimiter
            return ' / '.join(parts)
        else:
            # Single project name, just normalize capitalization
            return project_name.title()
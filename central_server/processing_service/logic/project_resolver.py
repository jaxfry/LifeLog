# central_server/processing_service/logic/project_resolver.py

import logging
import uuid
from typing import Optional, List, Dict, Any, cast

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from central_server.processing_service.db_models import Project as ProjectOrm, ProjectSuggestion, SuggestionStatus, PGVECTOR_AVAILABLE
from central_server.processing_service.logic.embeddings import get_embedding_service
from central_server.processing_service.logic.settings import settings as service_settings
from central_server.processing_service.models import TimelineEntry

logger = logging.getLogger(__name__)

def _to_float_list(embedding_val: Any) -> Optional[List[float]]:
    """Converts a database embedding value to a list of floats."""
    if embedding_val is None:
        return None
    
    if hasattr(embedding_val, 'tolist'):  # Handles numpy arrays
        return embedding_val.tolist()

    if isinstance(embedding_val, list):
        return embedding_val

    if isinstance(embedding_val, (bytes, bytearray)):
        try:
            return np.frombuffer(embedding_val, dtype=np.float32).tolist()
        except ValueError as e:
            logger.error(f"Could not convert bytes to embedding: {e}")
            return None
            
    logger.warning(f"Unhandled embedding type: {type(embedding_val)}")
    return None

class ProjectResolver:
    """
    Resolves project names against existing projects and handles the creation
    and deduplication of new project suggestions.
    """
    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = get_embedding_service()
        self.suggestion_similarity_threshold = getattr(service_settings, 'PROJECT_SUGGESTION_SIMILARITY_THRESHOLD', 0.90)
        self.suggestion_confidence_threshold = getattr(service_settings, 'PROJECT_SUGGESTION_CONFIDENCE_THRESHOLD', 0.95)
        self._project_cache: Dict[str, ProjectOrm] = {}

    async def get_project_by_name(self, name: str) -> Optional[ProjectOrm]:
        """Finds an approved project by its exact (case-insensitive) name."""
        if name in self._project_cache:
            return self._project_cache[name]

        stmt = select(ProjectOrm).where(ProjectOrm.name == name, ProjectOrm.manual_creation == True)
        result = await self.session.execute(stmt)
        project = result.scalar_one_or_none()
        
        if project:
            self._project_cache[name] = project
        
        return project

    async def handle_new_project_name(self, name: str, timeline_entries: List[TimelineEntry]) -> Optional[uuid.UUID]:
        """
        Handles a project name proposed by the LLM.
        Returns the project_id if it exists, otherwise None.
        """
        approved_project: Optional[ProjectOrm] = await self.get_project_by_name(name)
        if approved_project:
            return cast(uuid.UUID, approved_project.id)

        if not self.embedding_service or not self.embedding_service.model:
            logger.warning("No embedding service available. Cannot process suggestion.")
            return None
        
        embedding = self.embedding_service.generate_project_embedding(name)
        if not embedding:
            logger.warning(f"Could not generate embedding for suggestion '{name}'.")
            return None

        similar_suggestion = await self._find_similar_pending_suggestion(embedding)

        if similar_suggestion:
            logger.info(f"New name '{name}' is similar to pending suggestion '{similar_suggestion.suggested_name}'. Merging rationale.")
            await self._merge_suggestion_rationale(similar_suggestion, timeline_entries)
        else:
            await self._create_suggestion(name, embedding, timeline_entries)
            
        return None

    async def _find_similar_pending_suggestion(self, embedding: List[float]) -> Optional[ProjectSuggestion]:
        """Finds a pending suggestion that is semantically similar to the new name."""
        if not PGVECTOR_AVAILABLE:
            return None

        distance_threshold = 1 - self.suggestion_similarity_threshold
        
        stmt = (
            select(ProjectSuggestion)
            .where(ProjectSuggestion.status == SuggestionStatus.PENDING)
            .where(ProjectSuggestion.embedding.is_not(None))
            .order_by(ProjectSuggestion.embedding.cosine_distance(embedding))
            .limit(1)
        )
        
        result = await self.session.execute(stmt)
        best_match = result.scalar_one_or_none()

        if best_match:
            best_match_embedding_list = _to_float_list(best_match.embedding)
            if best_match_embedding_list:
                similarity = self.embedding_service.compute_similarity(embedding, best_match_embedding_list)
                if similarity >= self.suggestion_similarity_threshold:
                    return best_match
        
        return None

    async def _create_suggestion(self, name: str, embedding: List[float], timeline_entries: List[TimelineEntry]):
        """Creates a new project suggestion in the database."""
        logger.info(f"Creating new project suggestion: '{name}'")

        # The confidence score is now a fixed value, as the suggestion engine is the only source of new projects.
        confidence = 0.95

        rationale = {
            "source_timeline_entries": [entry.model_dump_json() for entry in timeline_entries]
        }

        try:
            new_suggestion = ProjectSuggestion(
                id=uuid.uuid4(),
                suggested_name=name,
                embedding=embedding,
                confidence_score=confidence,
                rationale=rationale,
                status=SuggestionStatus.PENDING
            )
            self.session.add(new_suggestion)
            await self.session.flush()
            logger.info(f"Successfully created project suggestion '{name}'.")
        except IntegrityError:
            await self.session.rollback()
            logger.warning(f"Race condition or duplicate detected for suggestion '{name}'.")

    async def _merge_suggestion_rationale(self, suggestion: ProjectSuggestion, new_timeline_entries: List[TimelineEntry]):
        """Merges new timeline entries into an existing suggestion's rationale."""
        
        # Start with the existing rationale or an empty dict
        current_rationale = dict(suggestion.rationale) if isinstance(suggestion.rationale, dict) else {}

        # Get the list of entries, or start a new one
        source_entries = current_rationale.get("source_timeline_entries", [])
        if not isinstance(source_entries, list):
            source_entries = []

        # Add the new entries
        new_entries_json = [entry.model_dump_json() for entry in new_timeline_entries]
        source_entries.extend(new_entries_json)

        # Update the dictionary
        current_rationale["source_timeline_entries"] = source_entries  # type: ignore

        # Assign the modified dictionary back.
        suggestion.rationale = current_rationale  # type: ignore
        
        # Explicitly flag as modified for robustness.
        flag_modified(suggestion, "rationale")

        try:
            await self.session.flush()
            logger.info(f"Successfully merged rationale for suggestion '{suggestion.suggested_name}'.")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to merge rationale for suggestion '{suggestion.suggested_name}': {e}")

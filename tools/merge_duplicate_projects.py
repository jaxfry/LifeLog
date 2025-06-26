#!/usr/bin/env python3
"""
Tool to merge duplicate projects using embedding similarity.
This will identify and merge projects that are semantically similar.
"""

import asyncio
import logging
import sys
import os
from typing import List, Dict, Tuple

# Add project root to sys.path
CURR_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURR_DIR, '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from backend.app.core.db import SessionLocal
from backend.app.core.settings import settings
from backend.app.models import Project, TimelineEntry
from backend.app.core.embeddings import get_embedding_service

logger = logging.getLogger(__name__)

class ProjectMerger:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.embedding_service = get_embedding_service()
        self.similarity_threshold = 0.75  # Threshold for considering projects as duplicates

    async def get_all_projects(self) -> List[Project]:
        """Fetch all projects from the database."""
        stmt = select(Project).order_by(Project.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def generate_missing_embeddings(self, projects: List[Project]) -> None:
        """Generate embeddings for projects that don't have them."""
        for project in projects:
            emb = project.embedding
            is_missing = emb is None or (hasattr(emb, '__len__') and len(emb) == 0)
            if is_missing:
                logger.info(f"Generating embedding for project: {project.name}")
                project.embedding = self.embedding_service.generate_project_embedding(project.name)
                self.session.add(project)
        await self.session.commit()

    def find_duplicate_groups(self, projects: List[Project]) -> List[List[Project]]:
        """Find groups of similar projects using embeddings."""
        duplicate_groups = []
        processed = set()

        for i, project in enumerate(projects):
            emb = project.embedding
            is_missing = emb is None or (hasattr(emb, '__len__') and len(emb) == 0)
            if project.id in processed or is_missing:
                continue

            # Find all similar projects
            similar_projects = [project]
            processed.add(project.id)

            for j, other_project in enumerate(projects[i+1:], i+1):
                other_emb = other_project.embedding
                other_missing = other_emb is None or (hasattr(other_emb, '__len__') and len(other_emb) == 0)
                if other_project.id in processed or other_missing:
                    continue

                similarity = self.embedding_service.compute_similarity(
                    project.embedding, other_project.embedding
                )

                if similarity >= self.similarity_threshold:
                    similar_projects.append(other_project)
                    processed.add(other_project.id)

            # Only add groups with more than one project
            if len(similar_projects) > 1:
                duplicate_groups.append(similar_projects)

        return duplicate_groups

    async def merge_project_group(self, project_group: List[Project]) -> Project:
        """Merge a group of similar projects into one."""
        # Choose the "best" project to keep (e.g., shortest name, or most recent)
        keeper = min(project_group, key=lambda p: len(p.name))
        to_merge = [p for p in project_group if p.id != keeper.id]

        logger.info(f"Merging projects into '{keeper.name}': {[p.name for p in to_merge]}")

        # Update all timeline entries to point to the keeper project
        for project_to_merge in to_merge:
            await self.session.execute(
                update(TimelineEntry)
                .where(TimelineEntry.project_id == project_to_merge.id)
                .values(project_id=keeper.id)
            )

        # Delete the duplicate projects
        for project_to_merge in to_merge:
            await self.session.execute(
                delete(Project).where(Project.id == project_to_merge.id)
            )

        await self.session.commit()
        return keeper

    async def run_merge(self, dry_run: bool = True) -> None:
        """Run the project merging process."""
        logger.info("Starting project merge process...")

        # Get all projects
        projects = await self.get_all_projects()
        logger.info(f"Found {len(projects)} total projects")

        # Generate missing embeddings
        await self.generate_missing_embeddings(projects)

        # Refresh projects after embedding generation
        projects = await self.get_all_projects()

        # Find duplicate groups
        duplicate_groups = self.find_duplicate_groups(projects)
        
        if not duplicate_groups:
            logger.info("No duplicate projects found!")
            return

        logger.info(f"Found {len(duplicate_groups)} groups of duplicate projects:")
        
        for i, group in enumerate(duplicate_groups, 1):
            logger.info(f"Group {i}: {[p.name for p in group]}")
            
            if not dry_run:
                keeper = await self.merge_project_group(group)
                logger.info(f"✓ Merged group {i} into: {keeper.name}")
            else:
                logger.info(f"[DRY RUN] Would merge group {i} into: {min(group, key=lambda p: len(p.name)).name}")

        if dry_run:
            logger.info("\nThis was a dry run. Use --execute to actually merge projects.")
        else:
            logger.info(f"\nSuccessfully merged {len(duplicate_groups)} groups of duplicate projects!")

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Merge duplicate projects using embedding similarity")
    parser.add_argument("--execute", action="store_true", help="Actually perform the merge (default is dry run)")
    parser.add_argument("--threshold", type=float, default=0.75, help="Similarity threshold for merging (default: 0.75)")
    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async with SessionLocal() as session:
        merger = ProjectMerger(session)
        merger.similarity_threshold = args.threshold
        await merger.run_merge(dry_run=not args.execute)

if __name__ == "__main__":
    asyncio.run(main())





#!/usr/bin/env python3
"""
Tool to clean up duplicate and similar projects in the database.
This will merge "LifeLog" and "LifeLog Development" into a single "LifeLog" project.
"""

import logging
import sys
from pathlib import Path

# Add the central_server path to import from there
sys.path.append(str(Path(__file__).parent.parent / "central_server" / "processing_service"))

from db_session import get_db_session
from db_models import Project, TimelineEntryOrm as TimelineEntry
from sqlalchemy import select, update, delete

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def cleanup_duplicate_projects():
    """Clean up duplicate projects and merge them."""
    
    with get_db_session() as session:
        # Fetch all projects
        projects = session.execute(select(Project)).scalars().all()
        
        logger.info(f"Found {len(projects)} projects in database:")
        for project in projects:
            logger.info(f"  - {project.name} (ID: {project.id})")
        
        # Find projects that should be merged
        lifelog_projects = []
        for project in projects:
            if project.name.lower() in ['lifelog', 'lifelog development', 'lifelog core', 'lifelog backend', 'lifelog frontend']:
                lifelog_projects.append(project)
        
        if len(lifelog_projects) <= 1:
            logger.info("No duplicate LifeLog projects found. Nothing to merge.")
            return
        
        logger.info(f"Found {len(lifelog_projects)} LifeLog-related projects to merge:")
        for project in lifelog_projects:
            logger.info(f"  - {project.name} (ID: {project.id})")
        
        # Choose the canonical project (prefer "LifeLog" if it exists, otherwise the first one)
        canonical_project = None
        for project in lifelog_projects:
            if project.name.lower() == "lifelog":
                canonical_project = project
                break
        
        if not canonical_project:
            canonical_project = lifelog_projects[0]
        
        # Update canonical project name to standardized "LifeLog"
        canonical_project.name = "LifeLog"
        session.flush()
        
        logger.info(f"Using '{canonical_project.name}' (ID: {canonical_project.id}) as canonical project")
        
        # Get projects to be merged (excluding the canonical one)
        projects_to_merge = [p for p in lifelog_projects if p.id != canonical_project.id]
        
        if not projects_to_merge:
            logger.info("No projects to merge.")
            return
        
        # Update timeline entries to point to the canonical project
        for project_to_merge in projects_to_merge:
            logger.info(f"Merging project '{project_to_merge.name}' into '{canonical_project.name}'")
            
            # Update timeline entries
            result = session.execute(
                update(TimelineEntry)
                .where(TimelineEntry.project_id == project_to_merge.id)
                .values(project_id=canonical_project.id)
            )
            logger.info(f"Updated {result.rowcount} timeline entries")
            
            # Delete the old project
            session.delete(project_to_merge)
            logger.info(f"Deleted project '{project_to_merge.name}'")
        
        logger.info("Successfully cleaned up duplicate projects!")
        
        # Show final state
        final_projects = session.execute(select(Project)).scalars().all()
        logger.info(f"Final projects in database ({len(final_projects)}):")
        for project in final_projects:
            logger.info(f"  - {project.name} (ID: {project.id})")

def cleanup_excessive_idle_entries():
    """Clean up excessive 'Idle / Away' entries that are too short or too long."""
    
    with get_db_session() as session:
        # Find all "Idle / Away" entries
        entries = session.execute(
            select(TimelineEntry)
            .where(TimelineEntry.title.like('%Idle%Away%'))
            .order_by(TimelineEntry.start_time)
        ).scalars().all()
        
        logger.info(f"Found {len(entries)} 'Idle / Away' entries")
        
        entries_to_delete = []
        
        for entry in entries:
            duration_minutes = (entry.end_time - entry.start_time).total_seconds() / 60
            
            # Delete very short idle entries (less than 15 minutes) or 
            # suspiciously long ones (24 hours = 1440 minutes)
            if duration_minutes < 15 or duration_minutes >= 1440:
                entries_to_delete.append(entry)
                logger.debug(f"Marking idle entry for deletion: {duration_minutes:.1f} min at {entry.start_time}")
        
        logger.info(f"Will delete {len(entries_to_delete)} problematic idle entries (< 15 min or >= 24 hours)")
        
        if entries_to_delete:
            for entry in entries_to_delete:
                session.delete(entry)
            
            logger.info(f"Successfully deleted {len(entries_to_delete)} problematic idle entries")
        else:
            logger.info("No problematic idle entries to delete")

def main():
    """Main cleanup function."""
    logger.info("Starting project and timeline cleanup...")
    
    # Test database connection first
    try:
        with get_db_session() as session:
            session.execute(select(1))
            logger.info("Database connection successful")
    except Exception as e:
        logger.error(f"Cannot connect to database: {e}")
        return
    
    try:
        cleanup_duplicate_projects()
        cleanup_excessive_idle_entries()
        logger.info("Cleanup completed successfully!")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

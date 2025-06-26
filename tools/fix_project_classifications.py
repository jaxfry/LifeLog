#!/usr/bin/env python3
"""
Script to fix project classifications and consolidate duplicate projects.
This will:
1. Consolidate duplicate/similar projects into main categories
2. Update timeline entries to use the consolidated projects
3. Generate embeddings for projects
4. Delete duplicate projects
"""

import asyncio
import os
import sys
import uuid
from typing import Dict, List, Optional

import asyncpg
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# Add the backend to path so we can import models
sys.path.append('/Users/jaxon/Coding/LifeLog')

from backend.app.models import Project, TimelineEntry
from backend.app.core.settings import settings

# Project consolidation mapping: old_name -> new_name
PROJECT_CONSOLIDATION = {
    # All Hack Club related items should be consolidated into one project only if they're actual work
    "Hack Club": None,  # Delete - just browsing/casual
    "Hack Club / Lifelog": "Lifelog",  # Merge into Lifelog
    "Hack Club Shipwrecked": None,  # Delete - just browsing/casual  
    "Hack Club Summer Of Making": "Summer Of Making Bot",  # Only keep if there's actual bot work
    "Hack Club Summer Of Making / Lifelog": "Lifelog",  # Merge into Lifelog
    
    # Lifelog consolidation
    "Lifelog": "Lifelog",  # Keep this one
    "Lifelog Dockerize Project": "Lifelog",  # Merge into main Lifelog project
    
    # Keep legitimate projects
    "Summer Of Making Bot": "Summer Of Making Bot",  # Keep if it's actual development work
}

async def generate_project_embedding(project_name: str) -> List[float]:
    """Generate a proper embedding for a project name using the embedding service."""
    try:
        from backend.app.core.embeddings import get_embedding_service
        embedding_service = get_embedding_service()
        return embedding_service.generate_project_embedding(project_name)
    except Exception as e:
        print(f"Warning: Failed to generate proper embedding for '{project_name}': {e}")
        print("Falling back to simple hash-based embedding")
        
        # Fallback to simple hash-based embedding
        import hashlib
        hash_obj = hashlib.md5(project_name.lower().encode())
        hash_bytes = hash_obj.digest()
        
        # Convert to 128-dimensional vector with values between -1 and 1
        embedding = []
        for i in range(128):
            byte_val = hash_bytes[i % len(hash_bytes)]
            # Normalize to [-1, 1] range
            embedding.append((byte_val / 127.5) - 1.0)
        
        return embedding
    for i in range(128):
        byte_val = hash_bytes[i % len(hash_bytes)]
        # Normalize to [-1, 1] range
        embedding.append((byte_val / 127.5) - 1.0)
    
    return embedding

async def main():
    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL)
    
    try:
        async with AsyncSession(engine) as session:
            print("🔍 Fetching current projects...")
            
            # Get all projects
            result = await session.execute(select(Project))
            all_projects = result.scalars().all()
            
            print(f"Found {len(all_projects)} projects:")
            for project in all_projects:
                print(f"  - {project.name} ({project.id})")
            
            # Create the consolidated projects
            print("\n🏗️  Creating consolidated projects...")
            
            consolidated_projects = {}
            # Get unique target project names (excluding None values)
            unique_new_names = {name for name in PROJECT_CONSOLIDATION.values() if name is not None}
            
            for new_name in unique_new_names:
                # Check if project already exists
                result = await session.execute(
                    select(Project).where(Project.name == new_name)
                )
                existing = result.scalar_one_or_none()
                
                if existing:
                    print(f"  ✓ Project '{new_name}' already exists")
                    # Update embedding if missing
                    if not existing.embedding:
                        embedding = await generate_project_embedding(new_name)
                        await session.execute(
                            update(Project)
                            .where(Project.id == existing.id)
                            .values(embedding=embedding)
                        )
                        print(f"  ✨ Added embedding to existing project '{new_name}'")
                    consolidated_projects[new_name] = existing
                else:
                    # Create new consolidated project with embedding
                    embedding = await generate_project_embedding(new_name)
                    new_project = Project(
                        id=uuid.uuid4(),
                        name=new_name,
                        embedding=embedding
                    )
                    session.add(new_project)
                    await session.flush()
                    await session.refresh(new_project)
                    
                    consolidated_projects[new_name] = new_project
                    print(f"  ✨ Created project '{new_name}' with embedding")
            
            # Update timeline entries to point to consolidated projects or remove project assignment
            print("\n🔄 Updating timeline entries...")
            
            for old_project in all_projects:
                new_name = PROJECT_CONSOLIDATION.get(old_project.name)
                
                if new_name is None:
                    # Remove project assignment for entries that shouldn't have projects
                    await session.execute(
                        update(TimelineEntry)
                        .where(TimelineEntry.project_id == old_project.id)
                        .values(project_id=None)
                    )
                    print(f"  ✓ Removed project assignment from timeline entries for '{old_project.name}' (casual activity)")
                    
                elif new_name != old_project.name:
                    # Move to consolidated project
                    new_project = consolidated_projects[new_name]
                    await session.execute(
                        update(TimelineEntry)
                        .where(TimelineEntry.project_id == old_project.id)
                        .values(project_id=new_project.id)
                    )
                    print(f"  ✓ Moved timeline entries from '{old_project.name}' to '{new_name}'")
            
            # Delete old projects that are no longer needed
            print("\n🗑️  Removing unnecessary/duplicate projects...")
            
            for old_project in all_projects:
                new_name = PROJECT_CONSOLIDATION.get(old_project.name)
                
                # Delete if mapping to None (casual activity) or if consolidating into different project
                if new_name is None:
                    await session.execute(
                        delete(Project).where(Project.id == old_project.id)
                    )
                    print(f"  ✓ Deleted casual activity project '{old_project.name}'")
                elif new_name != old_project.name:
                    await session.execute(
                        delete(Project).where(Project.id == old_project.id)
                    )
                    print(f"  ✓ Deleted duplicate project '{old_project.name}'")
            
            # Commit all changes
            await session.commit()
            print("\n✅ Project consolidation complete!")
            
            # Show final state
            print("\n📊 Final projects:")
            result = await session.execute(
                select(Project).order_by(Project.name)
            )
            final_projects = result.scalars().all()
            
            for project in final_projects:
                has_embedding = "✅" if project.embedding is not None else "❌"
                print(f"  - {project.name} {has_embedding}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        raise
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())

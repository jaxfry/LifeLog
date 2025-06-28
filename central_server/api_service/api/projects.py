from typing import List, Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import Project as ProjectModel
from central_server.api_service.auth import get_current_active_user
from central_server.api_service import schemas

router = APIRouter()

async def get_project_by_id(db: AsyncSession, project_id: uuid.UUID) -> ProjectModel:
    """Get a project by ID"""
    result = await db.execute(select(ProjectModel).where(ProjectModel.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    return project

async def get_project_by_name(db: AsyncSession, name: str) -> ProjectModel:
    """Get a project by name"""
    result = await db.execute(select(ProjectModel).where(ProjectModel.name == name))
    return result.scalar_one_or_none()

@router.post("", response_model=schemas.Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: schemas.ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Create a new project"""
    # Check if project with this name already exists
    existing_project = await get_project_by_name(db, project_in.name)
    if existing_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project with this name already exists"
        )
    
    # Create new project
    db_project = ProjectModel(name=project_in.name)
    db.add(db_project)
    await db.commit()
    await db.refresh(db_project)
    
    return schemas.Project.model_validate(db_project)

@router.get("", response_model=List[schemas.Project])
async def get_projects(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get all projects with pagination"""
    result = await db.execute(
        select(ProjectModel)
        .offset(skip)
        .limit(limit)
        .order_by(ProjectModel.name)
    )
    projects = result.scalars().all()
    
    return [schemas.Project.model_validate(project) for project in projects]

@router.get("/{project_id}", response_model=schemas.Project)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get a project by ID"""
    project = await get_project_by_id(db, project_id)
    return schemas.Project.model_validate(project)

@router.put("/{project_id}", response_model=schemas.Project)
async def update_project(
    project_id: uuid.UUID,
    project_update: schemas.ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Update a project"""
    project = await get_project_by_id(db, project_id)
    
    # Check if new name conflicts with existing project
    if project_update.name and project_update.name != project.name:
        existing_project = await get_project_by_name(db, project_update.name)
        if existing_project:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project with this name already exists"
            )
        project.name = project_update.name
    
    await db.commit()
    await db.refresh(project)
    
    return schemas.Project.model_validate(project)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Delete a project"""
    project = await get_project_by_id(db, project_id)
    
    # Check if project has associated timeline entries
    from ..core.models import TimelineEntry
    result = await db.execute(
        select(func.count(TimelineEntry.id)).where(TimelineEntry.project_id == project_id)
    )
    entry_count = result.scalar()
    
    if entry_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete project with {entry_count} associated timeline entries"
        )
    
    await db.delete(project)
    await db.commit()

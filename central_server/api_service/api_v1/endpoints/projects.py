from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from central_server.api_service.core.database import get_db
from central_server.api_service.core.models import Project as ProjectModel, ProjectSuggestion, SuggestionStatus
from central_server.api_service.auth import require_auth
from central_server.api_service import schemas

router = APIRouter()

async def get_project_by_id(db: AsyncSession, project_id: str) -> ProjectModel:
    result = await db.execute(select(ProjectModel).where(ProjectModel.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    return project

async def get_project_by_name(db: AsyncSession, name: str) -> ProjectModel | None:
    result = await db.execute(select(ProjectModel).where(ProjectModel.name == name))
    return result.scalar_one_or_none()

@router.post("", response_model=schemas.Project, status_code=status.HTTP_201_CREATED)
async def create_project(
    project_in: schemas.ProjectCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    existing_project = await get_project_by_name(db, project_in.name)
    if existing_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project with this name already exists"
        )
    db_project = ProjectModel(name=project_in.name, manual_creation=True)
    db.add(db_project)
    await db.commit()
    await db.refresh(db_project)
    return schemas.Project.model_validate(db_project)

@router.get("", response_model=List[schemas.Project])
async def get_projects(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of items to return"),
    include_all: bool = Query(False, description="Include all projects, not just manually created ones"),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    stmt = select(ProjectModel)
    if not include_all:
        stmt = stmt.where(ProjectModel.manual_creation == True)

    result = await db.execute(
        stmt.offset(skip)
        .limit(limit)
        .order_by(ProjectModel.name)
    )
    projects = result.scalars().all()
    return [schemas.Project.model_validate(project) for project in projects]

@router.get("/{project_id}", response_model=schemas.Project)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    project = await get_project_by_id(db, project_id)
    return schemas.Project.model_validate(project)

@router.put("/{project_id}", response_model=schemas.Project)
async def update_project(
    project_id: str,
    project_update: schemas.ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    project = await get_project_by_id(db, project_id)
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
    project_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    project = await get_project_by_id(db, project_id)
    await db.delete(project)
    await db.commit()
    return None


@router.get("/suggestions/", response_model=List[schemas.ProjectSuggestion])
async def get_project_suggestions(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth),
    status: Optional[SuggestionStatus] = Query(None, description="Filter by suggestion status"),
):
    stmt = select(ProjectSuggestion)
    if status:
        stmt = stmt.where(ProjectSuggestion.status == status)
    result = await db.execute(stmt)
    suggestions = result.scalars().all()
    return [schemas.ProjectSuggestion.model_validate(s) for s in suggestions]


@router.post("/suggestions/{suggestion_id}/accept", response_model=schemas.Project, status_code=status.HTTP_201_CREATED)
async def accept_project_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    suggestion = await db.execute(
        select(ProjectSuggestion).where(ProjectSuggestion.id == suggestion_id, ProjectSuggestion.status == SuggestionStatus.pending)
    )
    suggestion_obj = suggestion.scalar_one_or_none()

    if not suggestion_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending project suggestion not found"
        )

    # Create new Project
    new_project = ProjectModel(name=suggestion_obj.suggested_name, embedding=suggestion_obj.embedding, manual_creation=True)
    db.add(new_project)
    
    # Update suggestion status
    suggestion_obj.status = SuggestionStatus.accepted
    
    await db.commit()
    await db.refresh(new_project)
    return schemas.Project.model_validate(new_project)


@router.post("/suggestions/{suggestion_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_project_suggestion(
    suggestion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_auth)
):
    suggestion = await db.execute(
        select(ProjectSuggestion).where(ProjectSuggestion.id == suggestion_id, ProjectSuggestion.status == SuggestionStatus.pending)
    )
    suggestion_obj = suggestion.scalar_one_or_none()

    if not suggestion_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending project suggestion not found"
        )

    suggestion_obj.status = SuggestionStatus.rejected
    await db.commit()
    return None
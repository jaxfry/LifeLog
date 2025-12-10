from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col, or_

from app.core.db import get_session
from app.models.files import FileAttachment
from app.core.files import create_attachment, UPLOAD_DIR
from app.api.deps import Pagination

router = APIRouter()

@router.post("/upload", response_model=FileAttachment, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    tags: Optional[str] = Form(None), # Comma separated
    description: Optional[str] = Form(None),
    event_id: Optional[UUID] = Form(None),
    timeline_id: Optional[UUID] = Form(None),
    session: AsyncSession = Depends(get_session)
):
    """
    Upload a file and create a FileAttachment record.
    """
    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    
    attachment = await create_attachment(
        session=session,
        file=file,
        category=category,
        tags=tag_list,
        description=description,
        event_id=event_id,
        timeline_id=timeline_id
    )
    
    # Trigger background processing
    if hasattr(request.app.state, "arq_pool") and request.app.state.arq_pool:
        await request.app.state.arq_pool.enqueue_job("task_process_file_batch")
        
    return attachment

@router.get("/{file_id}", response_model=FileAttachment)
async def get_file_metadata(
    file_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """
    Get metadata for a specific file.
    """
    attachment = await session.get(FileAttachment, file_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="File not found")
    return attachment

@router.get("/{file_id}/download")
async def download_file(
    file_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """
    Download the actual file content.
    """
    attachment = await session.get(FileAttachment, file_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Construct absolute path
    # stored_path is relative to UPLOAD_DIR
    file_path = UPLOAD_DIR / attachment.stored_path
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Physical file not found")
        
    return FileResponse(
        path=file_path,
        filename=attachment.filename,
        media_type=attachment.mime_type
    )

@router.get("/", response_model=List[FileAttachment])
async def list_files(
    pagination: Pagination = Depends(),
    category: Optional[str] = None,
    q: Optional[str] = None,
    session: AsyncSession = Depends(get_session)
):
    """
    List files with optional filtering.
    """
    query = select(FileAttachment).order_by(col(FileAttachment.created_at).desc())
    
    if category:
        query = query.where(FileAttachment.category == category)
        
    if q:
        query = query.where(
            or_(
                col(FileAttachment.filename).ilike(f"%{q}%"),
                col(FileAttachment.description).ilike(f"%{q}%")
            )
        )
        
    query = query.offset(pagination.offset).limit(pagination.limit)
    
    result = await session.execute(query)
    return result.scalars().all()

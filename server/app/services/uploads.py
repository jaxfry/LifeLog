from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.captures import UploadSession


async def expire_upload_sessions(session: AsyncSession) -> int:
    """Expire abandoned resumable uploads and remove only their owned temp files."""
    now = datetime.now(UTC).replace(tzinfo=None)
    uploads = (
        await session.execute(
            select(UploadSession).where(
                UploadSession.expires_at < now,
                UploadSession.status.in_(("pending", "uploading")),
            )
        )
    ).scalars().all()
    for upload in uploads:
        upload.status = "expired"
        upload.updated_at = now
        session.add(upload)
        Path(upload.temp_path).unlink(missing_ok=True)
    await session.commit()
    return len(uploads)

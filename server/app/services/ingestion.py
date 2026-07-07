import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.logger import get_logger
from app.models.ingest import RawLog

logger = get_logger(__name__)


def calculate_payload_hash(payload: Dict[str, Any]) -> str:
    payload_str = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()


async def ingest_log(
    session: AsyncSession,
    device_id: str,
    extension_id: str,
    payload: Dict[str, Any],
    client_timestamp: Optional[datetime] = None,
    client_timezone: Optional[str] = None,
) -> tuple[RawLog, bool]:
    payload_hash = calculate_payload_hash(payload)

    statement = select(RawLog).where(
        RawLog.device_id == device_id,
        RawLog.payload_hash == payload_hash,
    )
    result = await session.execute(statement)
    existing = result.scalars().first()

    if existing:
        return existing, False

    raw_log = RawLog(
        device_id=device_id,
        extension_id=extension_id,
        payload=payload,
        payload_hash=payload_hash,
        client_timestamp=client_timestamp,
        client_timezone=client_timezone,
    )
    session.add(raw_log)

    try:
        await session.commit()
        await session.refresh(raw_log)
        return raw_log, True
    except IntegrityError:
        await session.rollback()
        result = await session.execute(statement)
        existing = result.scalars().first()
        if existing:
            return existing, False
        raise

from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.database import get_session
from app.core.security import decode_access_token, hash_api_key
from app.models.auth import Device, User

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/token", auto_error=False
)
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise credentials_exception

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise credentials_exception
    return user


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough privileges",
        )
    return current_user


async def verify_device(
    api_key: str = Security(api_key_header_scheme),
    session: AsyncSession = Depends(get_session),
) -> Device:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key required. Include X-API-Key header.",
        )

    api_key_hash = hash_api_key(api_key)
    statement = select(Device).where(Device.api_key_hash == api_key_hash)
    result = await session.execute(statement)
    device = result.scalars().first()

    if not device or not device.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    return device


class Pagination:
    def __init__(
        self,
        limit: int = Query(default=100, ge=1, le=1000),
        offset: int = Query(default=0, ge=0),
    ):
        self.limit = limit
        self.offset = offset

from fastapi import Query, Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from app.models.config import Device, User
from app.core.db import get_session
import hashlib
from jose import jwt, JWTError
from app.core.security import SECRET_KEY, ALGORITHM

# Define the security scheme
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/token")

async def verify_api_key(
    api_key: str = Security(api_key_header_scheme),
    session: AsyncSession = Depends(get_session)
) -> Device:
    """
    Validate API key and return the associated device.
    Raises 403 if invalid or missing.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key required. Include X-API-Key header."
        )
    
    # Hash the provided key
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    
    # Look up device by hash
    statement = select(Device).where(Device.api_key_hash == api_key_hash)
    result = await session.execute(statement)
    device = result.scalars().first()
    
    if not device:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )
    
    return device

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = await session.get(User, user_id)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=400, detail="The user doesn't have enough privileges"
        )
    return current_user

class Pagination:
    def __init__(
        self,
        limit: int = Query(default=100, ge=1, le=1000, description="Number of items to return"),
        offset: int = Query(default=0, ge=0, description="Number of items to skip")
    ):
        self.limit = limit
        self.offset = offset

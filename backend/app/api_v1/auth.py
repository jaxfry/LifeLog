import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

from backend.app.core.settings import settings
from backend.app.schemas import User, UserInDB, TokenPayload
from backend.app.core.db import get_db
from backend.app.models import User as UserModel

logger = logging.getLogger(__name__)

# Constants
CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

# Configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

# --- Password Operations ---
class PasswordManager:
    """Handles password hashing and verification."""
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

# --- Token Operations ---
class TokenManager:
    """Handles JWT token creation and validation."""
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        to_encode = data.copy()
        expire = TokenManager._calculate_expiry(expires_delta)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    @staticmethod
    def _calculate_expiry(expires_delta: Optional[timedelta]) -> datetime:
        if expires_delta:
            return datetime.now(timezone.utc) + expires_delta
        return datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

# --- User Repository ---
class UserRepository:
    """Handles user database operations using SQLAlchemy async session."""
    def __init__(self, db: AsyncSession):
        self.db = db
    async def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        try:
            result = await self.db.execute(
                select(UserModel).where(UserModel.username == username)
            )
            user_obj = result.scalar_one_or_none()
            if not user_obj:
                user_obj = await self._handle_missing_user(username)
            return self._obj_to_user(user_obj) if user_obj else None
        except Exception as e:
            logger.error(f"Database error in get_user_by_username: {e}")
            return None
    async def _handle_missing_user(self, username: str):
        if self._should_create_test_user(username):
            return await self._create_test_user_if_none_exist(username)
        return None
    def _should_create_test_user(self, username: str) -> bool:
        return username == settings.TEST_USER_USERNAME
    async def _create_test_user_if_none_exist(self, username: str):
        result = await self.db.execute(select(UserModel))
        total_users = len(result.scalars().all())
        if total_users == 0:
            return await self._create_test_user(username)
        return None
    async def _create_test_user(self, username: str):
        try:
            user_id = uuid.uuid4()
            hashed_password = PasswordManager.get_password_hash(settings.TEST_USER_PASSWORD)
            user_obj = UserModel(id=user_id, username=username, hashed_password=hashed_password)
            self.db.add(user_obj)
            await self.db.commit()
            logger.info(f"Development: Created test user '{username}'")
            return user_obj
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create test user '{username}': {e}")
            return None
    def _obj_to_user(self, obj) -> UserInDB:
        return UserInDB(id=obj.id, username=obj.username, hashed_password=obj.hashed_password)

# --- Authentication Service ---
class AuthenticationService:
    """Handles authentication logic."""
    def __init__(self, db: AsyncSession):
        self.user_repo = UserRepository(db)
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        user = await self.user_repo.get_user_by_username(username)
        if not user or not PasswordManager.verify_password(password, user.hashed_password):
            return None
        return User(id=user.id, username=user.username)
    async def get_current_user_from_token(self, token: str) -> User:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username = payload.get("sub")
            if not username:
                raise CREDENTIALS_EXCEPTION
            user = await self.user_repo.get_user_by_username(username)
            if not user:
                raise CREDENTIALS_EXCEPTION
            return User(id=user.id, username=user.username)
        except (JWTError, ValidationError):
            raise CREDENTIALS_EXCEPTION

# --- Dependency Functions ---
async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    auth_service = AuthenticationService(db)
    return await auth_service.get_current_user_from_token(token)

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    return current_user

# --- Legacy Functions (for backward compatibility) ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return PasswordManager.verify_password(plain_password, hashed_password)
def get_password_hash(password: str) -> str:
    return PasswordManager.get_password_hash(password)
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    return TokenManager.create_access_token(data, expires_delta)
# Legacy get_user is now async
async def get_user(db: AsyncSession, username: str) -> Optional[UserInDB]:
    user_repo = UserRepository(db)
    return await user_repo.get_user_by_username(username)

# --- Type Aliases ---
AuthFormDep = Annotated[OAuth2PasswordRequestForm, Depends()]
DBDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_active_user)]
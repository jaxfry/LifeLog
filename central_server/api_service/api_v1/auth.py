import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated
import logging

import duckdb
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

from backend.app.core.settings import settings
from backend.app.schemas import User, UserInDB, TokenPayload
from backend.app.api_v1.deps import get_db
from backend.app.core.utils import with_db_write_retry

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
        """Verify a plain password against its hash."""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Generate a hash from a plain password."""
        return pwd_context.hash(password)

# --- Token Operations ---
class TokenManager:
    """Handles JWT token creation and validation."""
    
    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a new access token."""
        to_encode = data.copy()
        expire = TokenManager._calculate_expiry(expires_delta)
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    @staticmethod
    def _calculate_expiry(expires_delta: Optional[timedelta]) -> datetime:
        """Calculate token expiry time."""
        if expires_delta:
            return datetime.now(timezone.utc) + expires_delta
        return datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

# --- User Repository ---
class UserRepository:
    """Handles user database operations."""
    
    def __init__(self, db: duckdb.DuckDBPyConnection):
        self.db = db
    
    def get_user_by_username(self, username: str) -> Optional[UserInDB]:
        """Retrieve a user by username."""
        try:
            user_row = self._fetch_user_row(username)
            if not user_row:
                user_row = self._handle_missing_user(username)
            
            return self._row_to_user(user_row) if user_row else None
        except duckdb.Error as e:
            logger.error(f"Database error in get_user_by_username: {e}")
            return None
    
    def _fetch_user_row(self, username: str) -> Optional[tuple]:
        """Fetch user row from database."""
        return self.db.execute(
            "SELECT id, username, hashed_password FROM users WHERE username = ?", 
            [username]
        ).fetchone()
    
    def _handle_missing_user(self, username: str) -> Optional[tuple]:
        """Handle case when user doesn't exist - create test user if needed."""
        if self._should_create_test_user(username):
            return self._create_test_user_if_none_exist(username)
        return None
    
    def _should_create_test_user(self, username: str) -> bool:
        """Check if we should attempt to create the test user."""
        return username == settings.TEST_USER_USERNAME
    
    def _create_test_user_if_none_exist(self, username: str) -> Optional[tuple]:
        """Create test user if no users exist in the database."""
        total_users = self._count_total_users()
        if total_users == 0:
            return self._create_test_user(username)
        return None
    
    def _count_total_users(self) -> int:
        """Count total number of users in database."""
        result = self.db.execute("SELECT COUNT(*) FROM users").fetchone()
        return result[0] if result else 0
    
    @with_db_write_retry()
    def _create_test_user(self, username: str) -> Optional[tuple]:
        """Create the test user for development."""
        try:
            user_id = uuid.uuid4()
            hashed_password = PasswordManager.get_password_hash(settings.TEST_USER_PASSWORD)
            
            self.db.execute(
                "INSERT INTO users (id, username, hashed_password) VALUES (?, ?, ?)",
                [str(user_id), username, hashed_password]
            )
            self.db.commit()
            
            logger.info(f"Development: Created test user '{username}'")
            return self._fetch_user_row(username)
            
        except duckdb.Error as e:
            self.db.rollback()
            logger.error(f"Failed to create test user '{username}': {e}")
            return None
    
    def _row_to_user(self, row: tuple) -> UserInDB:
        """Convert database row to UserInDB object."""
        return UserInDB(id=row[0], username=row[1], hashed_password=row[2])

# --- Authentication Service ---
class AuthenticationService:
    """Handles authentication logic."""
    
    def __init__(self, db: duckdb.DuckDBPyConnection):
        self.user_repo = UserRepository(db)
    
    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate a user with username and password."""
        user = self.user_repo.get_user_by_username(username)
        if not user or not PasswordManager.verify_password(password, user.hashed_password):
            return None
        return User(id=user.id, username=user.username)
    
    def get_current_user_from_token(self, token: str) -> User:
        """Extract and validate user from JWT token."""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            username = payload.get("sub")
            if not username:
                raise CREDENTIALS_EXCEPTION
                
            user = self.user_repo.get_user_by_username(username)
            if not user:
                raise CREDENTIALS_EXCEPTION
                
            return User(id=user.id, username=user.username)
            
        except (JWTError, ValidationError):
            raise CREDENTIALS_EXCEPTION

# --- Dependency Functions ---
async def get_current_user(
    db: Annotated[duckdb.DuckDBPyConnection, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    """FastAPI dependency to get current authenticated user."""
    auth_service = AuthenticationService(db)
    return auth_service.get_current_user_from_token(token)

async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """FastAPI dependency to get current active user."""
    # Future: Add is_active check here if needed
    return current_user

# --- Legacy Functions (for backward compatibility) ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Legacy function - use PasswordManager.verify_password instead."""
    return PasswordManager.verify_password(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Legacy function - use PasswordManager.get_password_hash instead."""
    return PasswordManager.get_password_hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Legacy function - use TokenManager.create_access_token instead."""
    return TokenManager.create_access_token(data, expires_delta)

def get_user(db: duckdb.DuckDBPyConnection, username: str) -> Optional[UserInDB]:
    """Legacy function - use UserRepository.get_user_by_username instead."""
    user_repo = UserRepository(db)
    return user_repo.get_user_by_username(username)

# --- Type Aliases ---
AuthFormDep = Annotated[OAuth2PasswordRequestForm, Depends()]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_active_user)]
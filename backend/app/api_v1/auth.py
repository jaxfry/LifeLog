from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

import duckdb
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

from backend.app.core.settings import settings
from backend.app.schemas import User, UserInDB, TokenPayload
from backend.app.api_v1.deps import get_db

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 Scheme
# tokenUrl will point to the /api/v1/auth/token endpoint
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

# --- Utility Functions ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

# --- User Fetching ---
def get_user(db: duckdb.DuckDBPyConnection, username: str) -> Optional[UserInDB]:
    """
    Retrieves a user from the database.
    NOTE: This assumes a 'users' table exists with 'username' and 'hashed_password' columns.
    This table needs to be added to schema.sql.
    """
    try:
        # The 'users' table is now defined in schema.sql.
        # This logic ensures a test user exists if the table is empty, for development convenience.
        # In production, user creation should be handled via dedicated endpoints or admin tools.
        
        # Check if the test user exists
        user_row = db.execute("SELECT id, username, hashed_password FROM users WHERE username = ?", [settings.TEST_USER_USERNAME]).fetchone()

        if not user_row:
            # Check if any users exist at all. If not, create the test user.
            total_users_count_row = db.execute("SELECT COUNT(*) FROM users").fetchone()
            if total_users_count_row and total_users_count_row[0] == 0:
                import uuid
                test_username = settings.TEST_USER_USERNAME
                test_password = settings.TEST_USER_PASSWORD
                hashed_password = get_password_hash(test_password)
                user_id = uuid.uuid4()
                try:
                    db.execute("INSERT INTO users (id, username, hashed_password) VALUES (?, ?, ?)", [str(user_id), test_username, hashed_password])
                    db.commit()
                    print(f"Development: Created test user '{test_username}'.")
                    # Re-fetch the user_row for the current username after creation
                    if username == test_username: # if the user we are trying to get is the one just created
                         user_row = db.execute("SELECT id, username, hashed_password FROM users WHERE username = ?", [username]).fetchone()
                except duckdb.Error as insert_e:
                    db.rollback()
                    print(f"Development: Failed to create test user '{test_username}': {insert_e}")
                    # Potentially raise or handle this error, but for now, just log it.
        
        # If user_row is still None (either not the test user, or test user creation failed/not applicable),
        # try fetching the requested username directly if it wasn't the test user.
        if not user_row and username != settings.TEST_USER_USERNAME:
             user_row = db.execute("SELECT id, username, hashed_password FROM users WHERE username = ?", [username]).fetchone()

        if user_row:
            return UserInDB(id=user_row[0], username=user_row[1], hashed_password=user_row[2])
    except duckdb.Error as e:
        print(f"Database error in get_user: {e}") # Log this properly
        return None
    return None

# --- Dependency for Current User ---
async def get_current_user(
    db: Annotated[duckdb.DuckDBPyConnection, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)]
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: Optional[str] = payload.get("sub")
        if username is None: # Should not happen if "sub" is always present in valid tokens
            raise credentials_exception
        token_data = TokenPayload(sub=username) # username is now confirmed to be str
    except (JWTError, ValidationError):
        raise credentials_exception
    
    # Explicitly check token_data.sub is not None before passing to get_user
    if token_data.sub is None:
        raise credentials_exception # Should be caught by username check above, but for type safety

    user = get_user(db, username=token_data.sub) # token_data.sub is now known to be str
    if user is None:
        raise credentials_exception
    return User(id=user.id, username=user.username) # Return the User schema, not UserInDB

async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    # If we add an "is_active" flag to the user model, we'd check it here.
    # For now, any authenticated user is considered active.
    # if not current_user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

# --- OAuth2PasswordRequestForm dependency for token endpoint ---
# This is how FastAPI gets username and password from the request form
AuthFormDep = Annotated[OAuth2PasswordRequestForm, Depends()]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_active_user)]
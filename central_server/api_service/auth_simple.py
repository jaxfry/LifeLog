"""
Simplified single-user authentication system for LifeLog.

This replaces the multi-user authentication system with a single-user approach
while maintaining security through password protection and JWT tokens.
"""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
import logging

from central_server.api_service.core.settings import settings

logger = logging.getLogger(__name__)

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

# Exception for unauthorized access
CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def authenticate_user(username: str, password: str) -> bool:
    """Authenticate the single user against configured credentials"""
    if username != settings.LIFELOG_USERNAME:
        return False
    
    if password != settings.LIFELOG_PASSWORD:
        return False
    
    return True

def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Get the current authenticated user (returns username since we only have one user)"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise CREDENTIALS_EXCEPTION
        
        # Verify this is our configured user
        if username != settings.LIFELOG_USERNAME:
            raise CREDENTIALS_EXCEPTION
            
        return username
    except JWTError:
        raise CREDENTIALS_EXCEPTION

def require_auth(current_user: str = Depends(get_current_user)) -> str:
    """Dependency to require authentication for endpoints"""
    return current_user

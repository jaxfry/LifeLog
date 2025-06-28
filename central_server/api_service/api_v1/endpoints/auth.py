from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from central_server.api_service.core.database import get_db
from central_server.api_service.core.settings import settings
from central_server.api_service.auth import authenticate_user, create_access_token, create_user, get_user_by_username, get_current_active_user
from central_server.api_service import schemas

router = APIRouter()

@router.post("/token", response_model=schemas.Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db)
):
    """Login and get access token"""
    user = await authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.post("/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: schemas.UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user"""
    # Check if user already exists
    existing_user = await get_user_by_username(db, user_create.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Create new user
    user = await create_user(db, user_create)
    return schemas.User.model_validate(user)

@router.get("/me", response_model=schemas.User)
async def read_users_me(
    current_user: schemas.User = Depends(get_current_active_user)
):
    """Get current user info"""
    return current_user

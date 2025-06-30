from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from central_server.api_service.core.settings import settings
from central_server.api_service.auth import authenticate_user, create_access_token, require_auth
from central_server.api_service import schemas

router = APIRouter()

@router.post("/token", response_model=schemas.Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
):
    """Login and get access token"""
    user_authenticated = authenticate_user(form_data.username, form_data.password)
    if not user_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": form_data.username}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }

@router.get("/me")
async def read_current_user(
    current_user: str = Depends(require_auth)
):
    """Get current user info"""
    return {"username": current_user}

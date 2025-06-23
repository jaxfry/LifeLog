import logging
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import duckdb

from backend.app.core.settings import settings
from backend.app.core.db import initialize_database, get_db_connection, DB_FILE
from backend.app.schemas import Token, User, UserCreate # Assuming UserCreate will be used for a user creation endpoint later
from backend.app.api_v1 import auth as v1_auth
from backend.app.api_v1.deps import get_db # For get_current_user, etc.
from backend.app.api_v1.endpoints import projects as projects_router
from backend.app.api_v1.endpoints import timeline as timeline_router
from backend.app.api_v1.endpoints import events as events_router
from backend.app.api_v1.endpoints import day as day_router
from backend.app.api_v1.endpoints import system as system_router

# Routers for future endpoints (to be created)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - [%(name)s] - %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up LifeLog API...")
    if not DB_FILE.exists():
        logger.info(f"Database file not found at {DB_FILE}. Initializing database...")
        try:
            initialize_database()
            logger.info("Database initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            # Potentially exit or prevent app from fully starting if DB is critical
    else:
        logger.info(f"Database file found at {DB_FILE}.")
    
    # Create a test user if it doesn't exist (for development convenience)
    # This is a simplified version; in production, manage users via dedicated tools/endpoints.
    try:
        with get_db_connection() as db:
            # The get_user function in auth.py now handles test user creation if no users exist.
            # We can call it here to ensure the user is created on startup if needed.
            _ = v1_auth.get_user(db, settings.TEST_USER_USERNAME)
    except Exception as e:
        logger.error(f"Could not ensure test user exists: {e}")

    yield
    # Shutdown
    logger.info("Shutting down LifeLog API...")

app = FastAPI(
    title="LifeLog API",
    description="The backend API for the LifeLog application, featuring robust features and ease of use.",
    version="0.1.0", # Initial version
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Frontend dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API Router for v1 ---
api_v1_router = APIRouter(prefix=settings.API_V1_STR)

# Authentication endpoint
@api_v1_router.post("/auth/token", response_model=Token, tags=["Authentication"])
async def login_for_access_token(
    form_data: v1_auth.AuthFormDep,
    db: duckdb.DuckDBPyConnection = Depends(get_db)
):
    user = v1_auth.get_user(db, form_data.username)
    if not user or not v1_auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = v1_auth.create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# Placeholder for user self-registration (example)
# @api_v1_router.post("/auth/register", response_model=User, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
# async def register_user(
#     user_in: UserCreate,
#     db: duckdb.DuckDBPyConnection = Depends(get_db)
# ):
#     existing_user = v1_auth.get_user(db, user_in.username)
#     if existing_user:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Username already registered"
#         )
#     hashed_password = v1_auth.get_password_hash(user_in.password)
#     # This part needs a proper "create_user" function that inserts into DB and returns UserInDB
#     # For now, this is a conceptual placeholder
#     # new_user_db = create_user_in_db(db, username=user_in.username, hashed_password=hashed_password)
#     # return User.from_orm(new_user_db) # Adapt to Pydantic v2 from_attributes
#     raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="User registration not yet implemented")


# Include the projects router
api_v1_router.include_router(projects_router.router, prefix="/projects", tags=["Projects"])
# Include the timeline router
api_v1_router.include_router(timeline_router.router, prefix="/timeline", tags=["Timeline Entries"])
# Include the events router
api_v1_router.include_router(events_router.router, prefix="/events", tags=["Events"])
# Include the day router
api_v1_router.include_router(day_router.router, prefix="/day", tags=["Daily Data"])
# Include the system router
api_v1_router.include_router(system_router.router, prefix="/system", tags=["System"])

# TODO: Include other routers once they are created


# Include the v1 router in the main app
app.include_router(api_v1_router)

# Basic root endpoint
@app.get("/", tags=["Root"])
async def read_root():
    return {"message": "Welcome to the LifeLog API. See /api/v1/docs for documentation."}

if __name__ == "__main__":
    import uvicorn
    # This is for development purposes. For production, use a process manager like Gunicorn.
    logger.info("Starting Uvicorn server for development...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

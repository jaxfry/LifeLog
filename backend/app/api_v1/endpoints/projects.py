import uuid
from typing import List, Optional, Annotated
import duckdb
from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.app import schemas # Use a more specific import if schemas grow large
from backend.app.api_v1.deps import get_db
from backend.app.api_v1.auth import get_current_active_user # For securing endpoints

router = APIRouter()

# --- CRUD Operations for Projects ---

def create_project_db(db: duckdb.DuckDBPyConnection, project: schemas.ProjectCreate) -> Optional[schemas.Project]:
    project_id = uuid.uuid4()
    # Embedding is not handled here as per schema, would be a separate process or internal.
    try:
        db.execute("INSERT INTO projects (id, name) VALUES (?, ?)", [str(project_id), project.name])
        db.commit()
        # Fetch the created project to return it
        created_project_row = db.execute("SELECT id, name FROM projects WHERE id = ?", [str(project_id)]).fetchone()
        if created_project_row:
            return schemas.Project(id=created_project_row[0], name=created_project_row[1])
    except duckdb.ConstraintException: # Handles unique constraint violations (e.g., duplicate name if UNIQUE index on name)
        # The schema.sql has CREATE UNIQUE INDEX projects_name_ci_idx ON projects (lower(name));
        # So this will catch duplicate names (case-insensitive)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project with name '{project.name}' already exists.",
        )
    except duckdb.Error as e:
        db.rollback()
        # Log the error e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create project.")
    return None # Should not be reached if successful or HTTPException raised

def get_project_db(db: duckdb.DuckDBPyConnection, project_id: uuid.UUID) -> Optional[schemas.Project]:
    project_row = db.execute("SELECT id, name FROM projects WHERE id = ?", [str(project_id)]).fetchone()
    if project_row:
        return schemas.Project(id=project_row[0], name=project_row[1])
    return None

def get_projects_db(db: duckdb.DuckDBPyConnection, skip: int = 0, limit: int = 100) -> List[schemas.Project]:
    project_rows = db.execute("SELECT id, name FROM projects ORDER BY name LIMIT ? OFFSET ?", [limit, skip]).fetchall()
    return [schemas.Project(id=row[0], name=row[1]) for row in project_rows]

def update_project_db(db: duckdb.DuckDBPyConnection, project_id: uuid.UUID, project_update: schemas.ProjectUpdate) -> Optional[schemas.Project]:
    # Check if project exists
    existing_project = get_project_db(db, project_id)
    if not existing_project:
        return None

    fields_to_update = project_update.model_dump(exclude_unset=True)
    if not fields_to_update:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update.")

    # Currently, only 'name' can be updated.
    if "name" in fields_to_update:
        try:
            db.execute("UPDATE projects SET name = ? WHERE id = ?", [fields_to_update["name"], str(project_id)])
            db.commit()
        except duckdb.ConstraintException:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Another project with name '{fields_to_update['name']}' already exists.",
            )
        except duckdb.Error as e:
            db.rollback()
            # Log error e
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not update project name.")
    
    return get_project_db(db, project_id)


def delete_project_db(db: duckdb.DuckDBPyConnection, project_id: uuid.UUID) -> bool:
    # Check if project exists
    existing_project = get_project_db(db, project_id)
    if not existing_project:
        return False # Or raise 404 here directly

    # Check for associations (e.g., timeline_entries) before deleting
    # This check needs to be adapted based on actual foreign key constraints and desired behavior.
    # The schema.sql does not have ON DELETE CASCADE/SET NULL for timeline_entries.project_id.
    # So, we should prevent deletion if there are linked entries.
    linked_entries_count_row = db.execute(
        "SELECT COUNT(*) FROM timeline_entries WHERE project_id = ?", [str(project_id)]
    ).fetchone()
    
    if linked_entries_count_row and linked_entries_count_row[0] > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project cannot be deleted: It is associated with {linked_entries_count_row[0]} timeline entries. Please reassign or delete them first.",
        )

    try:
        db.execute("DELETE FROM projects WHERE id = ?", [str(project_id)])
        db.commit()
        return True # Successfully deleted
    except duckdb.Error as e:
        db.rollback()
        # Log error e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not delete project.")


# --- API Endpoints for Projects ---

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

@router.post("", response_model=schemas.Project, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: schemas.ProjectCreate,
    db: DBDep,
    current_user: CurrentUserDep  # Secure this endpoint
):
    """
    Create a new project.
    """
    created_project = create_project_db(db, project_in)
    if not created_project:
        # This case should ideally be handled by specific exceptions within create_project_db
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create project.")
    return created_project

@router.get("", response_model=List[schemas.Project])
def read_projects(
    db: DBDep,
    current_user: CurrentUserDep, # Secure this endpoint
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return")
):
    """
    Retrieve all projects with pagination.
    """
    return get_projects_db(db, skip=skip, limit=limit)

@router.get("/{project_id}", response_model=schemas.Project)
def read_project(
    project_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep # Secure this endpoint
):
    """
    Get a specific project by its ID.
    """
    db_project = get_project_db(db, project_id)
    if db_project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return db_project

@router.put("/{project_id}", response_model=schemas.Project)
def update_project(
    project_id: uuid.UUID,
    project_in: schemas.ProjectUpdate,
    db: DBDep,
    current_user: CurrentUserDep # Secure this endpoint
):
    """
    Update an existing project.
    """
    updated_project = update_project_db(db, project_id, project_in)
    if updated_project is None: # Means project was not found initially by update_project_db
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return updated_project

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep # Secure this endpoint
):
    """
    Delete a project.
    Will fail if the project is associated with any timeline entries.
    """
    project_to_delete = get_project_db(db, project_id) # Check existence first
    if not project_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    # delete_project_db now raises HTTPException on failure or if associated
    delete_project_db(db, project_id)
    return # FastAPI handles 204 No Content response automatically
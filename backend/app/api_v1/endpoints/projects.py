import uuid
from typing import List, Optional, Annotated
import logging
import duckdb
from fastapi import APIRouter, Depends, HTTPException, status, Query

from backend.app import schemas
from backend.app.api_v1.deps import get_db
from backend.app.api_v1.auth import get_current_active_user
from backend.app.core.utils import with_db_write_retry

logger = logging.getLogger(__name__)
router = APIRouter()

CurrentUserDep = Annotated[schemas.User, Depends(get_current_active_user)]
DBDep = Annotated[duckdb.DuckDBPyConnection, Depends(get_db)]

class ProjectRepository:
    """Handles database operations for projects."""
    
    def __init__(self, db: duckdb.DuckDBPyConnection):
        self.db = db
    
    @with_db_write_retry()
    def create_project(self, project_data: schemas.ProjectCreate) -> schemas.Project:
        """
        Create a new project in the database.
        
        Raises:
            HTTPException: If project creation fails or name already exists
        """
        project_id = uuid.uuid4()
        
        try:
            self.db.execute(
                "INSERT INTO projects (id, name) VALUES (?, ?)", 
                [str(project_id), project_data.name]
            )
            self.db.commit()
            return self._fetch_project_by_id(project_id)
            
        except duckdb.ConstraintException:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project with name '{project_data.name}' already exists."
            )
        except duckdb.Error as e:
            self.db.rollback()
            logger.error(f"Failed to create project: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Could not create project."
            )
    
    def get_project_by_id(self, project_id: uuid.UUID) -> Optional[schemas.Project]:
        """Get a project by its ID."""
        try:
            return self._fetch_project_by_id(project_id)
        except Exception as e:
            logger.error(f"Error fetching project {project_id}: {e}")
            return None
    
    def get_projects(self, skip: int = 0, limit: int = 100) -> List[schemas.Project]:
        """Get paginated list of projects."""
        try:
            project_rows = self.db.execute(
                "SELECT id, name FROM projects ORDER BY name LIMIT ? OFFSET ?", 
                [limit, skip]
            ).fetchall()
            return [schemas.Project(id=row[0], name=row[1]) for row in project_rows]
        except duckdb.Error as e:
            logger.error(f"Error fetching projects: {e}")
            return []
    
    @with_db_write_retry()
    def update_project(self, project_id: uuid.UUID, update_data: schemas.ProjectUpdate) -> Optional[schemas.Project]:
        """
        Update an existing project.
        
        Returns:
            Updated project or None if project not found
            
        Raises:
            HTTPException: If update operation fails
        """
        if not self._project_exists(project_id):
            return None
        
        fields_to_update = update_data.model_dump(exclude_unset=True)
        if not fields_to_update:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="No fields to update."
            )
        
        if "name" in fields_to_update:
            self._update_project_name(project_id, fields_to_update["name"])
        
        return self.get_project_by_id(project_id)
    
    @with_db_write_retry()
    def delete_project(self, project_id: uuid.UUID) -> bool:
        """
        Delete a project if it has no associated timeline entries.
        
        Returns:
            True if deleted successfully, False if project not found
            
        Raises:
            HTTPException: If project has associated entries or deletion fails
        """
        if not self._project_exists(project_id):
            return False
        
        self._check_project_associations(project_id)
        
        try:
            self.db.execute("DELETE FROM projects WHERE id = ?", [str(project_id)])
            self.db.commit()
            return True
        except duckdb.Error as e:
            self.db.rollback()
            logger.error(f"Failed to delete project {project_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Could not delete project."
            )
    
    def _fetch_project_by_id(self, project_id: uuid.UUID) -> schemas.Project:
        """Fetch project by ID, assuming it exists."""
        project_row = self.db.execute(
            "SELECT id, name FROM projects WHERE id = ?", 
            [str(project_id)]
        ).fetchone()
        
        if not project_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found"
            )
        
        return schemas.Project(id=project_row[0], name=project_row[1])
    
    def _project_exists(self, project_id: uuid.UUID) -> bool:
        """Check if project exists."""
        result = self.db.execute(
            "SELECT COUNT(*) FROM projects WHERE id = ?", 
            [str(project_id)]
        ).fetchone()
        return result is not None and result[0] > 0
    
    def _update_project_name(self, project_id: uuid.UUID, new_name: str) -> None:
        """Update project name."""
        try:
            self.db.execute(
                "UPDATE projects SET name = ? WHERE id = ?", 
                [new_name, str(project_id)]
            )
            self.db.commit()
        except duckdb.ConstraintException:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Another project with name '{new_name}' already exists."
            )
        except duckdb.Error as e:
            self.db.rollback()
            logger.error(f"Failed to update project name: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Could not update project name."
            )
    
    def _check_project_associations(self, project_id: uuid.UUID) -> None:
        """Check if project has associated timeline entries."""
        linked_entries_result = self.db.execute(
            "SELECT COUNT(*) FROM timeline_entries WHERE project_id = ?", 
            [str(project_id)]
        ).fetchone()
        
        if linked_entries_result and linked_entries_result[0] > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Project cannot be deleted: It is associated with {linked_entries_result[0]} timeline entries. Please reassign or delete them first."
            )

class ProjectService:
    """Business logic for project operations."""
    
    def __init__(self, repository: ProjectRepository):
        self.repository = repository
    
    def create_project(self, project_data: schemas.ProjectCreate) -> schemas.Project:
        """Create a new project."""
        return self.repository.create_project(project_data)
    
    def get_project(self, project_id: uuid.UUID) -> schemas.Project:
        """Get a project by ID."""
        project = self.repository.get_project_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Project not found"
            )
        return project
    
    def get_projects(self, skip: int = 0, limit: int = 100) -> List[schemas.Project]:
        """Get paginated list of projects."""
        return self.repository.get_projects(skip, limit)
    
    def update_project(self, project_id: uuid.UUID, update_data: schemas.ProjectUpdate) -> schemas.Project:
        """Update an existing project."""
        updated_project = self.repository.update_project(project_id, update_data)
        if not updated_project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Project not found"
            )
        return updated_project
    
    def delete_project(self, project_id: uuid.UUID) -> None:
        """Delete a project."""
        deleted = self.repository.delete_project(project_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail="Project not found"
            )

# --- API Endpoints ---

@router.post("", response_model=schemas.Project, status_code=status.HTTP_201_CREATED)
def create_project(
    project_in: schemas.ProjectCreate,
    db: DBDep,
    current_user: CurrentUserDep
):
    """Create a new project."""
    repository = ProjectRepository(db)
    service = ProjectService(repository)
    return service.create_project(project_in)

@router.get("", response_model=List[schemas.Project])
def read_projects(
    db: DBDep,
    current_user: CurrentUserDep,
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return")
):
    """Retrieve all projects with pagination."""
    repository = ProjectRepository(db)
    service = ProjectService(repository)
    return service.get_projects(skip, limit)

@router.get("/{project_id}", response_model=schemas.Project)
def read_project(
    project_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep
):
    """Get a specific project by its ID."""
    repository = ProjectRepository(db)
    service = ProjectService(repository)
    return service.get_project(project_id)

@router.put("/{project_id}", response_model=schemas.Project)
def update_project(
    project_id: uuid.UUID,
    project_in: schemas.ProjectUpdate,
    db: DBDep,
    current_user: CurrentUserDep
):
    """Update an existing project."""
    repository = ProjectRepository(db)
    service = ProjectService(repository)
    return service.update_project(project_id, project_in)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    db: DBDep,
    current_user: CurrentUserDep
):
    """Delete a project. Will fail if the project is associated with any timeline entries."""
    repository = ProjectRepository(db)
    service = ProjectService(repository)
    service.delete_project(project_id)
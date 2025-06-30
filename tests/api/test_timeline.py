import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, date
import uuid
from central_server.api_service.main import app
from central_server.api_service.api_v1.endpoints.timeline import router
from central_server.api_service import schemas

client = TestClient(router)

@pytest.fixture
def mock_db_session():
    with patch('central_server.api_service.api_v1.endpoints.timeline.get_db') as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value = mock_session
        yield mock_session

@pytest.fixture
def mock_auth():
    with patch('central_server.api_service.api_v1.endpoints.timeline.require_auth') as mock_auth:
        mock_auth.return_value = "admin"  # Return the username
        yield mock_auth

def test_create_timeline_entry(mock_db_session, mock_auth):
    project_id = uuid.uuid4()
    entry_in = schemas.TimelineEntryCreate(
        start_time=datetime(2025, 1, 1, 9, 0, 0),
        end_time=datetime(2025, 1, 1, 10, 0, 0),
        title="Test Entry",
        summary="This is a test entry",
        project_id=project_id
    )

    mock_project_result = MagicMock()
    mock_project_result.scalar_one_or_none.return_value = schemas.Project(id=project_id, name="Test Project")
    mock_db_session.execute.return_value = mock_project_result

    response = client.post("", json=entry_in.model_dump_json())
    assert response.status_code == 201

def test_get_timeline_entries(mock_db_session, mock_auth):
    response = client.get("")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_update_timeline_entry(mock_db_session, mock_auth):
    entry_id = uuid.uuid4()
    entry_update = schemas.TimelineEntryUpdate(title="Updated Title")

    mock_entry = MagicMock()
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_entry

    response = client.put(f"/{entry_id}", json=entry_update.model_dump_json())
    assert response.status_code == 200

def test_delete_timeline_entry(mock_db_session, mock_auth):
    entry_id = uuid.uuid4()
    mock_entry = MagicMock()
    mock_db_session.execute.return_value.scalar_one_or_none.return_value = mock_entry

    response = client.delete(f"/{entry_id}")
    assert response.status_code == 204
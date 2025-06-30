import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
from central_server.api_service.main import app
from central_server.api_service.api_v1.endpoints.day import router
from central_server.api_service import schemas

client = TestClient(router)

@pytest.fixture
def mock_db_session():
    with patch('central_server.api_service.api_v1.endpoints.day.get_db') as mock_get_db:
        mock_session = MagicMock()
        mock_get_db.return_value = mock_session
        yield mock_session

@pytest.fixture
def mock_auth():
    with patch('central_server.api_service.api_v1.endpoints.day.require_auth') as mock_auth:
        mock_auth.return_value = "admin"  # Return the username
        yield mock_auth

def test_read_day_data_success(mock_db_session, mock_auth):
    # Mock data
    test_date = date(2025, 1, 1)
    project = schemas.Project(id=1, name="Test Project", description="A test project")
    timeline_entries = [
        schemas.TimelineEntry(
            id=1,
            event_type="test_event",
            start_time=datetime(2025, 1, 1, 9, 0, 0),
            end_time=datetime(2025, 1, 1, 10, 0, 0),
            data={},
            project=project,
            local_day=test_date
        )
    ]

    # Mock database call
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = timeline_entries
    mock_db_session.execute.return_value = mock_result

    # Make the request
    response = client.get(f"/{test_date.isoformat()}")

    # Assertions
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == test_date.isoformat()
    assert len(data["timeline_entries"]) == 1
    assert data["stats"]["total_events"] == 1
    assert data["stats"]["top_project"] == "Test Project"

def test_read_day_data_invalid_date_format(mock_db_session, mock_auth):
    response = client.get("/2025-13-40")
    assert response.status_code == 422 # FastAPI's validation error for regex mismatch

def test_read_day_data_no_data(mock_db_session, mock_auth):
    test_date = date(2025, 1, 2)
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db_session.execute.return_value = mock_result

    response = client.get(f"/{test_date.isoformat()}")

    assert response.status_code == 200
    data = response.json()
    assert data["date"] == test_date.isoformat()
    assert len(data["timeline_entries"]) == 0
    assert data["stats"]["total_events"] == 0
    assert data["stats"]["top_project"] is None

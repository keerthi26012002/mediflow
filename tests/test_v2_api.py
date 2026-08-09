import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

# Import app
from app.main import app
from app.auth import get_current_user

@pytest.fixture(autouse=True)
def setup_v2_auth():
    app.dependency_overrides[get_current_user] = lambda: {"email": "admin@mediflow.ai", "role": "ADMIN", "is_active": True}
    yield
    app.dependency_overrides.pop(get_current_user, None)

client = TestClient(app)

@patch("app.routers.v2_api.get_database")
def test_get_hospital_state_empty(mock_get_db):
    """Verify GET /hospital/state returns correct placeholders when DB is empty."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_find_one = AsyncMock(return_value=None)
    mock_collection.find_one = mock_find_one
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db

    response = client.get("/hospital/state")
    assert response.status_code == 200
    res_data = response.json()
    assert "general_beds_available" in res_data
    assert res_data["general_beds_available"] == 300
    assert res_data["general_beds_occupied"] == 0

@patch("app.routers.v2_api.get_database")
def test_get_capacity_metrics_empty(mock_get_db):
    """Verify GET /capacity returns default metrics when DB is empty."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_find_one = AsyncMock(return_value=None)
    mock_collection.find_one = mock_find_one
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db

    response = client.get("/capacity")
    assert response.status_code == 200
    res_data = response.json()
    assert "capacity_score" in res_data
    assert res_data["capacity_score"] == 100.0
    assert res_data["bottleneck_detected"] == "NOMINAL"

@patch("app.routers.v2_api.get_database")
def test_get_predictions_empty(mock_get_db):
    """Verify GET /prediction returns default prediction values when DB is empty."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_find_one = AsyncMock(return_value=None)
    mock_collection.find_one = mock_find_one
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db

    response = client.get("/prediction")
    assert response.status_code == 200
    res_data = response.json()
    assert "beds_required" in res_data
    assert res_data["beds_required"] == 0.0
    assert res_data["model_loaded"] is False

@patch("app.routers.v2_api.get_database")
def test_get_active_alerts_empty(mock_get_db):
    """Verify GET /alerts returns empty list when DB is empty."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_to_list = AsyncMock(return_value=[])
    mock_cursor.to_list = mock_to_list
    mock_collection.find.return_value = mock_cursor
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db

    response = client.get("/alerts")
    assert response.status_code == 200
    assert response.json() == []

@patch("app.routers.v2_api.get_database")
def test_get_active_recommendations_empty(mock_get_db):
    """Verify GET /recommendations returns empty list when DB is empty."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_to_list = AsyncMock(return_value=[])
    mock_cursor.to_list = mock_to_list
    mock_collection.find.return_value = mock_cursor
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db

    response = client.get("/recommendations")
    assert response.status_code == 200
    assert response.json() == []

@patch("app.consumer.process_stream_update")
def test_post_manual_events(mock_process):
    """Verify POST /events triggers processing update and returns success status."""
    mock_process.return_value = AsyncMock()
    event_payload = {
        "patient_id": "test-patient-v2",
        "timestamp": "2026-06-29 23:25:00",
        "general_beds_available": 150
    }
    response = client.post("/events", json=event_payload)
    assert response.status_code == 200
    assert response.json() == {"status": "success", "message": "Event processed successfully"}

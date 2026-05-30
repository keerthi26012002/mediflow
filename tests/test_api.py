import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

# Import app
from app.main import app

client = TestClient(app)

def test_health_check():
    """Verify that the health check endpoint returns 200 and OK status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MediFlow AI API"}

@patch("app.routers.dashboard.get_database")
def test_dashboard_live_empty(mock_get_db):
    """Verify dashboard/live behaves correctly when database is empty."""
    # Mock MongoDB find_one returning None
    mock_db = MagicMock()
    mock_collection = MagicMock()
    
    # Async mock for find_one
    mock_find_one = AsyncMock(return_value=None)
    mock_collection.find_one = mock_find_one
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db
    
    response = client.get("/dashboard/live")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["patients_per_hour"] == 0
    assert res_data["icu_beds_free"] == 0
    assert res_data["avg_wait_time"] == 0.0
    assert res_data["overload_status"] is False

@patch("app.routers.predictions.get_database")
def test_history_admissions_empty(mock_get_db):
    """Verify that history/admissions paginates properly and returns empty list when no data."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    
    # Mock async cursor
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    
    mock_to_list = AsyncMock(return_value=[])
    mock_cursor.to_list = mock_to_list
    
    mock_collection.find.return_value = mock_cursor
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db
    
    response = client.get("/history/admissions?skip=0&limit=10")
    assert response.status_code == 200
    assert response.json() == []

def test_predict_admission_stub():
    """Verify on-demand stub inference endpoint returns the correct structure."""
    event_payload = {
        "patient_id": "test-patient-123",
        "timestamp": "30-05-2026 23:30",
        "age": 45,
        "gender": "F",
        "wait_time": 25,
        "department": "Emergency",
        "admitted": True,
        "satisfaction_score": 4.0,
        "race": "Other",
        "icu_beds_available": 10,
        "ambulance_requests": 2,
        "doctor_availability": 15,
        "oxygen_utilization": 82.5,
        "emergency_severity_level": 2
    }
    
    response = client.post("/history/predict/admission", json=event_payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["patient_id"] == "test-patient-123"
    assert "predicted_admission" in res_data
    assert "admission_proba" in res_data
    assert res_data["model_loaded"] is False  # In stub mode, should be False

def test_forecast_beds_stub():
    """Verify that bed forecast endpoint returns predicted occupancy points."""
    response = client.get("/forecast/beds?hours=12")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["hours"] == 12
    assert len(res_data["forecast"]) == 12
    assert "ts" in res_data["forecast"][0]
    assert "predicted_occupancy" in res_data["forecast"][0]
    assert res_data["model_loaded"] is False  # Stubbed by default

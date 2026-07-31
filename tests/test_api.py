import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock

# Import app
from app.main import app
from app.auth import get_current_user
from app.rate_limiter import rate_limit

@pytest.fixture(autouse=True)
def setup_api_auth():
    app.dependency_overrides[get_current_user] = lambda: {"email": "admin@mediflow.ai", "role": "Admin", "is_active": True}
    app.dependency_overrides[rate_limit] = lambda: None
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(rate_limit, None)

client = TestClient(app)

def test_health_check():
    """Verify that the health check endpoint returns 200 and OK status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MediFlow AI API"}

@patch("app.routers.dashboard.get_database")
def test_dashboard_live_empty(mock_get_db):
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

@patch("app.routers.dashboard.get_database")
def test_dashboard_operations_empty(mock_get_db):
    """Verify the operations snapshot returns the architecture/control-tower contract."""
    mock_db = MagicMock()
    mock_collection = MagicMock()
    mock_collection.find_one = AsyncMock(return_value=None)
    mock_collection.count_documents = AsyncMock(return_value=0)
    mock_db.__getitem__.return_value = mock_collection
    mock_get_db.return_value = mock_db

    response = client.get("/dashboard/operations")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["digital_twin_state"] == "Awaiting Live Data"
    assert "bed_capacity" in res_data
    assert "emergency_resources" in res_data
    assert len(res_data["kafka_topics"]) >= 5
    assert len(res_data["security_controls"]) >= 4
    assert res_data["recommendations"]

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

@patch("app.ml.inference._xgb_model", None)
@patch("app.ml.inference.load_models")
def test_predict_admission_stub(mock_load_models):
    """Verify on-demand stub inference endpoint returns the correct structure."""
    mock_load_models.return_value = None
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

@patch("app.ml.inference._prophet_model", None)
@patch("app.ml.inference.load_models")
def test_forecast_beds_stub(mock_load_models):
    """Verify that bed forecast endpoint returns predicted occupancy points."""
    mock_load_models.return_value = None
    response = client.get("/forecast/beds?hours=12")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["hours"] == 12
    assert len(res_data["forecast"]) == 12
    assert "ts" in res_data["forecast"][0]
    assert "predicted_occupancy" in res_data["forecast"][0]
    assert res_data["model_loaded"] is False  # Stubbed by default

def test_landing_page_route():
    """Verify that GET / returns the public TemplateMo 618 adapted landing page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "MediFlow AI" in html
    assert "Intelligent Hospital" in html
    assert "Capacity Management" in html
    assert "Access Dashboard" in html
    assert "Built for Every Hospital Role" in html
    assert "Zero-Trust Enterprise Governance" in html

def test_login_page_route():
    """Verify that GET /login returns the dedicated login screen."""
    response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "Sign In to Control Center" in html
    assert "Quick Role Demo Logins" in html
    assert "admin@mediflow.ai" in html

def test_dashboard_page_route():
    """Verify that GET /dashboard returns the authenticated dashboard view."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    html = response.text
    assert "MediFlow AI Operations Control" in html
    assert "dashboard.js" in html

def test_landing_static_assets():
    """Verify that landing CSS and JS are served cleanly."""
    res_css = client.get("/landing/landing.css")
    assert res_css.status_code == 200
    assert "landing-body" in res_css.text

    res_js = client.get("/landing/landing.js")
    assert res_js.status_code == 200
    assert "toggleLandingTheme" in res_js.text



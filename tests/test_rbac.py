import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from app.main import app
from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    normalize_role,
    Role
)
from app.rate_limiter import rate_limit

# TestClient instance without global dependency overrides
client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_client_state():
    app.dependency_overrides.clear()
    app.dependency_overrides[rate_limit] = lambda: None
    client.cookies.clear()
    yield
    app.dependency_overrides.clear()
    client.cookies.clear()

# ==================== 1. PASSWORD & TOKEN CRYPTO TESTS ====================

def test_password_hashing_and_verification():
    """Verifies that bcrypt hashing generates secure hashes and properly validates matches."""
    raw_pwd = "DoctorSecurePass2026!"
    hashed = hash_password(raw_pwd)
    assert hashed != raw_pwd
    assert verify_password(raw_pwd, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False

def test_jwt_access_and_refresh_token_payload():
    """Verifies standard token fields: sub, type, exp, and role normalization."""
    token = create_access_token({"sub": "doctor@mediflow.ai", "role": "DOCTOR", "user_id": "u123"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "doctor@mediflow.ai"
    assert payload["role"] == "DOCTOR"
    assert payload["type"] == "access"
    assert "exp" in payload

    ref_token = create_refresh_token({"sub": "doctor@mediflow.ai", "role": "DOCTOR"})
    ref_payload = decode_token(ref_token)
    assert ref_payload["type"] == "refresh"

def test_role_normalization():
    """Verifies normalize_role converts various aliases and case variants to canonical uppercase."""
    assert normalize_role("admin") == "ADMIN"
    assert normalize_role("ADMINISTRATOR") == "ADMIN"
    assert normalize_role("doctor") == "DOCTOR"
    assert normalize_role("Physician") == "DOCTOR"
    assert normalize_role("clinician") == "DOCTOR"
    assert normalize_role("operations_manager") == "OPERATIONS_MANAGER"
    assert normalize_role("ops") == "OPERATIONS_MANAGER"
    assert normalize_role("operations") == "OPERATIONS_MANAGER"
    assert normalize_role("data_analyst") == "DATA_ANALYST"
    assert normalize_role("analyst") == "DATA_ANALYST"
    assert normalize_role(Role.ADMIN) == "ADMIN"

# ==================== 2. AUTHENTICATION & LOGIN EDGE CASES ====================

def test_login_invalid_email_domain():
    """Verifies that login rejects non-mediflow emails with HTTP 400."""
    response = client.post("/auth/login", json={
        "email": "hacker@gmail.com",
        "password": "Password123!"
    })
    assert response.status_code == 400
    assert "Unauthorized email domain" in response.json()["detail"]

def test_login_short_password():
    """Verifies that login rejects passwords shorter than 8 characters."""
    response = client.post("/auth/login", json={
        "email": "test@mediflow.ai",
        "password": "short"
    })
    assert response.status_code == 400
    assert "at least 8 characters" in response.json()["detail"]

@pytest.mark.parametrize("email,expected_role", [
    ("admin@mediflow.ai", "ADMIN"),
    ("doctor@mediflow.ai", "DOCTOR"),
    ("ops@mediflow.ai", "OPERATIONS_MANAGER"),
    ("analyst@mediflow.ai", "DATA_ANALYST"),
])
@patch("app.routers.auth.get_database")
def test_login_success_default_accounts(mock_get_db, email, expected_role):
    """Verifies all 4 default accounts authenticate and return the expected role."""
    mock_db = MagicMock()
    mock_db.__getitem__.return_value.find_one = AsyncMock(return_value=None)
    mock_db.__getitem__.return_value.insert_one = AsyncMock()
    mock_get_db.return_value = mock_db

    response = client.post("/auth/login", json={
        "email": email,
        "password": "mediflow123"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "access_token" in data
    assert data["user"]["role"] == expected_role

@patch("app.routers.auth.get_database")
def test_role_tampering_is_prevented(mock_get_db):
    """Verifies that client-supplied role in login body is strictly ignored in favor of DB role."""
    mock_db = MagicMock()
    mock_users = MagicMock()
    mock_audit = MagicMock()
    
    # User stored in DB is DOCTOR
    mock_users.find_one = AsyncMock(return_value={
        "_id": "doc_123",
        "email": "doctor@mediflow.ai",
        "username": "dr_smith",
        "hashed_password": hash_password("DoctorPass123!"),
        "role": "DOCTOR",
        "is_active": True
    })
    mock_users.update_one = AsyncMock()
    mock_audit.insert_one = AsyncMock()

    def get_coll(name):
        if name == "users":
            return mock_users
        return mock_audit

    mock_db.__getitem__.side_effect = get_coll
    mock_get_db.return_value = mock_db

    # Client attempts privilege escalation by requesting role ADMIN
    response = client.post("/auth/login", json={
        "email": "doctor@mediflow.ai",
        "password": "DoctorPass123!",
        "role": "ADMIN"
    })
    assert response.status_code == 200
    data = response.json()
    # Server assigns DOCTOR strictly from the DB record
    assert data["user"]["role"] == "DOCTOR"
    payload = decode_token(data["access_token"])
    assert payload["role"] == "DOCTOR"

@patch("app.routers.auth.get_database")
def test_login_deactivated_user_blocked(mock_get_db):
    """Verifies that inactive user accounts are blocked with 401."""
    mock_db = MagicMock()
    mock_users = MagicMock()
    mock_audit = MagicMock()

    mock_users.find_one = AsyncMock(return_value={
        "_id": "inactive_123",
        "email": "fired@mediflow.ai",
        "hashed_password": hash_password("ValidPassword123!"),
        "role": "DOCTOR",
        "is_active": False
    })
    mock_audit.insert_one = AsyncMock()

    def get_coll(name):
        return mock_users if name == "users" else mock_audit

    mock_db.__getitem__.side_effect = get_coll
    mock_get_db.return_value = mock_db

    response = client.post("/auth/login", json={
        "email": "fired@mediflow.ai",
        "password": "ValidPassword123!"
    })
    assert response.status_code == 401
    assert "deactivated" in response.json()["detail"]

def test_unauthenticated_request_returns_401():
    """Verifies that protected routes return 401 when no token is supplied."""
    response = client.get("/users")
    assert response.status_code == 401

def test_invalid_token_returns_401():
    """Verifies that forged or corrupted tokens return 401."""
    response = client.get("/users", headers={"Authorization": "Bearer forged.jwt.token"})
    assert response.status_code == 401

# ==================== 3. PARAMETERIZED RBAC MATRIX TESTS ====================

SAMPLE_PAYLOADS = {
    "/history/predict/admission": {
        "patient_id": "PT-001",
        "timestamp": "2026-09-08 12:00:00",
        "age": 55,
        "gender": "M",
        "wait_time": 20,
        "department": "Emergency",
        "admitted": True,
        "satisfaction_score": 4.0,
        "race": "Other",
        "icu_beds_available": 10,
        "ambulance_requests": 1,
        "doctor_availability": 10,
        "oxygen_utilization": 70.0,
        "emergency_severity_level": 3
    },
    "/predict/admission": {
        "patient_id": "PT-001",
        "timestamp": "2026-09-08 12:00:00",
        "age": 55,
        "gender": "M",
        "wait_time": 20,
        "department": "Emergency",
        "admitted": True,
        "satisfaction_score": 4.0,
        "race": "Other",
        "icu_beds_available": 10,
        "ambulance_requests": 1,
        "doctor_availability": 10,
        "oxygen_utilization": 70.0,
        "emergency_severity_level": 3
    },
    "/policies": {"policy": "PRESERVE_ICU"},
    "/events": {
        "patient_id": "EVT-001",
        "timestamp": "2026-09-08 12:00:00",
        "general_beds_available": 150
    },
    "/users": {
        "email": "testnewuser@mediflow.ai",
        "username": "testnewuser",
        "password": "Password123!",
        "role": "DOCTOR",
        "is_active": True
    },
    "/users/mock_id": {"is_active": False}
}

ENDPOINT_MATRIX = [
    # Auth & Profile
    ("GET", "/auth/me", ["ADMIN", "DOCTOR", "OPERATIONS_MANAGER", "DATA_ANALYST"]),
    # Overview
    ("GET", "/dashboard/live", ["ADMIN", "DOCTOR", "OPERATIONS_MANAGER", "DATA_ANALYST"]),
    # Digital Twin & ICU
    ("GET", "/hospital/state", ["ADMIN", "DOCTOR", "OPERATIONS_MANAGER"]),
    ("GET", "/icu/status", ["ADMIN", "DOCTOR", "OPERATIONS_MANAGER"]),
    # Clinical
    ("GET", "/history/admissions", ["ADMIN", "DOCTOR"]),
    ("POST", "/history/predict/admission", ["ADMIN", "DOCTOR"]),
    ("POST", "/predict/admission", ["ADMIN", "DOCTOR"]),
    # Operations
    ("GET", "/capacity", ["ADMIN", "OPERATIONS_MANAGER"]),
    ("GET", "/dashboard/operations", ["ADMIN", "OPERATIONS_MANAGER"]),
    ("GET", "/recommendations", ["ADMIN", "OPERATIONS_MANAGER"]),
    ("GET", "/policies", ["ADMIN", "OPERATIONS_MANAGER"]),
    ("POST", "/policies", ["ADMIN", "OPERATIONS_MANAGER"]),
    ("POST", "/events", ["ADMIN", "OPERATIONS_MANAGER"]),
    # Analytics & MLOps
    ("GET", "/forecast/beds", ["ADMIN", "DATA_ANALYST"]),
    ("GET", "/evaluations", ["ADMIN", "DATA_ANALYST"]),
    # Shared Operations + Analytics
    ("GET", "/prediction", ["ADMIN", "OPERATIONS_MANAGER", "DATA_ANALYST"]),
    ("GET", "/anomalies", ["ADMIN", "OPERATIONS_MANAGER", "DATA_ANALYST"]),
    # Shared Clinical + Operations
    ("GET", "/alerts", ["ADMIN", "DOCTOR", "OPERATIONS_MANAGER"]),
    # Admin Only
    ("GET", "/users", ["ADMIN"]),
    ("POST", "/users", ["ADMIN"]),
    ("GET", "/users/mock_id", ["ADMIN"]),
    ("PATCH", "/users/mock_id", ["ADMIN"]),
    ("DELETE", "/users/mock_id", ["ADMIN"]),
    ("GET", "/audit/logs", ["ADMIN"]),
]

ALL_ROLES = ["ADMIN", "DOCTOR", "OPERATIONS_MANAGER", "DATA_ANALYST"]

@pytest.mark.parametrize("method,path,allowed_roles", ENDPOINT_MATRIX)
@pytest.mark.parametrize("test_role", ALL_ROLES)
def test_rbac_endpoint_authorization_matrix(method, path, allowed_roles, test_role):
    """
    Tests every cell in the ROLE × ENDPOINT matrix:
    - Returns non-403 for authorized roles.
    - Returns HTTP 403 Forbidden for unauthorized roles.
    """
    token = create_access_token({
        "email": f"{test_role.lower()}@mediflow.ai",
        "role": test_role,
        "is_active": True,
        "user_id": f"u_{test_role.lower()}"
    })
    headers = {"Authorization": f"Bearer {token}"}
    payload = SAMPLE_PAYLOADS.get(path, {})

    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.skip.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_coll.find.return_value = mock_cursor
    mock_coll.find_one = AsyncMock(return_value=None)
    mock_coll.count_documents = AsyncMock(return_value=0)
    mock_coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock_id_123"))
    mock_coll.replace_one = AsyncMock()
    mock_coll.update_one = AsyncMock()
    mock_db.__getitem__.return_value = mock_coll

    with patch("app.auth.get_database", return_value=mock_db), \
         patch("app.routers.v2_api.get_database", return_value=mock_db), \
         patch("app.routers.forecast.get_database", return_value=mock_db), \
         patch("app.routers.predictions.get_database", return_value=mock_db), \
         patch("app.routers.dashboard.get_database", return_value=mock_db), \
         patch("app.routers.users.get_database", return_value=mock_db), \
         patch("app.consumer.process_stream_update", new_callable=AsyncMock), \
         patch("app.ml.inference._xgb_model", None), \
         patch("app.ml.inference._prophet_model", None), \
         patch("app.ml.inference.load_models", return_value=None):

        if method == "GET":
            response = client.get(path, headers=headers)
        elif method == "POST":
            response = client.post(path, headers=headers, json=payload)
        elif method == "PATCH":
            response = client.patch(path, headers=headers, json=payload)
        elif method == "DELETE":
            response = client.delete(path, headers=headers)

        if test_role in allowed_roles:
            assert response.status_code not in [401, 403], (
                f"Role '{test_role}' unexpectedly blocked from {method} {path}: {response.text}"
            )
        else:
            assert response.status_code == 403, (
                f"Role '{test_role}' was allowed access to {method} {path}, expected 403! Status: {response.status_code}"
            )
            assert "lacks permission" in response.json().get("detail", "")

# ==================== 4. WEBSOCKET AUTHORIZATION TESTS ====================

def test_websocket_connection_unauthenticated_rejected():
    """Verifies that WebSocket handshake without valid token is closed with WS 1008 policy violation."""
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/alerts") as ws:
            pass

def test_websocket_connection_authenticated_success():
    """Verifies that WebSocket handshake with valid JWT connects successfully."""
    token = create_access_token({"email": "admin@mediflow.ai", "role": "ADMIN"})
    with client.websocket_connect(f"/ws/alerts?token={token}") as ws:
        assert ws is not None

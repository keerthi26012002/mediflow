import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth import create_access_token, decode_token

client = TestClient(app)

def test_jwt_generation_and_decoding():
    user_data = {"email": "test@mediflow.ai", "role": "Doctor"}
    token = create_access_token(user_data)
    assert token is not None
    
    payload = decode_token(token)
    assert payload is not None
    assert payload["email"] == "test@mediflow.ai"
    assert payload["role"] == "Doctor"
    assert payload["type"] == "access"

def test_login_success():
    payload = {
        "email": "admin@mediflow.ai",
        "password": "mediflow123",
        "role": "Admin"
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["user"]["email"] == "admin@mediflow.ai"
    assert "access_token" in res_data
    
    # Check that cookies are set
    assert "access_token" in response.cookies
    assert "refresh_token" in response.cookies

def test_login_invalid_email():
    payload = {
        "email": "admin@gmail.com",
        "password": "mediflow123",
        "role": "Admin"
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 400
    assert "Unauthorized email domain" in response.json()["detail"]

def test_login_short_password():
    payload = {
        "email": "admin@mediflow.ai",
        "password": "short",
        "role": "Admin"
    }
    response = client.post("/auth/login", json=payload)
    assert response.status_code == 400
    assert "Password must be at least 8" in response.json()["detail"]

def test_logout():
    response = client.post("/auth/logout")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

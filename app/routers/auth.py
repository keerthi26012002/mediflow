from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from pydantic import BaseModel
from app.db import get_database
from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user
)

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str
    role: str

class LoginResponse(BaseModel):
    status: str
    user: dict
    access_token: str

@router.post("/login", response_model=LoginResponse)
async def login(response: Response, request: Request, credentials: LoginRequest):
    email = credentials.email.strip()
    password = credentials.password
    role = credentials.role
    
    # 1. Validation
    if not email.endswith("@mediflow.ai"):
        raise HTTPException(
            status_code=400,
            detail="Unauthorized email domain. Use a @mediflow.ai account."
        )
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long."
        )
        
    # Standard static user check (dev baseline)
    if email == "admin@mediflow.ai" and password != "mediflow123":
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials for Admin."
        )

    # 2. Token Generation
    user_data = {"email": email, "role": role}
    access_token = create_access_token(user_data)
    refresh_token = create_refresh_token(user_data)
    
    # 3. Set HttpOnly Cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=15 * 60,
        expires=15 * 60,
        samesite="lax",
        secure=False  # True in prod
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        expires=7 * 24 * 60 * 60,
        samesite="lax",
        secure=False  # True in prod
    )
    
    # 4. Insert Audit Log
    try:
        db = get_database()
        audit_event = {
            "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
            "parsed_timestamp": datetime.now(),
            "event_type": "USER_LOGIN",
            "email": email,
            "role": role,
            "ip_address": request.client.host if request.client else "unknown",
            "status": "SUCCESS",
            "details": f"User {email} successfully logged in as {role}"
        }
        await db["audit_logs"].insert_one(audit_event)
    except Exception as e:
        print(f"Error saving audit log: {e}")
        
    return LoginResponse(
        status="success",
        user={"email": email, "role": role},
        access_token=access_token
    )

@router.post("/refresh")
async def refresh_tokens(request: Request, response: Response):
    # Retrieve refresh token from cookies
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token missing. Please sign in again."
        )
        
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token."
        )
        
    email = payload.get("email")
    role = payload.get("role")
    user_data = {"email": email, "role": role}
    
    # Generate new access token
    new_access_token = create_access_token(user_data)
    
    # Set cookies
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        max_age=15 * 60,
        expires=15 * 60,
        samesite="lax",
        secure=False
    )
    
    return {
        "status": "success",
        "access_token": new_access_token
    }

@router.post("/logout")
async def logout(response: Response, request: Request):
    # Get current user for audit logs before deleting cookies
    email = "unknown"
    role = "unknown"
    
    # Extract access token to get user info if possible
    access_token = request.cookies.get("access_token")
    if access_token:
        payload = decode_token(access_token)
        if payload:
            email = payload.get("email", "unknown")
            role = payload.get("role", "unknown")
            
    # Clear cookies
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    
    # Insert Audit Log
    try:
        db = get_database()
        audit_event = {
            "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
            "parsed_timestamp": datetime.now(),
            "event_type": "USER_LOGOUT",
            "email": email,
            "role": role,
            "ip_address": request.client.host if request.client else "unknown",
            "status": "SUCCESS",
            "details": f"User {email} successfully logged out"
        }
        await db["audit_logs"].insert_one(audit_event)
    except Exception as e:
        print(f"Error saving audit log: {e}")
        
    return {"status": "success", "message": "Successfully logged out."}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

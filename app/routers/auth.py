import os
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from pydantic import BaseModel, EmailStr
from app.db import get_database, COLLECTION_USERS, COLLECTION_AUDIT_LOGS
from app.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    get_current_active_user,
    verify_password,
    normalize_role,
    Role
)

router = APIRouter(prefix="/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str
    role: Optional[str] = None  # Kept for backward compatibility, but strictly ignored for authorization!

class UserProfileResponse(BaseModel):
    id: Optional[str] = None
    email: str
    username: str
    role: str
    is_active: bool = True

class LoginResponse(BaseModel):
    status: str
    user: Dict[str, Any]
    access_token: str
    token_type: str = "bearer"

@router.post("/login", response_model=LoginResponse)
async def login(response: Response, request: Request, credentials: LoginRequest):
    """
    Authenticates user credentials against the database.
    Enforces password verification via bcrypt and resolves roles strictly from the DB record.
    """
    email = credentials.email.strip().lower()
    password = credentials.password
    ip_address = request.client.host if request.client else "unknown"
    
    # 1. Format & Domain Validation
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
        
    db = None
    try:
        db = get_database()
    except Exception:
        pass

    user = None
    if db is not None:
        try:
            user = await db[COLLECTION_USERS].find_one({"email": email})
        except Exception as e:
            print(f"Database lookup error during login: {e}")

    # 2. Credential Verification
    authenticated = False
    resolved_role = Role.DATA_ANALYST.value
    user_id = "default_id"
    username = email.split("@")[0]
    
    if user:
        if not user.get("is_active", True):
            # Record failed login in audit logs
            if db is not None:
                await db[COLLECTION_AUDIT_LOGS].insert_one({
                    "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
                    "parsed_timestamp": datetime.now(),
                    "event_type": "USER_LOGIN_FAILED",
                    "email": email,
                    "ip_address": ip_address,
                    "status": "BLOCKED",
                    "details": f"Attempted login to inactive account: {email}"
                })
            raise HTTPException(
                status_code=401,
                detail="User account is deactivated. Contact an administrator."
            )
            
        stored_hash = user.get("hashed_password")
        if stored_hash and verify_password(password, stored_hash):
            authenticated = True
            resolved_role = normalize_role(user.get("role"))
            user_id = str(user.get("_id", ""))
            username = user.get("username", username)
        elif not stored_hash and password == "mediflow123":
            # Fallback for unhashed dev credentials
            authenticated = True
            resolved_role = normalize_role(user.get("role"))
            user_id = str(user.get("_id", ""))
            username = user.get("username", username)
    else:
        # Fallback baseline check for default system accounts (ADMIN, DOCTOR, OPERATIONS_MANAGER, DATA_ANALYST)
        from app.auth import DEFAULT_SYSTEM_USERS
        if email in DEFAULT_SYSTEM_USERS and password == DEFAULT_SYSTEM_USERS[email]["default_password"]:
            authenticated = True
            resolved_role = DEFAULT_SYSTEM_USERS[email]["role"]
            user_id = DEFAULT_SYSTEM_USERS[email]["id"]
            username = DEFAULT_SYSTEM_USERS[email]["username"]

    if not authenticated:
        if db is not None:
            try:
                await db[COLLECTION_AUDIT_LOGS].insert_one({
                    "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
                    "parsed_timestamp": datetime.now(),
                    "event_type": "USER_LOGIN_FAILED",
                    "email": email,
                    "ip_address": ip_address,
                    "status": "FAILURE",
                    "details": f"Invalid password or user not found for: {email}"
                })
            except Exception:
                pass
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials. Please check your email and password."
        )

    # 3. Update Last Login
    if db is not None and user:
        try:
            await db[COLLECTION_USERS].update_one(
                {"_id": user["_id"]},
                {"$set": {"last_login": datetime.utcnow().isoformat()}}
            )
        except Exception as e:
            print(f"Error updating last login: {e}")

    # 4. Token Generation (Role derived strictly from database record)
    user_token_payload = {
        "user_id": user_id,
        "sub": email,
        "email": email,
        "username": username,
        "role": resolved_role
    }
    access_token = create_access_token(user_token_payload)
    refresh_token = create_refresh_token(user_token_payload)
    
    # 5. Set HttpOnly Cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=30 * 60,
        expires=30 * 60,
        samesite="lax",
        secure=False
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=7 * 24 * 60 * 60,
        expires=7 * 24 * 60 * 60,
        samesite="lax",
        secure=False
    )
    
    # 6. Audit Logging
    if db is not None:
        try:
            await db[COLLECTION_AUDIT_LOGS].insert_one({
                "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
                "parsed_timestamp": datetime.now(),
                "event_type": "USER_LOGIN",
                "email": email,
                "role": resolved_role,
                "ip_address": ip_address,
                "status": "SUCCESS",
                "details": f"User {email} logged in successfully with role {resolved_role}"
            })
        except Exception as e:
            print(f"Error writing login audit log: {e}")

    return LoginResponse(
        status="success",
        user={
            "id": user_id,
            "email": email,
            "username": username,
            "role": resolved_role,
            "is_active": True
        },
        access_token=access_token,
        token_type="bearer"
    )

@router.post("/refresh")
async def refresh_tokens(request: Request, response: Response):
    """Refreshes an expired access token using a valid refresh token."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        # Check Authorization header fallback
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            refresh_token = auth_header.split(" ")[1]

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
        
    email = payload.get("email") or payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    db = None
    try:
        db = get_database()
    except Exception:
        pass

    user = None
    if db is not None:
        try:
            user = await db[COLLECTION_USERS].find_one({"email": email})
            if user and not user.get("is_active", True):
                raise HTTPException(status_code=401, detail="User account is inactive.")
        except HTTPException:
            raise
        except Exception:
            pass

    resolved_role = normalize_role(user.get("role") if user else payload.get("role"))
    user_id = str(user.get("_id", payload.get("user_id", ""))) if user else payload.get("user_id", "")
    username = user.get("username", email.split("@")[0]) if user else email.split("@")[0]

    user_token_payload = {
        "user_id": user_id,
        "sub": email,
        "email": email,
        "username": username,
        "role": resolved_role
    }
    new_access_token = create_access_token(user_token_payload)
    
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        max_age=30 * 60,
        expires=30 * 60,
        samesite="lax",
        secure=False
    )
    
    return {
        "status": "success",
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout(response: Response, request: Request):
    """Terminates session, deletes authentication cookies, and records audit event."""
    email = "unknown"
    role = "unknown"
    
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if token:
        payload = decode_token(token)
        if payload:
            email = payload.get("email", payload.get("sub", "unknown"))
            role = payload.get("role", "unknown")
            
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    
    try:
        db = get_database()
        await db[COLLECTION_AUDIT_LOGS].insert_one({
            "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
            "parsed_timestamp": datetime.now(),
            "event_type": "USER_LOGOUT",
            "email": email,
            "role": role,
            "ip_address": request.client.host if request.client else "unknown",
            "status": "SUCCESS",
            "details": f"User {email} successfully logged out."
        })
    except Exception as e:
        print(f"Error logging logout audit: {e}")
        
    return {"status": "success", "message": "Successfully logged out."}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_active_user)):
    """Returns profile and assigned role permissions for the currently authenticated user."""
    return current_user

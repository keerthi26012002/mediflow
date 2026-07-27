import os
from enum import Enum
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
import jwt
import bcrypt
from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import APIKeyCookie, HTTPBearer, HTTPAuthorizationCredentials
from app.db import get_database, COLLECTION_USERS

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "mediflow_secret_key_123_enterprise_production!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

cookie_sec = APIKeyCookie(name="access_token", auto_error=False)
bearer_sec = HTTPBearer(auto_error=False)

class Role(str, Enum):
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    DATA_ANALYST = "DATA_ANALYST"

def normalize_role(role_val: Any) -> str:
    """Normalizes role strings and enums into canonical uppercase Role values."""
    if not role_val:
        return Role.DATA_ANALYST.value
    if isinstance(role_val, Role):
        return role_val.value
    r = str(role_val).strip().upper()
    if r in ["ADMIN", "ADMINISTRATOR"]:
        return Role.ADMIN.value
    elif r in ["DOCTOR", "PHYSICIAN", "CLINICIAN"]:
        return Role.DOCTOR.value
    elif r in ["OPERATIONS_MANAGER", "OPERATIONS", "OPS", "OPS_MANAGER"]:
        return Role.OPERATIONS_MANAGER.value
    elif r in ["DATA_ANALYST", "ANALYST"]:
        return Role.DATA_ANALYST.value
    return r

def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt with automatic salting."""
    # Truncate at 72 bytes if needed (bcrypt standard limit)
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a signed JWT access token with user metadata and expiration."""
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    
    if "email" in to_encode and "sub" not in to_encode:
        to_encode["sub"] = to_encode["email"]
        
    to_encode.update({
        "iat": now,
        "exp": expire,
        "type": "access"
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generates a signed JWT refresh token with extended validity."""
    to_encode = data.copy()
    now = datetime.utcnow()
    expire = now + (expires_delta if expires_delta else timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    
    if "email" in to_encode and "sub" not in to_encode:
        to_encode["sub"] = to_encode["email"]
        
    to_encode.update({
        "iat": now,
        "exp": expire,
        "type": "refresh"
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodes and validates a JWT token signature and expiration."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

DEFAULT_SYSTEM_USERS: Dict[str, Dict[str, Any]] = {
    "admin@mediflow.ai": {
        "id": "usr_admin_001",
        "username": "admin",
        "email": "admin@mediflow.ai",
        "role": Role.ADMIN.value,
        "is_active": True,
        "default_password": "mediflow123"
    },
    "doctor@mediflow.ai": {
        "id": "usr_doctor_002",
        "username": "doctor",
        "email": "doctor@mediflow.ai",
        "role": Role.DOCTOR.value,
        "is_active": True,
        "default_password": "mediflow123"
    },
    "ops@mediflow.ai": {
        "id": "usr_ops_003",
        "username": "operations",
        "email": "ops@mediflow.ai",
        "role": Role.OPERATIONS_MANAGER.value,
        "is_active": True,
        "default_password": "mediflow123"
    },
    "analyst@mediflow.ai": {
        "id": "usr_analyst_004",
        "username": "analyst",
        "email": "analyst@mediflow.ai",
        "role": Role.DATA_ANALYST.value,
        "is_active": True,
        "default_password": "mediflow123"
    }
}

async def get_current_user(
    request: Request,
    cookie_token: Optional[str] = Depends(cookie_sec),
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_sec)
) -> Dict[str, Any]:
    """
    Extracts, decodes, and validates the current user token from Cookie or Bearer header.
    Verifies user existence and active status in MongoDB when available.
    """
    token = None
    if cookie_token:
        token = cookie_token
    elif bearer_token:
        token = bearer_token.credentials
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated. Please login.")
        
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token or session expired.")
        
    email = payload.get("email") or payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Invalid token payload.")
        
    # Verify user against database if available
    try:
        db = get_database()
        user_doc = await db[COLLECTION_USERS].find_one({"email": email})
        if user_doc:
            if not user_doc.get("is_active", True):
                raise HTTPException(status_code=401, detail="User account is inactive. Contact Administrator.")
            return {
                "id": str(user_doc.get("_id", "")),
                "email": user_doc.get("email"),
                "username": user_doc.get("username", email.split("@")[0]),
                "role": normalize_role(user_doc.get("role")),
                "is_active": user_doc.get("is_active", True)
            }
        else:
            if email in DEFAULT_SYSTEM_USERS:
                return DEFAULT_SYSTEM_USERS[email].copy()
            # If not in default accounts and DB returned None, fall back to payload role
            return {
                "id": payload.get("id", "usr_fallback"),
                "email": email,
                "username": payload.get("username", email.split("@")[0]),
                "role": normalize_role(payload.get("role")),
                "is_active": True
            }
    except HTTPException:
        raise
    except Exception:
        # Fallback to token payload if DB lookup fails (offline dev mode)
        if email in DEFAULT_SYSTEM_USERS:
            return DEFAULT_SYSTEM_USERS[email].copy()
        return {
            "id": payload.get("id", "offline_id"),
            "email": email,
            "username": payload.get("username", email.split("@")[0]),
            "role": normalize_role(payload.get("role")),
            "is_active": True
        }

async def get_current_active_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Dependency verifying that the authenticated user account is active."""
    if not current_user.get("is_active", True):
        raise HTTPException(status_code=403, detail="Inactive user account.")
    return current_user

class RoleChecker:
    """Enforces Role-Based Access Control (RBAC) permissions on FastAPI endpoints."""
    def __init__(self, allowed_roles: List[Union[Role, str]]):
        self.allowed_roles = [normalize_role(r) for r in allowed_roles]
        
    def __call__(self, current_user: Dict[str, Any] = Depends(get_current_active_user)) -> Dict[str, Any]:
        user_role = normalize_role(current_user.get("role"))
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access forbidden: your role '{user_role}' lacks permission. Required roles: {self.allowed_roles}"
            )
        return current_user

# Predefined role dependencies matching the MediFlow AI v3 authorization matrix
require_admin = RoleChecker([Role.ADMIN])
require_doctor = RoleChecker([Role.ADMIN, Role.DOCTOR])
require_clinical = require_doctor
require_operations = RoleChecker([Role.ADMIN, Role.OPERATIONS_MANAGER])
require_analyst = RoleChecker([Role.ADMIN, Role.DATA_ANALYST])
require_hospital_state = RoleChecker([Role.ADMIN, Role.DOCTOR, Role.OPERATIONS_MANAGER])
require_forecast = RoleChecker([Role.ADMIN, Role.DATA_ANALYST])
require_resource_prediction = RoleChecker([Role.ADMIN, Role.OPERATIONS_MANAGER, Role.DATA_ANALYST])
require_anomalies = RoleChecker([Role.ADMIN, Role.OPERATIONS_MANAGER, Role.DATA_ANALYST])
require_alerts = RoleChecker([Role.ADMIN, Role.DOCTOR, Role.OPERATIONS_MANAGER])
require_authenticated = get_current_active_user


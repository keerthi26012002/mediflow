import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import jwt
from fastapi import Request, HTTPException, Security, Depends
from fastapi.security import APIKeyCookie, HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "mediflow_secret_key_123!")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

cookie_sec = APIKeyCookie(name="access_token", auto_error=False)
bearer_sec = HTTPBearer(auto_error=False)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None

async def get_current_user(
    request: Request,
    cookie_token: Optional[str] = Depends(cookie_sec),
    bearer_token: Optional[HTTPAuthorizationCredentials] = Depends(bearer_sec)
) -> Dict[str, Any]:
    token = None
    # 1. Try cookie
    if cookie_token:
        token = cookie_token
    # 2. Try Authorization header
    elif bearer_token:
        token = bearer_token.credentials
    
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated. Please login.")
        
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token or session expired.")
        
    return {
        "email": payload.get("email"),
        "role": payload.get("role")
    }

class RoleChecker:
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles
        
    def __call__(self, current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in self.allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access forbidden. Your role '{user_role}' does not have permission. Required roles: {self.allowed_roles}"
            )
        return current_user

from datetime import datetime
from typing import List, Dict, Any, Optional
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, EmailStr
from app.db import get_database, COLLECTION_USERS, COLLECTION_AUDIT_LOGS
from app.auth import (
    Role,
    normalize_role,
    hash_password,
    require_admin,
    get_current_active_user
)

router = APIRouter(tags=["user_management"])

class UserCreateRequest(BaseModel):
    email: str
    username: str
    password: str
    role: str = Role.DATA_ANALYST.value
    is_active: bool = True

class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None

class UserItemResponse(BaseModel):
    id: str
    email: str
    username: str
    role: str
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login: Optional[str] = None

@router.get("/users", response_model=List[UserItemResponse])
async def list_users(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    admin_user: dict = Depends(require_admin)
):
    """Retrieves all hospital user profiles. Restricted strictly to ADMIN."""
    db = get_database()
    cursor = db[COLLECTION_USERS].find().skip(skip).limit(limit)
    users = await cursor.to_list(length=limit)
    
    result = []
    for u in users:
        result.append(UserItemResponse(
            id=str(u["_id"]),
            email=u.get("email", ""),
            username=u.get("username", ""),
            role=normalize_role(u.get("role", Role.DATA_ANALYST.value)),
            is_active=u.get("is_active", True),
            created_at=u.get("created_at"),
            updated_at=u.get("updated_at"),
            last_login=u.get("last_login")
        ))
    return result

@router.post("/users", response_model=UserItemResponse)
async def create_user(
    request: Request,
    payload: UserCreateRequest,
    admin_user: dict = Depends(require_admin)
):
    """Creates a new user with an authorized role. Restricted strictly to ADMIN."""
    db = get_database()
    email = payload.email.strip().lower()
    username = payload.username.strip()
    
    if not email.endswith("@mediflow.ai"):
        raise HTTPException(
            status_code=400,
            detail="Unauthorized email domain. Use a @mediflow.ai account."
        )
    if len(payload.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long."
        )

    # Check for existing email or username
    existing = await db[COLLECTION_USERS].find_one({
        "$or": [{"email": email}, {"username": username}]
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A user with this email or username already exists."
        )

    normalized_role = normalize_role(payload.role)
    new_doc = {
        "email": email,
        "username": username,
        "hashed_password": hash_password(payload.password),
        "role": normalized_role,
        "is_active": payload.is_active,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "last_login": None
    }
    
    res = await db[COLLECTION_USERS].insert_one(new_doc)
    user_id = str(res.inserted_id)
    
    # Audit log
    await db[COLLECTION_AUDIT_LOGS].insert_one({
        "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "parsed_timestamp": datetime.now(),
        "event_type": "USER_CREATED",
        "actor_email": admin_user.get("email"),
        "actor_role": admin_user.get("role"),
        "target_email": email,
        "assigned_role": normalized_role,
        "status": "SUCCESS",
        "details": f"Admin {admin_user.get('email')} created user {email} with role {normalized_role}"
    })

    return UserItemResponse(
        id=user_id,
        email=email,
        username=username,
        role=normalized_role,
        is_active=payload.is_active,
        created_at=new_doc["created_at"],
        updated_at=new_doc["updated_at"],
        last_login=None
    )

@router.get("/users/{user_id}", response_model=UserItemResponse)
async def get_user_by_id(
    user_id: str,
    admin_user: dict = Depends(require_admin)
):
    """Retrieves a single user profile. Restricted strictly to ADMIN."""
    db = get_database()
    try:
        oid = ObjectId(user_id)
        user = await db[COLLECTION_USERS].find_one({"_id": oid})
    except Exception:
        user = await db[COLLECTION_USERS].find_one({"email": user_id})

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
        
    return UserItemResponse(
        id=str(user["_id"]),
        email=user.get("email", ""),
        username=user.get("username", ""),
        role=normalize_role(user.get("role", Role.DATA_ANALYST.value)),
        is_active=user.get("is_active", True),
        created_at=user.get("created_at"),
        updated_at=user.get("updated_at"),
        last_login=user.get("last_login")
    )

@router.patch("/users/{user_id}", response_model=UserItemResponse)
async def update_user(
    user_id: str,
    payload: UserUpdateRequest,
    admin_user: dict = Depends(require_admin)
):
    """Updates user role, active status, or password. Restricted strictly to ADMIN."""
    db = get_database()
    try:
        oid = ObjectId(user_id)
        query = {"_id": oid}
    except Exception:
        query = {"email": user_id}

    user = await db[COLLECTION_USERS].find_one(query)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    update_fields: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
    audit_changes = []

    if payload.role is not None:
        new_role = normalize_role(payload.role)
        update_fields["role"] = new_role
        audit_changes.append(f"role changed from {user.get('role')} to {new_role}")

    if payload.is_active is not None:
        update_fields["is_active"] = payload.is_active
        audit_changes.append(f"is_active changed to {payload.is_active}")

    if payload.password is not None:
        if len(payload.password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
        update_fields["hashed_password"] = hash_password(payload.password)
        audit_changes.append("password reset")

    await db[COLLECTION_USERS].update_one(query, {"$set": update_fields})
    updated_user = await db[COLLECTION_USERS].find_one(query)

    # Audit log
    await db[COLLECTION_AUDIT_LOGS].insert_one({
        "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "parsed_timestamp": datetime.now(),
        "event_type": "USER_UPDATED",
        "actor_email": admin_user.get("email"),
        "target_email": user.get("email"),
        "changes": audit_changes,
        "status": "SUCCESS",
        "details": f"Admin {admin_user.get('email')} updated user {user.get('email')}: {', '.join(audit_changes)}"
    })

    return UserItemResponse(
        id=str(updated_user["_id"]),
        email=updated_user.get("email", ""),
        username=updated_user.get("username", ""),
        role=normalize_role(updated_user.get("role", Role.DATA_ANALYST.value)),
        is_active=updated_user.get("is_active", True),
        created_at=updated_user.get("created_at"),
        updated_at=updated_user.get("updated_at"),
        last_login=updated_user.get("last_login")
    )

@router.delete("/users/{user_id}")
async def delete_or_deactivate_user(
    user_id: str,
    admin_user: dict = Depends(require_admin)
):
    """Deactivates a user account. Restricted strictly to ADMIN."""
    db = get_database()
    try:
        oid = ObjectId(user_id)
        query = {"_id": oid}
    except Exception:
        query = {"email": user_id}

    user = await db[COLLECTION_USERS].find_one(query)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.get("email") == admin_user.get("email"):
        raise HTTPException(status_code=400, detail="Cannot deactivate your own administrator account.")

    await db[COLLECTION_USERS].update_one(query, {
        "$set": {
            "is_active": False,
            "updated_at": datetime.utcnow().isoformat()
        }
    })

    # Audit log
    await db[COLLECTION_AUDIT_LOGS].insert_one({
        "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "parsed_timestamp": datetime.now(),
        "event_type": "USER_DEACTIVATED",
        "actor_email": admin_user.get("email"),
        "target_email": user.get("email"),
        "status": "SUCCESS",
        "details": f"Admin {admin_user.get('email')} deactivated account: {user.get('email')}"
    })

    return {"status": "success", "message": f"User {user.get('email')} has been deactivated."}

@router.get("/audit/logs")
async def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    admin_user: dict = Depends(require_admin)
):
    """Retrieves system security and operational audit logs. Restricted strictly to ADMIN."""
    db = get_database()
    cursor = db[COLLECTION_AUDIT_LOGS].find().sort("parsed_timestamp", -1).limit(limit)
    logs = await cursor.to_list(length=limit)
    for l in logs:
        l.pop("_id", None)
        l.pop("parsed_timestamp", None)
    return logs

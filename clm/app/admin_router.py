"""Admin routes: generate keys (SCEP, API), list keys, CRUD users. Admin only. ACME uses account key + JWS, not static keys."""

import secrets
import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from clm.app.auth import get_current_user, require_admin
from clm.app.db import get_db
from clm.app.models import ServiceKey, User
from clm.app.schemas import (
    CreateUserRequest,
    GenerateKeyRequest,
    GenerateKeyResponse,
    ServiceKeyInfo,
    UpdateUserRequest,
    UserInfo,
)
from clm.app.seed import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def _generate_key_value() -> str:
    """Return a cryptographically random key (base64url, 32 bytes)."""
    return secrets.token_urlsafe(32)


@router.post("/keys/generate", response_model=GenerateKeyResponse)
def generate_key(
    body: GenerateKeyRequest,
    db: Session = Depends(get_db),
    _admin: Annotated[str, Depends(require_admin)] = None,
) -> GenerateKeyResponse:
    """Generate a new key for SCEP or API. The plaintext key is returned once; copy it now. ACME uses built-in account key + JWS signing."""
    if body.scope == "api" and body.role not in ("admin", "user"):
        raise HTTPException(status_code=400, detail="role is required for scope=api (admin or user)")
    if body.scope != "api" and body.role is not None:
        body = body.model_copy(update={"role": None})
    key_plain = _generate_key_value()
    key_hash = _hash_key(key_plain)
    role = body.role if body.scope == "api" else None
    sk = ServiceKey(key_hash=key_hash, scope=body.scope, role=role, label=body.label or None)
    db.add(sk)
    db.commit()
    db.refresh(sk)
    return GenerateKeyResponse(
        id=sk.id,
        scope=sk.scope,
        role=sk.role,
        label=sk.label,
        key=key_plain,
    )


@router.get("/keys", response_model=list[ServiceKeyInfo])
def list_keys(
    db: Session = Depends(get_db),
    _admin: Annotated[str, Depends(require_admin)] = None,
) -> list[ServiceKeyInfo]:
    """List generated keys (metadata only; plaintext keys are never stored or returned)."""
    rows = db.execute(select(ServiceKey).order_by(ServiceKey.created_at.desc())).scalars().all()
    return [ServiceKeyInfo(id=r.id, scope=r.scope, role=r.role, label=r.label, created_at=r.created_at) for r in rows]


@router.get("/users", response_model=list[UserInfo])
def list_users(
    db: Session = Depends(get_db),
    _admin: Annotated[str, Depends(require_admin)] = None,
) -> list[UserInfo]:
    """List all users (no password hashes)."""
    rows = db.execute(select(User).order_by(User.created_at.asc())).scalars().all()
    return [
        UserInfo(
            id=r.id,
            email=r.email,
            role=r.role,
            must_change_password=r.must_change_password,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/users", response_model=UserInfo)
def create_user(
    body: CreateUserRequest,
    db: Session = Depends(get_db),
    _admin: Annotated[str, Depends(require_admin)] = None,
) -> UserInfo:
    """Add a new user (administrator or regular user)."""
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    user = User(
        email=email,
        password_hash=hash_password(body.password),
        role=body.role,
        must_change_password=body.must_change_password,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserInfo(
        id=user.id,
        email=user.email,
        role=user.role,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )


@router.patch("/users/{user_id}", response_model=UserInfo)
def update_user(
    user_id: str,
    body: UpdateUserRequest,
    db: Session = Depends(get_db),
    _admin: Annotated[str, Depends(require_admin)] = None,
) -> UserInfo:
    """Update user role, password, or must_change_password."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if body.role is not None:
        user.role = body.role
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.must_change_password is not None:
        user.must_change_password = body.must_change_password
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserInfo(
        id=user.id,
        email=user.email,
        role=user.role,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current: tuple = Depends(get_current_user),
    _admin: Annotated[str, Depends(require_admin)] = None,
) -> dict:
    """Remove a user. Cannot delete yourself."""
    current_user_id = current[0]
    if current_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own user")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"ok": True, "message": "User deleted"}

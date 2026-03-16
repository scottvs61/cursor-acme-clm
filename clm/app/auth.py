"""CLM API: Login (JWT) or API key auth; role-based access (admin vs user)."""

import hashlib
import secrets
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from clm.app.db import get_db
from clm.app.jwt_utils import decode_token
from clm.app.models import ServiceKey, User
from lib.config import get_api_keys, get_clm_ingest_secret

Role = Literal["admin", "user"]


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def _role_for_api_key_from_db(key: str, db: Session) -> Role | None:
    if not key or not key.strip():
        return None
    h = _hash_key(key)
    row = db.execute(select(ServiceKey).where(ServiceKey.key_hash == h, ServiceKey.scope == "api")).scalar_one_or_none()
    if row and row.role in ("admin", "user"):
        return row.role
    return None


def _role_for_api_key_from_config(key: str) -> Role | None:
    if not key or not key.strip():
        return None
    for entry in get_api_keys():
        if entry.get("key") == key.strip():
            r = entry.get("role")
            if r in ("admin", "user"):
                return r
    return None


def _resolve_user(
    authorization: str | None,
    x_api_key: str | None,
    db: Session,
) -> tuple[str, str, Role] | None:
    """Resolve (user_id, email, role) from Bearer JWT or X-API-Key. Returns None if no credentials. Raises 401 if invalid."""
    # 1. Bearer token
    if authorization and authorization.strip().lower().startswith("bearer "):
        token = authorization.strip()[7:].strip()
        payload = decode_token(token)
        if payload and payload.get("sub") and payload.get("role") in ("admin", "user"):
            return (payload["sub"], payload.get("email") or "", payload["role"])
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # 2. X-API-Key: DB first, then config
    if x_api_key:
        role = _role_for_api_key_from_db(x_api_key, db)
        if role is not None:
            return ("api-key", "", role)
        role = _role_for_api_key_from_config(x_api_key)
        if role is not None:
            return ("api-key", "", role)
        raise HTTPException(status_code=401, detail="Invalid API key (X-API-Key)")

    return None


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    db: Session = Depends(get_db),
) -> tuple[str, str, Role]:
    """
    Require authentication via Bearer JWT or X-API-Key. Returns (user_id, email, role).
    When no users in DB and no api_keys in config, treats as unauthenticated admin for backward compatibility.
    """
    try:
        current = _resolve_user(authorization, x_api_key, db)
    except HTTPException:
        raise
    if current is not None:
        return current
    # Backward compat: if no auth configured, allow as admin
    keys = get_api_keys()
    has_users = db.execute(select(User).limit(1)).scalar_one_or_none() is not None
    if not has_users and not keys:
        return ("anonymous", "", "admin")
    raise HTTPException(status_code=401, detail="Authentication required (Bearer token or X-API-Key)")


def require_api_key(
    current: Annotated[tuple[str, str, Role], Depends(get_current_user)],
) -> Role:
    """Dependency that returns role; use for endpoints that allow both user and admin."""
    return current[2]


def require_admin(
    current: Annotated[tuple[str, str, Role], Depends(get_current_user)],
) -> Literal["admin"]:
    """Require admin role. Returns 'admin' or raises 403."""
    if current[2] != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    return "admin"


def require_ingest_or_admin(
    x_clm_ingest_secret: Annotated[str | None, Header(alias="X-CLM-Ingest-Secret")] = None,
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    db: Session = Depends(get_db),
) -> Literal["admin"]:
    """
    For POST /api/events/issued: allow either X-CLM-Ingest-Secret (matches app.clm_ingest_secret)
    or normal admin auth (JWT / X-API-Key admin). ACME/SCEP use the shared secret.
    """
    configured = get_clm_ingest_secret()
    if configured and x_clm_ingest_secret:
        try:
            if secrets.compare_digest(configured.encode(), x_clm_ingest_secret.strip().encode()):
                return "admin"
        except Exception:
            pass
    # Fall back to normal admin auth (same logic as get_current_user + require_admin)
    try:
        current = _resolve_user(authorization, x_api_key, db)
    except HTTPException:
        raise
    if current is not None:
        if current[2] != "admin":
            raise HTTPException(status_code=403, detail="Admin role required")
        return "admin"
    keys = get_api_keys()
    has_users = db.execute(select(User).limit(1)).scalar_one_or_none() is not None
    if not has_users and not keys:
        return "admin"
    raise HTTPException(status_code=401, detail="Authentication required (Bearer token, X-API-Key, or X-CLM-Ingest-Secret)")


def get_current_user_id(
    current: Annotated[tuple[str, str, Role], Depends(get_current_user)],
) -> str:
    return current[0]

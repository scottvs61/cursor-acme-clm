"""Auth routes: login, change-password, me."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from clm.app.auth import get_current_user
from clm.app.db import get_db
from clm.app.jwt_utils import create_access_token
from clm.app.models import User
from clm.app.schemas import ChangePasswordRequest, LoginRequest, LoginResponse, UserMeResponse
from clm.app.seed import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    """Authenticate with email and password; returns JWT and user info."""
    email = (body.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email required")
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(
        data={"sub": user.id, "email": user.email, "role": user.role},
    )
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        email=user.email,
        role=user.role,
        user_id=user.id,
        must_change_password=user.must_change_password,
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current: tuple = Depends(get_current_user),
) -> dict:
    """Change password for the current user (or set new password when must_change_password)."""
    user_id, _, _ = current
    if user_id in ("api-key", "anonymous"):
        raise HTTPException(status_code=400, detail="Password change not available for API key or anonymous sessions")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    db.add(user)
    db.commit()
    return {"ok": True, "message": "Password updated"}


@router.get("/me", response_model=UserMeResponse)
def me(
    current: tuple = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserMeResponse:
    """Return current user info (from JWT or API key)."""
    user_id, email, role = current
    must_change = False
    if user_id not in ("api-key", "anonymous"):
        u = db.get(User, user_id)
        if u:
            must_change = u.must_change_password
            email = u.email
    return UserMeResponse(user_id=user_id, email=email or "(api key)", role=role, must_change_password=must_change)

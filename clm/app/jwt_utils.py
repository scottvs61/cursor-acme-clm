"""JWT creation and validation for CLM login. Uses JWT_SECRET from env or settings."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def _get_secret() -> str:
    secret = os.environ.get("JWT_SECRET") or os.environ.get("CLM_JWT_SECRET")
    if secret:
        return secret
    # Fallback for dev only; production should set JWT_SECRET
    return "clm-dev-secret-change-in-production"


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    to_encode["iat"] = datetime.now(timezone.utc)
    return jwt.encode(to_encode, _get_secret(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

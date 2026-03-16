"""Seed first administrator and write initial password to a one-time file. Do not log the password."""

import os
import secrets
from pathlib import Path

import bcrypt
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from clm.app.models import User

# bcrypt has a 72-byte limit; we truncate to avoid errors
_MAX_BCRYPT_BYTES = 72

SEED_EMAIL = "scott_stephenson@mckinsey.com"
SEED_ROLE = "admin"
PASSWORD_FILE = "initial_admin_password.txt"  # relative to config dir or repo root


def _generate_secure_password(length: int = 16) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%&"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def seed_first_admin_if_needed(engine) -> None:
    sm = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with sm() as db:
        existing = db.execute(select(User).limit(1)).scalar_one_or_none()
        if existing is not None:
            return
        # Generate password and hash
        password = os.environ.get("SEED_ADMIN_PASSWORD") or _generate_secure_password()
        password_hash = hash_password(password)
        user = User(
            email=SEED_EMAIL,
            password_hash=password_hash,
            role=SEED_ROLE,
            must_change_password=True,
        )
        db.add(user)
        db.commit()
        # Write password to file only when we generated it (not when from env)
        if not os.environ.get("SEED_ADMIN_PASSWORD"):
            for base in (Path(__file__).resolve().parent.parent.parent / "config", Path.cwd()):
                path = base / PASSWORD_FILE
                try:
                    path.write_text(
                        f"Initial administrator login\n\nEmail: {SEED_EMAIL}\nPassword: {password}\n\n"
                        "Change this password after first login. Then delete this file.\n",
                        encoding="utf-8",
                    )
                    print(f"CLM: Initial administrator created. One-time password written to {path}")
                    break
                except Exception:
                    continue


def reset_admin_password_if_requested(engine) -> None:
    """
    If CLM_RESET_ADMIN_PASSWORD is set, set the initial admin user's password to that value.
    Use this when you never received or lost the one-time password. After logging in, unset
    the variable and restart the server.
    """
    new_password = (os.environ.get("CLM_RESET_ADMIN_PASSWORD") or "").strip()
    if not new_password:
        return
    sm = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with sm() as db:
        user = db.execute(select(User).where(User.email == SEED_EMAIL)).scalar_one_or_none()
        if not user:
            return
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        db.add(user)
        db.commit()
        print("CLM: Admin password was set from CLM_RESET_ADMIN_PASSWORD. Unset the variable and restart to avoid resetting again.")


def hash_password(password: str) -> str:
    """Hash password with bcrypt. Passwords longer than 72 bytes are truncated (bcrypt limit)."""
    raw = password.encode("utf-8")
    if len(raw) > _MAX_BCRYPT_BYTES:
        raw = raw[:_MAX_BCRYPT_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plaintext password against a bcrypt hash."""
    try:
        raw = plain.encode("utf-8")
        if len(raw) > _MAX_BCRYPT_BYTES:
            raw = raw[:_MAX_BCRYPT_BYTES]
        return bcrypt.checkpw(raw, hashed.encode("ascii"))
    except Exception:
        return False

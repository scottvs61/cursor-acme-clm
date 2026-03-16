"""Check API keys against DB (service_keys) or config. Used by CLM auth and by SCEP when validating X-API-Key. ACME uses account key + JWS, not static keys."""

import hashlib
from sqlalchemy import select
from sqlalchemy.orm import Session

from lib.config import get_api_keys, get_scep_required_api_key

from clm.app.db import SessionLocal
from clm.app.models import ServiceKey


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.strip().encode("utf-8")).hexdigest()


def check_api_key_from_db(scope: str, key: str) -> bool:
    """Return True if the key matches a stored service key for the given scope (scep, api)."""
    if not key or not key.strip():
        return False
    with SessionLocal() as db:
        h = _hash_key(key)
        row = db.execute(select(ServiceKey).where(ServiceKey.key_hash == h, ServiceKey.scope == scope)).scalar_one_or_none()
        return row is not None


def check_scep_key(key: str | None) -> bool:
    """Return True if SCEP request is allowed. If config or DB has keys, key must match; else no restriction."""
    required = get_scep_required_api_key()
    if required:
        return (key or "").strip() == required
    if check_api_key_from_db("scep", key or ""):
        return True
    with SessionLocal() as db:
        has_any = db.execute(select(ServiceKey).where(ServiceKey.scope == "scep")).limit(1).first() is not None
    return not has_any


def get_api_keys_including_db(session: Session | None = None) -> list[dict]:
    """Return API keys from config plus from DB (scope=api). For auth dependency use DB directly; this is for optional use."""
    from_config = get_api_keys()
    keys = list(from_config)
    try:
        db = session or SessionLocal()
        try:
            rows = db.execute(select(ServiceKey).where(ServiceKey.scope == "api")).scalars().all()
            for r in rows:
                # We cannot return the actual key (only hash is stored); so DB keys are used only via X-API-Key lookup in auth
                pass
        finally:
            if not session:
                db.close()
    except Exception:
        pass
    return keys
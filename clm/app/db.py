"""Database engine and session. SQLAlchemy 2.0 style."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from clm.app.settings import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from sqlalchemy import text
    from clm.app.models import CertificateRecord, EventRecord, User, ServiceKey  # noqa: F401
    Base.metadata.create_all(bind=engine)
    # Add revoked_at if missing (e.g. existing SQLite DB)
    if "sqlite" in (settings.database_url or ""):
        try:
            with engine.begin() as conn:
                conn.execute(text("SELECT revoked_at FROM certificate_records LIMIT 1"))
        except Exception:
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE certificate_records ADD COLUMN revoked_at DATETIME"))
            except Exception:
                pass
    # Seed first admin if no users exist
    from clm.app.seed import seed_first_admin_if_needed, reset_admin_password_if_requested
    seed_first_admin_if_needed(engine)
    reset_admin_password_if_requested(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

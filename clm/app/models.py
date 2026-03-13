"""Certificate and event records. SQLAlchemy 2.0."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from clm.app.db import Base


def _uuid_str() -> str:
    return str(uuid.uuid4())


class CertificateRecord(Base):
    __tablename__ = "certificate_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    product_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    common_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sans_dns: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    serial_number: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    not_before: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    not_after: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sha256_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pem: Mapped[str] = mapped_column(Text, nullable=False)

    events: Mapped[list["EventRecord"]] = relationship("EventRecord", back_populates="certificate", foreign_keys="EventRecord.certificate_id")


class EventRecord(Base):
    __tablename__ = "event_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    certificate_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("certificate_records.id"), nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    certificate: Mapped[Optional["CertificateRecord"]] = relationship("CertificateRecord", back_populates="events", foreign_keys=[certificate_id])

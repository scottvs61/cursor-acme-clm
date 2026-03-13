"""CLM API routes."""

import json
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from clm.app.db import get_db
from clm.app.models import CertificateRecord, EventRecord
from clm.app.schemas import (
    BulkEnrollRequest,
    BulkEnrollResponse,
    BulkEnrollItemResult,
    CertificateCreateRequest,
    CertificateResponse,
    EventIssuedRequest,
    EventIssuedResponse,
    EventResponse,
)
from clm.app.servicenow import push_certificate_to_cmdb

_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from lib.cert_parse import parse_csr_or_cert_pem
from lib.issuance import IssuanceError, issue_certificate

router = APIRouter()


def _cert_to_response(record: CertificateRecord) -> CertificateResponse:
    sans = json.loads(record.sans_dns or "[]")
    return CertificateResponse(
        id=record.id,
        created_at=record.created_at,
        source=record.source,
        product_id=record.product_id,
        common_name=record.common_name,
        sans_dns=sans,
        serial_number=record.serial_number,
        not_before=record.not_before,
        not_after=record.not_after,
        sha256_fingerprint=record.sha256_fingerprint,
        pem=record.pem,
    )


def _event_to_response(record: EventRecord) -> EventResponse:
    return EventResponse(
        id=record.id,
        created_at=record.created_at,
        event_type=record.event_type,
        certificate_id=record.certificate_id,
        payload_json=record.payload_json,
    )


@router.post("/certificates", response_model=CertificateResponse)
def create_certificate(body: CertificateCreateRequest, db: Annotated[Session, Depends(get_db)]) -> CertificateResponse:
    try:
        parsed = parse_csr_or_cert_pem(body.pem)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if parsed.get("kind") != "certificate":
        raise HTTPException(status_code=400, detail="PEM must be a certificate, not a CSR")
    record = CertificateRecord(
        id=str(uuid.uuid4()),
        source=body.source,
        product_id=body.product_id,
        common_name=parsed.get("common_name"),
        sans_dns=json.dumps(parsed.get("sans_dns") or []),
        serial_number=parsed.get("serial_number") or "",
        not_before=parsed.get("not_before"),
        not_after=parsed.get("not_after"),
        sha256_fingerprint=parsed["sha256_fingerprint"],
        pem=body.pem,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    try:
        push_certificate_to_cmdb({
            "id": record.id,
            "common_name": record.common_name,
            "product_id": record.product_id,
            "sha256_fingerprint": record.sha256_fingerprint,
            "not_before": record.not_before,
            "not_after": record.not_after,
        })
    except Exception:
        pass
    return _cert_to_response(record)


@router.get("/certificates", response_model=list[CertificateResponse])
def list_certificates(db: Annotated[Session, Depends(get_db)]) -> list[CertificateResponse]:
    stmt = select(CertificateRecord).order_by(CertificateRecord.created_at.desc())
    rows = db.execute(stmt).scalars().all()
    return [_cert_to_response(r) for r in rows]


@router.get("/certificates/{cert_id}", response_model=CertificateResponse)
def get_certificate(cert_id: str, db: Annotated[Session, Depends(get_db)]) -> CertificateResponse:
    record = db.get(CertificateRecord, cert_id)
    if not record:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return _cert_to_response(record)


@router.post("/events/issued", response_model=EventIssuedResponse)
def event_issued(body: EventIssuedRequest, db: Annotated[Session, Depends(get_db)]) -> EventIssuedResponse:
    try:
        parsed = parse_csr_or_cert_pem(body.certificate_pem)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if parsed.get("kind") != "certificate":
        raise HTTPException(status_code=400, detail="PEM must be a certificate, not a CSR")
    fingerprint = parsed["sha256_fingerprint"]
    stmt = select(CertificateRecord).where(CertificateRecord.sha256_fingerprint == fingerprint)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        cert_record = existing
        cert_record.source = body.source
        cert_record.product_id = body.product_id
        cert_record.common_name = parsed.get("common_name")
        cert_record.sans_dns = json.dumps(parsed.get("sans_dns") or [])
        cert_record.serial_number = parsed.get("serial_number") or ""
        cert_record.not_before = parsed.get("not_before")
        cert_record.not_after = parsed.get("not_after")
        cert_record.pem = body.certificate_pem
        db.add(cert_record)
    else:
        cert_record = CertificateRecord(
            id=str(uuid.uuid4()),
            source=body.source,
            product_id=body.product_id,
            common_name=parsed.get("common_name"),
            sans_dns=json.dumps(parsed.get("sans_dns") or []),
            serial_number=parsed.get("serial_number") or "",
            not_before=parsed.get("not_before"),
            not_after=parsed.get("not_after"),
            sha256_fingerprint=fingerprint,
            pem=body.certificate_pem,
        )
        db.add(cert_record)
    db.flush()
    event_record = EventRecord(
        id=str(uuid.uuid4()),
        event_type="issued",
        certificate_id=cert_record.id,
        payload_json=json.dumps(body.raw),
    )
    db.add(event_record)
    db.commit()
    db.refresh(cert_record)
    db.refresh(event_record)
    try:
        push_certificate_to_cmdb({
            "id": cert_record.id,
            "common_name": cert_record.common_name,
            "product_id": cert_record.product_id,
            "sha256_fingerprint": cert_record.sha256_fingerprint,
            "not_before": cert_record.not_before,
            "not_after": cert_record.not_after,
        })
    except Exception:
        pass
    return EventIssuedResponse(certificate=_cert_to_response(cert_record), event=_event_to_response(event_record))


@router.post("/bulk/enroll", response_model=BulkEnrollResponse)
def bulk_enroll(body: BulkEnrollRequest, db: Annotated[Session, Depends(get_db)]) -> BulkEnrollResponse:
    """Enroll multiple CSRs via the configured CA; store certs in CLM and emit issued events."""
    results: list[BulkEnrollItemResult] = []
    default_pid = body.default_product_id
    for item in body.requests:
        product_id = item.product_id or default_pid
        try:
            cert_pem = issue_certificate(item.csr_pem, product_id=product_id)
        except IssuanceError as e:
            results.append(BulkEnrollItemResult(success=False, error=str(e)))
            continue
        try:
            parsed = parse_csr_or_cert_pem(cert_pem)
        except ValueError as e:
            results.append(BulkEnrollItemResult(success=False, error=f"Parse issued cert: {e}"))
            continue
        fingerprint = parsed.get("sha256_fingerprint") or ""
        stmt = select(CertificateRecord).where(CertificateRecord.sha256_fingerprint == fingerprint)
        existing = db.execute(stmt).scalar_one_or_none()
        if existing:
            rec = existing
            rec.source = "api"
            rec.product_id = product_id
            rec.common_name = parsed.get("common_name")
            rec.sans_dns = json.dumps(parsed.get("sans_dns") or [])
            rec.serial_number = parsed.get("serial_number") or ""
            rec.not_before = parsed.get("not_before")
            rec.not_after = parsed.get("not_after")
            rec.pem = cert_pem
            db.add(rec)
        else:
            rec = CertificateRecord(
                id=str(uuid.uuid4()),
                source="api",
                product_id=product_id,
                common_name=parsed.get("common_name"),
                sans_dns=json.dumps(parsed.get("sans_dns") or []),
                serial_number=parsed.get("serial_number") or "",
                not_before=parsed.get("not_before"),
                not_after=parsed.get("not_after"),
                sha256_fingerprint=fingerprint,
                pem=cert_pem,
            )
            db.add(rec)
        db.flush()
        ev = EventRecord(
            id=str(uuid.uuid4()),
            event_type="issued",
            certificate_id=rec.id,
            payload_json=json.dumps({"source": "bulk_enroll"}),
        )
        db.add(ev)
        try:
            push_certificate_to_cmdb({
                "id": rec.id,
                "common_name": rec.common_name,
                "product_id": rec.product_id,
                "sha256_fingerprint": rec.sha256_fingerprint,
                "not_before": rec.not_before,
                "not_after": rec.not_after,
            })
        except Exception:
            pass
        results.append(BulkEnrollItemResult(success=True, certificate_id=rec.id, certificate_pem=cert_pem))
    db.commit()
    succeeded = sum(1 for r in results if r.success)
    return BulkEnrollResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )

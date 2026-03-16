"""CLM API routes."""

import json
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from clm.app.auth import require_admin, require_api_key, require_ingest_or_admin
from clm.app.db import get_db
from clm.app.models import CertificateRecord, EventRecord
from clm.app.schemas import (
    BulkEnrollRequest,
    BulkEnrollResponse,
    BulkEnrollItemResult,
    CertificateCreateRequest,
    CertificateResponse,
    EnrollRequest,
    EventIssuedRequest,
    EventIssuedResponse,
    EventResponse,
    RenewRequest,
    RevokeRequest,
)
from clm.app.servicenow import push_certificate_to_cmdb

_repo = Path(__file__).resolve().parent.parent.parent
_clm_dir = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
from lib.cert_parse import parse_csr_or_cert_pem
from lib.config import get_subject_defaults
from lib.issuance import IssuanceError, issue_certificate, revoke_certificate_at_ca
from lib.keygen import build_pkcs12, generate_key_and_csr

router = APIRouter()


def _cert_to_response(record: CertificateRecord) -> CertificateResponse:
    sans = json.loads(record.sans_dns or "[]")
    revoked_at = getattr(record, "revoked_at", None)
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
        revoked_at=revoked_at,
    )


def _event_to_response(record: EventRecord) -> EventResponse:
    return EventResponse(
        id=record.id,
        created_at=record.created_at,
        event_type=record.event_type,
        certificate_id=record.certificate_id,
        payload_json=record.payload_json,
    )


def _store_issued_cert(
    cert_pem: str,
    product_id: str | None,
    db: Session,
    source: str = "api",
    event_payload: dict | None = None,
) -> CertificateRecord:
    """Upsert certificate by fingerprint, add issued event, commit, push to CMDB. Returns the record."""
    parsed = parse_csr_or_cert_pem(cert_pem)
    fingerprint = parsed.get("sha256_fingerprint") or ""
    stmt = select(CertificateRecord).where(CertificateRecord.sha256_fingerprint == fingerprint)
    existing = db.execute(stmt).scalar_one_or_none()
    if existing:
        rec = existing
        rec.source = source
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
            source=source,
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
    payload = event_payload or {"source": "manual_enroll"}
    ev = EventRecord(
        id=str(uuid.uuid4()),
        event_type="issued",
        certificate_id=rec.id,
        payload_json=json.dumps(payload),
    )
    db.add(ev)
    db.commit()
    db.refresh(rec)
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
    return rec


@router.post("/certificates", response_model=CertificateResponse)
def create_certificate(
    body: CertificateCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    _role: Annotated[str, Depends(require_admin)],
) -> CertificateResponse:
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


@router.get("/help", response_class=PlainTextResponse)
def api_help(_role: Annotated[str, Depends(require_api_key)]):
    """Return the API Knowledge document (markdown) for in-GUI help."""
    path = _clm_dir / "API-Knowledge.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="API Knowledge document not found")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/certificates", response_model=list[CertificateResponse])
def list_certificates(
    product_id: str | None = None,
    db: Annotated[Session, Depends(get_db)] = None,
    _role: Annotated[str, Depends(require_api_key)] = None,
) -> list[CertificateResponse]:
    """List certificates, newest first. Optional query param: product_id to filter by product."""
    stmt = select(CertificateRecord).order_by(CertificateRecord.created_at.desc())
    if product_id is not None and product_id.strip():
        stmt = stmt.where(CertificateRecord.product_id == product_id.strip())
    rows = db.execute(stmt).scalars().all()
    return [_cert_to_response(r) for r in rows]


@router.get("/certificates/{cert_id}", response_model=CertificateResponse)
def get_certificate(
    cert_id: str,
    db: Annotated[Session, Depends(get_db)],
    _role: Annotated[str, Depends(require_api_key)],
) -> CertificateResponse:
    record = db.get(CertificateRecord, cert_id)
    if not record:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return _cert_to_response(record)


@router.post("/enroll")
def enroll_manual(
    body: EnrollRequest,
    db: Annotated[Session, Depends(get_db)],
    _role: Annotated[str, Depends(require_admin)],
):
    """Manually enroll: provide your own CSR (returns JSON) or have CLM generate key+CSR (returns PKCS#12 .pfx/.p12)."""
    if body.generate:
        # Generate key and CSR in memory with full Subject DN (defaults from config + CN/OU from request); issue cert; store in CLM; build PKCS#12. Key/password never stored.
        subject_defaults = get_subject_defaults()
        private_key, csr_pem = generate_key_and_csr(
            common_name=body.common_name or "",
            sans_dns=body.sans_dns or [],
            subject_defaults=subject_defaults,
            organizational_units=body.organizational_units,
        )
        try:
            cert_pem = issue_certificate(csr_pem, product_id=body.product_id)
        except IssuanceError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        rec = _store_issued_cert(
            cert_pem,
            body.product_id,
            db,
            source="api",
            event_payload={"source": "manual_enroll", "generated_key": True},
        )
        p12_bytes = build_pkcs12(
            cert_pem=cert_pem,
            private_key=private_key,
            password=body.p12_password or "",
            friendly_name=rec.common_name or "Certificate",
        )
        ext = "pfx" if body.p12_format == "pfx" else "p12"
        filename = f"certificate.{ext}"
        return Response(
            content=p12_bytes,
            media_type="application/x-pkcs12",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    # Own CSR path: issue cert, store, return JSON
    try:
        cert_pem = issue_certificate(body.csr_pem or "", product_id=body.product_id)
    except IssuanceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    rec = _store_issued_cert(cert_pem, body.product_id, db)
    return _cert_to_response(rec)


@router.post("/certificates/{cert_id}/renew", response_model=CertificateResponse)
def renew_certificate(
    cert_id: str,
    body: RenewRequest,
    db: Annotated[Session, Depends(get_db)],
    _role: Annotated[str, Depends(require_admin)],
) -> CertificateResponse:
    """Issue a new certificate from the given CSR and record it as a renewal of the specified certificate."""
    existing = db.get(CertificateRecord, cert_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Certificate not found")
    product_id = existing.product_id
    try:
        cert_pem = issue_certificate(body.csr_pem, product_id=product_id)
    except IssuanceError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    parsed = parse_csr_or_cert_pem(cert_pem)
    fingerprint = parsed.get("sha256_fingerprint") or ""
    stmt = select(CertificateRecord).where(CertificateRecord.sha256_fingerprint == fingerprint)
    dup = db.execute(stmt).scalar_one_or_none()
    if dup:
        rec = dup
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
        event_type="renewed",
        certificate_id=rec.id,
        payload_json=json.dumps({"previous_certificate_id": cert_id}),
    )
    db.add(ev)
    db.commit()
    db.refresh(rec)
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
    return _cert_to_response(rec)


@router.post("/certificates/{cert_id}/revoke")
def revoke_certificate(
    cert_id: str,
    body: RevokeRequest | None = Body(None),
    db: Annotated[Session, Depends(get_db)] = None,
    _role: Annotated[str, Depends(require_admin)] = None,
):
    """Mark the certificate as revoked in the CLM and revoke at DigiCert One TLM when configured."""
    from datetime import datetime as dt
    record = db.get(CertificateRecord, cert_id)
    if not record:
        raise HTTPException(status_code=404, detail="Certificate not found")
    if getattr(record, "revoked_at", None) is not None:
        raise HTTPException(status_code=400, detail="Certificate already revoked")
    revocation_reason = (body.revocation_reason if body else "cessation_of_operation").strip() or "cessation_of_operation"
    ca_revoked = False
    ca_revoke_error = None
    if record.serial_number:
        ca_revoked, ca_revoke_error = revoke_certificate_at_ca(
            serial_number=record.serial_number,
            revocation_reason=revocation_reason,
        )
    setattr(record, "revoked_at", dt.utcnow())
    db.add(record)
    ev = EventRecord(
        id=str(uuid.uuid4()),
        event_type="revoked",
        certificate_id=record.id,
        payload_json=json.dumps({"ca_revoked": ca_revoked, "revocation_reason": revocation_reason}),
    )
    db.add(ev)
    db.commit()
    db.refresh(record)
    revoked_at = getattr(record, "revoked_at", None)
    return {
        "ok": True,
        "certificate_id": cert_id,
        "revoked_at": revoked_at.isoformat() if revoked_at else None,
        "ca_revoked": ca_revoked,
        "ca_revoke_error": ca_revoke_error,
    }


@router.post("/events/issued", response_model=EventIssuedResponse)
def event_issued(
    body: EventIssuedRequest,
    db: Annotated[Session, Depends(get_db)],
    _role: Annotated[str, Depends(require_ingest_or_admin)],
) -> EventIssuedResponse:
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
def bulk_enroll(
    body: BulkEnrollRequest,
    db: Annotated[Session, Depends(get_db)],
    _role: Annotated[str, Depends(require_admin)],
) -> BulkEnrollResponse:
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

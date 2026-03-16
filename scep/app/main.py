"""Minimal SCEP server: GetCACert, GetCACaps, PKIOperation. Uses config CA for issuance and CLM for ingestion."""

import base64
import sys
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
import httpx

_repo = Path(__file__).resolve().parent.parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from lib.config import load_config, get_app_config, get_scep_config, get_ca_config, get_scep_required_api_key
from lib.issuance import IssuanceError, issue_certificate

load_config(_repo / "config" / "config.yaml")

app = FastAPI(title="SCEP Server", description="SCEP enrollment; issues via configured CA and ingests to CLM")


def _get_ca_cert_pem() -> str:
    """Return CA cert PEM for GetCACert (from config or placeholder)."""
    cfg = get_scep_config()
    pem = (cfg.get("ca_cert_pem") or "").strip()
    if pem and "BEGIN CERTIFICATE" in pem:
        return pem
    path = cfg.get("ca_cert_path")
    if path:
        p = Path(path)
        if not p.is_absolute():
            p = _repo / p
        if p.exists():
            return p.read_text()
    # Placeholder so clients get a response; replace with your CA/intermediate in config
    return "-----BEGIN CERTIFICATE-----\nMIIBkTCB+wIJAKOR6ENz0b1HMA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMM\nBlNDRVAgQ0EwHhcNMjQwMTAxMDAwMDAwWhcNMjkwMTAxMDAwMDAwWjARMQ8w\nDQYDVQQDDAZTQ0VQIENBMFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAL+test\n-----END CERTIFICATE-----"


@app.get("/GetCACert")
def get_ca_cert() -> Response:
    """Return CA certificate(s) for SCEP client discovery."""
    pem = _get_ca_cert_pem()
    return Response(content=pem.encode(), media_type="application/x-x509-ca-cert")


@app.get("/GetCACaps")
def get_ca_caps() -> PlainTextResponse:
    """Return SCEP capabilities (one per line)."""
    caps = "POSTPKIOperation\nSHA-256\n"
    return PlainTextResponse(caps.strip())


def _check_scep_api_key(request: Request) -> None:
    """Require X-API-Key when config or CLM DB has SCEP keys. Raises HTTPException 401 on failure."""
    key = (request.headers.get("X-API-Key") or "").strip()
    try:
        from clm.app.key_store import check_scep_key
        if check_scep_key(key or None):
            return
    except Exception:
        required = get_scep_required_api_key()
        if not required:
            return
        if key != required:
            raise HTTPException(status_code=401, detail="API key required (X-API-Key)")
        return
    raise HTTPException(status_code=401, detail="API key required (X-API-Key)")


@app.post("/PKIOperation")
async def pki_operation(request: Request):
    """
    SCEP enrollment: accept PKCS#7 message (form message=) or JSON { "csr_pem": "..." }.
    Issues cert via configured CA, ingests to CLM, returns cert PEM.
    """
    _check_scep_api_key(request)
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    csr_pem: str | None = None
    product_id = get_scep_config().get("default_product_id") or None

    if content_type == "application/json":
        body = await request.json()
        csr_pem = (body.get("csr_pem") or "").strip()
        product_id = body.get("product_id") or product_id
    elif content_type in ("application/x-www-form-urlencoded", "application/form-data", ""):
        form = await request.form()
        op = (form.get("operation") or "").strip()
        message_b64 = (form.get("message") or "").strip()
        if message_b64:
            try:
                der = base64.b64decode(message_b64, validate=True)
            except Exception:
                der = base64.urlsafe_b64decode(message_b64 + "==")
            try:
                from cryptography import x509
                from cryptography.hazmat.primitives.serialization import Encoding
                csr = x509.load_der_x509_csr(der)
                csr_pem = csr.public_bytes(Encoding.PEM).decode()
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="Could not parse message as CSR DER. For full SCEP use a client that sends PKCS#7; or use JSON body: { \"csr_pem\": \"...\" }",
                )
        else:
            csr_pem = (form.get("csr_pem") or "").strip()
            product_id = form.get("product_id") or product_id

    if not csr_pem or "BEGIN CERTIFICATE REQUEST" not in csr_pem:
        raise HTTPException(status_code=400, detail="Missing csr_pem (PEM CSR) or valid SCEP message")

    pid = (product_id or "").strip() if product_id else ""
    if not pid:
        raise HTTPException(
            status_code=400,
            detail="product_id is required. Provide it in the request (JSON product_id or form product_id) or set scep.default_product_id in config.",
        )

    try:
        cert_pem = issue_certificate(csr_pem, product_id=pid)
    except IssuanceError as e:
        raise HTTPException(status_code=400, detail=f"CA rejected request: {e}") from e

    # Ingest to CLM
    clm_url = get_app_config().get("clm_ingest_url", "").strip()
    if clm_url:
        try:
            from lib.config import get_clm_ingest_secret

            headers = {}
            secret = get_clm_ingest_secret()
            if secret:
                headers["X-CLM-Ingest-Secret"] = secret
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(
                    clm_url,
                    json={
                        "certificate_pem": cert_pem,
                        "source": "scep",
                        "product_id": pid,
                        "raw": {"scep": True},
                    },
                    headers=headers,
                )
        except Exception:
            pass

    # Return cert (SCEP typically returns PKCS#7; for prototype we return PEM)
    return Response(content=cert_pem.encode(), media_type="application/x-x509-user-cert")

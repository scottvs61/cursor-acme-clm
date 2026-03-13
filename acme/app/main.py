"""ACME v2 server. Uses config for CA and CLM ingest URL. Ensure repo root is on PYTHONPATH."""

import base64
import secrets
import sys
import uuid
from pathlib import Path

# Repo root on path so 'lib' and config resolve
_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import httpx
from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from acme.app.acme_types import (
    AccountResponse,
    AccountStatus,
    AuthStatus,
    ChallengeType,
    FinalizeRequest,
    NewAccountRequest,
    NewOrderRequest,
    OrderStatus,
)
from acme.app.acme_jws import get_payload_from_request, jwk_thumbprint
from acme.app.store import get_store

from lib.config import get_app_config, get_ca_config, load_config
from lib.issuance import IssuanceError, issue_certificate

# Load config from repo root
load_config(_repo_root / "config" / "config.yaml")

app = FastAPI(title="ACME Gateway", description="ACME v2 with product_id and CLM integration")


def _nonce() -> str:
    n = secrets.token_urlsafe(32)
    get_store().add_nonce(n)
    return n


def _base() -> str:
    return get_app_config().get("acme_base_url", "http://localhost:8000").rstrip("/")


async def _post_issued_to_clm(cert_pem: str, product_id: str | None, source: str, raw: dict) -> None:
    """POST issued cert + product_id to CLM for ingestion (e.g. ServiceNow CMDB)."""
    url = get_app_config().get("clm_ingest_url", "").strip()
    if not url:
        return
    payload = {
        "certificate_pem": cert_pem,
        "source": source,
        "product_id": product_id,
        "raw": raw,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
    except Exception as e:
        # Log but do not fail ACME response
        print(f"[CLM] ingest POST failed: {e}")


@app.get("/directory", response_class=JSONResponse)
def directory(response: Response):
    res = JSONResponse(content={"newNonce": f"{_base()}/new-nonce", "newAccount": f"{_base()}/new-account", "newOrder": f"{_base()}/new-order"})
    res.headers["Replay-Nonce"] = _nonce()
    res.headers["Content-Type"] = "application/json"
    return res


@app.get("/new-nonce", status_code=status.HTTP_204_NO_CONTENT)
@app.head("/new-nonce", status_code=status.HTTP_204_NO_CONTENT)
def new_nonce() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Replay-Nonce": _nonce()})


def _parse_jws(body: bytes) -> tuple:
    return get_payload_from_request(body)


@app.post("/new-account", response_class=JSONResponse)
async def new_account(request: Request, response: Response):
    body = await request.body()
    try:
        protected, payload = _parse_jws(body)
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": str(e)})
    store = get_store()
    if not store.consume_nonce(protected.nonce):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:badNonce", "detail": "Invalid or used nonce"})
    base = _base()
    key_id = f"{base}/account/{uuid.uuid4()}"
    req = NewAccountRequest.model_validate(payload) if payload else NewAccountRequest()
    product_id = (req.product_id or "").strip()
    if not product_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "urn:ietf:params:acme:error:malformed", "detail": "product_id is required (prototype policy)"},
        )
    if not protected.jwk:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": "Missing jwk in protected header"})
    thumb = jwk_thumbprint(protected.jwk)
    existing = store.get_account_by_thumbprint(thumb)
    if existing and req.onlyReturnExisting:
        res = JSONResponse(content=AccountResponse(status=AccountStatus.valid, contact=existing.contact).model_dump(exclude_none=True))
        res.headers["Location"] = existing.key_id
        res.headers["Replay-Nonce"] = _nonce()
        return res
    if existing:
        res = JSONResponse(content=AccountResponse(status=AccountStatus.valid, contact=existing.contact).model_dump(exclude_none=True))
        res.headers["Location"] = existing.key_id
        res.headers["Replay-Nonce"] = _nonce()
        return res
    acc = store.create_account(key_id, thumb, req.contact, product_id=product_id)
    res = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=AccountResponse(status=AccountStatus.valid, contact=acc.contact).model_dump(exclude_none=True),
    )
    res.headers["Location"] = acc.key_id
    res.headers["Replay-Nonce"] = _nonce()
    return res


@app.post("/new-order", response_class=JSONResponse)
async def new_order(request: Request, response: Response):
    body = await request.body()
    try:
        protected, payload = _parse_jws(body)
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": str(e)})
    store = get_store()
    if not store.consume_nonce(protected.nonce):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:badNonce", "detail": "Invalid or used nonce"})
    try:
        req = NewOrderRequest.model_validate(payload)
    except Exception as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": str(e)})
    account_id = protected.kid
    if not account_id or not store.get_account_by_kid(account_id):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:accountDoesNotExist", "detail": "Unknown account"})
    order = store.create_order(account_id, req.identifiers)
    if not order.product_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "urn:ietf:params:acme:error:malformed", "detail": "product_id missing for account/order (prototype policy)"},
        )
    store.set_order_ready(order.order_id)
    base = _base()
    auth_urls = [f"{base}/auth/{aid}" for aid in order.auth_ids]
    finalize_url = f"{base}/finalize/{order.order_id}"
    out = {
        "status": order.status.value,
        "identifiers": [{"type": i.type.value, "value": i.value} for i in order.identifiers],
        "authorizations": auth_urls,
        "finalize": finalize_url,
    }
    res = JSONResponse(status_code=status.HTTP_201_CREATED, content=out)
    res.headers["Location"] = f"{base}/order/{order.order_id}"
    res.headers["Replay-Nonce"] = _nonce()
    return res


@app.get("/order/{order_id}", response_class=JSONResponse)
def get_order_GET(order_id: str, response: Response):
    store = get_store()
    order = store.get_order(order_id)
    if not order:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"type": "urn:ietf:params:acme:error:orderNotFound", "detail": "Order not found"})
    base = _base()
    auth_urls = [f"{base}/auth/{aid}" for aid in order.auth_ids]
    out = {
        "status": order.status.value,
        "identifiers": [{"type": i.type.value, "value": i.value} for i in order.identifiers],
        "authorizations": auth_urls,
        "finalize": f"{base}/finalize/{order.order_id}",
    }
    if order.certificate_id:
        out["certificate"] = f"{base}/cert/{order.certificate_id}"
    res = JSONResponse(content=out)
    res.headers["Replay-Nonce"] = _nonce()
    return res


@app.post("/order/{order_id}", response_class=JSONResponse)
async def get_order_POST(order_id: str, request: Request, response: Response):
    body = await request.body()
    try:
        protected, _ = _parse_jws(body)
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": str(e)})
    store = get_store()
    if not store.consume_nonce(protected.nonce):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:badNonce", "detail": "Invalid or used nonce"})
    if not store.get_account_by_kid(protected.kid or ""):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:accountDoesNotExist", "detail": "Unknown account"})
    return get_order_GET(order_id, response)


@app.post("/finalize/{order_id}", response_class=JSONResponse)
async def finalize_order(order_id: str, request: Request, response: Response):
    body = await request.body()
    try:
        protected, payload = _parse_jws(body)
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": str(e)})
    store = get_store()
    if not store.consume_nonce(protected.nonce):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:badNonce", "detail": "Invalid or used nonce"})
    order = store.get_order(order_id)
    if not order:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"type": "urn:ietf:params:acme:error:orderNotFound", "detail": "Order not found"})
    if order.status not in (OrderStatus.ready, OrderStatus.pending):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:orderNotReady", "detail": "Order not ready for finalize"})
    try:
        req = FinalizeRequest.model_validate(payload)
    except Exception as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": str(e)})
    raw = req.csr.encode("ascii")
    pad = 4 - (len(raw) % 4)
    if pad != 4:
        raw += b"=" * pad
    try:
        der = base64.urlsafe_b64decode(raw)
    except Exception:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:badCSR", "detail": "Invalid CSR encoding"})
    pem_lines = ["-----BEGIN CERTIFICATE REQUEST-----"]
    b64 = base64.b64encode(der).decode("ascii")
    for i in range(0, len(b64), 64):
        pem_lines.append(b64[i : i + 64])
    pem_lines.append("-----END CERTIFICATE REQUEST-----")
    csr_pem = "\n".join(pem_lines)
    if not order.product_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "urn:ietf:params:acme:error:malformed", "detail": "product_id missing on order (prototype policy)"},
        )
    profile_id = get_app_config().get("digicert_profile_id") or get_ca_config().get("profile_id")
    try:
        cert_pem = issue_certificate(csr_pem, product_id=order.product_id, profile_id=profile_id or None)
    except IssuanceError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "urn:ietf:params:acme:error:badCSR", "detail": f"CA rejected request: {str(e)}"},
        )
    cert_id = str(uuid.uuid4())
    store.store_certificate(cert_id, cert_pem)
    await _post_issued_to_clm(
        cert_pem,
        product_id=order.product_id,
        source="acme",
        raw={
            "order_id": order_id,
            "account_id": protected.kid or "",
            "identifiers": [i.value for i in order.identifiers],
            "acme": {"endpoint": "finalize"},
        },
    )
    store.set_order_valid(order_id, cert_id)
    base = _base()
    auth_urls = [f"{base}/auth/{aid}" for aid in order.auth_ids]
    out = {
        "status": OrderStatus.valid.value,
        "identifiers": [{"type": i.type.value, "value": i.value} for i in order.identifiers],
        "authorizations": auth_urls,
        "finalize": f"{base}/finalize/{order_id}",
        "certificate": f"{base}/cert/{cert_id}",
    }
    res = JSONResponse(content=out)
    res.headers["Replay-Nonce"] = _nonce()
    return res


@app.get("/cert/{cert_id}")
def get_cert_GET(cert_id: str, response: Response):
    store = get_store()
    pem = store.get_certificate(cert_id)
    if not pem:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"type": "urn:ietf:params:acme:error:notFound", "detail": "Certificate not found"})
    res = PlainTextResponse(content=pem, media_type="application/pem-certificate-chain")
    res.headers["Replay-Nonce"] = _nonce()
    return res


@app.post("/cert/{cert_id}")
async def get_cert_POST(cert_id: str, request: Request, response: Response):
    body = await request.body()
    try:
        protected, _ = _parse_jws(body)
    except ValueError as e:
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:malformed", "detail": str(e)})
    store = get_store()
    if not store.consume_nonce(protected.nonce):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"type": "urn:ietf:params:acme:error:badNonce", "detail": "Invalid or used nonce"})
    return get_cert_GET(cert_id, response)


@app.get("/auth/{auth_id}", response_class=JSONResponse)
def get_auth_GET(auth_id: str, response: Response):
    store = get_store()
    auth = store.get_authorization(auth_id)
    if not auth:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"type": "urn:ietf:params:acme:error:notFound", "detail": "Authorization not found"})
    base = _base()
    challenges = [
        {"type": ChallengeType.HTTP_01.value, "url": f"{base}/challenge/{auth_id}/http-01", "status": AuthStatus.valid.value, "token": c.get("token", "")}
        for c in auth.challenges
    ]
    out = {"status": auth.status.value, "identifier": {"type": auth.identifier.type.value, "value": auth.identifier.value}, "challenges": challenges}
    res = JSONResponse(content=out)
    res.headers["Replay-Nonce"] = _nonce()
    return res

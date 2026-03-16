"""ACME JWS parsing and signature verification (RFC 8555)."""

import base64
import hashlib
import json
from typing import Any, Optional

from jose import jwk, jws
from pydantic import BaseModel


class ProtectedHeader(BaseModel):
    alg: str = "RS256"
    jwk: Optional[dict[str, Any]] = None
    kid: Optional[str] = None
    nonce: str = ""
    url: str = ""


def b64url_decode(data: str) -> bytes:
    pad = 4 - (len(data) % 4)
    if pad != 4:
        data += "=" * pad
    return base64.urlsafe_b64decode(data)


def jwk_thumbprint(jwk_dict: dict[str, Any]) -> str:
    canonical = json.dumps(jwk_dict, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _get_jws_parts(body: bytes) -> tuple[str, str, str, Optional[str]]:
    """Return (protected_b64, payload_b64, signature_b64, alg) from compact or flattened JWS."""
    raw = body.decode("utf-8").strip()
    if raw.startswith("{"):
        data = json.loads(raw)
        protected_b64 = data.get("protected", "")
        payload_b64 = data.get("payload") or ""
        signature_b64 = data.get("signature", "")
        if not protected_b64 or not signature_b64:
            raise ValueError("Invalid JWS: missing protected or signature")
        protected_bytes = b64url_decode(protected_b64)
        protected_dict = json.loads(protected_bytes.decode())
        alg = protected_dict.get("alg", "RS256")
        return protected_b64, payload_b64, signature_b64, alg
    parts = raw.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWS: expected 3 parts")
    protected_bytes = b64url_decode(parts[0])
    protected_dict = json.loads(protected_bytes.decode())
    alg = protected_dict.get("alg", "RS256")
    return parts[0], parts[1], parts[2], alg


def verify_jws_signature(body: bytes, public_jwk: dict[str, Any]) -> bool:
    """
    Verify the JWS signature using the account's public key (JWK).
    ACME requires every POST to be signed with the client's private key; we verify with the public key.
    """
    try:
        protected_b64, payload_b64, signature_b64, alg = _get_jws_parts(body)
        compact = f"{protected_b64}.{payload_b64}.{signature_b64}"
        # ACME JWKs often omit "alg"; python-jose requires an algorithm to construct RSA keys.
        key = jwk.construct(public_jwk, algorithm=alg)
        jws.verify(compact, key, algorithms=[alg])
        return True
    except Exception:
        return False


def get_payload_from_request(body: bytes) -> tuple[ProtectedHeader, dict[str, Any]]:
    try:
        raw = body.decode("utf-8")
        if raw.strip().startswith("{"):
            data = json.loads(raw)
            payload_b64 = data.get("payload")
            if payload_b64:
                payload_bytes = b64url_decode(payload_b64)
                payload = json.loads(payload_bytes.decode()) if payload_bytes else {}
            else:
                payload = {}
            protected_b64 = data.get("protected", "")
        else:
            parts = raw.split(".")
            if len(parts) < 2:
                raise ValueError("Invalid JWS")
            protected_b64 = parts[0]
            payload_b64 = parts[1]
            payload_bytes = b64url_decode(payload_b64)
            payload = json.loads(payload_bytes.decode()) if payload_bytes else {}
        protected_bytes = b64url_decode(protected_b64)
        protected_dict = json.loads(protected_bytes.decode())
    except Exception as e:
        raise ValueError(f"Invalid JWS: {e}")

    protected = ProtectedHeader(
        alg=protected_dict.get("alg", "RS256"),
        jwk=protected_dict.get("jwk"),
        kid=protected_dict.get("kid"),
        nonce=protected_dict.get("nonce", ""),
        url=protected_dict.get("url", ""),
    )
    return protected, payload

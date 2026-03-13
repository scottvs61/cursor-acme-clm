"""ACME JWS parsing (minimal for prototype)."""

import base64
import hashlib
import json
from typing import Any, Optional

from jose import jwk, jws
from jose.backends.base import Key
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

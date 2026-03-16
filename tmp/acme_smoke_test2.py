"""
ACME smoke test: issue a certificate through the ACME server.

The server verifies JWS signatures (account key + JWK/kid). This script signs
every request with the account private key; no static API key is used.

Prerequisites:
  - ACME server running at BASE (default http://127.0.0.1:8000)
  - tmp/account.key  : RSA private key (PEM) for the ACME account
  - tmp/domain.csr   : PEM CSR with CN + SAN DNS (DigiCert One TLM requires SAN). Example:

    openssl genrsa -out tmp/domain.key 2048
    cat > /tmp/san.cnf <<'EOF'
    [req]
    distinguished_name = req_distinguished_name
    req_extensions = v3_req
    [req_distinguished_name]
    CN = example.local
    [v3_req]
    subjectAltName = DNS:example.local
    EOF
    openssl req -new -key tmp/domain.key -out tmp/domain.csr -config /tmp/san.cnf -extensions v3_req

Usage (from repo root):
  python tmp/acme_smoke_test2.py

Optional env:
  ACME_BASE_URL  - ACME directory URL (default http://127.0.0.1:8000)
  ACME_PRODUCT_ID - product_id for newAccount (default ABC123)

On success, the issued certificate is written to tmp/issued.crt.
"""

import base64
import json
import os
import subprocess
import sys

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# Default: ACME server on port 8000 (cursor-acme-clm ACME)
BASE = os.environ.get("ACME_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TMP = os.path.dirname(os.path.abspath(__file__))


def b64url(data: bytes) -> str:
    """Base64url without padding, per ACME/JWS."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def rsa_public_jwk_from_private_key_pem(pem_path: str) -> dict:
    with open(pem_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    pub = key.public_key().public_numbers()
    n = pub.n.to_bytes((pub.n.bit_length() + 7) // 8, "big")
    e = pub.e.to_bytes((pub.e.bit_length() + 7) // 8, "big")
    return {"kty": "RSA", "n": b64url(n), "e": b64url(e)}


def sign_rs256(private_key_pem_path: str, signing_input: bytes) -> bytes:
    with open(private_key_pem_path, "rb") as f:
        key = serialization.load_pem_private_key(f.read(), password=None)
    return key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())


def jws_post(
    url: str,
    nonce: str,
    payload_obj: dict | str,
    account_key_path: str,
    jwk: dict | None = None,
    kid: str | None = None,
):
    protected = {"alg": "RS256", "nonce": nonce, "url": url}
    if kid:
        protected["kid"] = kid
    elif jwk:
        protected["jwk"] = jwk
    else:
        raise ValueError("Must provide either jwk (newAccount) or kid (subsequent requests)")

    protected_b64 = b64url(json.dumps(protected, separators=(",", ":")).encode())
    # ACME POST-as-GET: payload is the empty string (not JSON "''")
    if payload_obj == "":
        payload_b64 = b64url(b"")
    else:
        payload_b64 = b64url(json.dumps(payload_obj, separators=(",", ":")).encode())
    signing_input = f"{protected_b64}.{payload_b64}".encode()
    sig = sign_rs256(account_key_path, signing_input)
    body = {"protected": protected_b64, "payload": payload_b64, "signature": b64url(sig)}
    return httpx.post(url, json=body)


def get_nonce() -> str:
    r = httpx.head(f"{BASE}/new-nonce")
    r.raise_for_status()
    nonce = r.headers.get("Replay-Nonce")
    if not nonce:
        raise RuntimeError("Server did not return Replay-Nonce")
    return nonce


def main():
    account_key = os.path.join(TMP, "account.key")
    domain_csr = os.path.join(TMP, "domain.csr")
    domain_der = os.path.join(TMP, "domain.der")
    issued_crt = os.path.join(TMP, "issued.crt")

    if not os.path.isfile(account_key):
        print(f"Missing {account_key}. Create an RSA key, e.g.: openssl genrsa -out {account_key} 2048")
        sys.exit(1)
    if not os.path.isfile(domain_csr):
        print(f"Missing {domain_csr}. Create a CSR with SAN DNS (required by DigiCert One TLM). See docstring at top of this file.")
        sys.exit(1)

    print("Directory...")
    directory = httpx.get(f"{BASE}/directory").json()
    print("  newAccount:", directory.get("newAccount"))
    print("  newOrder:", directory.get("newOrder"))

    jwk = rsa_public_jwk_from_private_key_pem(account_key)

    # --- newAccount ---
    print("newAccount...")
    nonce = get_nonce()
    account_payload = {
        "contact": ["mailto:test@example.com"],
        "termsOfServiceAgreed": True,
        "product_id": os.environ.get("ACME_PRODUCT_ID", "ABC123"),
    }
    r = jws_post(directory["newAccount"], nonce, account_payload, account_key, jwk=jwk)
    if r.status_code not in (200, 201):
        print("newAccount failed:", r.status_code, r.text)
        sys.exit(1)
    kid = r.headers.get("Location")
    if not kid:
        print("newAccount missing Location (kid)")
        sys.exit(1)
    print("  kid:", kid)

    # --- newOrder ---
    print("newOrder...")
    nonce = get_nonce()
    order_payload = {"identifiers": [{"type": "dns", "value": "example.local"}]}
    r = jws_post(directory["newOrder"], nonce, order_payload, account_key, kid=kid)
    if r.status_code != 201:
        print("newOrder failed:", r.status_code, r.text)
        sys.exit(1)
    order = r.json()
    finalize_url = order.get("finalize")
    if not finalize_url:
        print("newOrder response missing finalize")
        sys.exit(1)
    print("  finalize:", finalize_url)

    # --- CSR to DER ---
    subprocess.run(
        ["openssl", "req", "-in", domain_csr, "-outform", "DER", "-out", domain_der],
        check=True,
        capture_output=True,
    )
    with open(domain_der, "rb") as f:
        der = f.read()
    csr_b64url = base64.urlsafe_b64encode(der).decode("ascii").rstrip("=")
    finalize_payload = {"csr": csr_b64url}

    # --- finalize ---
    print("finalize...")
    nonce = get_nonce()
    r = jws_post(finalize_url, nonce, finalize_payload, account_key, kid=kid)
    if r.status_code != 200:
        print("finalize failed:", r.status_code, r.text)
        sys.exit(1)
    order = r.json()
    cert_url = order.get("certificate")
    if not cert_url:
        print("finalize response missing certificate URL:", order)
        sys.exit(1)
    print("  certificate URL:", cert_url)

    # --- fetch certificate (POST-as-GET) ---
    print("Fetching certificate...")
    nonce = get_nonce()
    # ACME POST-as-GET: payload is the empty string ""
    r = jws_post(cert_url, nonce, "", account_key, kid=kid)
    if r.status_code != 200:
        print("cert fetch failed:", r.status_code, r.text[:500])
        sys.exit(1)
    cert_pem = r.text
    if "BEGIN CERTIFICATE" not in cert_pem:
        print("cert response is not PEM")
        sys.exit(1)

    os.makedirs(TMP, exist_ok=True)
    with open(issued_crt, "w") as f:
        f.write(cert_pem)
    print(f"Issued certificate saved to {issued_crt}")


if __name__ == "__main__":
    main()

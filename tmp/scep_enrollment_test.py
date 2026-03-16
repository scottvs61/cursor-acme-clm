"""
SCEP enrollment smoke test: issue a certificate through the SCEP server.

Prerequisites:
  - SCEP server running at SCEP_BASE_URL (default http://127.0.0.1:8002)
  - tmp/domain.csr or tmp/scep.csr : PEM CSR (e.g. create with SAN for DigiCert:
      openssl req -new -key tmp/domain.key -subj "/CN=scep-test.local" -out tmp/domain.csr
    Or use a CSR with SAN; see tmp/acme_smoke_test2.py docstring for SAN example.)

Usage (from repo root):
  python tmp/scep_enrollment_test.py

Optional env:
  SCEP_BASE_URL   - SCEP server URL (default http://127.0.0.1:8002)
  SCEP_PRODUCT_ID - product_id for enrollment (required by server if not in config default)
  SCEP_API_KEY    - When SCEP server requires X-API-Key (config or CLM-generated key), set this
                    to the same key so the test can authenticate.

On success, the issued certificate is written to tmp/scep_issued.crt.
"""

import os
import sys

import httpx

# Default: SCEP server on port 8002 (cursor-acme-clm SCEP)
SCEP_BASE = os.environ.get("SCEP_BASE_URL", "http://127.0.0.1:8002").rstrip("/")
TMP = os.path.dirname(os.path.abspath(__file__))


def main():
    # Prefer scep.csr for SCEP-specific test; fall back to domain.csr
    csr_path = os.path.join(TMP, "scep.csr")
    if not os.path.isfile(csr_path):
        csr_path = os.path.join(TMP, "domain.csr")
    out_crt = os.path.join(TMP, "scep_issued.crt")

    if not os.path.isfile(csr_path):
        print(f"Missing CSR. Create one, e.g.:")
        print(f"  openssl genrsa -out {os.path.join(TMP, 'domain.key')} 2048")
        print(f"  openssl req -new -key {os.path.join(TMP, 'domain.key')} -subj '/CN=scep-test.local' -out {csr_path}")
        sys.exit(1)

    with open(csr_path) as f:
        csr_pem = f.read()
    if "BEGIN CERTIFICATE REQUEST" not in csr_pem:
        print(f"{csr_path} does not look like a PEM CSR")
        sys.exit(1)

    print("GetCACert...")
    r = httpx.get(f"{SCEP_BASE}/GetCACert")
    r.raise_for_status()
    print(f"  status {r.status_code}, content-type {r.headers.get('content-type')}")

    print("GetCACaps...")
    r = httpx.get(f"{SCEP_BASE}/GetCACaps")
    r.raise_for_status()
    print("  caps:", r.text.strip() or "(empty)")

    print("PKIOperation (JSON with csr_pem)...")
    body = {"csr_pem": csr_pem}
    product_id = os.environ.get("SCEP_PRODUCT_ID")
    if product_id:
        body["product_id"] = product_id
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("SCEP_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    r = httpx.post(
        f"{SCEP_BASE}/PKIOperation",
        json=body,
        headers=headers,
        timeout=60.0,
    )
    if r.status_code == 401:
        print("PKIOperation failed: 401 Unauthorized. SCEP server requires X-API-Key.")
        print("Set SCEP_API_KEY to the key (from config or CLM Administration → Keys, scope SCEP).")
        sys.exit(1)
    if r.status_code != 200:
        print(f"PKIOperation failed: {r.status_code}")
        print(r.text[:1000])
        sys.exit(1)
    cert_pem = r.text
    if "BEGIN CERTIFICATE" not in cert_pem:
        print("Response is not a PEM certificate")
        print(r.text[:500])
        sys.exit(1)

    os.makedirs(TMP, exist_ok=True)
    with open(out_crt, "w") as f:
        f.write(cert_pem)
    print(f"Issued certificate saved to {out_crt}")


if __name__ == "__main__":
    main()

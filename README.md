# ACME + Certificate Lifecycle Manager (CLM) Platform

Single-repo platform: ACME server, CLM API, SCEP server, bulk enrollment, and graphical UI.  
CA and integration settings are driven by configuration (no hardcoded CA).

## Structure

- **`config/`** – YAML configuration (CAs, ServiceNow, SCEP, app URLs).
- **`lib/`** – Shared code: cert parsing, config loader, CA-agnostic issuance.
- **`acme/`** – ACME v2 server (requires product_id; sends issued certs to CLM).
- **`clm/`** – CLM backend (certificates, events, bulk enroll, APIs; optional ServiceNow CMDB sync).
- **`scep/`** – SCEP server (GetCACert, GetCACaps, PKIOperation); issues via configured CA and ingests to CLM.
- **`frontend/`** – React + Vite graphical UI (certificates, bulk enroll, SCEP info).

## Quick start

**All commands from repo root:** `~/cursor-acme-clm`

```bash
# Create venv and install Python deps
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Build the graphical UI (optional; or run dev server)
cd frontend && npm install && npm run build && cd ..

# Edit config. Set env vars for secrets: DIGICERT_ONE_API_KEY, DIGICERT_ONE_PROFILE_ID, etc.

# Terminal 1: CLM (API + built UI at http://localhost:8001)
export PYTHONPATH=.
.venv/bin/python -m uvicorn clm.app.main:app --reload --host 0.0.0.0 --port 8001

# Terminal 2: ACME server (http://localhost:8000)
export PYTHONPATH=.
.venv/bin/python -m uvicorn acme.app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3 (optional): SCEP server (http://localhost:8002)
export PYTHONPATH=.
.venv/bin/python -m uvicorn scep.app.main:app --reload --host 0.0.0.0 --port 8002
```

Or use scripts: `bash run_clm.sh`, `bash run_acme.sh`, `bash run_scep.sh`.

**UI development:** Run the React dev server for hot reload: `cd frontend && npm run dev` (http://localhost:5173, proxies API to 8001).

## Features

- **Certificates** – List and inspect certificates (ACME, API, SCEP, bulk).
- **Bulk enrollment** – POST multiple CSRs to `/api/bulk/enroll`; optional default Product ID; up to 100 per request.
- **SCEP** – GetCACert, GetCACaps, PKIOperation; optional JSON body `{ "csr_pem": "..." }` for testing; issued certs are sent to CLM with source `scep`.

## Configuration

See `config/config.example.yaml` for CA (DigiCert One TLM, CertCentral), SCEP (`base_url`, `ca_cert_pem`, `default_product_id`), and ServiceNow placeholders.  
Secrets via environment variables (e.g. `DIGICERT_ONE_API_KEY`, `SCEP_DEFAULT_PRODUCT_ID`); see `lib/config.py`.

---

## Backend: DigiCert TLM and CertCentral

**Yes.** When the configured CA in `config/config.yaml` is **DigiCert One TLM** or **DigiCert CertCentral**, all enrollment flows use the DigiCert REST APIs on the backend:

| Flow | How it uses DigiCert |
|------|----------------------|
| **ACME** | On finalize, the server calls `lib.issuance.issue_certificate()` with the CSR and the order’s `product_id`. That dispatches to DigiCert One TLM (`/mpki/api/v1/certificate`) or CertCentral (enrollment endpoint) per config. |
| **CLM REST API** | `POST /api/bulk/enroll` and any path that issues a cert call the same `issue_certificate()`, so they use the same DigiCert TLM/CertCentral REST APIs. `POST /api/certificates` and `POST /api/events/issued` store or ingest already-issued certs (e.g. from ACME); they do not call DigiCert. |
| **SCEP** | `POST /PKIOperation` calls `issue_certificate()` for each enrollment, so SCEP issuance goes through the same DigiCert backend. |

Issuance is **CA-agnostic**: you choose the CA in config (`cas.default` and the `type` of each CA). Today the implemented types are `digicert_one_tlm` and `digicert_certcentral`. Certificate **listing and management** in the UI/API use the CLM’s own SQLite store; DigiCert is used for **enrollment/issuance** only, not as the source of truth for the CLM inventory.

---

## Access control (SCEP, ACME, REST API, UI)

### Current state

- **SCEP, ACME, and REST API:** Access is **not** controlled. There is no authentication or authorization: any client that can reach the service can use it (subject to CA policy for issuance). CORS on the CLM API is limited to `http://localhost:5173` and `http://localhost:8001`; that only restricts browser origins, not direct API or SCEP calls.
- **UI:** The React app is served as static files (by CLM or the Vite dev server). There is **no login or access control**; anyone who can load the URL can use the UI, and the UI calls the CLM API without any credentials.

### How access could be controlled

- **REST API (CLM):** Add auth in front of the API (e.g. API key header, OAuth2 access tokens, or mTLS). Validate the token/key in FastAPI middleware or a dependency and restrict CORS to your real frontend origin(s). Optionally add per-endpoint or per-role authorization.
- **ACME:** The protocol uses account keys and JWS; today the server does **not** verify JWS signatures (prototype). Enabling **JWS signature verification** would tie each request to an account key and effectively restrict who can create orders or finalize. You can also put ACME behind a reverse proxy that enforces mTLS or IP allowlists.
- **SCEP:** Add client authentication (e.g. challenge password, or reverse proxy with mTLS / VPN) and/or network-level restrictions so only trusted clients can reach the SCEP endpoints.
- **UI:** Access can be controlled by putting an identity provider in front of the app. Users would log in before reaching the CLM UI; the app would then call the CLM API with a token that the backend validates.

### Okta FastPass (passwordless) for the UI

The app does **not** implement Okta or FastPass today. You can **leverage Okta FastPass** (and/or Okta SSO) in one of these ways:

1. **Okta in front of the app (recommended):** Put the CLM UI behind Okta. For example: deploy the UI on a host that is protected by **Okta Web Application** (or Okta as SAML/OIDC IdP in front of a reverse proxy). Users hit Okta first, sign in with FastPass (or password); after success they are redirected to the CLM UI. The UI then calls the CLM API; the API can remain internal (e.g. only from the same host or from a BFF that forwards requests with a validated Okta session or token).
2. **Okta in the frontend:** Use the **Okta Sign-In Widget** or **Okta Auth SDK** in the React app. The app redirects unauthenticated users to Okta, uses FastPass if configured in your Okta org, and after login receives an access or ID token. The app sends that token (e.g. `Authorization: Bearer <token>`) to the CLM API; the API (or a BFF) must then **validate the token** (e.g. Okta JWKS) and enforce authorization. Without backend validation, the UI would still be the only thing checking “who is logged in.”
3. **API gateway / BFF:** Put an API gateway or Backend-for-Frontend in front of the CLM API. The gateway requires a valid Okta token (or session) and optionally checks FastPass/assurance level; only then does it forward requests to the CLM API. The UI talks only to the gateway and never to the CLM API directly without going through Okta.

To use **FastPass** specifically, configure your Okta application to allow passwordless (e.g. WebAuthn/FIDO2) and set the appropriate policy; the integration patterns above stay the same, with Okta handling the FastPass step during login.

---

## Security

**What is built in today**

| Service | In place | Not in place |
|--------|----------|--------------|
| **ACME** | **Nonce replay protection** – each request must include a valid, single-use nonce (from `GET /new-nonce`). JWS body is parsed (protected header + payload). | **No JWS signature verification** in this prototype – the server does not cryptographically verify that the request was signed by the account key. **No TLS** in the app (use a reverse proxy for HTTPS). No rate limiting. |
| **CLM API** | **CORS** – only `http://localhost:5173` and `http://localhost:8001` are allowed origins. **Secrets** – CA keys and ServiceNow credentials come from config/env, not from request body. | **No authentication** – any client that can reach the API can list certificates, create certificates, call bulk enroll, and post events. No API keys, no auth middleware. No rate limiting. |
| **SCEP** | **Issuance** – certs are issued only via the configured CA (which may enforce its own checks). **CLM ingest** – issued certs are sent to CLM with source `scep`. | **No client authentication** – anyone who can reach the SCEP server can request a cert (subject to CA policy). No challenge password or other SCEP client auth. **No TLS** in the app. No rate limiting. GetCACert can return a placeholder cert if not configured. |

**Recommendations for production**

- Run all services behind **HTTPS** (reverse proxy: nginx, Caddy, or cloud load balancer). Do not expose plain HTTP to the internet.
- Add **authentication and authorization** to the CLM API (e.g. API keys, OAuth2, or mTLS) and restrict CORS to your real frontend origin(s).
- Enable **JWS signature verification** in the ACME server (verify each request with the account’s public key).
- Consider **rate limiting** on ACME, CLM, and SCEP to reduce abuse and DoS.
- For SCEP, configure a real **CA cert** in `scep.ca_cert_pem` (or `ca_cert_path`) and, if required by your environment, add client authentication or network-level access control.
- Keep **secrets** (CA API keys, ServiceNow credentials, etc.) in environment variables or a secret manager; do not commit them to the repo.

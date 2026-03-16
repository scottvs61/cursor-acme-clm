# ACME + Certificate Lifecycle Manager (CLM) Platform

Single-repo platform: ACME server, CLM API, SCEP server, bulk enrollment, and graphical UI.  
CA and integration settings are driven by configuration (no hardcoded CA).

## Structure

- **`config/`** – YAML configuration (CAs, ServiceNow, SCEP, app URLs).
- **`docs/adr/`** – Architecture Decision Records (e.g. [ADR 0001](docs/adr/0001-platform-services-and-network.md) – platform services and network diagram).
- **`docs/ko/`** – [Knowledge & Operations (KO) documents](docs/ko/README.md) for consumers of each service (ACME, CLM API, SCEP).
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

- **Certificates** – List and inspect certificates (ACME, API, SCEP, bulk); filter by **product ID**; view **revoked** status.
- **Manual enroll** – Enroll a single certificate from a CSR: `POST /api/enroll` (or use the Enroll tab in the UI).
- **Renew** – `POST /api/certificates/{id}/renew` with a new CSR; issues a new cert and records it as a renewal.
- **Revoke** – `POST /api/certificates/{id}/revoke` marks a certificate as revoked in CLM and revokes it at DigiCert One TLM when configured.
- **Bulk enrollment** – POST multiple CSRs to `/api/bulk/enroll`; optional default Product ID; up to 100 per request.
- **SCEP** – GetCACert, GetCACaps, PKIOperation; optional JSON body `{ "csr_pem": "..." }` for testing; issued certs are sent to CLM with source `scep`.

## Configuration

Use `config/config.yaml` for runtime settings. Copy from `config/config.example.yaml` and set values. Any value can use **environment variable substitution**: write `${VAR_NAME}` and it will be replaced at load time (see `lib/config.py`).

### How `config.yaml` should look

**0. `subject_defaults`** – Default TLS Subject DN for **generated** CSRs (when the user chooses “Generate key and CSR”). Only C, ST, L, O are pre-defined here; **Common Name (CN)** and **Organizational Unit (OU)** are provided at enrollment. The CSR sent to the CA (e.g. DigiCert) includes this full subject so the issued certificate has complete Subject DN in the PKCS#12.

| Key | Description | Example |
|-----|-------------|---------|
| `C` | Country (2-letter) | `US` |
| `ST` | State or Province | `California` |
| `L` | Locality (city) | `San Francisco` |
| `O` | Organization | `Acme Corp` |

**1. `app`** – URLs for the platform (no secrets here):

| Key | Description | Example |
|-----|-------------|---------|
| `acme_base_url` | Public URL of the ACME server (directory, orders, certs). | `http://localhost:8000` |
| `clm_base_url` | Public URL of the CLM API (and UI if served there). | `http://localhost:8001` |
| `clm_ingest_url` | URL where ACME/SCEP POST issued certs (CLM `POST /api/events/issued`). Leave empty to disable ingest. | `http://localhost:8001/api/events/issued` |

**2. `cas`** – CA backends for issuance (DigiCert TLM, CertCentral, or others):

| Key | Description |
|-----|-------------|
| `default` | Name of the CA to use when no `ca_name` is specified (e.g. `digicert_one_tlm`). |
| *`<ca_name>`* | Each CA is a key under `cas` with its own block (see below). |

**DigiCert One TLM** (e.g. `digicert_one_tlm`):

| Key | Required | Description |
|-----|----------|-------------|
| `type` | Yes | Must be `digicert_one_tlm`. |
| `base_url` | Yes | DigiCert One base (e.g. `https://demo.one.digicert.com`). |
| `api_key` | Yes | API key (use `${DIGICERT_ONE_API_KEY}`). |
| `profile_id` | Yes | Profile GUID for issuance. |
| `seat_id` | Yes | Seat identifier (or use `account_id`). |
| `account_id` | No | Fallback if `seat_id` not set. |

**DigiCert CertCentral** (e.g. `digicert_certcentral`):

| Key | Required | Description |
|-----|----------|-------------|
| `type` | Yes | Must be `digicert_certcentral`. |
| `base_url` | No | Defaults to `https://api.digicert.com`. |
| `api_key` | Yes | CertCentral API key. |
| `product_name_id` | Yes | Product/template for SSL issuance. |
| `organization_id` | No | Org ID when required. |

**3. `scep`** – SCEP server:

| Key | Description |
|-----|-------------|
| `base_url` | Public URL of the SCEP server (for GetCACert, GetCACaps, PKIOperation). |
| `ca_cert_pem` | PEM string for GetCACert, or omit and use `ca_cert_path`. |
| `ca_cert_path` | Path to a file containing the CA cert PEM (relative to repo root or absolute). Used if `ca_cert_pem` is empty. |
| `default_product_id` | Product ID to associate with SCEP-issued certs (e.g. `${SCEP_DEFAULT_PRODUCT_ID}`). |

**4. `servicenow`** – Optional CMDB sync:

| Key | Description |
|-----|-------------|
| `enabled` | Set to `true` to push certificate records to ServiceNow. |
| `instance` | ServiceNow instance URL (e.g. `https://your-instance.service-now.com`). |
| `username` / `password` | Basic auth (use env vars). |
| `table` | Target table (e.g. `u_certificate_ci`). |
| `field_mapping` | Map of our field names to ServiceNow column names. |

**Example minimal `config/config.yaml`** (secrets from env):

```yaml
app:
  acme_base_url: "http://localhost:8000"
  clm_base_url: "http://localhost:8001"
  clm_ingest_url: "http://localhost:8001/api/events/issued"

cas:
  default: digicert_one_tlm
  digicert_one_tlm:
    type: digicert_one_tlm
    base_url: "https://demo.one.digicert.com"
    api_key: "${DIGICERT_ONE_API_KEY}"
    profile_id: "${DIGICERT_ONE_PROFILE_ID}"
    seat_id: "${DIGICERT_ONE_SEAT_ID}"
    account_id: "${DIGICERT_ONE_ACCOUNT_ID}"

scep:
  base_url: "http://localhost:8002"
  ca_cert_pem: ""
  default_product_id: "${SCEP_DEFAULT_PRODUCT_ID}"

servicenow:
  enabled: false
```

Full sample with all sections and comments: `config/config.example.yaml`. Do not commit `config/config.yaml` if it contains real secrets; it is listed in `.gitignore`.

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

### GUI login and roles

The CLM GUI **requires users to sign in**. After login, users are either **administrators** or **regular users**:

- **Administrators** can do everything: list and manage certificates, enroll, revoke, bulk enroll, view help, and access **Administration** (generate keys, add/edit/remove users and their roles).
- **Regular users** can list certificates, view one certificate, and view help. They cannot enroll, revoke, bulk enroll, or access Administration.

**Initial administrator:** On first startup, if no users exist, the CLM creates a single administrator with email **scott_stephenson@mckinsey.com** and a **one-time password**. The password is written to **`config/initial_admin_password.txt`** (or `initial_admin_password.txt` in the current working directory if `config/` is not writable). The server logs: `CLM: Initial administrator created. One-time password written to ...`  
**Use that password to sign in once, then change it** via the “Change password” screen. After that, delete the password file. To set the initial password yourself (e.g. from a secret manager), set the environment variable **`SEED_ADMIN_PASSWORD`** before the first run; then the file is not written.

**Secure storage:** User passwords are stored only as **bcrypt hashes** in the CLM SQLite database; plaintext passwords are never logged or returned. Generated **API and SCEP keys** are stored as **SHA-256 hashes**; the plaintext key is returned **only once** when an administrator generates it (copy it immediately). ACME does not use static keys; it uses account key + JWS signing (see below). JWT signing uses **`JWT_SECRET`** or **`CLM_JWT_SECRET`** from the environment; set it in production.

**Administration (admin only):**

- **Keys:** Generate keys for **SCEP** or **API** (with role admin/user). Each key is shown once with a “Copy” button; after that it cannot be retrieved. Use these keys so that SCEP/API require the `X-API-Key` header when keys exist in the DB or config. **ACME** uses built-in account key + JWS signing (no static key).
- **Users:** Add users (email + temporary password, role), change a user’s role, or remove a user. New users can be required to change password on first login.

### Optional API keys and roles (when configured)

In addition to GUI login, you can use **API keys** for programmatic access:

- **CLM API:** In `config/config.yaml`, set the `auth.api_keys` list, or generate API keys in the Administration → Keys tab (stored in DB). Each request must include header `X-API-Key` with a configured key. **Admin** keys have full access; **user** keys can only list certificates, get one certificate, and get help. See `docs/security-and-rbac.md`.
- **ACME:** Uses **account key + JWS** (RFC 8555). Every POST is signed by the client and verified by the server; no static API key. **SCEP:** Generate keys in Administration → Keys (SCEP). When a SCEP key exists (in config or DB), `PKIOperation` requires the `X-API-Key` header to match.

When **no users exist** in the database and **no** `auth.api_keys` are configured, the CLM API allows unauthenticated access (backward compatibility). Health and static UI (`/health`, `/`) are always unauthenticated.

### Current state when auth is not configured

- **SCEP, ACME, and REST API:** If no users and no API keys are configured, any client that can reach the service can use it. Once at least one user exists (e.g. after first startup), the GUI requires login and the API requires a Bearer token or X-API-Key.
- **UI:** The React app requires sign-in. After login, the app sends a JWT (Bearer token) with every API request.

### Further options

- **REST API (CLM):** Beyond API keys, you can put the API behind OAuth2, mTLS, or an API gateway and restrict CORS to your frontend origin(s).
- **ACME:** **JWS signature verification** is enabled: each request is verified with the account’s public key. You can also put ACME behind a reverse proxy that enforces mTLS or IP allowlists.
- **SCEP:** Add challenge password or network-level restrictions in addition to or instead of the optional API key.
- **UI:** Put an identity provider (e.g. Okta) in front of the app; the UI would then call the CLM API with a token or API key provided after login.

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
| **ACME** | **Nonce replay protection** – each request must include a valid, single-use nonce. **JWS signature verification** – every POST is verified with the account’s public key (JWK). | **No TLS** in the app (use a reverse proxy for HTTPS). No rate limiting. |
| **CLM API** | **CORS** – only `http://localhost:5173` and `http://localhost:8001` are allowed origins. **GUI login** – users sign in with email/password; JWT or X-API-Key required for `/api/*` when users or API keys exist. **Passwords** – stored as bcrypt hashes. **Generated keys** – stored as SHA-256 hashes; plaintext shown once. **Secrets** – CA keys and ServiceNow credentials from config/env. | Rate limiting not implemented. Set **JWT_SECRET** in production. |
| **SCEP** | **Issuance** – certs are issued only via the configured CA (which may enforce its own checks). **CLM ingest** – issued certs are sent to CLM with source `scep`. | **No client authentication** – anyone who can reach the SCEP server can request a cert (subject to CA policy). No challenge password or other SCEP client auth. **No TLS** in the app. No rate limiting. GetCACert can return a placeholder cert if not configured. |

**Recommendations for production**

- Run all services behind **HTTPS** (reverse proxy: nginx, Caddy, or cloud load balancer). Do not expose plain HTTP to the internet.
- Add **authentication and authorization** to the CLM API (e.g. API keys, OAuth2, or mTLS) and restrict CORS to your real frontend origin(s).
- ACME **JWS signature verification** is enabled (each request verified with the account’s public key).
- Consider **rate limiting** on ACME, CLM, and SCEP to reduce abuse and DoS.
- For SCEP, configure a real **CA cert** in `scep.ca_cert_pem` (or `ca_cert_path`) and, if required by your environment, add client authentication or network-level access control.
- Keep **secrets** (CA API keys, ServiceNow credentials, etc.) in environment variables or a secret manager; do not commit them to the repo.

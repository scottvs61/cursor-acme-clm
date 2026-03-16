# KO: CLM REST API

**Service:** Certificate Lifecycle Manager (CLM) API  
**Purpose:** Store and list certificates, ingest issued certificates from ACME/SCEP, support bulk enrollment, and (when configured) sync certificate records to ServiceNow CMDB.

**Audience:** API consumers (scripts, automation, other services), operators using the web UI, and systems that need to register or query certificate records.

---

## 1. Base URL and health

- **Default base URL:** `http://localhost:8001` (configurable by the platform operator via `config.config.yaml` → `app.clm_base_url`).
- **Health check:** `GET {base}/health`  
  Returns `{ "status": "ok" }` when the service is up.

**Example:**

```bash
curl -s http://localhost:8001/health
```

---

## 2. API endpoints (consumer view)

All API routes are under the `/api` prefix. Request/response are JSON unless noted.

### 2.1 Certificates

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/certificates` | List certificates (newest first). Query param: `product_id` to filter by product. |
| GET | `/api/certificates/{id}` | Get one certificate by ID. |
| POST | `/api/certificates` | Register an existing certificate (PEM). Does not call the CA. |
| POST | `/api/enroll` | Manually enroll one certificate from a CSR (issues via CA, stores in CLM). |
| POST | `/api/certificates/{id}/renew` | Issue a new cert from a CSR and record as renewal of this certificate. |
| POST | `/api/certificates/{id}/revoke` | Mark the certificate as revoked in CLM (does not call CA). |

### 2.2 Events (ingest)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/events/issued` | Ingest an issued certificate. Creates or updates the certificate record by SHA-256 fingerprint and creates an “issued” event. Used by ACME and SCEP servers internally. |

### 2.3 Bulk enrollment

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/bulk/enroll` | Submit multiple CSRs; each is sent to the configured CA for issuance. Certificates are stored in CLM and events created. Max 100 CSRs per request. |

---

## 3. Request and response examples

### List certificates

**Request:** `GET /api/certificates`

**Response:** `200 OK`, JSON array of certificate objects.

```json
[
  {
    "id": "uuid",
    "created_at": "2025-03-10T12:00:00Z",
    "source": "acme",
    "product_id": "my-product",
    "common_name": "example.com",
    "sans_dns": ["example.com", "www.example.com"],
    "serial_number": "ABC123",
    "not_before": "2025-03-10T00:00:00Z",
    "not_after": "2026-03-10T00:00:00Z",
    "sha256_fingerprint": "abc...",
    "pem": "-----BEGIN CERTIFICATE-----\n..."
  }
]
```

### Get one certificate

**Request:** `GET /api/certificates/{id}`

**Response:** `200 OK`, single certificate object (same shape as above), or `404` if not found.

### Register a certificate (no issuance)

**Request:** `POST /api/certificates`  
**Body:**

```json
{
  "pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "source": "api",
  "product_id": "my-product"
}
```

- **pem:** Full certificate PEM (must be a certificate, not a CSR).
- **source:** One of `api`, `acme`, `scep`.
- **product_id:** Optional string.

**Response:** `200 OK`, the stored certificate object.

### Manual enroll (single certificate from CSR)

**Request:** `POST /api/enroll`  
**Body:** `{ "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\\n...\\n-----END CERTIFICATE REQUEST-----", "product_id": "optional" }`  
**Response:** `200 OK`, the issued certificate object (same shape as above). The certificate is issued via the configured CA and stored in CLM.

### Renew certificate

**Request:** `POST /api/certificates/{id}/renew`  
**Body:** `{ "csr_pem": "..." }`  
**Response:** `200 OK`, the new certificate object. The new cert is issued via the CA and stored; an event of type `renewed` is created with `previous_certificate_id` in the payload.

### Revoke certificate

**Request:** `POST /api/certificates/{id}/revoke` (no body)  
**Response:** `200 OK`, `{ "ok": true, "certificate_id": "...", "revoked_at": "...", "ca_revoked": true|false, "ca_revoke_error": null|"..." }`. Marks the certificate as revoked in CLM and revokes it at DigiCert One TLM when configured. Optional body: `{ "revocation_reason": "cessation_of_operation" }` (or `key_compromise`, etc.).

### Ingest issued certificate (used by ACME/SCEP)

**Request:** `POST /api/events/issued`  
**Body:**

```json
{
  "certificate_pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "source": "acme",
  "product_id": "my-product",
  "raw": { "order_id": "...", "account_id": "..." }
}
```

- **certificate_pem:** Issued certificate PEM.
- **source:** `acme`, `api`, or `scep`.
- **product_id:** Optional.
- **raw:** Optional JSON; stored in the event payload.

**Response:** `200 OK`, `{ "certificate": { ... }, "event": { ... } }`. If a certificate with the same SHA-256 fingerprint exists, it is updated; a new “issued” event is always created.

### Bulk enrollment

**Request:** `POST /api/bulk/enroll`  
**Body:**

```json
{
  "requests": [
    { "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----", "product_id": null },
    { "csr_pem": "...", "product_id": "other-product" }
  ],
  "default_product_id": "my-product"
}
```

- **requests:** Array of 1–100 items. Each has `csr_pem` (required) and optional `product_id`.
- **default_product_id:** Used when an item’s `product_id` is null or omitted.

**Response:** `200 OK`:

```json
{
  "results": [
    { "success": true, "certificate_id": "uuid", "certificate_pem": "-----BEGIN CERTIFICATE-----\n..." },
    { "success": false, "error": "CA rejected request: ..." }
  ],
  "total": 2,
  "succeeded": 1,
  "failed": 1
}
```

---

## 4. Configuration that affects you

- **Base URL:** Ask the operator for the CLM API base URL (e.g. `https://clm.example.com`).
- **CORS:** Browsers are restricted to allowed origins (e.g. the UI origin). Scripts and server-side clients are not limited by CORS.
- **Ingest URL:** The operator may configure `clm_ingest_url` so that ACME/SCEP automatically POST to this API; you do not need to call `/api/events/issued` yourself for those flows.

---

## 5. Authentication and security

- **Current:** No API keys or authentication. Any client that can reach the API can list, create, and bulk-enroll. CORS limits only browser origins.
- **Production:** Expect authentication (e.g. API key, OAuth2) and HTTPS. Do not send secrets in request bodies; use headers or tokens as instructed by the operator.

---

## 6. Web UI

The same base URL may serve the **web UI** at `/` (e.g. `http://localhost:8001/`). The UI uses the same API to list certificates, run bulk enrollment, and display SCEP info. No separate login is implemented in the current version.

### 6.1 Screenshots (when available)

Screenshots are stored in `docs/ko/screenshots/`. If present, they appear below.

**Certificates list** – Sidebar and certificate table (newest first). Use **Details** to open the detail panel.

![Certificates list](screenshots/clm-certificates-list.png)

**Certificate detail** – JSON detail for one certificate (id, common_name, sans_dns, source, product_id, validity, fingerprint).

![Certificate detail](screenshots/clm-certificate-detail.png)

**Bulk Enroll** – Default Product ID field and CSRs textarea. Paste one or more PEM CSRs and click **Enroll**.

![Bulk Enroll form](screenshots/clm-bulk-enroll.png)

**Bulk Enroll result** – Per-row status (OK/Failed) and certificate ID or error message.

![Bulk Enroll result](screenshots/clm-bulk-enroll-result.png)

**SCEP** – SCEP base URL, endpoints (GetCACert, GetCACaps, PKIOperation), and usage notes.

![SCEP page](screenshots/clm-scep.png)

To add or refresh screenshots, see `docs/ko/screenshots/README.md` for suggested filenames and capture instructions.

---

## 7. Errors and troubleshooting

| HTTP | Meaning / action |
|------|------------------|
| 400 | Validation error (e.g. invalid PEM, wrong `source`, missing `csr_pem`). Response body includes `detail`. |
| 404 | Certificate ID not found for `GET /api/certificates/{id}`. |
| 500 | Server or CA error. Check server logs; for bulk enroll, see per-item `error` in `results`. |

---

## 8. References

- Platform README: configuration, security, access control
- ADR 0001: architecture and network

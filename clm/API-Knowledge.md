# CLM REST API — Knowledge Document

This document describes the Certificate Lifecycle Manager (CLM) REST API for support teams, automation, and integration. The same CLM server that serves this GUI exposes the API.

---

## Base URL and health

- **Base URL:** The same host and port as this GUI (e.g. `http://localhost:8001`). Ask your operator for the production URL.
- **Health:** `GET /health` → `{ "status": "ok" }`

Example: `curl -s http://localhost:8001/health`

---

## Authentication

The API does not implement authentication in the default setup. When auth is configured, the operator sets auth.api_keys in config; then X-API-Key header is required and roles (admin vs user) apply. In production, use API keys, OAuth, or network controls. Use HTTPS and follow your organization’s security guidelines.

---

## Product ID (required)

**Product ID is mandatory for all enrollments.** Every enrollment flow (ACME, SCEP, manual enroll, bulk enroll, and ingest) must provide a non-empty `product_id` (or `default_product_id` for bulk). Requests missing it will receive `400` with a validation error.

---

## Endpoints summary

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/certificates` | List certificates (optional `?product_id=...`) |
| GET | `/api/certificates/{id}` | Get one certificate |
| POST | `/api/certificates` | Register a certificate (PEM, no CA issuance) |
| POST | `/api/enroll` | Manual enroll: one CSR or generate key+CSR → PKCS#12 |
| POST | `/api/certificates/{id}/renew` | Renew with a new CSR |
| POST | `/api/certificates/{id}/revoke` | Revoke in CLM and at DigiCert One TLM when configured |
| POST | `/api/events/issued` | Ingest an issued certificate (used by ACME/SCEP) |
| POST | `/api/bulk/enroll` | Enroll up to 100 CSRs in one request |
| GET | `/api/help` | This API knowledge document (markdown) |

---

## Certificates

### List certificates

**Request:** `GET /api/certificates`

Optional query: `product_id` — filter by product ID.

**Response:** `200 OK`, JSON array of certificate objects (newest first). Each object includes `id`, `created_at`, `source`, `product_id`, `common_name`, `sans_dns`, `serial_number`, `not_before`, `not_after`, `sha256_fingerprint`, `pem`, `revoked_at`.

### Get one certificate

**Request:** `GET /api/certificates/{id}`

**Response:** `200 OK` — single certificate object; or `404` if not found.

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

- **pem:** Certificate PEM (not a CSR).
- **source:** One of `api`, `acme`, `scep`.
- **product_id:** Required.

**Response:** `200 OK` — stored certificate object.

---

## Manual enroll

**Request:** `POST /api/enroll`

Two modes:

**1. Provide your own CSR**

**Body:**

```json
{
  "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----",
  "product_id": "my-product"
}
```

**Response:** `200 OK` — issued certificate object (issued via configured CA, stored in CLM).

**2. Generate key and CSR (receive PKCS#12)**

**Body:**

```json
{
  "generate": true,
  "common_name": "host.example.com",
  "organizational_units": ["IT"],
  "sans_dns": ["host.example.com"],
  "product_id": "my-product",
  "p12_password": "your-password",
  "p12_format": "pfx"
}
```

- **p12_format:** `pfx` (Windows) or `p12` (Linux/macOS).

**Response:** `200 OK` with body = binary PKCS#12 file (Content-Type: application/x-pkcs12). Save as `.pfx` or `.p12` and import with the password you provided.

---

## Renew

**Request:** `POST /api/certificates/{id}/renew`

**Body:** `{ "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----..." }`

**Response:** `200 OK` — new certificate object. Same product ID as the original certificate.

---

## Revoke

**Request:** `POST /api/certificates/{id}/revoke`

**Body (optional):** `{ "revocation_reason": "cessation_of_operation" }`  
Other values: `key_compromise`, `superseded`, `affiliationChanged`, `unspecified`.

**Response:** `200 OK`:

```json
{
  "ok": true,
  "certificate_id": "...",
  "revoked_at": "2026-03-16T18:00:00Z",
  "ca_revoked": true,
  "ca_revoke_error": null
}
```

When the default CA is DigiCert One TLM, the certificate is also revoked at the CA. If `ca_revoked` is false, see `ca_revoke_error` for the reason.

---

## Bulk enrollment

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

- **requests:** 1–100 items. Each has `csr_pem` (required) and optional `product_id` (overrides default).
- **default_product_id:** Required. Used when an item does not set `product_id`.

**Response:** `200 OK`:

```json
{
  "results": [
    { "success": true, "certificate_id": "uuid", "certificate_pem": "..." },
    { "success": false, "error": "CA rejected request: ..." }
  ],
  "total": 2,
  "succeeded": 1,
  "failed": 1
}
```

---

## Ingest issued certificate

Used internally by ACME and SCEP servers. You can also call it to register certificates issued outside the CLM.

**Request:** `POST /api/events/issued`

**Body:**

```json
{
  "certificate_pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "source": "acme",
  "product_id": "my-product",
  "raw": {}
}
```

- **source:** `acme`, `api`, or `scep`.
- **product_id:** Required.

**Response:** `200 OK` — `{ "certificate": { ... }, "event": { ... } }`. If a certificate with the same SHA-256 fingerprint exists, it is updated; an “issued” event is always created.

---

## Errors

| HTTP | Meaning |
|------|--------|
| 400 | Validation error (invalid PEM, missing required field, wrong format). Body has `detail`. |
| 404 | Certificate or resource not found. |
| 500 | Server or CA error. Check logs; for bulk, see per-item `error` in `results`. |

---

## CORS

Browsers are subject to CORS (allowed origins configured by the operator). Server-side clients and scripts are not limited by CORS.

---

## More information

- **Platform README** (repo root): configuration, security, quick start.
- **CLM README** (`clm/README.md`): GUI color and layout customization.
- **KO-CLM-API** (`docs/ko/KO-CLM-API.md`): Extended API and operations guide.

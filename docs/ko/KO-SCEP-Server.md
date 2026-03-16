# KO: SCEP Server

**Service:** SCEP server (Simple Certificate Enrollment Protocol)  
**Purpose:** Issue certificates to devices or MDM via SCEP. The server uses the configured CA (e.g. DigiCert One TLM) for issuance and sends issued certificates to the Certificate Lifecycle Manager (CLM).

**Audience:** Device and MDM administrators configuring SCEP enrollment, and anyone using SCEP clients or testing enrollment (e.g. with a JSON body).

---

## 1. Base URL and endpoints

- **Default base URL:** `http://localhost:8002` (configurable by the platform operator via `config.config.yaml` → `scep.base_url`).

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| GET | `{base}/GetCACert` | Retrieve CA certificate(s) for SCEP client discovery. |
| GET | `{base}/GetCACaps` | Retrieve server capabilities (one per line). |
| POST | `{base}/PKIOperation` | Submit enrollment request (CSR); receive issued certificate. |

---

## 2. GetCACert

**Request:** `GET {base}/GetCACert`

**Response:** `200 OK`, body = CA certificate PEM (or chain), content-type `application/x-x509-ca-cert`.

Use this so your SCEP client knows the CA and can validate the enrollment response. The operator may configure a real CA/intermediate PEM in config; otherwise a placeholder may be returned.

**Example:**

```bash
curl -s http://localhost:8002/GetCACert
```

---

## 3. GetCACaps

**Request:** `GET {base}/GetCACaps`

**Response:** `200 OK`, plain text, one capability per line. Example:

```
POSTPKIOperation
SHA-256
```

Clients use this to determine how to send the enrollment (e.g. POST with PKIOperation).

**Example:**

```bash
curl -s http://localhost:8002/GetCACaps
```

---

## 4. PKIOperation (enrollment)

**Request:** `POST {base}/PKIOperation`

Two input formats are supported:

### 4.1 Standard SCEP (form with message)

- **Content-Type:** `application/x-www-form-urlencoded`
- **Body:** `operation=PKIOperation` and `message=<base64-encoded DER CSR>`  
  Some clients send the CSR as raw DER in the `message` parameter. The server accepts that and issues a certificate.

### 4.2 JSON (for testing or custom clients)

- **Content-Type:** `application/json`
- **Body:**

```json
{
  "csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----",
  "product_id": "my-product"
}
```

- **csr_pem:** PEM-encoded CSR (required).
- **product_id:** Optional; overrides the server’s default product ID for CLM.

**Response:** `200 OK`, body = issued certificate PEM, content-type `application/x-x509-user-cert`. On failure (e.g. CA rejection): `400` with JSON `detail`.

**Example (JSON):**

```bash
curl -s -X POST http://localhost:8002/PKIOperation \
  -H "Content-Type: application/json" \
  -d '{"csr_pem": "-----BEGIN CERTIFICATE REQUEST-----\n...\n-----END CERTIFICATE REQUEST-----", "product_id": "my-product"}'
```

---

## 5. Configuration that affects you

- **Base URL:** Ask the operator for the SCEP base URL (e.g. `https://scep.example.com`). Use it in your device/MDM SCEP configuration.
- **PKIOperation URL:** Typically `{base}/PKIOperation` (e.g. `https://scep.example.com/PKIOperation`).
- **Default product_id:** The operator may set `scep.default_product_id` in config so that enrollments without a product_id are associated with that product in CLM. You can override per request with the JSON `product_id` field when using the JSON API.

---

## 6. Post-enrollment behavior

- Issued certificates are **sent to the CLM** (POST to `clm_ingest_url`) with `source: "scep"` and the chosen `product_id`. They appear in the CLM certificate list and (if configured) in ServiceNow CMDB.
- The server does not retain long-term state; the certificate is returned in the response and stored in CLM.

---

## 7. Authentication and security

- **Current:** No client authentication. Anyone who can reach the server can call GetCACert, GetCACaps, and PKIOperation. Issuance is subject to the CA’s policy (e.g. DigiCert).
- **Production:** Expect HTTPS and possibly client authentication (e.g. challenge password, mTLS, or network restrictions). GetCACert may return a real CA/intermediate when configured.

---

## 8. Errors and troubleshooting

| HTTP | Meaning / action |
|------|------------------|
| 400 | Invalid or missing CSR (e.g. message not valid DER CSR, or JSON missing `csr_pem`). Response body includes `detail`. |
| 400 | CA rejected the request (e.g. profile or validation failure). Check `detail` and CA configuration. |

If the client sends PKCS#7 EnvelopedData that the server cannot decrypt (no server private key configured), use the JSON `csr_pem` format for testing or ask the operator about full SCEP support.

---

## 9. References

- Platform README: configuration, security
- ADR 0001: architecture and network
- KO-CLM-API: certificate list and ingest behavior

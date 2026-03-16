# KO: ACME Server

**Service:** ACME v2 server (RFC 8555)  
**Purpose:** Issue TLS/server certificates from a CSR via the ACME protocol. Certificates are issued by the configured CA (e.g. DigiCert One TLM) and automatically sent to the Certificate Lifecycle Manager (CLM).

**Audience:** Users running ACME clients (e.g. certbot, acme.sh), automation pipelines, or any system that needs to obtain certificates via ACME.

---

## 1. Base URL and discovery

- **Default base URL:** `http://localhost:8000` (configurable by the platform operator via `config.config.yaml` → `app.acme_base_url`).
- **Directory (discovery):** `GET {base}/directory`  
  Returns JSON with URLs for nonce, new account, and new order. Always use this URL as the ACME endpoint in your client.

**Example:**

```bash
curl -s http://localhost:8000/directory
```

**Example response:**

```json
{
  "newNonce": "http://localhost:8000/new-nonce",
  "newAccount": "http://localhost:8000/new-account",
  "newOrder": "http://localhost:8000/new-order"
}
```

- Every response includes a **Replay-Nonce** header. Your client **must** use this nonce in the next JWS request (single use).

---

## 2. Requirements for consumers

- **product_id is required.** When creating an account (`newAccount`), the payload must include a non-standard field **`product_id`** (string). This identifies the product/tenant and is sent to CLM with the issued certificate. Orders are tied to the account’s `product_id`.
- **JWS:** All POST requests must be signed JWS (RFC 7515). Protected header must include `nonce` (from `Replay-Nonce` or `GET /new-nonce`), and either `jwk` (new account) or `kid` (existing account).
- **Order flow:** newAccount → newOrder → (authorizations satisfied) → finalize with CSR → fetch certificate from the returned `certificate` URL.

---

## 3. Key endpoints (consumer view)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/directory` | Discover ACME URLs. |
| GET / HEAD | `/new-nonce` | Get a new nonce (or use `Replay-Nonce` from any response). |
| POST | `/new-account` | Create account. **Body:** JWS with payload including `product_id`. |
| POST | `/new-order` | Create order. **Body:** JWS with payload `{ "identifiers": [ { "type": "dns", "value": "example.com" } ] }`. |
| GET / POST | `/order/{order_id}` | Get order status. When status is `valid`, response includes `certificate` URL. |
| POST | `/finalize/{order_id}` | Submit CSR. **Body:** JWS with payload `{ "csr": "<base64url DER CSR>" }`. |
| GET / POST | `/cert/{cert_id}` | Download issued certificate (PEM). |
| GET | `/auth/{auth_id}` | Get authorization (for challenge discovery; this server marks auth valid for prototype). |

---

## 4. Example workflow (conceptual)

1. **GET** `{base}/directory` → note `newNonce`, `newAccount`, `newOrder`.
2. **GET** `{base}/new-nonce` → store `Replay-Nonce`.
3. **POST** `{base}/new-account` with JWS (protected: `nonce`, `jwk`; payload: `{ "product_id": "my-product", "contact": ["mailto:admin@example.com"] }`) → store account URL from `Location` and next `Replay-Nonce`.
4. **POST** `{base}/new-order` with JWS (protected: `nonce`, `kid` = account URL; payload: `{ "identifiers": [ { "type": "dns", "value": "example.com" } ] }`) → response includes `finalize` URL, `order` URL, `authorizations`.
5. **POST** `{base}/finalize/{order_id}` with JWS (payload: `{ "csr": "<base64url of DER CSR>" }`) → response status `valid` and `certificate` URL.
6. **GET** `{base}/cert/{cert_id}` (or POST with JWS) → PEM certificate.

---

## 5. Configuration that affects you

- **Base URL:** Ask the operator for the ACME base URL (e.g. `https://acme.example.com`). Use it as the ACME server in your client.
- **product_id:** Decide the product/tenant identifier to send in `newAccount`; it will be associated with all certificates from that account and sent to CLM.

---

## 6. Authentication and security

- **Current:** No HTTP authentication. The server uses **nonce replay protection** only; it does **not** verify JWS signatures in this prototype. Anyone who can reach the server can create accounts and orders.
- **Production:** Expect the platform to be behind HTTPS and possibly additional access control. Keep your account private key secure; in a full implementation it would be used to verify requests.

---

## 7. Errors and troubleshooting

| HTTP | ACME error type | Meaning / action |
|------|------------------|------------------|
| 400 | `badNonce` | Nonce invalid or already used. Get a new nonce and retry. |
| 400 | `malformed` | Invalid JWS or missing `product_id`. Check payload and required fields. |
| 400 | `accountDoesNotExist` | `kid` not found. Create account first or use correct account URL. |
| 400 | `orderNotFound` / `orderNotReady` | Invalid or not finalizable order. Check order ID and status. |
| 400 | `badCSR` | CSR encoding invalid or CA rejected the request. Check CSR is base64url DER and that the CA (e.g. DigiCert) accepts it. |
| 404 | `notFound` | Certificate or resource not found. |

---

## 8. References

- RFC 8555 (ACME)
- Platform README: configuration, security
- ADR 0001: architecture and network

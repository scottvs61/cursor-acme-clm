# Security and Role-Based Access (RBAC)

This document describes the **current** security posture and how **API keys and role-based access** are implemented when enabled.

---

## Current state (before enabling auth)

| Area | What exists today | What is not in place |
|------|-------------------|----------------------|
| **CLM API** | CORS (browser origins only). Secrets (CA, ServiceNow) from config/env. | No authentication. No API keys. No roles. Any client that can reach the API has full access. |
| **ACME** | Nonce replay protection. JWS parsed and **signature verified** with account public key (JWK). | No TLS in app (use reverse proxy for HTTPS). No rate limiting. |
| **SCEP** | Issuance via configured CA. CLM ingest. | No client authentication. No challenge password. No TLS in app. |
| **UI** | Served by CLM or Vite. | No login. No distinction between admin and ordinary user. |

So today there are **no security guardrails** that restrict who can call the API, use ACME, or use SCEP. Ordinary users and administrators see and can do the same things.

---

## What can be implemented

1. **Role-based access to the CLM**  
   - **Administrators:** Full access (list, get, register, enroll, renew, revoke, bulk enroll, ingest, help).  
   - **Ordinary users:** Limited access (e.g. list certificates, get one certificate, view help). No enroll, revoke, bulk, or ingest.

2. **Keys required for CLM API and SCEP**  
   - **CLM API:** Each request includes an API key (e.g. `X-API-Key`). Keys are configured with a role (admin or user). Invalid or missing key → 401.  
   - **ACME:** Uses **built-in cryptographic authentication** (RFC 8555): account key pair, JWS signing, nonce. Every POST is verified with the account’s public key; no static API key.  
   - **SCEP:** When configured, a shared API key can be required (e.g. in header or body) for PKIOperation.

3. **UI and “special user” access**  
   - The UI can call the CLM API only when the user supplies a valid API key (e.g. login screen or BFF that injects the key).  
   - Different keys (admin vs user) give different capabilities in the UI if the backend enforces roles and the UI hides/ disables actions the role does not allow.

---

## How it is implemented (when enabled)

**Implementation:** API key auth and role checks are implemented in the CLM API; optional API key check for SCEP. ACME uses JWS signature verification (account key), not static keys. See `config/config.example.yaml` (auth section).

### Configuration

In `config/config.yaml` (or env) you define:

- **CLM API keys and roles**  
  - List of `{ key: "<secret>", role: "admin" | "user" }`.  
  - Keys can be injected via env (e.g. `${CLM_API_KEY_ADMIN}`).  
  - If at least one key is configured, the CLM API **requires** a valid `X-API-Key` and enforces roles.

- **ACME**  
  - Does **not** use static API keys. Authentication is via **account key + JWS**: every request is signed with the client’s private key and verified with the account’s public key (JWK).

- **SCEP required key (optional)**  
  - If set, PKIOperation requires the API key (e.g. in `X-API-Key` header or in JSON body when using the JSON enrollment path).

### CLM API behavior

- **Health and static UI:** `GET /health` and `GET /` (and static assets) remain unauthenticated so load balancers and users can reach the app.
- **All `/api/*` routes:**  
  - If `api_keys` is configured: require `X-API-Key`; reject with 401 if missing or invalid.  
  - **Admin key:** Can call any API (list, get, create, enroll, renew, revoke, bulk enroll, events/issued, help).  
  - **User key:** Can call only: list certificates, get one certificate, get help. Other endpoints (enroll, renew, revoke, bulk, events/issued, create certificate) return 403.

### ACME

- **No static key.** Requests to new-account, new-order, finalize, order, and cert are authenticated by **JWS signature verification**: the server verifies the signature using the account’s public key (from JWK in new-account, or stored when the account was created). Invalid or missing signature → 401.

### SCEP

- When `scep_required_api_key` is set, PKIOperation (and any JSON enrollment path) must include the same key (header or body). Otherwise the server returns 401.

### UI

- When the CLM API requires API keys, the UI must send a valid key with each request (e.g. from a login step or a BFF).  
- To give “special user” access (ordinary users with limited capabilities), use a **user**-role API key for those users and an **admin** key only for administrators. The backend enforces the difference; the UI can hide or disable actions that the current key’s role does not allow.

---

## Summary

- **Today:** There are **no** security guardrails: no auth, no RBAC, no required keys for ACME, API, or SCEP.  
- **When enabled:**  
  - **CLM** can enforce API keys and roles (admin vs user) so ordinary users do not see or have the same capabilities as administrators.  
  - **ACME** uses account key + JWS (no static key). **SCEP** can require a shared API key when configured.  
- All of this is **possible** and can be implemented with API keys and role checks as described above; the exact configuration and code are in the repo (config schema, CLM dependency, and optional ACME/SCEP checks).

"""CA-agnostic certificate issuance. Dispatches to configured CA (DigiCert One TLM, CertCentral, etc.)."""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from lib.config import get_ca_config
from lib.cert_parse import parse_csr_or_cert_pem

# Optional: avoid hard dependency on cryptography in this file if only used by adapters
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
except ImportError:
    x509 = None  # type: ignore
    NameOID = None  # type: ignore


class IssuanceError(RuntimeError):
    """Raised when the CA rejects the request or returns an error."""


def _get_first_attr(subject: "x509.Name", oid: "NameOID") -> Optional[str]:
    try:
        attrs = subject.get_attributes_for_oid(oid)
        if attrs:
            return str(attrs[0].value).strip() or None
    except Exception:
        pass
    return None


def _get_all_attr(subject: "x509.Name", oid: "NameOID") -> list[str]:
    try:
        attrs = subject.get_attributes_for_oid(oid)
        return [str(a.value).strip() for a in attrs if a.value and str(a.value).strip()]
    except Exception:
        pass
    return []


def _parse_csr_subject_dn(csr_pem: str) -> dict[str, Any]:
    """Extract full Subject DN from CSR for DigiCert API (subject.* attributes)."""
    if not x509:
        raise IssuanceError("cryptography is required to parse CSR")
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    sub = csr.subject
    return {
        "country": _get_first_attr(sub, NameOID.COUNTRY_NAME),
        "state": _get_first_attr(sub, NameOID.STATE_OR_PROVINCE_NAME),
        "locality": _get_first_attr(sub, NameOID.LOCALITY_NAME),
        "organization_name": _get_first_attr(sub, NameOID.ORGANIZATION_NAME),
        "organization_units": _get_all_attr(sub, NameOID.ORGANIZATIONAL_UNIT_NAME),
        "common_name": _get_first_attr(sub, NameOID.COMMON_NAME),
    }


def _parse_csr_cn_sans(csr_pem: str) -> tuple[Optional[str], list[str]]:
    if not x509:
        raise IssuanceError("cryptography is required to parse CSR")
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    cn = _get_first_attr(csr.subject, NameOID.COMMON_NAME)
    sans: list[str] = []
    try:
        ext = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        sans = list(ext.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        pass
    return cn, sans


def _issue_digicert_one_tlm(csr_pem: str, product_id: Optional[str], profile_id: str, **kwargs: Any) -> str:
    """DigiCert One TLM /mpki/api/v1/certificate."""
    cfg = get_ca_config(kwargs.get("ca_name"))
    base_url = (cfg.get("base_url") or "").rstrip("/")
    api_key = cfg.get("api_key")
    seat_id = cfg.get("seat_id") or cfg.get("account_id")
    if not base_url or not api_key:
        raise IssuanceError("DigiCert One TLM: base_url and api_key required in config")
    if not profile_id:
        profile_id = cfg.get("profile_id") or ""
    if not profile_id:
        raise IssuanceError("DigiCert One TLM: profile_id required")
    if not seat_id:
        raise IssuanceError("DigiCert One TLM: seat_id or account_id required")

    cn, dns_names = _parse_csr_cn_sans(csr_pem)
    if not cn:
        raise IssuanceError("CSR has no subject CN; required by DigiCert One TLM profile")

    # DigiCert One TLM often requires SAN DNS names in the request; plain openssl -subj CN=... has no SAN.
    if not dns_names and cn:
        dns_names = [cn]

    # Use nested subject object; only common_name is sent. This profile rejects country, state,
    # locality, organization_name, organization_units in the request. For full Subject DN (C, ST, L,
    # O, OU) on the issued cert, configure the certificate profile in DigiCert One TLM so those
    # attributes use source "From CSR". Our CSR already contains the full subject.
    attributes: dict[str, Any] = {
        "tnc_accepted": True,
        "subject": {"common_name": cn},
    }
    if dns_names:
        attributes.setdefault("extensions", {})["san"] = {"dns_names": dns_names}

    payload: dict[str, Any] = {
        "profile": {"id": str(profile_id)},
        "seat": {"seat_id": str(seat_id), "email": str(seat_id)},
        "csr": csr_pem,
        "validity": kwargs.get("validity") or {"unit": "days", "duration": 365},
        "delivery_format": kwargs.get("delivery_format", "x509"),
        "include_ca_chain": kwargs.get("include_ca_chain", True),
        "attributes": attributes,
    }

    url = f"{base_url}/mpki/api/v1/certificate"
    headers = {
        "x-api-key": str(api_key),
        "content-type": "application/json",
        "accept": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=headers, json=payload)
    if r.status_code not in (200, 201, 202):
        raise IssuanceError(f"DigiCert One TLM HTTP {r.status_code}: {r.text}")
    try:
        data = r.json()
    except Exception as e:
        raise IssuanceError(f"DigiCert One TLM non-JSON response: {r.text}") from e
    cert_pem = data.get("certificate")
    if not cert_pem or "BEGIN CERTIFICATE" not in str(cert_pem):
        raise IssuanceError(f"DigiCert One TLM response missing certificate PEM. Keys: {list(data.keys())}")
    return str(cert_pem)


def _issue_digicert_certcentral(csr_pem: str, product_id: Optional[str], profile_id: str, **kwargs: Any) -> str:
    """DigiCert CertCentral REST (enrollment). Config: product_name_id, organization_id."""
    cfg = get_ca_config(kwargs.get("ca_name"))
    base_url = (cfg.get("base_url") or "https://api.digicert.com").rstrip("/")
    api_key = cfg.get("api_key")
    product_name_id = profile_id or cfg.get("product_name_id")
    org_id = cfg.get("organization_id")
    if not api_key:
        raise IssuanceError("DigiCert CertCentral: api_key required in config")
    if not product_name_id:
        raise IssuanceError("DigiCert CertCentral: product_name_id required in config")

    # CertCentral enrollment API shape (simplified; adjust to actual API docs)
    payload: dict[str, Any] = {
        "certificate": {"common_name": _parse_csr_cn_sans(csr_pem)[0] or "localhost"},
        "csr": csr_pem,
        "product_name_id": int(product_name_id) if str(product_name_id).isdigit() else product_name_id,
    }
    if org_id:
        payload["organization_id"] = int(org_id) if str(org_id).isdigit() else org_id

    url = f"{base_url}/v2/order/certificate/ssl"
    headers = {
        "X-DC-DEVKEY": str(api_key),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=60.0) as client:
        r = client.post(url, headers=headers, json=payload)
    if r.status_code not in (200, 201, 202):
        raise IssuanceError(f"DigiCert CertCentral HTTP {r.status_code}: {r.text}")
    try:
        data = r.json()
    except Exception as e:
        raise IssuanceError(f"DigiCert CertCentral non-JSON response: {r.text}") from e
    cert_pem = data.get("certificate") or data.get("certificates", [{}])[0].get("pem") if isinstance(data.get("certificates"), list) else None
    if not cert_pem or "BEGIN CERTIFICATE" not in str(cert_pem):
        raise IssuanceError(f"DigiCert CertCentral response missing certificate PEM. Keys: {list(data.keys())}")
    return str(cert_pem)


def issue_certificate(
    csr_pem: str,
    product_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    ca_name: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """
    Issue a certificate from the configured CA. Uses config 'cas.default' if ca_name is None.
    product_id is passed through for CLM/ServiceNow; profile_id overrides config profile when set.
    """
    cfg = get_ca_config(ca_name)
    ca_type = (cfg.get("type") or "").strip().lower()
    if ca_type == "digicert_one_tlm":
        return _issue_digicert_one_tlm(csr_pem, product_id, profile_id or "", ca_name=ca_name, **kwargs)
    if ca_type == "digicert_certcentral":
        return _issue_digicert_certcentral(csr_pem, product_id, profile_id or "", ca_name=ca_name, **kwargs)
    raise IssuanceError(f"Unknown or unsupported CA type in config: {ca_type!r}. Check config/config.yaml 'cas' section.")


def revoke_certificate_at_ca(
    serial_number: str,
    revocation_reason: str = "cessation_of_operation",
    ca_name: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """
    Revoke a certificate at the configured CA. Returns (success, error_message).
    Only DigiCert One TLM is supported; other CAs are skipped (success=False, message set).
    """
    if not (serial_number or "").strip():
        return False, "No serial number"
    serial = serial_number.strip()
    cfg = get_ca_config(ca_name)
    ca_type = (cfg.get("type") or "").strip().lower()
    if ca_type != "digicert_one_tlm":
        return False, f"CA type {ca_type!r} does not support revocation via this API"
    base_url = (cfg.get("base_url") or "").rstrip("/")
    api_key = cfg.get("api_key")
    if not base_url or not api_key:
        return False, "DigiCert One TLM: base_url and api_key required in config"
    url = f"{base_url}/mpki/api/v1/certificate/{serial}/revoke"
    headers = {
        "x-api-key": str(api_key),
        "content-type": "application/json",
        "accept": "application/json",
    }
    body: dict[str, Any] = {"revocation_reason": revocation_reason}
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.put(url, headers=headers, json=body)
    except Exception as e:
        return False, str(e)
    if r.status_code in (200, 204):
        return True, None
    return False, f"HTTP {r.status_code}: {r.text}"

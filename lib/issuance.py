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


def _parse_csr_cn_sans(csr_pem: str) -> tuple[Optional[str], list[str]]:
    if not x509:
        raise IssuanceError("cryptography is required to parse CSR")
    csr = x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    cn = None
    try:
        attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if attrs:
            cn = attrs[0].value
    except Exception:
        pass
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

    attributes: dict[str, Any] = {
        "tnc_accepted": True,
        "subject.common_name": cn,
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

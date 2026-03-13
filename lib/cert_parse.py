"""Parse certificate or CSR PEM; return consistent dict keys."""

import hashlib
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509 import load_pem_x509_certificate, load_pem_x509_csr


def _cn_from_subject(subject: x509.Name) -> str | None:
    try:
        cn = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        return cn[0].value if cn else None
    except Exception:
        return None


def _sans_dns_from_cert(cert: x509.Certificate) -> list[str]:
    try:
        sans = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        return list(sans.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        return []


def _sans_dns_from_csr(csr: x509.CertificateSigningRequest) -> list[str]:
    try:
        sans = csr.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        return list(sans.value.get_values_for_type(x509.DNSName))
    except x509.ExtensionNotFound:
        return []


def parse_csr_or_cert_pem(pem: str) -> dict[str, Any]:
    """
    Parse PEM as either CERTIFICATE or CSR.
    Returns dict with: kind, serial_number, not_before, not_after, common_name, sans_dns, sha256_fingerprint.
    Cert-only fields are None for CSR.
    """
    pem_bytes = pem.strip().encode("utf-8")
    try:
        cert = load_pem_x509_certificate(pem_bytes)
    except Exception:
        cert = None
    if cert is not None:
        fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
        return {
            "kind": "certificate",
            "serial_number": format(cert.serial_number, "x").upper(),
            "not_before": getattr(cert, "not_valid_before_utc", cert.not_valid_before),
            "not_after": getattr(cert, "not_valid_after_utc", cert.not_valid_after),
            "common_name": _cn_from_subject(cert.subject),
            "sans_dns": _sans_dns_from_cert(cert),
            "sha256_fingerprint": fingerprint,
        }
    try:
        csr = load_pem_x509_csr(pem_bytes)
    except Exception as e:
        raise ValueError(f"Invalid PEM: not a certificate or CSR: {e}") from e
    return {
        "kind": "csr",
        "serial_number": None,
        "not_before": None,
        "not_after": None,
        "common_name": _cn_from_subject(csr.subject),
        "sans_dns": _sans_dns_from_csr(csr),
        "sha256_fingerprint": None,
    }

"""Generate RSA key + CSR and build PKCS#12 bundles. Private keys are never persisted."""

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import PrivateFormat, pkcs12
from cryptography.x509 import load_pem_x509_certificate
from cryptography.x509.oid import NameOID

# Map config keys (C, ST, L, O, OU) to X.509 NameOID for Subject DN
_SUBJECT_OID_MAP = {
    "C": NameOID.COUNTRY_NAME,
    "ST": NameOID.STATE_OR_PROVINCE_NAME,
    "L": NameOID.LOCALITY_NAME,
    "O": NameOID.ORGANIZATION_NAME,
    "OU": NameOID.ORGANIZATIONAL_UNIT_NAME,
}


def _build_subject_attributes(
    subject_defaults: dict[str, str],
    organizational_units: list[str] | None,
    common_name: str,
) -> list[x509.NameAttribute]:
    """Build subject name attributes: defaults (C, ST, L, O) + OU(s) + CN. Skips empty values."""
    attrs: list[x509.NameAttribute] = []
    for key in ("C", "ST", "L", "O"):
        oid = _SUBJECT_OID_MAP.get(key)
        if not oid:
            continue
        val = (subject_defaults or {}).get(key)
        if val and isinstance(val, str) and val.strip():
            attrs.append(x509.NameAttribute(oid, val.strip()))
    for ou in organizational_units or []:
        if ou and str(ou).strip():
            attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, str(ou).strip()))
    cn = (common_name or "").strip()
    if cn:
        attrs.append(x509.NameAttribute(NameOID.COMMON_NAME, cn))
    return attrs


def generate_key_and_csr(
    common_name: str,
    sans_dns: list[str] | None = None,
    key_size: int = 2048,
    subject_defaults: dict[str, str] | None = None,
    organizational_units: list[str] | None = None,
) -> tuple[rsa.RSAPrivateKey, str]:
    """Generate an RSA private key and a PEM-encoded CSR with full Subject DN.
    subject_defaults: pre-defined C, ST, L, O from config. CN and OU(s) from enrollment.
    Returns (private_key, csr_pem)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    attrs = _build_subject_attributes(subject_defaults or {}, organizational_units, common_name)
    if not attrs:
        attrs = [x509.NameAttribute(NameOID.COMMON_NAME, common_name.strip() or "")]
    builder = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name(attrs))
    )
    if sans_dns:
        names = [x509.DNSName(n.strip()) for n in sans_dns if n.strip()]
        if names:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(names),
                critical=False,
            )
    csr = builder.sign(key, hashes.SHA256())
    csr_pem = csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return key, csr_pem


def build_pkcs12(
    cert_pem: str,
    private_key: rsa.RSAPrivateKey,
    password: str,
    friendly_name: str = "Certificate",
    ca_certs_pem: list[str] | None = None,
) -> bytes:
    """Build a PKCS#12 (PFX/P12) bundle from certificate PEM and private key. Password protects the bundle."""
    cert = load_pem_x509_certificate(cert_pem.strip().encode("utf-8"))
    cas = []
    if ca_certs_pem:
        for pem in ca_certs_pem:
            if pem.strip():
                cas.append(load_pem_x509_certificate(pem.strip().encode("utf-8")))
    pw = password.encode("utf-8")
    encryption = (
        PrivateFormat.PKCS12.encryption_builder()
        .kdf_rounds(50000)
        .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC)
        .hmac_hash(hashes.SHA1())
        .build(pw)
    )
    return pkcs12.serialize_key_and_certificates(
        name=friendly_name.encode("utf-8"),
        key=private_key,
        cert=cert,
        cas=cas,
        encryption_algorithm=encryption,
    )

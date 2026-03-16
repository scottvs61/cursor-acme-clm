"""Pydantic schemas for CLM API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CertificateCreateRequest(BaseModel):
    pem: str = Field(..., description="Certificate PEM (CERTIFICATE, not CSR)")
    source: str = Field(..., pattern="^(api|acme|scep)$")
    product_id: str = Field(..., description="Required for all enrollments (mandatory policy)")


class EventIssuedRequest(BaseModel):
    certificate_pem: str = Field(..., description="Certificate PEM")
    source: str = Field(..., pattern="^(api|acme|scep)$")
    product_id: str = Field(..., description="Required for all enrollments (mandatory policy)")
    raw: dict[str, Any] = Field(default_factory=dict)


class CertificateResponse(BaseModel):
    id: str
    created_at: datetime
    source: str
    product_id: str | None
    common_name: str | None
    sans_dns: list[str]
    serial_number: str
    not_before: datetime | None
    not_after: datetime | None
    sha256_fingerprint: str
    pem: str
    revoked_at: datetime | None = None
    model_config = {"from_attributes": True}


class EnrollRequest(BaseModel):
    """Either provide csr_pem (own CSR) or set generate=true with common_name and p12_password."""

    csr_pem: str | None = Field(None, description="PEM-encoded CSR (use when not generating)")
    product_id: str = Field(..., description="Required for all enrollments (mandatory policy)")
    # When generate is True: CLM generates key+CSR, issues cert, returns PKCS#12
    generate: bool = Field(False, description="If true, generate key and CSR for the user")
    common_name: str | None = Field(None, description="Common name for generated CSR (required when generate=true)")
    organizational_units: list[str] | None = Field(None, description="OU(s) for generated CSR Subject DN")
    sans_dns: list[str] | None = Field(None, description="SAN DNS names for generated CSR")
    p12_password: str | None = Field(None, description="Password for PKCS#12 bundle (required when generate=true)")
    p12_format: Literal["pfx", "p12"] = Field("p12", description="File extension: pfx (Windows) or p12 (Linux)")

    @model_validator(mode="after")
    def require_csr_or_generate(self) -> "EnrollRequest":
        if not (self.product_id or "").strip():
            raise ValueError("product_id is required for all enrollments")
        if self.generate:
            if not self.common_name or not self.common_name.strip():
                raise ValueError("common_name is required when generate=true")
            if not self.p12_password:
                raise ValueError("p12_password is required when generate=true")
        else:
            if not self.csr_pem or not self.csr_pem.strip():
                raise ValueError("csr_pem is required when generate=false")
            if "BEGIN CERTIFICATE REQUEST" not in self.csr_pem:
                raise ValueError("csr_pem must be a PEM-encoded CSR")
        return self


class RenewRequest(BaseModel):
    csr_pem: str = Field(..., description="PEM-encoded CSR for the renewed certificate")


class RevokeRequest(BaseModel):
    revocation_reason: str = Field(
        "cessation_of_operation",
        description="Reason for revocation (e.g. cessation_of_operation, key_compromise). Sent to DigiCert One TLM when configured.",
    )


class EventResponse(BaseModel):
    id: str
    created_at: datetime
    event_type: str
    certificate_id: str | None
    payload_json: str
    model_config = {"from_attributes": True}


class EventIssuedResponse(BaseModel):
    certificate: CertificateResponse
    event: EventResponse


class BulkEnrollItem(BaseModel):
    csr_pem: str = Field(..., description="PEM-encoded CSR")
    product_id: str | None = None


class BulkEnrollRequest(BaseModel):
    requests: list[BulkEnrollItem] = Field(..., min_length=1, max_length=100)
    default_product_id: str = Field(..., description="Required; used when item.product_id is not set (mandatory policy)")

    @model_validator(mode="after")
    def default_product_id_non_empty(self) -> "BulkEnrollRequest":
        if not (self.default_product_id or "").strip():
            raise ValueError("default_product_id is required and must be non-empty for all enrollments")
        return self


class BulkEnrollItemResult(BaseModel):
    success: bool
    certificate_id: str | None = None
    certificate_pem: str | None = None
    error: str | None = None


class BulkEnrollResponse(BaseModel):
    results: list[BulkEnrollItemResult]
    total: int
    succeeded: int
    failed: int


# --- Auth ---
class LoginRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., description="Password")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str  # admin | user
    user_id: str
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, description="New password (min 8 characters)")


class UserMeResponse(BaseModel):
    user_id: str
    email: str
    role: str
    must_change_password: bool = False


# --- Admin: keys and users ---
class GenerateKeyRequest(BaseModel):
    scope: Literal["scep", "api"] = Field(..., description="Key scope (ACME uses account key + JWS, not static keys)")
    role: Literal["admin", "user"] | None = Field(None, description="For scope=api only: admin or user")
    label: str | None = Field(None, description="Optional label for the key")


class GenerateKeyResponse(BaseModel):
    id: str
    scope: str
    role: str | None
    label: str | None
    key: str = Field(..., description="Plaintext key - copy now; it will not be shown again")


class ServiceKeyInfo(BaseModel):
    id: str
    scope: str
    role: str | None
    label: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class CreateUserRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="Temporary password (min 8 characters)")
    role: Literal["admin", "user"] = Field("user")
    must_change_password: bool = Field(True, description="Require password change on first login")


class UpdateUserRequest(BaseModel):
    role: Literal["admin", "user"] | None = None
    password: str | None = Field(None, min_length=8, description="New password (resets user password)")
    must_change_password: bool | None = None


class UserInfo(BaseModel):
    id: str
    email: str
    role: str
    must_change_password: bool
    created_at: datetime
    model_config = {"from_attributes": True}

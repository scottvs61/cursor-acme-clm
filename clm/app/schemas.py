"""Pydantic schemas for CLM API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CertificateCreateRequest(BaseModel):
    pem: str = Field(..., description="Certificate PEM (CERTIFICATE, not CSR)")
    source: str = Field(..., pattern="^(api|acme|scep)$")
    product_id: str | None = None


class EventIssuedRequest(BaseModel):
    certificate_pem: str = Field(..., description="Certificate PEM")
    source: str = Field(..., pattern="^(api|acme|scep)$")
    product_id: str | None = None
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
    model_config = {"from_attributes": True}


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
    default_product_id: str | None = Field(None, description="Used when item.product_id is not set")


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

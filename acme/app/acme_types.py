"""ACME v2 (RFC 8555) request/response types."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class IdentifierType(str, Enum):
    DNS = "dns"


class Identifier(BaseModel):
    type: IdentifierType = IdentifierType.DNS
    value: str


class AccountStatus(str, Enum):
    valid = "valid"
    deactivated = "deactivated"


class OrderStatus(str, Enum):
    pending = "pending"
    ready = "ready"
    processing = "processing"
    valid = "valid"
    invalid = "invalid"


class AuthStatus(str, Enum):
    pending = "pending"
    valid = "valid"
    invalid = "invalid"
    deactivated = "deactivated"
    expired = "expired"


class ChallengeType(str, Enum):
    HTTP_01 = "http-01"
    DNS_01 = "dns-01"


class NewAccountRequest(BaseModel):
    contact: Optional[list[str]] = None
    termsOfServiceAgreed: Optional[bool] = None
    onlyReturnExisting: Optional[bool] = None
    product_id: str = Field(..., description="Required for all enrollments (mandatory policy)")


class AccountResponse(BaseModel):
    status: AccountStatus
    contact: Optional[list[str]] = None
    orders: Optional[str] = None
    termsOfServiceAgreed: Optional[bool] = None


class NewOrderRequest(BaseModel):
    identifiers: list[Identifier]
    notBefore: Optional[str] = None
    notAfter: Optional[str] = None


class FinalizeRequest(BaseModel):
    csr: str  # base64url-encoded DER CSR

"""In-memory store for ACME state (no database)."""

import uuid
from dataclasses import dataclass, field
from typing import Optional

from acme.app.acme_types import (
    AccountStatus,
    AuthStatus,
    ChallengeType,
    Identifier,
    OrderStatus,
)


@dataclass
class Account:
    key_id: str
    jwk_thumbprint: str
    contact: Optional[list[str]] = None
    product_id: Optional[str] = None
    status: AccountStatus = AccountStatus.valid


@dataclass
class Authorization:
    auth_id: str
    order_id: str
    identifier: Identifier
    status: AuthStatus = AuthStatus.valid
    challenges: list[dict] = field(default_factory=list)


@dataclass
class Order:
    order_id: str
    account_id: str
    identifiers: list[Identifier]
    product_id: Optional[str] = None
    status: OrderStatus = OrderStatus.pending
    auth_ids: list[str] = field(default_factory=list)
    certificate_id: Optional[str] = None


class Store:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._accounts_by_thumbprint: dict[str, str] = {}
        self._orders: dict[str, Order] = {}
        self._authorizations: dict[str, Authorization] = {}
        self._nonces: set[str] = set()
        self._certificates: dict[str, str] = {}

    def add_nonce(self, nonce: str) -> None:
        self._nonces.add(nonce)

    def consume_nonce(self, nonce: str) -> bool:
        if nonce in self._nonces:
            self._nonces.discard(nonce)
            return True
        return False

    def create_account(
        self,
        key_id: str,
        jwk_thumbprint: str,
        contact: Optional[list[str]] = None,
        product_id: Optional[str] = None,
    ) -> Account:
        acc = Account(key_id=key_id, jwk_thumbprint=jwk_thumbprint, contact=contact, product_id=product_id)
        self._accounts[key_id] = acc
        self._accounts_by_thumbprint[jwk_thumbprint] = key_id
        return acc

    def get_account_by_kid(self, key_id: str) -> Optional[Account]:
        return self._accounts.get(key_id)

    def get_account_by_thumbprint(self, thumbprint: str) -> Optional[Account]:
        kid = self._accounts_by_thumbprint.get(thumbprint)
        return self._accounts.get(kid) if kid else None

    def create_order(self, account_id: str, identifiers: list[Identifier]) -> Order:
        acct = self.get_account_by_kid(account_id)
        product_id = acct.product_id if acct else None
        order_id = str(uuid.uuid4())
        auth_ids = [str(uuid.uuid4()) for _ in identifiers]
        order = Order(
            order_id=order_id,
            account_id=account_id,
            identifiers=identifiers,
            product_id=product_id,
            status=OrderStatus.pending,
            auth_ids=auth_ids,
        )
        self._orders[order_id] = order
        for i, ident in enumerate(identifiers):
            self._authorizations[auth_ids[i]] = Authorization(
                auth_id=auth_ids[i],
                order_id=order_id,
                identifier=ident,
                status=AuthStatus.valid,
                challenges=[
                    {
                        "type": ChallengeType.HTTP_01.value,
                        "url": "",
                        "status": AuthStatus.valid.value,
                        "token": str(uuid.uuid4()),
                    }
                ],
            )
        return order

    def get_order(self, order_id: str) -> Optional[Order]:
        return self._orders.get(order_id)

    def get_authorization(self, auth_id: str) -> Optional[Authorization]:
        return self._authorizations.get(auth_id)

    def set_order_ready(self, order_id: str) -> None:
        o = self._orders.get(order_id)
        if o:
            o.status = OrderStatus.ready

    def set_order_valid(self, order_id: str, cert_id: str) -> None:
        o = self._orders.get(order_id)
        if o:
            o.status = OrderStatus.valid
            o.certificate_id = cert_id

    def store_certificate(self, cert_id: str, pem: str) -> None:
        self._certificates[cert_id] = pem

    def get_certificate(self, cert_id: str) -> Optional[str]:
        return self._certificates.get(cert_id)


_store: Optional[Store] = None


def get_store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ErrorDisposition(StrEnum):
    """How callers should respond to a provider failure."""

    RETRYABLE = "retryable"
    REPAIRABLE = "repairable"
    TERMINAL = "terminal"


class FinancialConnectionError(RuntimeError):
    """A credential-safe error normalized across connection providers."""

    def __init__(
        self,
        *,
        provider: str,
        code: str,
        message: str,
        disposition: ErrorDisposition,
        error_type: str = "",
        request_id: str = "",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.message = message
        self.disposition = disposition
        self.error_type = error_type
        self.request_id = request_id
        self.status_code = status_code


@dataclass(frozen=True)
class ProviderReadiness:
    provider: str
    enabled: bool
    configured: bool
    environment: str
    client_id_configured: bool
    secret_configured: bool
    webhook_url_configured: bool
    redirect_uri_configured: bool
    country_codes_configured: bool
    missing_settings: tuple[str, ...] = ()


@dataclass(frozen=True)
class LinkSession:
    link_token: str
    expires_at: str
    request_id: str = ""


class TokenExchange:
    """Token exchange result whose access token is deliberately non-serializable."""

    __slots__ = ("_access_token", "provider_item_id", "request_id")

    def __init__(self, *, access_token: str, provider_item_id: str, request_id: str = "") -> None:
        self._access_token = access_token
        self.provider_item_id = provider_item_id
        self.request_id = request_id

    @property
    def access_token(self) -> str:
        return self._access_token

    def __repr__(self) -> str:
        return (
            "TokenExchange(access_token=<redacted>, "
            f"provider_item_id={self.provider_item_id!r}, request_id={self.request_id!r})"
        )


@dataclass(frozen=True)
class ProviderItem:
    provider_item_id: str
    institution_id: str | None
    webhook_url: str | None
    consent_expiration_at: str | None
    available_products: tuple[str, ...]
    billed_products: tuple[str, ...]
    products: tuple[str, ...]
    error_code: str | None = None
    request_id: str = ""


@dataclass(frozen=True)
class ProviderAccount:
    provider_account_id: str
    name: str
    official_name: str | None
    account_type: str
    account_subtype: str | None
    mask: str | None
    current_balance: float | None
    available_balance: float | None
    limit: float | None
    iso_currency_code: str | None
    unofficial_currency_code: str | None


@dataclass(frozen=True)
class AccountsSnapshot:
    accounts: tuple[ProviderAccount, ...]
    request_id: str = ""


@dataclass(frozen=True)
class ProviderSecurity:
    provider_security_id: str
    name: str | None
    ticker_symbol: str | None
    security_type: str | None
    security_subtype: str | None
    cusip: str | None
    isin: str | None
    sedol: str | None
    close_price: float | None
    close_price_as_of: str | None
    iso_currency_code: str | None
    unofficial_currency_code: str | None
    is_cash_equivalent: bool


@dataclass(frozen=True)
class ProviderHolding:
    provider_account_id: str
    provider_security_id: str
    quantity: float
    institution_value: float
    institution_price: float
    institution_price_as_of: str | None
    cost_basis: float | None
    iso_currency_code: str | None
    unofficial_currency_code: str | None


@dataclass(frozen=True)
class InvestmentHoldingsSnapshot:
    accounts: tuple[ProviderAccount, ...]
    holdings: tuple[ProviderHolding, ...]
    securities: tuple[ProviderSecurity, ...]
    request_id: str = ""


@dataclass(frozen=True)
class ItemRemoval:
    removed: bool
    request_id: str = ""


@dataclass(frozen=True)
class WebhookEvent:
    event_type: str
    event_code: str
    provider_item_id: str | None
    environment: str | None
    provider_error_code: str | None = None


class FinancialConnectionProvider(Protocol):
    provider: str

    def configuration_readiness(self) -> ProviderReadiness: ...

    async def create_link_token(
        self,
        *,
        user_id: str,
        access_token: str | None = None,
    ) -> LinkSession: ...

    async def exchange_public_token(self, public_token: str) -> TokenExchange: ...

    async def get_item(self, access_token: str) -> ProviderItem: ...

    async def get_accounts(self, access_token: str) -> AccountsSnapshot: ...

    async def get_investment_holdings(
        self,
        access_token: str,
    ) -> InvestmentHoldingsSnapshot: ...

    async def remove_item(self, access_token: str) -> ItemRemoval: ...

    async def validate_webhook(
        self,
        *,
        raw_body: bytes,
        verification_token: str,
    ) -> WebhookEvent: ...

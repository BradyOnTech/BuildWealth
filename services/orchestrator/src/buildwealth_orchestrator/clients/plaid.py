from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import random
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import httpx
import jwt

from buildwealth_orchestrator.clients.financial_connections import (
    AccountsSnapshot,
    ErrorDisposition,
    FinancialConnectionError,
    InvestmentHoldingsSnapshot,
    ItemRemoval,
    LinkSession,
    ProviderAccount,
    ProviderHolding,
    ProviderItem,
    ProviderReadiness,
    ProviderSecurity,
    TokenExchange,
    WebhookEvent,
)


_BASE_URLS = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}
_REPAIRABLE_CODES = {
    "ITEM_LOGIN_REQUIRED",
    "ITEM_LOCKED",
    "INVALID_CREDENTIALS",
    "INVALID_MFA",
    "MFA_NOT_SUPPORTED",
    "OAUTH_STATE_ID_ALREADY_PROCESSED",
    "USER_SETUP_REQUIRED",
}
_RETRYABLE_CODES = {
    "INTERNAL_SERVER_ERROR",
    "INSTITUTION_DOWN",
    "INSTITUTION_NOT_AVAILABLE",
    "INSTITUTION_NOT_RESPONDING",
    "PLANNED_MAINTENANCE",
    "PRODUCT_NOT_READY",
    "RATE_LIMIT_EXCEEDED",
}
_WEBHOOK_KEY_CACHE_TTL_SECONDS = 300.0
_PLAID_API_VERSION = "2020-09-14"


class PlaidConnectionProvider:
    """Small, read-only Plaid adapter used by BuildWealth connection services."""

    provider = "plaid"

    def __init__(
        self,
        *,
        enabled: bool = False,
        environment: str = "sandbox",
        client_id: str = "",
        secret: str = "",
        webhook_url: str = "",
        redirect_uri: str = "",
        country_codes: str | tuple[str, ...] = "US",
        timeout_seconds: float = 15.0,
        client_name: str = "BuildWealth",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        normalized_environment = str(environment or "sandbox").strip().lower()
        if normalized_environment not in _BASE_URLS:
            raise ValueError("Plaid environment must be 'sandbox' or 'production'")
        if timeout_seconds <= 0:
            raise ValueError("Plaid timeout must be greater than zero")
        self.enabled = bool(enabled)
        self.environment = normalized_environment
        self.client_id = str(client_id or "").strip()
        self._secret = str(secret or "").strip()
        self.webhook_url = str(webhook_url or "").strip()
        self.redirect_uri = str(redirect_uri or "").strip()
        self.country_codes = _normalize_country_codes(country_codes)
        self.timeout_seconds = float(timeout_seconds)
        self.client_name = str(client_name or "BuildWealth").strip() or "BuildWealth"
        self._http_client = http_client
        self._verification_keys: dict[
            str,
            tuple[Mapping[str, Any], float],
        ] = {}

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> PlaidConnectionProvider:
        return cls(
            enabled=bool(getattr(settings, "plaid_connections_enabled", False)),
            environment=str(getattr(settings, "plaid_environment", "sandbox")),
            client_id=str(getattr(settings, "plaid_client_id", "")),
            secret=_settings_secret_value(getattr(settings, "plaid_secret", "")),
            webhook_url=str(getattr(settings, "plaid_webhook_url", "")),
            redirect_uri=str(getattr(settings, "plaid_redirect_uri", "")),
            country_codes=str(getattr(settings, "plaid_country_codes", "US")),
            timeout_seconds=float(getattr(settings, "plaid_timeout_seconds", 15.0)),
            client_name=str(getattr(settings, "app_name", "BuildWealth")),
            http_client=http_client,
        )

    def configuration_readiness(self) -> ProviderReadiness:
        production = self.environment == "production"
        webhook_valid = bool(self.webhook_url) and (
            not production or urlparse(self.webhook_url).scheme == "https"
        )
        redirect_valid = bool(self.redirect_uri) and (
            not production or urlparse(self.redirect_uri).scheme == "https"
        )
        fields = {
            "PLAID_CLIENT_ID": bool(self.client_id),
            "PLAID_SECRET": bool(self._secret),
            "PLAID_WEBHOOK_URL": webhook_valid,
            "PLAID_REDIRECT_URI": redirect_valid,
            "PLAID_COUNTRY_CODES": bool(self.country_codes),
        }
        missing = tuple(name for name, configured in fields.items() if not configured)
        return ProviderReadiness(
            provider=self.provider,
            enabled=self.enabled,
            configured=not missing,
            environment=self.environment,
            client_id_configured=fields["PLAID_CLIENT_ID"],
            secret_configured=fields["PLAID_SECRET"],
            webhook_url_configured=fields["PLAID_WEBHOOK_URL"],
            redirect_uri_configured=fields["PLAID_REDIRECT_URI"],
            country_codes_configured=fields["PLAID_COUNTRY_CODES"],
            missing_settings=missing,
        )

    async def create_link_token(
        self,
        *,
        user_id: str,
        access_token: str | None = None,
    ) -> LinkSession:
        cleaned_user_id = str(user_id or "").strip()
        if not cleaned_user_id:
            raise ValueError("user_id is required")
        payload: dict[str, Any] = {
            "client_name": self.client_name,
            "country_codes": list(self.country_codes),
            "language": "en",
            "user": {"client_user_id": cleaned_user_id},
            "webhook": self.webhook_url,
            "redirect_uri": self.redirect_uri,
        }
        if access_token:
            payload["access_token"] = access_token
        else:
            payload["products"] = ["investments"]
        response = await self._post("/link/token/create", payload)
        return LinkSession(
            link_token=_required_string(response, "link_token"),
            expires_at=_required_string(response, "expiration"),
            request_id=_optional_string(response, "request_id") or "",
        )

    async def exchange_public_token(self, public_token: str) -> TokenExchange:
        token = str(public_token or "").strip()
        if not token:
            raise ValueError("public_token is required")
        response = await self._post(
            "/item/public_token/exchange",
            {"public_token": token},
            allow_retry=False,
        )
        return TokenExchange(
            access_token=_required_string(response, "access_token"),
            provider_item_id=_required_string(response, "item_id"),
            request_id=_optional_string(response, "request_id") or "",
        )

    async def get_item(self, access_token: str) -> ProviderItem:
        response = await self._post("/item/get", {"access_token": _require_token(access_token)})
        item = _required_mapping(response, "item")
        item_error = item.get("error")
        error_code = (
            _optional_string(item_error, "error_code")
            if isinstance(item_error, Mapping)
            else None
        )
        return ProviderItem(
            provider_item_id=_required_string(item, "item_id"),
            institution_id=_optional_string(item, "institution_id"),
            webhook_url=_optional_string(item, "webhook"),
            consent_expiration_at=_optional_string(item, "consent_expiration_time"),
            available_products=_string_tuple(item.get("available_products")),
            billed_products=_string_tuple(item.get("billed_products")),
            products=_string_tuple(item.get("products")),
            error_code=error_code,
            request_id=_optional_string(response, "request_id") or "",
        )

    async def get_accounts(self, access_token: str) -> AccountsSnapshot:
        response = await self._post("/accounts/get", {"access_token": _require_token(access_token)})
        return AccountsSnapshot(
            accounts=_parse_accounts(response.get("accounts")),
            request_id=_optional_string(response, "request_id") or "",
        )

    async def get_investment_holdings(
        self,
        access_token: str,
    ) -> InvestmentHoldingsSnapshot:
        response = await self._post(
            "/investments/holdings/get",
            {"access_token": _require_token(access_token)},
        )
        return InvestmentHoldingsSnapshot(
            accounts=_parse_accounts(response.get("accounts")),
            holdings=_parse_holdings(response.get("holdings")),
            securities=_parse_securities(response.get("securities")),
            request_id=_optional_string(response, "request_id") or "",
        )

    async def remove_item(self, access_token: str) -> ItemRemoval:
        response = await self._post(
            "/item/remove",
            {"access_token": _require_token(access_token)},
            allow_retry=False,
        )
        return ItemRemoval(
            # Plaid's current /item/remove success body contains request_id
            # only. A successful HTTP response is the removal confirmation.
            removed=True,
            request_id=_optional_string(response, "request_id") or "",
        )

    async def validate_webhook(
        self,
        *,
        raw_body: bytes,
        verification_token: str,
    ) -> WebhookEvent:
        self._ensure_ready()
        token = str(verification_token or "").strip()
        if not token:
            raise _webhook_error("MISSING_WEBHOOK_SIGNATURE")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise _webhook_error("INVALID_WEBHOOK_SIGNATURE") from exc
        if header.get("alg") != "ES256":
            raise _webhook_error("INVALID_WEBHOOK_ALGORITHM")
        key_id = str(header.get("kid") or "").strip()
        if not key_id:
            raise _webhook_error("MISSING_WEBHOOK_KEY_ID")

        key_payload = await self._get_verification_key(key_id)
        try:
            public_key = jwt.PyJWK.from_dict(dict(key_payload)).key
            claims = jwt.decode(
                token,
                key=public_key,
                algorithms=["ES256"],
                options={"require": ["iat", "request_body_sha256"]},
            )
        except (jwt.PyJWTError, ValueError) as exc:
            raise _webhook_error("INVALID_WEBHOOK_SIGNATURE") from exc
        issued_at = claims.get("iat")
        if not isinstance(issued_at, (int, float)):
            raise _webhook_error("INVALID_WEBHOOK_ISSUED_AT")
        age_seconds = time.time() - float(issued_at)
        if age_seconds < -30 or age_seconds > 300:
            raise _webhook_error("STALE_WEBHOOK_SIGNATURE")
        claimed_hash = str(claims.get("request_body_sha256") or "")
        actual_hash = hashlib.sha256(raw_body).hexdigest()
        if not hmac.compare_digest(actual_hash, claimed_hash):
            raise _webhook_error("WEBHOOK_BODY_MISMATCH")
        try:
            payload = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _webhook_error("INVALID_WEBHOOK_BODY") from exc
        if not isinstance(payload, Mapping):
            raise _webhook_error("INVALID_WEBHOOK_BODY")
        provider_error = payload.get("error")
        provider_error_code = (
            _optional_string(provider_error, "error_code")
            if isinstance(provider_error, Mapping)
            else None
        )
        return WebhookEvent(
            event_type=_required_string(payload, "webhook_type"),
            event_code=_required_string(payload, "webhook_code"),
            provider_item_id=_optional_string(payload, "item_id"),
            environment=_optional_string(payload, "environment"),
            provider_error_code=provider_error_code,
        )

    async def _get_verification_key(self, key_id: str) -> Mapping[str, Any]:
        cached = self._verification_keys.get(key_id)
        if cached is not None:
            cached_key, cached_at = cached
            if (
                time.monotonic() - cached_at < _WEBHOOK_KEY_CACHE_TTL_SECONDS
                and not _verification_key_expired(cached_key)
            ):
                return cached_key
        response = await self._post("/webhook_verification_key/get", {"key_id": key_id})
        key = _required_mapping(response, "key")
        if _optional_string(key, "kid") != key_id or key.get("alg") != "ES256":
            raise _webhook_error("INVALID_WEBHOOK_VERIFICATION_KEY")
        if _verification_key_expired(key):
            raise _webhook_error("EXPIRED_WEBHOOK_VERIFICATION_KEY")
        if key_id not in self._verification_keys and len(self._verification_keys) >= 8:
            oldest_key_id = min(
                self._verification_keys,
                key=lambda candidate: self._verification_keys[candidate][1],
            )
            self._verification_keys.pop(oldest_key_id, None)
        self._verification_keys[key_id] = (key, time.monotonic())
        return key

    async def _post(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        allow_retry: bool = True,
    ) -> Mapping[str, Any]:
        self._ensure_ready()
        attempts = 2 if allow_retry else 1
        for attempt in range(attempts):
            try:
                response = await self._send(path, payload)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if allow_retry and attempt == 0:
                    await asyncio.sleep(0.2 + random.random() * 0.2)
                    continue
                raise FinancialConnectionError(
                    provider=self.provider,
                    code="PROVIDER_UNAVAILABLE",
                    message="Plaid is temporarily unavailable",
                    disposition=ErrorDisposition.RETRYABLE,
                ) from exc
            if response.is_success:
                try:
                    body = response.json()
                except ValueError as exc:
                    raise _invalid_response_error(response.status_code) from exc
                if not isinstance(body, Mapping):
                    raise _invalid_response_error(response.status_code)
                return body
            error = _normalize_plaid_error(response)
            if allow_retry and attempt == 0 and error.disposition is ErrorDisposition.RETRYABLE:
                await asyncio.sleep(0.2 + random.random() * 0.2)
                continue
            raise error
        raise AssertionError("Plaid request retry loop exhausted")

    async def _send(self, path: str, payload: Mapping[str, Any]) -> httpx.Response:
        url = f"{_BASE_URLS[self.environment]}{path}"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Plaid-Version": _PLAID_API_VERSION,
            "PLAID-CLIENT-ID": self.client_id,
            "PLAID-SECRET": self._secret,
        }
        if self._http_client is not None:
            return await self._http_client.post(url, headers=headers, json=dict(payload))
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            return await client.post(url, headers=headers, json=dict(payload))

    def _ensure_ready(self) -> None:
        readiness = self.configuration_readiness()
        if not readiness.enabled:
            raise FinancialConnectionError(
                provider=self.provider,
                code="PROVIDER_DISABLED",
                message="Plaid financial connections are disabled",
                disposition=ErrorDisposition.TERMINAL,
            )
        if not readiness.configured:
            raise FinancialConnectionError(
                provider=self.provider,
                code="PROVIDER_NOT_CONFIGURED",
                message="Plaid financial connections are not fully configured",
                disposition=ErrorDisposition.TERMINAL,
            )


def _normalize_country_codes(value: str | tuple[str, ...]) -> tuple[str, ...]:
    parts = value.split(",") if isinstance(value, str) else value
    return tuple(dict.fromkeys(str(part).strip().upper() for part in parts if str(part).strip()))


def _settings_secret_value(value: Any) -> str:
    reveal = getattr(value, "get_secret_value", None)
    return str(reveal() if callable(reveal) else value or "")


def _require_token(value: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError("access_token is required")
    return token


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise _invalid_response_error()
    return value


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise _invalid_response_error()
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value else None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _required_float(value: Any) -> float:
    parsed = _optional_float(value)
    if parsed is None:
        raise _invalid_response_error()
    return parsed


def _parse_accounts(value: Any) -> tuple[ProviderAccount, ...]:
    if not isinstance(value, list):
        raise _invalid_response_error()
    accounts: list[ProviderAccount] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise _invalid_response_error()
        balances = raw.get("balances")
        if not isinstance(balances, Mapping):
            balances = {}
        accounts.append(
            ProviderAccount(
                provider_account_id=_required_string(raw, "account_id"),
                name=_required_string(raw, "name"),
                official_name=_optional_string(raw, "official_name"),
                account_type=_required_string(raw, "type"),
                account_subtype=_optional_string(raw, "subtype"),
                mask=_optional_string(raw, "mask"),
                current_balance=_optional_float(balances.get("current")),
                available_balance=_optional_float(balances.get("available")),
                limit=_optional_float(balances.get("limit")),
                iso_currency_code=_optional_string(balances, "iso_currency_code"),
                unofficial_currency_code=_optional_string(balances, "unofficial_currency_code"),
            )
        )
    return tuple(accounts)


def _parse_holdings(value: Any) -> tuple[ProviderHolding, ...]:
    if not isinstance(value, list):
        raise _invalid_response_error()
    holdings: list[ProviderHolding] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise _invalid_response_error()
        holdings.append(
            ProviderHolding(
                provider_account_id=_required_string(raw, "account_id"),
                provider_security_id=_required_string(raw, "security_id"),
                quantity=_required_float(raw.get("quantity")),
                institution_value=_required_float(raw.get("institution_value")),
                institution_price=_required_float(raw.get("institution_price")),
                institution_price_as_of=_optional_string(raw, "institution_price_as_of"),
                cost_basis=_optional_float(raw.get("cost_basis")),
                iso_currency_code=_optional_string(raw, "iso_currency_code"),
                unofficial_currency_code=_optional_string(raw, "unofficial_currency_code"),
            )
        )
    return tuple(holdings)


def _parse_securities(value: Any) -> tuple[ProviderSecurity, ...]:
    if not isinstance(value, list):
        raise _invalid_response_error()
    securities: list[ProviderSecurity] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise _invalid_response_error()
        securities.append(
            ProviderSecurity(
                provider_security_id=_required_string(raw, "security_id"),
                name=_optional_string(raw, "name"),
                ticker_symbol=_optional_string(raw, "ticker_symbol"),
                security_type=_optional_string(raw, "type"),
                security_subtype=_optional_string(raw, "subtype"),
                cusip=_optional_string(raw, "cusip"),
                isin=_optional_string(raw, "isin"),
                sedol=_optional_string(raw, "sedol"),
                close_price=_optional_float(raw.get("close_price")),
                close_price_as_of=_optional_string(raw, "close_price_as_of"),
                iso_currency_code=_optional_string(raw, "iso_currency_code"),
                unofficial_currency_code=_optional_string(raw, "unofficial_currency_code"),
                is_cash_equivalent=bool(raw.get("is_cash_equivalent")),
            )
        )
    return tuple(securities)


def _normalize_plaid_error(response: httpx.Response) -> FinancialConnectionError:
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, Mapping):
        payload = {}
    code = str(payload.get("error_code") or f"PLAID_HTTP_{response.status_code}")
    error_type = str(payload.get("error_type") or "HTTP_ERROR")
    return FinancialConnectionError(
        provider="plaid",
        code=code,
        message=f"Plaid request failed ({code})",
        disposition=_classify_error(code, error_type, response.status_code),
        error_type=error_type,
        request_id=str(payload.get("request_id") or ""),
        status_code=response.status_code,
    )


def _classify_error(code: str, error_type: str, status_code: int) -> ErrorDisposition:
    if code in _REPAIRABLE_CODES:
        return ErrorDisposition.REPAIRABLE
    if (
        code in _RETRYABLE_CODES
        or error_type in {"API_ERROR", "INSTITUTION_ERROR", "RATE_LIMIT_EXCEEDED"}
        or status_code == 429
        or status_code >= 500
    ):
        return ErrorDisposition.RETRYABLE
    return ErrorDisposition.TERMINAL


def _verification_key_expired(key: Mapping[str, Any]) -> bool:
    expired_at = key.get("expired_at")
    return isinstance(expired_at, (int, float)) and float(expired_at) <= time.time()


def _invalid_response_error(status_code: int | None = None) -> FinancialConnectionError:
    return FinancialConnectionError(
        provider="plaid",
        code="INVALID_PROVIDER_RESPONSE",
        message="Plaid returned an invalid response",
        disposition=ErrorDisposition.RETRYABLE,
        status_code=status_code,
    )


def _webhook_error(code: str) -> FinancialConnectionError:
    return FinancialConnectionError(
        provider="plaid",
        code=code,
        message="Plaid webhook verification failed",
        disposition=ErrorDisposition.TERMINAL,
    )

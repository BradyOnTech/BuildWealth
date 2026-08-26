from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import time

from cryptography.hazmat.primitives.asymmetric import ec
import httpx
import jwt
import pytest

from buildwealth_orchestrator.clients.financial_connections import (
    ErrorDisposition,
    FinancialConnectionError,
)
from buildwealth_orchestrator.clients.plaid import PlaidConnectionProvider
from buildwealth_orchestrator.settings import Settings


FIXTURES = Path(__file__).parent / "fixtures" / "plaid"


def _provider(
    client: httpx.AsyncClient,
    *,
    enabled: bool = True,
    secret: str = "test-secret-scrubbed",
) -> PlaidConnectionProvider:
    return PlaidConnectionProvider(
        enabled=enabled,
        environment="sandbox",
        client_id="test-client-id-scrubbed",
        secret=secret,
        webhook_url="https://example.test/api/webhooks/plaid",
        redirect_uri="https://example.test/plaid/oauth",
        country_codes="US,ca,US",
        timeout_seconds=1,
        http_client=client,
    )


def test_plaid_settings_are_disabled_and_empty_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PLAID_CONNECTIONS_ENABLED",
        "PLAID_ENVIRONMENT",
        "PLAID_CLIENT_ID",
        "PLAID_SECRET",
        "PLAID_WEBHOOK_URL",
        "PLAID_REDIRECT_URI",
        "PLAID_COUNTRY_CODES",
        "PLAID_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.plaid_connections_enabled is False
    assert settings.plaid_environment == "sandbox"
    assert settings.plaid_client_id == ""
    assert settings.plaid_secret.get_secret_value() == ""
    assert settings.plaid_country_codes == "US"
    assert settings.plaid_timeout_seconds == 15.0


def test_plaid_secret_is_redacted_by_settings_serialization() -> None:
    settings = Settings(PLAID_SECRET="deployment-secret-must-not-leak", _env_file=None)

    assert "deployment-secret-must-not-leak" not in repr(settings)
    assert "deployment-secret-must-not-leak" not in settings.model_dump_json()


def test_provider_factory_unwraps_secret_only_for_authenticated_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Plaid-Version"] == "2020-09-14"
        assert request.headers["PLAID-SECRET"] == "deployment-secret-scrubbed"
        return httpx.Response(
            200,
            json={"link_token": "link-token", "expiration": "2026-08-25T23:59:59Z"},
        )

    async def run() -> None:
        settings = Settings(
            PLAID_CONNECTIONS_ENABLED=True,
            PLAID_CLIENT_ID="client-id-scrubbed",
            PLAID_SECRET="deployment-secret-scrubbed",
            PLAID_WEBHOOK_URL="https://example.test/webhook",
            PLAID_REDIRECT_URI="https://example.test/oauth",
            _env_file=None,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = PlaidConnectionProvider.from_settings(settings, http_client=client)
            await provider.create_link_token(user_id="workspace-user-1")

    asyncio.run(run())


def test_readiness_reports_presence_without_returning_credentials() -> None:
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(500))) as client:
            provider = PlaidConnectionProvider(http_client=client)
            readiness = provider.configuration_readiness()

            assert readiness.enabled is False
            assert readiness.configured is False
            assert readiness.secret_configured is False
            assert "PLAID_SECRET" in readiness.missing_settings
            assert "test-secret-scrubbed" not in repr(readiness)

            with pytest.raises(FinancialConnectionError) as exc_info:
                await provider.get_accounts("access-token-must-not-leak")
            assert exc_info.value.code == "PROVIDER_DISABLED"
            assert "access-token-must-not-leak" not in str(exc_info.value)
            assert "access-token-must-not-leak" not in repr(exc_info.value)

    asyncio.run(run())


def test_link_token_create_and_exchange_use_headers_and_normalized_results() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/link/token/create":
            return httpx.Response(
                200,
                json={
                    "link_token": "link-token-scrubbed",
                    "expiration": "2026-08-25T23:59:59Z",
                    "request_id": "request-link-scrubbed",
                },
            )
        if request.url.path == "/item/public_token/exchange":
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token-scrubbed",
                    "item_id": "Item_CaseSensitive_01",
                    "request_id": "request-exchange-scrubbed",
                },
            )
        raise AssertionError(request.url.path)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _provider(client)
            session = await provider.create_link_token(user_id="workspace-user-1")
            exchange = await provider.exchange_public_token("public-token-scrubbed")

            assert session.link_token == "link-token-scrubbed"
            assert exchange.provider_item_id == "Item_CaseSensitive_01"
            assert exchange.access_token == "access-token-scrubbed"
            assert "access-token-scrubbed" not in repr(exchange)
            assert not hasattr(exchange, "__dict__")

    asyncio.run(run())

    link_payload = json.loads(requests[0].content)
    exchange_payload = json.loads(requests[1].content)
    assert link_payload == {
        "client_name": "BuildWealth",
        "country_codes": ["US", "CA"],
        "language": "en",
        "products": ["investments"],
        "redirect_uri": "https://example.test/plaid/oauth",
        "user": {"client_user_id": "workspace-user-1"},
        "webhook": "https://example.test/api/webhooks/plaid",
    }
    assert exchange_payload == {"public_token": "public-token-scrubbed"}
    for request in requests:
        assert request.headers["PLAID-CLIENT-ID"] == "test-client-id-scrubbed"
        assert request.headers["PLAID-SECRET"] == "test-secret-scrubbed"
        assert "client_id" not in json.loads(request.content)
        assert "secret" not in json.loads(request.content)


def test_update_mode_link_token_uses_access_token_and_omits_products() -> None:
    captured: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"link_token": "update-link", "expiration": "2026-08-25T23:59:59Z"},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await _provider(client).create_link_token(
                user_id="workspace-user-1",
                access_token="access-token-update-scrubbed",
            )

    asyncio.run(run())

    assert captured[0]["access_token"] == "access-token-update-scrubbed"
    assert "products" not in captured[0]


def test_item_accounts_holdings_and_remove_are_normalized() -> None:
    fixture = json.loads((FIXTURES / "holdings_get.json").read_text())

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/item/get":
            return httpx.Response(
                200,
                json={
                    "item": {
                        "item_id": "Item_CaseSensitive_01",
                        "institution_id": "ins_123",
                        "webhook": "https://example.test/api/webhooks/plaid",
                        "consent_expiration_time": None,
                        "available_products": ["transactions"],
                        "billed_products": ["investments"],
                        "products": ["investments"],
                        "error": None,
                    },
                    "request_id": "request-item-scrubbed",
                },
            )
        if request.url.path == "/accounts/get":
            return httpx.Response(
                200,
                json={"accounts": fixture["accounts"], "request_id": "request-accounts"},
            )
        if request.url.path == "/investments/holdings/get":
            return httpx.Response(200, json=fixture)
        if request.url.path == "/item/remove":
            return httpx.Response(200, json={"request_id": "request-remove"})
        raise AssertionError(request.url.path)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _provider(client)
            item = await provider.get_item("access-token-scrubbed")
            accounts = await provider.get_accounts("access-token-scrubbed")
            holdings = await provider.get_investment_holdings("access-token-scrubbed")
            removal = await provider.remove_item("access-token-scrubbed")

            assert item.provider_item_id == "Item_CaseSensitive_01"
            assert item.billed_products == ("investments",)
            assert accounts.accounts[0].provider_account_id == "Acct_CaseSensitive_01"
            assert accounts.accounts[0].current_balance == 10125.5
            assert holdings.holdings[0].provider_security_id == "Security_CaseSensitive_01"
            assert holdings.holdings[0].quantity == 200.0
            assert holdings.securities[0].ticker_symbol == "EXMPL"
            assert removal.removed is True

    asyncio.run(run())


def test_errors_are_classified_retried_and_do_not_leak_tokens() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            503,
            json={
                "error_type": "INSTITUTION_ERROR",
                "error_code": "INSTITUTION_DOWN",
                "error_message": "unsafe provider text access-token-must-not-leak",
                "request_id": "request-error-scrubbed",
            },
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(FinancialConnectionError) as exc_info:
                await _provider(client).get_accounts("access-token-must-not-leak")

            error = exc_info.value
            assert error.code == "INSTITUTION_DOWN"
            assert error.disposition is ErrorDisposition.RETRYABLE
            assert error.request_id == "request-error-scrubbed"
            assert error.status_code == 503
            assert "access-token-must-not-leak" not in str(error)
            assert "access-token-must-not-leak" not in repr(error)

    asyncio.run(run())
    assert attempts == 2


def test_item_login_required_is_repairable_without_retry() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            400,
            json={"error_type": "ITEM_ERROR", "error_code": "ITEM_LOGIN_REQUIRED"},
        )

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(FinancialConnectionError) as exc_info:
                await _provider(client).get_item("access-token-scrubbed")
            assert exc_info.value.disposition is ErrorDisposition.REPAIRABLE

    asyncio.run(run())
    assert attempts == 1


def test_webhook_signature_body_freshness_and_key_cache_are_verified() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private_key.public_key()))
    public_jwk.update({"kid": "key-1", "alg": "ES256", "use": "sig"})
    body = json.dumps(
        {
            "webhook_type": "HOLDINGS",
            "webhook_code": "DEFAULT_UPDATE",
            "item_id": "Item_CaseSensitive_01",
            "environment": "sandbox",
        },
        separators=(",", ":"),
    ).encode()
    verification_token = jwt.encode(
        {"iat": int(time.time()), "request_body_sha256": hashlib.sha256(body).hexdigest()},
        private_key,
        algorithm="ES256",
        headers={"kid": "key-1"},
    )
    key_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal key_requests
        assert request.url.path == "/webhook_verification_key/get"
        assert json.loads(request.content) == {"key_id": "key-1"}
        key_requests += 1
        return httpx.Response(200, json={"key": public_jwk, "request_id": "request-key"})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = _provider(client)
            event = await provider.validate_webhook(
                raw_body=body,
                verification_token=verification_token,
            )
            assert event.event_type == "HOLDINGS"
            assert event.event_code == "DEFAULT_UPDATE"
            assert event.provider_item_id == "Item_CaseSensitive_01"

            await provider.validate_webhook(raw_body=body, verification_token=verification_token)
            with pytest.raises(FinancialConnectionError) as exc_info:
                await provider.validate_webhook(
                    raw_body=body + b" ",
                    verification_token=verification_token,
                )
            assert exc_info.value.code == "WEBHOOK_BODY_MISMATCH"

    asyncio.run(run())
    assert key_requests == 1

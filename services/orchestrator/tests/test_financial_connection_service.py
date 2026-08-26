from __future__ import annotations

import asyncio
from types import SimpleNamespace

from buildwealth_orchestrator.clients.financial_connections import (
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
)
from buildwealth_orchestrator.services.financial_connection_service import (
    FinancialConnectionService,
)
from buildwealth_orchestrator.services.financial_connections import (
    FinancialConnectionStore,
)
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.connected_portfolio import (
    resolve_connected_portfolio,
)
from buildwealth_orchestrator.services.workspace_settings import WorkspaceSecretStore


class _FakeProvider:
    provider = "plaid"

    def __init__(self) -> None:
        self.environment = "sandbox"
        self.quantity = 5.0
        self.remove_error: Exception | None = None
        self.holdings_error: Exception | None = None
        self.exchange_calls = 0

    def configuration_readiness(self) -> ProviderReadiness:
        return ProviderReadiness(
            provider="plaid",
            enabled=True,
            configured=True,
            environment=self.environment,
            client_id_configured=True,
            secret_configured=True,
            webhook_url_configured=True,
            redirect_uri_configured=True,
            country_codes_configured=True,
        )

    async def create_link_token(self, *, user_id: str, access_token: str | None = None):
        return LinkSession(link_token="link-token", expires_at="2026-08-26T00:00:00Z")

    async def exchange_public_token(self, public_token: str) -> TokenExchange:
        self.exchange_calls += 1
        assert public_token == "one-use-public-token"
        return TokenExchange(
            access_token="access-token-must-stay-secret",
            provider_item_id="item-case-Sensitive",
            request_id="request-exchange",
        )

    async def get_item(self, access_token: str) -> ProviderItem:
        assert access_token == "access-token-must-stay-secret"
        return ProviderItem(
            provider_item_id="item-case-Sensitive",
            institution_id="ins_110476",
            webhook_url="https://example.test/api/webhooks/plaid",
            consent_expiration_at=None,
            available_products=(),
            billed_products=("investments",),
            products=("investments",),
            request_id="request-item",
        )

    async def get_investment_holdings(self, access_token: str):
        assert access_token == "access-token-must-stay-secret"
        if self.holdings_error is not None:
            raise self.holdings_error
        account = ProviderAccount(
            provider_account_id="provider-account-1",
            name="Individual Brokerage",
            official_name="Hills Bank Brokerage",
            account_type="investment",
            account_subtype="brokerage",
            mask="4321",
            current_balance=1500.0,
            available_balance=None,
            limit=None,
            iso_currency_code="USD",
            unofficial_currency_code=None,
        )
        security = ProviderSecurity(
            provider_security_id="security-vti",
            name="Vanguard Total Stock Market ETF",
            ticker_symbol="VTI",
            security_type="etf",
            security_subtype=None,
            cusip=None,
            isin=None,
            sedol=None,
            close_price=300.0,
            close_price_as_of="2026-08-25",
            iso_currency_code="USD",
            unofficial_currency_code=None,
            is_cash_equivalent=False,
        )
        holding = ProviderHolding(
            provider_account_id="provider-account-1",
            provider_security_id="security-vti",
            quantity=self.quantity,
            institution_value=self.quantity * 300.0,
            institution_price=300.0,
            institution_price_as_of="2026-08-25",
            cost_basis=1200.0,
            iso_currency_code="USD",
            unofficial_currency_code=None,
        )
        return InvestmentHoldingsSnapshot(
            accounts=(account,),
            holdings=(holding,),
            securities=(security,),
            request_id="request-holdings",
        )

    async def remove_item(self, access_token: str):
        if self.remove_error is not None:
            raise self.remove_error
        return ItemRemoval(removed=True, request_id="request-remove")


class _FakeControlPlane:
    def __init__(self) -> None:
        self.index: dict[tuple[str, str], SimpleNamespace] = {}

    def lookup_financial_connection_index(self, *, provider: str, provider_item_id: str):
        return self.index.get((provider, provider_item_id))

    def register_financial_connection_index(self, **record):
        value = SimpleNamespace(**record)
        self.index[(record["provider"], record["provider_item_id"])] = value
        return value

    def remove_financial_connection_index(self, **record):
        return self.index.pop((record["provider"], record["provider_item_id"]), None) is not None


def test_exchange_stays_staged_until_user_activates_accounts(tmp_path) -> None:
    asyncio.run(_exercise_exchange_and_activation(tmp_path))


def test_phase_one_accepts_only_investment_accounts() -> None:
    assert FinancialConnectionService._is_phase_one_investment_account(
        {"type": "investment", "subtype": "ira"}
    )
    assert not FinancialConnectionService._is_phase_one_investment_account(
        {"type": "loan", "subtype": "mortgage"}
    )
    assert not FinancialConnectionService._is_phase_one_investment_account(
        {"type": "credit", "subtype": "credit card"}
    )


def test_duplicate_institution_is_rejected_before_public_token_exchange(tmp_path) -> None:
    async def run() -> None:
        connection_store = FinancialConnectionStore(tmp_path / "connections", workspace_id="ws_household")
        provider = _FakeProvider()
        services = SimpleNamespace(
            context=SimpleNamespace(workspace_id="ws_household"),
            financial_connection_store=connection_store,
            secret_store=WorkspaceSecretStore(tmp_path / "settings" / "secrets.json", b"s" * 32),
            portfolio_store=PortfolioStore(tmp_path / "portfolio"),
            recommendation_inbox=SimpleNamespace(create=lambda **kwargs: kwargs),
        )
        service = FinancialConnectionService(provider=provider, services=services, control_plane=_FakeControlPlane())
        await service.exchange_public_token(
            user_id="owner",
            public_token="one-use-public-token",
            institution={"institution_id": "ins_110476", "name": "Hills Bank"},
        )
        try:
            await service.exchange_public_token(
                user_id="owner",
                public_token="one-use-public-token",
                institution={"institution_id": "ins_110476", "name": "Hills Bank"},
            )
        except Exception as exc:
            assert getattr(exc, "code", "") == "DUPLICATE_INSTITUTION_CONNECTION"
        else:
            raise AssertionError("duplicate institution should be rejected")
        assert provider.exchange_calls == 1

    asyncio.run(run())


def test_production_connections_require_secret_key_outside_backup_data(tmp_path) -> None:
    async def run() -> None:
        provider = _FakeProvider()
        provider.environment = "production"
        services = SimpleNamespace(
            context=SimpleNamespace(workspace_id="ws_household"),
            financial_connection_store=FinancialConnectionStore(tmp_path / "connections", workspace_id="ws_household"),
            secret_store=WorkspaceSecretStore(tmp_path / "settings" / "secrets.json", b"s" * 32),
            portfolio_store=PortfolioStore(tmp_path / "portfolio"),
            recommendation_inbox=SimpleNamespace(create=lambda **kwargs: kwargs),
            secret_key_source="data_dir",
        )
        service = FinancialConnectionService(provider=provider, services=services, control_plane=_FakeControlPlane())
        try:
            await service.create_link_token(user_id="owner")
        except Exception as exc:
            assert getattr(exc, "code", "") == "PRODUCTION_SECRET_KEY_NOT_EXTERNAL"
        else:
            raise AssertionError("production should reject a backup-colocated decryption key")

        services.secret_key_source = "file_override"
        response = await service.create_link_token(user_id="owner")
        assert response["link_token"] == "link-token"

    asyncio.run(run())


async def _exercise_exchange_and_activation(tmp_path) -> None:
    connection_store = FinancialConnectionStore(
        tmp_path / "connections", workspace_id="ws_household"
    )
    secret_store = WorkspaceSecretStore(
        tmp_path / "settings" / "workspace_secrets.json", b"s" * 32
    )
    portfolio_store = PortfolioStore(tmp_path / "portfolio")
    services = SimpleNamespace(
        context=SimpleNamespace(workspace_id="ws_household"),
        financial_connection_store=connection_store,
        secret_store=secret_store,
        portfolio_store=portfolio_store,
        recommendation_inbox=SimpleNamespace(create=lambda **kwargs: kwargs),
    )
    service = FinancialConnectionService(
        provider=_FakeProvider(),
        services=services,
        control_plane=_FakeControlPlane(),
    )

    exchanged = await service.exchange_public_token(
        user_id="user_household_owner",
        public_token="one-use-public-token",
        institution={"institution_id": "ins_110476", "name": "Hills Bank"},
    )

    connection_id = exchanged["connection"]["connection_id"]
    assert exchanged["connection"]["status"] == "pending_review"
    assert exchanged["preview"]["accounts"][0]["name"] == "Individual Brokerage"
    assert "access-token-must-stay-secret" not in str(exchanged)
    assert "access-token-must-stay-secret" not in connection_store.metadata_path.read_text()
    assert "access-token-must-stay-secret" not in secret_store.secrets_path.read_text()
    assert connection_store.get_observation_state(connection_id)["current"] is None

    activated = await service.activate_connection(
        connection_id=connection_id,
        accounts=[
            {
                "provider_account_id": "provider-account-1",
                "include": True,
                "buildwealth_account_id": None,
            }
        ],
    )

    assert activated["connection"]["status"] == "active"
    assert activated["report"]["accounts_created"] == 1
    current = connection_store.get_observation_state(connection_id)["current"]
    assert current["holdings"][0]["symbol_or_identifier"] == "VTI"
    assert current["holdings"][0]["buildwealth_account_id"]

    resolved = resolve_connected_portfolio(
        portfolio_store.get_holdings(),
        connection_store=connection_store,
        portfolio_store=portfolio_store,
    )
    connected_account_id = current["holdings"][0]["buildwealth_account_id"]
    position = resolved["holdings"][f"{connected_account_id}:VTI"]
    assert position["quantity"] == 5.0
    assert position["current_value"] == 1500.0
    assert position["source"] == "connected"
    assert position["provider_owned"] is True


def test_sync_preserves_previous_snapshot_and_disconnect_retries_before_token_shredding(
    tmp_path,
) -> None:
    asyncio.run(_exercise_sync_and_disconnect(tmp_path))


def test_remove_connected_data_deletes_created_account_shell(tmp_path) -> None:
    asyncio.run(_exercise_remove_connected_data(tmp_path))


async def _exercise_remove_connected_data(tmp_path) -> None:
    provider = _FakeProvider()
    connection_store = FinancialConnectionStore(
        tmp_path / "connections", workspace_id="ws_household"
    )
    services = SimpleNamespace(
        context=SimpleNamespace(workspace_id="ws_household"),
        financial_connection_store=connection_store,
        secret_store=WorkspaceSecretStore(
            tmp_path / "settings" / "workspace_secrets.json", b"s" * 32
        ),
        portfolio_store=PortfolioStore(tmp_path / "portfolio"),
        recommendation_inbox=SimpleNamespace(create=lambda **kwargs: kwargs),
    )
    service = FinancialConnectionService(
        provider=provider,
        services=services,
        control_plane=_FakeControlPlane(),
    )
    assert service._buildwealth_account_type("ira") == "ira"
    assert service._buildwealth_account_type("401k") == "401k"
    exchanged = await service.exchange_public_token(
        user_id="user_household_owner",
        public_token="one-use-public-token",
        institution={"institution_id": "ins_110476", "name": "Hills Bank"},
    )
    connection_id = exchanged["connection"]["connection_id"]
    await service.activate_connection(
        connection_id=connection_id,
        accounts=[
            {
                "provider_account_id": "provider-account-1",
                "include": True,
                "buildwealth_account_id": None,
            }
        ],
    )
    created_account_id = connection_store.list_account_mappings(connection_id)[0][
        "buildwealth_account_id"
    ]
    assert any(
        account["id"] == created_account_id
        for account in services.portfolio_store.get_accounts()
    )

    await service.disconnect_connection(
        connection_id=connection_id,
        retention="remove_connected_data",
    )

    assert all(
        account["id"] != created_account_id
        for account in services.portfolio_store.get_accounts()
    )


async def _exercise_sync_and_disconnect(tmp_path) -> None:
    provider = _FakeProvider()
    connection_store = FinancialConnectionStore(
        tmp_path / "connections", workspace_id="ws_household"
    )
    secret_store = WorkspaceSecretStore(
        tmp_path / "settings" / "workspace_secrets.json", b"s" * 32
    )
    services = SimpleNamespace(
        context=SimpleNamespace(workspace_id="ws_household"),
        financial_connection_store=connection_store,
        secret_store=secret_store,
        portfolio_store=PortfolioStore(tmp_path / "portfolio"),
        recommendation_inbox=SimpleNamespace(create=lambda **kwargs: kwargs),
    )
    service = FinancialConnectionService(
        provider=provider,
        services=services,
        control_plane=_FakeControlPlane(),
    )
    exchanged = await service.exchange_public_token(
        user_id="user_household_owner",
        public_token="one-use-public-token",
        institution={"institution_id": "ins_110476", "name": "Hills Bank"},
    )
    connection_id = exchanged["connection"]["connection_id"]
    await service.activate_connection(
        connection_id=connection_id,
        accounts=[
            {
                "provider_account_id": "provider-account-1",
                "include": True,
                "buildwealth_account_id": None,
            }
        ],
    )

    provider.quantity = 6.0
    synced = await service.sync_connection(
        connection_id=connection_id,
        trigger="manual",
    )
    state = connection_store.get_observation_state(connection_id)
    assert synced["change_summary"]["quantity_changes"] == 1
    assert state["previous"]["holdings"][0]["quantity"] == 5.0
    assert state["current"]["holdings"][0]["quantity"] == 6.0

    provider.holdings_error = FinancialConnectionError(
        provider="plaid",
        code="INSTITUTION_DOWN",
        message="Plaid is temporarily unavailable",
        disposition=ErrorDisposition.RETRYABLE,
    )
    try:
        await service.sync_connection(connection_id=connection_id, trigger="scheduled")
    except FinancialConnectionError:
        pass
    else:
        raise AssertionError("retryable sync failure should surface")
    assert connection_store.get_connection(connection_id)["status"] == "active"
    assert connection_store.get_observation_state(connection_id)["current"]["holdings"][0]["quantity"] == 6.0
    provider.holdings_error = None

    provider.remove_error = FinancialConnectionError(
        provider="plaid",
        code="INSTITUTION_DOWN",
        message="Plaid is temporarily unavailable",
        disposition=ErrorDisposition.RETRYABLE,
    )
    try:
        await service.disconnect_connection(
            connection_id=connection_id,
            retention="keep_frozen",
        )
    except FinancialConnectionError:
        pass
    else:
        raise AssertionError("disconnect should surface a retryable provider failure")

    pending = connection_store.get_connection(connection_id)
    assert pending["status"] == "disconnect_pending"
    token_key = f"financial_connection:plaid:{connection_id}:access_token"
    assert secret_store.get_secret(token_key) == "access-token-must-stay-secret"

    provider.remove_error = None
    disconnected = await service.disconnect_connection(
        connection_id=connection_id,
        retention="keep_frozen",
    )
    assert disconnected["remote_access_removed"] is True
    assert disconnected["connection"]["status"] == "disconnected"
    assert secret_store.get_secret(token_key) == ""
    assert connection_store.get_observation_state(connection_id)["current"] is not None

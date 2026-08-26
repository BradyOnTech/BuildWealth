from __future__ import annotations

import json
from pathlib import Path
import tarfile

import pytest

from buildwealth_orchestrator.services import financial_connections as connection_store_module
from buildwealth_orchestrator.services.account_data_deletion import (
    AccountDataDeletionPurgeError,
    AccountDataDeletionPurgeWorker,
    build_account_data_deletion_preview,
)
from buildwealth_orchestrator.services.control_plane import (
    ControlPlaneStore,
    DEFAULT_HOUSEHOLD_WORKSPACE_ID,
    RequestContext,
)
from buildwealth_orchestrator.services.backup_restore import BackupRestoreService
from buildwealth_orchestrator.services.data_protection import DataProtectionService
from buildwealth_orchestrator.services.financial_connections import (
    FinancialConnectionStore,
    FinancialConnectionStoreError,
    financial_connection_access_token_key,
    load_financial_connection_access_token,
    remove_financial_connection_access_token,
    save_financial_connection_access_token,
)
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory
from buildwealth_orchestrator.services.workspace_settings import (
    WorkspaceSecretStore,
    load_or_create_local_secret_key,
)
from buildwealth_orchestrator.settings import Settings


def _control_plane(tmp_path: Path) -> ControlPlaneStore:
    store = ControlPlaneStore(tmp_path / "control" / "control.db")
    store.bootstrap_default_household(
        owner_email="owner@example.test",
        default_storage_root=tmp_path / "real",
        demo_storage_root=tmp_path / "demo",
    )
    return store


def _connection(**overrides):
    return {
        "connection_id": "conn_A",
        "provider": "plaid",
        "workspace_id": "ws_1",
        "connected_by_user_id": "usr_1",
        "provider_item_id": "Item_CaseSensitive",
        "institution_id": "ins_1",
        "institution_name": "Hills Bank",
        "status": "pending_review",
        "environment": "sandbox",
        "consented_products": ["investments"],
        **overrides,
    }


def _snapshot(*, quantity: float, observed_at: str):
    return {
        "accounts": [
            {
                "provider_account_id": "Account_CaseSensitive",
                "buildwealth_account_id": "ira",
                "name": "IRA",
                "type": "investment",
                "subtype": "ira",
                "current_balance": quantity * 100,
                "cash_balance": 25,
                "currency": "usd",
            }
        ],
        "holdings": [
            {
                "provider_account_id": "Account_CaseSensitive",
                "buildwealth_account_id": "ira",
                "provider_security_id": "Security_CaseSensitive",
                "symbol_or_identifier": "VTI",
                "name": "Vanguard Total Stock Market ETF",
                "quantity": quantity,
                "institution_price": 100,
                "institution_value": quantity * 100,
                "cost_basis": None,
                "currency": "usd",
            }
        ],
        "observed_at": observed_at,
        "provider_payload_version": "plaid-investments-v1",
    }


def test_control_plane_index_is_case_sensitive_token_free_and_not_reassignable(
    tmp_path: Path,
) -> None:
    control = _control_plane(tmp_path)
    indexed = control.register_financial_connection_index(
        provider="Plaid",
        provider_item_id="Item_ABC",
        workspace_id=DEFAULT_HOUSEHOLD_WORKSPACE_ID,
        connection_id="conn_1",
    )

    assert indexed.provider == "plaid"
    assert indexed.provider_item_id == "Item_ABC"
    assert control.lookup_financial_connection_index(
        provider="PLAID", provider_item_id="Item_ABC"
    ) == indexed
    assert control.lookup_financial_connection_index(
        provider="plaid", provider_item_id="item_abc"
    ) is None
    with control._connect() as connection:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(financial_connection_index)"
            ).fetchall()
        }
    assert not {"access_token", "secret", "public_token"}.intersection(columns)

    with pytest.raises(ValueError, match="already assigned"):
        control.register_financial_connection_index(
            provider="plaid",
            provider_item_id="Item_ABC",
            workspace_id=DEFAULT_HOUSEHOLD_WORKSPACE_ID,
            connection_id="conn_2",
        )

    exported = control.export_account_bundle(control.default_dev_user()["id"])
    assert exported["financial_connection_indexes"][0]["provider_item_id"] == "Item_ABC"
    assert "access_token" not in json.dumps(exported)


def test_connection_permissions_follow_workspace_roles() -> None:
    assert {"connections.read", "connections.write"} <= ControlPlaneStore.ROLE_PERMISSIONS[
        "owner"
    ]
    assert {"connections.read", "connections.write"} <= ControlPlaneStore.ROLE_PERMISSIONS[
        "member"
    ]
    assert "connections.read" in ControlPlaneStore.ROLE_PERMISSIONS["read_only"]
    assert "connections.write" not in ControlPlaneStore.ROLE_PERMISSIONS["read_only"]
    assert "connections.read" in ControlPlaneStore.ROLE_PERMISSIONS["advisor"]
    assert "connections.write" not in ControlPlaneStore.ROLE_PERMISSIONS["advisor"]


def test_workspace_store_persists_mapping_sync_and_rotating_observations(tmp_path: Path) -> None:
    store = FinancialConnectionStore(tmp_path / "financial_connections", workspace_id="ws_1")
    created = store.upsert_connection(_connection(access_token="must-not-persist"))
    assert created["provider_item_id"] == "Item_CaseSensitive"
    assert "must-not-persist" not in store.metadata_path.read_text(encoding="utf-8")

    mapping = store.upsert_account_mapping(
        {
            "connection_id": "conn_A",
            "provider_account_id": "Account_CaseSensitive",
            "buildwealth_account_id": "ira",
            "match_status": "confirmed",
            "provider_name": "IRA",
            "provider_official_name": "Individual Retirement Account",
            "provider_type": "investment",
            "provider_subtype": "ira",
            "mask": "1234",
            "currency": "usd",
        }
    )
    assert mapping["provider_account_id"] == "Account_CaseSensitive"

    run = store.start_sync_run(connection_id="conn_A", trigger="initial")
    with pytest.raises(FinancialConnectionStoreError, match="already running"):
        store.start_sync_run(connection_id="conn_A", trigger="daily")
    finished = store.finish_sync_run(
        run["sync_run_id"],
        outcome="succeeded",
        provider_request_ids=["request-1"],
        counts={"accounts": 1, "holdings": 1},
    )
    assert finished["counts"] == {"accounts": 1, "holdings": 1}

    first = store.stage_observation(
        connection_id="conn_A",
        snapshot_id="snapshot-1",
        **_snapshot(quantity=2, observed_at="2026-08-24T12:00:00+00:00"),
    )
    assert store.get_observation_state("conn_A")["current"] is None
    store.promote_staged_observation("conn_A", expected_snapshot_id=first["snapshot_id"])
    second = store.stage_observation(
        connection_id="conn_A",
        snapshot_id="snapshot-2",
        **_snapshot(quantity=3, observed_at="2026-08-25T12:00:00+00:00"),
    )
    store.promote_staged_observation("conn_A", expected_snapshot_id=second["snapshot_id"])

    state = FinancialConnectionStore(
        tmp_path / "financial_connections", workspace_id="ws_1"
    ).get_observation_state("conn_A")
    assert state["staged"] is None
    assert state["current"]["snapshot_id"] == "snapshot-2"
    assert state["previous"]["snapshot_id"] == "snapshot-1"
    assert state["current"]["holdings"][0]["quantity"] == 3
    assert state["previous"]["holdings"][0]["quantity"] == 2
    assert state["current"]["holdings"][0]["connection_id"] == "conn_A"
    assert store.list_current_observed_holdings(buildwealth_account_id="ira")[0][
        "provider_security_id"
    ] == "Security_CaseSensitive"

    report = store.create_connection_report(
        {
            "report_id": "report-1",
            "connection_id": "conn_A",
            "action": "activated",
            "accounts_created": 1,
            "holdings_activated": 1,
        }
    )
    assert report["accounts_created"] == 1
    assert store.list_connection_reports("conn_A")[0]["counts"]["holdings_activated"] == 1
    assert store.record_webhook_event(
        event_id="event-sha256",
        connection_id="conn_A",
        event_type="HOLDINGS",
        event_code="DEFAULT_UPDATE",
        received_at="2026-08-25T13:00:00+00:00",
    )
    assert not store.record_webhook_event(
        event_id="event-sha256",
        connection_id="conn_A",
        event_type="HOLDINGS",
        event_code="DEFAULT_UPDATE",
        received_at="2026-08-25T13:00:01+00:00",
    )
    event_id = "delivery-retry"
    assert store.record_webhook_event(
        event_id=event_id,
        connection_id="conn_A",
        event_type="HOLDINGS",
        event_code="DEFAULT_UPDATE",
    )
    assert store.claim_webhook_event(event_id)
    assert not store.claim_webhook_event(event_id)
    assert store.finish_webhook_event(event_id, succeeded=False, error_code="INSTITUTION_DOWN")
    assert store.claim_webhook_event(event_id)
    assert store.finish_webhook_event(event_id, succeeded=True)
    assert not store.claim_webhook_event(event_id)

    with pytest.raises(ValueError, match="finite number"):
        store.stage_observation(
            connection_id="conn_A",
            snapshot_id="invalid-snapshot",
            **_snapshot(quantity=float("nan"), observed_at="2026-08-26T12:00:00+00:00"),
        )
    assert store.get_observation_state("conn_A")["current"]["snapshot_id"] == "snapshot-2"


def test_connection_store_atomic_write_failure_preserves_previous_file(
    tmp_path: Path, monkeypatch
) -> None:
    store = FinancialConnectionStore(tmp_path / "financial_connections", workspace_id="ws_1")
    store.upsert_connection(_connection())
    before = store.metadata_path.read_bytes()

    def fail_replace(_source, _target) -> None:
        raise OSError("disk failure")

    monkeypatch.setattr(connection_store_module.os, "replace", fail_replace)
    with pytest.raises(FinancialConnectionStoreError, match="atomically write"):
        store.update_connection("conn_A", {"institution_name": "Changed"})
    assert store.metadata_path.read_bytes() == before


def test_access_token_helpers_use_only_encrypted_workspace_secret_store(tmp_path: Path) -> None:
    key = load_or_create_local_secret_key(tmp_path / "secret.key")
    secrets_path = tmp_path / "workspace_secrets.json"
    secret_store = WorkspaceSecretStore(secrets_path, key)
    expected_key = "financial_connection:plaid:conn_A:access_token"
    assert (
        financial_connection_access_token_key(provider="Plaid", connection_id="conn_A")
        == expected_key
    )

    save_financial_connection_access_token(
        secret_store,
        provider="plaid",
        connection_id="conn_A",
        access_token="access-sandbox-secret",
    )
    assert "access-sandbox-secret" not in secrets_path.read_text(encoding="utf-8")
    assert (
        load_financial_connection_access_token(
            secret_store, provider="plaid", connection_id="conn_A"
        )
        == "access-sandbox-secret"
    )
    remove_financial_connection_access_token(
        secret_store, provider="plaid", connection_id="conn_A"
    )
    assert not load_financial_connection_access_token(
        secret_store, provider="plaid", connection_id="conn_A"
    )


def test_portfolio_account_provider_metadata_survives_normalization_and_detaches(
    tmp_path: Path,
) -> None:
    portfolio_dir = tmp_path / "portfolio"
    portfolio_dir.mkdir()
    (portfolio_dir / "accounts.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "default_account_id": "ira",
                "accounts": [
                    {
                        "id": "ira",
                        "name": "Existing IRA",
                        "type": "ira",
                        "currency": "USD",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "source": "manual",
                        "provider": "plaid",
                        "connection_id": "conn_A",
                        "provider_account_id": "Account_CaseSensitive",
                        "institution_name": "Hills Bank",
                        "mask": "1234",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    store = PortfolioStore(portfolio_dir)
    account = store.get_accounts()[0]
    assert account["source"] == "manual"
    assert account["provider_metadata"]["provider_account_id"] == "Account_CaseSensitive"

    holdings_before = store.get_holdings()
    attached = store.attach_provider_account_mapping(
        "ira",
        provider="plaid",
        connection_id="conn_A",
        provider_account_id="Account_CaseSensitive",
        institution_name="Hills Bank",
        provider_official_name="Individual Retirement Account",
        last_observed_at="2026-08-25T12:00:00+00:00",
    )
    assert attached["provider_metadata"]["provider_official_name"]
    holdings_after_attach = store.get_holdings()
    assert holdings_after_attach["holdings"] == holdings_before["holdings"]
    assert holdings_after_attach["account_cash"] == holdings_before["account_cash"]
    assert holdings_after_attach["total_portfolio_value"] == holdings_before[
        "total_portfolio_value"
    ]

    detached = store.detach_provider_account_mapping(
        "ira",
        connection_id="conn_A",
        provider_account_id="Account_CaseSensitive",
    )
    assert detached["source"] == "manual"
    assert "provider_metadata" not in detached
    holdings_after_detach = store.get_holdings()
    assert holdings_after_detach["holdings"] == holdings_before["holdings"]
    assert holdings_after_detach["account_cash"] == holdings_before["account_cash"]
    assert holdings_after_detach["total_portfolio_value"] == holdings_before[
        "total_portfolio_value"
    ]


def test_workspace_wiring_protection_and_deletion_preview_include_connections(
    tmp_path: Path,
) -> None:
    settings = Settings(
        CONTROL_DB_PATH=tmp_path / "control" / "control.db",
        WORKSPACE_ROOT_DIR=tmp_path / "workspaces",
        SECRET_KEY_PATH=tmp_path / "control" / "secret.key",
    )
    control = _control_plane(tmp_path)
    factory = WorkspaceServiceFactory(settings=settings, control_plane=control)
    user_id = control.default_dev_user()["id"]
    context = RequestContext(
        user_id=user_id,
        organization_id="org_default_household",
        workspace_id=DEFAULT_HOUSEHOLD_WORKSPACE_ID,
        role="owner",
        permissions=ControlPlaneStore.ROLE_PERMISSIONS["owner"],
        is_demo_workspace=False,
        auth_mode="dev",
    )
    services = factory.for_context(context)
    assert services.financial_connection_store.storage_dir == (
        services.paths.financial_connections_dir
    )
    services.financial_connection_store.upsert_connection(
        _connection(workspace_id=DEFAULT_HOUSEHOLD_WORKSPACE_ID)
    )
    control.register_financial_connection_index(
        provider="plaid",
        provider_item_id="Item_ABC",
        workspace_id=DEFAULT_HOUSEHOLD_WORKSPACE_ID,
        connection_id="conn_A",
    )

    preview = build_account_data_deletion_preview(
        control_plane=control,
        workspace_service_factory=factory,
        context=context,
        scope="workspace",
    )
    item = preview["affected_workspaces"][0]
    categories = {category["id"]: category for category in item["categories"]}
    assert categories["financial_connections"]["exists"] is True
    assert item["financial_connection_index_count"] == 1
    assert preview["totals"]["financial_connection_index_count"] == 1
    assert any("revoked" in warning for warning in preview["warnings"])

    protection = DataProtectionService.from_settings(factory.settings_for_paths(services.paths))
    protection_targets = {item["path"] for item in protection.get_status()["targets"]}
    assert str(services.paths.financial_connections_dir.resolve()) in protection_targets

    backup = BackupRestoreService(
        data_root=services.paths.root,
        backup_dir=services.paths.backup_archive_dir,
    ).create_backup(reason="financial-connection-test")
    with tarfile.open(backup["archive_path"], mode="r:gz") as archive:
        assert "financial_connections/connections.json" in archive.getnames()

    workspace = control.get_workspace_for_user(
        user_id=user_id, workspace_id=DEFAULT_HOUSEHOLD_WORKSPACE_ID
    )[0]
    worker = AccountDataDeletionPurgeWorker(
        control_plane=control,
        workspace_service_factory=factory,
    )
    with pytest.raises(AccountDataDeletionPurgeError, match="removed remotely"):
        worker._purge_workspace(workspace)
    assert services.paths.secrets_path.exists()

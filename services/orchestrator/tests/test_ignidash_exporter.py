import json

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot
from buildwealth_orchestrator.services.ignidash_exporter import (
    IgnidashExportStore,
    build_ignidash_plan_payload,
)
from datetime import datetime, timezone


def _snapshot(accounts: list[dict[str, object]] | None = None) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        base_currency="USD",
        total_value_usd=250000.0,
        total_investment_usd=200000.0,
        net_performance_usd=50000.0,
        net_performance_percent=0.25,
        holdings=[
            Holding(symbol="VTI", name="Vanguard Total Stock Market", value_usd=150000, allocation_percent=60.0),
        ],
        accounts=accounts or [],
    )


def test_build_ignidash_plan_payload_uses_account_details() -> None:
    payload = build_ignidash_plan_payload(
        _snapshot(
            accounts=[
                {"id": "retirement", "name": "Retirement 401k", "balance": 125000.0},
            ]
        )
    )

    assert payload["accounts"][0]["type"] == "401k"
    assert payload["contributionRules"][0]["accountId"] == "gf-retirement"
    assert payload["metadata"]["currency"] == "USD"


def test_ignidash_export_store_writes_json(tmp_path) -> None:
    payload = build_ignidash_plan_payload(_snapshot())
    store = IgnidashExportStore(tmp_path)

    path = store.write(payload)

    assert path.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["newPlanName"] == "BuildWealth Imported Plan"
    assert saved["accounts"][0]["id"] == "gf-default-taxable"

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot


def normalize_ghostfolio_snapshot(
    holdings_payload: dict[str, Any],
    performance_payload: dict[str, Any],
    accounts_payload: dict[str, Any] | list[dict[str, Any]],
    base_currency: str,
) -> PortfolioSnapshot:
    holdings: list[Holding] = []

    for position in holdings_payload.get("holdings", []):
        asset_profile = position.get("assetProfile", {})
        holdings.append(
            Holding(
                symbol=asset_profile.get("symbol") or position.get("symbol") or "UNKNOWN",
                name=asset_profile.get("name") or position.get("name") or "Unknown Asset",
                data_source=asset_profile.get("dataSource") or position.get("dataSource"),
                asset_class=asset_profile.get("assetClass") or position.get("assetClass"),
                allocation_percent=float(position.get("allocationInPercentage") or 0.0),
                value_usd=float(position.get("valueInBaseCurrency") or position.get("value") or 0.0),
                quantity=float(position.get("quantity") or 0.0),
                market_price=(
                    float(position.get("marketPrice"))
                    if position.get("marketPrice") is not None
                    else None
                ),
                net_performance_usd=(
                    float(position.get("netPerformance"))
                    if position.get("netPerformance") is not None
                    else None
                ),
                net_performance_percent=(
                    float(position.get("netPerformancePercent"))
                    if position.get("netPerformancePercent") is not None
                    else None
                ),
            )
        )

    performance = performance_payload.get("performance", {})

    accounts: list[dict[str, Any]]
    if isinstance(accounts_payload, list):
        accounts = accounts_payload
    else:
        accounts = accounts_payload.get("accounts", [])

    return PortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        base_currency=base_currency,
        total_value_usd=float(performance.get("currentValueInBaseCurrency") or 0.0),
        total_investment_usd=float(performance.get("totalInvestment") or 0.0),
        net_performance_usd=float(performance.get("netPerformance") or 0.0),
        net_performance_percent=float(performance.get("netPerformancePercentage") or 0.0),
        holdings=sorted(holdings, key=lambda x: x.value_usd, reverse=True),
        accounts=accounts,
        raw={
            "ghostfolio": {
                "holdings": holdings_payload,
                "performance": performance_payload,
                "accounts": accounts_payload,
            }
        },
    )


class SnapshotStore:
    def __init__(self, snapshot_dir: Path):
        self.snapshot_dir = snapshot_dir
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def write(self, snapshot: PortfolioSnapshot) -> Path:
        filename = snapshot.as_of.strftime("snapshot-%Y%m%dT%H%M%SZ.json")
        path = self.snapshot_dir / filename
        path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")
        return path

    def latest(self) -> PortfolioSnapshot:
        candidates = sorted(self.snapshot_dir.glob("snapshot-*.json"))
        if not candidates:
            raise FileNotFoundError("No snapshot files exist yet")

        payload = json.loads(candidates[-1].read_text(encoding="utf-8"))
        return PortfolioSnapshot(**payload)

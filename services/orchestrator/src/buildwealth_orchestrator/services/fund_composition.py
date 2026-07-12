"""Fund look-through — constituent-level overlap and diversification.

fund_overlap.py answers "do these funds track the same index?" from curated
`tracks` keys. This module goes one level deeper with seeded, approximate
constituent data: what companies, sectors, and regions a household actually
owns once each covered fund is opened up.

Honesty rules the design: the seed carries only broad, slow-moving funds,
every fund records its `as_of` date, and the top-10 basis is named in the
payload — a top-10 overlap number UNDERSTATES true overlap and the report
says so instead of pretending precision.
"""

from __future__ import annotations

import json
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any

_FUND_COMPOSITIONS_SEED_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "fund_compositions_seed.json"
)

_FUND_ASSET_TYPES = {"ETF", "FUND", "MUTUAL_FUND"}
_DIRECT_STOCK_ASSET_TYPES = {"STOCK", "EQUITY"}
_TOP_COMPANY_LIMIT = 15
_PAIRWISE_OVERLAP_FLOOR = 0.15

# Direct holdings write regions like "US"; the fund seed says
# "united_states". Alias so both land in one row instead of two.
_REGION_ALIASES = {
    "us": "united_states",
    "usa": "united_states",
    "u_s": "united_states",
    "united_states_of_america": "united_states",
}


def _normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _normalize_region_key(value: Any) -> str:
    key = _normalize_key(value)
    return _REGION_ALIASES.get(key, key)


def _normalize_weights(raw: Any, *, region: bool = False) -> dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    weights: dict[str, float] = {}
    for key, value in raw.items():
        normalized = _normalize_region_key(key) if region else _normalize_key(key)
        try:
            weight = float(value)
        except (TypeError, ValueError):
            continue
        if normalized and weight > 0:
            weights[normalized] = weights.get(normalized, 0.0) + weight
    return weights


def _normalize_top_holdings(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    holdings: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        try:
            weight = float(item.get("weight"))
        except (TypeError, ValueError):
            continue
        if symbol and 0 < weight < 1:
            holdings.append({"symbol": symbol, "weight": weight})
    return holdings


@lru_cache(maxsize=1)
def load_seed_fund_compositions() -> dict[str, dict[str, Any]]:
    if not _FUND_COMPOSITIONS_SEED_PATH.exists():
        return {}

    try:
        payload = json.loads(_FUND_COMPOSITIONS_SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

    raw_funds = payload.get("funds") if isinstance(payload, dict) else None
    if not isinstance(raw_funds, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for symbol, record in raw_funds.items():
        normalized_symbol = str(symbol or "").strip().upper()
        if not normalized_symbol or not isinstance(record, dict):
            continue
        normalized[normalized_symbol] = {
            "symbol": normalized_symbol,
            "as_of": str(record.get("as_of") or "").strip(),
            "source": str(record.get("source") or "seed_estimate").strip(),
            "asset_class": _normalize_key(record.get("asset_class")),
            "sector_weights": _normalize_weights(record.get("sector_weights")),
            "region_weights": _normalize_weights(record.get("region_weights"), region=True),
            "top_holdings": _normalize_top_holdings(record.get("top_holdings")),
        }
    return normalized


def _safe_value(holding: dict[str, Any]) -> float:
    try:
        value = float(holding.get("current_value") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return value if value > 0 else 0.0


def _exposure_rows(totals: dict[str, float], portfolio_value: float) -> list[dict[str, Any]]:
    rows = [
        {
            "key": key,
            "exposure_usd": round(usd, 2),
            "exposure_pct": round(usd / portfolio_value * 100.0, 2) if portfolio_value > 0 else 0.0,
        }
        for key, usd in totals.items()
        if usd > 0
    ]
    rows.sort(key=lambda row: -row["exposure_usd"])
    return rows


class FundCompositionService:
    """Opens up covered funds into estimated company / sector / region exposure."""

    def __init__(self, compositions: dict[str, dict[str, Any]] | None = None) -> None:
        self._compositions = compositions if compositions is not None else load_seed_fund_compositions()

    def composition_for(self, symbol: str) -> dict[str, Any] | None:
        record = self._compositions.get(str(symbol or "").strip().upper())
        return dict(record) if record else None

    def look_through_report(self, holdings_payload: dict[str, Any]) -> dict[str, Any]:
        raw_holdings = (
            holdings_payload.get("holdings") if isinstance(holdings_payload, dict) else None
        )
        holdings = [h for h in (raw_holdings or {}).values() if isinstance(h, dict)] if isinstance(
            raw_holdings, dict
        ) else [h for h in (raw_holdings or []) if isinstance(h, dict)]

        portfolio_value = sum(_safe_value(h) for h in holdings)

        # Funds first: aggregate value per symbol (same fund can live in
        # several accounts) and split covered from unknown.
        fund_value_by_symbol: dict[str, float] = {}
        direct_holdings: list[dict[str, Any]] = []
        for holding in holdings:
            value = _safe_value(holding)
            if value <= 0:
                continue
            asset_type = str(holding.get("asset_type") or "").strip().upper()
            symbol = str(holding.get("symbol") or "").strip().upper()
            if asset_type in _FUND_ASSET_TYPES and symbol:
                fund_value_by_symbol[symbol] = fund_value_by_symbol.get(symbol, 0.0) + value
            else:
                direct_holdings.append(holding)

        covered: dict[str, dict[str, Any]] = {}
        unknown_funds: list[str] = []
        covered_value = 0.0
        for symbol, value in fund_value_by_symbol.items():
            composition = self._compositions.get(symbol)
            if composition:
                covered[symbol] = composition
                covered_value += value
            else:
                unknown_funds.append(symbol)

        coverage = {
            "covered_value_usd": round(covered_value, 2),
            "total_fund_value_usd": round(sum(fund_value_by_symbol.values()), 2),
            "covered_fund_count": len(covered),
            "unknown_funds": sorted(unknown_funds),
            "covered_funds": [
                {
                    "symbol": symbol,
                    "value_usd": round(fund_value_by_symbol[symbol], 2),
                    "as_of": covered[symbol]["as_of"],
                    "source": covered[symbol]["source"],
                }
                for symbol in sorted(covered, key=lambda s: -fund_value_by_symbol[s])
            ],
        }

        return {
            "schema_version": 1,
            "total_portfolio_value_usd": round(portfolio_value, 2),
            "coverage": coverage,
            "effective_company_exposure": self._company_exposure(
                covered, fund_value_by_symbol, direct_holdings, portfolio_value
            ),
            "sector_exposure": self._weight_exposure(
                covered, fund_value_by_symbol, direct_holdings, portfolio_value, kind="sector"
            ),
            "region_exposure": self._weight_exposure(
                covered, fund_value_by_symbol, direct_holdings, portfolio_value, kind="region"
            ),
            "pairwise_fund_overlap": self._pairwise_overlap(covered),
            "notes": self._notes(covered),
        }

    def _company_exposure(
        self,
        covered: dict[str, dict[str, Any]],
        fund_value_by_symbol: dict[str, float],
        direct_holdings: list[dict[str, Any]],
        portfolio_value: float,
    ) -> list[dict[str, Any]]:
        exposure: dict[str, dict[str, Any]] = {}

        def add(company: str, usd: float, via_fund: str) -> None:
            entry = exposure.setdefault(company, {"usd": 0.0, "via": {}})
            entry["usd"] += usd
            entry["via"][via_fund] = entry["via"].get(via_fund, 0.0) + usd

        for fund_symbol, composition in covered.items():
            fund_value = fund_value_by_symbol.get(fund_symbol, 0.0)
            for top in composition["top_holdings"]:
                add(top["symbol"], fund_value * top["weight"], fund_symbol)

        for holding in direct_holdings:
            asset_type = str(holding.get("asset_type") or "").strip().upper()
            symbol = str(holding.get("symbol") or "").strip().upper()
            if asset_type in _DIRECT_STOCK_ASSET_TYPES and symbol:
                add(symbol, _safe_value(holding), "direct")

        rows = []
        for company, entry in exposure.items():
            usd = entry["usd"]
            rows.append(
                {
                    "symbol": company,
                    "exposure_usd": round(usd, 2),
                    "exposure_pct": round(usd / portfolio_value * 100.0, 2)
                    if portfolio_value > 0
                    else 0.0,
                    "via": [
                        {"fund": fund, "usd": round(via_usd, 2)}
                        for fund, via_usd in sorted(entry["via"].items(), key=lambda kv: -kv[1])
                    ],
                }
            )
        rows.sort(key=lambda row: -row["exposure_usd"])
        return rows[:_TOP_COMPANY_LIMIT]

    def _weight_exposure(
        self,
        covered: dict[str, dict[str, Any]],
        fund_value_by_symbol: dict[str, float],
        direct_holdings: list[dict[str, Any]],
        portfolio_value: float,
        *,
        kind: str,
    ) -> list[dict[str, Any]]:
        weights_key = "sector_weights" if kind == "sector" else "region_weights"
        totals: dict[str, float] = {}

        for fund_symbol, composition in covered.items():
            fund_value = fund_value_by_symbol.get(fund_symbol, 0.0)
            for key, weight in composition[weights_key].items():
                totals[key] = totals.get(key, 0.0) + fund_value * weight

        for holding in direct_holdings:
            raw_key = holding.get(kind)
            key = _normalize_region_key(raw_key) if kind == "region" else _normalize_key(raw_key)
            if not key:
                continue
            totals[key] = totals.get(key, 0.0) + _safe_value(holding)

        return _exposure_rows(totals, portfolio_value)

    def _pairwise_overlap(self, covered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        equity_funds = [
            (symbol, composition)
            for symbol, composition in covered.items()
            if composition["asset_class"] == "equity" and composition["top_holdings"]
        ]

        pairs: list[dict[str, Any]] = []
        for (symbol_a, comp_a), (symbol_b, comp_b) in combinations(sorted(equity_funds), 2):
            weights_a = {h["symbol"]: h["weight"] for h in comp_a["top_holdings"]}
            weights_b = {h["symbol"]: h["weight"] for h in comp_b["top_holdings"]}
            shared = sorted(
                set(weights_a) & set(weights_b),
                key=lambda s: -min(weights_a[s], weights_b[s]),
            )
            overlap_weight = sum(min(weights_a[s], weights_b[s]) for s in shared)
            if overlap_weight >= _PAIRWISE_OVERLAP_FLOOR:
                pairs.append(
                    {
                        "fund_a": symbol_a,
                        "fund_b": symbol_b,
                        "overlap_weight": round(overlap_weight, 4),
                        "shared_top_holdings": shared,
                        "basis": "top_10_holdings",
                    }
                )
        pairs.sort(key=lambda pair: -pair["overlap_weight"])
        return pairs

    @staticmethod
    def _notes(covered: dict[str, dict[str, Any]]) -> list[str]:
        notes = [
            "Constituent weights are seeded estimates for common broad funds, not live provider data.",
            "Pairwise overlap counts only each fund's top-10 holdings, so it understates true overlap.",
        ]
        as_of_dates = sorted({c["as_of"] for c in covered.values() if c["as_of"]})
        if as_of_dates:
            notes.append(
                f"Fund compositions are as of {as_of_dates[0]}"
                + (f" through {as_of_dates[-1]}" if len(as_of_dates) > 1 else "")
                + "; broad-fund weights drift slowly but do drift."
            )
        return notes

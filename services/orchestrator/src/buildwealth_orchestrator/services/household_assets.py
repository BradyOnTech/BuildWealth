"""Canonical interpretation of assets recorded in Profile and Portfolio.

Profile is useful for household context while Portfolio is useful for valuation
and analysis.  A physical asset may legitimately appear in both stores, but it
must contribute to household wealth only once.  This module owns that identity
and source-authority rule so financial-health, housing, planning, and Copilot
do not each invent their own duplicate heuristic.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
from typing import Any, Iterable, Mapping

from buildwealth_orchestrator.services.portfolio_rebalancing import is_untradable_position


_LABEL_TOKEN = re.compile(r"[a-z0-9]+")
_REAL_ESTATE_TYPES = {"property", "real_estate", "real-estate", "home", "house"}
_VEHICLE_TYPES = {"vehicle", "auto", "car", "truck"}


@dataclass(frozen=True)
class CanonicalHouseholdAsset:
    key: str
    label: str
    asset_type: str
    value_usd: float
    source: str
    portfolio_symbol: str | None
    profile_id: str | None
    is_housing: bool
    is_untradable: bool


@dataclass(frozen=True)
class HouseholdAssetReconciliation:
    assets: tuple[CanonicalHouseholdAsset, ...]
    matched_profile_ids: tuple[str, ...]
    portfolio_value_adjustment_usd: float = 0.0

    @property
    def profile_only_value_usd(self) -> float:
        return sum(asset.value_usd for asset in self.assets if asset.source == "profile")


def reconcile_household_assets(
    *,
    portfolio_assets: Iterable[Mapping[str, Any]] | None,
    profile_assets: Iterable[Mapping[str, Any]] | None,
) -> HouseholdAssetReconciliation:
    """Return one canonical row per asset, preferring Portfolio valuation.

    New Profile records can point at a Portfolio record with
    ``portfolio_symbol``.  Existing records are reconciled conservatively only
    when asset kind and value identify one unambiguous Portfolio asset.
    """

    canonical: list[CanonicalHouseholdAsset] = []
    portfolio_rows: list[tuple[CanonicalHouseholdAsset, Mapping[str, Any]]] = []
    portfolio_by_symbol: dict[str, CanonicalHouseholdAsset] = {}

    for index, raw in enumerate(portfolio_assets or ()):
        if not isinstance(raw, Mapping):
            continue
        symbol = _clean_symbol(raw.get("symbol"))
        value = _money(raw.get("current_value", raw.get("value_usd")))
        if value <= 0:
            continue
        asset_type = _asset_kind(raw.get("asset_type"), raw.get("asset_class"))
        record = CanonicalHouseholdAsset(
            key=f"portfolio:{symbol or index}",
            label=str(raw.get("name") or symbol or "Asset").strip(),
            asset_type=asset_type,
            value_usd=value,
            source="portfolio",
            portfolio_symbol=symbol or None,
            profile_id=None,
            is_housing=asset_type == "real_estate" and is_untradable_position(dict(raw)),
            is_untradable=is_untradable_position(dict(raw)),
        )
        canonical.append(record)
        portfolio_rows.append((record, raw))
        if symbol:
            portfolio_by_symbol[symbol] = record

    matched_profile_ids: list[str] = []
    claimed_portfolio_keys: set[str] = set()
    portfolio_value_adjustment = 0.0
    for index, raw in enumerate(profile_assets or ()):
        if not isinstance(raw, Mapping):
            continue
        profile_id = str(raw.get("id") or f"profile-{index}").strip()
        gross_value = _money(raw.get("current_value_usd", raw.get("current_value")))
        if gross_value <= 0:
            continue
        ownership_fraction = _ownership_fraction(raw.get("ownership_pct"))
        household_value = round(gross_value * ownership_fraction, 2)
        kind = _asset_kind(raw.get("asset_type"), None)
        explicit_symbol = _clean_symbol(raw.get("portfolio_symbol"))
        match = portfolio_by_symbol.get(explicit_symbol) if explicit_symbol else None
        if match is not None and not match.is_untradable:
            match = None
        if match is None:
            match = _legacy_match(
                raw,
                value=gross_value,
                kind=kind,
                candidates=[
                    record
                    for record, _ in portfolio_rows
                    if record.is_untradable and record.key not in claimed_portfolio_keys
                ],
            )
        if match is not None:
            claimed_portfolio_keys.add(match.key)
            matched_profile_ids.append(profile_id)
            adjusted = replace(
                match,
                value_usd=round(match.value_usd * ownership_fraction, 2),
                profile_id=profile_id,
            )
            portfolio_value_adjustment += adjusted.value_usd - match.value_usd
            canonical[canonical.index(match)] = adjusted
            if explicit_symbol:
                portfolio_by_symbol[explicit_symbol] = adjusted
            continue

        canonical.append(
            CanonicalHouseholdAsset(
                key=f"profile:{profile_id}",
                label=str(raw.get("label") or "Asset").strip(),
                asset_type=kind,
                value_usd=household_value,
                source="profile",
                portfolio_symbol=explicit_symbol or None,
                profile_id=profile_id,
                is_housing=kind == "real_estate",
                is_untradable=True,
            )
        )

    return HouseholdAssetReconciliation(
        assets=tuple(canonical),
        matched_profile_ids=tuple(matched_profile_ids),
        portfolio_value_adjustment_usd=round(portfolio_value_adjustment, 2),
    )


def _legacy_match(
    raw: Mapping[str, Any],
    *,
    value: float,
    kind: str,
    candidates: list[CanonicalHouseholdAsset],
) -> CanonicalHouseholdAsset | None:
    compatible = [candidate for candidate in candidates if candidate.asset_type == kind]
    if not compatible:
        return None

    label = _normalized_label(raw.get("label"))
    same_label = [candidate for candidate in compatible if _normalized_label(candidate.label) == label and label]
    if len(same_label) == 1:
        return same_label[0]

    close_value = [candidate for candidate in compatible if _same_value(candidate.value_usd, value)]
    return close_value[0] if len(close_value) == 1 else None


def _same_value(left: float, right: float) -> bool:
    tolerance = max(1.0, max(abs(left), abs(right)) * 0.001)
    return abs(left - right) <= tolerance


def _asset_kind(asset_type: Any, asset_class: Any) -> str:
    type_text = str(asset_type or "").strip().lower()
    class_text = str(asset_class or "").strip().lower()
    if type_text in _REAL_ESTATE_TYPES:
        return "real_estate"
    if type_text in _VEHICLE_TYPES:
        return "vehicle"
    if type_text in {"jewelry", "equipment", "collectible"}:
        return type_text
    if not type_text and class_text in _REAL_ESTATE_TYPES:
        return "real_estate"
    return type_text or class_text or "other"


def _clean_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalized_label(value: Any) -> str:
    return " ".join(_LABEL_TOKEN.findall(str(value or "").lower()))


def _money(value: Any) -> float:
    try:
        return round(float(value or 0.0), 2)
    except (TypeError, ValueError):
        return 0.0


def _ownership_fraction(value: Any) -> float:
    try:
        percentage = float(100.0 if value is None else value)
    except (TypeError, ValueError):
        percentage = 100.0
    return min(max(percentage, 0.0), 100.0) / 100.0

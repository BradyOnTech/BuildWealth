"""Portfolio drift/risk alert calculations from holdings concentration and allocation thresholds.

Concentration is a statement about INVESTABLE money. A primary residence (or
any personal/illiquid/custom-valued position) cannot be trimmed or rebalanced,
so it is excluded from every concentration percentage here — housing exposure
is real, but it is not concentration a person can trade away.
"""

from __future__ import annotations

from typing import Any, Literal

from buildwealth_orchestrator.services.portfolio_rebalancing import is_untradable_position
from buildwealth_orchestrator.services.value_coercion import safe_float, utc_now_iso

RISK_ALERTS_SCHEMA_VERSION = 1

# Rule defaults are conservative portfolio-review starting points:
# - account concentration max around 50%
# - asset-class cluster guardrail around 82%
# - regional cluster guardrail around 69%
DEFAULT_RISK_THRESHOLDS: dict[str, float] = {
    "single_holding_max_pct": 25.0,
    "top3_holdings_max_pct": 60.0,
    "account_max_pct": 50.0,
    "asset_class_max_pct": 82.0,
    "sector_max_pct": 35.0,
    "region_max_pct": 69.0,
    "hhi_max": 0.2,
    "effective_positions_min": 5.0,
}

_PERCENT_THRESHOLD_KEYS = {
    "single_holding_max_pct",
    "top3_holdings_max_pct",
    "account_max_pct",
    "asset_class_max_pct",
    "sector_max_pct",
    "region_max_pct",
}

_THRESHOLD_BOUNDS: dict[str, tuple[float, float]] = {
    "single_holding_max_pct": (0.0, 100.0),
    "top3_holdings_max_pct": (0.0, 100.0),
    "account_max_pct": (0.0, 100.0),
    "asset_class_max_pct": (0.0, 100.0),
    "sector_max_pct": (0.0, 100.0),
    "region_max_pct": (0.0, 100.0),
    "hhi_max": (0.01, 1.0),
    "effective_positions_min": (1.0, 100.0),
}


def _normalize_threshold_value(key: str, value: Any, fallback: float) -> float:
    raw = safe_float(value, fallback)
    minimum, maximum = _THRESHOLD_BOUNDS[key]
    bounded = max(minimum, min(maximum, raw))
    precision = 3 if key == "hhi_max" else 2
    return round(bounded, precision)


def normalize_risk_thresholds(raw_thresholds: Any) -> dict[str, float]:
    candidate = raw_thresholds if isinstance(raw_thresholds, dict) else {}
    return {
        key: _normalize_threshold_value(key, candidate.get(key), default)
        for key, default in DEFAULT_RISK_THRESHOLDS.items()
    }


def apply_investment_policy_thresholds(
    raw_thresholds: Any,
    investment_policy: Any,
) -> dict[str, float]:
    """Resolve portfolio monitoring limits from the confirmed Profile policy."""
    merged = normalize_risk_thresholds(raw_thresholds)
    policy = investment_policy if isinstance(investment_policy, dict) else {}
    if policy.get("max_single_symbol_exposure_pct") is not None:
        merged["single_holding_max_pct"] = safe_float(
            policy.get("max_single_symbol_exposure_pct"),
            merged["single_holding_max_pct"],
        )
    if policy.get("max_sector_exposure_pct") is not None:
        merged["sector_max_pct"] = safe_float(
            policy.get("max_sector_exposure_pct"),
            merged["sector_max_pct"],
        )
    asset_class_limits = policy.get("max_asset_class_exposure_pct")
    if isinstance(asset_class_limits, dict):
        limits = [safe_float(value, 0.0) for value in asset_class_limits.values()]
        positive_limits = [value for value in limits if value > 0]
        if positive_limits:
            merged["asset_class_max_pct"] = max(positive_limits)
    return normalize_risk_thresholds(merged)


def calculate_profile_aware_portfolio_risk_alerts(
    holdings_payload: dict[str, Any],
    investment_policy: dict[str, Any] | None,
) -> dict[str, Any]:
    """Calculate one canonical risk view using confirmed Profile guardrails."""
    stored_policy = (
        holdings_payload.get("risk_policy")
        if isinstance(holdings_payload.get("risk_policy"), dict)
        else {}
    )
    thresholds = apply_investment_policy_thresholds(
        stored_policy.get("thresholds"),
        investment_policy,
    )
    return calculate_portfolio_risk_alerts(
        holdings=holdings_payload.get("holdings", {}),
        account_totals=holdings_payload.get("account_totals"),
        allocation_breakdowns=holdings_payload.get("allocation_breakdowns"),
        thresholds=thresholds,
    )


def _severity_from_drift(metric: str, drift: float) -> Literal["low", "medium", "high"]:
    magnitude = abs(drift)
    if metric == "hhi":
        if magnitude >= 0.08:
            return "high"
        if magnitude >= 0.03:
            return "medium"
        return "low"
    if metric == "effective_positions":
        if magnitude >= 4:
            return "high"
        if magnitude >= 2:
            return "medium"
        return "low"
    if magnitude >= 12:
        return "high"
    if magnitude >= 5:
        return "medium"
    return "low"


def _max_threshold_alert(
    *,
    alert_id: str,
    category: str,
    label: str,
    metric: str,
    observed: float | None,
    threshold: float,
    unit: str,
    context: dict[str, Any] | None = None,
    recommendation: str,
    watch_multiplier: float = 0.9,
) -> dict[str, Any] | None:
    if observed is None:
        return None
    watch_floor = threshold * watch_multiplier
    if observed > threshold:
        state = "breach"
    elif observed >= watch_floor:
        state = "watch"
    else:
        return None

    drift = round(observed - threshold, 3 if unit == "ratio" else 2)
    severity: Literal["low", "medium", "high"] = (
        _severity_from_drift(metric, drift) if state == "breach" else "low"
    )
    return {
        "id": alert_id,
        "category": category,
        "state": state,
        "severity": severity,
        "label": label,
        "metric": metric,
        "direction": "max",
        "unit": unit,
        "observed": round(observed, 3 if unit == "ratio" else 2),
        "threshold": round(threshold, 3 if unit == "ratio" else 2),
        "drift_from_threshold": drift,
        "context": context or {},
        "message": (
            f"{label} is {round(observed, 3 if unit == 'ratio' else 2)}"
            f"{'%' if unit == 'pct' else ''} against max {round(threshold, 3 if unit == 'ratio' else 2)}"
            f"{'%' if unit == 'pct' else ''}."
        ),
        "recommendation": recommendation,
    }


def _min_threshold_alert(
    *,
    alert_id: str,
    category: str,
    label: str,
    metric: str,
    observed: float | None,
    threshold: float,
    unit: str,
    context: dict[str, Any] | None = None,
    recommendation: str,
    watch_multiplier: float = 1.1,
) -> dict[str, Any] | None:
    if observed is None:
        return None
    watch_ceiling = threshold * watch_multiplier
    if observed < threshold:
        state = "breach"
    elif observed <= watch_ceiling:
        state = "watch"
    else:
        return None

    drift = round(observed - threshold, 3 if unit == "ratio" else 2)
    severity: Literal["low", "medium", "high"] = (
        _severity_from_drift(metric, drift) if state == "breach" else "low"
    )
    return {
        "id": alert_id,
        "category": category,
        "state": state,
        "severity": severity,
        "label": label,
        "metric": metric,
        "direction": "min",
        "unit": unit,
        "observed": round(observed, 3 if unit == "ratio" else 2),
        "threshold": round(threshold, 3 if unit == "ratio" else 2),
        "drift_from_threshold": drift,
        "context": context or {},
        "message": (
            f"{label} is {round(observed, 3 if unit == 'ratio' else 2)}"
            f"{'%' if unit == 'pct' else ''} against min {round(threshold, 3 if unit == 'ratio' else 2)}"
            f"{'%' if unit == 'pct' else ''}."
        ),
        "recommendation": recommendation,
    }


def _largest_bucket(rows: Any) -> tuple[str | None, float | None]:
    if not isinstance(rows, list) or not rows:
        return None, None
    top = rows[0] if isinstance(rows[0], dict) else None
    if not isinstance(top, dict):
        return None, None
    label = str(top.get("key") or "").strip() or None
    pct = safe_float(top.get("allocation_pct"), None)
    if pct is None:
        return label, None
    return label, round(pct, 2)


def _largest_dimension_from_holdings(
    holding_rows: list[dict[str, Any]],
    *,
    field: str,
    fallback_label: str,
) -> tuple[str | None, float | None]:
    totals: dict[str, float] = {}
    total_value = 0.0
    for row in holding_rows:
        value = safe_float(row.get("current_value"), 0.0)
        if value <= 0:
            continue
        key = str(row.get(field) or "").strip() or fallback_label
        totals[key] = totals.get(key, 0.0) + value
        total_value += value

    if not totals or total_value <= 0:
        return None, None

    top_key, top_value = max(totals.items(), key=lambda item: item[1])
    return top_key, round((top_value / total_value) * 100, 2)


def calculate_portfolio_risk_alerts(
    *,
    holdings: dict[str, dict[str, Any]] | list[dict[str, Any]],
    account_totals: dict[str, dict[str, Any]] | None,
    allocation_breakdowns: dict[str, list[dict[str, Any]]] | None,
    thresholds: dict[str, Any] | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    normalized_thresholds = normalize_risk_thresholds(thresholds)

    if isinstance(holdings, dict):
        holding_rows = [row for row in holdings.values() if isinstance(row, dict)]
    elif isinstance(holdings, list):
        holding_rows = [row for row in holdings if isinstance(row, dict)]
    else:
        holding_rows = []

    # Housing-vs-investment scoping: only investable rows enter concentration
    # math. total_market_value stays full-portfolio for other consumers.
    investable_rows = [row for row in holding_rows if not is_untradable_position(row)]
    total_market_value = round(
        sum(
            safe_float(row.get("current_value"), 0.0)
            for row in holding_rows
            if safe_float(row.get("current_value"), 0.0) > 0
        ),
        2,
    )

    # A fund held in three accounts is still ONE concentration: aggregate by
    # symbol before ranking, or per-account rows understate real exposure.
    value_by_symbol: dict[str, float] = {}
    for row in investable_rows:
        value = safe_float(row.get("current_value"), 0.0)
        if value <= 0:
            continue
        symbol = str(row.get("symbol") or "").strip().upper() or "UNKNOWN"
        value_by_symbol[symbol] = value_by_symbol.get(symbol, 0.0) + value
    ranked_positions = sorted(
        [{"symbol": symbol, "value": round(value, 2)} for symbol, value in value_by_symbol.items()],
        key=lambda item: item["value"],
        reverse=True,
    )
    investable_market_value = round(sum(item["value"] for item in ranked_positions), 2)

    top_wrapper_symbol = ranked_positions[0]["symbol"] if ranked_positions else None
    top_wrapper_pct = (
        round((ranked_positions[0]["value"] / investable_market_value) * 100, 2)
        if ranked_positions and investable_market_value > 0
        else None
    )
    top3_wrapper_pct = (
        round((sum(item["value"] for item in ranked_positions[:3]) / investable_market_value) * 100, 2)
        if ranked_positions and investable_market_value > 0
        else None
    )

    lookthrough_report: dict[str, Any] = {}
    try:
        from buildwealth_orchestrator.services.fund_composition import FundCompositionService

        lookthrough_report = FundCompositionService().look_through_report({"holdings": investable_rows})
    except (OSError, TypeError, ValueError):
        lookthrough_report = {}
    coverage = lookthrough_report.get("coverage") if isinstance(lookthrough_report, dict) else {}
    covered_fund_value = safe_float(
        coverage.get("covered_value_usd") if isinstance(coverage, dict) else None,
        0.0,
    )
    economic_positions = (
        lookthrough_report.get("effective_company_exposure")
        if isinstance(lookthrough_report.get("effective_company_exposure"), list)
        else []
    )
    uses_lookthrough = covered_fund_value > 0 and bool(economic_positions)
    top_holding_symbol = (
        str(economic_positions[0].get("symbol") or "").strip().upper() or None
        if uses_lookthrough and isinstance(economic_positions[0], dict)
        else top_wrapper_symbol
    )
    top_holding_pct = (
        safe_float(economic_positions[0].get("exposure_pct"), None)
        if uses_lookthrough and isinstance(economic_positions[0], dict)
        else top_wrapper_pct
    )
    top3_holdings_pct = (
        round(
            sum(
                safe_float(item.get("exposure_pct"), 0.0)
                for item in economic_positions[:3]
                if isinstance(item, dict)
            ),
            2,
        )
        if uses_lookthrough
        else top3_wrapper_pct
    )

    if investable_market_value > 0 and not uses_lookthrough:
        hhi = round(sum((item["value"] / investable_market_value) ** 2 for item in ranked_positions), 4)
        effective_positions = round((1 / hhi) if hhi > 0 else 0.0, 2)
    else:
        hhi = None
        effective_positions = None

    # account_totals arrive pre-summed (holdings + cash), so the untradable
    # slice has to be backed out per account; an account that only holds the
    # house drops out of the concentration comparison entirely.
    untradable_value_by_account: dict[str, float] = {}
    for row in holding_rows:
        if not is_untradable_position(row):
            continue
        value = safe_float(row.get("current_value"), 0.0)
        if value <= 0:
            continue
        account_id = str(row.get("account") or "").strip()
        if account_id:
            untradable_value_by_account[account_id] = untradable_value_by_account.get(account_id, 0.0) + value

    account_leader_id: str | None = None
    account_leader_pct: float | None = None
    investable_account_count = 0
    if isinstance(account_totals, dict) and account_totals:
        account_rows = []
        for account_id, values in account_totals.items():
            if not isinstance(values, dict):
                continue
            total_value = safe_float(values.get("total_value"), 0.0)
            investable_value = total_value - untradable_value_by_account.get(str(account_id), 0.0)
            if investable_value <= 0:
                continue
            account_rows.append((str(account_id), investable_value))
        investable_account_count = len(account_rows)
        if account_rows:
            account_total_value = sum(value for _, value in account_rows)
            account_rows.sort(key=lambda item: item[1], reverse=True)
            account_leader_id = account_rows[0][0]
            if account_total_value > 0:
                account_leader_pct = round((account_rows[0][1] / account_total_value) * 100, 2)

    breakdowns = allocation_breakdowns if isinstance(allocation_breakdowns, dict) else {}
    largest_asset_class, largest_asset_class_pct = _largest_dimension_from_holdings(
        investable_rows,
        field="asset_class",
        fallback_label="Unclassified",
    )
    largest_sector, largest_sector_pct = _largest_dimension_from_holdings(
        investable_rows,
        field="sector",
        fallback_label="Unknown",
    )
    largest_region, largest_region_pct = _largest_dimension_from_holdings(
        investable_rows,
        field="region",
        fallback_label="Unknown",
    )
    if uses_lookthrough:
        sector_rows = lookthrough_report.get("sector_exposure")
        region_rows = lookthrough_report.get("region_exposure")
        if isinstance(sector_rows, list) and sector_rows and isinstance(sector_rows[0], dict):
            largest_sector = str(sector_rows[0].get("key") or "").strip() or largest_sector
            largest_sector_pct = safe_float(sector_rows[0].get("exposure_pct"), largest_sector_pct)
        if isinstance(region_rows, list) and region_rows and isinstance(region_rows[0], dict):
            largest_region = str(region_rows[0].get("key") or "").strip() or largest_region
            largest_region_pct = safe_float(region_rows[0].get("exposure_pct"), largest_region_pct)
    # The breakdown fallback covers callers that supplied no holdings detail
    # at all. When holdings exist, breakdowns stay unused: they are computed
    # over the full portfolio (house included), the wrong base for this lens.
    if not holding_rows:
        if largest_asset_class is None:
            largest_asset_class, largest_asset_class_pct = _largest_bucket(breakdowns.get("asset_class"))
        if largest_sector is None:
            largest_sector, largest_sector_pct = _largest_bucket(breakdowns.get("sector"))
        if largest_region is None:
            largest_region, largest_region_pct = _largest_bucket(breakdowns.get("region"))

    alerts: list[dict[str, Any]] = []

    single_alert = _max_threshold_alert(
        alert_id="single_holding_concentration",
        category="concentration",
        label="Top holding concentration",
        metric="single_holding",
        observed=top_holding_pct,
        threshold=normalized_thresholds["single_holding_max_pct"],
        unit="pct",
        context={"symbol": top_holding_symbol},
        recommendation="Trim or redirect contributions away from the largest position.",
    )
    if single_alert:
        alerts.append(single_alert)

    if uses_lookthrough and top_wrapper_pct is not None and top_wrapper_pct > normalized_thresholds["single_holding_max_pct"]:
        alerts.append(
            {
                "id": "fund_wrapper_concentration",
                "category": "lookthrough",
                "state": "watch",
                "severity": "low",
                "label": "Single fund wrapper concentration",
                "metric": "fund_wrapper",
                "direction": "max",
                "unit": "pct",
                "observed": top_wrapper_pct,
                "threshold": normalized_thresholds["single_holding_max_pct"],
                "drift_from_threshold": round(top_wrapper_pct - normalized_thresholds["single_holding_max_pct"], 2),
                "context": {
                    "symbol": top_wrapper_symbol,
                    "largest_company_symbol": top_holding_symbol,
                    "largest_company_exposure_pct": top_holding_pct,
                    "lookthrough_covered_value_usd": round(covered_fund_value, 2),
                },
                "message": (
                    f"{top_wrapper_symbol} is {top_wrapper_pct}% as a fund wrapper; "
                    f"its largest covered company exposure is {top_holding_pct}%."
                ),
                "recommendation": (
                    "Review the fund look-through before adding another fund solely to reduce the wrapper percentage."
                ),
            }
        )

    top3_alert = _max_threshold_alert(
        alert_id="top3_concentration",
        category="concentration",
        label="Top 3 holdings concentration",
        metric="top3",
        observed=top3_holdings_pct,
        threshold=normalized_thresholds["top3_holdings_max_pct"],
        unit="pct",
        context={
            "symbols": (
                [str(item.get("symbol") or "") for item in economic_positions[:3] if isinstance(item, dict)]
                if uses_lookthrough
                else [item["symbol"] for item in ranked_positions[:3]]
            )
        },
        recommendation="Rebalance into underweight positions or broaden index exposure.",
    )
    if top3_alert:
        alerts.append(top3_alert)

    # More than one INVESTABLE account required: a brokerage next to a
    # house-only "account" is not an account-concentration problem.
    if account_leader_pct is not None and investable_market_value > 0 and investable_account_count > 1:
        account_alert = _max_threshold_alert(
            alert_id="account_cluster_risk",
            category="allocation",
            label="Largest account concentration",
            metric="account",
            observed=account_leader_pct,
            threshold=normalized_thresholds["account_max_pct"],
            unit="pct",
            context={"account_id": account_leader_id},
            recommendation="Shift new capital toward underweight accounts over the next contribution cycle.",
        )
        if account_alert:
            alerts.append(account_alert)

    # investable_market_value > 0 guards the no-holdings fallback path: with a
    # zero investable base, every concentration percentage is meaningless.
    if largest_asset_class_pct is not None and investable_market_value > 0:
        asset_class_alert = _max_threshold_alert(
            alert_id="asset_class_cluster_risk",
            category="allocation",
            label="Largest asset-class concentration",
            metric="asset_class",
            observed=largest_asset_class_pct,
            threshold=normalized_thresholds["asset_class_max_pct"],
            unit="pct",
            context={"asset_class": largest_asset_class},
            recommendation="Diversify into complementary asset classes to reduce cluster risk.",
        )
        if asset_class_alert:
            alerts.append(asset_class_alert)

    if largest_sector_pct is not None and investable_market_value > 0:
        sector_alert = _max_threshold_alert(
            alert_id="sector_cluster_risk",
            category="allocation",
            label="Largest sector concentration",
            metric="sector",
            observed=largest_sector_pct,
            threshold=normalized_thresholds["sector_max_pct"],
            unit="pct",
            context={"sector": largest_sector},
            recommendation="Use new purchases to broaden sector exposure and lower single-sector dependence.",
        )
        if sector_alert:
            alerts.append(sector_alert)

    if largest_region_pct is not None and investable_market_value > 0:
        region_alert = _max_threshold_alert(
            alert_id="regional_cluster_risk",
            category="allocation",
            label="Largest region concentration",
            metric="region",
            observed=largest_region_pct,
            threshold=normalized_thresholds["region_max_pct"],
            unit="pct",
            context={"region": largest_region},
            recommendation="Add non-dominant regional exposure to reduce geographic concentration risk.",
        )
        if region_alert:
            alerts.append(region_alert)

    hhi_alert = _max_threshold_alert(
        alert_id="hhi_concentration",
        category="concentration",
        label="Herfindahl concentration index",
        metric="hhi",
        observed=hhi,
        threshold=normalized_thresholds["hhi_max"],
        unit="ratio",
        recommendation="Increase the number of meaningful positions to reduce portfolio concentration.",
    )
    if hhi_alert:
        alerts.append(hhi_alert)

    effective_positions_alert = _min_threshold_alert(
        alert_id="effective_positions",
        category="concentration",
        label="Effective number of positions",
        metric="effective_positions",
        observed=effective_positions,
        threshold=normalized_thresholds["effective_positions_min"],
        unit="count",
        recommendation="Broaden exposure with uncorrelated assets to improve diversification depth.",
    )
    if effective_positions_alert:
        alerts.append(effective_positions_alert)

    severity_rank = {"high": 3, "medium": 2, "low": 1}
    state_rank = {"breach": 2, "watch": 1}
    alerts.sort(
        key=lambda item: (
            state_rank.get(str(item.get("state")), 0),
            severity_rank.get(str(item.get("severity")), 0),
            abs(safe_float(item.get("drift_from_threshold"), 0.0)),
        ),
        reverse=True,
    )

    breach_count = sum(1 for alert in alerts if alert.get("state") == "breach")
    watch_count = sum(1 for alert in alerts if alert.get("state") == "watch")
    high_count = sum(1 for alert in alerts if alert.get("severity") == "high" and alert.get("state") == "breach")
    medium_count = sum(1 for alert in alerts if alert.get("severity") == "medium" and alert.get("state") == "breach")
    low_count = sum(1 for alert in alerts if alert.get("severity") == "low" and alert.get("state") == "breach")

    if high_count > 0:
        status = "critical"
    elif breach_count > 0 or watch_count > 0:
        status = "warning"
    else:
        status = "ok"

    metrics = {
        # Full-portfolio value (house included) for consumers that need the
        # household total; concentration percentages use the investable base.
        "total_market_value": total_market_value,
        "investable_market_value": investable_market_value,
        "positions_count": len(ranked_positions),
        "top_wrapper_symbol": top_wrapper_symbol,
        "top_wrapper_pct": top_wrapper_pct,
        "top3_wrapper_pct": top3_wrapper_pct,
        "lookthrough_covered_value_usd": round(covered_fund_value, 2),
        "top_holding_symbol": top_holding_symbol,
        "top_holding_pct": top_holding_pct,
        "top3_holdings_pct": top3_holdings_pct,
        "herfindahl_index": hhi,
        "effective_positions": effective_positions,
        "largest_account_id": account_leader_id,
        "largest_account_pct": account_leader_pct,
        "largest_asset_class": largest_asset_class,
        "largest_asset_class_pct": largest_asset_class_pct,
        "largest_sector": largest_sector,
        "largest_sector_pct": largest_sector_pct,
        "largest_region": largest_region,
        "largest_region_pct": largest_region_pct,
    }

    return {
        "schema_version": RISK_ALERTS_SCHEMA_VERSION,
        "generated_at": generated_at or utc_now_iso(),
        "status": status,
        "breach_count": breach_count,
        "watch_count": watch_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
        "thresholds": normalized_thresholds,
        "metrics": metrics,
        "alerts": alerts,
    }

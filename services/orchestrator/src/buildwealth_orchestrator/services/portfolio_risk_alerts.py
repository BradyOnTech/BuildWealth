"""Portfolio drift/risk alert calculations from holdings concentration and allocation thresholds."""

from __future__ import annotations

from typing import Any, Literal

from buildwealth_orchestrator.services.service_utils import safe_float, utc_now_iso

RISK_ALERTS_SCHEMA_VERSION = 1

# Rule defaults adapted from Ghostfolio x-ray patterns (MIT):
# - account concentration max around 50%
# - equity cluster guardrail around 82%
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

    ranked_positions = sorted(
        [
            {
                "symbol": str(row.get("symbol") or "").strip().upper() or "UNKNOWN",
                "value": round(safe_float(row.get("current_value"), 0.0), 2),
            }
            for row in holding_rows
            if safe_float(row.get("current_value"), 0.0) > 0
        ],
        key=lambda item: item["value"],
        reverse=True,
    )
    total_market_value = round(sum(item["value"] for item in ranked_positions), 2)

    top_holding_symbol = ranked_positions[0]["symbol"] if ranked_positions else None
    top_holding_pct = (
        round((ranked_positions[0]["value"] / total_market_value) * 100, 2)
        if ranked_positions and total_market_value > 0
        else None
    )
    top3_holdings_pct = (
        round((sum(item["value"] for item in ranked_positions[:3]) / total_market_value) * 100, 2)
        if ranked_positions and total_market_value > 0
        else None
    )

    if total_market_value > 0:
        hhi = round(sum((item["value"] / total_market_value) ** 2 for item in ranked_positions), 4)
        effective_positions = round((1 / hhi) if hhi > 0 else 0.0, 2)
    else:
        hhi = None
        effective_positions = None

    account_leader_id: str | None = None
    account_leader_pct: float | None = None
    if isinstance(account_totals, dict) and account_totals:
        account_rows = []
        for account_id, values in account_totals.items():
            if not isinstance(values, dict):
                continue
            total_value = safe_float(values.get("total_value"), 0.0)
            if total_value <= 0:
                continue
            account_rows.append((str(account_id), total_value))
        if account_rows:
            account_total_value = sum(value for _, value in account_rows)
            account_rows.sort(key=lambda item: item[1], reverse=True)
            account_leader_id = account_rows[0][0]
            if account_total_value > 0:
                account_leader_pct = round((account_rows[0][1] / account_total_value) * 100, 2)

    breakdowns = allocation_breakdowns if isinstance(allocation_breakdowns, dict) else {}
    largest_asset_class, largest_asset_class_pct = _largest_dimension_from_holdings(
        holding_rows,
        field="asset_class",
        fallback_label="Unclassified",
    )
    largest_sector, largest_sector_pct = _largest_dimension_from_holdings(
        holding_rows,
        field="sector",
        fallback_label="Unknown",
    )
    largest_region, largest_region_pct = _largest_dimension_from_holdings(
        holding_rows,
        field="region",
        fallback_label="Unknown",
    )
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

    top3_alert = _max_threshold_alert(
        alert_id="top3_concentration",
        category="concentration",
        label="Top 3 holdings concentration",
        metric="top3",
        observed=top3_holdings_pct,
        threshold=normalized_thresholds["top3_holdings_max_pct"],
        unit="pct",
        context={"symbols": [item["symbol"] for item in ranked_positions[:3]]},
        recommendation="Rebalance into underweight positions or broaden index exposure.",
    )
    if top3_alert:
        alerts.append(top3_alert)

    if account_leader_pct is not None and isinstance(account_totals, dict) and len(account_totals) > 1:
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

    if largest_asset_class_pct is not None:
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

    if largest_sector_pct is not None:
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

    if largest_region_pct is not None:
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
        "total_market_value": total_market_value,
        "positions_count": len(ranked_positions),
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

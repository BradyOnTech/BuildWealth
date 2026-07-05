from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from buildwealth_orchestrator.services.portfolio_diversification import build_diversification_payload
from buildwealth_orchestrator.services.portfolio_fees import build_portfolio_fee_payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _sanitize_warning(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "BuildWealth native analytics uses local" in text:
        return ""
    replacements = {
        "Portfolio benchmark": "Benchmark service",
        "Portfolio attribution": "Attribution service",
        "portfolio_analysis": "analytics",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _warning_list(payload: dict[str, Any]) -> list[str]:
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    return [text for item in warnings if (text := _sanitize_warning(item))]


def _performance_payload(holdings_payload: dict[str, Any]) -> dict[str, Any]:
    performance = holdings_payload.get("performance") if isinstance(holdings_payload.get("performance"), dict) else {}
    return {
        "as_of": performance.get("as_of") or holdings_payload.get("updated_at"),
        "total_value": _safe_float(holdings_payload.get("total_portfolio_value") or holdings_payload.get("total_value")),
        "total_cash": _safe_float(holdings_payload.get("total_cash")),
        "net_performance": _safe_float(holdings_payload.get("net_performance")),
        "net_performance_pct": _safe_float(holdings_payload.get("net_performance_pct")),
        "ending_value": _safe_float(performance.get("ending_value")),
        "net_contributions": _safe_float(performance.get("net_contributions")),
        "gross_contributions": _safe_float(performance.get("gross_contributions")),
        "price_return_usd": _safe_float(performance.get("price_return_usd")),
        "income_return_usd": _safe_float(performance.get("income_return_usd")),
        "realized_gains_usd": _safe_float(performance.get("realized_gains_usd")),
        "income_received_usd": _safe_float(performance.get("income_received_usd")),
        "fees_paid_usd": _safe_float(performance.get("fees_paid_usd")),
        "total_return_usd": _safe_float(performance.get("total_return_usd")),
        "twr_return_pct": _safe_float(performance.get("twr_return_pct")),
        "twr_annualized_return_pct": _safe_float(performance.get("twr_annualized_return_pct")),
        "xirr_annualized_return_pct": _safe_float(performance.get("xirr_annualized_return_pct")),
    }


def _period_payload(period: str, limit: int) -> dict[str, Any]:
    labels = {
        "today": "Today",
        "wtd": "WTD",
        "mtd": "MTD",
        "ytd": "YTD",
        "1y": "1Y",
        "5y": "5Y",
        "max": "Max",
    }
    normalized = str(period or "1y").strip().lower()
    if normalized not in labels:
        normalized = "1y"
    return {
        "id": normalized,
        "label": labels[normalized],
        "snapshot_limit": int(limit),
        "options": [{"id": key, "label": value} for key, value in labels.items()],
    }


def _benchmark_payload(benchmark_response: Any = None, error: str = "") -> dict[str, Any]:
    if error:
        return {
            "status": "unavailable",
            "message": error,
            "symbols": [],
            "rows": [],
            "warnings": [],
        }
    payload = _as_dict(benchmark_response)
    if not payload:
        return {
            "status": "unavailable",
            "message": "Benchmark comparison is unavailable.",
            "symbols": [],
            "rows": [],
            "warnings": [],
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    symbols = [str(item).upper() for item in payload.get("benchmark_symbols", []) if str(item).strip()]
    benchmark_returns = summary.get("benchmark_return_pct_by_symbol") if isinstance(summary.get("benchmark_return_pct_by_symbol"), dict) else {}
    alpha = summary.get("alpha_pct_by_symbol") if isinstance(summary.get("alpha_pct_by_symbol"), dict) else {}
    rows = [
        {
            "symbol": symbol,
            "benchmark_return_pct": _safe_float(benchmark_returns.get(symbol)),
            "alpha_pct": _safe_float(alpha.get(symbol)),
        }
        for symbol in symbols
    ]
    return {
        "status": "ready" if rows else "unavailable",
        "message": "",
        "symbols": symbols,
        "start_date": payload.get("start_date"),
        "end_date": payload.get("end_date"),
        "portfolio_return_pct": _safe_float(summary.get("portfolio_return_pct")),
        "tracking_error_pct": _safe_float(summary.get("tracking_error_pct")),
        "max_drawdown_pct": _safe_float(summary.get("max_drawdown_pct")),
        "rows": rows,
        "series": payload.get("series") if isinstance(payload.get("series"), list) else [],
        "warnings": _warning_list(payload),
    }


def _attribution_payload(attribution_response: Any = None, error: str = "") -> dict[str, Any]:
    if error:
        return {
            "status": "unavailable",
            "message": error,
            "contributors": [],
            "detractors": [],
            "warnings": [],
        }
    payload = _as_dict(attribution_response)
    if not payload:
        return {
            "status": "unavailable",
            "message": "Attribution is unavailable.",
            "contributors": [],
            "detractors": [],
            "warnings": [],
        }
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "status": "ready",
        "message": "",
        "as_of": payload.get("as_of"),
        "summary": {
            "portfolio_total_return": _safe_float(summary.get("portfolio_total_return_base")),
            "portfolio_total_value": _safe_float(summary.get("portfolio_total_value_base")),
            "accounted_return": _safe_float(summary.get("accounted_return_base")),
            "residual_return": _safe_float(summary.get("residual_return_base")),
            "contributors_count": int(summary.get("contributors_count") or 0),
            "detractors_count": int(summary.get("detractors_count") or 0),
        },
        "contributors": _position_rows(payload.get("contributors")),
        "detractors": _position_rows(payload.get("detractors")),
        "warnings": _warning_list(payload),
    }


def _position_rows(raw_rows: Any) -> list[dict[str, Any]]:
    rows = raw_rows if isinstance(raw_rows, list) else []
    normalized: list[dict[str, Any]] = []
    for row in rows[:10]:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "name": row.get("name"),
                "asset_class": row.get("asset_class"),
                "total_return": _safe_float(row.get("total_return_base")),
                "total_return_pct": _safe_float(row.get("total_return_pct")),
                "contribution_pct": _safe_float(row.get("contribution_pct")),
                "allocation_pct": _safe_float(row.get("allocation_pct")),
            }
        )
    return normalized


def _risk_explanations(holdings_payload: dict[str, Any]) -> dict[str, Any]:
    risk = holdings_payload.get("risk_alerts") if isinstance(holdings_payload.get("risk_alerts"), dict) else {}
    metrics = risk.get("metrics") if isinstance(risk.get("metrics"), dict) else {}
    alerts = risk.get("alerts") if isinstance(risk.get("alerts"), list) else []
    breakdowns = holdings_payload.get("allocation_breakdowns") if isinstance(holdings_payload.get("allocation_breakdowns"), dict) else {}

    rows = [
        _risk_row(
            key="concentration",
            label="Largest holding",
            value=metrics.get("top_holding_pct"),
            context=metrics.get("top_holding_symbol"),
            plain="One investment is taking up this share of the portfolio.",
        ),
        _risk_row(
            key="account",
            label="Largest account",
            value=metrics.get("largest_account_pct"),
            context=metrics.get("largest_account_id"),
            plain="One account holds this share of total account value.",
        ),
        _risk_row(
            key="allocation",
            label="Largest investment type",
            value=metrics.get("largest_asset_class_pct"),
            context=metrics.get("largest_asset_class"),
            plain="One broad investment type is carrying this share.",
        ),
        _risk_row(
            key="sector",
            label="Largest sector",
            value=metrics.get("largest_sector_pct"),
            context=metrics.get("largest_sector"),
            plain="One business sector is carrying this share.",
        ),
        _risk_row(
            key="region",
            label="Largest region",
            value=metrics.get("largest_region_pct"),
            context=metrics.get("largest_region"),
            plain="One country or region is carrying this share.",
        ),
        {
            "key": "spread",
            "label": "Portfolio spread",
            "value": _safe_float(metrics.get("effective_positions")),
            "context": "effective positions",
            "plain": "A higher number means risk is spread across more meaningful positions.",
            "state": _alert_state(alerts, "effective_positions"),
        },
    ]
    return {
        "status": risk.get("status") or "unknown",
        "breach_count": int(risk.get("breach_count") or 0),
        "watch_count": int(risk.get("watch_count") or 0),
        "rows": [row for row in rows if row.get("value") is not None],
        "alerts": alerts[:8],
        "breakdowns": {
            key: value[:6] if isinstance(value, list) else []
            for key, value in breakdowns.items()
            if key in {"asset_class", "sector", "region"}
        },
    }


def _risk_row(*, key: str, label: str, value: Any, context: Any, plain: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": _safe_float(value),
        "context": str(context or "").strip(),
        "plain": plain,
    }


def _alert_state(alerts: list[Any], metric: str) -> str:
    for alert in alerts:
        if isinstance(alert, dict) and alert.get("metric") == metric:
            return str(alert.get("state") or "")
    return ""


def build_portfolio_analytics_payload(
    *,
    holdings_payload: dict[str, Any],
    benchmark_response: Any = None,
    benchmark_error: str = "",
    attribution_response: Any = None,
    attribution_error: str = "",
    period: str = "1y",
    snapshot_limit: int = 180,
    generated_at: str | None = None,
    registry_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    benchmark = _benchmark_payload(benchmark_response, benchmark_error)
    attribution = _attribution_payload(attribution_response, attribution_error)
    warnings = [*_warning_list(_as_dict(benchmark_response)), *_warning_list(_as_dict(attribution_response))]
    for error in (benchmark_error, attribution_error):
        if error:
            warnings.append(error)
    ready_count = sum(1 for item in (benchmark, attribution) if item.get("status") == "ready")
    status = "ready" if ready_count == 2 else ("partial" if ready_count else "unavailable")
    holdings_map = holdings_payload.get("holdings") if isinstance(holdings_payload.get("holdings"), dict) else {}
    return {
        "generated_at": generated_at or _utc_now_iso(),
        "status": status,
        "period": _period_payload(period, snapshot_limit),
        "performance": _performance_payload(holdings_payload),
        "benchmark": benchmark,
        "attribution": attribution,
        "risk_explanations": _risk_explanations(holdings_payload),
        "fees": build_portfolio_fee_payload(
            [row for row in holdings_map.values() if isinstance(row, dict)],
            registry_rows=registry_rows,
        ),
        "diversification": build_diversification_payload(holdings_map),
        "warnings": warnings,
    }

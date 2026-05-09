from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


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
        "Ghostfolio benchmark sidecar": "Benchmark service",
        "Ghostfolio attribution sidecar": "Attribution service",
        "Ghostfolio benchmark": "Benchmark service",
        "Ghostfolio attribution": "Attribution service",
        "ghostfolio": "analytics",
        "sidecar": "adapter",
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
        "total_return_usd": _safe_float(performance.get("total_return_usd")),
        "twr_return_pct": _safe_float(performance.get("twr_return_pct")),
        "twr_annualized_return_pct": _safe_float(performance.get("twr_annualized_return_pct")),
        "xirr_annualized_return_pct": _safe_float(performance.get("xirr_annualized_return_pct")),
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


def build_portfolio_analytics_payload(
    *,
    holdings_payload: dict[str, Any],
    benchmark_response: Any = None,
    benchmark_error: str = "",
    attribution_response: Any = None,
    attribution_error: str = "",
    generated_at: str | None = None,
) -> dict[str, Any]:
    benchmark = _benchmark_payload(benchmark_response, benchmark_error)
    attribution = _attribution_payload(attribution_response, attribution_error)
    warnings = [*_warning_list(_as_dict(benchmark_response)), *_warning_list(_as_dict(attribution_response))]
    for error in (benchmark_error, attribution_error):
        if error:
            warnings.append(error)
    ready_count = sum(1 for item in (benchmark, attribution) if item.get("status") == "ready")
    status = "ready" if ready_count == 2 else ("partial" if ready_count else "unavailable")
    return {
        "generated_at": generated_at or _utc_now_iso(),
        "status": status,
        "performance": _performance_payload(holdings_payload),
        "benchmark": benchmark,
        "attribution": attribution,
        "warnings": warnings,
    }

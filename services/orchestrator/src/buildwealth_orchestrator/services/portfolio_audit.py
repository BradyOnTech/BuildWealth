from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _recommendation_is_open(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "proposed").strip().lower() == "proposed"


def _import_review_kind(row: dict[str, Any]) -> str:
    payload = row.get("action_payload") if isinstance(row.get("action_payload"), dict) else {}
    return str(payload.get("kind") or "").strip().lower()


def _finding(
    *,
    key: str,
    category: str,
    title: str,
    detail: str,
    severity: str,
    count: int = 0,
    href: str = "",
    action_label: str = "Review",
    evidence: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": key,
        "category": category,
        "title": title,
        "detail": detail,
        "severity": severity if severity in {"high", "medium", "low"} else "medium",
        "status": "open" if count > 0 else "clear",
        "count": max(0, int(count)),
        "href": href,
        "action_label": action_label,
        "evidence": evidence or [],
    }


def build_portfolio_audit_payload(
    *,
    import_reports: list[dict[str, Any]],
    asset_registry_payload: dict[str, Any],
    accounts: list[dict[str, Any]],
    transactions: list[dict[str, Any]],
    manual_prices_payload: dict[str, Any],
    cost_basis_payload: dict[str, Any],
    recommendations: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Any]:
    reports = [report for report in import_reports if isinstance(report, dict)]
    asset_items = [
        item
        for item in asset_registry_payload.get("items", [])
        if isinstance(item, dict)
    ] if isinstance(asset_registry_payload, dict) else []
    open_import_recommendations = [
        row
        for row in recommendations
        if isinstance(row, dict)
        and _recommendation_is_open(row)
        and str(row.get("source") or "") == "import_workbench"
    ]

    unresolved_rows = sum(_safe_int(report.get("summary", {}).get("unresolved_count")) for report in reports)
    duplicate_rows = sum(_safe_int(report.get("summary", {}).get("duplicate_count")) for report in reports)
    account_review_rows = sum(_safe_int(report.get("summary", {}).get("account_review_count")) for report in reports)
    rejected_rows = sum(_safe_int(report.get("summary", {}).get("rejected_count")) for report in reports)

    asset_review_count = sum(1 for item in asset_items if item.get("quality_status") == "needs_review")
    asset_price_count = sum(1 for item in asset_items if item.get("quality_status") == "unpriced")
    account_review_inbox = sum(1 for row in open_import_recommendations if _import_review_kind(row) == "portfolio_account_review_item")
    asset_review_inbox = sum(1 for row in open_import_recommendations if _import_review_kind(row) == "asset_review_item")

    manual_prices = manual_prices_payload.get("by_symbol") if isinstance(manual_prices_payload, dict) else {}
    manual_price_count = len(manual_prices) if isinstance(manual_prices, dict) else 0
    cost_basis_methods = 0
    if isinstance(cost_basis_payload, dict):
        for key in ("by_account", "by_symbol", "by_position"):
            value = cost_basis_payload.get(key)
            if isinstance(value, dict):
                cost_basis_methods += len(value)
        if cost_basis_payload.get("global"):
            cost_basis_methods += 1

    zero_cost_positions = [
        item
        for item in asset_items
        if item.get("held")
        and str(item.get("symbol") or "").upper() != "CASH"
        and _safe_float(item.get("cost_basis")) <= 0
    ]

    findings = [
        _finding(
            key="import_rows_need_review",
            category="Imports",
            title="Imported rows need review",
            detail="Some rows from recent imports were not safe to rely on automatically.",
            severity="high",
            count=unresolved_rows,
            href="#import-sync",
            action_label="Open import reports",
            evidence=[report.get("report_id", "") for report in reports[:3] if report.get("report_id")],
        ),
        _finding(
            key="account_mapping_needed",
            category="Accounts",
            title="Imported accounts need matching",
            detail="Some imported account names need to be connected to saved BuildWealth accounts.",
            severity="medium",
            count=max(account_review_rows, account_review_inbox),
            href="#portfolio?section=accounts",
            action_label="Review accounts",
        ),
        _finding(
            key="asset_metadata_needed",
            category="Assets",
            title="Assets need review",
            detail="Some assets are missing a plain name, type, class, or other metadata needed for trustworthy reports.",
            severity="medium",
            count=max(asset_review_count, asset_review_inbox),
            href="#portfolio?section=assets",
            action_label="Review assets",
        ),
        _finding(
            key="asset_prices_needed",
            category="Prices",
            title="Assets need prices",
            detail="Some held assets are understandable, but need a price or value before portfolio totals are dependable.",
            severity="medium",
            count=asset_price_count,
            href="#portfolio?section=prices",
            action_label="Review prices",
        ),
        _finding(
            key="duplicates_skipped",
            category="Imports",
            title="Duplicate rows were skipped",
            detail="Recent imports included rows that looked like transactions already in BuildWealth.",
            severity="low",
            count=duplicate_rows,
            href="#import-sync",
            action_label="Open import reports",
        ),
        _finding(
            key="cost_basis_needed",
            category="Cost Basis",
            title="Cost basis may need review",
            detail="Some held positions have no recorded cost basis, which can weaken performance and tax views.",
            severity="low",
            count=len(zero_cost_positions),
            href="#portfolio?section=cost-basis",
            action_label="Review cost basis",
        ),
    ]
    open_findings = [finding for finding in findings if finding["status"] == "open"]
    high_count = sum(1 for finding in open_findings if finding["severity"] == "high")
    medium_count = sum(1 for finding in open_findings if finding["severity"] == "medium")
    status = "clear" if not open_findings else ("attention" if high_count else "review")

    recent_reports = [
        {
            "report_id": str(report.get("report_id") or ""),
            "created_at": str(report.get("created_at") or ""),
            "source_file_name": str((report.get("source_file") or {}).get("name") or ""),
            "imported_activities": _safe_int(report.get("imported_activities")),
            "accepted_count": _safe_int(report.get("summary", {}).get("accepted_count")),
            "rejected_count": _safe_int(report.get("summary", {}).get("rejected_count")),
            "duplicate_count": _safe_int(report.get("summary", {}).get("duplicate_count")),
            "unresolved_count": _safe_int(report.get("summary", {}).get("unresolved_count")),
            "account_review_count": _safe_int(report.get("summary", {}).get("account_review_count")),
            "href": "#import-sync",
        }
        for report in reports[:10]
    ]

    return {
        "generated_at": generated_at or _utc_now_iso(),
        "status": status,
        "summary": {
            "open_findings": len(open_findings),
            "high_findings": high_count,
            "medium_findings": medium_count,
            "low_findings": sum(1 for finding in open_findings if finding["severity"] == "low"),
            "import_reports": len(reports),
            "imported_activities": sum(_safe_int(report.get("imported_activities")) for report in reports),
            "rejected_rows": rejected_rows,
            "unresolved_import_rows": unresolved_rows,
            "duplicate_rows": duplicate_rows,
            "account_review_rows": account_review_rows,
            "asset_review_items": asset_review_count,
            "asset_price_items": asset_price_count,
            "pending_inbox_items": len(open_import_recommendations),
            "accounts": len(accounts),
            "transactions": len(transactions),
            "manual_prices": manual_price_count,
            "cost_basis_methods": cost_basis_methods,
        },
        "findings": findings,
        "recent_reports": recent_reports,
        "links": {
            "import_reports": "#import-sync",
            "accounts": "#portfolio?section=accounts",
            "assets": "#portfolio?section=assets",
            "prices": "#portfolio?section=prices",
            "cost_basis": "#portfolio?section=cost-basis",
            "inbox": "#inbox",
        },
    }

"""Portfolio review packet builders and local export store."""

from __future__ import annotations

# Export payload packing pattern written independently; design reference: Ghostfolio (see ATTRIBUTIONS.md):
# apps/api/src/app/export/export.service.ts
# Activity/account-balance aggregation approach written independently; design reference: Ghostfolio (see ATTRIBUTIONS.md):
# apps/api/src/app/activities/activities.service.ts
# apps/api/src/app/account-balance/account-balance.service.ts

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.value_coercion import (
    parse_optional_date,
    parse_optional_datetime,
    safe_float,
    safe_int,
    utc_now_iso,
)

PORTFOLIO_REVIEW_PACKET_SCHEMA_VERSION = 1


def _status_counts(rows: list[dict[str, Any]], *, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get(key) or "").strip().lower() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _summarize_transactions(
    transactions: list[dict[str, Any]],
    *,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    in_period: list[dict[str, Any]] = []
    for row in transactions:
        if not isinstance(row, dict):
            continue
        txn_date = parse_optional_date(row.get("date"))
        if txn_date is None:
            continue
        if period_start <= txn_date <= period_end:
            in_period.append(row)

    action_counts = _status_counts(in_period, key="action")
    net_cash_flow = 0.0
    for row in in_period:
        action = str(row.get("action") or "").strip().upper()
        quantity = safe_float(row.get("quantity"), 0.0)
        unit_price = safe_float(row.get("unit_price"), 0.0)
        fee = safe_float(row.get("fee"), 0.0)
        gross = abs(quantity) * abs(unit_price)
        amount = gross + abs(fee)
        if action in {"BUY", "FEE", "CASH_WITHDRAW", "TRANSFER_OUT"}:
            net_cash_flow -= amount
        elif action in {"SELL", "DIVIDEND", "INTEREST", "CASH_DEPOSIT", "TRANSFER_IN", "MERGER"}:
            net_cash_flow += max(gross - abs(fee), 0.0)

    return {
        "period_transactions_count": len(in_period),
        "period_transaction_action_counts": action_counts,
        "period_net_cash_flow_estimate_usd": round(net_cash_flow, 2),
        "sample_transactions": in_period[:30],
    }


def _summarize_audit_events(
    holdings_payload: dict[str, Any],
    *,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    lot_audit = holdings_payload.get("lot_audit") if isinstance(holdings_payload.get("lot_audit"), dict) else {}
    lot_events_raw = lot_audit.get("events") if isinstance(lot_audit.get("events"), list) else []
    corporate_payload = (
        holdings_payload.get("corporate_actions") if isinstance(holdings_payload.get("corporate_actions"), dict) else {}
    )
    corporate_events_raw = (
        corporate_payload.get("events") if isinstance(corporate_payload.get("events"), list) else []
    )

    lot_events = [event for event in lot_events_raw if isinstance(event, dict)]
    corporate_events = [event for event in corporate_events_raw if isinstance(event, dict)]

    def within(event: dict[str, Any]) -> bool:
        dt = parse_optional_date(event.get("transaction_date"))
        return dt is not None and period_start <= dt <= period_end

    lot_in_period = [event for event in lot_events if within(event)]
    corporate_in_period = [event for event in corporate_events if within(event)]

    return {
        "lot_audit_total_events": len(lot_events),
        "lot_audit_period_events": len(lot_in_period),
        "lot_audit_sample": lot_in_period[:20],
        "corporate_actions_total_events": len(corporate_events),
        "corporate_actions_period_events": len(corporate_in_period),
        "corporate_actions_sample": corporate_in_period[:20],
        "corporate_actions_summary_by_symbol": corporate_payload.get("summary_by_symbol", {}),
    }


def _summarize_snapshots(
    snapshots: list[PortfolioSnapshot],
    *,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    window = [item for item in snapshots if period_start <= item.as_of.date() <= period_end]
    if not window:
        return {
            "period_snapshots_count": 0,
            "period_start_value_usd": None,
            "period_end_value_usd": None,
            "period_delta_value_usd": None,
            "period_delta_value_pct": None,
            "window_as_of": [],
        }

    ordered = sorted(window, key=lambda item: item.as_of)
    start_value = safe_float(ordered[0].total_value_usd, 0.0)
    end_value = safe_float(ordered[-1].total_value_usd, 0.0)
    delta = end_value - start_value
    delta_pct = (delta / start_value * 100) if start_value > 0 else None
    return {
        "period_snapshots_count": len(ordered),
        "period_start_value_usd": round(start_value, 2),
        "period_end_value_usd": round(end_value, 2),
        "period_delta_value_usd": round(delta, 2),
        "period_delta_value_pct": round(delta_pct, 2) if delta_pct is not None else None,
        "window_as_of": [item.as_of.isoformat() for item in ordered[-25:]],
    }


def build_portfolio_review_packet(
    *,
    generated_at: str,
    period_days: int,
    holdings_payload: dict[str, Any],
    transactions: list[dict[str, Any]],
    snapshots: list[PortfolioSnapshot],
    watchlist_items: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    plan_detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_generated_at = parse_optional_datetime(generated_at) or datetime.now(timezone.utc)
    period_end = resolved_generated_at.date()
    period_start = period_end - timedelta(days=max(1, int(period_days)) - 1)

    holdings = holdings_payload.get("holdings") if isinstance(holdings_payload.get("holdings"), dict) else {}
    holdings_rows = [row for row in holdings.values() if isinstance(row, dict)]
    holdings_rows.sort(key=lambda row: safe_float(row.get("current_value"), 0.0), reverse=True)

    performance = holdings_payload.get("performance") if isinstance(holdings_payload.get("performance"), dict) else {}
    risk = holdings_payload.get("risk_alerts") if isinstance(holdings_payload.get("risk_alerts"), dict) else {}
    recommendations_status = _status_counts(recommendations, key="status")
    open_recommendations = (
        recommendations_status.get("proposed", 0)
        + recommendations_status.get("accepted", 0)
        + recommendations_status.get("in_progress", 0)
    )
    transaction_summary = _summarize_transactions(
        transactions,
        period_start=period_start,
        period_end=period_end,
    )
    audit_summary = _summarize_audit_events(
        holdings_payload,
        period_start=period_start,
        period_end=period_end,
    )
    snapshot_summary = _summarize_snapshots(
        snapshots,
        period_start=period_start,
        period_end=period_end,
    )

    top_positions = []
    total_value = safe_float(holdings_payload.get("total_value"), 0.0)
    for row in holdings_rows[:10]:
        value = safe_float(row.get("current_value"), 0.0)
        allocation = (value / total_value * 100) if total_value > 0 else 0.0
        top_positions.append(
            {
                "symbol": str(row.get("symbol") or "UNKNOWN"),
                "account": str(row.get("account") or ""),
                "value_usd": round(value, 2),
                "allocation_pct": round(allocation, 2),
                "asset_class": row.get("asset_class"),
                "sector": row.get("sector"),
                "region": row.get("region"),
            }
        )

    plan_summary: dict[str, Any] | None = None
    if isinstance(plan_detail, dict):
        decisions = plan_detail.get("decisions") if isinstance(plan_detail.get("decisions"), list) else []
        artifacts = plan_detail.get("artifacts") if isinstance(plan_detail.get("artifacts"), list) else []
        top_actions = plan_detail.get("top_next_actions") if isinstance(plan_detail.get("top_next_actions"), list) else []
        plan_summary = {
            "plan_id": str(plan_detail.get("id") or ""),
            "title": str(plan_detail.get("title") or ""),
            "updated_at": str(plan_detail.get("updated_at") or ""),
            "decisions_count": len(decisions),
            "artifacts_count": len(artifacts),
            "top_next_actions_count": len(top_actions),
            "recent_decisions": decisions[:8],
            "recent_artifacts": artifacts[:8],
        }

    return {
        "meta": {
            "schema_version": PORTFOLIO_REVIEW_PACKET_SCHEMA_VERSION,
            "generated_at": resolved_generated_at.isoformat(),
            "period_days": int(period_days),
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "source": "buildwealth_orchestrator",
        },
        "summary": {
            "holdings_as_of": str(holdings_payload.get("prices_updated_at") or holdings_payload.get("updated_at") or ""),
            "total_portfolio_value_usd": round(safe_float(holdings_payload.get("total_portfolio_value"), 0.0), 2),
            "total_invested_value_usd": round(safe_float(holdings_payload.get("total_value"), 0.0), 2),
            "total_cash_usd": round(safe_float(holdings_payload.get("total_cash"), 0.0), 2),
            "holdings_count": len(holdings_rows),
            "accounts_count": len(holdings_payload.get("account_totals") or {}),
            "watchlist_count": len([item for item in watchlist_items if isinstance(item, dict)]),
            "risk_status": str(risk.get("status") or "ok"),
            "risk_breach_count": safe_int(risk.get("breach_count"), 0),
            "risk_watch_count": safe_int(risk.get("watch_count"), 0),
            "recommendations_open": open_recommendations,
            "recommendations_total": len(recommendations),
            "performance": {
                "twr_return_pct": performance.get("twr_return_pct"),
                "xirr_annualized_return_pct": performance.get("xirr_annualized_return_pct"),
                "total_return_usd": performance.get("total_return_usd"),
                "total_return_pct": performance.get("total_return_pct"),
                "realized_gains_usd": performance.get("realized_gains_usd"),
                "unrealized_gains_usd": performance.get("unrealized_gains_usd"),
                "income_received_usd": performance.get("income_received_usd"),
            },
        },
        "portfolio": {
            "accounts": holdings_payload.get("account_totals", {}),
            "allocation_breakdowns": holdings_payload.get("allocation_breakdowns", {}),
            "top_positions": top_positions,
        },
        "risk": {
            "risk_policy": holdings_payload.get("risk_policy", {}),
            "risk_alerts": risk,
        },
        "activity": {
            "transactions": transaction_summary,
            "audit": audit_summary,
        },
        "snapshots": snapshot_summary,
        "watchlist": {
            "items_count": len([item for item in watchlist_items if isinstance(item, dict)]),
            "items": [dict(item) for item in watchlist_items[:40] if isinstance(item, dict)],
        },
        "recommendations": {
            "status_counts": recommendations_status,
            "items_count": len(recommendations),
            "recent_items": recommendations[:40],
        },
        "plan": plan_summary,
    }


def build_portfolio_review_packet_markdown(
    *,
    title: str,
    packet: dict[str, Any],
) -> str:
    meta = packet.get("meta") if isinstance(packet.get("meta"), dict) else {}
    summary = packet.get("summary") if isinstance(packet.get("summary"), dict) else {}
    performance = summary.get("performance") if isinstance(summary.get("performance"), dict) else {}
    risk = packet.get("risk") if isinstance(packet.get("risk"), dict) else {}
    risk_alerts = risk.get("risk_alerts") if isinstance(risk.get("risk_alerts"), dict) else {}
    alerts = risk_alerts.get("alerts") if isinstance(risk_alerts.get("alerts"), list) else []
    transactions = (
        packet.get("activity", {}).get("transactions", {})
        if isinstance(packet.get("activity"), dict)
        else {}
    )
    snapshots = packet.get("snapshots") if isinstance(packet.get("snapshots"), dict) else {}
    recommendations = packet.get("recommendations") if isinstance(packet.get("recommendations"), dict) else {}
    plan = packet.get("plan") if isinstance(packet.get("plan"), dict) else None
    top_positions = (
        packet.get("portfolio", {}).get("top_positions", [])
        if isinstance(packet.get("portfolio"), dict)
        else []
    )

    lines = [
        f"# {title}",
        "",
        "## Packet Meta",
        "",
        f"- Generated at: {meta.get('generated_at') or ''}",
        f"- Period: {meta.get('period_start') or ''} to {meta.get('period_end') or ''} ({meta.get('period_days') or 0} days)",
        "",
        "## Portfolio Summary",
        "",
        f"- Total portfolio value: ${safe_float(summary.get('total_portfolio_value_usd'), 0.0):,.2f}",
        f"- Invested value: ${safe_float(summary.get('total_invested_value_usd'), 0.0):,.2f}",
        f"- Cash: ${safe_float(summary.get('total_cash_usd'), 0.0):,.2f}",
        f"- Holdings count: {safe_int(summary.get('holdings_count'), 0)}",
        f"- Accounts count: {safe_int(summary.get('accounts_count'), 0)}",
        f"- Holdings as of: {summary.get('holdings_as_of') or 'n/a'}",
        "",
        "## Performance",
        "",
        f"- TWR: {performance.get('twr_return_pct') if performance.get('twr_return_pct') is not None else 'n/a'}%",
        f"- XIRR (annualized): {performance.get('xirr_annualized_return_pct') if performance.get('xirr_annualized_return_pct') is not None else 'n/a'}%",
        f"- Total return: ${safe_float(performance.get('total_return_usd'), 0.0):,.2f} ({performance.get('total_return_pct') if performance.get('total_return_pct') is not None else 'n/a'}%)",
        f"- Realized gains: ${safe_float(performance.get('realized_gains_usd'), 0.0):,.2f}",
        f"- Unrealized gains: ${safe_float(performance.get('unrealized_gains_usd'), 0.0):,.2f}",
        "",
        "## Risk",
        "",
        f"- Status: {str(summary.get('risk_status') or 'ok').upper()}",
        f"- Breaches: {safe_int(summary.get('risk_breach_count'), 0)}",
        f"- Watches: {safe_int(summary.get('risk_watch_count'), 0)}",
    ]

    if alerts:
        lines.extend(["", "### Active Alerts", ""])
        for item in alerts[:12]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('label')}: {item.get('state')} ({item.get('severity')}) | "
                f"observed {item.get('observed')} vs threshold {item.get('threshold')}"
            )
    else:
        lines.extend(["", "- No active risk alerts."])

    lines.extend(
        [
            "",
            "## Activity (Period)",
            "",
            f"- Transactions: {safe_int(transactions.get('period_transactions_count'), 0)}",
            f"- Net cash-flow estimate: ${safe_float(transactions.get('period_net_cash_flow_estimate_usd'), 0.0):,.2f}",
            "",
            "## Snapshot Trend (Period)",
            "",
            f"- Snapshot points: {safe_int(snapshots.get('period_snapshots_count'), 0)}",
            f"- Start value: {snapshots.get('period_start_value_usd')}",
            f"- End value: {snapshots.get('period_end_value_usd')}",
            f"- Delta: {snapshots.get('period_delta_value_usd')} ({snapshots.get('period_delta_value_pct')}%)",
            "",
            "## Top Positions",
            "",
        ]
    )

    if isinstance(top_positions, list) and top_positions:
        for row in top_positions[:10]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {row.get('symbol')}: ${safe_float(row.get('value_usd'), 0.0):,.2f} "
                f"({row.get('allocation_pct')}%)"
            )
    else:
        lines.append("- No holdings positions available.")

    status_counts = recommendations.get("status_counts") if isinstance(recommendations.get("status_counts"), dict) else {}
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            f"- Open: {safe_int(summary.get('recommendations_open'), 0)}",
            f"- Total in packet scope: {safe_int(summary.get('recommendations_total'), 0)}",
            f"- Status counts: {json.dumps(status_counts, sort_keys=True)}",
            "",
            "## Watchlist",
            "",
            f"- Items: {safe_int(summary.get('watchlist_count'), 0)}",
        ]
    )

    if plan:
        lines.extend(
            [
                "",
                "## Linked Plan",
                "",
                f"- Plan: {plan.get('title') or plan.get('plan_id')}",
                f"- Updated at: {plan.get('updated_at') or 'n/a'}",
                f"- Decisions: {safe_int(plan.get('decisions_count'), 0)}",
                f"- Artifacts: {safe_int(plan.get('artifacts_count'), 0)}",
                f"- Top next actions: {safe_int(plan.get('top_next_actions_count'), 0)}",
            ]
        )

    lines.append("")
    return "\n".join(lines)


class PortfolioReviewPacketStore:
    def __init__(self, packet_dir: Path):
        self.packet_dir = packet_dir
        self.packet_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _packet_id() -> str:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"portfolio-review-{stamp}-{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _coerce_summary(
        payload: dict[str, Any],
        *,
        packet_id: str,
        title: str,
        json_file_name: str,
        markdown_file_name: str,
    ) -> dict[str, Any]:
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        return {
            "packet_id": packet_id,
            "title": title,
            "generated_at": str(meta.get("generated_at") or utc_now_iso()),
            "period_start": str(meta.get("period_start") or date.today().isoformat()),
            "period_end": str(meta.get("period_end") or date.today().isoformat()),
            "holdings_as_of": str(summary.get("holdings_as_of") or "") or None,
            "total_portfolio_value_usd": round(safe_float(summary.get("total_portfolio_value_usd"), 0.0), 2),
            "risk_status": str(summary.get("risk_status") or "ok"),
            "risk_breach_count": safe_int(summary.get("risk_breach_count"), 0),
            "risk_watch_count": safe_int(summary.get("risk_watch_count"), 0),
            "recommendations_open": safe_int(summary.get("recommendations_open"), 0),
            "recommendations_total": safe_int(summary.get("recommendations_total"), 0),
            "storage": {
                "json_file": json_file_name,
                "markdown_file": markdown_file_name,
            },
        }

    def write(
        self,
        *,
        packet_payload: dict[str, Any],
        markdown: str,
        title: str,
    ) -> dict[str, Any]:
        packet_id = self._packet_id()
        packet = dict(packet_payload)
        meta = packet.get("meta") if isinstance(packet.get("meta"), dict) else {}
        meta["packet_id"] = packet_id
        meta["generated_at"] = str(meta.get("generated_at") or utc_now_iso())
        meta["title"] = title
        packet["meta"] = meta

        json_name = f"{packet_id}.json"
        md_name = f"{packet_id}.md"
        json_path = self.packet_dir / json_name
        md_path = self.packet_dir / md_name

        json_path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
        md_path.write_text(markdown, encoding="utf-8")

        return self._coerce_summary(
            packet,
            packet_id=packet_id,
            title=title,
            json_file_name=json_name,
            markdown_file_name=md_name,
        )

    @staticmethod
    def _sanitize_packet_id(packet_id: str) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "", str(packet_id or ""))
        return sanitized

    def read(self, packet_id: str) -> dict[str, Any]:
        sanitized = self._sanitize_packet_id(packet_id)
        if not sanitized:
            raise FileNotFoundError("Invalid packet id.")
        json_path = self.packet_dir / f"{sanitized}.json"
        md_path = self.packet_dir / f"{sanitized}.md"
        if not json_path.exists():
            raise FileNotFoundError(f"Packet not found: {packet_id}")
        packet = json.loads(json_path.read_text(encoding="utf-8"))
        markdown = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
        title = (
            str(packet.get("meta", {}).get("title") or "").strip()
            or str(packet.get("summary", {}).get("title") or "").strip()
            or "Portfolio Review Packet"
        )
        summary = self._coerce_summary(
            packet,
            packet_id=sanitized,
            title=title,
            json_file_name=json_path.name,
            markdown_file_name=md_path.name,
        )
        return {
            "summary": summary,
            "packet": packet,
            "markdown": markdown,
        }

    def restore_file(self, *, file_name: str, content: str) -> dict[str, Any]:
        safe_name = Path(str(file_name or "")).name
        if not safe_name or safe_name != str(file_name or ""):
            raise ValueError("Invalid review packet file name.")
        path = self.packet_dir / safe_name
        if path.suffix.lower() == ".json":
            packet = json.loads(content)
            if not isinstance(packet, dict):
                raise ValueError("Review packet JSON restore payload must be an object.")
            packet_id = str(packet.get("meta", {}).get("packet_id") or path.stem)
            if self._sanitize_packet_id(packet_id) != path.stem:
                raise ValueError("Review packet id must match the restored file name.")
            path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
            return {"file_name": safe_name, "packet_id": path.stem, "status": "restored"}
        if path.suffix.lower() == ".md":
            if not path.stem.startswith("portfolio-review-"):
                raise ValueError("Review packet markdown restore file name is invalid.")
            path.write_text(content, encoding="utf-8")
            return {"file_name": safe_name, "packet_id": path.stem, "status": "restored"}
        raise ValueError("Review packet restore supports only .json and .md files.")

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), 500))
        rows: list[dict[str, Any]] = []
        candidates = sorted(self.packet_dir.glob("portfolio-review-*.json"), reverse=True)
        for path in candidates:
            if len(rows) >= bounded_limit:
                break
            try:
                packet = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            packet_id = str(packet.get("meta", {}).get("packet_id") or path.stem)
            title = (
                str(packet.get("meta", {}).get("title") or "").strip()
                or str(packet.get("summary", {}).get("title") or "").strip()
                or "Portfolio Review Packet"
            )
            md_name = f"{packet_id}.md"
            rows.append(
                self._coerce_summary(
                    packet,
                    packet_id=packet_id,
                    title=title,
                    json_file_name=path.name,
                    markdown_file_name=md_name,
                )
            )
        return rows

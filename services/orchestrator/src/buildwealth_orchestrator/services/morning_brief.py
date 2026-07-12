"""Morning brief — what changed since you last looked.

Assembles a digest from stores the heartbeat already keeps fresh (the
scheduled sync loop runs the recommendation sweeps, risk alerts recompute on
holdings reads, and snapshots land daily): new proposed recommendations,
active risk alerts, pending context reviews, and portfolio drift since the
last time the user marked the brief as seen.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class MorningBriefService:
    def __init__(
        self,
        *,
        recommendation_inbox: Any,
        portfolio_store: Any,
        snapshot_store: Any,
        context_intelligence_service: Any,
        seen_path: Path,
    ):
        self.recommendation_inbox = recommendation_inbox
        self.portfolio_store = portfolio_store
        self.snapshot_store = snapshot_store
        self.context_intelligence_service = context_intelligence_service
        self.seen_path = seen_path

    # ---- last-seen tracking -------------------------------------------------

    def seen_at(self) -> datetime | None:
        try:
            payload = json.loads(self.seen_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        return _parse_iso(payload.get("seen_at")) if isinstance(payload, dict) else None

    def mark_seen(self, *, now: datetime | None = None) -> dict[str, Any]:
        stamp = (now or _utc_now()).isoformat()
        self.seen_path.parent.mkdir(parents=True, exist_ok=True)
        self.seen_path.write_text(json.dumps({"seen_at": stamp}, indent=2), encoding="utf-8")
        return {"seen_at": stamp}

    # ---- digest -------------------------------------------------------------

    def build(self, *, now: datetime | None = None) -> dict[str, Any]:
        resolved_now = now or _utc_now()
        since = self.seen_at()

        new_recommendations = self._new_recommendations(since)
        risk = self._risk_summary()
        pending_reviews = self._pending_context_reviews()
        portfolio = self._portfolio_drift(since)

        return {
            "generated_at": resolved_now.isoformat(),
            "since": since.isoformat() if since else None,
            "first_visit": since is None,
            "new_recommendations": new_recommendations,
            "risk_alerts": risk,
            "pending_context_reviews": pending_reviews,
            "portfolio": portfolio,
            "has_news": bool(
                new_recommendations["count"]
                or risk["breach_count"]
                or risk["watch_count"]
                or pending_reviews["count"]
            ),
        }

    def _new_recommendations(self, since: datetime | None) -> dict[str, Any]:
        rows = self.recommendation_inbox.list(limit=500, status="proposed") or []
        fresh = []
        for row in rows:
            created = _parse_iso(row.get("created_at"))
            if since is not None and (created is None or created <= since):
                continue
            fresh.append(row)
        items = [
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "priority": row.get("priority"),
                "recommendation_type": row.get("recommendation_type"),
                "created_at": row.get("created_at"),
            }
            for row in fresh[:5]
        ]
        return {"count": len(fresh), "items": items}

    def _risk_summary(self) -> dict[str, Any]:
        try:
            holdings = self.portfolio_store.get_holdings()
        except Exception:
            holdings = {}
        alerts_payload = holdings.get("risk_alerts") if isinstance(holdings, dict) else {}
        if not isinstance(alerts_payload, dict):
            alerts_payload = {}
        alerts = alerts_payload.get("alerts")
        alerts = alerts if isinstance(alerts, list) else []
        return {
            "status": str(alerts_payload.get("status") or "ok"),
            "breach_count": int(alerts_payload.get("breach_count") or 0),
            "watch_count": int(alerts_payload.get("watch_count") or 0),
            "items": [
                {
                    "severity": alert.get("severity"),
                    "kind": alert.get("kind") or alert.get("metric") or alert.get("type"),
                    "message": alert.get("message") or alert.get("detail"),
                }
                for alert in alerts[:5]
                if isinstance(alert, dict)
            ],
        }

    def _pending_context_reviews(self) -> dict[str, Any]:
        try:
            candidates = self.context_intelligence_service.list_context_candidates(
                lifecycle_state="pending_review", limit=100
            )
        except Exception:
            candidates = []
        return {"count": len(candidates)}

    def _portfolio_drift(self, since: datetime | None) -> dict[str, Any]:
        try:
            snapshots = self.snapshot_store.recent(limit=30)
        except Exception:
            snapshots = []
        if not snapshots:
            return {"available": False}

        def _aware(stamp: datetime) -> datetime:
            return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)

        ordered = sorted(snapshots, key=lambda snap: _aware(snap.as_of))
        latest = ordered[-1]
        baseline = None
        if since is not None:
            candidates = [snap for snap in ordered if _aware(snap.as_of) <= since]
            baseline = candidates[-1] if candidates else ordered[0]
        current_value = float(latest.total_value_usd or 0.0)
        result: dict[str, Any] = {
            "available": True,
            "as_of": latest.as_of.isoformat(),
            "total_value_usd": round(current_value, 2),
        }
        if baseline is not None and baseline is not latest:
            baseline_value = float(baseline.total_value_usd or 0.0)
            change = current_value - baseline_value
            result["change_since_seen_usd"] = round(change, 2)
            if baseline_value:
                result["change_since_seen_pct"] = round(change / baseline_value * 100.0, 2)
        return result

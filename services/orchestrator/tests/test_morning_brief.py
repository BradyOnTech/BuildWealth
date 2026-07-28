from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from buildwealth_orchestrator.services.morning_brief import MorningBriefService


def _snapshot(as_of: datetime, total: float) -> SimpleNamespace:
    return SimpleNamespace(as_of=as_of, total_value_usd=total)


class _FakeInbox:
    def __init__(self, rows):
        self.rows = rows

    def list(self, **kwargs):
        return self.rows


class _FakePortfolio:
    def __init__(self, alerts_payload, holdings_payload=None):
        self.alerts_payload = alerts_payload
        self.holdings_payload = holdings_payload

    def get_holdings(self):
        if self.holdings_payload is not None:
            return self.holdings_payload
        return {"risk_alerts": self.alerts_payload}


class _FakeProfile:
    def __init__(self, investment_policy):
        self.investment_policy = investment_policy

    def load(self):
        return {"investment_policy": self.investment_policy}


class _FakeSnapshots:
    def __init__(self, snapshots):
        self.snapshots = snapshots

    def recent(self, limit=10):
        return self.snapshots


class _FakeContext:
    def __init__(self, count):
        self.count = count

    def list_context_candidates(self, **kwargs):
        return [{"id": f"c{i}"} for i in range(self.count)]


def _service(tmp_path: Path, *, rows=(), alerts=None, snapshots=(), reviews=0) -> MorningBriefService:
    return MorningBriefService(
        recommendation_inbox=_FakeInbox(list(rows)),
        portfolio_store=_FakePortfolio(alerts or {"status": "ok", "breach_count": 0, "watch_count": 0, "alerts": []}),
        snapshot_store=_FakeSnapshots(list(snapshots)),
        context_intelligence_service=_FakeContext(reviews),
        seen_path=tmp_path / "today" / "brief_seen.json",
    )


def test_first_visit_has_no_since_and_counts_everything(tmp_path: Path) -> None:
    now = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)
    rows = [{"id": "rec-1", "title": "Rebalance", "priority": "high",
             "recommendation_type": "rebalance", "created_at": (now - timedelta(days=2)).isoformat()}]
    service = _service(tmp_path, rows=rows, reviews=2)

    brief = service.build(now=now)
    assert brief["first_visit"] is True
    assert brief["since"] is None
    assert brief["new_recommendations"]["count"] == 1
    assert brief["pending_context_reviews"]["count"] == 2
    assert brief["has_news"] is True


def test_seen_marker_filters_recommendations_and_measures_drift(tmp_path: Path) -> None:
    now = datetime(2026, 7, 12, 9, 0, tzinfo=timezone.utc)
    seen = now - timedelta(days=3)
    rows = [
        {"id": "old", "title": "Old", "priority": "low", "recommendation_type": "general",
         "created_at": (seen - timedelta(days=1)).isoformat()},
        {"id": "new", "title": "Fresh idea", "priority": "high", "recommendation_type": "rebalance",
         "created_at": (seen + timedelta(days=1)).isoformat()},
    ]
    snapshots = [
        _snapshot(seen - timedelta(days=1), 100_000.0),
        _snapshot(now - timedelta(hours=2), 104_000.0),
    ]
    service = _service(tmp_path, rows=rows, snapshots=snapshots)
    service.mark_seen(now=seen)

    brief = service.build(now=now)
    assert brief["first_visit"] is False
    assert brief["new_recommendations"]["count"] == 1
    assert brief["new_recommendations"]["items"][0]["id"] == "new"
    portfolio = brief["portfolio"]
    assert portfolio["available"] is True
    assert portfolio["change_since_seen_usd"] == 4000.0
    assert portfolio["change_since_seen_pct"] == 4.0


def test_risk_alerts_summarized(tmp_path: Path) -> None:
    alerts = {
        "status": "breach",
        "breach_count": 1,
        "watch_count": 1,
        "alerts": [
            {"severity": "high", "kind": "single_symbol_exposure", "message": "NVDA is 18% of the portfolio."},
            {"severity": "medium", "kind": "sector_exposure", "message": "Tech exposure at watch level."},
        ],
    }
    service = _service(tmp_path, alerts=alerts)
    brief = service.build()
    assert brief["risk_alerts"]["breach_count"] == 1
    assert brief["risk_alerts"]["items"][0]["message"].startswith("NVDA")
    assert brief["has_news"] is True


def test_profile_aware_risk_replaces_fund_wrapper_concentration(tmp_path: Path) -> None:
    service = MorningBriefService(
        recommendation_inbox=_FakeInbox([]),
        portfolio_store=_FakePortfolio(
            {},
            holdings_payload={
                "holdings": {
                    "taxable": [
                        {
                            "symbol": "VTI",
                            "name": "Vanguard Total Stock Market ETF",
                            "market_value": 10_000.0,
                            "asset_class": "equity",
                        }
                    ]
                },
                "allocation_breakdowns": {
                    "security": [
                        {"key": "AAPL", "exposure_pct": 6.0},
                        {"key": "MSFT", "exposure_pct": 5.5},
                    ]
                },
            },
        ),
        financial_profile_store=_FakeProfile({"max_single_symbol_exposure_pct": 20.0}),
        snapshot_store=_FakeSnapshots([]),
        context_intelligence_service=_FakeContext(0),
        seen_path=tmp_path / "today" / "brief_seen.json",
    )

    brief = service.build()

    assert brief["risk_alerts"]["breach_count"] == 0
    assert not any("VTI" in str(item.get("message")) for item in brief["risk_alerts"]["items"])


def test_quiet_brief_reports_no_news(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.mark_seen()
    brief = service.build()
    assert brief["has_news"] is False
    assert brief["new_recommendations"]["count"] == 0

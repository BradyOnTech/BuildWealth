import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import PortfolioSnapshot, ResearchResponse


class _Dumpable:
    def __init__(self, payload):
        self._payload = payload

    def model_dump(self, mode: str = "json"):
        return dict(self._payload)


class _FakeResearchService:
    def __init__(self) -> None:
        self.quote_calls = 0
        self.history_calls = 0

    def quote(self, symbol: str) -> ResearchResponse:
        self.quote_calls += 1
        return ResearchResponse(
            symbol=symbol,
            provider="test",
            available=True,
            message="ok",
            records=[{"last": 100.0, "change_percent": 1.5}],
        )

    def price_history(self, symbol: str, period: str = "6mo", interval: str = "1d") -> ResearchResponse:
        self.history_calls += 1
        return ResearchResponse(
            symbol=symbol,
            provider="test",
            available=True,
            message="ok",
            records=[{"close": 100.0}, {"close": 110.0}],
        )


@pytest.mark.parametrize("force_refresh", [True, False])
def test_buildwealth_context_payload_cache_policy_and_freshness(
    monkeypatch: pytest.MonkeyPatch,
    force_refresh: bool,
) -> None:
    stale_as_of = datetime.now(timezone.utc) - timedelta(hours=2)
    snapshot = PortfolioSnapshot(
        as_of=stale_as_of,
        base_currency="USD",
        total_value_usd=250000.0,
        total_investment_usd=200000.0,
        net_performance_usd=50000.0,
        net_performance_percent=25.0,
        holdings=[],
        accounts=[],
        raw={},
    )

    fake_research = _FakeResearchService()

    monkeypatch.setattr(
        main,
        "snapshot_store",
        SimpleNamespace(
            latest=lambda: snapshot,
            recent=lambda limit=90: [],
        ),
    )
    monkeypatch.setattr(
        main,
        "portfolio_store",
        SimpleNamespace(
            list_watchlist=lambda: [],
            list_transactions=lambda limit=10_000: [],
        ),
    )
    monkeypatch.setattr(main, "build_snapshot_history_payload", lambda limit=30: _Dumpable({"points": [], "window_points": 0}))
    monkeypatch.setattr(
        main,
        "build_today_dashboard_response",
        lambda: _Dumpable(
            {
                "net_worth_usd": 320000.0,
                "monthly_surplus_usd": 1800.0,
                "savings_rate_pct": 24.0,
            }
        ),
    )
    monkeypatch.setattr(
        main,
        "get_financial_profile_payload",
        lambda: {
            "schema_version": 2,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "income_items": [],
            "expense_items": [],
            "debt_items": [],
            "goal_items": [],
            "physical_assets": [],
            "tax_profile": {},
            "flags": {},
            "notes": "",
        },
    )
    monkeypatch.setattr(main, "build_onboarding_status_response", lambda: _Dumpable({"completion_percent": 100.0}))
    monkeypatch.setattr(main, "_recommendation_list", lambda limit=10, status="proposed": [])
    monkeypatch.setattr(main, "resolve_active_plan_detail", lambda: None)
    monkeypatch.setattr(main, "research_service", fake_research)

    monkeypatch.setattr(main.settings, "copilot_context_cache_enabled", True)
    monkeypatch.setattr(main.settings, "copilot_context_research_cache_ttl_seconds", 120.0)
    monkeypatch.setattr(main.settings, "copilot_context_projection_cache_ttl_seconds", 90.0)
    monkeypatch.setattr(main.settings, "copilot_context_snapshot_stale_after_seconds", 3600.0)

    main.copilot_context_research_cache.clear()
    main.copilot_context_projection_cache.clear()

    payload_first = asyncio.run(
        main.build_buildwealth_context_payload(
            use_live_snapshot=False,
            include_research=True,
            include_plan_projection=False,
            research_symbols=["AAPL"],
            force_refresh=force_refresh,
            summary_max_chars=1200,
        )
    )

    assert payload_first["cache"]["enabled"] is True
    assert payload_first["cache"]["read_enabled"] is (not force_refresh)
    assert payload_first["cache"]["write_enabled"] is True
    if force_refresh:
        assert payload_first["cache"]["bypass_reason"] == "force_refresh"
    else:
        assert payload_first["cache"]["bypass_reason"] is None

    assert payload_first["cache"]["research"]["hit"] is False
    assert payload_first["cache"]["research"]["written"] is True
    assert payload_first["quality"]["freshness"]["snapshot_stale"] is True
    assert any("stale" in str(item).lower() for item in payload_first["warnings"])

    first_quote_calls = fake_research.quote_calls
    first_history_calls = fake_research.history_calls
    assert first_quote_calls == 1
    assert first_history_calls == 1

    payload_second = asyncio.run(
        main.build_buildwealth_context_payload(
            use_live_snapshot=False,
            include_research=True,
            include_plan_projection=False,
            research_symbols=["AAPL"],
            force_refresh=False,
            summary_max_chars=1200,
        )
    )

    assert payload_second["cache"]["read_enabled"] is True
    assert payload_second["cache"]["research"]["hit"] is True
    assert payload_second["cache"]["research"]["written"] is False
    assert fake_research.quote_calls == first_quote_calls
    assert fake_research.history_calls == first_history_calls

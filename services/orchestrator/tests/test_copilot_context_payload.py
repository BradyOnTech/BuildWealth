import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import (
    CopilotContextResponse,
    PortfolioSnapshot,
    ResearchResponse,
)


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


@pytest.mark.parametrize("include_research", [False, True])
@pytest.mark.parametrize("with_plan", [False, True])
@pytest.mark.parametrize("detail_level", ["full", "light"])
def test_buildwealth_context_payload_contract_permutations(
    monkeypatch: pytest.MonkeyPatch,
    include_research: bool,
    with_plan: bool,
    detail_level: str,
) -> None:
    snapshot = PortfolioSnapshot(
        as_of=datetime.now(timezone.utc),
        base_currency="USD",
        total_value_usd=300000.0,
        total_investment_usd=250000.0,
        net_performance_usd=50000.0,
        net_performance_percent=20.0,
        holdings=[],
        accounts=[],
        raw={},
    )

    fake_research = _FakeResearchService()
    now_iso = datetime.now(timezone.utc).isoformat()

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
            list_watchlist=lambda: [{"symbol": "AAPL"}],
            list_transactions=lambda limit=10_000: [],
        ),
    )
    monkeypatch.setattr(main, "build_snapshot_history_payload", lambda limit=30: _Dumpable({"points": [], "window_points": 0}))
    monkeypatch.setattr(
        main,
        "build_today_dashboard_response",
        lambda: _Dumpable(
            {
                "net_worth_usd": 360000.0,
                "monthly_surplus_usd": 2200.0,
                "savings_rate_pct": 26.0,
            }
        ),
    )
    monkeypatch.setattr(
        main,
        "get_financial_profile_payload",
        lambda: {
            "schema_version": 2,
            "updated_at": now_iso,
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
    monkeypatch.setattr(main, "research_service", fake_research)
    monkeypatch.setattr(main.settings, "copilot_context_cache_enabled", True)
    monkeypatch.setattr(main.settings, "copilot_context_snapshot_stale_after_seconds", 86400.0)
    main.copilot_context_research_cache.clear()
    main.copilot_context_projection_cache.clear()

    if with_plan:
        plan_detail = {
            "id": "plan-1",
            "title": "Primary Plan",
            "description": "",
            "updated_at": now_iso,
            "settings": {},
            "decisions": [],
        }
        monkeypatch.setattr(
            main,
            "_resolve_context_plan_detail",
            lambda plan_id, *, workspace=None: (plan_detail, "plan-1"),
        )
        monkeypatch.setattr(
            main,
            "plan_workspace",
            SimpleNamespace(
                get_context_payload=lambda plan_id: {"plan_id": plan_id},
                get_plan_assumption_sets=lambda plan_id: {"schema_version": 2, "active_assumption_set_id": "default", "sets": []},
                get_plan_timeline=lambda plan_id: {"schema_version": 2, "events": [], "retirement": {}},
                get_plan_contribution_rules=lambda plan_id: {"schema_version": 2, "base_rule": {"type": "save"}, "rules": []},
                get_plan_branch_templates=lambda plan_id: {"schema_version": 2, "default_template_id": None, "templates": []},
            ),
        )
        monkeypatch.setattr(
            main,
            "compute_plan_tracking",
            lambda **kwargs: _Dumpable(
                {
                    "status": "on_track",
                    "actual_annualized_return_pct": 7.0,
                    "expected_annualized_return_pct": 6.5,
                }
            ),
        )
    else:
        monkeypatch.setattr(
            main,
            "_resolve_context_plan_detail",
            lambda plan_id, *, workspace=None: (None, None),
        )

    payload = asyncio.run(
        main.build_buildwealth_context_payload(
            use_live_snapshot=False,
            plan_id="plan-1" if with_plan else None,
            include_research=include_research,
            include_plan_projection=False,
            research_symbols=["AAPL"],
            force_refresh=False,
            summary_max_chars=1400,
            detail_level=detail_level,
        )
    )

    parsed = CopilotContextResponse(**payload)
    assert parsed.scope.include_research is include_research
    assert parsed.scope.detail_level == detail_level
    assert isinstance(parsed.summary, str)
    assert parsed.quality.summary.max_chars == 1400

    active_plan = parsed.planning.get("active_plan")
    if with_plan:
        assert isinstance(active_plan, dict)
        assert active_plan.get("id") == "plan-1"
    else:
        assert active_plan is None

    if include_research:
        assert fake_research.quote_calls > 0
        assert isinstance(parsed.research.get("items"), list)
    else:
        assert fake_research.quote_calls == 0
        assert parsed.research.get("items") == []

    if detail_level == "light":
        profile_payload = parsed.financial_picture.get("financial_profile")
        assert isinstance(profile_payload, dict)
        assert "income_items" not in profile_payload
        assert "income_items_count" in profile_payload


def test_get_copilot_context_cache_status_reports_store_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main.settings, "copilot_context_cache_enabled", True)
    main.copilot_context_research_cache.clear()
    main.copilot_context_projection_cache.clear()

    main.copilot_context_research_cache.set("r1", {"ok": True}, ttl_seconds=30)
    main.copilot_context_research_cache.set("r-expired", {"ok": False}, ttl_seconds=0.01)
    main.copilot_context_projection_cache.set("p1", {"ok": True}, ttl_seconds=30)
    main.copilot_context_projection_cache.set("p2", {"ok": True}, ttl_seconds=30)

    import time
    time.sleep(0.02)

    status = main.get_copilot_context_cache_status()

    assert status.enabled is True
    stores = {item.name: item for item in status.stores}
    assert set(stores.keys()) == {"research", "baseline_projection"}
    assert stores["research"].entries == 1
    assert stores["research"].expired_pruned >= 1
    assert stores["research"].write_count == 2
    assert stores["research"].lookup_count == 0
    assert stores["research"].hit_rate_pct == 0.0
    assert stores["baseline_projection"].entries == 2
    assert stores["baseline_projection"].write_count == 2


def test_reset_copilot_context_cache_resets_selected_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main.settings, "copilot_context_cache_enabled", True)
    main.copilot_context_research_cache.clear()
    main.copilot_context_projection_cache.clear()

    main.copilot_context_research_cache.set("r1", {"ok": True}, ttl_seconds=30)
    main.copilot_context_projection_cache.set("p1", {"ok": True}, ttl_seconds=30)

    status = main.reset_copilot_context_cache(target="research")

    stores = {item.name: item for item in status.stores}
    assert stores["research"].entries == 0
    assert stores["research"].write_count == 0
    assert stores["baseline_projection"].entries == 1
    assert stores["baseline_projection"].write_count == 1


def test_reset_copilot_context_cache_rejects_invalid_target() -> None:
    with pytest.raises(main.HTTPException) as exc:
        main.reset_copilot_context_cache(target="unknown")
    assert exc.value.status_code == 400

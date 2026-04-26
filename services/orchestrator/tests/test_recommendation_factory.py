from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_risk_alerts import calculate_portfolio_risk_alerts
from buildwealth_orchestrator.services.recommendation_factory import (
    generate_cash_liquidity_recommendations,
    generate_plan_tracking_recommendations,
    generate_portfolio_risk_recommendations,
    generate_profile_completeness_recommendations,
    generate_stale_assumption_recommendations,
    generate_watchlist_research_recommendations,
)
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def _assert_quality_metadata(candidate: dict[str, object], *, expected_source: str) -> None:
    payload = candidate["action_payload"]
    assert isinstance(payload, dict)
    quality = payload["quality"]
    assert quality["schema_version"] == 1
    assert quality["source"] == expected_source
    assert quality["confidence_level"] in {"high", "medium", "low"}
    assert isinstance(quality["confidence_score"], float)
    assert 0.0 <= quality["confidence_score"] <= 1.0
    assert quality["confidence_reasons"]
    assert quality["freshness_status"] in {"fresh", "stale", "unknown"}
    assert isinstance(quality["freshness_reasons"], list)
    assert quality["actionability"] in {"previewable", "review_only", "context_gathering"}
    assert isinstance(quality["actionability_reasons"], list)
    assert quality["reversibility"] in {"high", "medium", "low", "unknown"}
    assert isinstance(quality["impact"], dict)
    assert quality["impact"]["level"] in {"high", "medium", "low"}
    assert isinstance(quality["impact"]["summary"], str)
    assert isinstance(quality["blocking_context"], list)
    assert isinstance(quality["decision_grade"], bool)


def _holdings_payload() -> dict[str, object]:
    holdings = {
        "default:AAPL": {
            "symbol": "AAPL",
            "account": "default",
            "current_value": 70_000.0,
            "asset_class": "US Stocks",
            "sector": "Technology",
            "region": "US",
        },
        "default:MSFT": {
            "symbol": "MSFT",
            "account": "default",
            "current_value": 20_000.0,
            "asset_class": "US Stocks",
            "sector": "Technology",
            "region": "US",
        },
        "default:BND": {
            "symbol": "BND",
            "account": "default",
            "current_value": 10_000.0,
            "asset_class": "US Bonds",
            "sector": "Fixed Income",
            "region": "US",
        },
    }
    risk_alerts = calculate_portfolio_risk_alerts(
        holdings=holdings,
        account_totals={"default": {"total_value": 100_000.0}},
        allocation_breakdowns=None,
        thresholds={
            "single_holding_max_pct": 25.0,
            "top3_holdings_max_pct": 60.0,
            "account_max_pct": 100.0,
            "asset_class_max_pct": 82.0,
            "sector_max_pct": 35.0,
            "region_max_pct": 69.0,
            "hhi_max": 0.2,
            "effective_positions_min": 5.0,
        },
        generated_at="2026-04-25T12:00:00+00:00",
    )
    return {
        "updated_at": "2026-04-25T12:00:00+00:00",
        "total_value": 100_000.0,
        "holdings": holdings,
        "risk_alerts": risk_alerts,
    }


def _cash_holdings_payload(total_cash: float) -> dict[str, object]:
    payload = _holdings_payload()
    payload["total_cash"] = total_cash
    payload["total_portfolio_value"] = 100_000.0 + total_cash
    payload["account_cash"] = {"default": total_cash}
    return payload


def _financial_profile_payload(*, monthly_expenses: float = 4_000.0, monthly_debt_payment: float = 500.0) -> dict[str, object]:
    return {
        "schema_version": 2,
        "updated_at": "2026-04-25T12:00:00+00:00",
        "income_items": [{"id": "income-1", "label": "Salary", "monthly_amount_usd": 10_000.0}],
        "expense_items": [{"id": "expense-1", "label": "Core expenses", "monthly_amount_usd": monthly_expenses}],
        "debt_items": [{"id": "debt-1", "label": "Auto loan", "balance_usd": 12_000, "minimum_payment_usd": monthly_debt_payment}],
        "goal_items": [],
        "physical_assets": [],
        "tax_profile": {},
        "flags": {"no_debt": False, "no_goals": False},
        "notes": "",
    }


def test_profile_completeness_factory_generates_next_gap_candidate() -> None:
    readiness = main.build_onboarding_status_response(
        profile_payload={
            "income_items": [{"id": "income-1", "label": "Salary", "monthly_amount_usd": 10_000}],
            "expense_items": [],
            "debt_items": [],
            "goal_items": [],
            "physical_assets": [],
            "tax_profile": {"filing_status": None, "marginal_tax_rate": None},
            "flags": {"no_debt": False, "no_goals": False},
        },
        latest_snapshot=None,
        active_plan_detail=None,
        load_fallbacks=False,
    ).profile_readiness

    result = generate_profile_completeness_recommendations(
        profile_readiness_payload=readiness.model_dump(mode="json"),
        existing_recommendations=[],
        dry_run=True,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["source"] == "generator:profile_completeness"
    assert "Expense profile" in candidate["title"]
    payload = candidate["action_payload"]
    assert payload["generator"]["dedupe_key"] == "profile_completeness:expenses"
    assert payload["evidence"]["data_keys"] == ["financial_profile.readiness"]
    assert payload["suggested_action"]["kind"] == "complete_profile_section"
    assert "cash_liquidity" in payload["evidence"]["blocking_recommendation_sources"]
    _assert_quality_metadata(candidate, expected_source="generator:profile_completeness")
    assert payload["quality"]["actionability"] == "context_gathering"
    assert payload["quality"]["decision_grade"] is False


def test_profile_completeness_factory_apply_skips_active_duplicates(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    readiness = main.build_onboarding_status_response(
        profile_payload={
            "income_items": [],
            "expense_items": [],
            "debt_items": [],
            "goal_items": [],
            "physical_assets": [],
            "tax_profile": {"filing_status": None, "marginal_tax_rate": None},
            "flags": {"no_debt": False, "no_goals": False},
        },
        latest_snapshot=None,
        active_plan_detail=None,
        load_fallbacks=False,
    ).profile_readiness

    first = generate_profile_completeness_recommendations(
        profile_readiness_payload=readiness.model_dump(mode="json"),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )
    second = generate_profile_completeness_recommendations(
        profile_readiness_payload=readiness.model_dump(mode="json"),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        now=datetime(2026, 4, 25, 12, 35, tzinfo=timezone.utc),
    )

    assert first.generated_count == 1
    assert len(first.created) == 1
    assert second.generated_count == 0
    assert second.skipped[0]["reason"] == "active_duplicate"


def test_portfolio_risk_factory_dry_run_generates_specific_candidates() -> None:
    result = generate_portfolio_risk_recommendations(
        holdings_payload=_holdings_payload(),
        existing_recommendations=[],
        dry_run=True,
        limit=3,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 3
    assert result.created == []
    assert result.candidates[0]["priority"] == "high"
    assert result.candidates[0]["source"] == "generator:portfolio_risk"
    assert "concentration" in result.candidates[0]["title"].lower()
    assert "$" in result.candidates[0]["detail"]
    payload = result.candidates[0]["action_payload"]
    assert payload["generator"]["dedupe_key"].startswith("portfolio_risk_alert:")
    assert payload["evidence"]["data_keys"] == ["portfolio.holdings", "portfolio.risk_alerts"]
    assert payload["suggested_action"]["estimated_rebalance_usd"] is not None
    _assert_quality_metadata(result.candidates[0], expected_source="generator:portfolio_risk")


def test_watchlist_research_factory_generates_refresh_candidate_for_partial_evidence() -> None:
    result = generate_watchlist_research_recommendations(
        watchlist_rank_payload={
            "items": [
                {
                    "symbol": "MSFT",
                    "research_evidence_packet_id": "research-evidence:yfinance:MSFT:6mo:1d",
                    "research_provider": "yfinance",
                    "research_freshness_status": "partial",
                    "research_confidence": "medium",
                    "research_coverage_score": 50.0,
                    "research_blocking_gaps": ["history"],
                    "watchlist_score_total": 62.0,
                    "provider_coverage": {"provider_status": "partial"},
                }
            ]
        },
        fit_assessments_by_symbol={
            "MSFT": {
                "fit_status": "needs_more_context",
                "fit_score": 45.0,
                "fit_reasons": [],
                "fit_risks": ["Research evidence is partial."],
                "blocking_gaps": ["research:partial"],
                "recommended_next_step": "research_more",
            }
        },
        existing_recommendations=[],
        dry_run=True,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["source"] == "generator:watchlist_research"
    assert candidate["title"] == "Refresh research evidence for MSFT"
    payload = candidate["action_payload"]
    assert payload["generator"]["dedupe_key"] == "watchlist_research:msft:research_partial"
    assert payload["suggested_action"]["kind"] == "refresh_research_evidence"
    assert payload["evidence"]["research_evidence_packet_id"] == "research-evidence:yfinance:MSFT:6mo:1d"
    assert payload["evidence"]["freshness_status"] == "partial"
    assert payload["quality"]["actionability"] == "context_gathering"
    _assert_quality_metadata(candidate, expected_source="generator:watchlist_research")


def test_watchlist_research_factory_generates_fit_conflict_review_without_trade_language() -> None:
    result = generate_watchlist_research_recommendations(
        watchlist_rank_payload={
            "items": [
                {
                    "symbol": "NVDA",
                    "research_evidence_packet_id": "research-evidence:yfinance:NVDA:6mo:1d",
                    "research_provider": "yfinance",
                    "research_freshness_status": "fresh",
                    "research_confidence": "high",
                    "research_coverage_score": 100.0,
                    "research_blocking_gaps": [],
                }
            ]
        },
        fit_assessments_by_symbol={
            "NVDA": {
                "fit_status": "does_not_fit",
                "fit_score": 25.0,
                "fit_reasons": [],
                "fit_risks": ["Simulated trade worsens concentration risk."],
                "blocking_gaps": ["concentration"],
                "recommended_next_step": "review_concentration",
            }
        },
        existing_recommendations=[],
        dry_run=True,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["title"] == "Review why NVDA does not currently fit"
    assert candidate["priority"] == "high"
    payload = candidate["action_payload"]
    assert payload["suggested_action"]["kind"] == "review_portfolio_fit"
    joined = " ".join([candidate["title"], candidate["detail"], payload["suggested_action"]["kind"]])
    assert "buy" not in joined.lower()
    assert "sell" not in joined.lower()


def test_portfolio_risk_factory_apply_creates_rows_and_skips_duplicates(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    first = generate_portfolio_risk_recommendations(
        holdings_payload=_holdings_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=50,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert first.generated_count >= 2
    assert len(first.created) == first.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == first.generated_count

    second = generate_portfolio_risk_recommendations(
        holdings_payload=_holdings_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=50,
        now=datetime(2026, 4, 25, 12, 35, tzinfo=timezone.utc),
    )

    assert second.generated_count == 0
    assert second.created == []
    assert second.skipped_count >= first.generated_count
    assert {item["reason"] for item in second.skipped} == {"active_duplicate"}
    assert len(inbox.list(limit=None, status="proposed")) == first.generated_count


class _FakePortfolioStore:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def get_holdings(self) -> dict[str, object]:
        return self.payload

    def list_transactions(self, limit: int | None = None) -> list[dict[str, object]]:
        return []


class _FakeFinancialProfileStore:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def get(self) -> dict[str, object]:
        return self.payload

    def load(self) -> dict[str, object]:
        return self.payload


def test_generate_portfolio_risk_route_supports_dry_run_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "portfolio_store", _FakePortfolioStore(_holdings_payload()))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dry_run = main.generate_portfolio_risk_recommendation_candidates(
        main.PortfolioRiskRecommendationGenerateRequest(dry_run=True, limit=2),
    )

    assert dry_run.dry_run is True
    assert dry_run.generated_count == 2
    assert dry_run.created == []
    assert inbox.list(limit=None, status="proposed") == []

    applied = main.generate_portfolio_risk_recommendation_candidates(
        main.PortfolioRiskRecommendationGenerateRequest(dry_run=False, limit=50),
    )

    assert applied.dry_run is False
    assert applied.generated_count >= 2
    assert len(applied.created) == applied.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == applied.generated_count

    duplicate = main.generate_portfolio_risk_recommendation_candidates(
        main.PortfolioRiskRecommendationGenerateRequest(dry_run=False, limit=50),
    )

    assert duplicate.generated_count == 0
    assert duplicate.skipped_count >= applied.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == applied.generated_count


def test_generate_cash_liquidity_route_supports_dry_run_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "portfolio_store", _FakePortfolioStore(_cash_holdings_payload(2_000.0)))
    monkeypatch.setattr(main, "financial_profile_store", _FakeFinancialProfileStore(_financial_profile_payload()))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dry_run = main.generate_cash_liquidity_recommendation_candidates(
        main.CashLiquidityRecommendationGenerateRequest(dry_run=True, plan_id="plan-1", limit=10),
    )

    assert dry_run.dry_run is True
    assert dry_run.generated_count == 1
    assert dry_run.candidates[0]["source"] == "generator:cash_liquidity"
    assert dry_run.created == []
    assert inbox.list(limit=None, status="proposed") == []

    applied = main.generate_cash_liquidity_recommendation_candidates(
        main.CashLiquidityRecommendationGenerateRequest(dry_run=False, plan_id="plan-1", limit=10),
    )

    assert applied.dry_run is False
    assert applied.generated_count == 1
    assert len(applied.created) == 1
    assert len(inbox.list(limit=None, status="proposed")) == 1


def test_generate_profile_completeness_route_supports_dry_run_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    profile = _financial_profile_payload()
    profile["expense_items"] = []
    profile["debt_items"] = []
    profile["tax_profile"] = {"filing_status": None, "marginal_tax_rate": None}
    monkeypatch.setattr(main, "financial_profile_store", _FakeFinancialProfileStore(profile))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dry_run = main.generate_profile_completeness_recommendation_candidates(
        main.ProfileCompletenessRecommendationGenerateRequest(dry_run=True, plan_id="plan-1", limit=10),
    )

    assert dry_run.dry_run is True
    assert dry_run.generated_count == 1
    assert dry_run.candidates[0]["source"] == "generator:profile_completeness"
    assert dry_run.created == []
    assert inbox.list(limit=None, status="proposed") == []

    applied = main.generate_profile_completeness_recommendation_candidates(
        main.ProfileCompletenessRecommendationGenerateRequest(dry_run=False, plan_id="plan-1", limit=10),
    )

    assert applied.dry_run is False
    assert applied.generated_count == 1
    assert len(applied.created) == 1
    assert len(inbox.list(limit=None, status="proposed")) == 1


def _plan_tracking_payload() -> dict[str, object]:
    return {
        "plan_id": "plan-1",
        "plan_title": "Primary Plan",
        "status": "behind",
        "status_detail": "Portfolio value and contributions are behind target.",
        "tracking_window_days": 90,
        "window_start": "2026-01-25T12:00:00+00:00",
        "window_end": "2026-04-25T12:00:00+00:00",
        "starting_value_usd": 100_000.0,
        "current_value_usd": 95_000.0,
        "projected_value_usd": 106_000.0,
        "value_drift_usd": -11_000.0,
        "value_drift_pct": -10.38,
        "actual_annualized_return_pct": -18.0,
        "expected_annualized_return_pct": 6.5,
        "return_drift_pct": -24.5,
        "actual_return_method": "snapshot_delta",
        "expected_return_method": "plan_setting",
        "actual_contributions_usd": 1_000.0,
        "expected_contributions_usd": 4_500.0,
        "contribution_pace_pct": 22.2,
        "market_growth_usd": -6_000.0,
        "snapshot_count": 3,
        "plan_settings": {
            "annual_contribution_usd": 18_000.0,
            "hsa_extra_contribution_usd": 0.0,
        },
        "planner_defaults": {
            "annual_contribution_usd": 18_000.0,
            "hsa_extra_contribution_usd": 1_000.0,
        },
    }


def _stale_plan_detail() -> dict[str, object]:
    return {
        "id": "plan-1",
        "title": "Primary Plan",
        "updated_at": "2025-12-15T12:00:00+00:00",
        "settings": {
            "annual_contribution_usd": 18_000.0,
            "expected_return_baseline": 0.065,
            "expected_return_optimistic": 0.095,
            "expected_return_conservative": 0.035,
            "marginal_tax_rate": None,
        },
        "decisions": [
            {
                "id": "decision-1",
                "title": "Initial assumptions",
                "created_at": "2025-12-20T12:00:00+00:00",
            }
        ],
        "artifacts": [],
    }


def _blocking_readiness_payload() -> dict[str, object]:
    return {
        "completion_percent": 58.0,
        "status": "incomplete",
        "next_gap_key": "tax_profile",
        "next_gap_title": "Tax basics",
        "next_gap_detail": "Tax basics are missing, which lowers confidence in plan and investment-fit guidance.",
        "blocking_recommendation_sources": ["tax_planning", "investment_fit"],
        "sections": [],
    }


def test_stale_assumption_factory_generates_review_and_context_candidates() -> None:
    result = generate_stale_assumption_recommendations(
        plan_detail_payload=_stale_plan_detail(),
        plan_tracking_payload={
            **_plan_tracking_payload(),
            "status": "insufficient_data",
            "snapshot_count": 1,
            "tracking_window_days": 14,
        },
        profile_readiness_payload=_blocking_readiness_payload(),
        existing_recommendations=[],
        dry_run=True,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 5
    titles = {candidate["title"] for candidate in result.candidates}
    assert "Review stale assumptions for Primary Plan" in titles
    assert "Review expected return assumptions for Primary Plan" in titles
    assert "Complete tax basics before assumption review" in titles
    assert "Refresh plan decision log for Primary Plan" in titles
    assert "Build tracking history before trusting plan confidence" in titles

    by_signal = {
        candidate["action_payload"]["generator"]["signal_key"]: candidate
        for candidate in result.candidates
    }
    stale_plan = by_signal["active_plan_stale"]
    assert stale_plan["source"] == "generator:stale_assumptions"
    assert stale_plan["action_payload"]["generator"]["dedupe_key"] == "stale_assumptions:plan-1:active_plan_stale"
    assert stale_plan["action_payload"]["quality"]["actionability"] == "review_only"
    assert stale_plan["action_payload"]["quality"]["decision_grade"] is True
    assert stale_plan["action_payload"]["evidence"]["data_keys"] == [
        "plan.detail",
        "plan.settings",
        "plan.tracking",
        "financial_profile.readiness",
    ]

    tax_context = by_signal["profile_readiness_blocking:tax_profile"]
    assert tax_context["action_payload"]["quality"]["actionability"] == "context_gathering"
    assert tax_context["action_payload"]["quality"]["decision_grade"] is False
    assert "financial_profile.tax_profile" in tax_context["action_payload"]["quality"]["blocking_context"]


def test_stale_assumption_factory_apply_skips_duplicates(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    first = generate_stale_assumption_recommendations(
        plan_detail_payload=_stale_plan_detail(),
        plan_tracking_payload=_plan_tracking_payload(),
        profile_readiness_payload=_blocking_readiness_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )
    second = generate_stale_assumption_recommendations(
        plan_detail_payload=_stale_plan_detail(),
        plan_tracking_payload=_plan_tracking_payload(),
        profile_readiness_payload=_blocking_readiness_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        now=datetime(2026, 4, 25, 12, 35, tzinfo=timezone.utc),
    )

    assert first.generated_count >= 3
    assert len(first.created) == first.generated_count
    assert second.generated_count == 0
    assert second.created == []
    assert second.skipped_count == first.generated_count
    assert {item["reason"] for item in second.skipped} == {"active_duplicate"}


def test_plan_tracking_factory_dry_run_generates_plan_specific_candidates() -> None:
    result = generate_plan_tracking_recommendations(
        plan_tracking_payload=_plan_tracking_payload(),
        existing_recommendations=[],
        dry_run=True,
        limit=10,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 3
    assert result.created == []
    titles = [candidate["title"] for candidate in result.candidates]
    assert "Increase contributions for Primary Plan" in titles
    assert "Review plan assumptions for Primary Plan" in titles
    assert "Close plan value gap for Primary Plan" in titles
    first_payload = result.candidates[0]["action_payload"]
    assert result.candidates[0]["source"] == "generator:plan_tracking"
    assert result.candidates[0]["plan_id"] == "plan-1"
    assert first_payload["generator"]["dedupe_key"].startswith("plan_tracking:plan-1:")
    assert first_payload["generator"]["signal_type"] == "plan_tracking"
    assert first_payload["evidence"]["data_keys"] == ["plan.tracking", "plan.settings", "portfolio.snapshots"]
    assert first_payload["suggested_action"]["estimated_monthly_contribution_increase_usd"] > 0
    assert first_payload["suggested_action"]["current_annual_contribution_usd"] == 18_000.0
    assert first_payload["suggested_action"]["proposed_annual_contribution_usd"] > 18_000.0
    assert first_payload["plan_settings_updates"] == {
        "annual_contribution_usd": first_payload["suggested_action"]["proposed_annual_contribution_usd"]
    }
    assert "to $" in result.candidates[0]["detail"]
    _assert_quality_metadata(result.candidates[0], expected_source="generator:plan_tracking")
    assert first_payload["quality"]["actionability"] == "previewable"
    assert first_payload["quality"]["decision_grade"] is True


def test_plan_tracking_factory_apply_creates_rows_and_skips_duplicates(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    first = generate_plan_tracking_recommendations(
        plan_tracking_payload=_plan_tracking_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=10,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert first.generated_count == 3
    assert len(first.created) == 3

    second = generate_plan_tracking_recommendations(
        plan_tracking_payload=_plan_tracking_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=10,
        now=datetime(2026, 4, 25, 12, 35, tzinfo=timezone.utc),
    )

    assert second.generated_count == 0
    assert second.created == []
    assert second.skipped_count == 3
    assert {item["reason"] for item in second.skipped} == {"active_duplicate"}
    assert len(inbox.list(limit=None, status="proposed")) == 3


def test_cash_liquidity_factory_generates_emergency_fund_shortfall() -> None:
    result = generate_cash_liquidity_recommendations(
        holdings_payload=_cash_holdings_payload(2_000.0),
        financial_profile_payload=_financial_profile_payload(),
        existing_recommendations=[],
        dry_run=True,
        plan_id="plan-1",
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["title"] == "Build emergency cash reserve"
    assert candidate["priority"] == "high"
    assert candidate["source"] == "generator:cash_liquidity"
    assert candidate["plan_id"] == "plan-1"
    payload = candidate["action_payload"]
    assert payload["generator"]["dedupe_key"] == "cash_liquidity:emergency_fund_shortfall"
    assert payload["generator"]["signal_type"] == "cash_liquidity"
    assert payload["evidence"]["data_keys"] == [
        "portfolio.holdings",
        "portfolio.cash",
        "financial_profile.expenses",
        "financial_profile.debts",
    ]
    assert payload["suggested_action"]["cash_shortfall_usd"] == 11_500.0
    assert payload["suggested_action"]["target_cash_reserve_usd"] == 13_500.0
    _assert_quality_metadata(candidate, expected_source="generator:cash_liquidity")
    assert payload["quality"]["actionability"] == "review_only"
    assert payload["quality"]["decision_grade"] is True


def test_cash_liquidity_factory_generates_excess_cash_review() -> None:
    result = generate_cash_liquidity_recommendations(
        holdings_payload=_cash_holdings_payload(80_000.0),
        financial_profile_payload=_financial_profile_payload(),
        existing_recommendations=[],
        dry_run=True,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert result.generated_count == 1
    candidate = result.candidates[0]
    assert candidate["title"] == "Review excess idle cash"
    assert candidate["priority"] == "medium"
    assert candidate["action_payload"]["suggested_action"]["excess_cash_usd"] == 53_000.0


def test_cash_liquidity_factory_apply_skips_duplicates(tmp_path: Path) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    first = generate_cash_liquidity_recommendations(
        holdings_payload=_cash_holdings_payload(2_000.0),
        financial_profile_payload=_financial_profile_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=10,
        now=datetime(2026, 4, 25, 12, 30, tzinfo=timezone.utc),
    )

    assert first.generated_count == 1
    assert len(first.created) == 1

    second = generate_cash_liquidity_recommendations(
        holdings_payload=_cash_holdings_payload(2_000.0),
        financial_profile_payload=_financial_profile_payload(),
        existing_recommendations=inbox.list(limit=None, include_archived=True, sort="none"),
        creator=inbox,
        dry_run=False,
        limit=10,
        now=datetime(2026, 4, 25, 12, 35, tzinfo=timezone.utc),
    )

    assert second.generated_count == 0
    assert second.created == []
    assert second.skipped == [
        {
            "dedupe_key": "cash_liquidity:emergency_fund_shortfall",
            "reason": "active_duplicate",
            "title": "Build emergency cash reserve",
            "signal_key": "emergency_fund_shortfall",
        }
    ]


class _FakePlanWorkspace:
    def get_active_plan_id(self) -> str:
        return "plan-1"

    def get_plan(self, plan_id: str) -> dict[str, object]:
        return {
            "id": plan_id,
            "title": "Primary Plan",
            "settings": {
                "expected_return_baseline": 0.065,
                "annual_contribution_usd": 18_000,
                "hsa_extra_contribution_usd": 0,
            },
        }


class _FakeSnapshotStore:
    def recent(self, limit: int | None = None) -> list[PortfolioSnapshot]:
        now = datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc)
        return [
            PortfolioSnapshot(
                as_of=now,
                total_value_usd=95_000,
                total_investment_usd=81_000,
                net_performance_usd=14_000,
                net_performance_percent=17.28,
            ),
            PortfolioSnapshot(
                as_of=now - timedelta(days=90),
                total_value_usd=100_000,
                total_investment_usd=80_000,
                net_performance_usd=20_000,
                net_performance_percent=25,
            ),
        ]


def test_generate_plan_tracking_route_supports_active_plan_dry_run_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "plan_workspace", _FakePlanWorkspace())
    monkeypatch.setattr(main, "snapshot_store", _FakeSnapshotStore())
    monkeypatch.setattr(main, "portfolio_store", _FakePortfolioStore(_holdings_payload()))
    monkeypatch.setattr(main, "financial_profile_store", _FakeFinancialProfileStore(_financial_profile_payload()))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dry_run = main.generate_plan_tracking_recommendation_candidates(
        main.PlanTrackingRecommendationGenerateRequest(dry_run=True, limit=2),
    )

    assert dry_run.dry_run is True
    assert dry_run.generated_count == 2
    assert dry_run.created == []
    assert all(item["source"] == "generator:plan_tracking" for item in dry_run.candidates)
    contribution_candidate = next(
        item for item in dry_run.candidates if item["action_payload"]["generator"]["signal_key"] == "contribution_pace"
    )
    assert contribution_candidate["action_payload"]["plan_settings_updates"]["annual_contribution_usd"] > 18_000
    assert inbox.list(limit=None, status="proposed") == []

    applied = main.generate_plan_tracking_recommendation_candidates(
        main.PlanTrackingRecommendationGenerateRequest(dry_run=False, limit=10),
    )

    assert applied.dry_run is False
    assert applied.generated_count >= 2
    assert len(applied.created) == applied.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == applied.generated_count


def test_generate_stale_assumptions_route_supports_dry_run_and_apply(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "plan_workspace", _FakePlanWorkspace())
    monkeypatch.setattr(main, "snapshot_store", _FakeSnapshotStore())
    monkeypatch.setattr(main, "portfolio_store", _FakePortfolioStore(_holdings_payload()))
    profile = _financial_profile_payload()
    profile["tax_profile"] = {"filing_status": None, "marginal_tax_rate": None}
    monkeypatch.setattr(main, "financial_profile_store", _FakeFinancialProfileStore(profile))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dry_run = main.generate_stale_assumption_recommendation_candidates(
        main.StaleAssumptionRecommendationGenerateRequest(dry_run=True, limit=10),
    )

    assert dry_run.dry_run is True
    assert dry_run.generated_count >= 1
    assert all(item["source"] == "generator:stale_assumptions" for item in dry_run.candidates)
    assert inbox.list(limit=None, status="proposed") == []

    applied = main.generate_stale_assumption_recommendation_candidates(
        main.StaleAssumptionRecommendationGenerateRequest(dry_run=False, limit=10),
    )

    assert applied.dry_run is False
    assert applied.generated_count == dry_run.generated_count
    assert len(applied.created) == applied.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == applied.generated_count


def test_run_all_recommendation_factories_groups_results_and_applies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "plan_workspace", _FakePlanWorkspace())
    monkeypatch.setattr(main, "snapshot_store", _FakeSnapshotStore())
    monkeypatch.setattr(main, "portfolio_store", _FakePortfolioStore(_holdings_payload()))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dry_run = main.run_all_recommendation_factories(
        main.RecommendationFactoryRunAllRequest(dry_run=True, limit=2),
    )

    assert dry_run.dry_run is True
    assert dry_run.errors == []
    assert dry_run.factory_count == 6
    assert set(dry_run.factories) == {
        "portfolio_risk",
        "plan_tracking",
        "cash_liquidity",
        "profile_completeness",
        "stale_assumptions",
        "watchlist_research",
    }
    assert dry_run.factories["portfolio_risk"].generated_count == 2
    assert dry_run.factories["plan_tracking"].generated_count == 2
    assert dry_run.factories["cash_liquidity"].generated_count == 1
    assert dry_run.factories["profile_completeness"].generated_count == 1
    assert dry_run.factories["stale_assumptions"].generated_count >= 1
    assert dry_run.factories["watchlist_research"].generated_count == 0
    assert dry_run.generated_count >= 7
    assert inbox.list(limit=None, status="proposed") == []

    applied = main.run_all_recommendation_factories(
        main.RecommendationFactoryRunAllRequest(dry_run=False, limit=2),
    )

    assert applied.dry_run is False
    assert applied.factory_count == 6
    assert applied.errors == []
    assert applied.generated_count == dry_run.generated_count
    assert len(inbox.list(limit=None, status="proposed")) == applied.generated_count


class _NoActivePlanWorkspace:
    def get_active_plan_id(self) -> str | None:
        return None


def test_run_all_recommendation_factories_keeps_portfolio_results_when_plan_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "plan_workspace", _NoActivePlanWorkspace())
    monkeypatch.setattr(main, "portfolio_store", _FakePortfolioStore(_holdings_payload()))
    monkeypatch.setattr(main, "financial_profile_store", _FakeFinancialProfileStore(_financial_profile_payload()))
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    response = main.run_all_recommendation_factories(
        main.RecommendationFactoryRunAllRequest(dry_run=True, limit=2),
    )

    assert response.factory_count == 4
    assert set(response.factories) == {
        "portfolio_risk",
        "cash_liquidity",
        "profile_completeness",
        "watchlist_research",
    }
    assert response.generated_count == 4
    assert response.errors == [
        {
            "factory": "plan_tracking",
            "reason": "No active plan is configured and no plan_id was provided.",
        },
        {
            "factory": "stale_assumptions",
            "reason": "No active plan is configured and no plan_id was provided.",
        },
    ]

from datetime import datetime, timezone

from buildwealth_orchestrator.schemas import Holding, PortfolioSnapshot, ResearchEvidencePacket
from buildwealth_orchestrator.services.portfolio_fit import assess_portfolio_fit
import buildwealth_orchestrator.main as main


def _snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        as_of=datetime(2026, 4, 26, tzinfo=timezone.utc),
        base_currency="USD",
        total_value_usd=100_000.0,
        total_investment_usd=100_000.0,
        holdings=[
            Holding(symbol="AAPL", name="Apple", value_usd=40_000.0, allocation_percent=40.0),
            Holding(symbol="VTI", name="Total Market", value_usd=35_000.0, allocation_percent=35.0),
            Holding(symbol="VXUS", name="International", value_usd=25_000.0, allocation_percent=25.0),
        ],
    )


def _packet(symbol: str = "AAPL", *, status: str = "fresh", confidence: str = "high") -> ResearchEvidencePacket:
    return ResearchEvidencePacket(
        packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
        symbol=symbol,
        provider="yfinance",
        period="6mo",
        interval="1d",
        generated_at=datetime(2026, 4, 26, tzinfo=timezone.utc),
        coverage={"quote_available": True, "history_available": True, "warnings": []},
        freshness={"status": status},
        metrics={"last_price": 100.0, "period_change_pct": 12.0, "volatility_pct": 18.0},
        risk={"drawdown_from_high_pct": -5.0},
        quality={"confidence": confidence, "coverage_score": 100.0, "blocking_gaps": []},
        provenance={"warnings": []},
    )


def test_portfolio_fit_flags_concentration_conflict_for_existing_large_holding() -> None:
    result = assess_portfolio_fit(
        symbol="AAPL",
        amount_usd=10_000.0,
        evidence_packet=_packet("AAPL"),
        snapshot=_snapshot(),
        holdings_payload={
            "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
            "total_cash": 50_000.0,
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    assert result.fit_status == "does_not_fit"
    assert result.simulation_required is True
    assert result.recommended_next_step == "review_concentration"
    assert "AAPL already represents 40.0% of the portfolio." in result.fit_risks
    assert result.portfolio_impact["existing_position"] is True
    assert result.portfolio_impact["simulated_concentration_change"] == "unchanged"
    assert result.evidence["packet_id"] == "research-evidence:yfinance:AAPL:6mo:1d"


def test_portfolio_fit_blocks_when_context_is_missing() -> None:
    result = assess_portfolio_fit(
        symbol="NVDA",
        amount_usd=5_000.0,
        evidence_packet=_packet("NVDA", status="partial", confidence="medium"),
        snapshot=_snapshot(),
        holdings_payload={"risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}}},
        profile_readiness_payload={
            "status": "incomplete",
            "completion_percent": 62.0,
            "next_gap_key": "risk_profile",
            "next_gap_title": "Risk profile",
        },
        emergency_fund_months=1.8,
    )

    assert result.fit_status == "needs_more_context"
    assert result.recommended_next_step == "update_profile"
    assert "profile:risk_profile" in result.blocking_gaps
    assert "cash_runway" in result.blocking_gaps
    assert "research:partial" in result.blocking_gaps
    assert any("Emergency fund runway is below 3 months" in risk for risk in result.fit_risks)


def test_portfolio_fit_marks_small_new_position_as_mixed_not_buy_advice() -> None:
    result = assess_portfolio_fit(
        symbol="MSFT",
        amount_usd=2_000.0,
        evidence_packet=_packet("MSFT"),
        snapshot=_snapshot(),
        holdings_payload={
            "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
            "total_cash": 25_000.0,
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 96.0},
        emergency_fund_months=7.0,
    )

    assert result.fit_status == "mixed"
    assert result.recommended_next_step == "simulate_trade"
    assert result.simulation_required is True
    assert "MSFT is not currently held, so it may add diversification." in result.fit_reasons
    joined = " ".join([*result.fit_reasons, *result.fit_risks, result.recommended_next_step])
    assert "buy " not in joined.lower()


def test_portfolio_fit_includes_active_plan_time_horizon_context() -> None:
    result = assess_portfolio_fit(
        symbol="MSFT",
        amount_usd=2_000.0,
        evidence_packet=_packet("MSFT"),
        snapshot=_snapshot(),
        holdings_payload={
            "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
            "total_cash": 25_000.0,
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 96.0},
        emergency_fund_months=7.0,
        active_plan_detail={
            "id": "plan-long",
            "title": "Long Horizon Plan",
            "settings": {"years": 25, "expected_return_baseline": 0.07},
            "timeline": {"retirement": {"target_retirement_age": 65}},
        },
    )

    assert result.plan_impact["plan_id"] == "plan-long"
    assert result.plan_impact["title"] == "Long Horizon Plan"
    assert result.plan_impact["years"] == 25
    assert result.plan_impact["time_horizon"] == "long"
    assert "Active plan horizon is long (25 years)." in result.fit_reasons


def test_portfolio_fit_blocks_when_active_plan_horizon_missing() -> None:
    result = assess_portfolio_fit(
        symbol="MSFT",
        amount_usd=2_000.0,
        evidence_packet=_packet("MSFT"),
        snapshot=_snapshot(),
        holdings_payload={"risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}}},
        profile_readiness_payload={"status": "ready", "completion_percent": 96.0},
        emergency_fund_months=7.0,
        active_plan_detail={"id": "plan-weak", "title": "Plan Without Horizon", "settings": {}},
    )

    assert result.fit_status == "needs_more_context"
    assert result.recommended_next_step == "update_profile"
    assert "plan:time_horizon" in result.blocking_gaps
    assert "Active plan is missing time-horizon assumptions needed for investment fit." in result.fit_risks


def test_build_portfolio_fit_assessment_payload_assembles_context(monkeypatch) -> None:
    class FakeSnapshotStore:
        def latest(self) -> PortfolioSnapshot:
            return _snapshot()

    class FakePortfolioStore:
        def get_holdings(self) -> dict[str, object]:
            return {
                "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
                "total_cash": 25_000.0,
            }

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str, interval: str) -> ResearchEvidencePacket:
            assert symbol == "MSFT"
            assert period == "6mo"
            assert interval == "1d"
            return _packet("MSFT")

    class FakeHealth:
        emergency_fund_months = 7.0

    monkeypatch.setattr(main, "snapshot_store", FakeSnapshotStore())
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    monkeypatch.setattr(
        main,
        "get_financial_profile_payload",
        lambda: {
            "income_items": [{"id": "income-1"}],
            "expense_items": [{"id": "expense-1"}],
            "goal_items": [{"id": "goal-1"}],
            "physical_assets": [{"id": "asset-1"}],
            "flags": {"no_debt": True},
            "tax_profile": {"filing_status": "single", "marginal_tax_rate": 0.24},
        },
    )
    monkeypatch.setattr(main, "get_financial_health", lambda: FakeHealth())
    monkeypatch.setattr(
        main,
        "resolve_active_plan_detail",
        lambda: {
            "id": "plan-long",
            "title": "Long Horizon Plan",
            "settings": {"years": 25, "expected_return_baseline": 0.07},
        },
    )

    result = main.build_portfolio_fit_assessment_payload(
        main.PortfolioFitAssessmentRequest(symbol="msft", amount_usd=2_000.0)
    )

    assert result.symbol == "MSFT"
    assert result.evidence["packet_id"] == "research-evidence:yfinance:MSFT:6mo:1d"
    assert result.portfolio_impact["amount_usd"] == 2_000.0
    assert result.plan_impact["plan_id"] == "plan-long"
    assert result.plan_impact["time_horizon"] == "long"
    assert result.recommended_next_step == "simulate_trade"

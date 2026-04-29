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


def _packet(
    symbol: str = "AAPL",
    *,
    status: str = "fresh",
    confidence: str = "high",
    sector: str | None = None,
) -> ResearchEvidencePacket:
    return ResearchEvidencePacket(
        packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
        symbol=symbol,
        sector=sector,
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


def test_portfolio_fit_uses_personal_investment_policy_single_symbol_cap() -> None:
    result = assess_portfolio_fit(
        symbol="MSFT",
        amount_usd=20_000.0,
        evidence_packet=_packet("MSFT"),
        snapshot=_snapshot(),
        holdings_payload={
            "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
            "investment_policy": {
                "max_single_symbol_exposure_pct": 10.0,
                "minimum_research_confidence": "medium",
            },
            "total_cash": 50_000.0,
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    assert result.fit_status == "does_not_fit"
    assert result.recommended_next_step == "review_concentration"
    assert "concentration" in result.blocking_gaps
    assert result.portfolio_impact["single_holding_max_pct"] == 10.0
    assert result.portfolio_impact["single_holding_policy_source"] == "profile.investment_policy"
    assert result.portfolio_impact["simulated_symbol_weight_pct"] == 16.67
    assert any("personal policy cap is 10.0%" in risk for risk in result.fit_risks)


def test_portfolio_fit_blocks_when_research_confidence_below_personal_policy() -> None:
    result = assess_portfolio_fit(
        symbol="MSFT",
        amount_usd=2_000.0,
        evidence_packet=_packet("MSFT", confidence="medium"),
        snapshot=_snapshot(),
        holdings_payload={
            "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
            "investment_policy": {
                "minimum_research_confidence": "high",
            },
            "total_cash": 50_000.0,
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    assert result.fit_status == "needs_more_context"
    assert result.recommended_next_step == "research_more"
    assert "research:confidence_policy" in result.blocking_gaps
    assert result.portfolio_impact["investment_policy"]["minimum_research_confidence"] == "high"
    assert any("below personal policy minimum high" in risk for risk in result.fit_risks)


def test_portfolio_fit_applies_high_tax_sensitivity_to_taxable_exposure() -> None:
    result = assess_portfolio_fit(
        symbol="AAPL",
        amount_usd=2_000.0,
        evidence_packet=_packet("AAPL"),
        snapshot=_snapshot(),
        holdings_payload={
            "accounts": [
                {"id": "default", "name": "Taxable Brokerage", "type": "taxable"},
            ],
            "holdings": {
                "default:AAPL": {
                    "symbol": "AAPL",
                    "account": "default",
                    "quantity": 10,
                    "current_value": 3_000.0,
                    "cost_basis": 2_000.0,
                    "lots": [
                        {
                            "lot_id": "lot-long",
                            "acquired_date": "2024-01-15",
                            "remaining_quantity": 10,
                            "unit_cost": 200.0,
                        },
                    ],
                },
            },
            "risk_policy": {"thresholds": {"single_holding_max_pct": 60.0}},
            "investment_policy": {
                "tax_sensitivity": "high",
            },
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    assert result.fit_status == "mixed"
    assert result.recommended_next_step == "discuss_in_copilot"
    assert "tax:policy_review" in result.blocking_gaps
    assert result.portfolio_impact["investment_policy"]["tax_sensitivity"] == "high"
    assert any("Personal tax sensitivity is high" in risk for risk in result.fit_risks)


def test_portfolio_fit_blocks_restricted_symbol_from_personal_policy() -> None:
    result = assess_portfolio_fit(
        symbol="NVDA",
        amount_usd=2_000.0,
        evidence_packet=_packet("NVDA", sector="Technology"),
        snapshot=_snapshot(),
        holdings_payload={
            "risk_policy": {"thresholds": {"single_holding_max_pct": 60.0}},
            "investment_policy": {
                "restricted_symbols": ["NVDA"],
                "restricted_sectors": [],
            },
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    assert result.fit_status == "does_not_fit"
    assert result.recommended_next_step == "review_policy_restriction"
    assert "policy:restricted_symbol" in result.blocking_gaps
    assert result.portfolio_impact["investment_policy"]["restricted_symbols"] == ["NVDA"]
    assert any("personal investment policy restricts NVDA" in risk for risk in result.fit_risks)


def test_portfolio_fit_blocks_sector_exposure_above_personal_policy_cap() -> None:
    snapshot = PortfolioSnapshot(
        as_of=datetime(2026, 4, 26, tzinfo=timezone.utc),
        base_currency="USD",
        total_value_usd=100_000.0,
        total_investment_usd=100_000.0,
        holdings=[
            Holding(symbol="AAPL", name="Apple", sector="Technology", value_usd=28_000.0, allocation_percent=28.0),
            Holding(symbol="VTI", name="Total Market", sector="Diversified", value_usd=45_000.0, allocation_percent=45.0),
            Holding(symbol="VXUS", name="International", sector="Diversified", value_usd=27_000.0, allocation_percent=27.0),
        ],
    )

    result = assess_portfolio_fit(
        symbol="MSFT",
        amount_usd=5_000.0,
        evidence_packet=_packet("MSFT", sector="Technology"),
        snapshot=snapshot,
        holdings_payload={
            "risk_policy": {"thresholds": {"single_holding_max_pct": 60.0}},
            "investment_policy": {
                "max_sector_exposure_pct": 30.0,
            },
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    assert result.fit_status == "does_not_fit"
    assert result.recommended_next_step == "review_sector_exposure"
    assert "sector:policy_cap" in result.blocking_gaps
    assert result.portfolio_impact["candidate_sector"] == "Technology"
    assert result.portfolio_impact["sector_policy_source"] == "profile.investment_policy"
    assert result.portfolio_impact["sector_weight_after_trade_pct"] == 31.43
    assert any("Technology exposure would be 31.4%" in risk for risk in result.fit_risks)


def test_portfolio_fit_includes_account_location_and_tax_lot_context() -> None:
    result = assess_portfolio_fit(
        symbol="AAPL",
        amount_usd=5_000.0,
        evidence_packet=_packet("AAPL"),
        snapshot=_snapshot(),
        holdings_payload={
            "accounts": [
                {"id": "default", "name": "Taxable Brokerage", "type": "taxable"},
                {"id": "roth", "name": "Roth IRA", "type": "roth_ira"},
            ],
            "holdings": {
                "default:AAPL": {
                    "symbol": "AAPL",
                    "account": "default",
                    "quantity": 10,
                    "current_value": 3_000.0,
                    "cost_basis": 2_000.0,
                    "cost_basis_method": "FIFO",
                    "lots": [
                        {
                            "lot_id": "lot-long",
                            "acquired_date": "2024-01-15",
                            "remaining_quantity": 6,
                            "unit_cost": 100.0,
                        },
                        {
                            "lot_id": "lot-short",
                            "acquired_date": "2026-01-20",
                            "remaining_quantity": 4,
                            "unit_cost": 350.0,
                        },
                    ],
                },
                "roth:AAPL": {
                    "symbol": "AAPL",
                    "account": "roth",
                    "quantity": 5,
                    "current_value": 1_000.0,
                    "cost_basis": 900.0,
                    "lots": [
                        {
                            "lot_id": "lot-roth",
                            "acquired_date": "2025-01-01",
                            "remaining_quantity": 5,
                            "unit_cost": 180.0,
                        }
                    ],
                },
            },
            "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    account_location = result.portfolio_impact["account_location"]
    assert account_location["status"] == "known"
    assert account_location["tax_lot_coverage"] == "known"
    assert account_location["confidence_gap"] is False
    assert account_location["tax_treatments"] == ["tax_free", "taxable"]
    assert len(account_location["accounts"]) == 2
    taxable = next(item for item in account_location["accounts"] if item["account_id"] == "default")
    assert taxable["account_name"] == "Taxable Brokerage"
    assert taxable["account_type"] == "taxableBrokerage"
    assert taxable["tax_treatment"] == "taxable"
    assert taxable["unrealized_gain_loss_usd"] == 1000.0
    assert taxable["unrealized_gain_loss_pct"] == 50.0
    assert taxable["lot_term_mix"] == "mixed"
    assert any("taxable" in risk.lower() for risk in result.fit_risks)


def test_portfolio_fit_flags_missing_account_location_as_confidence_gap() -> None:
    result = assess_portfolio_fit(
        symbol="AAPL",
        amount_usd=5_000.0,
        evidence_packet=_packet("AAPL"),
        snapshot=_snapshot(),
        holdings_payload={
            "holdings": {
                "mystery:AAPL": {
                    "symbol": "AAPL",
                    "account": "mystery",
                    "quantity": 10,
                    "current_value": 3_000.0,
                    "cost_basis": 2_000.0,
                    "lots": [],
                },
            },
            "risk_policy": {"thresholds": {"single_holding_max_pct": 35.0}},
        },
        profile_readiness_payload={"status": "ready", "completion_percent": 100.0},
        emergency_fund_months=8.0,
    )

    account_location = result.portfolio_impact["account_location"]
    assert account_location["status"] == "partial"
    assert account_location["tax_lot_coverage"] == "missing"
    assert account_location["confidence_gap"] is True
    assert "tax:account_location" in result.blocking_gaps
    assert "tax:lots" in result.blocking_gaps
    assert any("Account location or tax-lot context is incomplete" in risk for risk in result.fit_risks)


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
            "investment_policy": {
                "max_single_symbol_exposure_pct": 12.0,
                "minimum_research_confidence": "medium",
            },
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
    assert result.portfolio_impact["single_holding_max_pct"] == 12.0
    assert result.portfolio_impact["single_holding_policy_source"] == "profile.investment_policy"
    assert result.plan_impact["plan_id"] == "plan-long"
    assert result.plan_impact["time_horizon"] == "long"
    assert result.recommended_next_step == "simulate_trade"

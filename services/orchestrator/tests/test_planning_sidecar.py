import asyncio
import json

import httpx

from buildwealth_orchestrator.services.engine_adapter import SidecarAdapter
from buildwealth_orchestrator.services.planning_sidecar import IgnidashScenarioService
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine


def _build_scenario_engine() -> ScenarioEngine:
    return ScenarioEngine(
        years_to_retirement=30,
        annual_contribution_usd=12000,
        baseline_return=0.06,
        optimistic_return=0.08,
        conservative_return=0.04,
        return_volatility=0.12,
        inflation=0.025,
        monte_carlo_runs=200,
        hsa_delta_default=1000,
        marginal_tax_rate=0.25,
    )


def test_ignidash_sidecar_service_returns_local_when_disabled() -> None:
    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=None,
        sidecar_enabled=False,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(service.run(current_portfolio_value_usd=100000))

    assert len(result.scenarios) == 4
    assert result.engine == "local"
    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.warnings == []


def test_ignidash_sidecar_service_merges_sidecar_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["contract_version"] == 1
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine": "ignidash",
                "engine_status": "ok",
                "fallback_method": None,
                "scenarios": [
                    {
                        "scenario_id": "baseline",
                        "label": "baseline",
                        "summary": {
                            "ending_balance_nominal": 1000000,
                            "ending_balance_real": 700000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "optimistic",
                        "label": "optimistic",
                        "summary": {
                            "ending_balance_nominal": 1200000,
                            "ending_balance_real": 850000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "conservative",
                        "label": "conservative",
                        "summary": {
                            "ending_balance_nominal": 800000,
                            "ending_balance_real": 560000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "hsa_delta",
                        "label": "hsa_delta",
                        "summary": {
                            "ending_balance_nominal": 1030000,
                            "ending_balance_real": 721000,
                        },
                        "timeline": [],
                    },
                ],
                "warnings": [],
                "generated_at": "2026-04-10T13:00:00Z",
            },
        )

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(service.run(current_portfolio_value_usd=100000))

    assert result.engine == "ignidash"
    assert result.engine_status == "ok"
    by_label = {scenario.label: scenario for scenario in result.scenarios}
    assert by_label["baseline"].future_value_usd == 1000000
    assert by_label["optimistic"].real_value_usd == 850000


def test_ignidash_sidecar_service_falls_back_on_sidecar_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": "temporary outage"})

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(service.run(current_portfolio_value_usd=100000))

    assert result.engine == "local"
    assert result.engine_status == "degraded"
    assert result.fallback_method == "local_scenario_engine_fallback"
    assert any("sidecar unavailable" in warning.lower() for warning in result.warnings)


def test_ignidash_sidecar_service_skips_sidecar_when_contract_guarded() -> None:
    calls = {"count": 0}

    def handler(_: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(status_code=200, json={})

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(
        service.run(
            current_portfolio_value_usd=100000,
            sidecar_guard_reason="Sidecar contract version mismatch (expected v1, got v2)",
        )
    )

    assert calls["count"] == 0
    assert result.engine == "local"
    assert result.engine_status == "degraded"
    assert result.fallback_method == "contract_version_guard"
    assert any("sidecar skipped" in warning.lower() for warning in result.warnings)


def test_ignidash_sidecar_service_uses_account_allocation_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        accounts = payload["accounts"]
        assert len(accounts) == 2
        assert payload["baseline_assumptions"]["annual_income"] == 130000
        assert payload["baseline_assumptions"]["annual_expenses"] == 66000
        assert payload["baseline_assumptions"]["annual_debt_payments"] == 11000
        assert accounts[0]["account_id"] == "acct-401k"
        assert accounts[0]["account_type"] == "401k"
        assert accounts[0]["tax_treatment"] == "tax_deferred"
        assert accounts[0]["annual_contribution"] == 18000
        assert payload["metadata"]["income_projection"]["first_year_gross_income_usd"] == 125000
        assert payload["metadata"]["expense_projection"]["first_year_expenses_usd"] == 64000
        assert payload["metadata"]["debt_projection"]["selected_scenario"]["first_year_payments_usd"] == 10000
        assert payload["metadata"]["timeline_projection"]["first_year_income_impact_usd"] == 5000
        assert payload["metadata"]["contribution_allocation"]["total_contributions_usd"] == 22000
        assert payload["metadata"]["social_security_projection"]["selected_annual_benefit_usd"] == 18000
        assert payload["metadata"]["rmd_projection"]["rmd_start_age"] == 75
        assert payload["metadata"]["filing_status"] == "single"
        assert payload["metadata"]["state_tax_rate"] == 0.05
        assert payload["metadata"]["include_irmaa"] is False
        assert payload["metadata"]["roth_conversion_annual_amount_usd"] == 12000.0
        assert payload["metadata"]["roth_conversion_start_age"] == 60
        assert payload["metadata"]["roth_conversion_end_age"] == 72
        assert payload["metadata"]["drawdown_order"] == "tax_deferred, taxable, tax_free, cash"
        assert payload["metadata"]["household_mode"] == "couple"
        assert payload["metadata"]["household_partner_income_usd"] == 90000.0
        assert payload["metadata"]["household_partner_income_growth_rate"] == 0.03
        assert payload["metadata"]["household_partner_retirement_age"] == 65
        assert payload["metadata"]["household_partner_social_security_annual_usd"] == 24000.0
        assert payload["metadata"]["household_partner_social_security_claiming_age"] == 67
        assert payload["metadata"]["household_shared_goal_target_usd"] == 150000.0
        assert payload["metadata"]["household_shared_goal_target_year"] == 2035
        assert payload["metadata"]["household_shared_goal_annual_funding_usd"] == 10000.0
        assert payload["metadata"]["household_partner_income_added_first_year_usd"] == 90000.0
        assert payload["metadata"]["household_partner_income_added_total_usd"] == 920000.0
        assert payload["metadata"]["withdrawal_strategy"] == "4_percent_rule"
        assert payload["metadata"]["retirement_age"] == 60
        assert payload["metadata"]["simulation_mode"] == "historical"
        assert payload["metadata"]["simulation_monte_carlo_variant"] == "p10"
        assert payload["metadata"]["simulation_historical_start_year"] == 1972
        assert payload["metadata"]["simulation_seed"] == 314159
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine": "ignidash",
                "engine_status": "ok",
                "fallback_method": None,
                "scenarios": [
                    {
                        "scenario_id": "baseline",
                        "label": "baseline",
                        "summary": {
                            "ending_balance_nominal": 1000000,
                            "ending_balance_real": 700000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "optimistic",
                        "label": "optimistic",
                        "summary": {
                            "ending_balance_nominal": 1200000,
                            "ending_balance_real": 850000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "conservative",
                        "label": "conservative",
                        "summary": {
                            "ending_balance_nominal": 800000,
                            "ending_balance_real": 560000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "hsa_delta",
                        "label": "hsa_delta",
                        "summary": {
                            "ending_balance_nominal": 1030000,
                            "ending_balance_real": 721000,
                        },
                        "timeline": [],
                    },
                ],
                "warnings": [],
                "generated_at": "2026-04-10T13:00:00Z",
            },
        )

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(
        service.run(
            current_portfolio_value_usd=100000,
            annual_contribution_usd=22000,
            accounts=[
                {
                    "account_id": "acct-401k",
                    "account_type": "401k",
                    "balance_usd": 120000,
                    "annual_contribution_usd": 18000,
                },
                {
                    "account_id": "acct-taxable",
                    "account_type": "taxableBrokerage",
                    "balance_usd": 50000,
                    "annual_contribution_usd": 4000,
                },
            ],
            income_projection={
                "start_year": 2026,
                "years": 30,
                "default_annual_growth_rate": 0.03,
                "income_items_count": 1,
                "first_year_gross_income_usd": 125000,
                "final_year_gross_income_usd": 280000,
                "cumulative_gross_income_usd": 5800000,
                "annualized_income_growth_rate": 0.028,
                "yearly_points": [],
                "warnings": [],
            },
            expense_projection={
                "start_year": 2026,
                "years": 30,
                "default_inflation_rate": 0.03,
                "expense_items_count": 2,
                "first_year_expenses_usd": 64000,
                "final_year_expenses_usd": 130000,
                "cumulative_expenses_usd": 2400000,
                "annualized_expense_growth_rate": 0.024,
                "yearly_points": [],
                "warnings": [],
            },
            debt_projection={
                "start_date": "2026-01-01",
                "max_years": 30,
                "debt_items_count": 1,
                "strategy": "avalanche",
                "monthly_accelerated_payment_usd": 0,
                "minimum_scenario": {
                    "strategy": "minimum",
                    "months_to_payoff": 48,
                    "payoff_date": "2029-12-01",
                    "paid_off": True,
                    "remaining_balance_usd": 0,
                    "total_interest_paid_usd": 2500,
                    "total_principal_paid_usd": 20000,
                    "total_paid_usd": 22500,
                    "first_year_payments_usd": 9000,
                    "month_points": [],
                    "debt_summaries": [],
                    "warnings": [],
                },
                "selected_scenario": {
                    "strategy": "avalanche",
                    "months_to_payoff": 42,
                    "payoff_date": "2029-06-01",
                    "paid_off": True,
                    "remaining_balance_usd": 0,
                    "total_interest_paid_usd": 2100,
                    "total_principal_paid_usd": 20000,
                    "total_paid_usd": 22100,
                    "first_year_payments_usd": 10000,
                    "month_points": [],
                    "debt_summaries": [],
                    "warnings": [],
                },
                "payoff_months_saved_vs_minimum": 6,
                "interest_saved_vs_minimum_usd": 400,
                "warnings": [],
            },
            timeline_projection={
                "start_year": 2026,
                "years": 30,
                "events_count": 2,
                "first_year_income_impact_usd": 5000,
                "first_year_expense_impact_usd": 2000,
                "first_year_portfolio_impact_usd": -10000,
                "first_year_contribution_impact_usd": 1000,
                "first_year_debt_payment_impact_usd": 1000,
                "cumulative_net_cashflow_impact_usd": -40000,
                "yearly_points": [],
                "warnings": [],
            },
            contribution_allocation={
                "profile_id": "tax_optimized_high_earner",
                "base_rule_type": "save",
                "annual_contribution_target_usd": 22000,
                "employee_contributions_usd": 22000,
                "employer_match_usd": 0,
                "total_contributions_usd": 22000,
                "unallocated_contribution_usd": 0,
                "allocations": [],
                "rule_results": [],
                "warnings": [],
            },
            social_security_projection={
                "start_year": 2026,
                "years": 30,
                "current_age": 35,
                "birth_year": None,
                "fra_age": 67.0,
                "life_expectancy_age": 90,
                "selected_claiming_age": 67,
                "optimal_claiming_age": 70,
                "fra_monthly_benefit_usd": 1500,
                "estimated_aime_usd": 4000,
                "estimated_pia_monthly_usd": 1500,
                "selected_monthly_benefit_usd": 1500,
                "selected_annual_benefit_usd": 18000,
                "cola_rate": 0.02,
                "pia_bend_point_1_usd": 1226,
                "pia_bend_point_2_usd": 7391,
                "claim_options": [],
                "yearly_points": [
                    {
                        "year": 2026,
                        "age": 67,
                        "annual_benefit_usd": 18000,
                        "cumulative_benefits_usd": 18000,
                    }
                ],
                "warnings": [],
            },
            rmd_projection={
                "start_year": 2026,
                "years": 30,
                "current_age": 35,
                "birth_year": 1960,
                "rmd_start_age": 75,
                "expected_return": 0.06,
                "eligible_account_count": 1,
                "total_initial_eligible_balance_usd": 120000,
                "total_projected_rmds_usd": 350000,
                "yearly_points": [],
                "warnings": [],
            },
            filing_status="single",
            state_tax_rate=0.05,
            include_irmaa=False,
            roth_conversion_annual_amount_usd=12000,
            roth_conversion_start_age=60,
            roth_conversion_end_age=72,
            drawdown_order=["tax_deferred", "taxable", "tax_free", "cash"],
            household_mode="couple",
            household_partner_income_usd=90000,
            household_partner_income_growth_rate=0.03,
            household_partner_retirement_age=65,
            household_partner_social_security_annual_usd=24000,
            household_partner_social_security_claiming_age=67,
            household_shared_goal_target_usd=150000,
            household_shared_goal_target_year=2035,
            household_shared_goal_annual_funding_usd=10000,
            household_partner_income_added_first_year_usd=90000,
            household_partner_income_added_total_usd=920000,
            withdrawal_strategy="4_percent_rule",
            retirement_age=60,
            simulation_mode="historical",
            simulation_monte_carlo_variant="p10",
            simulation_historical_start_year=1972,
            simulation_seed=314159,
        )
    )

    assert result.engine == "ignidash"
    assert result.income_projection is not None
    assert result.income_projection.first_year_gross_income_usd == 125000
    assert result.expense_projection is not None
    assert result.expense_projection.first_year_expenses_usd == 64000
    assert result.debt_projection is not None
    assert result.debt_projection.selected_scenario.first_year_payments_usd == 10000
    assert result.timeline_projection is not None
    assert result.timeline_projection.first_year_income_impact_usd == 5000
    assert result.contribution_allocation is not None
    assert result.contribution_allocation.total_contributions_usd == 22000
    assert result.social_security_projection is not None
    assert result.social_security_projection.selected_annual_benefit_usd == 18000
    assert result.rmd_projection is not None
    assert result.rmd_projection.rmd_start_age == 75
    assert result.simulation["mode"] == "historical"
    assert result.simulation["monte_carlo_variant"] == "p10"
    assert result.simulation["requested_historical_start_year"] == 1972
    assert result.simulation["seed"] == 314159


def test_ignidash_sidecar_service_forwards_assumption_set_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["metadata"]["assumption_set_id"] == "stagflation"
        assert payload["metadata"]["assumption_set_name"] == "Stagflation"
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine": "ignidash",
                "engine_status": "ok",
                "fallback_method": None,
                "scenarios": [
                    {
                        "scenario_id": "baseline",
                        "label": "baseline",
                        "summary": {
                            "ending_balance_nominal": 1000000,
                            "ending_balance_real": 700000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "optimistic",
                        "label": "optimistic",
                        "summary": {
                            "ending_balance_nominal": 1200000,
                            "ending_balance_real": 850000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "conservative",
                        "label": "conservative",
                        "summary": {
                            "ending_balance_nominal": 800000,
                            "ending_balance_real": 560000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "hsa_delta",
                        "label": "hsa_delta",
                        "summary": {
                            "ending_balance_nominal": 1030000,
                            "ending_balance_real": 721000,
                        },
                        "timeline": [],
                    },
                ],
                "warnings": [],
                "generated_at": "2026-04-10T13:00:00Z",
            },
        )

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(
        service.run(
            current_portfolio_value_usd=100000,
            assumption_set_id="stagflation",
            assumption_set_name="Stagflation",
        )
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    assert baseline.assumptions["assumption_set_id"] == "stagflation"
    assert baseline.assumptions["assumption_set_name"] == "Stagflation"

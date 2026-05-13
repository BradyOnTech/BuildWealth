import asyncio

from buildwealth_orchestrator.services.plan_simulation_service import BuildWealthScenarioService
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


def _build_service() -> BuildWealthScenarioService:
    return BuildWealthScenarioService(scenario_engine=_build_scenario_engine())


def test_plan_simulation_service_returns_native_simulation() -> None:
    result = asyncio.run(_build_service().run(current_portfolio_value_usd=100000))

    assert len(result.scenarios) == 4
    assert result.engine == "local"
    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.warnings == []


def test_plan_simulation_service_local_path_preserves_projection_payloads() -> None:
    result = asyncio.run(
        _build_service().run(
            current_portfolio_value_usd=100000,
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
        )
    )

    assert result.engine == "local"
    assert result.engine_status == "ok"
    assert result.income_projection is not None
    assert result.income_projection.first_year_gross_income_usd == 125000
    assert result.expense_projection is not None
    assert result.expense_projection.first_year_expenses_usd == 64000


def test_plan_simulation_service_uses_account_allocation_and_planning_controls() -> None:
    result = asyncio.run(
        _build_service().run(
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
            withdrawal_strategy="4_percent_rule",
            retirement_age=60,
            simulation_mode="historical",
            simulation_monte_carlo_variant="p10",
            simulation_historical_start_year=1972,
            simulation_seed=314159,
        )
    )

    assert result.engine == "local"
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

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    assert baseline.assumptions["account_count"] == 3
    assert baseline.assumptions["annual_contribution_usd"] == 22000
    assert baseline.assumptions["state_tax_rate"] == 0.05
    assert baseline.assumptions["include_irmaa"] is False
    assert baseline.assumptions["roth_conversion_annual_amount_usd"] == 12000
    assert baseline.assumptions["roth_conversion_start_age"] == 60
    assert baseline.assumptions["roth_conversion_end_age"] == 72
    assert baseline.assumptions["drawdown_order"] == "tax_deferred,taxable,tax_free,cash"
    assert baseline.assumptions["withdrawal_strategy"] == "four_percent_rule"
    assert baseline.assumptions["retirement_age"] == 60
    assert {point.account_id for point in baseline.account_balance_points} == {
        "acct-401k",
        "acct-taxable",
        "synthetic-roth-conversion",
    }


def test_plan_simulation_service_forwards_assumption_set_metadata() -> None:
    result = asyncio.run(
        _build_service().run(
            current_portfolio_value_usd=100000,
            assumption_set_id="stagflation",
            assumption_set_name="Stagflation",
        )
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    assert baseline.assumptions["assumption_set_id"] == "stagflation"
    assert baseline.assumptions["assumption_set_name"] == "Stagflation"

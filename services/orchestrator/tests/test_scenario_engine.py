from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine


def test_scenario_engine_returns_four_scenarios() -> None:
    engine = ScenarioEngine(
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

    result = engine.run(current_portfolio_value_usd=100000)

    assert len(result.scenarios) == 4
    labels = {scenario.label for scenario in result.scenarios}
    assert labels == {"baseline", "optimistic", "conservative", "hsa_delta"}
    assert result.monte_carlo["runs"] == 200


def test_scenario_engine_respects_explicit_zero_hsa_delta() -> None:
    engine = ScenarioEngine(
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

    result = engine.run(
        current_portfolio_value_usd=100000,
        annual_contribution_usd=15000,
        hsa_extra_contribution_usd=0,
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    hsa_delta = next(item for item in result.scenarios if item.label == "hsa_delta")
    assert hsa_delta.assumptions["annual_contribution_usd"] == baseline.assumptions["annual_contribution_usd"]


def test_scenario_engine_projects_tax_and_account_timelines() -> None:
    engine = ScenarioEngine(
        years_to_retirement=3,
        annual_contribution_usd=12000,
        baseline_return=0.06,
        optimistic_return=0.08,
        conservative_return=0.04,
        return_volatility=0.12,
        inflation=0.025,
        monte_carlo_runs=100,
        hsa_delta_default=1000,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=100000,
        annual_contribution_usd=12000,
        years=3,
        accounts=[
            {
                "account_id": "acct-taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 50000,
                "annual_contribution_usd": 4000,
            },
            {
                "account_id": "acct-401k",
                "account_type": "401k",
                "tax_treatment": "tax_deferred",
                "balance_usd": 50000,
                "annual_contribution_usd": 8000,
            },
        ],
        income_projection={
            "start_year": 2026,
            "years": 3,
            "first_year_gross_income_usd": 120000,
            "yearly_points": [
                {"year": 2026, "gross_income_usd": 120000},
                {"year": 2027, "gross_income_usd": 123000},
                {"year": 2028, "gross_income_usd": 126000},
            ],
        },
        expense_projection={
            "start_year": 2026,
            "years": 3,
            "first_year_expenses_usd": 65000,
            "yearly_points": [
                {"year": 2026, "total_expenses_usd": 65000},
                {"year": 2027, "total_expenses_usd": 67000},
                {"year": 2028, "total_expenses_usd": 69000},
            ],
        },
        debt_projection={
            "start_date": "2026-01-01",
            "selected_scenario": {
                "first_year_payments_usd": 6000,
            },
        },
        filing_status="single",
        start_year=2026,
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    assert len(baseline.timeline_points) == 3
    assert baseline.assumptions["total_taxes_paid_usd"] > 0
    assert len(baseline.account_balance_points) == 6
    assert baseline.timeline_points[0].taxes_usd > 0


def test_scenario_engine_withdrawal_order_prefers_taxable_first() -> None:
    engine = ScenarioEngine(
        years_to_retirement=1,
        annual_contribution_usd=0,
        baseline_return=0.05,
        optimistic_return=0.06,
        conservative_return=0.04,
        return_volatility=0.1,
        inflation=0.02,
        monte_carlo_runs=50,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=50000,
        annual_contribution_usd=0,
        years=1,
        accounts=[
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 10000,
            },
            {
                "account_id": "deferred",
                "account_type": "401k",
                "tax_treatment": "tax_deferred",
                "balance_usd": 40000,
            },
        ],
        income_projection={
            "start_year": 2026,
            "years": 1,
            "first_year_gross_income_usd": 12000,
            "yearly_points": [{"year": 2026, "gross_income_usd": 12000}],
        },
        expense_projection={
            "start_year": 2026,
            "years": 1,
            "first_year_expenses_usd": 62000,
            "yearly_points": [{"year": 2026, "total_expenses_usd": 62000}],
        },
        start_year=2026,
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    year_points = [p for p in baseline.account_balance_points if p.year == 2026]
    taxable = next(point for point in year_points if point.account_id == "taxable")
    deferred = next(point for point in year_points if point.account_id == "deferred")

    assert baseline.timeline_points[0].withdrawals_usd > 0
    assert taxable.withdrawal_usd >= 9999
    assert deferred.withdrawal_usd > 0

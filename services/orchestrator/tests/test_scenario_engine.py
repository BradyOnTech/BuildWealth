import pytest

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


def test_scenario_engine_propagates_assumption_set_metadata() -> None:
    engine = ScenarioEngine(
        years_to_retirement=5,
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
        assumption_set_id="stagflation",
        assumption_set_name="Stagflation",
    )

    for scenario in result.scenarios:
        assert scenario.assumptions["assumption_set_id"] == "stagflation"
        assert scenario.assumptions["assumption_set_name"] == "Stagflation"


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


def test_scenario_engine_applies_four_percent_rule_strategy() -> None:
    engine = ScenarioEngine(
        years_to_retirement=2,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.025,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=1_000_000,
        annual_contribution_usd=0,
        years=2,
        accounts=[
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 1_000_000,
            }
        ],
        income_projection={
            "yearly_points": [
                {"year": 2026, "gross_income_usd": 0},
                {"year": 2027, "gross_income_usd": 0},
            ]
        },
        expense_projection={
            "yearly_points": [
                {"year": 2026, "total_expenses_usd": 10000},
                {"year": 2027, "total_expenses_usd": 10000},
            ]
        },
        start_year=2026,
        start_age=35,
        retirement_age=35,
        withdrawal_strategy="4_percent_rule",
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    assert len(baseline.timeline_points) == 2
    assert baseline.timeline_points[0].withdrawals_usd == 40000
    assert baseline.timeline_points[1].withdrawals_usd == 41000
    assert baseline.assumptions["withdrawal_strategy"] == "four_percent_rule"


def test_scenario_engine_dynamic_guardrails_reduce_after_down_year() -> None:
    engine = ScenarioEngine(
        years_to_retirement=2,
        annual_contribution_usd=0,
        baseline_return=-0.2,
        optimistic_return=-0.2,
        conservative_return=-0.2,
        return_volatility=0.0,
        inflation=0.025,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=1_000_000,
        annual_contribution_usd=0,
        years=2,
        accounts=[
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 1_000_000,
            }
        ],
        income_projection={
            "yearly_points": [
                {"year": 2026, "gross_income_usd": 0},
                {"year": 2027, "gross_income_usd": 0},
            ]
        },
        expense_projection={
            "yearly_points": [
                {"year": 2026, "total_expenses_usd": 10000},
                {"year": 2027, "total_expenses_usd": 10000},
            ]
        },
        start_year=2026,
        start_age=35,
        retirement_age=35,
        withdrawal_strategy="dynamic_guardrails",
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    year_1 = baseline.timeline_points[0]
    year_2 = baseline.timeline_points[1]
    assert year_1.withdrawals_usd == 40000
    assert year_2.withdrawals_usd == 36000


def test_scenario_engine_bucket_strategy_prioritizes_cash_then_bond_bucket() -> None:
    engine = ScenarioEngine(
        years_to_retirement=1,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.0,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=50_000,
        annual_contribution_usd=0,
        years=1,
        accounts=[
            {
                "account_id": "cash",
                "account_type": "savings",
                "tax_treatment": "taxable",
                "balance_usd": 10_000,
            },
            {
                "account_id": "deferred",
                "account_type": "401k",
                "tax_treatment": "tax_deferred",
                "balance_usd": 10_000,
            },
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 30_000,
            },
        ],
        income_projection={"yearly_points": [{"year": 2026, "gross_income_usd": 0}]},
        expense_projection={"yearly_points": [{"year": 2026, "total_expenses_usd": 25000}]},
        start_year=2026,
        start_age=40,
        retirement_age=40,
        withdrawal_strategy="bucket_strategy",
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    year_points = [p for p in baseline.account_balance_points if p.year == 2026]
    by_id = {item.account_id: item for item in year_points}
    assert baseline.timeline_points[0].withdrawals_usd == 25000
    assert by_id["cash"].withdrawal_usd == 10000
    assert by_id["deferred"].withdrawal_usd == 10000
    assert by_id["taxable"].withdrawal_usd == 5000


def test_scenario_engine_bond_tent_strategy_increases_withdrawal_rate_over_time() -> None:
    engine = ScenarioEngine(
        years_to_retirement=3,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.0,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=1_000_000,
        annual_contribution_usd=0,
        years=3,
        accounts=[
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 1_000_000,
            }
        ],
        income_projection={
            "yearly_points": [
                {"year": 2026, "gross_income_usd": 0},
                {"year": 2027, "gross_income_usd": 0},
                {"year": 2028, "gross_income_usd": 0},
            ]
        },
        expense_projection={
            "yearly_points": [
                {"year": 2026, "total_expenses_usd": 10000},
                {"year": 2027, "total_expenses_usd": 10000},
                {"year": 2028, "total_expenses_usd": 10000},
            ]
        },
        start_year=2026,
        start_age=45,
        retirement_age=45,
        withdrawal_strategy="bond_tent",
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    rates = [
        point.withdrawals_usd / point.starting_balance_usd
        for point in baseline.timeline_points
        if point.starting_balance_usd > 0
    ]
    assert len(rates) == 3
    assert rates[1] > rates[0]
    assert rates[2] > rates[1]


def test_scenario_engine_uses_social_security_projection_for_cashflow() -> None:
    engine = ScenarioEngine(
        years_to_retirement=1,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.0,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    without_ss = engine.run(
        current_portfolio_value_usd=100000,
        annual_contribution_usd=0,
        years=1,
        accounts=[
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 100000,
            }
        ],
        income_projection={"yearly_points": [{"year": 2026, "gross_income_usd": 0}]},
        expense_projection={"yearly_points": [{"year": 2026, "total_expenses_usd": 50000}]},
        start_year=2026,
        start_age=67,
        retirement_age=65,
    )

    with_ss = engine.run(
        current_portfolio_value_usd=100000,
        annual_contribution_usd=0,
        years=1,
        accounts=[
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 100000,
            }
        ],
        income_projection={"yearly_points": [{"year": 2026, "gross_income_usd": 0}]},
        expense_projection={"yearly_points": [{"year": 2026, "total_expenses_usd": 50000}]},
        social_security_projection={
            "yearly_points": [
                {"year": 2026, "age": 67, "annual_benefit_usd": 24000.0},
            ],
            "selected_claiming_age": 67,
            "optimal_claiming_age": 70,
        },
        start_year=2026,
        start_age=67,
        retirement_age=65,
    )

    without_baseline = next(item for item in without_ss.scenarios if item.label == "baseline")
    with_baseline = next(item for item in with_ss.scenarios if item.label == "baseline")

    assert with_baseline.timeline_points[0].social_security_income_usd == pytest.approx(24000.0, abs=0.01)
    assert with_baseline.timeline_points[0].withdrawals_usd < without_baseline.timeline_points[0].withdrawals_usd
    assert with_baseline.assumptions["total_social_security_income_usd"] == pytest.approx(24000.0, abs=0.01)
    assert with_baseline.assumptions["social_security_claiming_age"] == 67


def test_scenario_engine_forces_rmd_withdrawals_for_eligible_accounts() -> None:
    engine = ScenarioEngine(
        years_to_retirement=1,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.0,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=1_000_000,
        annual_contribution_usd=0,
        years=1,
        accounts=[
            {
                "account_id": "deferred",
                "account_type": "401k",
                "tax_treatment": "tax_deferred",
                "balance_usd": 1_000_000,
            }
        ],
        income_projection={"yearly_points": [{"year": 2026, "gross_income_usd": 0}]},
        expense_projection={"yearly_points": [{"year": 2026, "total_expenses_usd": 0}]},
        rmd_projection={"birth_year": 1955, "rmd_start_age": 73},
        start_year=2026,
        start_age=73,
        retirement_age=65,
        withdrawal_strategy="cashflow_only",
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    timeline = baseline.timeline_points[0]
    account_point = baseline.account_balance_points[0]
    assert timeline.rmds_usd == pytest.approx(37735.85, abs=0.02)
    assert timeline.withdrawals_usd > timeline.rmds_usd
    assert account_point.rmd_withdrawal_usd == pytest.approx(37735.85, abs=0.02)
    assert baseline.assumptions["total_rmds_usd"] == pytest.approx(37735.85, abs=0.02)
    assert baseline.assumptions["rmd_start_age"] == 73
    assert timeline.taxes_usd > 0


def test_scenario_engine_honors_rmd_start_age_override() -> None:
    engine = ScenarioEngine(
        years_to_retirement=1,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.0,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=1_000_000,
        annual_contribution_usd=0,
        years=1,
        accounts=[
            {
                "account_id": "deferred",
                "account_type": "401k",
                "tax_treatment": "tax_deferred",
                "balance_usd": 1_000_000,
            }
        ],
        income_projection={"yearly_points": [{"year": 2026, "gross_income_usd": 0}]},
        expense_projection={"yearly_points": [{"year": 2026, "total_expenses_usd": 0}]},
        rmd_projection={"birth_year": 1960, "rmd_start_age": 75},
        start_year=2026,
        start_age=73,
        retirement_age=65,
        withdrawal_strategy="cashflow_only",
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    timeline = baseline.timeline_points[0]
    account_point = baseline.account_balance_points[0]
    assert timeline.rmds_usd == 0
    assert timeline.withdrawals_usd == 0
    assert account_point.rmd_withdrawal_usd == 0
    assert baseline.assumptions["total_rmds_usd"] == 0
    assert baseline.assumptions["rmd_start_age"] == 75


def test_scenario_engine_surfaces_state_tax_and_irmaa_breakdown() -> None:
    engine = ScenarioEngine(
        years_to_retirement=1,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.0,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=500000,
        annual_contribution_usd=0,
        years=1,
        accounts=[
            {
                "account_id": "taxable",
                "account_type": "taxableBrokerage",
                "tax_treatment": "taxable",
                "balance_usd": 500000,
            }
        ],
        income_projection={"yearly_points": [{"year": 2026, "gross_income_usd": 260000}]},
        expense_projection={"yearly_points": [{"year": 2026, "total_expenses_usd": 120000}]},
        social_security_projection={"yearly_points": [{"year": 2026, "age": 67, "annual_benefit_usd": 36000}]},
        state_tax_rate=0.05,
        include_irmaa=True,
        start_year=2026,
        start_age=67,
        retirement_age=67,
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    point = baseline.timeline_points[0]
    assert point.federal_taxes_usd > 0
    assert point.state_taxes_usd > 0
    assert point.irmaa_surcharges_usd > 0
    assert baseline.assumptions["state_tax_rate"] == pytest.approx(0.05, abs=1e-6)
    assert baseline.assumptions["total_federal_taxes_paid_usd"] > 0
    assert baseline.assumptions["total_state_taxes_paid_usd"] > 0
    assert baseline.assumptions["total_irmaa_surcharges_paid_usd"] > 0


def test_scenario_engine_applies_roth_conversion_window_and_balances() -> None:
    engine = ScenarioEngine(
        years_to_retirement=3,
        annual_contribution_usd=0,
        baseline_return=0.0,
        optimistic_return=0.0,
        conservative_return=0.0,
        return_volatility=0.0,
        inflation=0.0,
        monte_carlo_runs=10,
        hsa_delta_default=0,
        marginal_tax_rate=0.25,
    )

    result = engine.run(
        current_portfolio_value_usd=210000,
        annual_contribution_usd=0,
        years=3,
        accounts=[
            {
                "account_id": "deferred",
                "account_type": "401k",
                "tax_treatment": "tax_deferred",
                "balance_usd": 200000,
            },
            {
                "account_id": "roth",
                "account_type": "rothIra",
                "tax_treatment": "tax_free",
                "balance_usd": 10000,
            },
        ],
        income_projection={
            "yearly_points": [
                {"year": 2026, "gross_income_usd": 0},
                {"year": 2027, "gross_income_usd": 0},
                {"year": 2028, "gross_income_usd": 0},
            ]
        },
        expense_projection={
            "yearly_points": [
                {"year": 2026, "total_expenses_usd": 0},
                {"year": 2027, "total_expenses_usd": 0},
                {"year": 2028, "total_expenses_usd": 0},
            ]
        },
        filing_status="single",
        start_year=2026,
        start_age=60,
        retirement_age=65,
        roth_conversion_annual_amount_usd=50000,
        roth_conversion_start_age=60,
        roth_conversion_end_age=61,
    )

    baseline = next(item for item in result.scenarios if item.label == "baseline")
    assert baseline.timeline_points[0].roth_conversions_usd == pytest.approx(50000.0, abs=0.01)
    assert baseline.timeline_points[1].roth_conversions_usd == pytest.approx(50000.0, abs=0.01)
    assert baseline.timeline_points[2].roth_conversions_usd == pytest.approx(0.0, abs=0.01)
    assert baseline.assumptions["total_roth_conversions_usd"] == pytest.approx(100000.0, abs=0.01)

    year_2026_points = [point for point in baseline.account_balance_points if point.year == 2026]
    deferred_2026 = next(point for point in year_2026_points if point.account_id == "deferred")
    roth_2026 = next(point for point in year_2026_points if point.account_id == "roth")
    assert deferred_2026.roth_conversion_out_usd == pytest.approx(50000.0, abs=0.01)
    assert roth_2026.roth_conversion_in_usd == pytest.approx(50000.0, abs=0.01)

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import PlanningResponse, ScenarioResult


def test_apply_household_adjustments_adds_partner_income_and_shared_goal_funding() -> None:
    income_projection = {
        "start_year": 2026,
        "years": 3,
        "first_year_gross_income_usd": 100000.0,
        "final_year_gross_income_usd": 100000.0,
        "cumulative_gross_income_usd": 300000.0,
        "yearly_points": [
            {"year": 2026, "gross_income_usd": 100000.0, "post_tax_income_usd": 80000.0, "active_income_items": 1},
            {"year": 2027, "gross_income_usd": 100000.0, "post_tax_income_usd": 80000.0, "active_income_items": 1},
            {"year": 2028, "gross_income_usd": 100000.0, "post_tax_income_usd": 80000.0, "active_income_items": 1},
        ],
    }
    expense_projection = {
        "start_year": 2026,
        "years": 3,
        "first_year_expenses_usd": 60000.0,
        "final_year_expenses_usd": 60000.0,
        "cumulative_expenses_usd": 180000.0,
        "yearly_points": [
            {"year": 2026, "total_expenses_usd": 60000.0},
            {"year": 2027, "total_expenses_usd": 60000.0},
            {"year": 2028, "total_expenses_usd": 60000.0},
        ],
    }
    household_settings = {
        "household_mode": "couple",
        "household_partner_income_usd": 50000.0,
        "household_partner_income_growth_rate": 0.0,
        "household_partner_retirement_age": 36,
        "household_partner_social_security_annual_usd": 12000.0,
        "household_partner_social_security_claiming_age": 36,
        "household_shared_goal_target_usd": 30000.0,
        "household_shared_goal_target_year": 2027,
    }

    adjusted_income, adjusted_expenses, metadata = main._apply_household_adjustments_to_projection_payloads(  # noqa: SLF001
        income_projection=income_projection,
        expense_projection=expense_projection,
        household_settings=household_settings,
        start_year=2026,
        start_age=35,
        years=3,
    )

    assert adjusted_income is not None
    assert adjusted_expenses is not None
    income_points = adjusted_income["yearly_points"]
    expense_points = adjusted_expenses["yearly_points"]
    assert income_points[0]["gross_income_usd"] == 150000.0
    assert income_points[1]["gross_income_usd"] == 112000.0
    assert income_points[2]["gross_income_usd"] == 112000.0
    assert adjusted_income["first_year_gross_income_usd"] == 150000.0
    assert adjusted_income["cumulative_gross_income_usd"] == 374000.0

    assert expense_points[0]["total_expenses_usd"] == 75000.0
    assert expense_points[1]["total_expenses_usd"] == 75000.0
    assert expense_points[2]["total_expenses_usd"] == 60000.0
    assert adjusted_expenses["cumulative_expenses_usd"] == 210000.0

    assert metadata["mode"] == "couple"
    assert metadata["partner_income_added_first_year_usd"] == 50000.0
    assert metadata["partner_income_added_total_usd"] == 74000.0
    assert metadata["shared_goal_annual_funding_usd"] == 15000.0
    assert metadata["shared_goal_target_year"] == 2027


def test_resolve_filing_status_for_household_defaults_joint_for_couple() -> None:
    assert main._resolve_filing_status_for_household(  # noqa: SLF001
        filing_status=None,
        household_mode="couple",
    ) == "married_filing_jointly"
    assert main._resolve_filing_status_for_household(  # noqa: SLF001
        filing_status="single",
        household_mode="couple",
    ) == "single"
    assert main._resolve_filing_status_for_household(  # noqa: SLF001
        filing_status="invalid",
        household_mode="couple",
    ) == "married_filing_jointly"
    assert main._resolve_filing_status_for_household(  # noqa: SLF001
        filing_status="invalid",
        household_mode="individual",
    ) is None


def test_build_household_response_context_and_apply_to_scenarios() -> None:
    context = main._build_household_response_context(  # noqa: SLF001
        household_settings={
            "household_mode": "couple",
            "household_partner_income_usd": 95000.0,
            "household_partner_income_growth_rate": 0.025,
            "household_partner_retirement_age": 64,
            "household_partner_social_security_annual_usd": 22000.0,
            "household_partner_social_security_claiming_age": 67,
            "household_shared_goal_target_usd": 120000.0,
            "household_shared_goal_target_year": 2033,
        },
        household_adjustments={
            "shared_goal_annual_funding_usd": 15000.0,
            "partner_income_added_first_year_usd": 95000.0,
            "partner_income_added_total_usd": 760000.0,
        },
        filing_status="married_filing_jointly",
        source="plan_settings",
    )

    baseline = ScenarioResult(
        label="baseline",
        future_value_usd=1_000_000.0,
        real_value_usd=750_000.0,
        assumptions={"annual_return_rate": 0.07},
        timeline_points=[],
        account_balance_points=[],
    )
    optimistic = ScenarioResult(
        label="optimistic",
        future_value_usd=1_250_000.0,
        real_value_usd=900_000.0,
        assumptions={"annual_return_rate": 0.09},
        timeline_points=[],
        account_balance_points=[],
    )
    response = PlanningResponse(
        scenarios=[baseline, optimistic],
        monte_carlo={"p50_future_value_usd": 1_050_000.0},
    )

    updated = main._apply_household_context_to_planning_response(  # noqa: SLF001
        response=response,
        household_context=context,
    )

    assert updated.household is not None
    assert updated.household.mode == "couple"
    assert updated.household.filing_status == "married_filing_jointly"
    assert updated.household.partner_income_added_first_year_usd == 95000.0
    assert updated.household.shared_goal_annual_funding_usd == 15000.0
    for scenario in updated.scenarios:
        assert scenario.assumptions["household_mode"] == "couple"
        assert scenario.assumptions["filing_status"] == "married_filing_jointly"
        assert scenario.assumptions["household_partner_income_usd"] == 95000.0
        assert scenario.assumptions["household_shared_goal_target_year"] == 2033

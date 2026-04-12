import pytest

from buildwealth_orchestrator.services.social_security_projection import (
    project_social_security_income,
)


def test_social_security_projection_estimates_and_optimizes_claiming_age() -> None:
    result = project_social_security_income(
        start_year=2026,
        years=5,
        current_age=60,
        claiming_age=67,
        life_expectancy_age=90,
        estimated_annual_earnings_usd=120000,
        claim_age_options=[62, 67, 70],
        cola_rate=0.02,
    )

    assert result["fra_monthly_benefit_usd"] > 0
    assert result["estimated_aime_usd"] > 0
    assert result["selected_claiming_age"] == 67
    assert result["optimal_claiming_age"] == 70
    assert len(result["claim_options"]) == 3
    assert len(result["yearly_points"]) == 5


def test_social_security_projection_applies_claiming_adjustments() -> None:
    early = project_social_security_income(
        start_year=2026,
        years=1,
        current_age=62,
        claiming_age=62,
        fra_monthly_benefit_usd=3000,
        cola_rate=0.0,
    )
    late = project_social_security_income(
        start_year=2026,
        years=1,
        current_age=70,
        claiming_age=70,
        fra_monthly_benefit_usd=3000,
        cola_rate=0.0,
    )

    assert early["selected_annual_benefit_usd"] == pytest.approx(25200.0, abs=0.01)
    assert late["selected_annual_benefit_usd"] == pytest.approx(44640.0, abs=0.01)
    assert late["selected_annual_benefit_usd"] > early["selected_annual_benefit_usd"]


def test_social_security_projection_warns_without_income_inputs() -> None:
    result = project_social_security_income(
        start_year=2026,
        years=3,
        current_age=40,
    )

    assert result["fra_monthly_benefit_usd"] == 0.0
    assert result["selected_annual_benefit_usd"] == 0.0
    assert result["warnings"]

import pytest

from buildwealth_orchestrator.services.rmd_projection import (
    determine_rmd_start_age,
    estimate_year_rmd_for_accounts,
    project_rmd_schedule,
)


def test_determine_rmd_start_age_uses_secure_2_rules() -> None:
    assert determine_rmd_start_age(birth_year=1959) == 73
    assert determine_rmd_start_age(birth_year=1960) == 75
    assert determine_rmd_start_age(birth_year=1980, override_start_age=74) == 74


def test_estimate_year_rmd_for_accounts_filters_by_age_and_type() -> None:
    accounts = [
        {"account_id": "ira-1", "account_type": "ira", "balance_usd": 53000},
        {"account_id": "taxable-1", "account_type": "taxableBrokerage", "balance_usd": 53000},
    ]

    before_start = estimate_year_rmd_for_accounts(accounts=accounts, age=72, rmd_start_age=73)
    assert before_start["total_rmd_usd"] == 0
    assert before_start["account_rmds"] == []

    at_start = estimate_year_rmd_for_accounts(accounts=accounts, age=73, rmd_start_age=73)
    assert at_start["lookup_age"] == 73
    assert at_start["total_rmd_usd"] == pytest.approx(2000.0, abs=0.01)
    assert len(at_start["account_rmds"]) == 1
    assert at_start["account_rmds"][0]["account_id"] == "ira-1"


def test_project_rmd_schedule_projects_yearly_points() -> None:
    result = project_rmd_schedule(
        accounts=[{"account_id": "ira-1", "account_type": "ira", "balance_usd": 265000}],
        start_year=2026,
        years=2,
        current_age=73,
        birth_year=1955,
        expected_return=0.0,
    )

    assert result["rmd_start_age"] == 73
    assert result["eligible_account_count"] == 1
    assert len(result["yearly_points"]) == 2
    assert result["yearly_points"][0]["total_rmd_usd"] == pytest.approx(10000.0, abs=0.01)
    assert result["yearly_points"][1]["total_rmd_usd"] == pytest.approx(10000.0, abs=0.01)
    assert result["total_projected_rmds_usd"] == pytest.approx(20000.0, abs=0.01)


def test_project_rmd_schedule_respects_birth_year_start_age() -> None:
    result = project_rmd_schedule(
        accounts=[{"account_id": "ira-1", "account_type": "ira", "balance_usd": 265000}],
        start_year=2026,
        years=1,
        current_age=74,
        birth_year=1960,
        expected_return=0.0,
    )

    assert result["rmd_start_age"] == 75
    assert result["yearly_points"][0]["total_rmd_usd"] == 0

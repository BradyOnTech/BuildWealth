import pytest

from buildwealth_orchestrator.services.income_projection import project_income_schedule


def test_project_income_schedule_applies_growth_rates() -> None:
    result = project_income_schedule(
        [
            {
                "id": "income-1",
                "label": "Salary",
                "monthly_amount_usd": 10000,
                "annual_growth_rate": 0.03,
            }
        ],
        start_year=2026,
        years=3,
        default_annual_growth_rate=0.02,
    )

    points = result["yearly_points"]
    assert len(points) == 3
    assert points[0]["gross_income_usd"] == pytest.approx(120000.0, abs=0.01)
    assert points[1]["gross_income_usd"] == pytest.approx(123600.0, abs=0.01)
    assert points[2]["gross_income_usd"] == pytest.approx(127308.0, abs=0.01)
    assert result["first_year_gross_income_usd"] == pytest.approx(120000.0, abs=0.01)
    assert result["final_year_gross_income_usd"] == pytest.approx(127308.0, abs=0.01)


def test_project_income_schedule_respects_start_end_dates() -> None:
    result = project_income_schedule(
        [
            {
                "id": "income-1",
                "label": "Contract",
                "monthly_amount_usd": 1000,
                "annual_growth_rate": 0.0,
                "start_date": "2026-04-15",
                "end_date": "2027-09-01",
            }
        ],
        start_year=2026,
        years=3,
        default_annual_growth_rate=0.03,
    )

    points = result["yearly_points"]
    assert points[0]["gross_income_usd"] == pytest.approx(9000.0, abs=0.01)
    assert points[1]["gross_income_usd"] == pytest.approx(9000.0, abs=0.01)
    assert points[2]["gross_income_usd"] == pytest.approx(0.0, abs=0.01)
    assert points[0]["active_income_items"] == 1
    assert points[2]["active_income_items"] == 0


def test_project_income_schedule_splits_pre_tax_and_post_tax_income() -> None:
    result = project_income_schedule(
        [
            {
                "id": "income-1",
                "label": "Salary",
                "monthly_amount_usd": 8000,
                "is_pre_tax": True,
                "annual_growth_rate": 0.0,
            },
            {
                "id": "income-2",
                "label": "Rental",
                "monthly_amount_usd": 2000,
                "is_pre_tax": False,
                "annual_growth_rate": 0.0,
            },
        ],
        start_year=2026,
        years=1,
        default_annual_growth_rate=0.03,
    )

    point = result["yearly_points"][0]
    assert point["pre_tax_income_usd"] == pytest.approx(96000.0, abs=0.01)
    assert point["post_tax_income_usd"] == pytest.approx(24000.0, abs=0.01)
    assert point["gross_income_usd"] == pytest.approx(120000.0, abs=0.01)


def test_project_income_schedule_warns_on_invalid_date_range() -> None:
    result = project_income_schedule(
        [
            {
                "id": "income-1",
                "label": "Bad Range",
                "monthly_amount_usd": 1000,
                "start_date": "2027-01-01",
                "end_date": "2026-01-01",
            }
        ],
        start_year=2026,
        years=2,
        default_annual_growth_rate=0.03,
    )

    assert result["income_items_count"] == 0
    assert result["first_year_gross_income_usd"] == 0.0
    assert result["warnings"]

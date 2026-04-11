import pytest

from buildwealth_orchestrator.services.expense_projection import project_expense_schedule


def test_project_expense_schedule_applies_inflation_rates() -> None:
    result = project_expense_schedule(
        [
            {
                "id": "expense-1",
                "label": "Living",
                "monthly_amount_usd": 3000,
                "inflation_rate": 0.03,
            }
        ],
        start_year=2026,
        years=3,
        default_inflation_rate=0.02,
    )

    points = result["yearly_points"]
    assert len(points) == 3
    assert points[0]["total_expenses_usd"] == pytest.approx(36000.0, abs=0.01)
    assert points[1]["total_expenses_usd"] == pytest.approx(37080.0, abs=0.01)
    assert points[2]["total_expenses_usd"] == pytest.approx(38192.4, abs=0.01)
    assert result["first_year_expenses_usd"] == pytest.approx(36000.0, abs=0.01)
    assert result["final_year_expenses_usd"] == pytest.approx(38192.4, abs=0.01)


def test_project_expense_schedule_uses_default_inflation_when_item_rate_missing() -> None:
    result = project_expense_schedule(
        [
            {
                "id": "expense-1",
                "label": "Groceries",
                "monthly_amount_usd": 1000,
            }
        ],
        start_year=2026,
        years=2,
        default_inflation_rate=0.05,
    )

    points = result["yearly_points"]
    assert points[0]["total_expenses_usd"] == pytest.approx(12000.0, abs=0.01)
    assert points[1]["total_expenses_usd"] == pytest.approx(12600.0, abs=0.01)


def test_project_expense_schedule_respects_start_end_dates() -> None:
    result = project_expense_schedule(
        [
            {
                "id": "expense-1",
                "label": "Tuition",
                "monthly_amount_usd": 1000,
                "inflation_rate": 0.0,
                "start_date": "2026-04-15",
                "end_date": "2027-09-01",
            }
        ],
        start_year=2026,
        years=3,
        default_inflation_rate=0.03,
    )

    points = result["yearly_points"]
    assert points[0]["total_expenses_usd"] == pytest.approx(9000.0, abs=0.01)
    assert points[1]["total_expenses_usd"] == pytest.approx(9000.0, abs=0.01)
    assert points[2]["total_expenses_usd"] == pytest.approx(0.0, abs=0.01)
    assert points[0]["active_expense_items"] == 1
    assert points[2]["active_expense_items"] == 0


def test_project_expense_schedule_splits_fixed_and_variable_expenses() -> None:
    result = project_expense_schedule(
        [
            {
                "id": "expense-1",
                "label": "Rent",
                "monthly_amount_usd": 2000,
                "is_fixed": True,
                "inflation_rate": 0.0,
            },
            {
                "id": "expense-2",
                "label": "Travel",
                "monthly_amount_usd": 500,
                "is_fixed": False,
                "inflation_rate": 0.0,
            },
        ],
        start_year=2026,
        years=1,
        default_inflation_rate=0.03,
    )

    point = result["yearly_points"][0]
    assert point["fixed_expenses_usd"] == pytest.approx(24000.0, abs=0.01)
    assert point["variable_expenses_usd"] == pytest.approx(6000.0, abs=0.01)
    assert point["total_expenses_usd"] == pytest.approx(30000.0, abs=0.01)


def test_project_expense_schedule_warns_on_invalid_date_range() -> None:
    result = project_expense_schedule(
        [
            {
                "id": "expense-1",
                "label": "Bad Range",
                "monthly_amount_usd": 1000,
                "start_date": "2027-01-01",
                "end_date": "2026-01-01",
            }
        ],
        start_year=2026,
        years=2,
        default_inflation_rate=0.03,
    )

    assert result["expense_items_count"] == 0
    assert result["first_year_expenses_usd"] == 0.0
    assert result["warnings"]


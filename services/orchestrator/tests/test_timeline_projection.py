import pytest

from buildwealth_orchestrator.services.timeline_projection import project_timeline_impacts


def test_project_timeline_impacts_handles_one_time_events() -> None:
    result = project_timeline_impacts(
        [
            {
                "id": "e1",
                "date": "2027-06-01",
                "label": "Home Purchase",
                "event_type": "purchase",
                "impact_type": "expense",
                "amount_usd": 80000,
                "recurring_frequency": "one_time",
            },
            {
                "id": "e2",
                "date": "2028-03-01",
                "label": "Inheritance",
                "event_type": "windfall",
                "impact_type": "income",
                "amount_usd": 50000,
                "recurring_frequency": "one_time",
            },
        ],
        start_year=2026,
        years=4,
    )

    points = result["yearly_points"]
    assert points[0]["net_cashflow_impact_usd"] == pytest.approx(0.0, abs=0.01)
    assert points[1]["expense_impact_usd"] == pytest.approx(80000.0, abs=0.01)
    assert points[1]["net_cashflow_impact_usd"] == pytest.approx(-80000.0, abs=0.01)
    assert points[2]["income_impact_usd"] == pytest.approx(50000.0, abs=0.01)
    assert points[2]["net_cashflow_impact_usd"] == pytest.approx(50000.0, abs=0.01)


def test_project_timeline_impacts_handles_monthly_recurring_events() -> None:
    result = project_timeline_impacts(
        [
            {
                "id": "e1",
                "date": "2026-04-01",
                "end_date": "2027-09-01",
                "label": "College Expense",
                "event_type": "milestone",
                "impact_type": "expense",
                "amount_usd": 2000,
                "recurring_frequency": "monthly",
            }
        ],
        start_year=2026,
        years=3,
    )

    points = result["yearly_points"]
    assert points[0]["expense_impact_usd"] == pytest.approx(18000.0, abs=0.01)
    assert points[1]["expense_impact_usd"] == pytest.approx(18000.0, abs=0.01)
    assert points[2]["expense_impact_usd"] == pytest.approx(0.0, abs=0.01)


def test_project_timeline_impacts_maps_default_impact_types() -> None:
    result = project_timeline_impacts(
        [
            {
                "id": "e1",
                "date": "2026-01-01",
                "label": "Retire",
                "event_type": "retirement",
                "amount_usd": 12000,
                "recurring_frequency": "yearly",
            }
        ],
        start_year=2026,
        years=2,
    )

    points = result["yearly_points"]
    assert points[0]["contribution_impact_usd"] == pytest.approx(12000.0, abs=0.01)
    assert points[1]["contribution_impact_usd"] == pytest.approx(12000.0, abs=0.01)


def test_project_timeline_impacts_warns_and_skips_invalid_rows() -> None:
    result = project_timeline_impacts(
        [
            {"date": "bad", "label": "Invalid"},
            {"date": "2026-01-01", "label": "Bad Type", "event_type": "unknown"},
        ],
        start_year=2026,
        years=2,
    )

    assert result["events_count"] == 0
    assert result["yearly_points"][0]["events_applied"] == 0
    assert result["warnings"]


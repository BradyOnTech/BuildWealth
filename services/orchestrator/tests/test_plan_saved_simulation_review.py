from __future__ import annotations

from buildwealth_orchestrator.services.plan_saved_simulation_review import (
    compare_saved_simulation_to_current_plan,
)


def test_saved_simulation_review_detects_current_plan_setting_changes() -> None:
    comparison = compare_saved_simulation_to_current_plan(
        plan_id="plan-1",
        saved_simulation={
            "id": "saved-simulation-1",
            "title": "Early retirement",
            "input_payload": {"compare_settings": {"annual_contribution_usd": 30_000}},
            "result_payload": {
                "base_settings": {
                    "annual_contribution_usd": 20_000,
                    "expected_return_baseline": 0.06,
                },
                "candidate_settings": {
                    "annual_contribution_usd": 30_000,
                    "expected_return_baseline": 0.06,
                },
                "scenario_deltas": [
                    {
                        "label": "baseline",
                        "delta_future_value_usd": 80_000,
                        "delta_real_value_usd": 50_000,
                    }
                ],
            },
        },
        current_settings={
            "annual_contribution_usd": 24_000,
            "expected_return_baseline": 0.06,
        },
    )

    assert comparison["changed_since_saved"] is True
    assert comparison["setting_differences"] == [
        {
            "field": "annual_contribution_usd",
            "label": "Annual contribution",
            "saved_value": "$20,000",
            "current_value": "$24,000",
        }
    ]
    assert comparison["saved_metrics"]["delta_future_value_usd"] == 80_000
    assert comparison["rerun_payload"]["compare_settings"]["annual_contribution_usd"] == 30_000


def test_saved_simulation_review_reports_current_when_base_still_matches() -> None:
    comparison = compare_saved_simulation_to_current_plan(
        plan_id="plan-1",
        saved_simulation={
            "id": "saved-simulation-1",
            "title": "Contribution increase",
            "input_payload": {"compare_settings": {"annual_contribution_usd": 30_000}},
            "result_payload": {
                "base_settings": {"annual_contribution_usd": 20_000},
                "candidate_settings": {"annual_contribution_usd": 30_000},
            },
        },
        current_settings={"annual_contribution_usd": 20_000},
    )

    assert comparison["changed_since_saved"] is False
    assert comparison["setting_differences"] == []
    assert "still matches" in comparison["summary"]

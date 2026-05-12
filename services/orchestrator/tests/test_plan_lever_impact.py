from __future__ import annotations

from buildwealth_orchestrator.services.plan_lever_impact import classify_plan_lever_impact


def test_plan_lever_impact_low_review_for_small_traceable_change() -> None:
    result = classify_plan_lever_impact(
        plan_id="plan-1",
        source="scenario_diff",
        result_payload={
            "base_settings": {"annual_contribution_usd": 25_000},
            "candidate_settings": {"annual_contribution_usd": 27_000},
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "base_future_value_usd": 1_000_000,
                    "candidate_future_value_usd": 1_012_000,
                    "delta_future_value_usd": 12_000,
                    "delta_real_value_usd": 8_000,
                }
            ],
        },
        explanation_payload={
            "outcome_label": "better",
            "confidence_level": "high",
        },
    )

    assert result["review_level"] == "low"
    assert result["stage_one"]["level"] == "low"
    assert result["stage_two"]["level"] == "low"
    assert "normal simulation workflow" in result["summary"]


def test_plan_lever_impact_high_review_for_material_cash_change() -> None:
    result = classify_plan_lever_impact(
        plan_id="plan-1",
        source="scenario_diff",
        result_payload={
            "base_settings": {"annual_contribution_usd": 20_000},
            "candidate_settings": {"annual_contribution_usd": 35_000},
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "base_future_value_usd": 900_000,
                    "candidate_future_value_usd": 960_000,
                    "delta_future_value_usd": 60_000,
                    "delta_real_value_usd": 42_000,
                }
            ],
        },
        explanation_payload={
            "outcome_label": "better",
            "confidence_level": "high",
        },
    )

    assert result["review_level"] == "high"
    assert result["stage_one"]["level"] == "high"
    assert result["stage_two"]["level"] == "low"
    assert any("Annual contribution" in reason for reason in result["stage_one"]["reasons"])
    assert any("Future value" in reason for reason in result["stage_one"]["reasons"])


def test_plan_lever_impact_treats_new_large_assumption_as_material() -> None:
    result = classify_plan_lever_impact(
        plan_id="plan-1",
        source="scenario_diff",
        result_payload={
            "base_settings": {"annual_contribution_usd": None},
            "candidate_settings": {"annual_contribution_usd": 12_000},
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "base_future_value_usd": 500_000,
                    "candidate_future_value_usd": 530_000,
                    "delta_future_value_usd": 30_000,
                    "delta_real_value_usd": 21_000,
                }
            ],
        },
        explanation_payload={
            "outcome_label": "better",
            "confidence_level": "high",
        },
    )

    assert result["review_level"] == "high"
    assert any("Annual contribution" in reason for reason in result["stage_one"]["reasons"])


def test_plan_lever_impact_high_review_for_weak_or_worse_result() -> None:
    result = classify_plan_lever_impact(
        plan_id="plan-1",
        source="scenario_branch",
        result_payload={
            "base_settings": {"expected_return_baseline": 0.06},
            "branch_settings": {"expected_return_baseline": 0.055},
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "base_future_value_usd": 1_000_000,
                    "candidate_future_value_usd": 980_000,
                    "delta_future_value_usd": -20_000,
                    "delta_real_value_usd": -14_000,
                }
            ],
            "warnings": ["Tax assumptions are incomplete."],
        },
        explanation_payload={
            "outcome_label": "worse",
            "confidence_level": "low",
            "warnings": ["Tax assumptions are incomplete."],
        },
    )

    assert result["review_level"] == "high"
    assert result["stage_one"]["level"] == "low"
    assert result["stage_two"]["level"] == "high"
    assert "The explanation has low confidence." in result["stage_two"]["reasons"]
    assert "The result weakens the active plan." in result["stage_two"]["reasons"]


def test_plan_lever_impact_high_review_for_recurring_branch_event() -> None:
    result = classify_plan_lever_impact(
        plan_id="plan-1",
        source="scenario_branch",
        input_payload={
            "branch_events": [
                {
                    "label": "One income year",
                    "amount_usd": 45_000,
                    "recurring_frequency": "annual",
                }
            ]
        },
        result_payload={
            "base_settings": {"years": 25},
            "branch_settings": {"years": 25},
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "base_future_value_usd": 1_000_000,
                    "candidate_future_value_usd": 970_000,
                    "delta_future_value_usd": -30_000,
                    "delta_real_value_usd": -20_000,
                }
            ],
        },
        explanation_payload={
            "outcome_label": "mixed",
            "confidence_level": "medium",
        },
    )

    assert result["review_level"] == "high"
    assert any("One income year" in reason for reason in result["stage_one"]["reasons"])
    assert "The result has trade-offs." in result["stage_two"]["reasons"]

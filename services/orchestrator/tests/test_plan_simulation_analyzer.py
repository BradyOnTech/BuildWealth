from __future__ import annotations

from buildwealth_orchestrator.services.plan_simulation_analyzer import explain_plan_simulation


def test_simulation_explainer_reports_better_outcome_with_high_confidence() -> None:
    explanation = explain_plan_simulation(
        plan_id="plan-1",
        source="scenario_diff",
        input_payload={"compare_settings": {"annual_contribution_usd": 30_000}},
        result_payload={
            "base_settings": {"annual_contribution_usd": 20_000, "expected_return_baseline": 0.06},
            "candidate_settings": {"annual_contribution_usd": 30_000, "expected_return_baseline": 0.06},
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "base_future_value_usd": 1_000_000,
                    "candidate_future_value_usd": 1_080_000,
                    "delta_future_value_usd": 80_000,
                    "base_real_value_usd": 740_000,
                    "candidate_real_value_usd": 790_000,
                    "delta_real_value_usd": 50_000,
                }
            ],
            "monte_carlo_delta": {"success_probability_delta": 0.03},
        },
    )

    assert explanation["outcome_label"] == "better"
    assert explanation["confidence_level"] == "high"
    assert "Future value changes by +$80,000." in explanation["summary"]
    assert explanation["drivers"][0]["direction"] == "positive"
    assert explanation["assumption_traces"][0]["field"] == "annual_contribution_usd"


def test_simulation_explainer_separates_weak_model_from_bad_outcome() -> None:
    explanation = explain_plan_simulation(
        plan_id="plan-1",
        source="scenario_branch",
        input_payload={"branch_template_id": "market_stress"},
        result_payload={
            "base_settings": {"expected_return_baseline": 0.06},
            "branch_settings": {"expected_return_baseline": 0.03},
            "scenario_deltas": [
                {
                    "label": "baseline",
                    "delta_future_value_usd": -90_000,
                    "delta_real_value_usd": -70_000,
                }
            ],
            "warnings": ["Tax assumptions are incomplete."],
        },
    )

    assert explanation["outcome_label"] == "worse"
    assert explanation["confidence_level"] == "medium"
    assert explanation["warnings"] == ["Tax assumptions are incomplete."]
    assert any("Model warnings need review" in reason for reason in explanation["confidence_reasons"])


def test_simulation_explainer_low_confidence_without_comparable_deltas() -> None:
    explanation = explain_plan_simulation(
        plan_id="plan-1",
        input_payload={},
        result_payload={"candidate_settings": {"annual_contribution_usd": 30_000}},
    )

    assert explanation["outcome_label"] == "unclear"
    assert explanation["confidence_level"] == "low"
    assert "does not include comparable" in explanation["confidence_reasons"][0]

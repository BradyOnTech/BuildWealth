from buildwealth_orchestrator.main import (
    apply_assumption_set_to_settings,
    parse_assumption_sets_payload,
)


def test_parse_assumption_sets_payload_normalizes_rates_and_active_set() -> None:
    payload = parse_assumption_sets_payload(
        {
            "active_assumption_set_id": "StagFlation",
            "sets": [
                {
                    "id": "StagFlation",
                    "name": "Stagflation",
                    "expected_return_baseline": "0.04",
                    "expected_return_optimistic": "0.03",
                    "expected_return_conservative": "0.05",
                    "inflation_rate": "0.05",
                    "marginal_tax_rate": "0.27",
                },
                {
                    "id": "bad-set",
                    "name": "Bad Set",
                    "expected_return_baseline": "not-a-number",
                    "expected_return_optimistic": 5,
                    "expected_return_conservative": -2,
                    "inflation_rate": 2,
                    "marginal_tax_rate": -1,
                },
            ],
        }
    )

    assert payload["active_assumption_set_id"] == "stagflation"
    parsed_sets = {item["id"]: item for item in payload["sets"]}
    assert parsed_sets["stagflation"]["expected_return_baseline"] == 0.04
    assert parsed_sets["stagflation"]["expected_return_optimistic"] == 0.04
    assert parsed_sets["stagflation"]["expected_return_conservative"] == 0.04
    assert parsed_sets["stagflation"]["inflation_rate"] == 0.05
    assert parsed_sets["stagflation"]["marginal_tax_rate"] == 0.27
    assert parsed_sets["bad-set"]["expected_return_baseline"] is None
    assert parsed_sets["bad-set"]["expected_return_optimistic"] is None
    assert parsed_sets["bad-set"]["expected_return_conservative"] is None
    assert parsed_sets["bad-set"]["inflation_rate"] is None
    assert parsed_sets["bad-set"]["marginal_tax_rate"] is None


def test_apply_assumption_set_to_settings_overrides_plan_values() -> None:
    assumption_sets_payload = parse_assumption_sets_payload(
        {
            "active_assumption_set_id": "historical_average",
            "sets": [
                {
                    "id": "historical_average",
                    "name": "Historical Average",
                    "expected_return_baseline": 0.07,
                    "expected_return_optimistic": 0.09,
                    "expected_return_conservative": 0.05,
                    "inflation_rate": 0.03,
                    "marginal_tax_rate": 0.24,
                },
                {
                    "id": "conservative",
                    "name": "Conservative",
                    "expected_return_baseline": 0.05,
                    "expected_return_optimistic": 0.06,
                    "expected_return_conservative": 0.04,
                    "inflation_rate": 0.025,
                    "marginal_tax_rate": 0.2,
                },
            ],
        }
    )

    merged, selected = apply_assumption_set_to_settings(
        plan_settings={
            "years": 25,
            "expected_return_baseline": 0.08,
            "inflation_rate": 0.02,
            "marginal_tax_rate": 0.3,
        },
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id="conservative",
    )

    assert selected is not None
    assert selected["id"] == "conservative"
    assert merged["years"] == 25
    assert merged["expected_return_baseline"] == 0.05
    assert merged["expected_return_optimistic"] == 0.06
    assert merged["expected_return_conservative"] == 0.04
    assert merged["inflation_rate"] == 0.025
    assert merged["marginal_tax_rate"] == 0.2
    assert merged["assumption_set_id"] == "conservative"
    assert merged["assumption_set_name"] == "Conservative"

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
                    "state_tax_rate": "0.06",
                    "simulation_mode": "historical_backtest",
                    "simulation_monte_carlo_variant": "P90",
                    "simulation_historical_start_year": "1980",
                    "simulation_seed": "12345",
                    "roth_conversion_annual_amount_usd": "15000",
                    "roth_conversion_start_age": "60",
                    "roth_conversion_end_age": "70",
                },
                {
                    "id": "bad-set",
                    "name": "Bad Set",
                    "expected_return_baseline": "not-a-number",
                    "expected_return_optimistic": 5,
                    "expected_return_conservative": -2,
                    "inflation_rate": 2,
                    "marginal_tax_rate": -1,
                    "state_tax_rate": 3,
                    "simulation_mode": "invalid_mode",
                    "simulation_monte_carlo_variant": "invalid_variant",
                    "simulation_historical_start_year": 1800,
                    "simulation_seed": -1,
                    "roth_conversion_annual_amount_usd": -1,
                    "roth_conversion_start_age": 121,
                    "roth_conversion_end_age": -5,
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
    assert parsed_sets["stagflation"]["state_tax_rate"] == 0.06
    assert parsed_sets["stagflation"]["simulation_mode"] == "historical"
    assert parsed_sets["stagflation"]["simulation_monte_carlo_variant"] == "p90"
    assert parsed_sets["stagflation"]["simulation_historical_start_year"] == 1980
    assert parsed_sets["stagflation"]["simulation_seed"] == 12345
    assert parsed_sets["stagflation"]["roth_conversion_annual_amount_usd"] == 15000.0
    assert parsed_sets["stagflation"]["roth_conversion_start_age"] == 60
    assert parsed_sets["stagflation"]["roth_conversion_end_age"] == 70
    assert parsed_sets["bad-set"]["expected_return_baseline"] is None
    assert parsed_sets["bad-set"]["expected_return_optimistic"] is None
    assert parsed_sets["bad-set"]["expected_return_conservative"] is None
    assert parsed_sets["bad-set"]["inflation_rate"] is None
    assert parsed_sets["bad-set"]["marginal_tax_rate"] is None
    assert parsed_sets["bad-set"]["state_tax_rate"] is None
    assert parsed_sets["bad-set"]["simulation_mode"] is None
    assert parsed_sets["bad-set"]["simulation_monte_carlo_variant"] is None
    assert parsed_sets["bad-set"]["simulation_historical_start_year"] is None
    assert parsed_sets["bad-set"]["simulation_seed"] == 9521
    assert parsed_sets["bad-set"]["roth_conversion_annual_amount_usd"] is None
    assert parsed_sets["bad-set"]["roth_conversion_start_age"] is None
    assert parsed_sets["bad-set"]["roth_conversion_end_age"] is None


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
                    "state_tax_rate": 0.05,
                    "simulation_mode": "fixed",
                    "simulation_monte_carlo_variant": "p50",
                    "simulation_historical_start_year": 1990,
                    "simulation_seed": 456,
                    "roth_conversion_annual_amount_usd": 12000,
                    "roth_conversion_start_age": 60,
                    "roth_conversion_end_age": 70,
                },
                {
                    "id": "conservative",
                    "name": "Conservative",
                    "expected_return_baseline": 0.05,
                    "expected_return_optimistic": 0.06,
                    "expected_return_conservative": 0.04,
                    "inflation_rate": 0.025,
                    "marginal_tax_rate": 0.2,
                    "state_tax_rate": 0.04,
                    "simulation_mode": "stochastic",
                    "simulation_monte_carlo_variant": "p10",
                    "simulation_historical_start_year": 1975,
                    "simulation_seed": 9876,
                    "roth_conversion_annual_amount_usd": 8000,
                    "roth_conversion_start_age": 62,
                    "roth_conversion_end_age": 72,
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
            "state_tax_rate": 0.07,
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
    assert merged["state_tax_rate"] == 0.04
    assert merged["simulation_mode"] == "stochastic"
    assert merged["simulation_monte_carlo_variant"] == "p10"
    assert merged["simulation_historical_start_year"] == 1975
    assert merged["simulation_seed"] == 9876
    assert merged["roth_conversion_annual_amount_usd"] == 8000
    assert merged["roth_conversion_start_age"] == 62
    assert merged["roth_conversion_end_age"] == 72
    assert merged["assumption_set_id"] == "conservative"
    assert merged["assumption_set_name"] == "Conservative"

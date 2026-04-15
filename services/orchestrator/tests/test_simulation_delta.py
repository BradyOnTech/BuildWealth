import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.schemas import PlanningResponse, ScenarioResult


def _planning_response(simulation: dict[str, object]) -> PlanningResponse:
    return PlanningResponse(
        scenarios=[
            ScenarioResult(
                label="baseline",
                future_value_usd=1_000_000.0,
                real_value_usd=750_000.0,
                assumptions={},
                timeline_points=[],
                account_balance_points=[],
            )
        ],
        monte_carlo={},
        simulation=simulation,
    )


def test_simulation_delta_ignores_irrelevant_controls_for_fixed_mode() -> None:
    base = _planning_response(
        {
            "mode": "fixed",
            "timeline_mode": "fixed",
            "monte_carlo_variant": "p50",
            "seed": 9521,
            "requested_historical_start_year": 1980,
            "resolved_historical_start_year_by_scenario": {"baseline": 1980},
        }
    )
    candidate = _planning_response(
        {
            "mode": "fixed",
            "timeline_mode": "fixed",
            "monte_carlo_variant": "p90",
            "seed": 12345,
            "requested_historical_start_year": 1990,
            "resolved_historical_start_year_by_scenario": {"baseline": 1990},
        }
    )

    payload = main._build_simulation_delta_payload(  # noqa: SLF001
        base_result=base,
        candidate_result=candidate,
        candidate_label="candidate",
    )

    assert payload["base"] == {"mode": "fixed", "timeline_mode": "fixed"}
    assert payload["candidate"] == {"mode": "fixed", "timeline_mode": "fixed"}
    assert payload["changed"] is False


def test_simulation_delta_tracks_variant_changes_for_monte_carlo_mode() -> None:
    base = _planning_response(
        {
            "mode": "monte_carlo",
            "timeline_mode": "fixed",
            "monte_carlo_variant": "p50",
            "seed": 9521,
        }
    )
    candidate = _planning_response(
        {
            "mode": "monte_carlo",
            "timeline_mode": "fixed",
            "monte_carlo_variant": "p90",
            "seed": 9521,
        }
    )

    payload = main._build_simulation_delta_payload(  # noqa: SLF001
        base_result=base,
        candidate_result=candidate,
        candidate_label="candidate",
    )

    assert payload["base"]["monte_carlo_variant"] == "p50"
    assert payload["candidate"]["monte_carlo_variant"] == "p90"
    assert payload["changed"] is True


def test_simulation_delta_tracks_historical_start_year_for_historical_mode() -> None:
    base = _planning_response(
        {
            "mode": "historical",
            "timeline_mode": "historical",
            "seed": 42,
            "requested_historical_start_year": 1980,
            "resolved_historical_start_year_by_scenario": {"baseline": 1980},
        }
    )
    candidate = _planning_response(
        {
            "mode": "historical",
            "timeline_mode": "historical",
            "seed": 42,
            "requested_historical_start_year": 1981,
            "resolved_historical_start_year_by_scenario": {"baseline": 1981},
        }
    )

    payload = main._build_simulation_delta_payload(  # noqa: SLF001
        base_result=base,
        candidate_result=candidate,
        candidate_label="candidate",
    )

    assert payload["base"]["requested_historical_start_year"] == 1980
    assert payload["candidate"]["requested_historical_start_year"] == 1981
    assert payload["changed"] is True

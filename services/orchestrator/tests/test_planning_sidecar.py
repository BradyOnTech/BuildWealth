import asyncio
import json

import httpx

from buildwealth_orchestrator.services.engine_adapter import SidecarAdapter
from buildwealth_orchestrator.services.planning_sidecar import IgnidashScenarioService
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine


def _build_scenario_engine() -> ScenarioEngine:
    return ScenarioEngine(
        years_to_retirement=30,
        annual_contribution_usd=12000,
        baseline_return=0.06,
        optimistic_return=0.08,
        conservative_return=0.04,
        return_volatility=0.12,
        inflation=0.025,
        monte_carlo_runs=200,
        hsa_delta_default=1000,
        marginal_tax_rate=0.25,
    )


def test_ignidash_sidecar_service_returns_local_when_disabled() -> None:
    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=None,
        sidecar_enabled=False,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(service.run(current_portfolio_value_usd=100000))

    assert len(result.scenarios) == 4
    assert result.engine == "local"
    assert result.engine_status == "ok"
    assert result.fallback_method is None
    assert result.warnings == []


def test_ignidash_sidecar_service_merges_sidecar_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["contract_version"] == 1
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine": "ignidash",
                "engine_status": "ok",
                "fallback_method": None,
                "scenarios": [
                    {
                        "scenario_id": "baseline",
                        "label": "baseline",
                        "summary": {
                            "ending_balance_nominal": 1000000,
                            "ending_balance_real": 700000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "optimistic",
                        "label": "optimistic",
                        "summary": {
                            "ending_balance_nominal": 1200000,
                            "ending_balance_real": 850000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "conservative",
                        "label": "conservative",
                        "summary": {
                            "ending_balance_nominal": 800000,
                            "ending_balance_real": 560000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "hsa_delta",
                        "label": "hsa_delta",
                        "summary": {
                            "ending_balance_nominal": 1030000,
                            "ending_balance_real": 721000,
                        },
                        "timeline": [],
                    },
                ],
                "warnings": [],
                "generated_at": "2026-04-10T13:00:00Z",
            },
        )

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(service.run(current_portfolio_value_usd=100000))

    assert result.engine == "ignidash"
    assert result.engine_status == "ok"
    by_label = {scenario.label: scenario for scenario in result.scenarios}
    assert by_label["baseline"].future_value_usd == 1000000
    assert by_label["optimistic"].real_value_usd == 850000


def test_ignidash_sidecar_service_falls_back_on_sidecar_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=503, json={"detail": "temporary outage"})

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(service.run(current_portfolio_value_usd=100000))

    assert result.engine == "local"
    assert result.engine_status == "degraded"
    assert result.fallback_method == "local_scenario_engine_fallback"
    assert any("sidecar unavailable" in warning.lower() for warning in result.warnings)


def test_ignidash_sidecar_service_uses_account_allocation_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        accounts = payload["accounts"]
        assert len(accounts) == 2
        assert accounts[0]["account_id"] == "acct-401k"
        assert accounts[0]["account_type"] == "401k"
        assert accounts[0]["tax_treatment"] == "tax_deferred"
        assert accounts[0]["annual_contribution"] == 18000
        assert payload["metadata"]["contribution_allocation"]["total_contributions_usd"] == 22000
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine": "ignidash",
                "engine_status": "ok",
                "fallback_method": None,
                "scenarios": [
                    {
                        "scenario_id": "baseline",
                        "label": "baseline",
                        "summary": {
                            "ending_balance_nominal": 1000000,
                            "ending_balance_real": 700000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "optimistic",
                        "label": "optimistic",
                        "summary": {
                            "ending_balance_nominal": 1200000,
                            "ending_balance_real": 850000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "conservative",
                        "label": "conservative",
                        "summary": {
                            "ending_balance_nominal": 800000,
                            "ending_balance_real": 560000,
                        },
                        "timeline": [],
                    },
                    {
                        "scenario_id": "hsa_delta",
                        "label": "hsa_delta",
                        "summary": {
                            "ending_balance_nominal": 1030000,
                            "ending_balance_real": 721000,
                        },
                        "timeline": [],
                    },
                ],
                "warnings": [],
                "generated_at": "2026-04-10T13:00:00Z",
            },
        )

    adapter = SidecarAdapter(
        base_url="http://localhost:8412",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )
    service = IgnidashScenarioService(
        scenario_engine=_build_scenario_engine(),
        sidecar_adapter=adapter,
        sidecar_enabled=True,
        sidecar_path="/v1/scenario/simulate",
        currency="USD",
    )

    result = asyncio.run(
        service.run(
            current_portfolio_value_usd=100000,
            annual_contribution_usd=22000,
            accounts=[
                {
                    "account_id": "acct-401k",
                    "account_type": "401k",
                    "balance_usd": 120000,
                    "annual_contribution_usd": 18000,
                },
                {
                    "account_id": "acct-taxable",
                    "account_type": "taxableBrokerage",
                    "balance_usd": 50000,
                    "annual_contribution_usd": 4000,
                },
            ],
            contribution_allocation={
                "profile_id": "tax_optimized_high_earner",
                "base_rule_type": "save",
                "annual_contribution_target_usd": 22000,
                "employee_contributions_usd": 22000,
                "employer_match_usd": 0,
                "total_contributions_usd": 22000,
                "unallocated_contribution_usd": 0,
                "allocations": [],
                "rule_results": [],
                "warnings": [],
            },
        )
    )

    assert result.engine == "ignidash"
    assert result.contribution_allocation is not None
    assert result.contribution_allocation.total_contributions_usd == 22000

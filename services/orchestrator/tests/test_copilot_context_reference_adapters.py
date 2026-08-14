from __future__ import annotations

from types import SimpleNamespace

from buildwealth_orchestrator.services.copilot_context_reference_adapters import (
    build_workspace_context_reference_lookups,
)
from buildwealth_orchestrator.services.copilot_context_references import (
    resolve_context_references,
)
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def test_workspace_adapters_resolve_each_supported_reference_from_canonical_stores(
    tmp_path,
) -> None:
    plans = PlanWorkspace(tmp_path / "plans")
    recommendations = RecommendationInbox(tmp_path / "recommendations.json")
    portfolio = PortfolioStore(tmp_path / "portfolio")
    plan = plans.create_plan("Retirement decision", "Review a contribution change.")
    recommendation = recommendations.create(
        title="Increase retirement contribution",
        detail="Review the effect before applying anything.",
        plan_id=plan["id"],
    )
    artifact = plans.write_artifact(
        plan["id"],
        "Decision evidence",
        "# Decision evidence\n\nA bounded source snapshot.",
    )
    simulation = plans.save_simulation(
        plan["id"],
        {
            "title": "Higher contribution",
            "source": "scenario_diff",
            "summary": "Modeled a higher monthly contribution.",
            "input_payload": {"monthly_contribution_usd": 2_000},
            "result_payload": {"success_probability": 0.83},
        },
    )
    portfolio.add_transaction(
        date="2026-07-31",
        symbol="AAPL",
        action="BUY",
        quantity=10,
        unit_price=200,
        name="Apple",
    )
    services = SimpleNamespace(
        record=SimpleNamespace(id="workspace-1"),
        plan_workspace=plans,
        recommendation_inbox=recommendations,
        portfolio_store=portfolio,
    )

    resolved = resolve_context_references(
        [
            {"type": "plan", "id": plan["id"]},
            {"type": "recommendation", "id": recommendation["id"]},
            {"type": "saved_simulation", "id": simulation["id"]},
            {"type": "plan_artifact", "id": artifact["id"]},
            {"type": "holding", "id": "AAPL"},
        ],
        workspace_id="workspace-1",
        lookups=build_workspace_context_reference_lookups(services),
    )

    assert [reference.reference_type for reference in resolved] == [
        "plan",
        "recommendation",
        "saved_simulation",
        "plan_artifact",
        "holding",
    ]
    assert resolved[0].label == "Retirement decision"
    assert resolved[1].evidence["status"] == "proposed"
    assert resolved[2].evidence["plan_id"] == plan["id"]
    assert resolved[3].evidence["plan_id"] == plan["id"]
    assert resolved[4].evidence["symbol"] == "AAPL"
    assert resolved[4].evidence["quantity"] == 10
    assert resolved[4].evidence["cost_basis_usd"] == 2_000
    assert all(reference.authority == "canonical_state" for reference in resolved)

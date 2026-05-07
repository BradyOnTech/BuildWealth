from __future__ import annotations

from pathlib import Path

from buildwealth_orchestrator.services.context_intelligence import (
    ACTION_READINESS_BY_MATERIALITY,
    ContextIntelligenceService,
    MaterialityPolicy,
)
from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def test_materiality_policy_is_rules_first_and_separates_confidence() -> None:
    policy = MaterialityPolicy()

    tax_decision = policy.classify(
        domain="profile",
        entity_type="tax_profile_field",
        field_path="tax_profile.marginal_tax_rate",
        payload={"confidence": "low"},
    )
    preference_decision = policy.classify(
        domain="conversation",
        entity_type="preference_note",
        field_path="learning_interest",
        payload={"confidence": "high"},
    )
    research_decision = policy.classify(
        domain="research",
        entity_type="research_dossier_artifact",
        field_path="artifact",
    )

    assert tax_decision.materiality == "high"
    assert tax_decision.action_readiness == ACTION_READINESS_BY_MATERIALITY["high"]
    assert "profile_material_field_high" in tax_decision.rule_ids
    assert preference_decision.materiality == "low"
    assert research_decision.materiality == "medium"


def test_materiality_policy_escalates_material_conflicts_affecting_live_advice() -> None:
    policy = MaterialityPolicy()

    decision = policy.classify(
        domain="conversation",
        entity_type="context_candidate",
        field_path="investment_policy.single_stock_interest",
        conflicts_material_context=True,
        affects_live_advice=True,
    )

    assert decision.materiality == "critical"
    assert decision.action_readiness == "Needs attention before acting"
    assert "material_conflict_floor_high" in decision.rule_ids
    assert "live_advice_escalation" in decision.rule_ids


def test_context_registry_rebuild_indexes_stable_source_refs_and_domains(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    first_report = service.rebuild_registry()
    first_items = service.registry.list_items(limit=500)
    second_report = service.rebuild_registry()
    second_items = service.registry.list_items(limit=500)

    first_ids = sorted(item.id for item in first_items)
    second_ids = sorted(item.id for item in second_items)
    source_refs = {item.source_ref for item in first_items}
    domains = {item.domain for item in first_items}

    assert first_report["item_count"] == second_report["item_count"]
    assert first_ids == second_ids
    assert "profile" in domains
    assert "plan" in domains
    assert "research" in domains
    assert "recommendation" in domains
    assert "profile/financial_profile.json#investment_policy.max_single_symbol_exposure_pct" in source_refs
    assert any(ref.endswith("/decisions.jsonl#decision-fixed") for ref in source_refs)
    assert any(ref.endswith("research-dossier-nvda.md") for ref in source_refs)
    assert any(ref.startswith("recommendations/inbox.json#recommendations.") for ref in source_refs)


def test_context_registry_status_tracks_counts_without_using_durable_snapshot_db(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    empty_status = service.get_status()
    rebuild_report = service.rebuild_registry()
    status = service.get_status()

    assert empty_status["database_exists"] is False
    assert Path(status["database_path"]).name == "context_index.db"
    assert Path(status["database_path"]).exists()
    assert Path(status["database_path"]).name != "buildwealth_durable.db"
    assert status["item_count"] == rebuild_report["item_count"]
    assert status["counts_by_domain"]["profile"] >= 2
    assert status["latest_rebuild_at"]


def test_indexed_profile_material_fields_get_action_readiness(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    service.rebuild_registry()

    profile_items = service.registry.list_items(domain="profile", limit=100)
    max_single_symbol = next(
        item
        for item in profile_items
        if item.entity_id == "investment_policy.max_single_symbol_exposure_pct"
    )
    marginal_tax_rate = next(
        item
        for item in profile_items
        if item.entity_id == "tax_profile.marginal_tax_rate"
    )

    assert max_single_symbol.materiality == "high"
    assert max_single_symbol.action_readiness == "Review before relying on this"
    assert max_single_symbol.quality["materiality_policy_version"] == "global_v1"
    assert "profile_material_field_high" in max_single_symbol.quality["materiality_rule_ids"]
    assert marginal_tax_rate.text.endswith("28.00%.")


def _build_service(tmp_path: Path) -> ContextIntelligenceService:
    profile_store = FinancialProfileStore(tmp_path / "profile" / "financial_profile.json")
    profile_store.save(
        {
            "tax_profile": {
                "filing_status": "single",
                "marginal_tax_rate": 0.28,
                "state_tax_rate": 0.07,
                "state": "MN",
            },
            "investment_policy": {
                "max_single_symbol_exposure_pct": 10.0,
                "minimum_cash_runway_months": 9.0,
                "restricted_symbols": ["NVDA"],
                "risk_tolerance": "moderate",
            },
        }
    )

    plan_workspace = PlanWorkspace(tmp_path / "plans")
    plan = plan_workspace.create_plan("Retirement 2055", "Keep allocation risk aligned with policy.")
    plan_id = str(plan["id"])
    decision = plan_workspace.append_decision(
        plan_id,
        summary="Avoid adding single-stock exposure until concentration is reviewed.",
        rationale="The profile limits single-symbol risk.",
        status="accepted",
    )
    _force_decision_id(plan_workspace, plan_id=plan_id, decision_id=str(decision["id"]), new_id="decision-fixed")
    plan_workspace.write_artifact(
        plan_id=plan_id,
        title="Research Dossier: NVDA",
        markdown="# Research Dossier: NVDA\n\n## Thesis\n\nReview valuation before adding exposure.\n",
        kind="research-dossier",
    )

    recommendation_inbox = RecommendationInbox(tmp_path / "recommendations" / "inbox.json")
    recommendation_inbox.create(
        title="Review NVDA concentration before buying",
        detail="This review checks the investment policy before acting on the idea.",
        priority="high",
        recommendation_type="review_only",
        source="context_intelligence_test",
        plan_id=plan_id,
        action_payload={
            "quality": {
                "confidence_level": "medium",
                "impact": {"level": "high"},
                "blocking_context": ["investment_policy.max_single_symbol_exposure_pct"],
                "decision_grade": False,
            }
        },
    )

    return ContextIntelligenceService(
        database_path=tmp_path / "storage" / "context_index.db",
        financial_profile_store=profile_store,
        plan_workspace=plan_workspace,
        recommendation_inbox=recommendation_inbox,
    )


def _force_decision_id(
    plan_workspace: PlanWorkspace,
    *,
    plan_id: str,
    decision_id: str,
    new_id: str,
) -> None:
    decisions_path = plan_workspace.base_dir / plan_id / "decisions.jsonl"
    text = decisions_path.read_text(encoding="utf-8")
    decisions_path.write_text(text.replace(decision_id, new_id), encoding="utf-8")

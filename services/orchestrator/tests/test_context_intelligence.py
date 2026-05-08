from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from buildwealth_orchestrator.services.context_intelligence import (
    ACTION_READINESS_BY_MATERIALITY,
    CONTEXT_ASSEMBLER_VERSION,
    ContextAssembler,
    ContextIntelligenceService,
    MaterialityPolicy,
    classify_context_intent,
)
from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


class FakeEmbeddingClient:
    provider = "fake"
    model = "semantic-test"
    enabled = True

    def embed_text(self, text: str) -> list[float] | None:
        lowered = str(text or "").lower()
        if any(term in lowered for term in ("college", "education", "tuition", "school", "student")):
            return [1.0, 0.0, 0.0]
        if "nvda" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


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
    assert "portfolio/watchlist.json#items.NVDA.OPENBB" in source_refs
    assert any(ref.endswith("/decisions.jsonl#decision-fixed") for ref in source_refs)
    assert any(ref.endswith("research-dossier-nvda.md") for ref in source_refs)
    assert any(ref.startswith("recommendations/inbox.json#recommendations.") for ref in source_refs)
    assert first_report["embeddings"]["enabled"] is False


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


def test_context_search_retrieves_symbol_related_plan_research_and_watchlist(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    service.rebuild_registry()

    result = service.search_context(query="NVDA investment fit", symbols=["NVDA"], limit=20)
    source_refs = {item["source_ref"] for item in result["items"]}
    entity_types = {item["entity_type"] for item in result["items"]}

    assert result["count"] >= 4
    assert result["semantic"]["enabled"] is False
    assert any(ref.endswith("research-dossier-nvda.md") for ref in source_refs)
    assert any(ref.endswith("/decisions.jsonl#decision-fixed") for ref in source_refs)
    assert "portfolio/watchlist.json#items.NVDA.OPENBB" in source_refs
    assert "recommendation" in entity_types


def test_context_search_supports_plan_domain_and_recommendation_status_filters(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    service.rebuild_registry()
    plan_id = str(service.plan_workspace.list_plans(limit=1)[0]["id"])

    plan_result = service.search_context(plan_id=plan_id, domains=["plan", "research"], limit=50)
    assert plan_result["count"] >= 3
    assert all(
        item["structured_payload"].get("plan_id") == plan_id
        for item in plan_result["items"]
        if item["domain"] in {"plan", "research"} and item["entity_type"] != "watchlist_thesis"
    )

    recommendation_result = service.search_context(
        domains=["recommendation"],
        recommendation_status="proposed",
        limit=10,
    )
    assert recommendation_result["count"] == 1
    assert recommendation_result["items"][0]["structured_payload"]["status"] == "proposed"


def test_context_search_retrieves_profile_field_fact_and_metadata(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    service.rebuild_registry()

    result = service.search_context(
        query="tax rate",
        domains=["profile"],
        field_path="tax_profile.marginal_tax_rate",
        limit=5,
    )

    assert result["count"] == 1
    item = result["items"][0]
    assert item["entity_id"] == "tax_profile.marginal_tax_rate"
    assert item["structured_payload"]["value"] == 0.28
    assert item["quality"]["status"] == "user_confirmed"
    assert item["action_readiness"] == "Review before relying on this"
    assert "tax" in item["matched_terms"]


def test_context_intent_classification_is_deterministic() -> None:
    investment = classify_context_intent("Should I buy NVDA for my portfolio?", symbols=[])
    profile = classify_context_intent("What tax rate is in my profile?")

    assert investment["intent"] == "investment_fit"
    assert investment["symbols"] == ["NVDA"]
    assert "research" in investment["domains"]
    assert "symbol_detected" in investment["signals"]
    assert profile["intent"] == "profile_question"
    assert profile["domains"][0] == "profile"


def test_context_assembler_adds_retrieval_citations_conflicts_and_trace(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    assembler = ContextAssembler(
        context_service=service,
        max_retrieved_items=2,
        max_retrieved_text_chars=120,
    )
    plan_id = str(service.plan_workspace.list_plans(limit=1)[0]["id"])
    now = datetime.now(timezone.utc).isoformat()

    async def fake_structured_context_builder(**kwargs: object) -> dict[str, object]:
        return {
            "generated_at": now,
            "scope": {"plan_id": kwargs.get("plan_id"), "include_research": False, "detail_level": "light"},
            "cache": {},
            "location_state": "MN",
            "currency": "USD",
            "warnings": ["Financial profile metadata needs review."],
            "quality": {
                "freshness": {"generated_at": now, "snapshot_stale": None},
                "coverage": {
                    "score_pct": 80.0,
                    "checks": {"financial_profile_metadata": False},
                    "missing_sections": ["financial_profile.tax_profile.marginal_tax_rate.stale"],
                },
                "warnings": {"count": 1, "has_warnings": True},
                "summary": {"max_chars": 600, "full_chars": 700, "actual_chars": 600, "truncated": True},
            },
            "planning_defaults": {},
            "financial_picture": {},
            "planning": {},
            "research": {},
            "decisions": {},
            "summary": "Structured context",
        }

    assembled = asyncio.run(
        assembler.assemble_context(
            question="Should I buy NVDA?",
            plan_id=plan_id,
            symbols=["NVDA"],
            intent=None,
            structured_context_builder=fake_structured_context_builder,
            builder_options={"plan_id": plan_id},
        )
    )

    assert assembled["retrieved_context"]["count"] == 2
    assert assembled["citations"]
    assert assembled["context_budget"]["truncated"] is True
    assert assembled["conflicts"][0]["type"] == "missing_or_stale_context"
    assert "needs review" in assembled["conflicts"][0]["plain_language"]
    assert assembled["conflict_review_items"][0]["route"] == "profile"
    assert assembled["trace"]["assembler_version"] == CONTEXT_ASSEMBLER_VERSION
    assert assembled["trace"]["intent"]["intent"] == "investment_fit"
    assert assembled["trace"]["retrieval"]["citation_count"] == len(assembled["citations"])
    assert assembled["trace"]["context_warnings"][0]["type"] == "missing_or_stale_context"
    assert "needs review" in assembled["trace"]["context_warnings"][0]["message"]


def test_context_conflict_review_items_are_deduped_and_routed(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    conflict = {
        "id": "context_quality:tax-stale",
        "type": "missing_or_stale_context",
        "severity": "high",
        "plain_language": (
            "Your marginal tax rate needs review before using it for tax-sensitive advice."
        ),
        "source_refs": ["profile/financial_profile.json#tax_profile.marginal_tax_rate"],
        "missing_sections": ["financial_profile.tax_profile.marginal_tax_rate.stale"],
        "blocks_decision_grade_advice": True,
    }

    first_sync = service.sync_conflict_review_items(
        [conflict],
        plan_id="plan-1",
        symbols=["NVDA"],
        relevance_reason="copilot_answer",
    )
    second_sync = service.sync_conflict_review_items(
        [conflict],
        plan_id="plan-1",
        symbols=["NVDA"],
        relevance_reason="copilot_answer",
    )
    rows = [
        row
        for row in service.recommendation_inbox.list(limit=None, include_archived=True)
        if row["recommendation_type"] == "context_conflict_review"
    ]

    assert len(rows) == 1
    assert first_sync[0]["recommendation_id"] == second_sync[0]["recommendation_id"]
    assert first_sync[0]["created"] is True
    assert second_sync[0]["created"] is False

    item = rows[0]
    payload = item["action_payload"]
    context_conflict = payload["context_conflict"]
    assert item["source"] == "context_intelligence"
    assert item["priority"] == "high"
    assert item["recommendation_type"] == "context_conflict_review"
    assert "marginal tax rate needs review" in item["detail"]
    assert "explicit confirmation" in item["detail"]
    assert context_conflict["route"]["route"] == "profile"
    assert context_conflict["source_refs"] == ["profile/financial_profile.json#tax_profile.marginal_tax_rate"]
    assert context_conflict["seen_count"] == 2
    assert context_conflict["resolution_state"] == "unresolved"
    assert context_conflict["blocks_decision_grade_advice"] is True
    assert payload["quality"]["actionability"] == "review_only"
    assert payload["quality"]["blocking_context"] == [context_conflict["dedupe_key"]]
    assert any(action["action"] == "defer" for action in context_conflict["review_actions"])
    assert payload["suggested_action"]["mutation_requires_confirmation"] is True


def test_context_embeddings_store_only_eligible_rows_and_enable_semantic_search(tmp_path: Path) -> None:
    service = _build_service(tmp_path, embedding_client=FakeEmbeddingClient())

    rebuild_report = service.rebuild_registry()
    status = service.get_status()
    vectors = service.registry.embedding_vectors(provider="fake", model="semantic-test")
    result = service.search_context(query="school expenses", domains=["plan"], limit=5)
    top_item = result["items"][0]

    assert rebuild_report["embeddings"]["enabled"] is True
    assert rebuild_report["embeddings"]["eligible_count"] > 0
    assert status["embeddings"]["embedded_count"] == len(vectors)
    assert not any(item_id.startswith("ctx_profile") for item_id in vectors)

    assert result["semantic"]["enabled"] is True
    assert result["semantic"]["provider"] == "fake"
    assert "family-college-funding" in top_item["source_ref"]
    assert top_item["score_breakdown"]["semantic"] == 1.0
    assert top_item["matched_terms"] == []


def test_context_embeddings_can_be_rebuilt_without_reindexing_registry(tmp_path: Path) -> None:
    service = _build_service(tmp_path, embedding_client=FakeEmbeddingClient())
    service.rebuild_registry()

    report = service.rebuild_embeddings()

    assert report["enabled"] is True
    assert report["provider"] == "fake"
    assert report["eligible_count"] > 0
    assert report["reused_count"] > 0


def test_chat_fact_detection_drafts_material_context_candidates_for_review(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    candidates = service.detect_chat_context_candidates(
        message="My tax rate is 32% and my risk tolerance is moderate.",
        conversation_id="conversation-1",
        message_index=3,
    )
    candidates_again = service.detect_chat_context_candidates(
        message="My tax rate is 32% and my risk tolerance is moderate.",
        conversation_id="conversation-1",
        message_index=3,
    )
    review_rows = [
        row
        for row in service.recommendation_inbox.list(limit=None, include_archived=True)
        if row["recommendation_type"] == "context_candidate_review"
    ]

    assert len(candidates) == 2
    assert len(candidates_again) == 2
    assert len(review_rows) == 2

    tax_candidate = next(
        candidate
        for candidate in candidates
        if candidate["target_field"] == "tax_profile.marginal_tax_rate"
    )
    assert tax_candidate["source_domain"] == "conversation"
    assert tax_candidate["source_ref"] == "conversation/conversation-1#message.3"
    assert tax_candidate["target_domain"] == "profile"
    assert tax_candidate["target_value"] == 0.32
    assert tax_candidate["confidence"] == "medium"
    assert tax_candidate["materiality"] == "high"
    assert tax_candidate["action_readiness"] == "Review before relying on this"
    assert tax_candidate["review_route"]["route"] == "profile"
    assert tax_candidate["lifecycle_state"] == "pending_review"
    assert tax_candidate["prompt_influence"] == "mention_only"
    assert tax_candidate["metadata"]["materiality_policy_version"] == "global_v1"
    assert "profile_material_field_high" in tax_candidate["metadata"]["materiality_rule_ids"]

    review_payload = review_rows[0]["action_payload"]
    assert review_payload["quality"]["actionability"] == "review_only"
    assert review_payload["suggested_action"]["mutation_requires_confirmation"] is True
    assert "not treated as financial truth yet" in review_rows[0]["detail"]


def test_chat_income_claim_detection_drafts_review_only_profile_candidate(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    [candidate] = service.detect_chat_context_candidates(
        message="I make $100,000 per year and my wife makes $60,000 per year.",
        conversation_id="conversation-income",
        message_index=2,
    )
    review_rows = [
        row
        for row in service.recommendation_inbox.list(limit=None, include_archived=True)
        if row["recommendation_type"] == "context_candidate_review"
    ]

    assert candidate["source_domain"] == "conversation"
    assert candidate["source_ref"] == "conversation/conversation-income#message.2"
    assert candidate["target_domain"] == "profile"
    assert candidate["target_area"] == "income_items"
    assert candidate["target_field"] == "income_items"
    assert candidate["target_value"]["summary"] == "My income: $8,333.33/month; Spouse income: $5,000.00/month"
    assert candidate["target_value"]["income_items"] == [
        {
            "label": "My income",
            "monthly_amount_usd": 8333.33,
            "source_type": "salary",
            "is_pre_tax": False,
        },
        {
            "label": "Spouse income",
            "monthly_amount_usd": 5000.0,
            "source_type": "salary",
            "is_pre_tax": False,
        },
    ]
    assert candidate["target_value"]["requires_user_confirmation"] is True
    assert candidate["materiality"] == "high"
    assert candidate["lifecycle_state"] == "pending_review"
    assert candidate["prompt_influence"] == "mention_only"
    assert candidate["review_route"]["route"] == "profile"
    assert len(review_rows) == 1
    assert review_rows[0]["action_payload"]["suggested_action"]["mutation_requires_confirmation"] is True

    service.rebuild_registry()
    result = service.search_context(query="100000 wife income", domains=["profile"], limit=20)
    assert all(item["entity_type"] != "context_candidate" for item in result["items"])


def test_chat_income_claim_detection_ignores_hypotheticals(tmp_path: Path) -> None:
    service = _build_service(tmp_path)

    candidates = service.detect_chat_context_candidates(
        message="What if I make $100,000 per year after switching jobs?",
        conversation_id="conversation-income-hypothetical",
    )

    assert candidates == []


def test_unreviewed_context_candidates_do_not_become_authoritative_prompt_context(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    [candidate] = service.detect_chat_context_candidates(
        message="My tax rate is 32%.",
        conversation_id="conversation-2",
    )

    service.rebuild_registry()
    result = service.search_context(
        query="tax rate 32",
        domains=["profile"],
        limit=20,
    )

    assert candidate["lifecycle_state"] == "pending_review"
    assert candidate["prompt_influence"] == "mention_only"
    assert all(item["entity_type"] != "context_candidate" for item in result["items"])


def test_applied_candidates_can_be_supporting_context_but_stale_or_archived_cannot(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    candidate = service.draft_context_candidate(
        source_domain="conversation",
        source_ref="conversation/preference#message.1",
        extracted_claim="I prefer plain-language explanations before financial terminology.",
        target_domain="conversation",
        target_area="preference",
        target_field="preference.explanation_style",
        target_value="plain_language_first",
        confidence="medium",
        metadata={"note": "preference, not financial fact"},
    )

    service.update_context_candidate_lifecycle(
        candidate["id"],
        lifecycle_state="applied",
        prompt_influence="supporting_context",
    )
    events = service.list_context_candidate_events(candidate["id"])
    service.rebuild_registry()
    applied_result = service.search_context(query="plain language explanations", domains=["conversation"], limit=10)
    applied_items = [item for item in applied_result["items"] if item["entity_type"] == "context_candidate"]
    assert applied_items
    assert applied_items[0]["quality"]["prompt_influence"] == "supporting_context"
    assert [event["event_type"] for event in events] == ["candidate_created", "candidate_applied"]

    service.update_context_candidate_lifecycle(
        candidate["id"],
        lifecycle_state="stale_unconfirmed",
        prompt_influence="none",
    )
    service.rebuild_registry()
    stale_result = service.search_context(query="plain language explanations", domains=["conversation"], limit=10)
    assert all(item["entity_type"] != "context_candidate" for item in stale_result["items"])

    archived = service.update_context_candidate_lifecycle(candidate["id"], lifecycle_state="archived")
    service.rebuild_registry()
    archived_result = service.search_context(query="plain language explanations", domains=["conversation"], limit=10)
    audit_rows = service.list_context_candidates(include_archived=True, limit=None)
    assert archived["lifecycle_state"] == "archived"
    assert any(row["id"] == candidate["id"] for row in audit_rows)
    assert all(item["entity_type"] != "context_candidate" for item in archived_result["items"])


def test_resolved_material_context_candidates_close_review_item(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    [candidate] = service.detect_chat_context_candidates(
        message="My marginal tax rate is 32%.",
        conversation_id="conversation-1",
        message_index=1,
    )
    review_items = [
        row
        for row in service.recommendation_inbox.list(limit=None, include_archived=True)
        if row["recommendation_type"] == "context_candidate_review"
    ]
    assert len(review_items) == 1
    assert review_items[0]["status"] == "proposed"

    service.update_context_candidate_lifecycle(
        candidate["id"],
        lifecycle_state="applied",
        prompt_influence="authoritative",
        metadata_patch={"resolution_state": "resolved_by_source_update"},
    )

    [closed] = [
        row
        for row in service.recommendation_inbox.list(limit=None, include_archived=True)
        if row["recommendation_type"] == "context_candidate_review"
    ]
    assert closed["status"] == "applied"
    assert closed["action_payload"]["context_candidate"]["lifecycle_state"] == "applied"
    assert closed["action_payload"]["quality"]["blocking_context"] == []


def test_conversation_summary_candidates_are_reviewable_registry_only_captures(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    conversation = {
        "id": "conversation-summary",
        "messages": [
            {"role": "user", "content": f"Question {index}: explain the plan plainly."}
            for index in range(9)
        ],
    }

    candidate = service.summarize_conversation_candidate(conversation=conversation, min_messages=8)

    assert candidate is not None
    assert candidate["source_ref"] == "conversation/conversation-summary#summary"
    assert candidate["target_domain"] == "conversation"
    assert candidate["target_area"] == "conversation_summary"
    assert candidate["lifecycle_state"] == "pending_review"
    assert candidate["prompt_influence"] == "mention_only"
    assert candidate["materiality"] == "low"
    assert "message_count" in candidate["target_value"]


def test_deferred_context_conflict_does_not_resolve_or_unblock_and_resurfaces(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    conflict = {
        "id": "context_quality:policy-stale",
        "type": "missing_or_stale_context",
        "severity": "high",
        "plain_language": "Your investment policy needs review before using it for advice.",
        "source_refs": ["profile/financial_profile.json#investment_policy.max_single_symbol_exposure_pct"],
        "blocks_decision_grade_advice": True,
    }
    created = service.sync_conflict_review_items(
        [conflict],
        plan_id="plan-1",
        symbols=["NVDA"],
        relevance_reason="background_index",
    )[0]
    deferred_until = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    deferred = service.defer_context_conflict_review_item(
        str(created["recommendation_id"]),
        deferred_until=deferred_until,
        reason="Review this after plan cleanup.",
    )
    deferred_conflict = deferred["action_payload"]["context_conflict"]
    assert deferred["status"] == "proposed"
    assert deferred_conflict["resolution_state"] == "deferred"
    assert deferred_conflict["blocks_decision_grade_advice"] is True
    assert deferred["action_payload"]["quality"]["blocking_context"] == [deferred_conflict["dedupe_key"]]

    still_deferred = service.sync_conflict_review_items(
        [conflict],
        plan_id="plan-1",
        symbols=["NVDA"],
        relevance_reason="background_index",
        now=datetime.now(timezone.utc),
    )[0]
    assert still_deferred["resolution_state"] == "deferred"
    assert still_deferred["blocks_decision_grade_advice"] is True

    resurfaced_for_relevance = service.sync_conflict_review_items(
        [conflict],
        plan_id="plan-1",
        symbols=["NVDA"],
        relevance_reason="investment_fit_review",
        now=datetime.now(timezone.utc),
    )[0]
    assert resurfaced_for_relevance["resolution_state"] == "unresolved"
    assert resurfaced_for_relevance["relevance_triggered_resurfaced"] is True

    service.defer_context_conflict_review_item(
        str(created["recommendation_id"]),
        deferred_until=deferred_until,
        reason="Snooze again.",
    )
    resurfaced_for_time = service.sync_conflict_review_items(
        [conflict],
        plan_id="plan-1",
        symbols=["NVDA"],
        relevance_reason="background_index",
        now=datetime.now(timezone.utc) + timedelta(days=8),
    )[0]
    assert resurfaced_for_time["resolution_state"] == "unresolved"


def _build_service(
    tmp_path: Path,
    *,
    embedding_client: object | None = None,
) -> ContextIntelligenceService:
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
        summary="Avoid adding NVDA single-stock exposure until concentration is reviewed.",
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
    plan_workspace.write_artifact(
        plan_id=plan_id,
        title="Family College Funding",
        markdown=(
            "# Family College Funding\n\n"
            "Build a college tuition bridge before increasing taxable brokerage risk.\n"
        ),
        kind="planning-note",
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

    portfolio_store = PortfolioStore(tmp_path / "portfolio")
    portfolio_store.upsert_watchlist_item(
        symbol="NVDA",
        thesis="Growth remains attractive, but valuation and single-symbol concentration must be reviewed first.",
        note="Use the investment policy before increasing exposure.",
        target_price_usd=950.0,
        tags=["semiconductors", "ai"],
    )

    return ContextIntelligenceService(
        database_path=tmp_path / "storage" / "context_index.db",
        financial_profile_store=profile_store,
        plan_workspace=plan_workspace,
        recommendation_inbox=recommendation_inbox,
        portfolio_store=portfolio_store,
        embedding_client=embedding_client,
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

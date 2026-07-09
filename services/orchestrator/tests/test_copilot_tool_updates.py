import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox


def test_copilot_registry_includes_phase_3_5_tools() -> None:
    required_tools = {
        "get_account_balances",
        "compute_tax",
        "add_timeline_event",
        "compare_withdrawal_strategies",
        "get_asset_allocation",
        "set_contribution_rules",
        "get_buildwealth_context",
        "search_context",
        "pin_watchlist_research_to_plan",
        "research_compare",
        "research_dossier",
        "research_dossier_lookup",
        "research_watchlist_rank",
        "assess_portfolio_fit",
        "draft_investment_research_recommendation",
        "draft_watchlist_thesis_revision",
        "draft_dossier_thesis_revision",
        "update_recommendation_outcome",
        "get_recommendation_closure_analytics",
        "create_plan_recommendation_closure_summary",
        "get_plan_review_context",
        "preview_recommendation",
        "draft_financial_profile_update",
        "list_import_reports",
        "get_import_report",
    }
    assert required_tools <= set(main.copilot.tools.keys())


def test_copilot_prompt_includes_context_quality_guidance() -> None:
    prompt = str(main.copilot.system_prompt)
    assert "quality.freshness.snapshot_stale" in prompt
    assert "caveat recommendations when context quality is degraded" in prompt
    assert "draft_watchlist_thesis_revision" in prompt
    assert "draft_dossier_thesis_revision" in prompt
    assert "user review without saving" in prompt
    assert "Import Report ID" in prompt
    assert "Saved Simulation IDs" in prompt
    assert "draft and review helper" in prompt


def test_copilot_native_boundary_tool_descriptions() -> None:
    descriptions = "\n".join(str(tool.description) for tool in main.copilot.tools.values())
    assert "Fetch a live portfolio snapshot from Portfolio Analysis" not in descriptions
    assert "List known Portfolio Analysis accounts" not in descriptions
    assert "Import Reports" in descriptions
    assert "BuildWealth portfolio accounts" in descriptions


def test_import_report_copilot_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeImportWorkbenchStore:
        def list_reports(self, limit: int = 10):
            return [{"report_id": "ir_1", "summary": {"accepted_count": 2}, "imported_activities": 2}]

        def load_report(self, report_id: str):
            return {"report_id": report_id, "summary": {"accepted_count": 2}}

    monkeypatch.setattr(main, "import_workbench_store", FakeImportWorkbenchStore())

    listed = asyncio.run(main.tool_list_import_reports({"limit": 5}))
    detail = asyncio.run(main.tool_get_import_report({"report_id": "ir_1"}))

    assert listed["reports"][0]["report_id"] == "ir_1"
    assert detail["report_id"] == "ir_1"


def test_get_buildwealth_context_tool_supports_detail_level_control() -> None:
    tool = main.copilot.tools["get_buildwealth_context"]
    properties = tool.parameters.get("properties", {})
    detail_field = properties.get("detail_level")
    assert isinstance(detail_field, dict)
    assert detail_field.get("enum") == ["light", "full"]
    assert "detail_level=light" in tool.description
    assert "research and plan projection off" in tool.description


def test_search_context_tool_contract() -> None:
    tool = main.copilot.tools["search_context"]
    properties = tool.parameters.get("properties", {})
    assert "query" in properties
    assert "domain" in properties
    assert "domains" in properties
    assert "plan_id" in properties
    assert "symbol" in properties
    assert "symbols" in properties
    assert "recommendation_status" in properties
    assert "field_path" in properties
    assert "decision-grade advice" in tool.description


def test_search_context_tool_and_endpoint_parse_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeContextIntelligenceService:
        def search_context(self, **kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            return {"count": 0, "items": [], "filters": kwargs}

    monkeypatch.setattr(main, "context_intelligence_service", FakeContextIntelligenceService())

    tool_result = asyncio.run(
        main.tool_search_context(
            {
                "query": "NVDA fit",
                "domain": "research",
                "symbols": ["NVDA", "MSFT"],
                "plan_id": "plan-1",
                "recommendation_status": "proposed",
                "field_path": "investment_policy.max_single_symbol_exposure_pct",
                "limit": 5,
            }
        )
    )
    endpoint_result = main.search_context_endpoint(
        q="tax rate",
        domain="profile",
        symbols="NVDA, AAPL",
        entity_type="tax_profile_field",
        limit=3,
        rebuild_if_empty=False,
    )

    assert tool_result["count"] == 0
    assert endpoint_result["count"] == 0
    assert calls[0]["query"] == "NVDA fit"
    assert calls[0]["domains"] == ["research"]
    assert calls[0]["symbols"] == ["NVDA", "MSFT"]
    assert calls[0]["rebuild_if_empty"] is True
    assert calls[1]["query"] == "tax rate"
    assert calls[1]["domains"] == ["profile"]
    assert calls[1]["symbols"] == ["NVDA", "AAPL"]
    assert calls[1]["entity_types"] == ["tax_profile_field"]
    assert calls[1]["rebuild_if_empty"] is False


def test_copilot_chat_uses_context_assembler_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assembler_calls: list[dict[str, object]] = []
    copilot_calls: list[dict[str, object]] = []
    now = main.context_utc_now_iso()

    class FakeAssembler:
        async def assemble_context(self, **kwargs: object) -> dict[str, object]:
            assembler_calls.append(kwargs)
            return {
                "generated_at": now,
                "scope": {"plan_id": kwargs.get("plan_id"), "include_research": False, "detail_level": "light"},
                "cache": {},
                "location_state": "MN",
                "currency": "USD",
                "warnings": [],
                "quality": {
                    "freshness": {"generated_at": now, "snapshot_stale": None},
                    "coverage": {"score_pct": 100.0, "checks": {}, "missing_sections": []},
                    "warnings": {"count": 0, "has_warnings": False},
                    "summary": {"max_chars": 1000, "full_chars": 20, "actual_chars": 20, "truncated": False},
                },
                "planning_defaults": {},
                "financial_picture": {},
                "planning": {},
                "research": {},
                "decisions": {},
                "retrieved_context": {"count": 1, "items": [{"id": "ctx_profile"}]},
                "citations": [{"context_item_id": "ctx_profile", "source_ref": "profile/financial_profile.json"}],
                "context_budget": {"truncated": False, "returned_items": 1},
                "conflicts": [],
                "trace": {"assembler_version": "context_intelligence_assembler_v1", "intent": {"intent": "profile_question"}},
                "summary": "assembled context",
            }

    class FakeCopilot:
        async def chat(self, **kwargs: object) -> dict[str, object]:
            copilot_calls.append(kwargs)
            return {
                "conversation_id": "conversation-1",
                "answer": "ok",
                "tool_calls": [],
                "model": "fake",
                "context_trace": kwargs.get("context_trace"),
                "created_at": main.utc_now(),
            }

    class FakeConversationStore:
        def __init__(self) -> None:
            self.docs: dict[str, dict[str, object]] = {}

        def get_or_create(self, conversation_id: str | None, first_user_message: str) -> dict[str, object]:
            if conversation_id and conversation_id in self.docs:
                return self.docs[conversation_id]
            doc = {
                "id": conversation_id or "conversation-1",
                "title": first_user_message[:64],
                "focus": {
                    "mode": "balanced",
                    "primary_domains": [],
                    "secondary_domains": [],
                    "muted_domains": [],
                    "pinned_entity_ids": [],
                    "priority_note": "",
                    "set_by": "default",
                    "updated_at": None,
                    "schema_version": 1,
                },
                "messages": [],
            }
            self.docs[str(doc["id"])] = doc
            return doc

        def get(self, conversation_id: str) -> dict[str, object]:
            return self.docs[conversation_id]

        def update_focus(self, conversation_id: str, focus: dict[str, object]) -> dict[str, object]:
            doc = self.docs[conversation_id]
            doc["focus"] = focus
            return doc

        def update_latest_assistant_metadata(self, conversation_id: str, metadata: dict[str, object]) -> None:
            return None

    fake_store = FakeConversationStore()
    monkeypatch.setattr(main, "context_assembler", FakeAssembler())
    monkeypatch.setattr(main, "copilot", FakeCopilot())
    monkeypatch.setattr(main, "conversation_store", fake_store)

    response = asyncio.run(
        main.copilot_chat(
            main.CopilotChatRequest(
                question="What tax rate is in my profile?",
                plan_id="plan-1",
            )
        )
    )

    assert assembler_calls[0]["question"] == "What tax rate is in my profile?"
    assert assembler_calls[0]["plan_id"] == "plan-1"
    contextual_brief = copilot_calls[0]["contextual_brief"]
    assert isinstance(contextual_brief, str)
    assert '"retrieved_context"' in contextual_brief
    assert '"brief_version"' in contextual_brief
    assert "copilot_prompt_brief_v1" in contextual_brief
    # Slim brief: no full assembler dump / registry telemetry in the system message.
    assert '"assembler_version"' not in contextual_brief
    assert '"registry"' not in contextual_brief
    assert copilot_calls[0]["conversation"]["id"] == "conversation-1"
    assert copilot_calls[0]["context_trace"]["assembler_version"] == "context_intelligence_assembler_v1"
    assert copilot_calls[0]["context_trace"]["focus_applied"]["effect"] == "stored_only"
    assert response.context_trace["intent"]["intent"] == "profile_question"
    assert response.context_trace["focus_applied"]["effect"] == "stored_only"
    assert response.focus is not None
    assert response.focus.mode == "balanced"


def test_copilot_chat_persists_request_focus_before_assembly(monkeypatch: pytest.MonkeyPatch) -> None:
    copilot_calls: list[dict[str, object]] = []
    now = main.context_utc_now_iso()

    class FakeAssembler:
        async def assemble_context(self, **kwargs: object) -> dict[str, object]:
            return {
                "generated_at": now,
                "scope": {"plan_id": None, "include_research": False, "detail_level": "light"},
                "cache": {},
                "location_state": "MN",
                "currency": "USD",
                "warnings": [],
                "quality": {
                    "freshness": {"generated_at": now, "snapshot_stale": None},
                    "coverage": {"score_pct": 100.0, "checks": {}, "missing_sections": []},
                    "warnings": {"count": 0, "has_warnings": False},
                    "summary": {"max_chars": 1000, "full_chars": 20, "actual_chars": 20, "truncated": False},
                },
                "planning_defaults": {},
                "financial_picture": {},
                "planning": {},
                "research": {},
                "decisions": {},
                "retrieved_context": {"count": 0, "items": []},
                "citations": [],
                "context_budget": {"truncated": False, "returned_items": 0},
                "conflicts": [],
                "trace": {"assembler_version": "context_intelligence_assembler_v1", "intent": {"intent": "planning_question"}},
                "summary": "assembled context",
            }

    class FakeCopilot:
        async def chat(self, **kwargs: object) -> dict[str, object]:
            copilot_calls.append(kwargs)
            conversation = kwargs.get("conversation")
            assert isinstance(conversation, dict)
            return {
                "conversation_id": conversation["id"],
                "answer": "ok",
                "tool_calls": [],
                "model": "fake",
                "context_trace": kwargs.get("context_trace"),
                "created_at": main.utc_now(),
            }

    class FakeConversationStore:
        def __init__(self) -> None:
            self.docs: dict[str, dict[str, object]] = {}

        def get_or_create(self, conversation_id: str | None, first_user_message: str) -> dict[str, object]:
            doc = {
                "id": "conv-focus-1",
                "title": first_user_message[:64],
                "focus": {
                    "mode": "balanced",
                    "primary_domains": [],
                    "secondary_domains": [],
                    "muted_domains": [],
                    "pinned_entity_ids": [],
                    "priority_note": "",
                    "set_by": "default",
                    "updated_at": None,
                    "schema_version": 1,
                },
                "messages": [],
            }
            self.docs[str(doc["id"])] = doc
            return doc

        def get(self, conversation_id: str) -> dict[str, object]:
            return self.docs[conversation_id]

        def update_focus(self, conversation_id: str, focus: dict[str, object]) -> dict[str, object]:
            doc = self.docs[conversation_id]
            doc["focus"] = focus
            return doc

        def update_latest_assistant_metadata(self, conversation_id: str, metadata: dict[str, object]) -> None:
            return None

    store = FakeConversationStore()
    monkeypatch.setattr(main, "context_assembler", FakeAssembler())
    monkeypatch.setattr(main, "copilot", FakeCopilot())
    monkeypatch.setattr(main, "conversation_store", store)

    response = asyncio.run(
        main.copilot_chat(
            main.CopilotChatRequest(
                question="Help with my plan",
                focus=main.SessionFocus(
                    mode="narrow",
                    primary_domains=["plan"],
                    muted_domains=["research"],
                    set_by="entry_surface",
                ),
                persist_focus=True,
            )
        )
    )

    assert store.docs["conv-focus-1"]["focus"]["primary_domains"] == ["plan"]
    assert store.docs["conv-focus-1"]["focus"]["muted_domains"] == ["research"]
    assert store.docs["conv-focus-1"]["focus"]["set_by"] == "entry_surface"
    assert copilot_calls[0]["conversation"]["focus"]["primary_domains"] == ["plan"]
    assert response.focus is not None
    assert response.focus.primary_domains == ["plan"]
    assert response.context_trace["focus_applied"]["effect"] == "stored_only"
    assert response.context_trace["focus_applied"]["primary_domains"] == ["plan"]
    assert "session_focus" in copilot_calls[0]["contextual_brief"]


def test_assess_portfolio_fit_tool_contract() -> None:
    tool = main.copilot.tools["assess_portfolio_fit"]
    properties = tool.parameters.get("properties", {})
    assert tool.parameters.get("required") == ["symbol"]
    assert "symbol" in properties
    assert "amount_usd" in properties
    assert "period" in properties
    assert "interval" in properties
    assert "does not execute trades" in tool.description


def test_compute_tax_tool_supports_state_tax_and_irmaa_inputs() -> None:
    tool = main.copilot.tools["compute_tax"]
    properties = tool.parameters.get("properties", {})
    assert "state_tax_rate" in properties
    assert "state_tax_deduction_usd" in properties
    assert "tax_exempt_interest_income_usd" in properties
    assert "age" in properties
    assert "include_irmaa" in properties
    assert "medicare_months_covered" in properties


def test_run_planning_tool_supports_roth_conversion_and_drawdown_inputs() -> None:
    tool = main.copilot.tools["run_planning_scenarios"]
    properties = tool.parameters.get("properties", {})
    assert "roth_conversion_annual_amount_usd" in properties
    assert "roth_conversion_start_age" in properties
    assert "roth_conversion_end_age" in properties
    assert "drawdown_order" in properties
    assert "simulation_mode" in properties
    assert "simulation_monte_carlo_variant" in properties
    assert "simulation_historical_start_year" in properties
    assert "simulation_seed" in properties


def test_update_plan_settings_tool_supports_household_inputs() -> None:
    tool = main.copilot.tools["update_plan_settings"]
    properties = tool.parameters.get("properties", {})
    assert "simulation_mode" in properties
    assert "simulation_monte_carlo_variant" in properties
    assert "simulation_historical_start_year" in properties
    assert "simulation_seed" in properties
    assert "household_mode" in properties
    assert "household_partner_income_usd" in properties
    assert "household_partner_income_growth_rate" in properties
    assert "household_partner_retirement_age" in properties
    assert "household_partner_social_security_annual_usd" in properties
    assert "household_partner_social_security_claiming_age" in properties
    assert "household_shared_goal_target_usd" in properties
    assert "household_shared_goal_target_year" in properties
    assert "filing_status" in properties


def test_apply_recommendation_tool_supports_decision_packet_controls() -> None:
    tool = main.copilot.tools["apply_recommendation"]
    properties = tool.parameters.get("properties", {})
    assert "create_decision_packet" in properties
    assert "capture_scenario_diff" in properties
    assert "decision_packet_research_symbols" in properties
    assert "pin_research_bridge" in properties
    assert "research_bridge_symbols" in properties
    assert "research_bridge_template_id" in properties


def test_reject_recommendation_tool_supports_decision_packet_controls() -> None:
    tool = main.copilot.tools["reject_recommendation"]
    properties = tool.parameters.get("properties", {})
    assert "plan_id" in properties
    assert "capture_scenario_diff" in properties
    assert "create_decision_packet" in properties
    assert "decision_packet_research_symbols" in properties


def test_update_recommendation_outcome_tool_contract() -> None:
    tool = main.copilot.tools["update_recommendation_outcome"]
    properties = tool.parameters.get("properties", {})
    assert "recommendation_id" in properties
    assert "plan_id" in properties
    assert "realized_delta_future_value_usd" in properties
    assert "realized_delta_real_value_usd" in properties
    assert "observed_at" in properties
    assert "observation_window_days" in properties
    assert "measurement_source" in properties
    assert "note" in properties


def test_get_recommendation_closure_analytics_tool_contract() -> None:
    tool = main.copilot.tools["get_recommendation_closure_analytics"]
    properties = tool.parameters.get("properties", {})
    assert "limit" in properties
    assert "plan_id" in properties
    assert "statuses" in properties
    assert "include_pending_realized" in properties


def test_create_plan_recommendation_closure_summary_tool_contract() -> None:
    tool = main.copilot.tools["create_plan_recommendation_closure_summary"]
    properties = tool.parameters.get("properties", {})
    assert "plan_id" in properties
    assert "limit" in properties
    assert "statuses" in properties
    assert "include_pending_realized" in properties
    assert "write_artifact" in properties


def test_get_plan_review_context_tool_contract() -> None:
    tool = main.copilot.tools["get_plan_review_context"]
    properties = tool.parameters.get("properties", {})
    assert "plan_id" in properties
    assert "selected_artifact_ids" in properties
    assert "scenario_diff_result" in properties
    assert "max_health_signals" in properties
    assert "bounded" in tool.description
    assert "full artifact contents" in tool.description


def test_preview_recommendation_tool_contract() -> None:
    tool = main.copilot.tools["preview_recommendation"]
    properties = tool.parameters.get("properties", {})
    assert "recommendation_id" in properties
    assert "plan_id" in properties
    assert "plan_settings_updates" in properties
    assert "capture_scenario_diff" in properties
    assert "decision_status" in properties


def test_list_recommendations_tool_contract_includes_sort() -> None:
    tool = main.copilot.tools["list_recommendations"]
    properties = tool.parameters.get("properties", {})
    assert "status" in properties
    assert "plan_id" in properties
    assert "limit" in properties
    assert "include_archived" in properties
    assert "sort" in properties


def test_draft_financial_profile_update_tool_contract() -> None:
    tool = main.copilot.tools["draft_financial_profile_update"]
    properties = tool.parameters.get("properties", {})
    assert "income_items" in properties
    assert "expense_items" in properties
    assert "debt_items" in properties
    assert "goal_items" in properties
    assert "physical_assets" in properties
    assert "tax_profile" in properties
    assert "investment_policy" in properties
    assert "flags" in properties
    assert "notes" in properties


def test_draft_investment_research_recommendation_tool_contract() -> None:
    tool = main.copilot.tools["draft_investment_research_recommendation"]
    properties = tool.parameters.get("properties", {})
    assert tool.parameters.get("required") == ["symbol"]
    assert "symbol" in properties
    assert "fit_status" in properties
    assert "fit_score" in properties
    assert "research_evidence_packet_id" in properties
    assert "suggested_action_kind" in properties
    assert "review-only" in tool.description
    assert "does not create buy/sell actions" in tool.description
    outcome_tool = main.copilot.tools["update_recommendation_outcome"]
    outcome_properties = outcome_tool.parameters.get("properties", {})
    assert "process_outcome" in outcome_properties
    assert "evidence_sufficiency" in outcome_properties


def test_draft_watchlist_thesis_revision_tool_contract() -> None:
    tool = main.copilot.tools["draft_watchlist_thesis_revision"]
    properties = tool.parameters.get("properties", {})
    assert tool.parameters.get("required") == ["symbol", "proposed_thesis"]
    assert "symbol" in properties
    assert "data_source" in properties
    assert "proposed_thesis" in properties
    assert "proposed_note" in properties
    assert "reference_price_usd" in properties
    assert "review_window_days" in properties
    assert "rationale" in properties
    assert "evidence_gaps" in properties
    assert "user review" in tool.description
    assert "without saving" in tool.description


def test_draft_dossier_thesis_revision_tool_contract() -> None:
    tool = main.copilot.tools["draft_dossier_thesis_revision"]
    properties = tool.parameters.get("properties", {})
    assert tool.parameters.get("required") == ["plan_id", "artifact_id", "proposed_thesis"]
    assert "plan_id" in properties
    assert "artifact_id" in properties
    assert "proposed_thesis" in properties
    assert "reference_price_usd" in properties
    assert "review_window_days" in properties
    assert "rationale" in properties
    assert "evidence_gaps" in properties
    assert "user review" in tool.description
    assert "without saving" in tool.description


def test_tool_get_plan_review_context_returns_bounded_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Bounded Plan")
    workspace.update_plan_settings(
        plan_id=plan["id"],
        updates={
            "annual_contribution_usd": 0,
            "expected_return_baseline": 0.065,
            "marginal_tax_rate": None,
        },
        log_decision=False,
    )
    workspace.update_plan_assumption_sets(
        plan_id=plan["id"],
        assumption_sets_payload={
            "schema_version": 2,
            "active_assumption_set_id": "policy",
            "sets": [
                {
                    "id": "policy",
                    "name": "Policy baseline",
                    "description": "Use personal policy assumptions.",
                    "settings": {
                        "expected_return_baseline": 0.065,
                        "marginal_tax_rate": None,
                    },
                }
            ],
        },
        log_decision=False,
    )
    artifact = workspace.write_artifact(
        plan_id=plan["id"],
        title="Research Dossier - MSFT",
        kind="research_dossier",
        markdown=(
            "# Research Dossier - MSFT\n\n"
            "Citation research-evidence:yfinance:MSFT:6mo:1d.\n\n"
            "SECRET FULL ARTIFACT BODY SHOULD NOT BE RETURNED."
        ),
    )
    workspace.write_artifact(
        plan_id=plan["id"],
        title="Unselected Research Dossier - NVDA",
        kind="research_dossier",
        markdown="research-evidence:yfinance:NVDA:6mo:1d",
    )
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    inbox.create(
        title="Review stale assumptions",
        detail="Tax context is missing.",
        source="generator:stale_assumptions",
        plan_id=plan["id"],
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = asyncio.run(
        main.tool_get_plan_review_context(
            {
                "plan_id": plan["id"],
                "selected_artifact_ids": [artifact["id"]],
                "scenario_diff_result": {
                    "scenario_deltas": [
                        {
                            "label": "baseline",
                            "delta_future_value_usd": 42000,
                            "delta_real_value_usd": 30000,
                        }
                    ],
                    "raw_rows": ["this should be omitted"],
                },
                "max_health_signals": 5,
            }
        )
    )

    assert payload["plan_id"] == plan["id"]
    assert payload["title"] == "Bounded Plan"
    assert payload["active_assumption_set"]["name"] == "Policy baseline"
    assert len(payload["health_signals"]) <= 5
    assert {signal["id"] for signal in payload["health_signals"]} >= {
        "tax-assumptions",
        "contribution-assumptions",
        "open-stale-assumptions",
    }
    assert payload["selected_artifacts"] == [
        {
            "id": artifact["id"],
            "title": "Research Dossier - MSFT",
            "file_name": artifact["file_name"],
            "citations": ["research-evidence:yfinance:MSFT:6mo:1d"],
        }
    ]
    assert "SECRET FULL ARTIFACT BODY" not in str(payload)
    assert "Unselected Research Dossier" not in str(payload)
    assert payload["scenario_diff_summary"]["deltas"][0]["delta_future_value_usd"] == 42000
    assert "raw_rows" not in str(payload["scenario_diff_summary"])
    assert payload["suggested_next_step"]["section"] == "assumptions"


def test_tool_draft_watchlist_thesis_revision_does_not_save(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    portfolio = PortfolioStore(tmp_path / "portfolio")
    portfolio.upsert_watchlist_item(
        symbol="NVDA",
        data_source="OPENBB",
        thesis="Old thesis",
        thesis_reference_price_usd=800.0,
        tags=["ai"],
    )
    monkeypatch.setattr(main, "portfolio_store", portfolio)

    payload = asyncio.run(
        main.tool_draft_watchlist_thesis_revision(
            {
                "symbol": "nvda",
                "proposed_thesis": "Only keep NVDA on the watchlist if portfolio concentration and valuation remain inside policy.",
                "proposed_note": "Revisit if evidence freshness degrades.",
                "reference_price_usd": 898.0,
                "review_window_days": 45,
                "rationale": "Price moved materially from the prior thesis reference.",
                "evidence_gaps": ["tax lot impact not reviewed"],
            }
        )
    )

    assert payload["draft_kind"] == "watchlist_thesis_revision"
    assert payload["requires_confirmation"] is True
    assert payload["target"] == {"type": "watchlist", "symbol": "NVDA", "data_source": "OPENBB"}
    assert payload["current"]["thesis"] == "Old thesis"
    assert payload["proposed"]["thesis"].startswith("Only keep NVDA")
    assert payload["proposed"]["reference_price_usd"] == pytest.approx(898.0)
    assert payload["proposed"]["review_window_days"] == 45
    assert payload["rationale"] == "Price moved materially from the prior thesis reference."
    assert payload["evidence_gaps"] == ["tax lot impact not reviewed"]
    assert portfolio.list_watchlist()[0]["thesis"] == "Old thesis"
    assert portfolio.list_watchlist()[0]["thesis_reference_price_usd"] == pytest.approx(800.0)


def test_tool_draft_dossier_thesis_revision_does_not_save(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Dossier Plan")
    artifact = workspace.write_artifact(
        plan_id=plan["id"],
        title="Research Dossier - MSFT vs VTI",
        kind="research_dossier",
        markdown="\n".join([
            "# Research Dossier: MSFT vs VTI",
            "",
            "## Thesis",
            "",
            "Old dossier thesis.",
            "",
            "## Evidence Packets",
            "",
            "| Symbol | Packet | Provider | Freshness | Confidence | Coverage | Blocking gaps |",
            "| --- | --- | --- | --- | --- | ---: | --- |",
            "| MSFT | research-evidence:yfinance:MSFT:6mo:1d | yfinance | stale | medium | 82% | none |",
        ]),
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = asyncio.run(
        main.tool_draft_dossier_thesis_revision(
            {
                "plan_id": plan["id"],
                "artifact_id": artifact["id"],
                "proposed_thesis": "Revised dossier thesis focused on fit, evidence freshness, and portfolio concentration.",
                "reference_price_usd": 410.0,
                "review_window_days": 60,
                "rationale": "The prior thesis expired and provider evidence is stale.",
                "evidence_gaps": ["provider freshness should be refreshed"],
            }
        )
    )

    assert payload["draft_kind"] == "dossier_thesis_revision"
    assert payload["requires_confirmation"] is True
    assert payload["target"] == {
        "type": "dossier",
        "plan_id": plan["id"],
        "artifact_id": artifact["id"],
        "title": "Research Dossier: MSFT vs VTI",
    }
    assert payload["current"]["thesis"] == "Old dossier thesis."
    assert payload["proposed"]["thesis"].startswith("Revised dossier thesis")
    assert payload["proposed"]["reference_price_usd"] == pytest.approx(410.0)
    assert payload["proposed"]["review_window_days"] == 60
    assert payload["evidence_gaps"] == ["provider freshness should be refreshed"]
    assert "Old dossier thesis." in workspace.read_artifact(plan["id"], artifact["id"])["content"]


def test_save_watchlist_thesis_revision_updates_review_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    portfolio = PortfolioStore(tmp_path / "portfolio")
    portfolio.upsert_watchlist_item(
        symbol="NVDA",
        data_source="OPENBB",
        thesis="Old thesis",
        note="Old note",
        thesis_reference_price_usd=800.0,
    )
    monkeypatch.setattr(main, "portfolio_store", portfolio)

    payload = main.save_portfolio_watchlist_thesis_revision(
        "nvda",
        {
            "data_source": "OPENBB",
            "thesis": "Revised thesis",
            "note": "Revised note",
            "thesis_reference_price_usd": 898.0,
            "review_window_days": 45,
        },
    )

    item = payload["item"]
    assert item["symbol"] == "NVDA"
    assert item["thesis"] == "Revised thesis"
    assert item["note"] == "Revised note"
    assert item["thesis_reference_price_usd"] == pytest.approx(898.0)
    assert item["thesis_reviewed_at"]
    assert item["thesis_expires_at"]
    assert payload["thesis_review"]["status"] == "current"
    assert payload["thesis_review"]["target"] == "watchlist"
    assert payload["thesis_review"]["symbol"] == "NVDA"


def test_save_watchlist_thesis_revision_records_compact_bounded_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    portfolio = PortfolioStore(tmp_path / "portfolio")
    old_long = "Old thesis " + ("with detailed context " * 40)
    new_long = "Revised thesis " + ("with refreshed fit context " * 40)
    portfolio.upsert_watchlist_item(
        symbol="NVDA",
        data_source="OPENBB",
        thesis=old_long,
        note="Old note",
        thesis_reference_price_usd=800.0,
    )
    monkeypatch.setattr(main, "portfolio_store", portfolio)

    for idx in range(10):
        payload = main.save_portfolio_watchlist_thesis_revision(
            "nvda",
            {
                "data_source": "OPENBB",
                "thesis": f"{new_long} #{idx}",
                "note": "Revised note",
                "thesis_reference_price_usd": 898.0 + idx,
                "review_window_days": 45,
                "rationale": "Prior thesis changed after updated evidence and portfolio-fit review.",
                "evidence_gaps": ["tax lot impact not reviewed", "provider freshness should be refreshed"],
                "warnings": ["Review-only; not a buy recommendation."],
                "recommendation_id": "rec-thesis",
                "conversation_id": "conversation-thesis",
            },
        )

    history = payload["item"]["thesis_revision_history"]
    assert len(history) == main.THESIS_REVISION_HISTORY_LIMIT
    latest = history[0]
    assert latest["target_type"] == "watchlist"
    assert latest["symbol"] == "NVDA"
    assert latest["source"] == "copilot_review"
    assert latest["recommendation_id"] == "rec-thesis"
    assert latest["conversation_id"] == "conversation-thesis"
    assert latest["reference_price_usd"] == pytest.approx(907.0)
    assert latest["previous_thesis_chars"] > len(latest["previous_thesis_excerpt"])
    assert latest["revised_thesis_chars"] > len(latest["revised_thesis_excerpt"])
    assert len(latest["previous_thesis_hash"]) == 12
    assert len(latest["revised_thesis_hash"]) == 12
    assert "tax lot impact not reviewed" in latest["evidence_gaps"]
    assert "Review-only" in latest["warnings"][0]


def test_save_watchlist_thesis_revision_links_related_recommendation_for_calibration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    portfolio = PortfolioStore(tmp_path / "portfolio")
    portfolio.upsert_watchlist_item(
        symbol="NVDA",
        data_source="OPENBB",
        thesis="Old thesis",
        thesis_reference_price_usd=800.0,
    )
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Review NVDA thesis",
        detail="Copilot should revise the thesis if the review changes.",
        recommendation_type="workflow_action",
        source="copilot:investment_fit",
        status="applied",
        action_payload={
            "evidence": {"symbol": "NVDA", "fit_status": "review_needed"},
            "quality": {
                "actionability": "review_only",
                "calibration": {"domain": "investment_research", "track_process_outcome": True},
            },
            "decision_closure": {
                "decision_status": "accepted",
                "expected_outcome": {"expected_next_safe_action": "review_thesis"},
            },
        },
    )
    monkeypatch.setattr(main, "portfolio_store", portfolio)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = main.save_portfolio_watchlist_thesis_revision(
        "nvda",
        {
            "data_source": "OPENBB",
            "thesis": "Revised thesis",
            "reference_price_usd": 898.0,
            "review_window_days": 45,
            "rationale": "The fit discussion changed the thesis framing.",
            "evidence_gaps": ["tax lot impact not reviewed"],
            "recommendation_id": recommendation["id"],
            "conversation_id": "conversation-thesis",
        },
    )

    linked = inbox.get(recommendation["id"])["action_payload"]["thesis_revision"]
    assert linked["event_id"] == payload["item"]["thesis_revision_history"][0]["event_id"]
    assert linked["target_type"] == "watchlist"
    assert linked["symbol"] == "NVDA"
    assert linked["revised_thesis_hash"] == payload["item"]["thesis_revision_history"][0]["revised_thesis_hash"]
    assert linked["conversation_id"] == "conversation-thesis"
    assert linked["evidence_gaps"] == ["tax lot impact not reviewed"]


def test_save_dossier_thesis_revision_updates_artifact_content_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Dossier Plan")
    artifact = workspace.write_artifact(
        plan_id=plan["id"],
        title="Research Dossier - MSFT vs VTI",
        kind="research_dossier",
        markdown="# Research Dossier: MSFT vs VTI\n\n## Thesis\n\nOld dossier thesis.\n\n## Evidence Packets\n\nKeep packet table.\n",
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = main.save_plan_artifact_thesis_revision(
        plan["id"],
        artifact["id"],
        {
            "thesis": "Revised dossier thesis.",
            "rationale": "Prior thesis expired.",
            "reference_price_usd": 410.0,
            "review_window_days": 45,
        },
    )

    updated = workspace.read_artifact(plan["id"], artifact["id"])["content"]
    assert "## Thesis\n\nRevised dossier thesis." in updated
    assert main._extract_markdown_section(updated, "Thesis") == "Revised dossier thesis."
    assert "## Evidence Packets\n\nKeep packet table." in updated
    assert "## Thesis Revision Notes" in updated
    assert "Prior thesis expired." in updated
    assert "## Thesis Review Metadata" in updated
    assert "- Reference price USD: `410.0`" in updated
    assert payload["artifact"]["id"] == artifact["id"]
    assert payload["thesis_review"]["status"] == "current"
    assert payload["thesis_review"]["target"] == "dossier"
    assert payload["thesis_review"]["artifact_id"] == artifact["id"]


def test_save_dossier_thesis_revision_records_compact_history_section(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Dossier Plan")
    artifact = workspace.write_artifact(
        plan_id=plan["id"],
        title="Research Dossier - MSFT vs VTI",
        kind="research_dossier",
        markdown=(
            "# Research Dossier: MSFT vs VTI\n\n"
            "## Thesis\n\n"
            f"Old dossier thesis {'with extensive supporting details ' * 40}\n\n"
            "## Evidence Packets\n\n"
            "Keep packet table.\n"
        ),
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = None
    for idx in range(10):
        payload = main.save_plan_artifact_thesis_revision(
            plan["id"],
            artifact["id"],
            {
                "thesis": f"Revised dossier thesis {'with refreshed fit context ' * 40} #{idx}",
                "rationale": "Prior thesis expired and new evidence changed the review framing.",
                "reference_price_usd": 410.0 + idx,
                "review_window_days": 45,
                "evidence_gaps": ["provider freshness should be refreshed"],
                "warnings": ["Review-only; not a buy recommendation."],
                "recommendation_id": "rec-dossier-thesis",
                "conversation_id": "conversation-dossier-thesis",
            },
        )

    assert payload is not None
    updated = workspace.read_artifact(plan["id"], artifact["id"])["content"]
    assert "## Thesis Revision History" in updated
    history_lines = [line for line in updated.splitlines() if line.startswith("- Reviewed `")]
    assert len(history_lines) == main.THESIS_REVISION_HISTORY_LIMIT
    assert "rec-dossier-thesis" in history_lines[0]
    assert "conversation-dossier-thesis" in history_lines[0]
    assert "prior_hash=`" in history_lines[0]
    assert "revised_hash=`" in history_lines[0]
    assert "provider freshness should be refreshed" in history_lines[0]
    assert "Review-only; not a buy recommendation." in history_lines[0]
    assert "## Evidence Packets\n\nKeep packet table." in updated
    assert payload["thesis_revision_history"][0]["target_type"] == "dossier"
    assert len(payload["thesis_revision_history"]) == main.THESIS_REVISION_HISTORY_LIMIT
    artifact_response = main.read_plan_artifact(plan["id"], artifact["id"])
    assert artifact_response.thesis_revision_history[0]["target_type"] == "dossier"
    assert artifact_response.thesis_revision_history[0]["revised_thesis_excerpt"].startswith("Revised dossier thesis")
    assert artifact_response.thesis_revision_history[0]["evidence_gaps"] == ["provider freshness should be refreshed"]


def test_tool_draft_investment_research_recommendation_creates_review_only_row(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    workspace = PlanWorkspace(tmp_path / "plans")
    plan = workspace.create_plan(title="Investment Fit Plan")
    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = asyncio.run(
        main.tool_draft_investment_research_recommendation(
            {
                "symbol": "nvda",
                "title": "Review NVDA fit before changing exposure",
                "detail": "NVDA conflicts with current concentration policy. Review fit context before making any portfolio decision.",
                "priority": "high",
                "fit_status": "does_not_fit",
                "fit_score": 25,
                "fit_reasons": ["Active plan horizon is long enough to evaluate growth exposure."],
                "fit_risks": ["NVDA would worsen concentration risk."],
                "blocking_gaps": ["concentration"],
                "research_evidence_packet_id": "research-evidence:yfinance:NVDA:6mo:1d",
                "provider": "yfinance",
                "freshness_status": "fresh",
                "confidence": "high",
                "coverage_score": 100,
                "suggested_action_kind": "review_portfolio_fit",
                "source_recommendation_id": "rec-invest",
            }
        )
    )

    recommendation = payload["recommendation"]
    action_payload = recommendation["action_payload"]
    evidence = action_payload["evidence"]
    quality = action_payload["quality"]

    assert payload["draft_kind"] == "investment_research_recommendation"
    assert payload["requires_review"] is True
    assert recommendation["source"] == "copilot:investment_fit"
    assert recommendation["status"] == "proposed"
    assert recommendation["recommendation_type"] == "workflow_action"
    assert recommendation["plan_id"] == plan["id"]
    assert action_payload["suggested_action"]["kind"] == "review_portfolio_fit"
    assert action_payload["suggested_action"]["symbol"] == "NVDA"
    assert evidence["symbol"] == "NVDA"
    assert evidence["research_symbols"] == ["NVDA"]
    assert evidence["research_evidence_packet_id"] == "research-evidence:yfinance:NVDA:6mo:1d"
    assert evidence["fit_status"] == "does_not_fit"
    assert quality["actionability"] == "review_only"
    assert quality["decision_grade"] is True
    assert quality["freshness_status"] == "fresh"
    assert quality["calibration"]["domain"] == "investment_research"
    assert quality["calibration"]["track_process_outcome"] is True

    stored = inbox.list(limit=None)
    assert len(stored) == 1
    assert stored[0]["id"] == recommendation["id"]


def test_tool_draft_investment_research_recommendation_rejects_direct_trade_actions() -> None:
    with pytest.raises(ValueError, match="review, compare, simulate, refresh, discuss, or context"):
        asyncio.run(
            main.tool_draft_investment_research_recommendation(
                {
                    "symbol": "NVDA",
                    "suggested_action_kind": "buy",
                }
            )
        )


def test_tool_draft_financial_profile_update_validates_without_saving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProfileStore:
        def __init__(self) -> None:
            self.saved_payload = None
            self.payload = {
                "schema_version": 2,
                "income_items": [],
                "expense_items": [],
                "debt_items": [],
                "goal_items": [],
                "physical_assets": [],
                "tax_profile": {
                    "filing_status": None,
                    "marginal_tax_rate": None,
                    "effective_tax_rate": None,
                    "state_tax_rate": None,
                    "state": None,
                },
                "flags": {"no_debt": False, "no_goals": False},
                "notes": "",
                "updated_at": "2026-04-26T12:00:00+00:00",
            }

        def load(self) -> dict[str, object]:
            return dict(self.payload)

        def get(self) -> dict[str, object]:
            return dict(self.payload)

        def save(self, payload: dict[str, object]) -> dict[str, object]:
            self.saved_payload = payload
            return dict(payload)

    store = FakeProfileStore()
    monkeypatch.setattr(main, "financial_profile_store", store)

    payload = asyncio.run(
        main.tool_draft_financial_profile_update(
            {
                "income_items": [
                    {
                        "id": "income-salary",
                        "label": "Salary",
                        "monthly_amount_usd": 11000,
                        "source_type": "salary",
                    }
                ],
                "expense_items": [
                    {
                        "id": "expense-rent",
                        "label": "Rent",
                        "monthly_amount_usd": 2600,
                        "category": "housing",
                    }
                ],
                "flags": {"no_debt": True},
            }
        )
    )

    assert store.saved_payload is None
    assert payload["draft_kind"] == "financial_profile_update"
    assert payload["section_counts"] == {"income_items": 1, "expense_items": 1, "flags": 1}
    assert payload["proposed_profile"]["income_items"][0]["label"] == "Salary"
    assert payload["proposed_profile"]["expense_items"][0]["label"] == "Rent"
    assert payload["proposed_profile"]["flags"]["no_debt"] is True


def test_tool_update_financial_profile_records_copilot_audit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProfileStore:
        def __init__(self) -> None:
            self.payload = {
                "schema_version": 2,
                "income_items": [],
                "expense_items": [],
                "debt_items": [],
                "goal_items": [],
                "physical_assets": [],
                "tax_profile": {
                    "filing_status": None,
                    "marginal_tax_rate": None,
                    "effective_tax_rate": None,
                    "state_tax_rate": None,
                    "state": None,
                },
                "investment_policy": {},
                "flags": {"no_debt": False, "no_goals": False},
                "notes": "",
                "updated_at": "2026-04-26T12:00:00+00:00",
            }

        def load(self) -> dict[str, object]:
            return dict(self.payload)

        def get(self) -> dict[str, object]:
            return dict(self.payload)

        def save(self, payload: dict[str, object]) -> dict[str, object]:
            self.payload = dict(payload)
            self.payload["schema_version"] = 2
            self.payload["updated_at"] = "2026-04-30T12:00:00+00:00"
            return dict(self.payload)

    class FakeActivityStore:
        def __init__(self) -> None:
            self.events = []

        def record(self, **kwargs):
            self.events.append(kwargs)
            return kwargs

    store = FakeProfileStore()
    activity = FakeActivityStore()
    monkeypatch.setattr(main, "financial_profile_store", store)
    monkeypatch.setattr(main, "_git_activity_store", lambda: activity)

    asyncio.run(
        main.tool_update_financial_profile(
            {
                "investment_policy": {
                    "max_single_symbol_exposure_pct": 10,
                }
            }
        )
    )

    assert activity.events
    event = activity.events[-1]
    assert event["event_type"] == "copilot_profile_update"
    assert event["title"] == "Copilot profile update applied"
    assert event["metadata"]["sections"] == ["investment_policy"]
    assert event["metadata"]["source"] == "copilot_tool"


def test_update_financial_profile_records_profile_audit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProfileStore:
        def save(self, payload: dict[str, object]) -> dict[str, object]:
            saved = dict(payload)
            saved["schema_version"] = 2
            saved["updated_at"] = "2026-04-30T12:00:00+00:00"
            return saved

    class FakeActivityStore:
        def __init__(self) -> None:
            self.events = []

        def record(self, **kwargs):
            self.events.append(kwargs)
            return kwargs

    activity = FakeActivityStore()
    monkeypatch.setattr(main, "financial_profile_store", FakeProfileStore())
    monkeypatch.setattr(main, "_git_activity_store", lambda: activity)
    monkeypatch.setattr(main, "_queue_autogit_event", lambda event_type: None)

    response = main.update_financial_profile(
        main.FinancialProfileRequest(
            investment_policy={"max_single_symbol_exposure_pct": 12},
            notes="Updated policy",
        ),
        source="profile_editor",
    )

    assert response.investment_policy.max_single_symbol_exposure_pct == 12
    assert activity.events
    event = activity.events[-1]
    assert event["event_type"] == "profile_update"
    assert event["title"] == "Financial profile updated"
    assert event["metadata"]["sections"] == ["investment_policy", "notes"]
    assert event["metadata"]["source"] == "profile_editor"


def test_profile_readiness_marks_stale_material_metadata_as_attention() -> None:
    readiness = main._build_profile_readiness_summary(
        income_items=[{"id": "income-1"}],
        expense_items=[{"id": "expense-1"}],
        debt_items=[],
        goal_items=[{"id": "goal-1"}],
        physical_assets=[],
        flags={"no_debt": True, "no_goals": False},
        tax_profile={"filing_status": "single", "marginal_tax_rate": 0.28},
        investment_policy={"max_single_symbol_exposure_pct": 10.0},
        profile_metadata={
            "tax_profile.marginal_tax_rate": {
                "status": "stale",
                "source": "profile_editor",
                "confidence": "high",
                "last_confirmed_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "stale_after_days": 180,
                "confirmed_by_user": True,
            },
            "investment_policy.max_single_symbol_exposure_pct": {
                "status": "stale",
                "source": "profile_editor",
                "confidence": "high",
                "last_confirmed_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
                "stale_after_days": 365,
                "confirmed_by_user": True,
            },
        },
    )

    tax_section = next(section for section in readiness.sections if section.key == "tax_profile")
    policy_section = next(section for section in readiness.sections if section.key == "investment_policy")

    assert readiness.status == "attention"
    assert tax_section.status == "attention"
    assert tax_section.blocking_recommendations is True
    assert policy_section.status == "attention"
    assert policy_section.blocking_recommendations is True
    assert "investment_fit" in readiness.blocking_recommendation_sources


def test_tool_apply_recommendation_records_copilot_audit_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResult:
        recommendation = SimpleNamespace(id="rec-123", title="Review NVDA fit")
        plan = SimpleNamespace(id="plan-active")
        decision_packet_artifact = SimpleNamespace(file_name="plans/decision-packet.md")
        decision_closure_artifact = None
        message = "Recommendation applied."

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            return {"message": self.message, "mode": mode}

    class FakeActivityStore:
        def __init__(self) -> None:
            self.events = []

        def record(self, **kwargs):
            self.events.append(kwargs)
            return kwargs

    async def fake_apply(recommendation_id, request):
        assert recommendation_id == "rec-123"
        assert request.decision_status == "accepted"
        return FakeResult()

    activity = FakeActivityStore()
    monkeypatch.setattr(main, "apply_recommendation_with_decision_packet", fake_apply)
    monkeypatch.setattr(main, "_git_activity_store", lambda: activity)

    result = asyncio.run(
        main.tool_apply_recommendation(
            {
                "recommendation_id": "rec-123",
                "decision_status": "accepted",
            }
        )
    )

    assert result["message"] == "Recommendation applied."
    assert activity.events
    event = activity.events[-1]
    assert event["event_type"] == "copilot_recommendation_apply"
    assert event["title"] == "Copilot applied recommendation"
    assert event["metadata"]["recommendation_id"] == "rec-123"
    assert event["metadata"]["plan_id"] == "plan-active"
    assert "recommendations/inbox.json" in event["paths"]
    assert "plans/decision-packet.md" in event["paths"]


def test_tool_draft_financial_profile_update_generates_missing_item_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProfileStore:
        def get(self) -> dict[str, object]:
            return {
                "schema_version": 2,
                "income_items": [],
                "expense_items": [],
                "debt_items": [],
                "goal_items": [],
                "physical_assets": [],
                "tax_profile": {
                    "filing_status": None,
                    "marginal_tax_rate": None,
                    "effective_tax_rate": None,
                    "state_tax_rate": None,
                    "state": None,
                },
                "flags": {"no_debt": False, "no_goals": False},
                "notes": "",
                "updated_at": "2026-04-26T12:00:00+00:00",
            }

    monkeypatch.setattr(main, "financial_profile_store", FakeProfileStore())

    payload = asyncio.run(
        main.tool_draft_financial_profile_update(
            {
                "income_items": [
                    {
                        "label": "Salary",
                        "monthly_amount_usd": 11000,
                        "source_type": "salary",
                    }
                ],
                "goal_items": [
                    {
                        "label": "Emergency fund",
                        "target_amount_usd": 30000,
                    }
                ],
            }
        )
    )

    assert payload["patch_payload"]["income_items"][0]["id"].startswith("income-")
    assert payload["patch_payload"]["goal_items"][0]["id"].startswith("goal-")
    assert payload["proposed_profile"]["income_items"][0]["id"].startswith("income-")
    assert payload["proposed_profile"]["goal_items"][0]["id"].startswith("goal-")


def test_tool_draft_financial_profile_update_supports_investment_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProfileStore:
        def get(self) -> dict[str, object]:
            return {
                "schema_version": 2,
                "income_items": [],
                "expense_items": [],
                "debt_items": [],
                "goal_items": [],
                "physical_assets": [],
                "tax_profile": {},
                "investment_policy": {},
                "flags": {"no_debt": False, "no_goals": False},
                "notes": "",
                "updated_at": "2026-04-26T12:00:00+00:00",
            }

    monkeypatch.setattr(main, "financial_profile_store", FakeProfileStore())

    payload = asyncio.run(
        main.tool_draft_financial_profile_update(
            {
                "investment_policy": {
                    "max_single_symbol_exposure_pct": 10.0,
                    "minimum_research_confidence": "medium",
                    "tax_sensitivity": "high",
                },
            }
        )
    )

    assert payload["section_counts"] == {"investment_policy": 3}
    assert payload["patch_payload"]["investment_policy"]["max_single_symbol_exposure_pct"] == 10.0
    assert payload["proposed_profile"]["investment_policy"]["minimum_research_confidence"] == "medium"
    metadata = payload["proposed_profile"]["profile_metadata"]
    single_symbol_metadata = metadata["investment_policy.max_single_symbol_exposure_pct"]
    assert single_symbol_metadata["status"] == "copilot_drafted"
    assert single_symbol_metadata["source"] == "copilot_profile_draft"
    assert single_symbol_metadata["confirmed_by_user"] is False


def test_pin_watchlist_research_tool_contract() -> None:
    tool = main.copilot.tools["pin_watchlist_research_to_plan"]
    properties = tool.parameters.get("properties", {})
    assert "plan_id" in properties
    assert "branch_template_id" in properties
    assert "symbols" in properties
    assert "max_symbols" in properties


def test_research_compare_tool_contract() -> None:
    tool = main.copilot.tools["research_compare"]
    properties = tool.parameters.get("properties", {})
    assert "symbols" in properties
    assert "period" in properties
    assert "interval" in properties
    assert "baseline_symbol" in properties


def test_research_dossier_tool_contract() -> None:
    tool = main.copilot.tools["research_dossier"]
    properties = tool.parameters.get("properties", {})
    assert "symbols" in properties
    assert "period" in properties
    assert "interval" in properties
    assert "baseline_symbol" in properties
    assert "thesis" in properties
    assert "risks" in properties
    assert "catalysts" in properties
    assert "plan_id" in properties
    assert "save_to_plan" in properties
    assert "include_portfolio_fit" in properties


def test_research_dossier_lookup_tool_contract() -> None:
    tool = main.copilot.tools["research_dossier_lookup"]
    properties = tool.parameters.get("properties", {})
    assert "plan_id" in properties
    assert "limit" in properties
    assert "include_content" in properties


def test_research_watchlist_rank_tool_contract() -> None:
    tool = main.copilot.tools["research_watchlist_rank"]
    properties = tool.parameters.get("properties", {})
    assert "period" in properties
    assert "interval" in properties
    assert "limit" in properties


def test_tool_pin_watchlist_research_to_plan_calls_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_pin(
        *,
        plan_id: str,
        request: main.PlanResearchBridgeRequest,
    ) -> main.PlanResearchBridgeResponse:
        assert plan_id == "plan-abc"
        assert request.symbols == ["NVDA", "VTI"]
        return main.PlanResearchBridgeResponse(
            plan_id=plan_id,
            template_id="research_watchlist_bridge",
            template_name="Research Watchlist Thesis",
            pinned_symbols=["NVDA", "VTI"],
            pinned_items=[],
            branch_templates=main.PlanScenarioBranchTemplatesResponse(
                schema_version=2,
                default_template_id="research_watchlist_bridge",
                templates=[],
            ),
        )

    monkeypatch.setattr(main, "pin_watchlist_research_bridge", fake_pin)
    payload = asyncio.run(
        main.tool_pin_watchlist_research_to_plan(
            {
                "plan_id": "plan-abc",
                "symbols": ["NVDA", "VTI"],
                "max_symbols": 4,
            }
        )
    )

    assert payload["plan_id"] == "plan-abc"
    assert payload["template_id"] == "research_watchlist_bridge"
    assert payload["pinned_symbols"] == ["NVDA", "VTI"]


def test_tool_research_compare_calls_research_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "provider": "test",
                "period": "6mo",
                "interval": "1d",
                "symbols": ["MSFT", "AAPL"],
                "summary": {"best_period_return_symbol": "MSFT"},
                "items": [
                    {"symbol": "MSFT", "rank": 1},
                    {"symbol": "AAPL", "rank": 2},
                ],
                "warnings": [],
            }

    class FakeResearchService:
        def compare(self, *, symbols, period: str, interval: str, baseline_symbol: str | None):
            assert symbols == ["MSFT", "AAPL"]
            assert period == "6mo"
            assert interval == "1d"
            assert baseline_symbol == "MSFT"
            return FakeResponse()

    monkeypatch.setattr(main, "research_service", FakeResearchService())

    payload = asyncio.run(
        main.tool_research_compare(
            {
                "symbols": ["msft", "AAPL"],
                "period": "6mo",
                "interval": "1d",
                "baseline_symbol": "MSFT",
            }
        )
    )

    assert payload["provider"] == "test"
    assert payload["summary"]["best_period_return_symbol"] == "MSFT"
    assert [item["symbol"] for item in payload["items"]] == ["MSFT", "AAPL"]


def test_tool_research_dossier_calls_research_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        warnings: list[str] = []
        artifact: dict[str, object] | None = None
        symbols: list[str] = ["MSFT", "AAPL"]
        dossier_markdown: str = "# Dossier"

        def model_dump(self, mode: str = "json") -> dict[str, object]:
            del mode
            return {
                "provider": "test",
                "period": "6mo",
                "interval": "1d",
                "generated_at": "2026-04-14T00:00:00+00:00",
                "symbols": ["MSFT", "AAPL"],
                "baseline_symbol": "MSFT",
                "headline": "MSFT leads.",
                "thesis": "Prefer quality.",
                "risks": ["valuation"],
                "catalysts": ["earnings"],
                "key_takeaways": ["MSFT leads period returns."],
                "freshness": {"status": "fresh", "available_symbols": 2, "compared_symbols": 2},
                "compare": {
                    "provider": "test",
                    "period": "6mo",
                    "interval": "1d",
                    "generated_at": "2026-04-14T00:00:00+00:00",
                    "symbols": ["MSFT", "AAPL"],
                    "summary": {"best_period_return_symbol": "MSFT"},
                    "items": [
                        {"symbol": "MSFT", "rank": 1},
                        {"symbol": "AAPL", "rank": 2},
                    ],
                    "warnings": [],
                },
                "portfolio_fit": {"existing_symbols": ["MSFT"], "new_symbols": ["AAPL"]},
                "dossier_markdown": "# Dossier",
                "artifact": None,
                "warnings": [],
            }

    class FakeResearchService:
        def dossier(
            self,
            *,
            symbols,
            period: str,
            interval: str,
            baseline_symbol: str | None,
            thesis: str,
            risks,
            catalysts,
            include_portfolio_fit: bool,
            portfolio_weights_pct,
        ):
            assert symbols == ["MSFT", "AAPL"]
            assert period == "6mo"
            assert interval == "1d"
            assert baseline_symbol == "MSFT"
            assert thesis == "Prefer quality."
            assert risks == ["valuation risk"]
            assert catalysts == ["earnings expansion"]
            assert include_portfolio_fit is False
            assert portfolio_weights_pct == {}
            return FakeResponse()

    monkeypatch.setattr(main, "research_service", FakeResearchService())

    payload = asyncio.run(
        main.tool_research_dossier(
            {
                "symbols": ["msft", "AAPL"],
                "period": "6mo",
                "interval": "1d",
                "baseline_symbol": "MSFT",
                "thesis": "Prefer quality.",
                "risks": ["valuation risk"],
                "catalysts": ["earnings expansion"],
                "save_to_plan": False,
                "include_portfolio_fit": False,
            }
        )
    )

    assert payload["provider"] == "test"
    assert payload["headline"] == "MSFT leads."
    assert payload["freshness"]["status"] == "fresh"
    assert [item["symbol"] for item in payload["compare"]["items"]] == ["MSFT", "AAPL"]


def test_tool_research_dossier_lookup_calls_payload_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build(
        *,
        plan_id: str | None,
        limit: int,
        include_content: bool,
    ) -> dict[str, object]:
        assert plan_id == "plan-abc"
        assert limit == 4
        assert include_content is True
        return {
            "plan_id": plan_id,
            "count": 1,
            "items": [
                {
                    "artifact_id": "artifact-1",
                    "file_name": "artifact-1.md",
                    "title": "Research Dossier: MSFT, AAPL",
                    "created_at": "2026-04-14T00:00:00+00:00",
                    "plan_id": plan_id,
                    "symbols": ["MSFT", "AAPL"],
                    "content_preview": "# Research Dossier: MSFT, AAPL",
                }
            ],
            "warnings": [],
            "updated_at": "2026-04-14T00:00:00+00:00",
        }

    monkeypatch.setattr(main, "build_research_dossier_lookup_payload", fake_build)
    payload = asyncio.run(
        main.tool_research_dossier_lookup(
            {
                "plan_id": "plan-abc",
                "limit": 4,
                "include_content": True,
            }
        )
    )

    assert payload["count"] == 1
    assert payload["items"][0]["artifact_id"] == "artifact-1"
    assert payload["items"][0]["symbols"] == ["MSFT", "AAPL"]


def test_tool_research_watchlist_rank_calls_payload_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build(
        *,
        period: str,
        interval: str,
        sort: str,
        limit: int,
    ) -> dict[str, object]:
        assert period == "6mo"
        assert interval == "1d"
        assert sort == "ranked"
        assert limit == 75
        return {
            "period": period,
            "interval": interval,
            "count": 1,
            "score_model": "watchlist_v1",
            "sorted_by": sort,
            "items": [{"symbol": "NVDA", "watchlist_rank": 1, "watchlist_score_total": 78.2}],
            "warnings": [],
            "updated_at": "2026-04-14T00:00:00+00:00",
        }

    monkeypatch.setattr(main, "build_portfolio_watchlist_payload", fake_build)
    payload = asyncio.run(
        main.tool_research_watchlist_rank(
            {
                "period": "6mo",
                "interval": "1d",
                "limit": 75,
            }
        )
    )

    assert payload["sorted_by"] == "ranked"
    assert payload["score_model"] == "watchlist_v1"
    assert payload["items"][0]["symbol"] == "NVDA"


def test_tool_preview_recommendation_calls_preview_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_preview(
        recommendation_id: str,
        request: main.RecommendationPreviewRequest,
    ) -> main.RecommendationPreviewResponse:
        assert recommendation_id == "rec-123"
        assert request.plan_id == "plan-abc"
        assert request.plan_settings_updates == {"annual_contribution_usd": 22000}
        assert request.capture_scenario_diff is True
        assert request.decision_status == "accepted"
        return main.RecommendationPreviewResponse(
            recommendation=main.RecommendationItem(
                id="rec-123",
                created_at="2026-04-14T00:00:00+00:00",
                updated_at="2026-04-14T00:00:00+00:00",
                title="Increase contributions",
                detail="Raise annual contributions.",
                priority="high",
                status="proposed",
                recommendation_type="plan_settings_update",
                source="workflow:plan_review",
                plan_id="plan-abc",
                action_payload={"plan_settings_updates": {"annual_contribution_usd": 22000}},
            ),
            preview={
                "status": "captured",
                "scenario_diff_preview": {"status": "captured"},
            },
            suggested_research_symbols=["VTI"],
            message="Pre-apply preview captured with scenario diff deltas.",
        )

    monkeypatch.setattr(main, "preview_recommendation", fake_preview)
    payload = asyncio.run(
        main.tool_preview_recommendation(
            {
                "recommendation_id": "rec-123",
                "plan_id": "plan-abc",
                "plan_settings_updates": {"annual_contribution_usd": 22000},
                "capture_scenario_diff": True,
                "decision_status": "accepted",
            }
        )
    )

    assert payload["recommendation"]["id"] == "rec-123"
    assert payload["preview"]["status"] == "captured"
    assert payload["suggested_research_symbols"] == ["VTI"]


def test_tool_update_recommendation_outcome_calls_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_update(
        recommendation_id: str,
        request: main.RecommendationOutcomeUpdateRequest,
    ) -> main.RecommendationActionResponse:
        assert recommendation_id == "rec-123"
        assert request.plan_id == "plan-abc"
        assert request.realized_delta_future_value_usd == 1200.0
        assert request.realized_delta_real_value_usd == 900.0
        assert request.observation_window_days == 30
        assert request.measurement_source == "manual-review"
        assert request.note == "Outcome stabilized"
        return main.RecommendationActionResponse(
            recommendation=main.RecommendationItem(
                id="rec-123",
                created_at="2026-04-14T00:00:00+00:00",
                updated_at="2026-04-14T00:00:00+00:00",
                title="Increase contributions",
                detail="Raise annual contributions.",
                priority="high",
                status="applied",
                recommendation_type="plan_settings_update",
                source="workflow:plan_review",
                plan_id="plan-abc",
                action_payload={
                    "decision_closure": {
                        "expected_vs_realized": {"status": "measured"},
                    }
                },
            ),
            message="Recommendation outcome recorded.",
            decision_closure={"expected_vs_realized": {"status": "measured"}},
        )

    monkeypatch.setattr(main, "update_recommendation_outcome", fake_update)
    payload = asyncio.run(
        main.tool_update_recommendation_outcome(
            {
                "recommendation_id": "rec-123",
                "plan_id": "plan-abc",
                "realized_delta_future_value_usd": 1200.0,
                "realized_delta_real_value_usd": 900.0,
                "observation_window_days": 30,
                "measurement_source": "manual-review",
                "note": "Outcome stabilized",
            }
        )
    )

    assert payload["recommendation"]["id"] == "rec-123"
    assert payload["decision_closure"]["expected_vs_realized"]["status"] == "measured"


def test_tool_get_recommendation_closure_analytics_calls_payload_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build(
        *,
        limit: int,
        statuses,
        include_pending_realized: bool,
    ) -> dict[str, object]:
        assert limit == 120
        assert statuses == ["applied", "rejected"]
        assert include_pending_realized is False
        return {
            "generated_at": "2026-04-14T00:00:00+00:00",
            "count": 2,
            "statuses": ["applied", "rejected"],
            "include_pending_realized": False,
            "summary": {"measured_count": 1},
            "by_status": [{"key": "applied", "count": 1}],
            "by_type": [{"key": "plan_settings_update", "count": 1}],
            "by_source": [{"key": "copilot", "count": 1}],
            "items": [],
        }

    monkeypatch.setattr(main, "build_recommendation_closure_analytics_payload", fake_build)
    payload = asyncio.run(
        main.tool_get_recommendation_closure_analytics(
            {
                "limit": 120,
                "statuses": ["applied", "rejected"],
                "include_pending_realized": False,
            }
        )
    )

    assert payload["count"] == 2
    assert payload["summary"]["measured_count"] == 1


def test_tool_get_recommendation_closure_analytics_passes_plan_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_build(
        *,
        limit: int,
        statuses,
        include_pending_realized: bool,
        plan_id: str | None = None,
    ) -> dict[str, object]:
        assert limit == 50
        assert statuses == ["applied", "rejected"]
        assert include_pending_realized is True
        assert plan_id == "plan-123"
        return {
            "generated_at": "2026-04-14T00:00:00+00:00",
            "count": 1,
            "plan_id": "plan-123",
            "statuses": ["applied", "rejected"],
            "include_pending_realized": True,
            "summary": {"measured_count": 1},
            "by_status": [{"key": "applied", "count": 1}],
            "by_type": [{"key": "plan_settings_update", "count": 1}],
            "by_source": [{"key": "copilot", "count": 1}],
            "items": [],
        }

    monkeypatch.setattr(main, "build_recommendation_closure_analytics_payload", fake_build)
    payload = asyncio.run(
        main.tool_get_recommendation_closure_analytics(
            {
                "limit": 50,
                "plan_id": "plan-123",
                "statuses": ["applied", "rejected"],
                "include_pending_realized": True,
            }
        )
    )

    assert payload["count"] == 1
    assert payload["plan_id"] == "plan-123"


def test_tool_create_plan_recommendation_closure_summary_calls_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_create(
        *,
        plan_id: str,
        request: main.PlanRecommendationClosureSummaryRequest,
    ) -> main.PlanRecommendationClosureSummaryResponse:
        assert plan_id == "plan-xyz"
        assert request.limit == 120
        assert request.statuses == ["applied", "rejected"]
        assert request.include_pending_realized is False
        assert request.write_artifact is False
        return main.PlanRecommendationClosureSummaryResponse(
            plan_id=plan_id,
            analytics=main.RecommendationClosureAnalyticsResponse(
                generated_at="2026-04-14T00:00:00+00:00",
                count=2,
                plan_id=plan_id,
                statuses=["applied", "rejected"],
                include_pending_realized=False,
                summary={"measured_count": 1},
            ),
            artifact=None,
            decision_summary="Generated recommendation closure analytics summary (2 closed, 1 measured).",
        )

    monkeypatch.setattr(main, "resolve_plan_id_or_active", lambda value: "plan-xyz")
    monkeypatch.setattr(main, "create_plan_recommendation_closure_summary", fake_create)

    payload = asyncio.run(
        main.tool_create_plan_recommendation_closure_summary(
            {
                "plan_id": "plan-xyz",
                "limit": 120,
                "statuses": ["applied", "rejected"],
                "include_pending_realized": False,
                "write_artifact": False,
            }
        )
    )

    assert payload["plan_id"] == "plan-xyz"
    assert payload["analytics"]["count"] == 2


def test_tool_add_timeline_event_appends_event_and_preserves_retirement_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Timeline Tool Plan")
    workspace.update_plan_timeline(
        plan_id=detail["id"],
        timeline_payload={
            "events": [
                {
                    "id": "event-existing",
                    "date": "2028-01-01",
                    "label": "Existing Event",
                    "event_type": "milestone",
                    "impact_type": "portfolio",
                    "amount_usd": 0,
                    "recurring_frequency": "one_time",
                }
            ],
            "retirement": {
                "target_retirement_age": 60,
                "withdrawal_strategy": "four_percent_rule",
            },
        },
        log_decision=False,
    )
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = asyncio.run(
        main.tool_add_timeline_event(
            {
                "plan_id": detail["id"],
                "date": "2030-03-15",
                "label": "Inheritance",
                "event_type": "windfall",
                "amount_usd": 50_000,
                "recurring_frequency": "one_time",
                "notes": "Family transfer",
            }
        )
    )

    assert payload["plan_id"] == detail["id"]
    assert payload["event"]["label"] == "Inheritance"
    assert payload["event"]["impact_type"] == "income"
    assert payload["event"]["notes"] == "Family transfer"

    timeline = workspace.get_plan_timeline(detail["id"])
    assert len(timeline["events"]) == 2
    assert any(item["label"] == "Existing Event" for item in timeline["events"])
    assert any(item["label"] == "Inheritance" for item in timeline["events"])
    assert timeline["retirement"]["target_retirement_age"] == 60
    assert timeline["retirement"]["withdrawal_strategy"] == "four_percent_rule"


def test_tool_add_timeline_event_uses_active_plan_when_plan_id_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path)
    detail = workspace.create_plan(title="Active Plan")
    monkeypatch.setattr(main, "plan_workspace", workspace)

    payload = asyncio.run(
        main.tool_add_timeline_event(
            {
                "date": "2031-01-01",
                "label": "Raise",
                "event_type": "job_change",
                "amount_usd": 2_000,
                "recurring_frequency": "monthly",
            }
        )
    )

    assert payload["plan_id"] == detail["id"]
    assert payload["event"]["label"] == "Raise"
    assert payload["event"]["impact_type"] == "income"
    assert payload["event"]["recurring_frequency"] == "monthly"

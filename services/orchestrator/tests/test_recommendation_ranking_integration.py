from pathlib import Path

import pytest

import buildwealth_orchestrator.main as main
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.schemas import TodayActivePlanSummary


def test_recommendation_list_defaults_to_ranked_sort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    high = inbox.create(
        title="Increase annual contributions",
        detail="Boost annual contributions by $5,000.",
        priority="high",
        recommendation_type="plan_settings_update",
        source="workflow:plan_review",
        action_payload={"plan_settings_updates": {"annual_contribution_usd": 25000.0}},
    )
    low = inbox.create(
        title="Review checklist",
        detail="Read the checklist later.",
        priority="low",
        recommendation_type="general",
        source="manual-ui",
    )
    assert high["id"] != low["id"]

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    rows = main._recommendation_list(limit=10, status="proposed")

    assert rows[0]["id"] == high["id"]
    assert rows[0]["score"]["rank"] == 1
    assert rows[1]["id"] == low["id"]
    assert rows[1]["score"]["rank"] == 2


def test_recommendation_list_uses_outcome_history_for_calibration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    strong = inbox.create(
        title="Reliable next action",
        detail="Same source has historically matched expected direction.",
        priority="medium",
        recommendation_type="plan_settings_update",
        source="workflow:reliable_review",
    )
    weak = inbox.create(
        title="Noisy next action",
        detail="Same source has historically missed expected direction.",
        priority="medium",
        recommendation_type="plan_settings_update",
        source="workflow:noisy_review",
    )
    for index in range(2):
        created = inbox.create(
            title=f"Reliable measured {index}",
            detail="Measured historical recommendation.",
            priority="medium",
            recommendation_type="plan_settings_update",
            source="workflow:reliable_review",
            action_payload={
                "decision_closure": {
                    "expected_vs_realized": {
                        "status": "measured",
                        "future_value_gap_usd": 500.0,
                        "future_value_direction_match": True,
                    }
                }
            },
        )
        inbox.set_status(created["id"], status="applied")
        created = inbox.create(
            title=f"Noisy measured {index}",
            detail="Measured historical recommendation.",
            priority="medium",
            recommendation_type="plan_settings_update",
            source="workflow:noisy_review",
            action_payload={
                "decision_closure": {
                    "expected_vs_realized": {
                        "status": "measured",
                        "future_value_gap_usd": -500.0,
                        "future_value_direction_match": False,
                    }
                }
            },
        )
        inbox.set_status(created["id"], status="applied")

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    rows = main._recommendation_list(limit=10, status="proposed")
    by_id = {row["id"]: row for row in rows}

    assert rows[0]["id"] == strong["id"]
    assert by_id[strong["id"]]["score"]["calibration"]["confidence_delta"] > 0
    assert by_id[weak["id"]]["score"]["calibration"]["confidence_delta"] < 0


def test_recommendation_list_supports_created_at_sort(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    older = inbox.create(
        title="Older recommendation",
        detail="Created first.",
        priority="high",
    )
    newer = inbox.create(
        title="Newer recommendation",
        detail="Created second.",
        priority="low",
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    rows = main._recommendation_list(limit=10, status="proposed", sort="created_at")

    assert rows[0]["id"] == newer["id"]
    assert rows[1]["id"] == older["id"]
    assert rows[0]["score"]["rank"] is None


def test_create_recommendation_route_includes_score(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = main.RecommendationCreateRequest(
        title="Increase emergency fund",
        detail="Increase monthly savings transfer to emergency account.",
        priority="medium",
        recommendation_type="plan_settings_update",
        source="manual-ui",
    )
    item = main.create_recommendation(payload)

    assert item.score is not None
    assert item.score.total > 0
    assert item.score.impact > 0


def test_build_top_next_actions_scopes_to_plan_and_global(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    target_plan = inbox.create(
        title="Increase annual contributions",
        detail="Raise annual contribution by $4,000.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id="plan-target",
        source="workflow:weekly_review",
    )
    other_plan = inbox.create(
        title="Different plan action",
        detail="Belongs to another plan.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id="plan-other",
        source="workflow:weekly_review",
    )
    global_action = inbox.create(
        title="Global hygiene review",
        detail="Review global assumptions.",
        priority="low",
        recommendation_type="general",
        source="manual-ui",
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    actions = main._build_top_next_actions(plan_id="plan-target", limit=3)

    ids = [item.recommendation_id for item in actions]
    assert target_plan["id"] in ids
    assert global_action["id"] in ids
    assert other_plan["id"] not in ids
    assert ids[0] == target_plan["id"]


def test_top_next_actions_include_quality_explanation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Increase annual contributions",
        detail="Raise annual contribution after preview.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id="plan-target",
        source="generator:plan_tracking",
        action_payload={
            "plan_settings_updates": {"annual_contribution_usd": 24000.0},
            "quality": {
                "confidence_level": "medium",
                "confidence_score": 0.65,
                "freshness_status": "fresh",
                "actionability": "previewable",
                "reversibility": "high",
                "impact": {"level": "high", "summary": "Improves plan contribution pace."},
                "blocking_context": [],
                "decision_grade": True,
            },
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    actions = main._build_top_next_actions(plan_id="plan-target", limit=1)

    assert actions[0].recommendation_id == recommendation["id"]
    assert actions[0].quality_actionability == "previewable"
    assert actions[0].quality_summary == "high impact · medium confidence · fresh evidence · previewable · decision-grade"
    assert actions[0].blocking_context == []
    assert actions[0].action_hint == "Open Recommendation Inbox to preview before applying."


def test_get_plan_includes_top_next_actions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    workspace = PlanWorkspace(tmp_path / "plans")
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    plan = workspace.create_plan(title="Primary Plan")
    recommendation = inbox.create(
        title="Boost contribution rate",
        detail="Increase annual contribution in plan settings.",
        priority="high",
        recommendation_type="plan_settings_update",
        plan_id=plan["id"],
        source="workflow:plan_review",
    )

    monkeypatch.setattr(main, "plan_workspace", workspace)
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    payload = main.get_plan(plan["id"])

    assert payload.top_next_actions
    assert payload.top_next_actions[0].recommendation_id == recommendation["id"]


def test_today_command_cards_include_recommendation_loop_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    stale = inbox.create(
        title="Review stale tax assumptions",
        detail="Tax assumptions need review before plan advice is decision-grade.",
        priority="medium",
        source="generator:stale_assumptions",
        action_payload={"quality": {"actionability": "review_only"}},
    )
    pending = inbox.create(
        title="Applied contribution change",
        detail="Measure the realized outcome.",
        priority="medium",
        source="generator:plan_tracking",
        action_payload={
            "decision_closure": {
                "expected_vs_realized": {"status": "pending_realized"},
            }
        },
    )
    inbox.set_status(pending["id"], status="applied")

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=2.4,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["stale-assumptions"].status == "warning"
    assert cards["stale-assumptions"].metric_value == "1"
    assert cards["stale-assumptions"].href == f"#inbox?focus={stale['id']}"
    assert cards["outcome-loop"].status == "warning"
    assert cards["outcome-loop"].metric_value == "1"
    assert cards["cash-runway"].status == "warning"
    assert cards["cash-runway"].metric_value == "2.4 mo"
    assert cards["cash-runway"].href == "#inbox"


def test_today_confidence_domains_summarize_decision_readiness() -> None:
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        snapshot_age_minutes=90,
        snapshot_points_30d=2,
        total_value_usd=100_000,
        top_holding_symbol="NVDA",
        top_holding_percent=41,
        concentration_risk="high",
        active_plan=TodayActivePlanSummary(
            id="plan-1",
            title="Retire at 60",
            settings_completion_percent=72,
        ),
        profile_readiness=main.ProfileReadinessSummary(
            completion_percent=70,
            status="incomplete",
            next_gap_key="tax_profile",
            next_gap_title="Tax profile",
            next_gap_detail="Set filing status and marginal tax rate.",
            blocking_recommendation_sources=["tax_planning"],
            sections=[
                main.ProfileReadinessSection(
                    key="tax_profile",
                    title="Tax profile",
                    status="incomplete",
                    detail="Set filing status and marginal tax rate.",
                    required_for=["investment_fit"],
                    blocking_recommendations=True,
                )
            ],
        ),
        inbox_high_priority_count=2,
        emergency_fund_months=2.4,
        financial_health_status="critical",
        context_state="warning",
        command_cards=[
            main.TodayCommandCard(
                id="research-readiness",
                title="Research readiness",
                status="warning",
                detail="Evidence has material thesis changes.",
                metric_label="Ready",
                metric_value="1/3",
                action_label="Review research",
                href="#research-thesis-review?symbol=NVDA",
            ),
            main.TodayCommandCard(
                id="outcome-loop",
                title="Outcome loop",
                status="warning",
                detail="2 closed recommendations need outcome capture.",
                metric_label="Pending",
                metric_value="2",
                action_label="Log outcome",
                href="#inbox",
            ),
        ],
    )

    domains = {domain.id: domain for domain in main._build_today_confidence_domains(dashboard)}

    assert list(domains) == [
        "profile",
        "cash",
        "taxes",
        "plan",
        "portfolio",
        "research",
        "provider_data",
        "trust",
        "recommendations",
    ]
    assert domains["profile"].status == "missing_context"
    assert domains["cash"].status == "degraded"
    assert domains["taxes"].status == "missing_context"
    assert domains["plan"].status == "usable_with_caveats"
    assert domains["portfolio"].status == "degraded"
    assert domains["research"].status == "usable_with_caveats"
    assert domains["research"].href == "#research-thesis-review?symbol=NVDA"
    assert domains["provider_data"].status == "usable_with_caveats"
    assert domains["trust"].status == "missing_context"
    assert domains["recommendations"].status == "usable_with_caveats"


def test_today_trust_durability_card_surfaces_protection_backup_and_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BackupService:
        def list_backups(self) -> dict:
            return {
                "backups": [
                    {
                        "backup_id": "20260430T120000Z",
                        "created_at": main.utc_now(),
                        "size_bytes": 1024,
                    }
                ]
            }

    class DurableService:
        def get_status(self) -> dict:
            return {
                "database_exists": True,
                "document_count": 12,
                "latest_rollback_check_passed": True,
                "latest_migration_at": main.utc_now(),
            }

    class ProtectionService:
        def get_status(self) -> dict:
            return {
                "supported": True,
                "total_non_compliant_files": 2,
                "total_non_compliant_directories": 1,
                "policy": {
                    "protection_level": "standard",
                    "last_applied_at": None,
                },
                "targets": [],
            }

    class GitRepository:
        def status(self) -> dict:
            return {
                "status": "ok",
                "dirty": True,
                "changed_files": [{"path": "plans/plan.md", "status": "M"}],
                "last_commit": None,
                "has_remote": False,
            }

    class GitActivity:
        def query(self, **_: object) -> dict:
            return {"summary": {"total_matched": 3}, "events": []}

    monkeypatch.setattr(main, "backup_restore_service", BackupService())
    monkeypatch.setattr(main, "durable_storage_service", DurableService())
    monkeypatch.setattr(main, "data_protection_service", ProtectionService())
    monkeypatch.setattr(main, "_git_policy", lambda: {"enabled": True})
    monkeypatch.setattr(main, "_git_repository_service", lambda _policy: GitRepository())
    monkeypatch.setattr(main, "_git_activity_store", lambda: GitActivity())
    monkeypatch.setattr(
        main,
        "_engine_status_snapshot_sync",
        lambda: main.EngineStatusResponse(as_of=main.utc_now(), engines=[]),
    )

    card = main._build_trust_durability_command_card()
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        command_cards=[card],
    )
    domains = {domain.id: domain for domain in main._build_today_confidence_domains(dashboard)}

    assert card.id == "trust-durability"
    assert card.status == "warning"
    assert card.metric_label == "Ready"
    assert card.metric_value == "4/8"
    assert "Release readiness has warnings" in card.detail
    assert "3 protection item" in card.detail
    assert card.href == "#atelier?section=trust"
    assert domains["trust"].status == "usable_with_caveats"
    assert domains["trust"].href == "#atelier?section=trust"


def test_today_command_cards_surface_copilot_drafted_reviews(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    draft = inbox.create(
        title="Review NVDA fit before changing exposure",
        detail="NVDA conflicts with current concentration policy.",
        priority="high",
        source="copilot:investment_fit",
        recommendation_type="workflow_action",
        action_payload={
            "evidence": {
                "symbol": "NVDA",
                "freshness_status": "fresh",
                "confidence": "high",
                "fit_status": "does_not_fit",
            },
            "suggested_action": {
                "kind": "review_portfolio_fit",
                "symbol": "NVDA",
            },
            "quality": {
                "actionability": "review_only",
                "freshness_status": "fresh",
                "confidence_level": "high",
                "decision_grade": True,
            },
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    card = cards["copilot-drafts"]
    assert card.status == "warning"
    assert card.title == "Copilot prepared reviews"
    assert card.metric_label == "Drafts"
    assert card.metric_value == "1"
    assert card.action_label == "Review draft"
    assert card.href == f"#inbox?focus={draft['id']}"
    assert "NVDA" in card.detail
    assert "fresh" in card.detail
    assert "review-only" in card.detail


def test_today_what_changed_card_includes_operating_loop_deltas() -> None:
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        total_value_usd=300000,
        top_holding_symbol="AAPL",
        top_holding_percent=20.0,
        context_state="warning",
        context_notes=[],
        command_cards=[
            main.TodayCommandCard(
                id="research-readiness",
                title="Research readiness",
                status="warning",
                detail="2 research symbols have partial or degraded evidence.",
                metric_label="Ready",
                metric_value="1/3",
            ),
            main.TodayCommandCard(
                id="copilot-drafts",
                title="Copilot prepared reviews",
                status="warning",
                detail="2 Copilot-drafted reviews are waiting.",
                metric_label="Drafts",
                metric_value="2",
            ),
        ],
        top_next_actions=[
            main.TopNextAction(
                recommendation_id="rec-contribution",
                title="Review contribution account fit",
                detail="Contribution route needs review.",
                priority="high",
            )
        ],
        emergency_fund_months=3.0,
        financial_health_status="needs_attention",
    )

    card = main._build_enriched_what_changed_card(
        dashboard,
        {
            "recorded_at": "2026-04-29T12:00:00+00:00",
            "total_value_usd": 300000,
            "top_holding_symbol": "AAPL",
            "top_holding_percent": 20.0,
            "emergency_fund_months": 5.5,
            "financial_health_status": "healthy",
            "inbox_high_priority_count": 0,
            "command_card_statuses": {
                "research-readiness": {"status": "ready", "metric_value": "3/3"},
                "copilot-drafts": {"status": "ready", "metric_value": "0"},
            },
            "top_next_action_ids": ["rec-old"],
        },
    )

    assert card.status == "warning"
    assert card.metric_label == "Changes"
    assert card.metric_value == "4"
    assert "Cash runway is 2.5 months lower" in card.detail
    assert "Research readiness changed from ready to warning" in card.detail
    assert "2 new Copilot-drafted review(s) are waiting" in card.detail
    assert card.href == "#today?review=complete"


def test_today_review_checkpoint_captures_operating_loop_state() -> None:
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="warning",
        context_notes=[],
        command_cards=[
            main.TodayCommandCard(
                id="research-readiness",
                title="Research readiness",
                status="warning",
                detail="Research evidence is partial.",
                metric_label="Ready",
                metric_value="1/2",
            ),
            main.TodayCommandCard(
                id="copilot-drafts",
                title="Copilot prepared reviews",
                status="warning",
                detail="1 Copilot draft is waiting.",
                metric_label="Drafts",
                metric_value="1",
            ),
            main.TodayCommandCard(
                id="what-changed",
                title="What changed",
                status="warning",
                detail="Ignore this generated card.",
                metric_label="Changes",
                metric_value="2",
            ),
        ],
        top_next_actions=[
            main.TopNextAction(
                recommendation_id="rec-1",
                title="Review policy guardrails",
                detail="Policy is weak.",
                priority="medium",
            )
        ],
        emergency_fund_months=4.5,
        financial_health_status="needs_attention",
    )

    checkpoint = main._today_review_checkpoint_from_dashboard(dashboard)

    assert checkpoint["emergency_fund_months"] == 4.5
    assert checkpoint["financial_health_status"] == "needs_attention"
    assert checkpoint["top_next_action_ids"] == ["rec-1"]
    assert checkpoint["top_next_action_titles"] == ["Review policy guardrails"]
    assert checkpoint["command_card_statuses"] == {
        "research-readiness": {"status": "warning", "metric_value": "1/2"},
        "copilot-drafts": {"status": "warning", "metric_value": "1"},
    }


def test_today_command_cards_surface_missing_investment_policy_guardrails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    monkeypatch.setattr(main, "recommendation_inbox", inbox)

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
        profile_readiness=main.ProfileReadinessSummary(
            completion_percent=92.0,
            status="ready",
            sections=[
                main.ProfileReadinessSection(
                    key="investment_policy",
                    title="Investment policy",
                    status="attention",
                    detail="Set personal investment guardrails such as max single-symbol exposure.",
                    required_for=["investment_fit", "recommendation_ranking", "research_review"],
                    blocking_recommendations=False,
                )
            ],
        ),
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    card = cards["investment-policy"]
    assert card.status == "warning"
    assert card.title == "Investment policy"
    assert card.metric_label == "Guardrails"
    assert card.metric_value == "Missing"
    assert "max single-symbol exposure" in card.detail
    assert "investment-fit confidence" in card.detail
    assert card.action_label == "Define policy"
    assert card.href == "#copilot?intent=investment-policy"


def test_today_outcome_loop_surfaces_copilot_investment_process_calibration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Review NVDA fit before changing exposure",
        detail="NVDA conflicts with current concentration policy.",
        priority="high",
        status="applied",
        source="copilot:investment_fit",
        recommendation_type="workflow_action",
        action_payload={
            "evidence": {"symbol": "NVDA", "freshness_status": "fresh"},
            "quality": {
                "actionability": "review_only",
                "calibration": {"domain": "investment_research", "track_process_outcome": True},
            },
            "decision_closure": {
                "decision_status": "accepted",
                "expected_vs_realized": {"status": "unavailable"},
            },
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["outcome-loop"].status == "warning"
    assert cards["outcome-loop"].metric_value == "1"
    assert cards["outcome-loop"].href == f"#inbox?focus={recommendation['id']}"
    assert "decision-process calibration" in cards["outcome-loop"].detail


def test_today_outcome_loop_prioritizes_pending_pre_mortem_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Increase annual contributions",
        detail="High-impact contribution change accepted.",
        priority="high",
        status="applied",
        source="generator:plan_tracking",
        recommendation_type="plan_settings_update",
        action_payload={
            "decision_closure": {
                "decision_status": "accepted",
                "pre_mortem": {
                    "expected_benefit": "Retirement baseline improves.",
                    "main_risk": "Cash runway gets too tight.",
                    "disconfirming_signal": "Savings rate turns negative.",
                    "monitoring_plan": "Review cash runway after two pay cycles.",
                    "review_date": "2026-06-30",
                },
                "expected_outcome": {"expected_delta_future_value_usd": 1000.0},
                "expected_vs_realized": {"status": "pending_realized"},
            }
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["outcome-loop"].status == "warning"
    assert cards["outcome-loop"].metric_value == "1"
    assert cards["outcome-loop"].action_label == "Check pre-mortem"
    assert cards["outcome-loop"].href == f"#inbox?focus={recommendation['id']}"
    assert "pre-mortem check" in cards["outcome-loop"].detail
    assert "Cash runway gets too tight" in cards["outcome-loop"].detail


def test_today_command_cards_surface_pending_thesis_revision_outcome(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    recommendation = inbox.create(
        title="Revise NVDA thesis after concentration review",
        detail="Copilot prepared a revised thesis for review.",
        priority="high",
        status="applied",
        source="copilot:investment_fit",
        recommendation_type="workflow_action",
        action_payload={
            "thesis_revision": {
                "event_id": "thesis-revision:watchlist:nvda-1",
                "target_type": "watchlist",
                "symbol": "NVDA",
                "reviewed_at": "2026-04-29T12:00:00Z",
            },
            "quality": {
                "actionability": "review_only",
                "calibration": {"domain": "investment_research", "track_process_outcome": True},
            },
            "decision_closure": {
                "decision_status": "accepted",
                "expected_vs_realized": {"status": "unavailable"},
            },
        },
    )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    card = cards["thesis-outcome-loop"]
    assert card.status == "warning"
    assert card.metric_label == "Pending"
    assert card.metric_value == "1"
    assert card.href == f"#inbox?focus={recommendation['id']}"
    assert "thesis revision outcome" in card.detail
    assert "NVDA" in card.detail


def test_today_command_cards_surface_investment_process_calibration_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    for index, outcome in enumerate(["useful_review", "acted_elsewhere", "insufficient_evidence"], start=1):
        inbox.create(
            title=f"Investment review {index}",
            detail="Closed investment/research review.",
            priority="medium",
            status="applied",
            source="copilot:investment_fit",
            recommendation_type="workflow_action",
            action_payload={
                "decision_closure": {
                    "decision_status": "accepted",
                    "expected_vs_realized": {"status": "unavailable"},
                    "decision_process_calibration": {
                        "domain": "investment_research",
                        "process_outcome": outcome,
                        "evidence_sufficiency": "sufficient",
                    },
                },
            },
        )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    card = cards["investment-calibration"]
    assert card.status == "ready"
    assert card.metric_label == "Useful"
    assert card.metric_value == "67%"
    assert "3 investment/research outcomes calibrated" in card.detail
    assert "2 useful" in card.detail
    assert "1 weak" in card.detail
    assert card.href == "#inbox"


def test_today_command_cards_surface_thesis_revision_calibration_history(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    for index, outcome in enumerate(["useful_review", "insufficient_evidence"], start=1):
        inbox.create(
            title=f"Thesis review {index}",
            detail="Closed thesis revision review.",
            priority="medium",
            status="applied",
            source="copilot:investment_fit",
            recommendation_type="workflow_action",
            action_payload={
                "decision_closure": {
                    "decision_status": "accepted",
                    "expected_vs_realized": {"status": "unavailable"},
                    "decision_process_calibration": {
                        "domain": "investment_research",
                        "process_outcome": outcome,
                        "evidence_sufficiency": "sufficient",
                        "thesis_revision": {
                            "event_id": f"thesis-revision:watchlist:nvda-{index}",
                            "target_type": "watchlist",
                            "symbol": "NVDA",
                        },
                    },
                },
            },
        )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    card = cards["thesis-calibration"]
    assert card.status == "ready"
    assert card.metric_label == "Useful"
    assert card.metric_value == "1/2"
    assert "2 thesis revision outcome(s) calibrated" in card.detail
    assert "1 useful" in card.detail
    assert card.href == "#inbox"


def test_today_command_cards_include_research_readiness_from_evidence_packets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "MSFT"}, {"symbol": "NVDA"}]

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d"):
            del period, interval
            status = "fresh" if symbol in {"AAPL", "MSFT"} else "partial"
            blocking_gaps = [] if status == "fresh" else ["history"]
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
                symbol=symbol,
                provider="yfinance",
                period="6mo",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={
                    "quote_available": True,
                    "history_available": status == "fresh",
                    "warnings": [] if status == "fresh" else [f"{symbol}: history unavailable"],
                },
                freshness={"status": status},
                quality={
                    "confidence": "high" if status == "fresh" else "medium",
                    "blocking_gaps": blocking_gaps,
                },
                provenance={"warnings": [] if status == "fresh" else [f"{symbol}: history unavailable"]},
            )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    main.today_research_evidence_cache.clear()

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        top_holding_symbol="AAPL",
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["research-readiness"].status == "warning"
    assert cards["research-readiness"].metric_label == "Ready"
    assert cards["research-readiness"].metric_value == "2/3"
    assert cards["research-readiness"].detail == "1 research symbol has partial or degraded evidence: NVDA."
    assert cards["research-readiness"].action_label == "Refresh research"
    assert cards["research-readiness"].href == "#today?refresh=research"


def test_today_command_cards_mark_research_provider_degraded(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "MSFT"}]

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d"):
            del period, interval
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
                symbol=symbol,
                provider="yfinance",
                period="6mo",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={
                    "quote_available": False,
                    "history_available": False,
                    "warnings": [f"{symbol}: OpenBB unavailable"],
                },
                freshness={"status": "degraded"},
                quality={"confidence": "low", "blocking_gaps": ["quote", "history"]},
                provenance={"warnings": [f"{symbol}: OpenBB unavailable"]},
            )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    main.today_research_evidence_cache.clear()

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        top_holding_symbol="AAPL",
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["research-readiness"].status == "critical"
    assert cards["research-readiness"].metric_value == "0/2"
    assert "degraded provider/data coverage" in cards["research-readiness"].detail


def test_today_research_readiness_uses_cached_packets_with_age_and_refresh_action(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    calls: list[str] = []

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "MSFT"}]

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d"):
            del period, interval
            calls.append(symbol)
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
                symbol=symbol,
                provider="yfinance",
                period="6mo",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={"quote_available": True, "history_available": True, "warnings": []},
                freshness={"status": "fresh"},
                quality={"confidence": "high", "blocking_gaps": []},
                provenance={"warnings": []},
            )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    main.today_research_evidence_cache.clear()

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        top_holding_symbol="AAPL",
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    first_cards = {card.id: card for card in main._build_today_command_cards(dashboard)}
    second_cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert calls == ["AAPL", "MSFT"]
    assert second_cards["research-readiness"].status == "ready"
    assert second_cards["research-readiness"].metric_value == "2/2"
    assert "cached research age" in second_cards["research-readiness"].detail.lower()
    assert second_cards["research-readiness"].action_label == "Refresh research"
    assert second_cards["research-readiness"].href == "#today?refresh=research"
    assert first_cards["research-readiness"].metric_value == "2/2"


def test_today_research_readiness_surfaces_expired_saved_dossier_thesis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "MSFT"}]

    class FakePlanWorkspace:
        def get_active_plan_id(self) -> str:
            return "plan-1"

        def get_plan(self, plan_id: str) -> dict[str, object]:
            return {
                "id": plan_id,
                "artifacts": [
                    {
                        "id": "artifact-dossier-msft",
                        "file_name": "20260301T120000Z-research-dossier-msft-vti.md",
                        "title": "Research Dossier - MSFT vs VTI",
                        "created_at": "2026-03-01T12:00:00+00:00",
                    }
                ],
            }

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d"):
            del period, interval
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
                symbol=symbol,
                provider="yfinance",
                period="6mo",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={"quote_available": True, "history_available": True, "warnings": []},
                freshness={"status": "fresh"},
                metrics={"last_price": 410.0},
                quality={"confidence": "high", "blocking_gaps": []},
                provenance={"warnings": []},
            )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "plan_workspace", FakePlanWorkspace())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    main.today_research_evidence_cache.clear()

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        top_holding_symbol="AAPL",
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["research-readiness"].status == "warning"
    assert cards["research-readiness"].metric_value == "2/2"
    assert "saved research thesis review is due" in cards["research-readiness"].detail
    assert "MSFT" in cards["research-readiness"].detail
    assert cards["research-readiness"].action_label == "Review theses"
    assert cards["research-readiness"].href == "#research?thesisReview=artifact-dossier-msft&plan=plan-1"


def test_today_research_readiness_surfaces_watchlist_thesis_material_price_move(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [
                {
                    "symbol": "NVDA",
                    "thesis": "AI compute thesis.",
                    "updated_at": "2026-04-20T12:00:00+00:00",
                    "thesis_reference_price_usd": 800.0,
                }
            ]

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d"):
            del period, interval
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
                symbol=symbol,
                provider="yfinance",
                period="6mo",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={"quote_available": True, "history_available": True, "warnings": []},
                freshness={"status": "fresh"},
                metrics={"last_price": 980.0},
                quality={"confidence": "high", "blocking_gaps": []},
                provenance={"warnings": []},
            )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    main.today_research_evidence_cache.clear()

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        top_holding_symbol=None,
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["research-readiness"].status == "warning"
    assert "material price move" in cards["research-readiness"].detail
    assert "NVDA" in cards["research-readiness"].detail
    assert cards["research-readiness"].action_label == "Review theses"
    assert cards["research-readiness"].href == "#research?thesisReview=NVDA"


def test_today_research_readiness_surfaces_policy_material_change_thesis_review(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    inbox.create(
        title="Review MSFT thesis after policy context changed",
        detail="Your investment policy changed enough to revisit the saved thesis.",
        priority="medium",
        recommendation_type="workflow_action",
        source="generator:research_thesis_expiration",
        plan_id="plan-1",
        action_payload={
            "generator": {
                "signal_key": "thesis_policy_material_change",
                "signal_type": "research_thesis_expiration",
            },
            "evidence": {
                "artifact_id": "artifact-dossier-msft",
                "symbols": ["MSFT"],
                "policy_material_change_gaps": ["asset_class:policy_cap"],
            },
            "suggested_action": {
                "kind": "review_research_thesis",
                "reason": "policy_material_change",
                "artifact_id": "artifact-dossier-msft",
                "plan_id": "plan-1",
                "symbols": ["MSFT"],
            },
        },
    )

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return [{"symbol": "MSFT"}]

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d"):
            del period, interval
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
                symbol=symbol,
                provider="yfinance",
                period="6mo",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={"quote_available": True, "history_available": True, "warnings": []},
                freshness={"status": "fresh"},
                metrics={"last_price": 410.0},
                quality={"confidence": "high", "blocking_gaps": []},
                provenance={"warnings": []},
            )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    monkeypatch.setattr(main, "build_research_dossier_lookup_payload", lambda **_: {"items": []})
    main.today_research_evidence_cache.clear()

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        top_holding_symbol=None,
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )

    cards = {card.id: card for card in main._build_today_command_cards(dashboard)}

    assert cards["research-readiness"].status == "warning"
    assert "policy context changed" in cards["research-readiness"].detail
    assert "MSFT" in cards["research-readiness"].detail
    assert cards["research-readiness"].href == "#research?thesisReview=artifact-dossier-msft&plan=plan-1"


def test_refresh_today_research_readiness_clears_packet_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    inbox = RecommendationInbox(tmp_path / "recommendations.json")
    calls: list[str] = []

    class FakePortfolioStore:
        def list_watchlist(self) -> list[dict[str, object]]:
            return []

    class FakeResearchService:
        def evidence_packet(self, *, symbol: str, period: str = "6mo", interval: str = "1d"):
            del period, interval
            calls.append(symbol)
            return main.ResearchEvidencePacket(
                packet_id=f"research-evidence:yfinance:{symbol}:6mo:1d",
                symbol=symbol,
                provider="yfinance",
                period="6mo",
                interval="1d",
                generated_at=main.utc_now(),
                coverage={"quote_available": True, "history_available": True, "warnings": []},
                freshness={"status": "fresh"},
                quality={"confidence": "high", "blocking_gaps": []},
                provenance={"warnings": []},
            )

    monkeypatch.setattr(main, "recommendation_inbox", inbox)
    monkeypatch.setattr(main, "portfolio_store", FakePortfolioStore())
    monkeypatch.setattr(main, "research_service", FakeResearchService())
    main.today_research_evidence_cache.clear()

    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        top_holding_symbol="AAPL",
        context_state="ready",
        context_notes=[],
        command_cards=[],
        emergency_fund_months=8.0,
    )
    monkeypatch.setattr(main, "build_today_dashboard_response", lambda: dashboard)

    main._build_today_command_cards(dashboard)
    main._build_today_command_cards(dashboard)
    assert calls == ["AAPL"]

    refreshed = main.refresh_today_research_readiness()
    refreshed.command_cards = main._build_today_command_cards(refreshed)

    assert calls == ["AAPL", "AAPL"]
    refreshed_cards = {card.id: card for card in refreshed.command_cards}
    assert refreshed_cards["research-readiness"].metric_value == "1/1"

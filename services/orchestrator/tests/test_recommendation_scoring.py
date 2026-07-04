from buildwealth_orchestrator.services.recommendation_scoring import (
    build_recommendation_calibration_profile,
    normalize_recommendation_sort,
    score_and_sort_recommendations,
)


def test_normalize_recommendation_sort_defaults_to_ranked() -> None:
    assert normalize_recommendation_sort("ranked") == "ranked"
    assert normalize_recommendation_sort("created_at") == "created_at"
    assert normalize_recommendation_sort("unknown") == "ranked"


def test_score_and_sort_recommendations_ranks_proposed_before_newest() -> None:
    rows = [
        {
            "id": "rec-high",
            "created_at": "2026-04-10T10:00:00+00:00",
            "updated_at": "2026-04-10T10:00:00+00:00",
            "title": "Increase annual contributions",
            "detail": "Raise annual contributions by $6,000.",
            "priority": "high",
            "status": "proposed",
            "recommendation_type": "plan_settings_update",
            "source": "workflow:plan_review",
            "action_payload": {
                "plan_settings_updates": {"annual_contribution_usd": 26000.0},
                "scenario_diff_preview": {
                    "status": "captured",
                    "scenario_deltas": [{"label": "baseline", "delta_future_value_usd": 42000.0}],
                },
            },
        },
        {
            "id": "rec-low",
            "created_at": "2026-04-14T10:00:00+00:00",
            "updated_at": "2026-04-14T10:00:00+00:00",
            "title": "Review notes",
            "detail": "Read notes later.",
            "priority": "low",
            "status": "proposed",
            "recommendation_type": "general",
            "source": "manual-ui",
            "action_payload": {},
        },
    ]

    ranked = score_and_sort_recommendations(rows, sort="ranked")

    assert [row["id"] for row in ranked] == ["rec-high", "rec-low"]
    assert ranked[0]["score"]["rank"] == 1
    assert ranked[1]["score"]["rank"] == 2
    assert ranked[0]["score"]["total"] > ranked[1]["score"]["total"]


def test_score_and_sort_recommendations_created_at_mode_disables_rank() -> None:
    rows = [
        {
            "id": "rec-older",
            "created_at": "2026-04-10T10:00:00+00:00",
            "updated_at": "2026-04-10T10:00:00+00:00",
            "title": "Older",
            "detail": "Older row",
            "priority": "high",
            "status": "proposed",
            "recommendation_type": "plan_settings_update",
            "source": "workflow:plan_review",
            "action_payload": {},
        },
        {
            "id": "rec-newer",
            "created_at": "2026-04-14T10:00:00+00:00",
            "updated_at": "2026-04-14T10:00:00+00:00",
            "title": "Newer",
            "detail": "Newer row",
            "priority": "low",
            "status": "proposed",
            "recommendation_type": "general",
            "source": "manual-ui",
            "action_payload": {},
        },
    ]

    newest = score_and_sort_recommendations(rows, sort="created_at")

    assert [row["id"] for row in newest] == ["rec-newer", "rec-older"]
    assert newest[0]["score"]["rank"] is None
    assert newest[1]["score"]["rank"] is None


def test_ranked_sort_places_non_proposed_after_open_actions() -> None:
    rows = [
        {
            "id": "rec-applied",
            "created_at": "2026-04-10T10:00:00+00:00",
            "updated_at": "2026-04-14T10:00:00+00:00",
            "title": "Applied",
            "detail": "Already handled",
            "priority": "high",
            "status": "applied",
            "recommendation_type": "plan_settings_update",
            "source": "workflow:plan_review",
            "action_payload": {},
        },
        {
            "id": "rec-proposed",
            "created_at": "2026-04-12T10:00:00+00:00",
            "updated_at": "2026-04-12T10:00:00+00:00",
            "title": "Proposed",
            "detail": "Open action",
            "priority": "medium",
            "status": "proposed",
            "recommendation_type": "general",
            "source": "manual-ui",
            "action_payload": {},
        },
    ]

    ranked = score_and_sort_recommendations(rows, sort="ranked")

    assert [row["id"] for row in ranked] == ["rec-proposed", "rec-applied"]
    assert ranked[0]["score"]["rank"] == 1
    assert ranked[1]["score"]["rank"] is None


def test_scoring_penalizes_missing_required_dossier_citations() -> None:
    rows = [
        {
            "id": "rec-cited",
            "created_at": "2026-04-14T10:00:00+00:00",
            "updated_at": "2026-04-14T10:00:00+00:00",
            "title": "Cited recommendation",
            "detail": "Has complete dossier citations.",
            "priority": "medium",
            "status": "proposed",
            "recommendation_type": "general",
            "source": "copilot",
            "action_payload": {
                "evidence": {
                    "citation_quality": {
                        "required": True,
                        "status": "satisfied",
                        "required_symbols": ["NVDA"],
                        "cited_symbols": ["NVDA"],
                        "missing_dossier_symbols": [],
                    }
                }
            },
        },
        {
            "id": "rec-missing",
            "created_at": "2026-04-14T10:00:00+00:00",
            "updated_at": "2026-04-14T10:00:00+00:00",
            "title": "Missing citations",
            "detail": "No dossier citation coverage.",
            "priority": "medium",
            "status": "proposed",
            "recommendation_type": "general",
            "source": "copilot",
            "action_payload": {
                "evidence": {
                    "citation_quality": {
                        "required": True,
                        "status": "missing",
                        "required_symbols": ["NVDA"],
                        "cited_symbols": [],
                        "missing_dossier_symbols": ["NVDA"],
                    }
                }
            },
        },
    ]

    ranked = score_and_sort_recommendations(rows, sort="ranked")
    by_id = {row["id"]: row for row in ranked}
    assert by_id["rec-cited"]["score"]["confidence"] > by_id["rec-missing"]["score"]["confidence"]
    assert by_id["rec-cited"]["score"]["total"] > by_id["rec-missing"]["score"]["total"]


def _measured_recommendation(
    recommendation_id: str,
    *,
    source: str,
    recommendation_type: str = "plan_settings_update",
    direction_match: bool,
    gap_usd: float = 1000.0,
) -> dict[str, object]:
    return {
        "id": recommendation_id,
        "created_at": "2026-04-10T10:00:00+00:00",
        "updated_at": "2026-04-11T10:00:00+00:00",
        "title": recommendation_id,
        "detail": "Closed recommendation with measured outcome.",
        "priority": "medium",
        "status": "applied",
        "recommendation_type": recommendation_type,
        "source": source,
        "action_payload": {
            "decision_closure": {
                "expected_vs_realized": {
                    "status": "measured",
                    "future_value_gap_usd": gap_usd,
                    "future_value_direction_match": direction_match,
                }
            }
        },
    }


def _proposed_recommendation(
    recommendation_id: str,
    *,
    source: str,
    recommendation_type: str = "plan_settings_update",
) -> dict[str, object]:
    return {
        "id": recommendation_id,
        "created_at": "2026-04-14T10:00:00+00:00",
        "updated_at": "2026-04-14T10:00:00+00:00",
        "title": recommendation_id,
        "detail": "Open recommendation.",
        "priority": "medium",
        "status": "proposed",
        "recommendation_type": recommendation_type,
        "source": source,
        "action_payload": {},
    }


def _process_calibrated_recommendation(
    recommendation_id: str,
    *,
    source: str,
    process_outcome: str,
    recommendation_type: str = "workflow_action",
) -> dict[str, object]:
    return {
        "id": recommendation_id,
        "created_at": "2026-04-10T10:00:00+00:00",
        "updated_at": "2026-04-11T10:00:00+00:00",
        "title": recommendation_id,
        "detail": "Closed investment research recommendation with process calibration.",
        "priority": "medium",
        "status": "applied",
        "recommendation_type": recommendation_type,
        "source": source,
        "action_payload": {
            "decision_closure": {
                "expected_vs_realized": {"status": "unavailable"},
                "decision_process_calibration": {
                    "domain": "investment_research",
                    "process_outcome": process_outcome,
                    "evidence_sufficiency": "sufficient",
                },
            }
        },
    }


def test_calibration_profile_summarizes_measured_outcomes_by_source_and_type() -> None:
    profile = build_recommendation_calibration_profile(
        [
            _measured_recommendation("match-1", source="workflow:daily_review", direction_match=True),
            _measured_recommendation("match-2", source="workflow:daily_review", direction_match=True),
            _measured_recommendation("miss-1", source="workflow:other", direction_match=False),
        ]
    )

    source = profile["by_source"]["workflow:daily_review"]
    assert source["measured_count"] == 2
    assert source["future_value_direction_match_rate_pct"] == 100.0
    assert source["confidence_adjustment"] > 0

    recommendation_type = profile["by_type"]["plan_settings_update"]
    assert recommendation_type["measured_count"] == 3
    assert recommendation_type["future_value_direction_match_rate_pct"] == 66.67


def test_calibration_adjusts_confidence_and_ranking_for_future_recommendations() -> None:
    good_source = "workflow:reliable_review"
    weak_source = "workflow:noisy_review"
    rows = [
        _proposed_recommendation("good-next", source=good_source),
        _proposed_recommendation("weak-next", source=weak_source),
    ]
    calibration_rows = [
        _measured_recommendation("good-1", source=good_source, direction_match=True),
        _measured_recommendation("good-2", source=good_source, direction_match=True),
        _measured_recommendation("weak-1", source=weak_source, direction_match=False),
        _measured_recommendation("weak-2", source=weak_source, direction_match=False),
    ]

    ranked = score_and_sort_recommendations(rows, sort="ranked", calibration_rows=calibration_rows)
    by_id = {row["id"]: row for row in ranked}

    assert ranked[0]["id"] == "good-next"
    assert by_id["good-next"]["score"]["calibration"]["confidence_delta"] > 0
    assert by_id["weak-next"]["score"]["calibration"]["confidence_delta"] < 0
    assert by_id["good-next"]["score"]["confidence"] > by_id["weak-next"]["score"]["confidence"]
    assert any("Calibration adjusted confidence" in reason for reason in by_id["good-next"]["score"]["reasons"])


def test_investment_process_outcomes_calibrate_future_copilot_drafts() -> None:
    rows = [
        _proposed_recommendation("next-useful", source="copilot:investment_fit", recommendation_type="workflow_action"),
        _proposed_recommendation("next-weak", source="copilot:weak_investment_fit", recommendation_type="workflow_action"),
    ]
    calibration_rows = [
        _process_calibrated_recommendation("useful-1", source="copilot:investment_fit", process_outcome="useful_review"),
        _process_calibrated_recommendation("useful-2", source="copilot:investment_fit", process_outcome="acted_elsewhere"),
        _process_calibrated_recommendation("weak-1", source="copilot:weak_investment_fit", process_outcome="insufficient_evidence"),
        _process_calibrated_recommendation("weak-2", source="copilot:weak_investment_fit", process_outcome="not_useful"),
    ]

    ranked = score_and_sort_recommendations(rows, sort="ranked", calibration_rows=calibration_rows)
    by_id = {row["id"]: row for row in ranked}

    assert ranked[0]["id"] == "next-useful"
    assert by_id["next-useful"]["score"]["calibration"]["source"]["process_count"] == 2
    assert by_id["next-useful"]["score"]["calibration"]["confidence_delta"] > 0
    assert by_id["next-weak"]["score"]["calibration"]["confidence_delta"] < 0
    assert any("process outcomes" in reason for reason in by_id["next-useful"]["score"]["reasons"])


def test_quality_metadata_promotes_decision_grade_actions_over_context_gathering() -> None:
    rows = [
        {
            "id": "context-gap",
            "created_at": "2026-04-14T10:00:00+00:00",
            "updated_at": "2026-04-14T10:00:00+00:00",
            "title": "Complete profile gap",
            "detail": "Missing data blocks better recommendations.",
            "priority": "high",
            "status": "proposed",
            "recommendation_type": "workflow_action",
            "source": "generator:profile_completeness",
            "action_payload": {
                "quality": {
                    "confidence_level": "high",
                    "confidence_score": 0.85,
                    "freshness_status": "unknown",
                    "actionability": "context_gathering",
                    "reversibility": "high",
                    "impact": {"level": "high", "summary": "Improves context."},
                    "blocking_context": ["financial_profile.expenses"],
                    "decision_grade": False,
                }
            },
        },
        {
            "id": "previewable-plan",
            "created_at": "2026-04-14T10:00:00+00:00",
            "updated_at": "2026-04-14T10:00:00+00:00",
            "title": "Increase contributions",
            "detail": "Preview contribution change before applying.",
            "priority": "high",
            "status": "proposed",
            "recommendation_type": "plan_settings_update",
            "source": "generator:plan_tracking",
            "action_payload": {
                "plan_settings_updates": {"annual_contribution_usd": 24000.0},
                "quality": {
                    "confidence_level": "medium",
                    "confidence_score": 0.65,
                    "freshness_status": "fresh",
                    "actionability": "previewable",
                    "reversibility": "high",
                    "impact": {"level": "high", "summary": "Improves plan pace."},
                    "blocking_context": [],
                    "decision_grade": True,
                },
            },
        },
    ]

    ranked = score_and_sort_recommendations(rows, sort="ranked")

    assert [row["id"] for row in ranked] == ["previewable-plan", "context-gap"]
    assert ranked[0]["score"]["confidence"] > ranked[1]["score"]["confidence"]
    assert any("decision-grade" in reason.lower() for reason in ranked[0]["score"]["reasons"])
    assert any("missing context" in reason.lower() for reason in ranked[1]["score"]["reasons"])


def _rejected_row(source: str, index: int) -> dict:
    return {
        "id": f"rec-declined-{index}",
        "title": f"Declined suggestion {index}",
        "status": "rejected",
        "source": source,
        "recommendation_type": "workflow_action",
        "created_at": "2026-06-01T00:00:00+00:00",
        "action_payload": {"decision_closure": {"decision_status": "rejected"}},
    }


def test_calibration_counts_declines_and_penalizes_refused_sources() -> None:
    rows = [_rejected_row("generator:noisy", index) for index in range(3)]
    profile = build_recommendation_calibration_profile(rows)
    bucket = profile["by_source"]["generator:noisy"]

    assert bucket["rejected_count"] == 3
    assert bucket["decided_count"] == 3
    assert bucket["rejection_rate_pct"] == 100.0
    assert bucket["confidence_adjustment"] == -4.0

    # two declines are not yet a pattern
    thin = build_recommendation_calibration_profile(rows[:2])
    assert thin["by_source"]["generator:noisy"]["confidence_adjustment"] == 0.0

    # a 50% rejection rate earns the smaller penalty
    mixed_rows = rows[:2] + [
        {
            "id": f"rec-applied-{index}",
            "title": f"Applied suggestion {index}",
            "status": "applied",
            "source": "generator:noisy",
            "recommendation_type": "workflow_action",
            "created_at": "2026-06-01T00:00:00+00:00",
            "action_payload": {"decision_closure": {"decision_status": "accepted"}},
        }
        for index in range(2)
    ]
    mixed = build_recommendation_calibration_profile(mixed_rows)
    assert mixed["by_source"]["generator:noisy"]["rejection_rate_pct"] == 50.0
    assert mixed["by_source"]["generator:noisy"]["confidence_adjustment"] == -2.0


def test_ranking_quiets_repeatedly_declined_sources() -> None:
    history = [_rejected_row("generator:noisy", index) for index in range(4)]
    proposed = [
        {
            "id": "rec-noisy-new",
            "title": "Another noisy suggestion",
            "status": "proposed",
            "priority": "medium",
            "source": "generator:noisy",
            "recommendation_type": "workflow_action",
            "created_at": "2026-07-01T00:00:00+00:00",
            "action_payload": {},
        },
        {
            "id": "rec-quiet-new",
            "title": "A suggestion from a source with no decline history",
            "status": "proposed",
            "priority": "medium",
            "source": "generator:quiet",
            "recommendation_type": "workflow_action",
            "created_at": "2026-07-01T00:00:00+00:00",
            "action_payload": {},
        },
    ]

    ranked = score_and_sort_recommendations(history + proposed, sort="ranked")
    ranked_proposed = [row for row in ranked if row["status"] == "proposed"]

    assert ranked_proposed[0]["id"] == "rec-quiet-new"
    noisy = next(row for row in ranked_proposed if row["id"] == "rec-noisy-new")
    assert noisy["score"]["calibration"]["confidence_delta"] < 0
    assert any("declined" in reason for reason in noisy["score"]["reasons"])

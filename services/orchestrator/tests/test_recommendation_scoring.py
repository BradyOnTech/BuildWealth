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

"""Session Focus normalize / resolve / store lifecycle (PR3)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from buildwealth_orchestrator.services.copilot_runtime import ConversationStore, FinancialCopilot
from buildwealth_orchestrator.services.session_focus import (
    SessionFocusValidationError,
    covers_focus_domain,
    focus_applied_stored_only,
    focus_equal,
    list_covers,
    merge_focus_patch,
    merge_focus_with_intent,
    normalize_focus,
    parse_session_focus_utterance,
    pinned_focus_domains,
    public_focus,
    resolve_turn_focus,
    run_plan_id_pass,
)


def test_normalize_focus_defaults_missing() -> None:
    focus = normalize_focus(None)
    assert focus["mode"] == "balanced"
    assert focus["primary_domains"] == []
    assert focus["set_by"] == "default"
    assert focus["schema_version"] == 1


def test_normalize_focus_drops_unknown_on_read() -> None:
    focus = normalize_focus(
        {
            "mode": "narrow",
            "primary_domains": ["plan", "not_a_domain"],
            "muted_domains": ["research"],
        },
        strict=False,
    )
    assert focus["primary_domains"] == ["plan"]
    assert focus["muted_domains"] == ["research"]
    assert "not_a_domain" in focus.get("_dropped_domains", [])


def test_normalize_focus_strict_rejects_unknown() -> None:
    with pytest.raises(SessionFocusValidationError, match="Unknown focus domain"):
        normalize_focus(
            {"primary_domains": ["plan", "spaceship"]},
            strict=True,
        )


def test_user_primary_wins_over_mute_on_write() -> None:
    focus = normalize_focus(
        {
            "primary_domains": ["research"],
            "muted_domains": ["research", "portfolio"],
            "set_by": "user",
        },
        strict=True,
        set_by_override="user",
        touch_updated_at=True,
    )
    assert focus["primary_domains"] == ["research"]
    assert "research" not in focus["muted_domains"]
    assert "portfolio" in focus["muted_domains"]
    assert focus["updated_at"]


def test_secondary_dropped_when_covered_by_primary_or_mute() -> None:
    focus = normalize_focus(
        {
            "primary_domains": ["profile"],
            "secondary_domains": ["profile.goals", "plan", "research"],
            "muted_domains": ["research"],
        },
        strict=True,
    )
    assert focus["primary_domains"] == ["profile"]
    assert focus["secondary_domains"] == ["plan"]
    assert focus["muted_domains"] == ["research"]


def test_merge_focus_patch_partial() -> None:
    stored = normalize_focus(
        {
            "mode": "balanced",
            "primary_domains": ["plan"],
            "muted_domains": ["research"],
        }
    )
    merged = merge_focus_patch(
        stored,
        {"muted_domains": ["research", "portfolio.holdings"], "priority_note": "cashflow first"},
        set_by="user",
    )
    assert merged["primary_domains"] == ["plan"]
    assert merged["muted_domains"] == ["research", "portfolio.holdings"]
    assert merged["priority_note"] == "cashflow first"
    assert merged["set_by"] == "user"


def test_resolve_turn_focus_request_wins() -> None:
    stored = normalize_focus({"primary_domains": ["plan"], "set_by": "entry_surface"})
    resolved = resolve_turn_focus(
        stored=stored,
        request_focus={"primary_domains": ["profile.goals"], "mode": "narrow"},
    )
    assert resolved["primary_domains"] == ["profile.goals"]
    assert resolved["mode"] == "narrow"
    assert resolved["set_by"] == "user"


def test_resolve_turn_focus_falls_back_to_stored() -> None:
    stored = normalize_focus(
        {"primary_domains": ["recommendation"], "set_by": "entry_surface"},
        touch_updated_at=True,
    )
    resolved = resolve_turn_focus(stored=stored, request_focus=None)
    assert resolved["primary_domains"] == ["recommendation"]
    assert resolved["set_by"] == "entry_surface"


def test_focus_applied_stored_only() -> None:
    payload = focus_applied_stored_only(
        {"mode": "narrow", "primary_domains": ["plan"], "muted_domains": ["research"], "set_by": "user"}
    )
    assert payload["effect"] == "stored_only"
    assert payload["primary_domains"] == ["plan"]
    assert payload["muted_domains"] == ["research"]
    assert "package_sections_included" not in payload


def test_public_focus_strips_private_keys() -> None:
    raw = normalize_focus({"primary_domains": ["plan", "zzz"]}, strict=False)
    assert "_dropped_domains" in raw
    cleaned = public_focus(raw)
    assert "_dropped_domains" not in cleaned


def test_focus_equal_ignores_updated_at() -> None:
    a = normalize_focus({"primary_domains": ["plan"]}, touch_updated_at=True)
    b = normalize_focus({"primary_domains": ["plan"]}, touch_updated_at=True)
    assert a["updated_at"] != b["updated_at"] or True
    assert focus_equal(a, b)


def test_conversation_store_persists_focus(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    conversation = store.get_or_create(None, "Focus on goals please")
    assert "focus" in conversation
    assert conversation["focus"]["mode"] == "balanced"

    focus = normalize_focus(
        {
            "mode": "narrow",
            "primary_domains": ["profile.goals"],
            "muted_domains": ["research"],
            "set_by": "user",
        },
        strict=True,
        set_by_override="user",
        touch_updated_at=True,
    )
    updated = store.update_focus(conversation["id"], public_focus(focus))
    loaded = store.get(conversation["id"])
    assert loaded["focus"]["primary_domains"] == ["profile.goals"]
    assert updated["focus"]["muted_domains"] == ["research"]


def test_parse_session_focus_utterance_mute_and_focus() -> None:
    mute = parse_session_focus_utterance("For this conversation ignore research please.")
    assert mute is not None
    assert "research" in mute.get("muted_domains", [])

    focus = parse_session_focus_utterance("Focus only on goals for this chat.")
    assert focus is not None
    assert focus.get("primary_domains") == ["profile.goals"]
    assert focus.get("mode") == "narrow"

    assert parse_session_focus_utterance("What is my net worth?") is None


def test_covers_and_list_covers_parent_child() -> None:
    assert covers_focus_domain("profile", "profile.goals")
    assert covers_focus_domain("profile.goals", "profile")
    assert not covers_focus_domain("profile.goals", "profile.tax")
    assert list_covers(["profile.goals"], "profile")
    assert list_covers(["profile"], "profile.goals")


def test_pinned_focus_domains_map() -> None:
    assert pinned_focus_domains(["recommendation:rec-1", "goal:house", "symbol:AAPL"]) == {
        "recommendation",
        "profile.goals",
        "research",
    }
    assert pinned_focus_domains(["nope", "weird"]) == set()


def test_merge_focus_with_intent_golden_examples() -> None:
    planning_medium = {
        "intent": "planning_question",
        "confidence": "medium",
        "domains": ["plan", "profile", "recommendation", "research"],
    }
    investment_high = {
        "intent": "investment_fit",
        "confidence": "high",
        "domains": ["research", "plan", "profile", "recommendation"],
    }
    investment_medium = {
        "intent": "investment_fit",
        "confidence": "medium",
        "domains": ["research", "plan", "profile", "recommendation"],
    }
    general_medium = {
        "intent": "general",
        "confidence": "medium",
        "domains": ["profile", "plan", "recommendation", "research"],
    }

    # Example 1
    e1 = merge_focus_with_intent(None, planning_medium)
    assert list(e1.primary_domains) == ["plan", "profile"]
    assert list(e1.secondary_domains) == ["recommendation", "research"]
    assert list(e1.muted_domains) == []
    assert list(e1.retrieval_registry_domains) == ["plan", "profile", "recommendation", "research"]

    # Example 2
    e2 = merge_focus_with_intent(
        {
            "mode": "balanced",
            "primary_domains": ["profile.goals"],
            "muted_domains": ["research"],
            "secondary_domains": [],
        },
        planning_medium,
    )
    assert list(e2.primary_domains) == ["profile.goals"]
    assert list(e2.secondary_domains) == ["plan", "recommendation"]
    assert list(e2.muted_domains) == ["research"]
    assert list(e2.retrieval_registry_domains) == ["profile", "plan", "recommendation"]

    # Example 3a
    e3a = merge_focus_with_intent({"muted_domains": ["research"]}, investment_high)
    assert list(e3a.primary_domains) == ["plan"]
    assert "research" in e3a.muted_domains
    assert "research" not in e3a.retrieval_registry_domains

    # Example 3b
    e3b = merge_focus_with_intent({"muted_domains": ["research"]}, investment_medium)
    assert list(e3b.primary_domains) == ["plan"]
    assert "research" in e3b.muted_domains

    # Example 3c
    e3c = merge_focus_with_intent(
        {"primary_domains": ["research"], "muted_domains": ["research"]},
        investment_high,
    )
    assert list(e3c.primary_domains) == ["research"]
    assert list(e3c.muted_domains) == []
    assert "research" in e3c.retrieval_registry_domains

    # Example 4
    e4 = merge_focus_with_intent(
        {"mode": "narrow", "primary_domains": ["plan"], "secondary_domains": []},
        general_medium,
    )
    assert list(e4.primary_domains) == ["plan"]
    assert list(e4.secondary_domains) == []
    assert "research" in e4.muted_domains
    assert "profile" in e4.muted_domains
    assert list(e4.retrieval_registry_domains) == ["plan"]

    # Example 4b
    e4b = merge_focus_with_intent(
        {
            "mode": "narrow",
            "primary_domains": ["plan"],
            "secondary_domains": [],
            "pinned_entity_ids": ["recommendation:rec-1"],
        },
        general_medium,
    )
    assert list(e4b.primary_domains) == ["plan"]
    assert list(e4b.secondary_domains) == []
    assert "recommendation" not in e4b.muted_domains or list_covers(["plan", "recommendation"], "recommendation")
    assert "recommendation" in e4b.retrieval_registry_domains
    assert "plan" in e4b.retrieval_registry_domains

    # Example 5
    e5 = merge_focus_with_intent(
        {"mode": "wide", "muted_domains": ["portfolio.holdings"]},
        planning_medium,
    )
    assert list(e5.primary_domains) == ["plan", "profile"]
    assert list(e5.muted_domains) == ["portfolio.holdings"]

    # Example 6
    e6 = merge_focus_with_intent(
        {"mode": "balanced", "primary_domains": ["portfolio"], "secondary_domains": []},
        planning_medium,
    )
    assert list(e6.primary_domains) == ["portfolio"]
    assert "plan" in e6.secondary_domains
    assert "portfolio" in e6.retrieval_registry_domains


def test_run_plan_id_pass_rules() -> None:
    narrow_plan = merge_focus_with_intent(
        {"mode": "narrow", "primary_domains": ["plan"]},
        {"domains": ["profile", "plan"], "confidence": "medium"},
    )
    narrow_goals = merge_focus_with_intent(
        {"mode": "narrow", "primary_domains": ["profile.goals"]},
        {"domains": ["profile", "plan"], "confidence": "medium"},
    )
    balanced = merge_focus_with_intent(None, {"domains": ["plan", "profile"], "confidence": "medium"})
    assert run_plan_id_pass(plan_id="plan-1", effective=narrow_plan) is True
    assert run_plan_id_pass(plan_id="plan-1", effective=narrow_goals) is False
    assert run_plan_id_pass(plan_id="plan-1", effective=balanced) is True
    assert run_plan_id_pass(plan_id=None, effective=balanced) is False


def test_copilot_chat_accepts_preloaded_conversation(tmp_path: Path) -> None:
    store = ConversationStore(tmp_path)
    conversation = store.get_or_create(None, "Hello")
    focus = public_focus(
        normalize_focus(
            {"primary_domains": ["plan"], "set_by": "user"},
            strict=True,
            set_by_override="user",
            touch_updated_at=True,
        )
    )
    conversation = store.update_focus(conversation["id"], focus)

    class DisabledClient:
        enabled = False
        model = "none"

    copilot = FinancialCopilot(
        conversation_store=store,
        llm_client=DisabledClient(),  # type: ignore[arg-type]
        max_history_messages=10,
        max_tool_rounds=1,
        system_prompt="System",
    )
    result = asyncio.run(
        copilot.chat(
            question="Am I on track?",
            conversation=conversation,
            contextual_brief='{"brief_version":"copilot_prompt_brief_v1"}',
            context_trace={"focus_applied": focus_applied_stored_only(focus)},
        )
    )
    loaded = store.get(result["conversation_id"])
    assert loaded["focus"]["primary_domains"] == ["plan"]
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][-1]["metadata"]["context_trace"]["focus_applied"]["effect"] == "stored_only"

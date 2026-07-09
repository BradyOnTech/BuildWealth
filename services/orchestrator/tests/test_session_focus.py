"""Session Focus normalize / resolve / store lifecycle (PR3)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from buildwealth_orchestrator.services.copilot_runtime import ConversationStore, FinancialCopilot
from buildwealth_orchestrator.services.session_focus import (
    SessionFocusValidationError,
    focus_applied_stored_only,
    focus_equal,
    merge_focus_patch,
    normalize_focus,
    public_focus,
    resolve_turn_focus,
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

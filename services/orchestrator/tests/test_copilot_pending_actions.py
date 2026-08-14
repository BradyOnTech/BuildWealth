from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from buildwealth_orchestrator.services import copilot_pending_actions
from buildwealth_orchestrator.services.copilot_pending_actions import (
    FinancialActionImpact,
    PendingActionError,
    PendingActionExpiredError,
    PendingActionStateError,
    PendingActionStatus,
    PendingActionStaleError,
    PendingActionStoreCorruptionError,
    PendingActionValidationError,
    PendingFinancialActionStore,
    fingerprint_source_state,
    validate_source_fingerprint,
)

BASE_TIME = datetime(2026, 7, 31, 15, 0, tzinfo=timezone.utc)


class MutableClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, delta: timedelta) -> None:
        self.value += delta


def _store(
    tmp_path: Path,
    *,
    clock: MutableClock | None = None,
    action_ids: list[str] | None = None,
) -> PendingFinancialActionStore:
    ids = iter(action_ids or ["pfa_test_action"])
    return PendingFinancialActionStore(
        tmp_path / "workspace" / "copilot" / "pending_financial_actions.json",
        workspace_id="workspace-real",
        clock=clock or MutableClock(BASE_TIME),
        id_factory=lambda: next(ids),
        default_ttl=timedelta(minutes=20),
    )


def _create(
    store: PendingFinancialActionStore,
    *,
    payload: dict[str, Any] | None = None,
    source_state: dict[str, Any] | None = None,
    **overrides: Any,
):
    current_source = source_state or {
        "profile_revision": 7,
        "plan_revision": "plan-rev-12",
    }
    arguments: dict[str, Any] = {
        "payload": payload
        or {
            "operation": "update_profile",
            "patch": {"investment_policy": {"risk_tolerance": "moderate"}},
        },
        "conversation_id": "conversation-1",
        "turn_id": "turn-9",
        "tool_name": "draft_profile_update",
        "tool_call_id": "call-42",
        "summary": "Change the saved risk posture to Moderate.",
        "impact_level": "medium",
        "source_state_fingerprint": fingerprint_source_state(current_source),
        "evidence_refs": ["profile:investment_policy", "risk-lens:comparison-9"],
    }
    arguments.update(overrides)
    return store.create(**arguments)


def test_create_persists_exact_immutable_payload_and_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = {
        "operation": "apply_plan_patch",
        "patch": {
            "annual_contribution_usd": 24_000.0,
            "drawdown_order": ["taxable", "traditional", "roth"],
        },
    }

    action = _create(store, payload=payload, impact_level=FinancialActionImpact.HIGH)
    payload["patch"]["annual_contribution_usd"] = 1.0
    returned_payload = action.payload
    returned_payload["patch"]["drawdown_order"].append("mutated")

    assert action.action_id == "pfa_test_action"
    assert action.workspace_id == "workspace-real"
    assert action.conversation_id == "conversation-1"
    assert action.turn_id == "turn-9"
    assert action.tool_name == "draft_profile_update"
    assert action.tool_call_id == "call-42"
    assert action.summary == "Change the saved risk posture to Moderate."
    assert action.impact_level is FinancialActionImpact.HIGH
    assert action.status is PendingActionStatus.PENDING
    assert action.created_at == BASE_TIME
    assert action.expires_at == BASE_TIME + timedelta(minutes=20)
    assert action.evidence_refs == (
        "profile:investment_policy",
        "risk-lens:comparison-9",
    )
    assert action.payload == {
        "operation": "apply_plan_patch",
        "patch": {
            "annual_contribution_usd": 24_000.0,
            "drawdown_order": ["taxable", "traditional", "roth"],
        },
    }

    on_disk = json.loads(store.path.read_text(encoding="utf-8"))
    assert on_disk["workspace_id"] == "workspace-real"
    assert on_disk["actions"][0]["payload"] == action.payload
    assert on_disk["actions"][0]["payload_sha256"] == action.payload_sha256
    assert not list(store.path.parent.glob("*.tmp"))


def test_reload_preserves_pending_and_terminal_actions(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    store = _store(
        tmp_path,
        clock=clock,
        action_ids=["pfa_first", "pfa_second"],
    )
    first = _create(store)
    clock.advance(timedelta(minutes=1))
    second = _create(
        store,
        conversation_id="conversation-2",
        summary="Save a reviewed contribution change.",
    )
    rejected = store.reject(second.action_id, reason="Keep the current contribution.")

    reloaded = PendingFinancialActionStore(
        store.path,
        workspace_id="workspace-real",
        clock=clock,
    )

    assert reloaded.get(first.action_id).payload == first.payload
    reloaded_rejected = reloaded.get(second.action_id)
    assert reloaded_rejected.status is PendingActionStatus.REJECTED
    assert reloaded_rejected.rejected_at == rejected.rejected_at
    assert reloaded_rejected.status_reason == "Keep the current contribution."
    assert [item.action_id for item in reloaded.list()] == [
        "pfa_second",
        "pfa_first",
    ]
    assert [
        item.action_id
        for item in reloaded.list(
            statuses=["pending"],
            conversation_id="conversation-1",
        )
    ] == ["pfa_first"]


def test_pending_action_expires_deterministically_and_stays_terminal(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    store = _store(tmp_path, clock=clock)
    action = _create(store, expires_in=timedelta(minutes=5))

    clock.advance(timedelta(minutes=5))
    expired = store.get(action.action_id)

    assert expired.status is PendingActionStatus.EXPIRED
    assert expired.expired_at == clock.value
    assert "fresh proposal" in (expired.status_reason or "")
    with pytest.raises(PendingActionExpiredError) as exc_info:
        store.mark_applied(
            action.action_id,
            current_source_fingerprint=action.source_state_fingerprint,
        )
    assert exc_info.value.action.status is PendingActionStatus.EXPIRED
    assert store.get(action.action_id).expired_at == clock.value


def test_fingerprint_is_canonical_and_stale_source_is_recorded(tmp_path: Path) -> None:
    left = {"plan": {"revision": 4, "settings": {"years": 25, "rate": 0.06}}}
    reordered = {"plan": {"settings": {"rate": 0.06, "years": 25}, "revision": 4}}
    changed = {"plan": {"revision": 5, "settings": {"years": 25, "rate": 0.06}}}
    assert fingerprint_source_state(left) == fingerprint_source_state(reordered)
    assert validate_source_fingerprint(
        fingerprint_source_state(left),
        fingerprint_source_state(reordered),
    )
    assert not validate_source_fingerprint(
        fingerprint_source_state(left),
        fingerprint_source_state(changed),
    )

    store = _store(tmp_path)
    action = _create(store, source_state=left)
    with pytest.raises(PendingActionStaleError) as exc_info:
        store.mark_applied(
            action.action_id,
            current_source_fingerprint=fingerprint_source_state(changed),
        )

    stale = exc_info.value.action
    assert stale.status is PendingActionStatus.STALE
    assert stale.stale_at == BASE_TIME
    assert "underlying financial state changed" in (stale.status_reason or "")
    assert store.get(action.action_id).status is PendingActionStatus.STALE
    with pytest.raises(PendingActionStaleError):
        store.mark_applied(
            action.action_id,
            current_source_fingerprint=action.source_state_fingerprint,
        )


def test_apply_is_one_time_and_reject_cannot_follow(tmp_path: Path) -> None:
    clock = MutableClock(BASE_TIME)
    store = _store(tmp_path, clock=clock)
    action = _create(store)
    clock.advance(timedelta(seconds=10))

    applied = store.mark_applied(
        action.action_id,
        current_source_fingerprint=action.source_state_fingerprint,
    )

    assert applied.status is PendingActionStatus.APPLIED
    assert applied.applied_at == clock.value
    assert applied.payload == action.payload
    with pytest.raises(PendingActionStateError):
        store.mark_applied(
            action.action_id,
            current_source_fingerprint=action.source_state_fingerprint,
        )
    with pytest.raises(PendingActionStateError):
        store.reject(action.action_id)


def test_reject_is_one_time_and_apply_cannot_follow(tmp_path: Path) -> None:
    store = _store(tmp_path)
    action = _create(store)

    rejected = store.reject(action.action_id, reason="I do not want this change.")

    assert rejected.status is PendingActionStatus.REJECTED
    assert rejected.rejected_at == BASE_TIME
    with pytest.raises(PendingActionStateError):
        store.reject(action.action_id)
    with pytest.raises(PendingActionStateError):
        store.mark_applied(
            action.action_id,
            current_source_fingerprint=action.source_state_fingerprint,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"value": float("nan")},
        {"value": float("inf")},
        {"value": datetime(2026, 7, 31, tzinfo=timezone.utc)},
        {"value": (1, 2)},
        {"value": 9_007_199_254_740_992},
        {1: "non-string key"},
    ],
)
def test_unsafe_or_lossy_json_payloads_are_rejected(
    tmp_path: Path,
    payload: dict[Any, Any],
) -> None:
    store = _store(tmp_path)

    with pytest.raises(PendingActionValidationError):
        _create(store, payload=payload)

    assert not store.path.exists()


def test_workspace_mismatch_and_payload_tampering_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    action = _create(store)

    wrong_workspace = PendingFinancialActionStore(
        store.path,
        workspace_id="workspace-demo",
    )
    with pytest.raises(PendingActionStoreCorruptionError):
        wrong_workspace.get(action.action_id)

    raw = json.loads(store.path.read_text(encoding="utf-8"))
    raw["actions"][0]["payload"]["patch"]["investment_policy"]["risk_tolerance"] = "aggressive"
    store.path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(
        PendingActionStoreCorruptionError,
        match="Payload checksum mismatch",
    ):
        store.get(action.action_id)


def test_failed_atomic_replace_preserves_existing_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _store(
        tmp_path,
        action_ids=["pfa_first", "pfa_second"],
    )
    first = _create(store)
    before = store.path.read_bytes()

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(copilot_pending_actions.os, "replace", fail_replace)
    with pytest.raises(PendingActionError, match="atomically write"):
        _create(store, conversation_id="conversation-2")

    assert store.path.read_bytes() == before
    assert json.loads(before)["actions"][0]["action_id"] == first.action_id
    assert not list(store.path.parent.glob("*.tmp"))


def test_create_validates_expiry_and_required_identity(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(PendingActionValidationError, match="later than created_at"):
        _create(store, expires_at=BASE_TIME)
    with pytest.raises(PendingActionValidationError, match="conversation_id"):
        _create(store, conversation_id=" ")
    with pytest.raises(PendingActionValidationError, match="impact_level"):
        _create(store, impact_level="advisory")

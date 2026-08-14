from __future__ import annotations

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.copilot_pending_actions import PendingActionError
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory


@pytest.fixture()
def isolated_workspace_services(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Bind both direct Copilot tools and HTTP routes to one isolated workspace."""

    test_settings = copy(main.settings)
    test_settings.auth_mode = "dev"
    test_settings.auth_dev_email = "pending-action-owner@example.test"
    test_settings.auth_oidc_client_id = ""
    test_settings.auth_oidc_client_secret = ""
    test_settings.auth_oidc_issuer_url = ""
    test_settings.control_db_path = tmp_path / "control" / "control.db"
    test_settings.workspace_root_dir = tmp_path / "workspaces"
    test_settings.secret_key_path = tmp_path / "control" / "local_secret.key"

    control_plane = ControlPlaneStore(test_settings.control_db_path)
    control_plane.bootstrap_default_household(
        owner_email=test_settings.auth_dev_email,
        default_storage_root=tmp_path / "household",
        demo_storage_root=tmp_path / "demo",
    )
    factory = WorkspaceServiceFactory(
        settings=test_settings,
        control_plane=control_plane,
    )

    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(main, "control_plane_store", control_plane)
    monkeypatch.setattr(main, "workspace_service_factory", factory)
    monkeypatch.setattr(main, "_queue_autogit_event", lambda _event: None)

    services = main.default_workspace_services()
    main.app.dependency_overrides[main.get_workspace_services] = lambda: services
    workspace_token = main.current_copilot_workspace_services.set(services)
    try:
        yield services
    finally:
        main.current_copilot_workspace_services.reset(workspace_token)
        main.app.dependency_overrides.pop(main.get_workspace_services, None)


def _draft_profile_action(
    *,
    conversation_id: str,
    turn_id: str,
    patch: dict[str, object],
) -> dict[str, object]:
    conversation_token = main.current_copilot_conversation_id.set(conversation_id)
    turn_token = main.current_copilot_turn_id.set(turn_id)
    try:
        return asyncio.run(main.tool_draft_financial_profile_update(patch))
    finally:
        main.current_copilot_turn_id.reset(turn_token)
        main.current_copilot_conversation_id.reset(conversation_token)


def _salary_patch(monthly_amount_usd: float) -> dict[str, object]:
    return {
        "income_items": [
            {
                "id": "income-salary",
                "label": "Salary",
                "monthly_amount_usd": monthly_amount_usd,
                "source_type": "salary",
            }
        ]
    }


def test_profile_draft_is_inert_and_explicit_apply_writes_once(
    isolated_workspace_services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = isolated_workspace_services
    profile_before = services.financial_profile_store.get()

    draft = _draft_profile_action(
        conversation_id="conversation-apply",
        turn_id="turn-apply",
        patch=_salary_patch(12_500),
    )

    assert services.financial_profile_store.get() == profile_before
    assert draft["requires_confirmation"] is True
    action_snapshot = draft["pending_action"]
    assert isinstance(action_snapshot, dict)
    assert action_snapshot["status"] == "pending"
    assert action_snapshot["conversation_id"] == "conversation-apply"
    assert action_snapshot["turn_id"] == "turn-apply"
    assert action_snapshot["tool_name"] == "draft_financial_profile_update"
    assert "payload" not in action_snapshot

    save_calls: list[dict[str, object]] = []
    original_save = services.financial_profile_store.save

    def counted_save(payload, **kwargs):
        save_calls.append(dict(payload))
        return original_save(payload, **kwargs)

    monkeypatch.setattr(services.financial_profile_store, "save", counted_save)

    action_id = str(action_snapshot["action_id"])
    with TestClient(main.app) as client:
        detail = client.get(f"/api/copilot/pending-actions/{action_id}")
        applied = client.post(f"/api/copilot/pending-actions/{action_id}/apply")
        replay = client.post(f"/api/copilot/pending-actions/{action_id}/apply")

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["action_id"] == action_id
    assert detail_payload["status"] == "pending"
    assert detail_payload["payload"]["kind"] == "financial_profile_update"
    assert detail_payload["payload"]["patch_payload"] == _salary_patch(12_500)

    assert applied.status_code == 200
    assert applied.json()["action"]["status"] == "applied"
    assert applied.json()["result"]["already_applied"] is False
    assert applied.json()["result"]["profile"]["income_items"][0]["monthly_amount_usd"] == 12_500
    assert len(save_calls) == 1

    assert replay.status_code == 200
    assert replay.json()["action"]["status"] == "applied"
    assert replay.json()["result"]["already_applied"] is True
    assert replay.json()["result"]["profile"]["income_items"][0]["monthly_amount_usd"] == 12_500
    assert len(save_calls) == 1


def test_concurrent_apply_requests_serialize_the_domain_write(
    isolated_workspace_services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = isolated_workspace_services
    draft = _draft_profile_action(
        conversation_id="conversation-concurrent",
        turn_id="turn-concurrent",
        patch=_salary_patch(11_250),
    )
    action_id = str(draft["pending_action"]["action_id"])

    save_count = 0
    count_lock = threading.Lock()
    original_save = services.financial_profile_store.save

    def slow_counted_save(payload, **kwargs):
        nonlocal save_count
        with count_lock:
            save_count += 1
        time.sleep(0.05)
        return original_save(payload, **kwargs)

    monkeypatch.setattr(
        services.financial_profile_store,
        "save",
        slow_counted_save,
    )

    with TestClient(main.app) as client:
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(
                executor.map(
                    lambda _index: client.post(
                        f"/api/copilot/pending-actions/{action_id}/apply"
                    ),
                    range(2),
                )
            )

    assert [response.status_code for response in responses] == [200, 200]
    assert sorted(
        response.json()["result"]["already_applied"] for response in responses
    ) == [False, True]
    assert save_count == 1
    assert services.financial_profile_store.get()["income_items"][0][
        "monthly_amount_usd"
    ] == 11_250


def test_failed_lifecycle_commit_restores_profile_and_emits_no_success_side_effects(
    isolated_workspace_services,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    services = isolated_workspace_services
    profile_before = services.financial_profile_store.get()
    draft = _draft_profile_action(
        conversation_id="conversation-rollback",
        turn_id="turn-rollback",
        patch=_salary_patch(10_750),
    )
    action_id = str(draft["pending_action"]["action_id"])
    store = main.pending_financial_action_store(services)
    activity_calls: list[dict[str, object]] = []
    autogit_calls: list[str] = []

    def fail_mark_applied(*_args, **_kwargs):
        raise PendingActionError("simulated lifecycle commit failure")

    monkeypatch.setattr(main, "pending_financial_action_store", lambda _services: store)
    monkeypatch.setattr(store, "mark_applied", fail_mark_applied)
    monkeypatch.setattr(
        main,
        "_record_profile_update_activity",
        lambda **kwargs: activity_calls.append(kwargs),
    )
    monkeypatch.setattr(main, "_queue_autogit_event", autogit_calls.append)

    with TestClient(main.app) as client:
        response = client.post(
            f"/api/copilot/pending-actions/{action_id}/apply"
        )

    assert response.status_code == 500
    assert response.json()["detail"] == "Pending action storage failed."
    assert services.financial_profile_store.get() == profile_before
    assert store.get(action_id).status is main.PendingActionStatus.PENDING
    assert activity_calls == []
    assert autogit_calls == []


def test_rejected_profile_action_cannot_be_applied(
    isolated_workspace_services,
) -> None:
    services = isolated_workspace_services
    profile_before = services.financial_profile_store.get()
    draft = _draft_profile_action(
        conversation_id="conversation-reject",
        turn_id="turn-reject",
        patch=_salary_patch(9_500),
    )
    action_id = str(draft["pending_action"]["action_id"])

    with TestClient(main.app) as client:
        rejected = client.post(
            f"/api/copilot/pending-actions/{action_id}/reject",
            json={"reason": "Keep the current profile."},
        )
        blocked_apply = client.post(
            f"/api/copilot/pending-actions/{action_id}/apply"
        )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["status_reason"] == "Keep the current profile."
    assert blocked_apply.status_code == 409
    assert blocked_apply.json()["detail"]["action"]["status"] == "rejected"
    assert services.financial_profile_store.get() == profile_before


def test_stale_profile_action_returns_conflict_without_overwriting_new_state(
    isolated_workspace_services,
) -> None:
    services = isolated_workspace_services
    draft = _draft_profile_action(
        conversation_id="conversation-stale",
        turn_id="turn-stale",
        patch=_salary_patch(8_000),
    )
    action_id = str(draft["pending_action"]["action_id"])

    externally_updated = services.financial_profile_store.save(
        {"notes": "Changed in the Profile editor after the Copilot draft."},
        metadata_source="profile_editor",
    )

    with TestClient(main.app) as client:
        stale_apply = client.post(
            f"/api/copilot/pending-actions/{action_id}/apply"
        )
        detail = client.get(f"/api/copilot/pending-actions/{action_id}")

    assert stale_apply.status_code == 409
    conflict = stale_apply.json()["detail"]
    assert conflict["action"]["status"] == "stale"
    assert "underlying financial state changed" in (
        conflict["action"]["status_reason"].lower()
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "stale"
    assert services.financial_profile_store.get() == externally_updated
    assert services.financial_profile_store.get()["income_items"] == []


def test_model_tool_policy_cannot_reach_pending_action_apply_or_profile_write(
    isolated_workspace_services,
) -> None:
    selection = main.resolve_model_tools(
        main.copilot_tool_metadata.values(),
        main.ToolSelectionContext(
            mode=main.InteractionMode.REVIEW,
            intent_domains=frozenset({"profile"}),
            primary_domains=frozenset({"profile"}),
        ),
        main.ProviderCapabilities(provider_id="test"),
    )

    assert "draft_financial_profile_update" in selection.names
    assert "update_financial_profile" not in selection.names
    assert selection.excluded["update_financial_profile"] == (
        "final write/apply tools are never model-exposed"
    )
    assert "apply_copilot_pending_action" not in main.copilot.tools

    definitions = main.copilot._tool_definitions(selection.names)
    exposed_names = {
        definition["function"]["name"]
        for definition in definitions
    }
    assert "draft_financial_profile_update" in exposed_names
    assert "update_financial_profile" not in exposed_names
    assert "apply_copilot_pending_action" not in exposed_names

    result, error = asyncio.run(
        main.copilot._execute_tool(
            "update_financial_profile",
            _salary_patch(99_999),
            allowed_tool_names=selection.names,
        )
    )
    assert result == {}
    assert error == "Tool is not available for this turn: update_financial_profile"
    assert isolated_workspace_services.financial_profile_store.get()["income_items"] == []

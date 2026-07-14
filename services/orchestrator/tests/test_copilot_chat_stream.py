from __future__ import annotations

import json
from copy import copy
from pathlib import Path

from fastapi.testclient import TestClient

from buildwealth_orchestrator import main
from buildwealth_orchestrator.services.control_plane import ControlPlaneStore
from buildwealth_orchestrator.services.workspace_services import WorkspaceServiceFactory


def _install_temp_workspace_spine(monkeypatch, tmp_path: Path) -> None:
    test_settings = copy(main.settings)
    test_settings.auth_mode = "dev"
    test_settings.auth_dev_email = "owner@example.test"
    test_settings.auth_oidc_client_id = ""
    test_settings.auth_oidc_client_secret = ""
    test_settings.auth_oidc_issuer_url = ""
    test_settings.auth_oidc_logout_url = ""
    test_settings.auth_post_logout_redirect_uri = ""
    test_settings.control_db_path = tmp_path / "control" / "control.db"
    test_settings.workspace_root_dir = tmp_path / "workspaces"
    test_settings.secret_key_path = tmp_path / "control" / "local_secret.key"

    control_plane = ControlPlaneStore(test_settings.control_db_path)
    control_plane.bootstrap_default_household(
        owner_email=test_settings.auth_dev_email,
        default_storage_root=tmp_path / "real",
        demo_storage_root=tmp_path / "demo",
    )
    factory = WorkspaceServiceFactory(settings=test_settings, control_plane=control_plane)

    monkeypatch.setattr(main, "settings", test_settings)
    monkeypatch.setattr(main, "control_plane_store", control_plane)
    monkeypatch.setattr(main, "workspace_service_factory", factory)
    main.auth_rate_limiter.reset_all()


def _sse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


class StreamingFakeCopilot:
    async def chat(
        self,
        *,
        question,
        conversation_id=None,
        conversation=None,
        turn=None,
        contextual_brief=None,
        context_trace=None,
        conversation_store=None,
        llm_client=None,
        progress_cb=None,
    ):
        assert conversation_store is not None
        if conversation is None:
            conversation = conversation_store.get_or_create(conversation_id, question)
        if turn is None:
            turn = conversation_store.start_turn(conversation, question)
        if progress_cb is not None:
            progress_cb({"type": "round", "round": 1})
            progress_cb({"type": "tool", "name": "get_financial_profile", "status": "start"})
            progress_cb({"type": "tool", "name": "get_financial_profile", "status": "done"})
            progress_cb({"type": "answer_delta", "text": "Streamed "})
            progress_cb({"type": "answer_delta", "text": "answer."})
        answer = "Streamed answer."
        assistant_message = conversation_store.append_message(
            conversation,
            "assistant",
            answer,
            metadata={"context_trace": context_trace or {}},
            turn_id=turn["id"],
        )
        conversation_store.set_turn_status(
            conversation,
            turn["id"],
            "completed",
            assistant_message_id=assistant_message["id"],
        )
        conversation_store.save(conversation)
        return {
            "conversation_id": conversation["id"],
            "turn_id": turn["id"],
            "user_message_id": turn["user_message_id"],
            "assistant_message_id": assistant_message["id"],
            "turn_status": "completed",
            "answer": answer,
            "tool_calls": [],
            "model": "test-copilot",
            "context_trace": context_trace or {},
            "created_at": main.utc_now(),
        }


async def _fake_assemble(**kwargs):
    return {"trace": {}, "question": kwargs.get("question")}


def test_copilot_chat_stream_emits_progress_then_result(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "assemble_copilot_context_payload", _fake_assemble)
    monkeypatch.setattr(main, "copilot", StreamingFakeCopilot())

    with TestClient(main.app) as client:
        response = client.post(
            "/api/copilot/chat/stream",
            json={"question": "What changed this week?"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _sse_events(response.text)
        types = [event["type"] for event in events]
        assert types[0] == "turn"
        assert "stage" in types
        assert "tool" in types
        assert "answer_delta" in types
        assert types[-1] == "result"

        result = events[-1]["data"]
        assert result["answer"] == "Streamed answer."
        assert result["conversation_id"]

        deltas = "".join(e["text"] for e in events if e["type"] == "answer_delta")
        assert deltas == "Streamed answer."


def test_copilot_chat_stream_reports_errors_as_events(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)

    async def failing_assemble(**kwargs):
        raise RuntimeError("context assembly exploded")

    monkeypatch.setattr(main, "assemble_copilot_context_payload", failing_assemble)
    monkeypatch.setattr(main, "copilot", StreamingFakeCopilot())

    with TestClient(main.app) as client:
        response = client.post(
            "/api/copilot/chat/stream",
            json={"question": "boom"},
        )
        assert response.status_code == 200
        events = _sse_events(response.text)
        assert events[-1]["type"] == "error"
        assert events[-1]["status"] == 500
        assert "context assembly exploded" in events[-1]["detail"]
        conversations = client.get("/api/copilot/conversations").json()
        assert len(conversations) == 1
        failed = client.get(f"/api/copilot/conversations/{conversations[0]['id']}").json()
        assert failed["turns"][-1]["status"] == "failed"
        assert "context assembly exploded" in failed["turns"][-1]["error"]


def test_copilot_conversation_can_be_renamed_archived_and_restored(monkeypatch, tmp_path: Path) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "assemble_copilot_context_payload", _fake_assemble)
    monkeypatch.setattr(main, "copilot", StreamingFakeCopilot())

    with TestClient(main.app) as client:
        streamed = client.post(
            "/api/copilot/chat/stream",
            json={"question": "Should I increase my contribution?"},
        )
        conversation_id = _sse_events(streamed.text)[-1]["data"]["conversation_id"]

        renamed = client.patch(
            f"/api/copilot/conversations/{conversation_id}",
            json={"title": "Retirement contribution decision"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Retirement contribution decision"

        archived = client.patch(
            f"/api/copilot/conversations/{conversation_id}",
            json={"archived": True},
        )
        assert archived.status_code == 200
        assert archived.json()["archived_at"]
        assert client.get("/api/copilot/conversations").json() == []
        archived_list = client.get(
            "/api/copilot/conversations?include_archived=true",
        ).json()
        assert archived_list[0]["id"] == conversation_id

        restored = client.patch(
            f"/api/copilot/conversations/{conversation_id}",
            json={"archived": False},
        )
        assert restored.status_code == 200
        assert restored.json()["archived_at"] is None
        assert client.get("/api/copilot/conversations").json()[0]["id"] == conversation_id


def test_copilot_chat_stream_works_with_legacy_fake_signature(monkeypatch, tmp_path: Path) -> None:
    """A copilot whose chat() lacks progress_cb still completes the stream."""
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "assemble_copilot_context_payload", _fake_assemble)

    class LegacyFake:
        async def chat(
            self,
            *,
            question,
            conversation_id=None,
            conversation=None,
            contextual_brief=None,
            context_trace=None,
            conversation_store=None,
            llm_client=None,
        ):
            if conversation is None:
                conversation = conversation_store.get_or_create(conversation_id, question)
            conversation_store.append_message(conversation, "user", question)
            conversation_store.append_message(conversation, "assistant", "legacy answer")
            conversation_store.save(conversation)
            return {
                "conversation_id": conversation["id"],
                "answer": "legacy answer",
                "tool_calls": [],
                "model": "legacy",
                "context_trace": {},
                "created_at": main.utc_now(),
            }

    monkeypatch.setattr(main, "copilot", LegacyFake())

    with TestClient(main.app) as client:
        response = client.post("/api/copilot/chat/stream", json={"question": "hi"})
        assert response.status_code == 200
        events = _sse_events(response.text)
        assert events[-1]["type"] == "result"
        assert events[-1]["data"]["answer"] == "legacy answer"

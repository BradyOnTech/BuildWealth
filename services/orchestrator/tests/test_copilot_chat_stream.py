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


class ContextCapturingCopilot(StreamingFakeCopilot):
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.system_prompt = main.copilot.system_prompt

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
        system_prompt=None,
        allowed_tool_names=None,
    ):
        self.calls.append(
            {
                "contextual_brief": contextual_brief,
                "context_trace": context_trace,
                "system_prompt": system_prompt,
                "allowed_tool_names": tuple(allowed_tool_names or ()),
            }
        )
        return await super().chat(
            question=question,
            conversation_id=conversation_id,
            conversation=conversation,
            turn=turn,
            contextual_brief=contextual_brief,
            context_trace=context_trace,
            conversation_store=conversation_store,
            llm_client=llm_client,
            progress_cb=progress_cb,
        )


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
        assert "financial data was not changed" in events[-1]["detail"]
        assert "context assembly exploded" not in events[-1]["detail"]
        conversations = client.get("/api/copilot/conversations").json()
        assert len(conversations) == 1
        failed = client.get(f"/api/copilot/conversations/{conversations[0]['id']}").json()
        assert failed["turns"][-1]["status"] == "failed"
        assert "financial data was not changed" in failed["turns"][-1]["error"]
        assert "context assembly exploded" not in failed["turns"][-1]["error"]


def test_explicit_context_references_are_scoped_visible_and_tool_relevant(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    services = main.default_workspace_services()
    plan = services.plan_workspace.create_plan(
        "Retirement decision",
        "Compare a contribution change.",
    )
    recommendation = services.recommendation_inbox.create(
        title="Review contribution increase",
        detail="Consider increasing the monthly contribution after review.",
        plan_id=plan["id"],
    )
    capturing = ContextCapturingCopilot()
    monkeypatch.setattr(main, "assemble_copilot_context_payload", _fake_assemble)
    monkeypatch.setattr(main, "copilot", capturing)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/copilot/chat/stream",
            json={
                "question": "Explain these exact items.",
                "context_references": [
                    {"type": "plan", "id": plan["id"]},
                    {"type": "recommendation", "id": recommendation["id"]},
                ],
            },
        )
        assert response.status_code == 200
        events = _sse_events(response.text)
        assert events[-1]["type"] == "result", events
        result = events[-1]["data"]
        conversation = client.get(
            f"/api/copilot/conversations/{result['conversation_id']}"
        ).json()

    assert len(capturing.calls) == 1
    call = capturing.calls[0]
    assert "BEGIN_UNTRUSTED_EXPLICIT_CONTEXT_JSON" in call["contextual_brief"]
    assert plan["id"] in call["contextual_brief"]
    assert recommendation["id"] in call["contextual_brief"]
    assert "get_plan_review_context" in call["allowed_tool_names"]
    assert "list_recommendations" in call["allowed_tool_names"]
    assert "update_plan_settings" not in call["allowed_tool_names"]
    assert "apply_recommendation" not in call["allowed_tool_names"]

    trace = result["context_trace"]["explicit_context_references"]
    assert trace["count"] == 2
    assert "evidence" not in trace["references"][0]
    user_message = next(
        message for message in conversation["messages"] if message["role"] == "user"
    )
    assert [item["type"] for item in user_message["metadata"]["context_references"]] == [
        "plan",
        "recommendation",
    ]
    assert user_message["metadata"]["context_references"][0]["label"] == (
        "Retirement decision"
    )


def test_unresolvable_context_reference_fails_before_creating_a_turn(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_temp_workspace_spine(monkeypatch, tmp_path)
    monkeypatch.setattr(main, "assemble_copilot_context_payload", _fake_assemble)
    monkeypatch.setattr(main, "copilot", ContextCapturingCopilot())

    with TestClient(main.app) as client:
        response = client.post(
            "/api/copilot/chat",
            json={
                "question": "Explain this.",
                "context_references": [
                    {"type": "recommendation", "id": "rec-does-not-exist"},
                ],
            },
        )
        conversations = client.get("/api/copilot/conversations").json()

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "reference_not_found"
    assert "rec-does-not-exist" in response.json()["detail"]["id"]
    assert conversations == []


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

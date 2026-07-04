from __future__ import annotations

import json

from buildwealth_orchestrator import maintenance


def test_maintenance_cli_runs_due_deletion_purge(monkeypatch, capsys) -> None:
    calls: list[dict[str, object]] = []

    def fake_purge_due_account_data_deletions(*, due_at: str | None = None, limit: int = 20):
        calls.append({"due_at": due_at, "limit": limit})
        return {
            "ok": True,
            "request_count": 1,
            "items": [{"request_id": "del_123", "status": "completed"}],
        }

    monkeypatch.setattr(
        maintenance.app_main,
        "purge_due_account_data_deletions",
        fake_purge_due_account_data_deletions,
    )

    exit_code = maintenance.main(
        [
            "purge-due-account-data-deletions",
            "--due-at",
            "2026-06-13T12:00:00Z",
            "--limit",
            "5",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert calls == [{"due_at": "2026-06-13T12:00:00Z", "limit": 5}]
    assert payload["ok"] is True
    assert payload["items"][0]["status"] == "completed"


def test_maintenance_cli_returns_failure_when_purge_fails(monkeypatch, capsys) -> None:
    def fake_purge_due_account_data_deletions(*, due_at: str | None = None, limit: int = 20):
        return {
            "ok": False,
            "request_count": 1,
            "items": [{"request_id": "del_123", "status": "failed"}],
        }

    monkeypatch.setattr(
        maintenance.app_main,
        "purge_due_account_data_deletions",
        fake_purge_due_account_data_deletions,
    )

    exit_code = maintenance.main(["purge-due-account-data-deletions"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["items"][0]["status"] == "failed"

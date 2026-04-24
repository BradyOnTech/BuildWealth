from __future__ import annotations

import json
from pathlib import Path

from buildwealth_orchestrator.services.git_integration_settings import GitIntegrationSettingsStore


def test_git_integration_settings_defaults_to_local_only_disabled_policy(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings" / "git_integration.json"
    workspace_dir = tmp_path / "versioned"

    store = GitIntegrationSettingsStore(
        settings_path,
        default_workspace_dir=workspace_dir,
    )

    settings = store.load()

    assert settings["enabled"] is False
    assert settings["autogit_enabled"] is False
    assert settings["auto_push_enabled"] is False
    assert settings["include_plans"] is True
    assert settings["include_recommendations"] is True
    assert settings["include_review_packets"] is True
    assert settings["include_snapshot_checkpoints"] is True
    assert settings["include_financial_profile"] is False
    assert settings["workspace_dir"] == str(workspace_dir)
    assert settings_path.exists()


def test_git_integration_settings_sanitizes_and_persists_supported_updates(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings" / "git_integration.json"
    store = GitIntegrationSettingsStore(settings_path)

    saved = store.save(
        {
            "enabled": "true",
            "autogit_enabled": "yes",
            "auto_push_enabled": "no",
            "include_financial_profile": True,
            "auto_checkpoint_idle_seconds": 5,
            "remote_name": "",
            "unsupported": "ignored",
        }
    )

    persisted = json.loads(settings_path.read_text(encoding="utf-8"))

    assert saved["enabled"] is True
    assert saved["autogit_enabled"] is True
    assert saved["auto_push_enabled"] is False
    assert saved["include_financial_profile"] is True
    assert saved["auto_checkpoint_idle_seconds"] == 30
    assert saved["remote_name"] == "origin"
    assert "unsupported" not in saved
    assert "unsupported" not in persisted
    assert persisted["enabled"] is True

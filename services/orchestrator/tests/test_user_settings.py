from pathlib import Path

from buildwealth_orchestrator.services.user_settings import MASKED_PLACEHOLDER, UserSettingsStore


def test_user_settings_filters_legacy_bridge_keys(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings" / "user_settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        (
            "{"
            '"openai_api_key":"sk-test-1234",'
            '"openai_model":"gpt-5.5",'
            '"openai_base_url":"https://api.openai.com/v1",'
            '"ghostfolio_api_base":"http://localhost:3333/api",'
            '"ghostfolio_security_token":"legacy-token",'
            '"updated_at":"2026-04-14T12:00:00+00:00"'
            "}"
        ),
        encoding="utf-8",
    )

    store = UserSettingsStore(settings_path)
    raw = store.load_raw()
    masked = store.load_masked()

    assert "ghostfolio_api_base" not in raw
    assert "ghostfolio_security_token" not in raw
    assert "ghostfolio_api_base" not in masked
    assert "ghostfolio_security_token" not in masked
    assert masked["openai_api_key"] == f"{MASKED_PLACEHOLDER}1234"


def test_user_settings_save_ignores_unknown_keys_and_preserves_masked_secret(tmp_path: Path) -> None:
    store = UserSettingsStore(tmp_path / "settings" / "user_settings.json")
    saved = store.save(
        {
            "openai_api_key": "sk-live-9876",
            "openai_model": "gpt-5.4-mini",
            "ghostfolio_api_base": "http://localhost:3333/api",
        }
    )
    assert "ghostfolio_api_base" not in saved
    assert saved["openai_api_key"] == "sk-live-9876"

    saved = store.save({"openai_api_key": f"{MASKED_PLACEHOLDER}9876"})
    assert saved["openai_api_key"] == "sk-live-9876"

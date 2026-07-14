from __future__ import annotations

import atexit
import os
from pathlib import Path
import shutil
import tempfile

import pytest


_TEST_DATA_ROOT = Path(tempfile.mkdtemp(prefix="buildwealth-orchestrator-tests-"))

_PATH_OVERRIDES: dict[str, Path] = {
    "SNAPSHOT_DIR": _TEST_DATA_ROOT / "snapshots",
    "DURABLE_STORAGE_DIR": _TEST_DATA_ROOT / "storage",
    "BACKUP_ARCHIVE_DIR": _TEST_DATA_ROOT / "backups",
    "PROTECTION_POLICY_PATH": _TEST_DATA_ROOT / "security" / "protection_policy.json",
    "PORTFOLIO_REVIEW_PACKET_DIR": _TEST_DATA_ROOT / "reports" / "portfolio_review_packets",
    "IMPORT_INBOX_DIR": _TEST_DATA_ROOT / "imports" / "inbox",
    "IMPORT_ARCHIVE_DIR": _TEST_DATA_ROOT / "imports" / "archive",
    "IMPORT_WORKBENCH_DIR": _TEST_DATA_ROOT / "imports" / "workbench",
    "IMPORT_REPORTS_DIR": _TEST_DATA_ROOT / "imports" / "reports",
    "CONVERSATION_DIR": _TEST_DATA_ROOT / "conversations",
    "PLANS_DIR": _TEST_DATA_ROOT / "plans",
    "VERSIONED_WORKSPACE_DIR": _TEST_DATA_ROOT / "versioned",
    "GIT_INTEGRATION_SETTINGS_PATH": _TEST_DATA_ROOT / "settings" / "git_integration.json",
    "FINANCIAL_PROFILE_PATH": _TEST_DATA_ROOT / "profile" / "financial_profile.json",
    "RECOMMENDATIONS_PATH": _TEST_DATA_ROOT / "recommendations" / "inbox.json",
    "TODAY_REVIEW_CHECKPOINT_PATH": _TEST_DATA_ROOT / "today" / "review_checkpoint.json",
}


def _initialize_test_paths() -> None:
    for key, path in _PATH_OVERRIDES.items():
        os.environ[key] = str(path)
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)


def _clear_settings_cache() -> None:
    # Ensure settings are reloaded from test-only env paths.
    from buildwealth_orchestrator.settings import get_settings

    get_settings.cache_clear()


def _cleanup_test_data_root() -> None:
    shutil.rmtree(_TEST_DATA_ROOT, ignore_errors=True)


_initialize_test_paths()
_clear_settings_cache()
atexit.register(_cleanup_test_data_root)


class _WorkspacePathsProxy:
    """Expose legacy test path monkeypatches as one workspace path contract."""

    def __init__(self, main_module) -> None:
        self._main = main_module

    @property
    def root(self) -> Path:
        return Path(self._main.settings.versioned_workspace_dir).parent

    @property
    def profile_path(self) -> Path:
        return Path(self._main.settings.financial_profile_path)

    @property
    def portfolio_dir(self) -> Path:
        return Path(self._main.settings.snapshot_dir).parent / "portfolio"

    @property
    def snapshot_dir(self) -> Path:
        return Path(self._main.settings.snapshot_dir)

    @property
    def plans_dir(self) -> Path:
        return Path(self._main.settings.plans_dir)

    @property
    def recommendations_path(self) -> Path:
        return Path(self._main.settings.recommendations_path)

    @property
    def conversation_dir(self) -> Path:
        return Path(self._main.settings.conversation_dir)

    @property
    def durable_storage_dir(self) -> Path:
        return Path(self._main.settings.durable_storage_dir)

    @property
    def backup_archive_dir(self) -> Path:
        return Path(self._main.settings.backup_archive_dir)

    @property
    def import_inbox_dir(self) -> Path:
        return Path(self._main.settings.import_inbox_dir)

    @property
    def import_archive_dir(self) -> Path:
        return Path(self._main.settings.import_archive_dir)

    @property
    def import_workbench_dir(self) -> Path:
        return Path(self._main.settings.import_workbench_dir)

    @property
    def import_reports_dir(self) -> Path:
        return Path(self._main.settings.import_reports_dir)

    @property
    def portfolio_review_packet_dir(self) -> Path:
        return Path(self._main.settings.portfolio_review_packet_dir)

    @property
    def today_review_checkpoint_path(self) -> Path:
        return Path(self._main.settings.today_review_checkpoint_path)

    @property
    def protection_policy_path(self) -> Path:
        return Path(self._main.settings.protection_policy_path)

    @property
    def settings_path(self) -> Path:
        return self.root / "settings" / "workspace_settings.json"

    @property
    def secrets_path(self) -> Path:
        return self.root / "settings" / "workspace_secrets.json"


class _WorkspaceServicesProxy:
    """Bind old unit-test monkeypatches to the explicit workspace contract.

    Production code no longer falls back to module-level Canonical State.
    Existing focused tests still patch those stores, so the test harness binds
    them as an explicit service graph while the migration finishes.
    """

    _STORE_NAMES = {
        "financial_profile_store",
        "portfolio_store",
        "asset_registry",
        "snapshot_store",
        "plan_workspace",
        "recommendation_inbox",
        "conversation_store",
        "context_intelligence_service",
        "import_workbench_store",
        "portfolio_review_packet_store",
        "today_review_checkpoint_store",
    }

    def __init__(self, main_module, fallback) -> None:
        self._main = main_module
        self._fallback = fallback
        self.paths = _WorkspacePathsProxy(main_module)
        self.context = fallback.context
        self.record = fallback.record

    def __getattr__(self, name: str):
        if name in self._STORE_NAMES:
            return getattr(self._main, name)
        if name == "context_assembler":
            return self._main.context_assembler
        if name == "settings_store":
            return self._main.user_settings_store
        return getattr(self._fallback, name)


_FALLBACK_WORKSPACE_SERVICES = None


@pytest.fixture(autouse=True)
def _bind_explicit_test_workspace_services():
    """Give direct handler/tool calls the same explicit workspace boundary as HTTP."""
    global _FALLBACK_WORKSPACE_SERVICES

    import buildwealth_orchestrator.main as main

    if _FALLBACK_WORKSPACE_SERVICES is None:
        _FALLBACK_WORKSPACE_SERVICES = main.default_workspace_services()
    proxy = _WorkspaceServicesProxy(main, _FALLBACK_WORKSPACE_SERVICES)
    token = main.current_copilot_workspace_services.set(proxy)
    try:
        yield proxy
    finally:
        main.current_copilot_workspace_services.reset(token)

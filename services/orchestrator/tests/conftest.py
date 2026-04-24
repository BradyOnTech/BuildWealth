from __future__ import annotations

import atexit
import os
from pathlib import Path
import shutil
import tempfile


_TEST_DATA_ROOT = Path(tempfile.mkdtemp(prefix="buildwealth-orchestrator-tests-"))

_PATH_OVERRIDES: dict[str, Path] = {
    "SNAPSHOT_DIR": _TEST_DATA_ROOT / "snapshots",
    "DURABLE_STORAGE_DIR": _TEST_DATA_ROOT / "storage",
    "BACKUP_ARCHIVE_DIR": _TEST_DATA_ROOT / "backups",
    "PROTECTION_POLICY_PATH": _TEST_DATA_ROOT / "security" / "protection_policy.json",
    "IGNIDASH_EXPORT_DIR": _TEST_DATA_ROOT / "ignidash",
    "PORTFOLIO_REVIEW_PACKET_DIR": _TEST_DATA_ROOT / "reports" / "portfolio_review_packets",
    "IMPORT_INBOX_DIR": _TEST_DATA_ROOT / "imports" / "inbox",
    "IMPORT_ARCHIVE_DIR": _TEST_DATA_ROOT / "imports" / "archive",
    "CONVERSATION_DIR": _TEST_DATA_ROOT / "conversations",
    "PLANS_DIR": _TEST_DATA_ROOT / "plans",
    "VERSIONED_WORKSPACE_DIR": _TEST_DATA_ROOT / "versioned",
    "GIT_INTEGRATION_SETTINGS_PATH": _TEST_DATA_ROOT / "settings" / "git_integration.json",
    "FINANCIAL_PROFILE_PATH": _TEST_DATA_ROOT / "profile" / "financial_profile.json",
    "RECOMMENDATIONS_PATH": _TEST_DATA_ROOT / "recommendations" / "inbox.json",
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

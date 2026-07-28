from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.backup_restore import BackupRestoreService
from buildwealth_orchestrator.services.onboarding_progress import OnboardingProgressStore
from buildwealth_orchestrator.services.store_locks import locked_store


ONBOARDING_RESET_CONFIRMATION_PHRASE = "reset and register again"


class OnboardingResetError(RuntimeError):
    pass


class OnboardingResetService:
    """Reset one workspace's live data while preserving its owner identity.

    The control-plane user, organization, membership, workspace record, and
    active session live outside the workspace root. This service only clears
    workspace-scoped files after creating a recovery archive.
    """

    def __init__(self, *, data_root: Path, backup_dir: Path):
        self.data_root = data_root.resolve()
        self.backup_dir = backup_dir.resolve()
        self.progress_store = OnboardingProgressStore(
            self.data_root / "onboarding" / "progress.json"
        )
        self.backup_service = BackupRestoreService(
            data_root=self.data_root,
            backup_dir=self.backup_dir,
        )
        self._validate_paths()

    def preview(self) -> dict[str, Any]:
        with locked_store(self.data_root):
            live = self._live_data_stats()
            backups = self.backup_service.list_backups().get("backups") or []
        return {
            "schema_version": 1,
            "confirmation_phrase": ONBOARDING_RESET_CONFIRMATION_PHRASE,
            "file_count": live["file_count"],
            "size_bytes": live["size_bytes"],
            "existing_backup_count": len(backups),
            "will_clear": [
                "financial profile and household details",
                "portfolio, snapshots, and account history",
                "plans, recommendations, and review history",
                "Copilot conversations and imported documents",
                "workspace settings and encrypted provider secrets",
                "saved Setup progress",
            ],
            "will_preserve": [
                "your BuildWealth sign-in and email",
                "your household owner role",
                "this workspace and its access",
                "a new recovery backup of the current workspace",
            ],
        }

    def reset(self) -> dict[str, Any]:
        with locked_store(self.data_root):
            preview = self.preview()
            backup = self.backup_service.create_backup(reason="pre_onboarding_reset")
            try:
                self._clear_live_data()
                progress = self.progress_store.start()
            except Exception as exc:
                try:
                    self.backup_service.restore_backup(
                        backup_id=str(backup["backup_id"]),
                        create_pre_restore_backup=False,
                    )
                except Exception as restore_exc:
                    raise OnboardingResetError(
                        "Workspace reset failed and the recovery backup could not be restored."
                    ) from restore_exc
                raise OnboardingResetError(
                    "Workspace reset failed. The previous workspace was restored."
                ) from exc

        return {
            "ok": True,
            "message": "Workspace data reset. Your sign-in is unchanged and Setup is ready.",
            "backup_id": backup["backup_id"],
            "files_cleared": preview["file_count"],
            "bytes_cleared": preview["size_bytes"],
            "progress": progress,
            "identity_preserved": True,
            "next_path": "/v2#setup",
        }

    def _live_data_stats(self) -> dict[str, int]:
        if not self.data_root.exists():
            return {"file_count": 0, "size_bytes": 0}
        file_count = 0
        size_bytes = 0
        for path in self.data_root.rglob("*"):
            if path.is_symlink() or not path.is_file():
                continue
            resolved = path.resolve()
            if resolved.is_relative_to(self.backup_dir):
                continue
            file_count += 1
            size_bytes += path.stat().st_size
        return {"file_count": file_count, "size_bytes": size_bytes}

    def _clear_live_data(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        for child in self.data_root.iterdir():
            if child.resolve() == self.backup_dir:
                continue
            if child.is_symlink() or child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                shutil.rmtree(child)

    def _validate_paths(self) -> None:
        if self.backup_dir.parent != self.data_root:
            raise OnboardingResetError(
                "Workspace backup directory must be a direct child of the workspace root."
            )
        forbidden_exact = {
            Path("/").resolve(),
            Path.cwd().resolve(),
            Path.home().resolve(),
        }
        forbidden_parents = {
            Path("/").resolve(),
            Path("/bin").resolve(),
            Path("/boot").resolve(),
            Path("/dev").resolve(),
            Path("/etc").resolve(),
            Path("/lib").resolve(),
            Path("/lib64").resolve(),
            Path("/proc").resolve(),
            Path("/root").resolve(),
            Path("/run").resolve(),
            Path("/sbin").resolve(),
            Path("/sys").resolve(),
            Path("/tmp").resolve(),
            Path("/usr").resolve(),
            Path("/var").resolve(),
            Path("/Applications").resolve(),
            Path("/Library").resolve(),
            Path("/System").resolve(),
            Path("/private/tmp").resolve(),
            Path("/private/var").resolve(),
        }
        if (
            self.data_root in forbidden_exact
            or self.data_root.parent in forbidden_parents
            or len(self.data_root.parts) < 3
        ):
            raise OnboardingResetError(
                f"Refusing to reset unsafe workspace path: {self.data_root}"
            )

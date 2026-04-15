"""Local data-protection policy and permission hardening service."""

from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

PROTECTION_POLICY_SCHEMA_VERSION = 1
PROTECTION_STRATEGY = "filesystem_permissions_v1"
PROTECTION_LEVEL = Literal["standard", "hardened"]
VALID_PROTECTION_LEVELS: set[str] = {"standard", "hardened"}
FILE_MODE_BY_LEVEL: dict[str, int] = {
    "standard": 0o640,
    "hardened": 0o600,
}
DIR_MODE_BY_LEVEL: dict[str, int] = {
    "standard": 0o750,
    "hardened": 0o700,
}
SAMPLE_LIMIT = 8


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DataProtectionError(RuntimeError):
    pass


class DataProtectionService:
    """Manages local data-protection policy and applies permission hardening."""

    def __init__(
        self,
        *,
        policy_path: Path,
        sensitive_paths: list[Path],
        backup_dir: Path,
    ):
        self.policy_path = policy_path.resolve()
        self.sensitive_paths = tuple(path.resolve() for path in sensitive_paths)
        self.backup_dir = backup_dir.resolve()
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_policy()

    @classmethod
    def from_settings(cls, settings: Any) -> "DataProtectionService":
        data_root = settings.snapshot_dir.parent
        return cls(
            policy_path=settings.protection_policy_path,
            sensitive_paths=[
                data_root / "portfolio",
                settings.snapshot_dir,
                settings.conversation_dir,
                settings.plans_dir,
                settings.financial_profile_path,
                settings.recommendations_path,
                data_root / "settings",
                settings.durable_storage_dir,
            ],
            backup_dir=settings.backup_archive_dir,
        )

    @property
    def supported(self) -> bool:
        return os.name == "posix"

    def get_policy(self) -> dict[str, Any]:
        return self._load_policy()

    def update_policy(self, updates: dict[str, Any]) -> dict[str, Any]:
        current = self._load_policy()
        changed = False

        level = updates.get("protection_level")
        if level is not None:
            level_str = str(level).strip().lower()
            if level_str not in VALID_PROTECTION_LEVELS:
                raise DataProtectionError("protection_level must be one of: standard, hardened")
            if current["protection_level"] != level_str:
                current["protection_level"] = level_str
                changed = True

        for key in ("auto_apply_on_startup", "include_backups"):
            if key in updates and updates[key] is not None:
                next_value = bool(updates[key])
                if current[key] != next_value:
                    current[key] = next_value
                    changed = True

        if changed:
            current["updated_at"] = utc_now_iso()
            self._save_policy(current)
        return current

    def get_status(self) -> dict[str, Any]:
        policy = self._load_policy()
        targets = self._scan_targets(policy=policy)
        non_compliant_files = sum(int(target["non_compliant_files"]) for target in targets)
        non_compliant_directories = sum(int(target["non_compliant_directories"]) for target in targets)
        return {
            "supported": self.supported,
            "strategy": PROTECTION_STRATEGY,
            "policy": policy,
            "targets": targets,
            "total_non_compliant_files": non_compliant_files,
            "total_non_compliant_directories": non_compliant_directories,
        }

    def apply_protection(self, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        policy = self._load_policy()
        if overrides:
            policy = self.update_policy(overrides)

        warnings: list[str] = []
        files_scanned = 0
        directories_scanned = 0
        files_updated = 0
        directories_updated = 0

        if self.supported:
            required_file_mode = FILE_MODE_BY_LEVEL[policy["protection_level"]]
            required_dir_mode = DIR_MODE_BY_LEVEL[policy["protection_level"]]
            targets = self._target_paths(policy=policy)
            for target in targets:
                if not target.exists():
                    continue
                for node in self._iter_target_nodes(target):
                    if node.is_symlink():
                        continue
                    try:
                        current_mode = stat.S_IMODE(node.stat().st_mode)
                    except OSError as exc:
                        warnings.append(f"Unable to read mode for {node}: {exc}")
                        continue
                    desired_mode = required_dir_mode if node.is_dir() else required_file_mode
                    if node.is_dir():
                        directories_scanned += 1
                    else:
                        files_scanned += 1
                    if current_mode == desired_mode:
                        continue
                    try:
                        node.chmod(desired_mode)
                    except OSError as exc:
                        warnings.append(f"Unable to update mode for {node}: {exc}")
                        continue
                    if node.is_dir():
                        directories_updated += 1
                    else:
                        files_updated += 1
        else:
            warnings.append("Permission hardening is only supported on POSIX-compatible systems.")

        policy["last_applied_at"] = utc_now_iso()
        policy["updated_at"] = utc_now_iso()
        self._save_policy(policy)

        status = self.get_status()
        return {
            "applied_at": utc_now_iso(),
            "supported": self.supported,
            "protection_level": policy["protection_level"],
            "include_backups": policy["include_backups"],
            "files_scanned": files_scanned,
            "directories_scanned": directories_scanned,
            "files_updated": files_updated,
            "directories_updated": directories_updated,
            "non_compliant_files_after": status["total_non_compliant_files"],
            "non_compliant_directories_after": status["total_non_compliant_directories"],
            "warnings": warnings,
        }

    def _initialize_policy(self) -> None:
        if self.policy_path.exists():
            self._load_policy()
            return
        self._save_policy(self._default_policy())

    def _default_policy(self) -> dict[str, Any]:
        return {
            "schema_version": PROTECTION_POLICY_SCHEMA_VERSION,
            "protection_level": "standard",
            "auto_apply_on_startup": False,
            "include_backups": False,
            "updated_at": utc_now_iso(),
            "last_applied_at": None,
        }

    def _load_policy(self) -> dict[str, Any]:
        try:
            raw = self.policy_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            payload = self._default_policy()
            self._save_policy(payload)
            return payload

        try:
            import json

            payload = json.loads(raw)
        except Exception:
            payload = self._default_policy()
            self._save_policy(payload)
            return payload

        if not isinstance(payload, dict):
            payload = {}
        default_payload = self._default_policy()
        level = str(payload.get("protection_level") or default_payload["protection_level"]).strip().lower()
        if level not in VALID_PROTECTION_LEVELS:
            level = default_payload["protection_level"]
        normalized = {
            "schema_version": PROTECTION_POLICY_SCHEMA_VERSION,
            "protection_level": level,
            "auto_apply_on_startup": bool(payload.get("auto_apply_on_startup", default_payload["auto_apply_on_startup"])),
            "include_backups": bool(payload.get("include_backups", default_payload["include_backups"])),
            "updated_at": str(payload.get("updated_at") or default_payload["updated_at"]),
            "last_applied_at": payload.get("last_applied_at"),
        }
        if normalized != payload:
            self._save_policy(normalized)
        return normalized

    def _save_policy(self, payload: dict[str, Any]) -> None:
        import json

        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _target_paths(self, *, policy: dict[str, Any]) -> list[Path]:
        targets: list[Path] = []
        seen: set[Path] = set()
        for path in self.sensitive_paths:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            targets.append(resolved)
        if bool(policy.get("include_backups")):
            backup = self.backup_dir.resolve()
            if backup not in seen:
                targets.append(backup)
        return targets

    def _scan_targets(self, *, policy: dict[str, Any]) -> list[dict[str, Any]]:
        required_file_mode = FILE_MODE_BY_LEVEL[policy["protection_level"]]
        required_dir_mode = DIR_MODE_BY_LEVEL[policy["protection_level"]]
        targets: list[dict[str, Any]] = []
        for target in self._target_paths(policy=policy):
            if not target.exists():
                targets.append(
                    {
                        "path": str(target),
                        "exists": False,
                        "files_scanned": 0,
                        "directories_scanned": 0,
                        "non_compliant_files": 0,
                        "non_compliant_directories": 0,
                        "sample_non_compliant_paths": [],
                        "compliant": None,
                    }
                )
                continue

            files_scanned = 0
            directories_scanned = 0
            non_compliant_files = 0
            non_compliant_directories = 0
            sample_non_compliant_paths: list[str] = []

            for node in self._iter_target_nodes(target):
                if node.is_symlink():
                    continue
                try:
                    current_mode = stat.S_IMODE(node.stat().st_mode)
                except OSError:
                    continue
                expected_mode = required_dir_mode if node.is_dir() else required_file_mode
                compliant = current_mode == expected_mode
                if node.is_dir():
                    directories_scanned += 1
                    if not compliant:
                        non_compliant_directories += 1
                else:
                    files_scanned += 1
                    if not compliant:
                        non_compliant_files += 1
                if not compliant and len(sample_non_compliant_paths) < SAMPLE_LIMIT:
                    sample_non_compliant_paths.append(str(node))

            targets.append(
                {
                    "path": str(target),
                    "exists": True,
                    "files_scanned": files_scanned,
                    "directories_scanned": directories_scanned,
                    "non_compliant_files": non_compliant_files,
                    "non_compliant_directories": non_compliant_directories,
                    "sample_non_compliant_paths": sample_non_compliant_paths,
                    "compliant": non_compliant_files == 0 and non_compliant_directories == 0,
                }
            )
        return targets

    @staticmethod
    def _iter_target_nodes(target: Path):
        yield target
        if target.is_dir():
            for node in sorted(target.rglob("*")):
                if node.is_file() or node.is_dir():
                    yield node

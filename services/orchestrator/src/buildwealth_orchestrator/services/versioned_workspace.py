"""Materialize a curated, Git-friendly BuildWealth workspace."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORKSPACE_POLICY_VERSION = 1


@dataclass(frozen=True)
class VersionedWorkspacePolicy:
    include_plans: bool = True
    include_recommendations: bool = True
    include_review_packets: bool = True
    include_snapshot_checkpoints: bool = True
    include_financial_profile: bool = False

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "VersionedWorkspacePolicy":
        return cls(
            include_plans=bool(settings.get("include_plans", True)),
            include_recommendations=bool(settings.get("include_recommendations", True)),
            include_review_packets=bool(settings.get("include_review_packets", True)),
            include_snapshot_checkpoints=bool(settings.get("include_snapshot_checkpoints", True)),
            include_financial_profile=bool(settings.get("include_financial_profile", False)),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_version": WORKSPACE_POLICY_VERSION,
            "include_plans": self.include_plans,
            "include_recommendations": self.include_recommendations,
            "include_review_packets": self.include_review_packets,
            "include_snapshot_checkpoints": self.include_snapshot_checkpoints,
            "include_financial_profile": self.include_financial_profile,
        }


@dataclass(frozen=True)
class VersionedWorkspaceExportResult:
    workspace_dir: str
    files_written: int
    files_removed: int
    sections: dict[str, int]
    manifest_path: str


class VersionedWorkspaceService:
    def __init__(
        self,
        *,
        workspace_dir: Path,
        plans_dir: Path,
        recommendations_path: Path,
        review_packet_dir: Path,
        protection_policy_path: Path | None = None,
        financial_profile_path: Path | None = None,
    ):
        self.workspace_dir = workspace_dir
        self.plans_dir = plans_dir
        self.recommendations_path = recommendations_path
        self.review_packet_dir = review_packet_dir
        self.protection_policy_path = protection_policy_path
        self.financial_profile_path = financial_profile_path
        self._files_written = 0
        self._files_removed = 0

    def materialize(
        self,
        policy: VersionedWorkspacePolicy | None = None,
    ) -> VersionedWorkspaceExportResult:
        policy = policy or VersionedWorkspacePolicy()
        self._files_written = 0
        self._files_removed = 0
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        sections: dict[str, int] = {}
        self._write_workspace_bootstrap()
        self._write_json(self.workspace_dir / "manifests" / "workspace_policy.json", policy.as_dict())

        if policy.include_plans:
            sections["plans"] = self._export_plans()
        else:
            self._clear_managed_path(self.workspace_dir / "plans")
            sections["plans"] = 0

        if policy.include_recommendations:
            sections["recommendations"] = self._export_recommendations()
        else:
            self._clear_managed_path(self.workspace_dir / "recommendations")
            sections["recommendations"] = 0

        if policy.include_review_packets:
            sections["review_packets"] = self._export_review_packets()
        else:
            self._clear_managed_path(self.workspace_dir / "reports" / "portfolio_review_packets")
            sections["review_packets"] = 0

        if policy.include_snapshot_checkpoints:
            (self.workspace_dir / "snapshots" / "checkpoints").mkdir(parents=True, exist_ok=True)
        else:
            self._clear_managed_path(self.workspace_dir / "snapshots" / "checkpoints")
        sections["snapshot_checkpoints"] = self._count_files(
            self.workspace_dir / "snapshots" / "checkpoints"
        )

        if policy.include_financial_profile:
            sections["financial_profile"] = self._export_optional_json(
                self.financial_profile_path,
                self.workspace_dir / "profile" / "financial_profile.json",
            )
        else:
            self._clear_managed_path(self.workspace_dir / "profile")
            sections["financial_profile"] = 0

        sections["protection_policy"] = self._export_optional_json(
            self.protection_policy_path,
            self.workspace_dir / "policy" / "protection_policy.json",
        )

        manifest_path = self.workspace_dir / "manifests" / "export_manifest.json"
        self._write_json(
            manifest_path,
            {
                "schema_version": 1,
                "workspace_policy_version": WORKSPACE_POLICY_VERSION,
                "sections": sections,
                "source_paths": self._source_paths(),
            },
        )

        return VersionedWorkspaceExportResult(
            workspace_dir=str(self.workspace_dir),
            files_written=self._files_written,
            files_removed=self._files_removed,
            sections=sections,
            manifest_path=str(manifest_path),
        )

    def _source_paths(self) -> dict[str, str | None]:
        return {
            "plans_dir": str(self.plans_dir),
            "recommendations_path": str(self.recommendations_path),
            "review_packet_dir": str(self.review_packet_dir),
            "protection_policy_path": (
                str(self.protection_policy_path) if self.protection_policy_path else None
            ),
            "financial_profile_path": (
                str(self.financial_profile_path) if self.financial_profile_path else None
            ),
        }

    def _write_workspace_bootstrap(self) -> None:
        self._write_text(
            self.workspace_dir / "README.md",
            "\n".join(
                [
                    "# BuildWealth Versioned Workspace",
                    "",
                    "This directory is generated from BuildWealth's canonical local stores.",
                    "Use BuildWealth to change financial data; this workspace is for audit history.",
                    "",
                ]
            ),
        )
        self._write_text(
            self.workspace_dir / ".gitignore",
            "\n".join(
                [
                    ".DS_Store",
                    "*.log",
                    "",
                ]
            ),
        )

    def _export_plans(self) -> int:
        target = self.workspace_dir / "plans"
        self._clear_managed_path(target)
        if not self.plans_dir.exists():
            target.mkdir(parents=True, exist_ok=True)
            return 0

        exported = 0
        for path in sorted(self.plans_dir.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(self.plans_dir)
            if any(part in {"scenarios", "__pycache__"} for part in relative.parts):
                continue
            target_path = target / relative
            if path.suffix.lower() == ".json":
                self._write_json(target_path, self._load_json(path))
            else:
                self._copy_text(path, target_path)
            exported += 1
        return exported

    def _export_recommendations(self) -> int:
        target = self.workspace_dir / "recommendations"
        self._clear_managed_path(target)
        target.mkdir(parents=True, exist_ok=True)

        payload = self._load_json(self.recommendations_path)
        rows = payload.get("recommendations") if isinstance(payload.get("recommendations"), list) else []
        recommendations = [row for row in rows if isinstance(row, dict)]
        recommendations.sort(key=lambda row: str(row.get("id") or ""))

        index_rows = []
        for index, recommendation in enumerate(recommendations, start=1):
            recommendation_id = str(recommendation.get("id") or f"recommendation-{index:04d}")
            safe_id = self._safe_file_stem(recommendation_id)
            normalized = dict(recommendation)
            normalized["id"] = recommendation_id
            self._write_json(target / f"{safe_id}.json", normalized)
            index_rows.append(
                {
                    "id": recommendation_id,
                    "file": f"{safe_id}.json",
                    "title": str(recommendation.get("title") or ""),
                    "status": str(recommendation.get("status") or ""),
                    "updated_at": recommendation.get("updated_at"),
                }
            )

        self._write_json(target / "index.json", {"recommendations": index_rows})
        return len(recommendations) + 1

    def _export_review_packets(self) -> int:
        target = self.workspace_dir / "reports" / "portfolio_review_packets"
        self._clear_managed_path(target)
        target.mkdir(parents=True, exist_ok=True)

        exported = 0
        for path in sorted(self.review_packet_dir.glob("*")):
            if not path.is_file() or path.suffix.lower() not in {".json", ".md"}:
                continue
            target_path = target / path.name
            if path.suffix.lower() == ".json":
                self._write_json(target_path, self._load_json(path))
            else:
                self._copy_text(path, target_path)
            exported += 1
        return exported

    def _export_optional_json(self, source: Path | None, target: Path) -> int:
        if source is None or not source.exists():
            self._clear_managed_path(target)
            return 0
        self._write_json(target, self._load_json(source))
        return 1

    def _clear_managed_path(self, path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            removed = self._count_files(path)
            shutil.rmtree(path)
            self._files_removed += removed
            return
        path.unlink()
        self._files_removed += 1

    def _write_json(self, path: Path, payload: Any) -> None:
        text = json.dumps(payload, indent=2, sort_keys=True, default=str)
        self._write_text(path, f"{text}\n")

    def _write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text(encoding="utf-8") == text:
            return
        path.write_text(text, encoding="utf-8")
        self._files_written += 1

    def _copy_text(self, source: Path, target: Path) -> None:
        self._write_text(target, source.read_text(encoding="utf-8"))

    @staticmethod
    def _load_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _safe_file_stem(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
        cleaned = cleaned.strip("-_")
        return cleaned or "item"

    @staticmethod
    def _count_files(path: Path) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            return 1
        return sum(1 for candidate in path.rglob("*") if candidate.is_file())

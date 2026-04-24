from __future__ import annotations

import json
from pathlib import Path

from buildwealth_orchestrator.services.versioned_workspace import (
    VersionedWorkspacePolicy,
    VersionedWorkspaceService,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _snapshot_workspace(workspace_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(workspace_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(workspace_dir.rglob("*"))
        if path.is_file()
    }


def _build_service(tmp_path: Path) -> tuple[VersionedWorkspaceService, Path]:
    data_root = tmp_path / "data"
    workspace_dir = data_root / "versioned"
    plans_dir = data_root / "plans"
    recommendations_path = data_root / "recommendations" / "inbox.json"
    review_packet_dir = data_root / "reports" / "portfolio_review_packets"
    protection_policy_path = data_root / "security" / "protection_policy.json"
    financial_profile_path = data_root / "profile" / "financial_profile.json"

    _write_json(
        plans_dir / "index.json",
        {
            "schema_version": 2,
            "active_plan_id": "plan-alpha",
            "plans": [{"id": "plan-alpha", "title": "Plan Alpha"}],
        },
    )
    _write_text(plans_dir / "plan-alpha" / "plan.md", "# Plan Alpha\n")
    _write_json(plans_dir / "plan-alpha" / "settings.json", {"years": 30, "schema_version": 2})
    _write_text(
        plans_dir / "plan-alpha" / "decisions.jsonl",
        json.dumps({"id": "decision-1", "summary": "Increase savings"}) + "\n",
    )
    _write_json(plans_dir / "plan-alpha" / "scenarios" / "scratch.json", {"ignored": True})
    _write_text(plans_dir / "plan-alpha" / "artifacts" / "packet.md", "# Artifact\n")

    _write_json(
        recommendations_path,
        {
            "recommendations": [
                {
                    "id": "rec-beta",
                    "title": "Beta",
                    "status": "proposed",
                    "updated_at": "2026-04-23T00:00:00Z",
                },
                {
                    "id": "rec-alpha",
                    "title": "Alpha",
                    "status": "applied",
                    "updated_at": "2026-04-22T00:00:00Z",
                },
            ]
        },
    )

    _write_json(
        review_packet_dir / "portfolio-review-20260423T000000Z-a.json",
        {"meta": {"packet_id": "portfolio-review-20260423T000000Z-a"}, "summary": {}},
    )
    _write_text(review_packet_dir / "portfolio-review-20260423T000000Z-a.md", "# Review\n")
    _write_json(protection_policy_path, {"level": "standard"})
    _write_json(financial_profile_path, {"schema_version": 2, "income_items": []})

    service = VersionedWorkspaceService(
        workspace_dir=workspace_dir,
        plans_dir=plans_dir,
        recommendations_path=recommendations_path,
        review_packet_dir=review_packet_dir,
        protection_policy_path=protection_policy_path,
        financial_profile_path=financial_profile_path,
    )
    return service, workspace_dir


def test_versioned_workspace_materializes_curated_artifacts(tmp_path: Path) -> None:
    service, workspace_dir = _build_service(tmp_path)

    result = service.materialize()

    assert result.sections["plans"] >= 4
    assert result.sections["recommendations"] == 3
    assert result.sections["review_packets"] == 2
    assert result.sections["financial_profile"] == 0
    assert (workspace_dir / "README.md").exists()
    assert (workspace_dir / "plans" / "plan-alpha" / "plan.md").read_text(encoding="utf-8")
    assert not (workspace_dir / "plans" / "plan-alpha" / "scenarios" / "scratch.json").exists()
    assert (workspace_dir / "recommendations" / "rec-alpha.json").exists()
    assert (workspace_dir / "recommendations" / "rec-beta.json").exists()
    assert (workspace_dir / "reports" / "portfolio_review_packets").exists()
    assert (workspace_dir / "policy" / "protection_policy.json").exists()
    assert not (workspace_dir / "profile" / "financial_profile.json").exists()

    index = json.loads((workspace_dir / "recommendations" / "index.json").read_text(encoding="utf-8"))
    assert [row["id"] for row in index["recommendations"]] == ["rec-alpha", "rec-beta"]


def test_versioned_workspace_export_is_content_stable_for_repeated_runs(tmp_path: Path) -> None:
    service, workspace_dir = _build_service(tmp_path)

    service.materialize()
    first_snapshot = _snapshot_workspace(workspace_dir)
    service.materialize()
    second_snapshot = _snapshot_workspace(workspace_dir)

    assert second_snapshot == first_snapshot


def test_versioned_workspace_policy_controls_sensitive_profile_export(tmp_path: Path) -> None:
    service, workspace_dir = _build_service(tmp_path)

    service.materialize(VersionedWorkspacePolicy(include_financial_profile=True))

    assert (workspace_dir / "profile" / "financial_profile.json").exists()

    service.materialize(VersionedWorkspacePolicy(include_financial_profile=False))

    assert not (workspace_dir / "profile" / "financial_profile.json").exists()

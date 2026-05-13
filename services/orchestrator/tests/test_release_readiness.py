from __future__ import annotations

from datetime import timedelta

import buildwealth_orchestrator.main as main


class DurableReady:
    def get_status(self) -> dict:
        return {
            "database_exists": True,
            "document_count": 24,
            "latest_rollback_check_passed": True,
            "latest_migration_at": main.utc_now(),
        }


class DurableMissing:
    def get_status(self) -> dict:
        return {
            "database_exists": False,
            "document_count": 0,
            "latest_rollback_check_passed": None,
            "latest_migration_at": None,
        }


class BackupReady:
    def list_backups(self) -> dict:
        return {
            "backups": [
                {
                    "backup_id": "backup-fresh",
                    "created_at": main.utc_now(),
                    "size_bytes": 2048,
                }
            ]
        }


class BackupMissing:
    def list_backups(self) -> dict:
        return {"backups": []}


class ProtectionReady:
    def get_status(self) -> dict:
        return {
            "supported": True,
            "total_non_compliant_files": 0,
            "total_non_compliant_directories": 0,
            "policy": {"protection_level": "standard", "last_applied_at": main.utc_now()},
        }


class ProtectionWeak:
    def get_status(self) -> dict:
        return {
            "supported": True,
            "total_non_compliant_files": 2,
            "total_non_compliant_directories": 1,
            "policy": {"protection_level": "standard", "last_applied_at": None},
        }


class GitReady:
    def status(self) -> dict:
        return {
            "status": "ok",
            "dirty": False,
            "changed_files": [],
            "last_commit": {
                "hash": "abc123",
                "short_hash": "abc123",
                "date": main.utc_now(),
                "message": "Checkpoint",
            },
        }


class GitDirty:
    def status(self) -> dict:
        return {
            "status": "ok",
            "dirty": True,
            "changed_files": [{"path": "plans/plan.md", "status": "M"}],
            "last_commit": None,
        }


class ActivityReady:
    def query(self, **_: object) -> dict:
        return {
            "summary": {"total_matched": 4},
            "events": [
                {
                    "event_type": "product_workflow_verification",
                    "created_at": main.utc_now().isoformat(),
                    "title": "Product workflow verification passed",
                    "status": "passed",
                    "metadata": {
                        "workflow": "product_testing",
                        "passed_count": 9,
                        "failed_count": 0,
                        "checklist_path": "docs/PRODUCT_TESTING_CHECKLIST_2026-04-30.md",
                    },
                },
                {
                    "event_type": "restore_preview",
                    "created_at": main.utc_now().isoformat(),
                    "title": "Restore preview generated",
                    "status": "ok",
                },
                {
                    "event_type": "profile_update",
                    "created_at": main.utc_now().isoformat(),
                    "title": "Financial profile updated",
                    "status": "applied",
                },
            ],
        }


class ActivityMissingWorkflow:
    def query(self, **_: object) -> dict:
        return {
            "summary": {"total_matched": 2},
            "events": [
                {
                    "event_type": "restore_preview",
                    "created_at": main.utc_now().isoformat(),
                    "title": "Restore preview generated",
                    "status": "ok",
                },
                {
                    "event_type": "profile_update",
                    "created_at": main.utc_now().isoformat(),
                    "title": "Financial profile updated",
                    "status": "applied",
                },
            ],
        }


class ActivityEmpty:
    def query(self, **_: object) -> dict:
        return {"summary": {"total_matched": 0}, "events": []}


class RecordingActivityStore:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, **kwargs: object) -> dict:
        event = {"id": f"event-{len(self.events) + 1}", "created_at": main.utc_now().isoformat(), **kwargs}
        self.events.append(event)
        return event

    def query(self, **_: object) -> dict:
        return {"summary": {"total_matched": len(self.events)}, "events": list(reversed(self.events))}


def _ready_engine_status() -> main.EngineStatusResponse:
    return main.EngineStatusResponse(
        as_of=main.utc_now(),
        engines=[
            {
                "name": "plan_simulation",
                "enabled": True,
                "reachable": True,
                "contract_compatible": True,
            }
        ],
    )


def _degraded_engine_status() -> main.EngineStatusResponse:
    return main.EngineStatusResponse(
        as_of=main.utc_now(),
        engines=[
            {
                "name": "plan_simulation",
                "enabled": True,
                "reachable": False,
                "contract_compatible": False,
                "last_error": "calculation unavailable",
            }
        ],
    )


def test_release_readiness_contract_reports_ready_state(monkeypatch) -> None:
    monkeypatch.setattr(main, "durable_storage_service", DurableReady())
    monkeypatch.setattr(main, "backup_restore_service", BackupReady())
    monkeypatch.setattr(main, "data_protection_service", ProtectionReady())
    monkeypatch.setattr(main, "_git_policy", lambda: {"enabled": True})
    monkeypatch.setattr(main, "_git_repository_service", lambda _policy: GitReady())
    monkeypatch.setattr(main, "_git_activity_store", lambda: ActivityReady())
    monkeypatch.setattr(main, "_engine_status_snapshot_sync", _ready_engine_status)

    response = main.build_release_readiness_response()
    checks = {check.id: check for check in response.checks}

    assert response.status == "ready"
    assert response.ready_count == response.total_count
    assert response.blocking_gaps == []
    assert response.warnings == []
    assert checks["backup"].status == "ready"
    assert checks["restore_preview"].status == "ready"
    assert checks["providers"].status == "ready"
    assert checks["workflow_verification"].status == "ready"
    assert checks["workflow_verification"].last_verified_at is not None
    assert checks["workflow_verification"].metadata["passed_count"] == 9
    assert response.recommended_actions == []


def test_release_readiness_contract_blocks_on_missing_trust_evidence(monkeypatch) -> None:
    monkeypatch.setattr(main, "durable_storage_service", DurableMissing())
    monkeypatch.setattr(main, "backup_restore_service", BackupMissing())
    monkeypatch.setattr(main, "data_protection_service", ProtectionWeak())
    monkeypatch.setattr(main, "_git_policy", lambda: {"enabled": True})
    monkeypatch.setattr(main, "_git_repository_service", lambda _policy: GitDirty())
    monkeypatch.setattr(main, "_git_activity_store", lambda: ActivityEmpty())
    monkeypatch.setattr(main, "_engine_status_snapshot_sync", _degraded_engine_status)

    response = main.build_release_readiness_response(now=main.utc_now() + timedelta(days=1))
    checks = {check.id: check for check in response.checks}
    action_kinds = {action.action_kind for action in response.recommended_actions}

    assert response.status == "blocked"
    assert response.ready_count < response.total_count
    assert checks["durable_store"].status == "blocked"
    assert checks["backup"].status == "blocked"
    assert checks["protection"].status == "warning"
    assert checks["checkpoint"].status == "warning"
    assert checks["audit_feed"].status == "warning"
    assert checks["restore_preview"].status == "warning"
    assert checks["providers"].status == "blocked"
    assert any("backup" in gap.lower() for gap in response.blocking_gaps)
    assert {
        "create_backup",
        "apply_protection",
        "create_checkpoint",
        "preview_restore",
        "run_product_testing",
    } <= action_kinds


def test_release_readiness_warns_when_workflow_verification_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(main, "durable_storage_service", DurableReady())
    monkeypatch.setattr(main, "backup_restore_service", BackupReady())
    monkeypatch.setattr(main, "data_protection_service", ProtectionReady())
    monkeypatch.setattr(main, "_git_policy", lambda: {"enabled": True})
    monkeypatch.setattr(main, "_git_repository_service", lambda _policy: GitReady())
    monkeypatch.setattr(main, "_git_activity_store", lambda: ActivityMissingWorkflow())
    monkeypatch.setattr(main, "_engine_status_snapshot_sync", _ready_engine_status)

    response = main.build_release_readiness_response()
    checks = {check.id: check for check in response.checks}
    action_kinds = {action.action_kind for action in response.recommended_actions}

    assert response.status == "warning"
    assert checks["workflow_verification"].status == "warning"
    assert "No product workflow verification" in checks["workflow_verification"].detail
    assert "run_product_testing" in action_kinds


def test_release_readiness_workflow_endpoint_records_audit_evidence(monkeypatch) -> None:
    activity = RecordingActivityStore()
    monkeypatch.setattr(main, "_git_activity_store", lambda: activity)

    response = main.record_release_workflow_verification(
        main.ReleaseWorkflowVerificationRequest(
            workflow="product_testing",
            status="passed",
            passed_count=9,
            failed_count=0,
            checklist_path="docs/PRODUCT_TESTING_CHECKLIST_2026-04-30.md",
            notes="Manual product pass completed.",
        )
    )

    assert response.status == "passed"
    assert response.event_type == "product_workflow_verification"
    assert activity.events[0]["metadata"]["workflow"] == "product_testing"
    assert activity.events[0]["metadata"]["passed_count"] == 9
    assert activity.events[0]["metadata"]["failed_count"] == 0


def test_today_trust_card_uses_release_readiness_contract(monkeypatch) -> None:
    def fake_readiness() -> main.ReleaseReadinessResponse:
        return main.ReleaseReadinessResponse(
            status="blocked",
            ready_count=5,
            total_count=8,
            generated_at=main.utc_now(),
            summary="Release readiness is blocked by trust or provider gaps.",
            checks=[],
            blocking_gaps=["No local backup archive is available."],
            warnings=["Run a read-only restore preview."],
            recommended_actions=[],
        )

    monkeypatch.setattr(main, "build_release_readiness_response", fake_readiness)

    card = main._build_trust_durability_command_card()
    dashboard = main.TodayDashboardResponse(
        generated_at=main.utc_now(),
        currency="USD",
        state="MN",
        sync_status=main.SyncStatusResponse(running=False, runs_total=0, runs_failed=0),
        context_state="ready",
        command_cards=[card],
    )
    domains = {domain.id: domain for domain in main._build_today_confidence_domains(dashboard)}

    assert card.status == "critical"
    assert card.metric_value == "5/8"
    assert "No local backup archive is available." in card.detail
    assert domains["trust"].status == "degraded"

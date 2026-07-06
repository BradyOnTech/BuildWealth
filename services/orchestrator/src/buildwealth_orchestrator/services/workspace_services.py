from __future__ import annotations

from contextlib import suppress
from copy import copy
from dataclasses import dataclass
from pathlib import Path
import secrets

from buildwealth_orchestrator.services.control_plane import (
    ControlPlaneStore,
    RequestContext,
    WorkspaceRecord,
)
from buildwealth_orchestrator.services.context_intelligence import ContextIntelligenceService
from buildwealth_orchestrator.services.embedding_clients import apply_context_embedding_overrides
from buildwealth_orchestrator.services.copilot_runtime import ConversationStore
from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.import_workbench import ImportWorkbenchStore
from buildwealth_orchestrator.services.plan_workspace import PlanWorkspace
from buildwealth_orchestrator.services.asset_registry import AssetRegistry
from buildwealth_orchestrator.services.portfolio_review_packets import PortfolioReviewPacketStore
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.recommendation_inbox import RecommendationInbox
from buildwealth_orchestrator.services.snapshot_store import SnapshotStore
from buildwealth_orchestrator.services.today_review_checkpoints import TodayReviewCheckpointStore
from buildwealth_orchestrator.services.workspace_settings import (
    WorkspaceSecretStore,
    WorkspaceSettingsStore,
    load_or_create_local_secret_key,
    write_local_secret_key,
)


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    profile_path: Path
    portfolio_dir: Path
    snapshot_dir: Path
    plans_dir: Path
    recommendations_path: Path
    conversation_dir: Path
    durable_storage_dir: Path
    backup_archive_dir: Path
    import_inbox_dir: Path
    import_archive_dir: Path
    import_workbench_dir: Path
    import_reports_dir: Path
    portfolio_review_packet_dir: Path
    today_review_checkpoint_path: Path
    protection_policy_path: Path
    settings_path: Path
    secrets_path: Path


@dataclass
class WorkspaceServices:
    record: WorkspaceRecord
    context: RequestContext
    paths: WorkspacePaths
    financial_profile_store: FinancialProfileStore
    portfolio_store: PortfolioStore
    asset_registry: AssetRegistry
    snapshot_store: SnapshotStore
    plan_workspace: PlanWorkspace
    recommendation_inbox: RecommendationInbox
    conversation_store: ConversationStore
    context_intelligence_service: ContextIntelligenceService
    import_workbench_store: ImportWorkbenchStore
    portfolio_review_packet_store: PortfolioReviewPacketStore
    today_review_checkpoint_store: TodayReviewCheckpointStore
    settings_store: WorkspaceSettingsStore
    secret_store: WorkspaceSecretStore


class WorkspaceServiceFactory:
    def __init__(self, *, settings, control_plane: ControlPlaneStore):
        self.settings = settings
        self.control_plane = control_plane
        self.secret_key = load_or_create_local_secret_key(settings.secret_key_path)

    def paths_for_record(self, record: WorkspaceRecord) -> WorkspacePaths:
        root = record.storage_path
        return WorkspacePaths(
            root=root,
            profile_path=root / "profile" / "financial_profile.json",
            portfolio_dir=root / "portfolio",
            snapshot_dir=root / "snapshots",
            plans_dir=root / "plans",
            recommendations_path=root / "recommendations" / "inbox.json",
            conversation_dir=root / "conversations",
            durable_storage_dir=root / "storage",
            backup_archive_dir=root / "backups",
            import_inbox_dir=root / "imports" / "inbox",
            import_archive_dir=root / "imports" / "archive",
            import_workbench_dir=root / "imports" / "workbench",
            import_reports_dir=root / "imports" / "reports",
            portfolio_review_packet_dir=root / "reports" / "portfolio_review_packets",
            today_review_checkpoint_path=root / "today" / "review_checkpoint.json",
            protection_policy_path=root / "security" / "protection_policy.json",
            settings_path=root / "settings" / "workspace_settings.json",
            secrets_path=root / "settings" / "workspace_secrets.json",
        )

    def settings_for_paths(self, paths: WorkspacePaths):
        workspace_settings = copy(self.settings)
        workspace_settings.snapshot_dir = paths.snapshot_dir
        workspace_settings.durable_storage_dir = paths.durable_storage_dir
        workspace_settings.backup_archive_dir = paths.backup_archive_dir
        workspace_settings.protection_policy_path = paths.protection_policy_path
        workspace_settings.portfolio_review_packet_dir = paths.portfolio_review_packet_dir
        workspace_settings.import_inbox_dir = paths.import_inbox_dir
        workspace_settings.import_archive_dir = paths.import_archive_dir
        workspace_settings.import_workbench_dir = paths.import_workbench_dir
        workspace_settings.import_reports_dir = paths.import_reports_dir
        workspace_settings.conversation_dir = paths.conversation_dir
        workspace_settings.plans_dir = paths.plans_dir
        workspace_settings.financial_profile_path = paths.profile_path
        workspace_settings.recommendations_path = paths.recommendations_path
        workspace_settings.today_review_checkpoint_path = paths.today_review_checkpoint_path
        return workspace_settings

    def for_context(self, context: RequestContext) -> WorkspaceServices:
        record, _role = self.control_plane.get_workspace_for_user(
            user_id=context.user_id,
            workspace_id=context.workspace_id,
        )
        paths = self.paths_for_record(record)
        paths.root.mkdir(parents=True, exist_ok=True)
        secret_store = WorkspaceSecretStore(paths.secrets_path, self.secret_key)
        settings_store = WorkspaceSettingsStore(paths.settings_path, secret_store)
        profile_store = FinancialProfileStore(paths.profile_path)
        portfolio_store = PortfolioStore(paths.portfolio_dir)
        asset_registry = AssetRegistry(portfolio_store)
        plan_workspace = PlanWorkspace(paths.plans_dir)
        recommendation_inbox = RecommendationInbox(paths.recommendations_path)
        snapshot_store = SnapshotStore(paths.snapshot_dir)
        conversation_store = ConversationStore(paths.conversation_dir)
        workspace_settings = self.settings_for_paths(paths)
        # Saved workspace settings are authoritative for embeddings — the
        # global settings object may still carry stale legacy-store overrides
        # applied at boot.
        try:
            apply_context_embedding_overrides(workspace_settings, settings_store.load_stored_raw())
        except Exception:
            pass
        context_intelligence_service = ContextIntelligenceService.from_settings(
            workspace_settings,
            financial_profile_store=profile_store,
            plan_workspace=plan_workspace,
            recommendation_inbox=recommendation_inbox,
            portfolio_store=portfolio_store,
        )
        return WorkspaceServices(
            record=record,
            context=context,
            paths=paths,
            financial_profile_store=profile_store,
            portfolio_store=portfolio_store,
            asset_registry=asset_registry,
            snapshot_store=snapshot_store,
            plan_workspace=plan_workspace,
            recommendation_inbox=recommendation_inbox,
            conversation_store=conversation_store,
            context_intelligence_service=context_intelligence_service,
            import_workbench_store=ImportWorkbenchStore(
                workbench_dir=paths.import_workbench_dir,
                reports_dir=paths.import_reports_dir,
            ),
            portfolio_review_packet_store=PortfolioReviewPacketStore(paths.portfolio_review_packet_dir),
            today_review_checkpoint_store=TodayReviewCheckpointStore(paths.today_review_checkpoint_path),
            settings_store=settings_store,
            secret_store=secret_store,
        )

    def preview_secret_key_rotation(self) -> dict[str, object]:
        items: list[dict[str, object]] = []
        total_secrets = 0
        for record in self.control_plane.list_active_workspaces():
            paths = self.paths_for_record(record)
            secret_store = WorkspaceSecretStore(paths.secrets_path, self.secret_key)
            exported = secret_store.export_plaintext_secrets()
            total_secrets += len(exported)
            items.append(
                {
                    "workspace_id": record.id,
                    "workspace_name": record.name,
                    "workspace_type": record.workspace_type,
                    "secret_count": len(exported),
                }
            )
        return {
            "can_rotate": True,
            "workspace_count": len(items),
            "secret_count": total_secrets,
            "items": items,
        }

    def rotate_secret_key(self) -> dict[str, object]:
        preview = self.preview_secret_key_rotation()
        new_key = secrets.token_bytes(32)
        rotated_items: list[dict[str, object]] = []
        records = self.control_plane.list_active_workspaces()
        backups: list[tuple[Path, str | None]] = []
        for record in records:
            path = self.paths_for_record(record).secrets_path
            backups.append((path, path.read_text(encoding="utf-8") if path.exists() else None))
        try:
            for record in records:
                paths = self.paths_for_record(record)
                secret_store = WorkspaceSecretStore(paths.secrets_path, self.secret_key)
                result = secret_store.rotate_key(new_key)
                rotated_items.append(
                    {
                        "workspace_id": record.id,
                        "workspace_name": record.name,
                        "workspace_type": record.workspace_type,
                        "secret_count": result["secret_count"],
                        "rotated_at": result["rotated_at"],
                    }
                )
            write_local_secret_key(self.settings.secret_key_path, new_key)
            self.secret_key = new_key
        except Exception as exc:
            for path, backup in backups:
                if backup is None:
                    with suppress(FileNotFoundError):
                        path.unlink()
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(backup, encoding="utf-8")
            raise RuntimeError("Secret key rotation failed; workspace secret files were restored") from exc
        return {
            "rotated": True,
            "workspace_count": preview["workspace_count"],
            "secret_count": preview["secret_count"],
            "items": rotated_items,
        }

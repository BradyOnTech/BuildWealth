from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import re
import shutil
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote as url_quote, urlencode

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx

from buildwealth_orchestrator.schemas import (
    ChatRequest,
    ChatResponse,
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotContextCacheStatusResponse,
    CopilotContextResponse,
    CopilotConversationResponse,
    CopilotConversationSummary,
    CsvImportRequest,
    CsvImportResponse,
    CsvTemplateOption,
    ImportReportListResponse,
    ImportReportResponse,
    ImportWorkbenchApplyRequest,
    ImportWorkbenchApplyResponse,
    ImportWorkbenchPreviewResponse,
    FinancialProfileRequest,
    FinancialProfileResponse,
    OnboardingStatusResponse,
    OptionsChainRequest,
    PriceHistoryRequest,
    PortfolioFitAssessmentRequest,
    PortfolioFitAssessmentResponse,
    ResearchCompareRequest,
    ResearchCompareResponse,
    ResearchDossierRequest,
    ResearchDossierResponse,
    ResearchDossierLookupResponse,
    ResearchEvidencePacket,
    ResearchEvidencePacketRequest,
    WatchlistRankResponse,
    AssetMetadataUpdateRequest,
    AssetRegistryItem,
    AssetRegistrySearchResponse,
    PortfolioAuditResponse,
    PortfolioAnalyticsResponse,
    PlanArtifactSummary,
    PlanArtifactResponse,
    PlanCreateRequest,
    PlanDecisionCreateRequest,
    PlanDetailResponse,
    PlanScenarioDiffRequest,
    PlanScenarioDiffResponse,
    PlanWithdrawalStrategyCompareRequest,
    PlanWithdrawalStrategyCompareResponse,
    PlanScenarioBranchRequest,
    PlanScenarioBranchResponse,
    PlanSimulationExplainRequest,
    PlanSimulationExplainResponse,
    PlanWhatIfReviewLevelRequest,
    PlanWhatIfReviewLevelResponse,
    PlanSettings,
    PlanSettingsUpdateRequest,
    PlanTimelineResponse,
    PlanTimelineUpdateRequest,
    PlanContributionRulesResponse,
    PlanContributionRulesUpdateRequest,
    PlanAssumptionSetsResponse,
    PlanAssumptionSetsUpdateRequest,
    PlanScenarioBranchTemplatesResponse,
    PlanScenarioBranchTemplatesUpdateRequest,
    PlanSavedSimulation,
    PlanSavedSimulationCreateRequest,
    PlanSavedSimulationDecisionRequest,
    PlanSavedSimulationDecisionResponse,
    PlanSavedSimulationCompareResponse,
    PlanSavedSimulationRerunRequest,
    PlanSavedSimulationRerunResponse,
    PlanSavedSimulationsResponse,
    PlanResearchBridgeRequest,
    PlanResearchBridgeResponse,
    PlanResearchBridgePinnedItem,
    PlanRecommendationClosureSummaryRequest,
    PlanRecommendationClosureSummaryResponse,
    ScenarioComparisonRow,
    PlanSummary,
    PlanUpdateRequest,
    PlanningResponse,
    HouseholdPlanningContext,
    PortfolioSnapshot,
    ProfileReadinessSection,
    ProfileReadinessSummary,
    PortfolioBenchmarkResponse,
    PortfolioAttributionResponse,
    ResearchResponse,
    ScenarioRequest,
    IncomeProjectionRequest,
    IncomeProjectionResponse,
    ExpenseProjectionRequest,
    ExpenseProjectionResponse,
    DebtProjectionRequest,
    DebtProjectionResponse,
    SocialSecurityProjectionRequest,
    SocialSecurityProjectionResponse,
    RmdProjectionRequest,
    RmdProjectionResponse,
    ContributionAllocationRequest,
    ContributionAllocationResponse,
    TaxEstimateRequest,
    TaxEstimateResponse,
    TimelineImpactProjectionResponse,
    SnapshotHistoryResponse,
    SyncStatusResponse,
    RecommendationActionResponse,
    RecommendationApplyRequest,
    RecommendationClosureAnalyticsResponse,
    RecommendationCreateRequest,
    RecommendationItem,
    RecommendationOutcomePrefillResponse,
    RecommendationOutcomeUpdateRequest,
    CashLiquidityRecommendationGenerateRequest,
    PlanTrackingRecommendationGenerateRequest,
    ProfileCompletenessRecommendationGenerateRequest,
    PortfolioRiskRecommendationGenerateRequest,
    RecommendationFactoryResponse,
    RecommendationFactoryRunAllRequest,
    RecommendationFactoryRunAllResponse,
    ResearchThesisExpirationRecommendationGenerateRequest,
    AllocationDriftRecommendationGenerateRequest,
    FundOverlapRecommendationGenerateRequest,
    DueOutcomeReviewRecommendationGenerateRequest,
    StaleAssumptionRecommendationGenerateRequest,
    WatchlistResearchRecommendationGenerateRequest,
    RecommendationPreviewRequest,
    RecommendationPreviewResponse,
    RecommendationRejectRequest,
    RecommendationUpdateRequest,
    AffordabilityRequest,
    AffordabilityResponse,
    SimulateTradeRequest,
    SimulateTradeResponse,
    FinancialHealthResponse,
    GoalProgressResponse,
    PlanTrackingResponse,
    ServiceStatusResponse,
    DurableStorageStatusResponse,
    DurableStorageMigrationRequest,
    DurableStorageMigrationResponse,
    DurableStorageRollbackRequest,
    DurableStorageRollbackResponse,
    BackupListResponse,
    BackupCreateRequest,
    BackupCreateResponse,
    BackupRestoreRequest,
    BackupRestoreResponse,
    StorageProtectionStatusResponse,
    StorageProtectionPolicyUpdateRequest,
    StorageProtectionPolicyResponse,
    StorageProtectionApplyRequest,
    StorageProtectionApplyResponse,
    GitActivityCleanupRequest,
    GitActivityCleanupResponse,
    GitActivityEvent,
    GitActivityResponse,
    GitCheckpointRequest,
    GitCheckpointResponse,
    GitDiffResponse,
    GitAutoGitStateResponse,
    GitHistoryResponse,
    GitInitResponse,
    GitPolicyResponse,
    GitPolicyUpdateRequest,
    GitRemoteConnectRequest,
    GitRemoteOperationRequest,
    GitRemoteOperationResponse,
    GitRestoreApplyRequest,
    GitRestoreApplyResponse,
    GitRestorePreviewResponse,
    GitStatusResponse,
    ReleaseReadinessCheck,
    ReleaseReadinessRecommendedAction,
    ReleaseReadinessResponse,
    ReleaseWorkflowVerificationRequest,
    RuntimeTelemetryResponse,
    TodayCommandCard,
    TodayConfidenceDomain,
    TodayDashboardResponse,
    TopNextAction,
    PortfolioReviewPacketListResponse,
    PortfolioReviewPacketRequest,
    PortfolioReviewPacketResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
    WorkflowTemplateResponse,
)
from buildwealth_orchestrator.services.coordinator import Coordinator
from buildwealth_orchestrator.services.copilot_runtime import (
    ConversationStore,
    FinancialCopilot,
)
from buildwealth_orchestrator.services.csv_importer import (
    apply_existing_transaction_reconciliation,
    archive_import_file,
    list_csv_templates,
    parse_transaction_csv,
)
from buildwealth_orchestrator.services.import_workbench import ImportWorkbenchStore
from buildwealth_orchestrator.services.asset_registry import AssetRegistry
from buildwealth_orchestrator.services.portfolio_audit import build_portfolio_audit_payload
from buildwealth_orchestrator.services.portfolio_analytics import build_portfolio_analytics_payload
from buildwealth_orchestrator.services.llm_clients import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    LLMProviderConfig,
    build_llm_client,
    default_base_url_for_provider,
    default_model_for_provider,
    run_tool_call_probe,
)
from buildwealth_orchestrator.services.financial_profile import (
    FinancialProfileStore,
    merge_profile_metadata,
    patch_material_profile_field_paths,
    profile_metadata_review_field_paths,
)
from buildwealth_orchestrator.services.research import OpenBBResearchService
from buildwealth_orchestrator.services.scenario_engine import (
    DEFAULT_SIMULATION_SEED,
    HISTORICAL_YEARS,
    MONTE_CARLO_VARIANT_ALIASES,
    SIMULATION_MODE_ALIASES,
    STRATEGY_ALIASES,
    ScenarioEngine,
)
from buildwealth_orchestrator.services.timeline_defaults import (
    TIMELINE_DEFAULT_IMPACT_BY_EVENT,
    TIMELINE_EVENT_TYPES,
    TIMELINE_EVENT_TYPE_VALUES,
    TIMELINE_FREQUENCIES,
    TIMELINE_IMPACT_TYPES,
    TIMELINE_IMPACT_TYPE_VALUES,
)
from buildwealth_orchestrator.services.snapshot_store import (
    SnapshotStore,
)
from buildwealth_orchestrator.services.snapshot_backfill import backfill_snapshot_history
from buildwealth_orchestrator.services.affordability import assess_affordability
from buildwealth_orchestrator.services.statement_importer import parse_statement_csv
from buildwealth_orchestrator.services.statement_vision import extract_statement_from_image
from buildwealth_orchestrator.services.portfolio_simulator import simulate_trade
from buildwealth_orchestrator.services.portfolio_fit import assess_portfolio_fit
from buildwealth_orchestrator.services.goal_tracker import compute_goal_progress
from buildwealth_orchestrator.services.financial_health import compute_financial_health
from buildwealth_orchestrator.services.peer_benchmark import build_peer_benchmark
from buildwealth_orchestrator.services.plan_tracker import compute_plan_tracking
from buildwealth_orchestrator.services.portfolio_store import PortfolioStore
from buildwealth_orchestrator.services.portfolio_review_packets import (
    PortfolioReviewPacketStore,
    build_portfolio_review_packet,
    build_portfolio_review_packet_markdown,
)
from buildwealth_orchestrator.services.contribution_rules import (
    allocate_contributions,
    build_tax_optimized_high_earner_rules,
    normalize_account_type,
    tax_treatment_for_account_type,
)
from buildwealth_orchestrator.services.income_projection import project_income_schedule
from buildwealth_orchestrator.services.expense_projection import project_expense_schedule
from buildwealth_orchestrator.services.debt_projection import project_debt_payoff
from buildwealth_orchestrator.services.social_security_projection import project_social_security_income
from buildwealth_orchestrator.services.rmd_projection import project_rmd_schedule
from buildwealth_orchestrator.services.timeline_projection import project_timeline_impacts
from buildwealth_orchestrator.services.price_updater import (
    build_snapshot_from_holdings,
    refresh_portfolio,
)
from buildwealth_orchestrator.services.portfolio_benchmark import (
    BuildWealthBenchmarkService,
)
from buildwealth_orchestrator.services.portfolio_attribution import (
    BuildWealthAttributionService,
)
from buildwealth_orchestrator.services.plan_simulation_service import BuildWealthScenarioService
from buildwealth_orchestrator.services.durable_storage import (
    DurableStorageMigrationError,
    DurableStorageMigrationNotFoundError,
    DurableStorageMigrationService,
)
from buildwealth_orchestrator.services.backup_restore import (
    BackupNotFoundError,
    BackupRestoreError,
    BackupRestoreService,
)
from buildwealth_orchestrator.services.account_data_deletion import (
    AccountDataDeletionPurgeWorker,
    RECOVERY_WINDOW_DAYS,
    build_account_data_deletion_preview,
    purge_after_for_recovery_window,
    required_confirmation_phrase,
    serialize_deletion_request,
)
from buildwealth_orchestrator.services.data_protection import (
    DataProtectionError,
    DataProtectionService,
)
from buildwealth_orchestrator.services.git_activity import GitActivityStore
from buildwealth_orchestrator.services.git_checkpoint import GitCheckpointService
from buildwealth_orchestrator.services.git_autogit import GitAutoGitService
from buildwealth_orchestrator.services.git_integration_settings import GitIntegrationSettingsStore
from buildwealth_orchestrator.services.git_repository import GitRepositoryError, GitRepositoryService
from buildwealth_orchestrator.services.git_restore_apply import GitRestoreApplyError, GitRestoreApplyService
from buildwealth_orchestrator.services.git_restore_tokens import (
    GitRestorePreviewTokenError,
    GitRestorePreviewTokenStore,
)
from buildwealth_orchestrator.services.hosted_identity import (
    HostedIdentityConfigError,
    HostedIdentityExchangeError,
    OIDCAuthProvider,
    code_challenge_for,
    generate_code_verifier,
    generate_nonce,
)
from buildwealth_orchestrator.services.versioned_workspace import (
    VersionedWorkspacePolicy,
    VersionedWorkspaceService,
)
from buildwealth_orchestrator.services.tax_engine import estimate_federal_tax
from buildwealth_orchestrator.services.today_dashboard import build_today_dashboard_payload
from buildwealth_orchestrator.services.today_review_checkpoints import TodayReviewCheckpointStore
from buildwealth_orchestrator.services.buildwealth_context import (
    DEFAULT_CONTEXT_DETAIL_LEVEL,
    DEFAULT_CONTEXT_SUMMARY_MAX_CHARS,
    DEFAULT_RESEARCH_SYMBOL_LIMIT,
    build_context_quality,
    build_context_summary_with_metadata,
    normalize_context_detail_level,
    normalize_context_warnings,
    derive_research_symbols,
    normalize_research_symbols,
    shape_context_payload,
    utc_now_iso as context_utc_now_iso,
)
from buildwealth_orchestrator.services.context_cache import ExpiringCache
from buildwealth_orchestrator.services.context_intelligence import (
    ContextAssembler,
    ContextIntelligenceService,
)
from buildwealth_orchestrator.services.embedding_clients import (
    apply_context_embedding_overrides,
    build_embedding_client_from_settings,
)
from buildwealth_orchestrator.services.auth_rate_limit import SlidingWindowRateLimiter
from buildwealth_orchestrator.services.health_report import build_health_report
from buildwealth_orchestrator.services.llm_routing import LLMRouter, extract_task_overrides
from buildwealth_orchestrator.services.llm_usage_ledger import LLMUsageLedger
from buildwealth_orchestrator.services.runtime_telemetry import (
    RuntimeTelemetryTracker,
    summarize_cache_quality,
)
from buildwealth_orchestrator.services.workflow_runner import WorkflowRunner
from buildwealth_orchestrator.services.plan_workspace import (
    PlanNotFoundError,
    PlanWorkspace,
)
from buildwealth_orchestrator.services.plan_simulation_analyzer import explain_plan_simulation
from buildwealth_orchestrator.services.plan_lever_impact import classify_plan_lever_impact
from buildwealth_orchestrator.services.plan_strategy_explainer import (
    explain_withdrawal_strategy_comparison,
)
from buildwealth_orchestrator.services.plan_saved_simulation_review import (
    compare_saved_simulation_to_current_plan,
)
from buildwealth_orchestrator.services.recommendation_inbox import (
    RecommendationInbox,
    RecommendationNotFoundError,
)
from buildwealth_orchestrator.services.recommendation_scoring import (
    normalize_recommendation_sort,
    score_and_sort_recommendations,
)
from buildwealth_orchestrator.services.recommendation_factory import (
    _closure_outcome_measured as _factory_closure_outcome_measured,
    _parse_review_date as _factory_parse_review_date,
    generate_cash_liquidity_recommendations,
    generate_plan_tracking_recommendations,
    generate_portfolio_risk_recommendations,
    generate_allocation_drift_recommendations,
    generate_due_outcome_review_recommendations,
    generate_fund_overlap_recommendations,
    generate_profile_completeness_recommendations,
    generate_research_thesis_expiration_recommendations,
    generate_stale_assumption_recommendations,
    generate_watchlist_research_recommendations,
    research_thesis_review_metadata,
)
from buildwealth_orchestrator.services.user_settings import (
    MASKED_PLACEHOLDER,
    UserSettingsStore,
    provider_default_model_ids,
)
from buildwealth_orchestrator.services.control_plane import (
    AuthenticationError,
    AuthorizationError,
    ControlPlaneStore,
    RequestContext,
)
from buildwealth_orchestrator.services.workspace_services import (
    WorkspaceServiceFactory,
    WorkspaceServices,
)
from buildwealth_orchestrator.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    await on_startup()
    try:
        yield
    finally:
        await on_shutdown()


app = FastAPI(title=settings.app_name, lifespan=_app_lifespan)

web_dir = Path(__file__).resolve().parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

web_v2_dir = Path(__file__).resolve().parent / "web-v2"
if web_v2_dir.exists():
    app.mount("/static-v2", StaticFiles(directory=str(web_v2_dir)), name="static-v2")


user_settings_store = UserSettingsStore(settings.snapshot_dir.parent / "settings" / "user_settings.json")
git_integration_settings_store = GitIntegrationSettingsStore(
    settings.git_integration_settings_path,
    default_workspace_dir=settings.versioned_workspace_dir,
)
control_plane_store = ControlPlaneStore(settings.control_db_path)
hosted_identity_provider = OIDCAuthProvider(settings)
auth_rate_limiter = SlidingWindowRateLimiter()
# The auto-created default household is a dev/local convenience (it backs
# dev auto-login). Hosted instances must start EMPTY: in secure/hosted/oidc
# modes the first real registration or IdP login creates the owner and their
# household — a pre-seeded local user would close secure-mode registration
# before anyone registered, and is a credential that nobody owns.
if str(settings.auth_mode or "dev").strip().lower() in {"dev", "test", "local", "disabled"}:
    control_plane_store.bootstrap_default_household(
        owner_email=settings.auth_dev_email,
        default_storage_root=settings.snapshot_dir.parent,
        demo_storage_root=settings.workspace_root_dir / "ws_demo_household",
    )
workspace_service_factory = WorkspaceServiceFactory(
    settings=settings,
    control_plane=control_plane_store,
)

# Apply user settings over env defaults
_user_cfg = user_settings_store.load_raw()
_user_stored_cfg = user_settings_store.load_stored_raw()
if "openai_api_key" in _user_stored_cfg and _user_cfg.get("openai_api_key"):
    settings.openai_api_key = _user_cfg["openai_api_key"]
if "openai_model" in _user_stored_cfg and _user_cfg.get("openai_model"):
    settings.openai_model = _user_cfg["openai_model"]
if "openai_base_url" in _user_stored_cfg and _user_cfg.get("openai_base_url"):
    settings.openai_base_url = _user_cfg["openai_base_url"]


def _has_user_llm_intent(stored_cfg: dict[str, Any]) -> bool:
    if stored_cfg.get("llm_settings_saved_at"):
        return True
    llm_defaults = user_settings_store.DEFAULTS
    for key in (
        "llm_provider",
        "llm_api_key",
        "llm_model",
        "llm_base_url",
        "llm_timeout_seconds",
        "llm_max_tokens",
        "llm_parallel_tool_calls",
    ):
        if key in stored_cfg and stored_cfg.get(key) != llm_defaults.get(key):
            return True
    for key in ("openai_api_key", "openai_model", "openai_base_url"):
        if key in stored_cfg and stored_cfg.get(key) != llm_defaults.get(key):
            return True
    return False


_user_llm_override_keys: set[str] = set()
if _has_user_llm_intent(_user_stored_cfg):
    _user_llm_override_keys = {
        key
        for key in _user_stored_cfg
        if key.startswith("llm_") or key.startswith("openai_")
    }

if "llm_provider" in _user_llm_override_keys and _user_cfg.get("llm_provider"):
    settings.llm_provider = _user_cfg["llm_provider"]
if "llm_api_key" in _user_llm_override_keys and _user_cfg.get("llm_api_key"):
    settings.llm_api_key = _user_cfg["llm_api_key"]
if "llm_model" in _user_llm_override_keys and _user_cfg.get("llm_model"):
    settings.llm_model = _user_cfg["llm_model"]
if "llm_base_url" in _user_llm_override_keys and _user_cfg.get("llm_base_url"):
    settings.llm_base_url = _user_cfg["llm_base_url"]
if "llm_timeout_seconds" in _user_llm_override_keys and _user_cfg.get("llm_timeout_seconds"):
    settings.llm_timeout_seconds = float(_user_cfg["llm_timeout_seconds"])
if "llm_max_tokens" in _user_llm_override_keys and _user_cfg.get("llm_max_tokens"):
    settings.llm_max_tokens = int(_user_cfg["llm_max_tokens"])
if "llm_parallel_tool_calls" in _user_llm_override_keys:
    _parallel_tool_calls = _user_cfg["llm_parallel_tool_calls"]
    if isinstance(_parallel_tool_calls, str):
        settings.llm_parallel_tool_calls = _parallel_tool_calls.strip().lower() in {"true", "1", "yes", "on"}
    else:
        settings.llm_parallel_tool_calls = bool(_parallel_tool_calls)

# Context-embedding overrides — env-driven defaults are kept if the user hasn't
# explicitly saved a value. Empty strings are treated as "use the default".
_user_context_keys = {
    key for key in _user_stored_cfg
    if key.startswith("context_embedding") or key == "context_embeddings_enabled"
}
if "context_embeddings_enabled" in _user_context_keys:
    _embeddings_enabled = _user_cfg.get("context_embeddings_enabled")
    if isinstance(_embeddings_enabled, str):
        settings.context_embeddings_enabled = _embeddings_enabled.strip().lower() in {"true", "1", "yes", "on"}
    else:
        settings.context_embeddings_enabled = bool(_embeddings_enabled)
if "context_embedding_provider" in _user_context_keys and _user_cfg.get("context_embedding_provider"):
    settings.context_embedding_provider = str(_user_cfg["context_embedding_provider"])
if "context_embedding_model" in _user_context_keys and _user_cfg.get("context_embedding_model"):
    settings.context_embedding_model = str(_user_cfg["context_embedding_model"])
if "context_embedding_base_url" in _user_context_keys and _user_cfg.get("context_embedding_base_url"):
    settings.context_embedding_base_url = str(_user_cfg["context_embedding_base_url"])
if "context_embedding_timeout_seconds" in _user_context_keys:
    _timeout = _user_cfg.get("context_embedding_timeout_seconds")
    try:
        settings.context_embedding_timeout_seconds = float(_timeout) if _timeout is not None else settings.context_embedding_timeout_seconds
    except (TypeError, ValueError):
        pass


def _auth_mode() -> str:
    return str(settings.auth_mode or "dev").strip().lower()


def _local_auth_enabled() -> bool:
    # "secure" is the private hosted-instance mode: password registration and
    # login stay enabled (no identity provider required yet), while cookies
    # are Secure and CSRF is enforced — see _session_cookie_kwargs and
    # require_csrf. "hosted"/"oidc" replace local login with the IdP.
    return _auth_mode() in {"dev", "test", "local", "secure"}


def _hosted_auth_enabled() -> bool:
    return _auth_mode() in {"hosted", "oidc"} and hosted_identity_provider.is_configured()


def _safe_post_login_redirect(value: str | None = None) -> str:
    redirect_to = str(value or settings.auth_post_login_redirect_path or "/v2").strip()
    if not redirect_to.startswith("/") or redirect_to.startswith("//") or "\r" in redirect_to or "\n" in redirect_to:
        return "/v2"
    return redirect_to


def _auth_error_redirect(message: str, *, status_code: int = 307) -> RedirectResponse:
    detail = str(message or "Hosted sign-in could not be completed.").strip()
    params = urlencode({"auth_error": detail[:180]})
    return RedirectResponse(url=f"/v2?{params}", status_code=status_code)


def _hosted_logout_redirect_url() -> str:
    logout_url = str(settings.auth_oidc_logout_url or "").strip()
    if not logout_url:
        return ""
    params: dict[str, str] = {}
    post_logout_redirect_uri = str(settings.auth_post_logout_redirect_uri or "").strip()
    if post_logout_redirect_uri:
        params["post_logout_redirect_uri"] = post_logout_redirect_uri
    client_id = str(settings.auth_oidc_client_id or "").strip()
    if client_id:
        params["client_id"] = client_id
    if not params:
        return logout_url
    separator = "&" if "?" in logout_url else "?"
    return f"{logout_url}{separator}{urlencode(params)}"


def _session_cookie_kwargs() -> dict[str, Any]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": _auth_mode() not in {"dev", "test", "local", "disabled"},
        "max_age": max(1, int(settings.auth_session_days)) * 24 * 60 * 60,
        "path": "/",
    }


def get_request_context(request: Request) -> RequestContext:
    requested_workspace_id = (
        request.headers.get("x-buildwealth-workspace-id")
        or request.query_params.get("workspace_id")
        or None
    )
    token = request.cookies.get(settings.auth_session_cookie_name) or ""
    mode = _auth_mode()
    try:
        if token:
            return control_plane_store.request_context_for_token(
                token=token,
                auth_mode=mode,
                requested_workspace_id=requested_workspace_id,
            )
        if mode in {"dev", "test", "disabled"}:
            return control_plane_store.dev_request_context(
                auth_mode=mode,
                requested_workspace_id=requested_workspace_id,
            )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise HTTPException(status_code=401, detail="Authentication required")


def get_authenticated_account_user(request: Request) -> dict[str, Any]:
    token = request.cookies.get(settings.auth_session_cookie_name) or ""
    mode = _auth_mode()
    try:
        if token:
            return control_plane_store.authenticated_user_for_token(token=token)
        if mode in {"dev", "test", "disabled"}:
            return control_plane_store.default_dev_user()
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    raise HTTPException(status_code=401, detail="Authentication required")


def purge_due_account_data_deletions(*, due_at: str | None = None, limit: int = 20) -> dict[str, Any]:
    return AccountDataDeletionPurgeWorker(
        control_plane=control_plane_store,
        workspace_service_factory=workspace_service_factory,
    ).purge_due(due_at=due_at, limit=limit)


def _audit_event(action: str, **kwargs: Any) -> None:
    """Best-effort security audit trail — a failed audit write must never
    turn into a failed request."""
    try:
        control_plane_store.record_audit_event(action=action, **kwargs)
    except Exception:
        pass


def _client_ip(request: Request | None) -> str:
    """Client address for rate limiting. Behind the production proxy the
    socket peer is Caddy, which sets X-Forwarded-For; the first entry is the
    client. Best-effort — rate limiting blunts abuse, it isn't identity."""
    if request is None:
        return "unknown"
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _auth_rate_limits_enforced() -> bool:
    return _auth_mode() not in {"dev", "test", "disabled"}


def _enforce_auth_rate_limit(request: Request, *, key: str, limit: int, window_seconds: float, action: str) -> None:
    if not _auth_rate_limits_enforced():
        return
    allowed, retry_after = auth_rate_limiter.allow(key, limit=limit, window_seconds=window_seconds)
    if allowed:
        return
    _audit_event(
        "auth.rate_limited",
        outcome="denied",
        target_type="rate_limit",
        target_id=action,
        metadata_json=json.dumps({"key": key, "retry_after_seconds": retry_after}),
    )
    raise HTTPException(
        status_code=429,
        detail="Too many attempts. Try again shortly.",
        headers={"Retry-After": str(retry_after)},
    )


def require_permission(context: RequestContext, permission: str) -> None:
    if permission not in context.permissions:
        _audit_event(
            "permission.denied",
            actor_user_id=context.user_id,
            organization_id=context.organization_id,
            workspace_id=context.workspace_id,
            target_type="permission",
            target_id=permission,
            outcome="denied",
        )
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")


def require_csrf(request: Request) -> None:
    mode = _auth_mode()
    if mode in {"dev", "test", "disabled"}:
        return
    session_token = request.cookies.get(settings.auth_session_cookie_name) or ""
    csrf_token = request.headers.get("x-buildwealth-csrf-token") or ""
    if not control_plane_store.verify_csrf_token(
        session_token=session_token,
        csrf_token=csrf_token,
    ):
        _audit_event(
            "csrf.rejected",
            outcome="denied",
            target_type="request",
            target_id=str(request.url.path),
            metadata_json=json.dumps({"ip": _client_ip(request)}),
        )
        raise HTTPException(status_code=403, detail="CSRF token is missing or invalid")


def get_workspace_services(
    context: RequestContext = Depends(get_request_context),
) -> WorkspaceServices:
    return workspace_service_factory.for_context(context)


def get_current_request(request: Request) -> Request:
    return request


def workspace_services_or_legacy(candidate: Any) -> Any:
    if candidate is None:
        candidate = current_copilot_workspace_services.get()
    if isinstance(candidate, WorkspaceServices) or hasattr(candidate, "context"):
        return candidate
    from types import SimpleNamespace

    return SimpleNamespace(
        record=SimpleNamespace(id="legacy"),
        context=SimpleNamespace(permissions=ControlPlaneStore.OWNER_PERMISSIONS),
        settings_store=user_settings_store,
        financial_profile_store=financial_profile_store,
        portfolio_store=portfolio_store,
        snapshot_store=snapshot_store,
        plan_workspace=plan_workspace,
        recommendation_inbox=recommendation_inbox,
        import_workbench_store=import_workbench_store,
        conversation_store=conversation_store,
        context_intelligence_service=context_intelligence_service,
        today_review_checkpoint_store=today_review_checkpoint_store,
    )


def route_workspace_services(
    candidate: Any,
    *,
    permission: str,
    http_request: Request | None = None,
    require_write_token: bool = False,
) -> Any:
    resolved_services = workspace_services_or_legacy(candidate)
    if require_write_token and hasattr(http_request, "headers"):
        require_csrf(http_request)
    require_permission(resolved_services.context, permission)
    return resolved_services


def durable_storage_service_for_workspace(services: Any) -> DurableStorageMigrationService:
    paths = getattr(services, "paths", None)
    if paths is None:
        return durable_storage_service
    return DurableStorageMigrationService(
        data_root=paths.root,
        storage_dir=paths.durable_storage_dir,
        include_paths=[
            paths.portfolio_dir,
            paths.snapshot_dir,
            paths.conversation_dir,
            paths.plans_dir,
            paths.profile_path,
            paths.recommendations_path,
        ],
    )


def backup_restore_service_for_workspace(services: Any) -> BackupRestoreService:
    paths = getattr(services, "paths", None)
    if paths is None:
        return backup_restore_service
    return BackupRestoreService(data_root=paths.root, backup_dir=paths.backup_archive_dir)


def data_protection_service_for_workspace(services: Any) -> DataProtectionService:
    paths = getattr(services, "paths", None)
    if paths is None:
        return data_protection_service
    return DataProtectionService(
        policy_path=paths.protection_policy_path,
        sensitive_paths=[
            paths.portfolio_dir,
            paths.snapshot_dir,
            paths.conversation_dir,
            paths.plans_dir,
            paths.profile_path,
            paths.recommendations_path,
            paths.settings_path.parent,
            paths.durable_storage_dir,
        ],
        backup_dir=paths.backup_archive_dir,
    )


def _seed_demo_workspace_data(workspace_root: Path) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parents[4] / "scripts" / "seed-demo-data.py"
    if not script_path.exists():
        raise RuntimeError("Demo seed script was not found")
    spec = importlib.util.spec_from_file_location("buildwealth_demo_seed", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Demo seed script could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seed_demo_dataset = getattr(module, "seed_demo_dataset", None)
    if not callable(seed_demo_dataset):
        raise RuntimeError("Demo seed function was not found")
    return seed_demo_dataset(workspace_root, include_settings=False)


snapshot_store = SnapshotStore(settings.snapshot_dir)
portfolio_store = PortfolioStore(settings.snapshot_dir.parent / "portfolio")
asset_registry = AssetRegistry(portfolio_store)
today_review_checkpoint_store = TodayReviewCheckpointStore(settings.today_review_checkpoint_path)
durable_storage_service = DurableStorageMigrationService.from_settings(settings)
backup_restore_service = BackupRestoreService.from_settings(settings)
data_protection_service = DataProtectionService.from_settings(settings)
portfolio_review_packet_store = PortfolioReviewPacketStore(settings.portfolio_review_packet_dir)
import_workbench_store = ImportWorkbenchStore(
    workbench_dir=settings.import_workbench_dir,
    reports_dir=settings.import_reports_dir,
)


def git_integration_settings_store_for_workspace(services: Any) -> GitIntegrationSettingsStore:
    paths = getattr(services, "paths", None)
    if paths is None:
        return git_integration_settings_store
    return GitIntegrationSettingsStore(
        paths.settings_path.with_name("git_integration.json"),
        default_workspace_dir=paths.root / "versioned",
    )


def _git_policy(services: Any | None = None) -> dict[str, Any]:
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    return git_integration_settings_store_for_workspace(resolved_services).load()


def _versioned_workspace_service(
    policy: dict[str, Any],
    services: Any | None = None,
) -> VersionedWorkspaceService:
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    paths = getattr(resolved_services, "paths", None)
    if paths is not None:
        return VersionedWorkspaceService(
            workspace_dir=Path(str(policy.get("workspace_dir") or paths.root / "versioned")),
            plans_dir=paths.plans_dir,
            recommendations_path=paths.recommendations_path,
            review_packet_dir=paths.portfolio_review_packet_dir,
            protection_policy_path=paths.protection_policy_path,
            financial_profile_path=paths.profile_path,
        )
    return VersionedWorkspaceService(
        workspace_dir=Path(str(policy.get("workspace_dir") or settings.versioned_workspace_dir)),
        plans_dir=settings.plans_dir,
        recommendations_path=settings.recommendations_path,
        review_packet_dir=settings.portfolio_review_packet_dir,
        protection_policy_path=settings.protection_policy_path,
        financial_profile_path=settings.financial_profile_path,
    )


def _git_repository_service(
    policy: dict[str, Any],
    services: Any | None = None,
) -> GitRepositoryService:
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    paths = getattr(resolved_services, "paths", None)
    default_workspace_dir = paths.root / "versioned" if paths is not None else settings.versioned_workspace_dir
    return GitRepositoryService(Path(str(policy.get("workspace_dir") or default_workspace_dir)))


def _git_checkpoint_service(
    policy: dict[str, Any],
    services: Any | None = None,
) -> GitCheckpointService:
    workspace_service = _versioned_workspace_service(policy, services=services)
    return GitCheckpointService(
        workspace_service=workspace_service,
        git_repository=_git_repository_service(policy, services=services),
    )


def _git_restore_apply_service(
    policy: dict[str, Any],
    services: Any | None = None,
) -> GitRestoreApplyService:
    resolved_services = workspace_services_or_legacy(services)
    return GitRestoreApplyService(
        git_repository=_git_repository_service(policy, services=resolved_services),
        checkpoint_service=_git_checkpoint_service(policy, services=resolved_services),
        workspace_policy=_git_workspace_policy(policy),
        plan_workspace=resolved_services.plan_workspace,
        recommendation_inbox=resolved_services.recommendation_inbox,
        review_packet_store=getattr(
            resolved_services,
            "portfolio_review_packet_store",
            portfolio_review_packet_store,
        ),
    )


def _git_activity_store(services: Any | None = None) -> GitActivityStore:
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    paths = getattr(resolved_services, "paths", None)
    settings_path = (
        paths.settings_path.with_name("git_activity.jsonl")
        if paths is not None
        else settings.git_integration_settings_path.with_name("git_activity.jsonl")
    )
    return GitActivityStore(settings_path)


def _git_restore_preview_token_store(services: Any | None = None) -> GitRestorePreviewTokenStore:
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    paths = getattr(resolved_services, "paths", None)
    settings_path = (
        paths.settings_path.with_name("git_restore_preview_tokens.jsonl")
        if paths is not None
        else settings.git_integration_settings_path.with_name("git_restore_preview_tokens.jsonl")
    )
    return GitRestorePreviewTokenStore(
        settings_path
    )


def _git_autogit_service(
    policy: dict[str, Any],
    services: Any | None = None,
) -> GitAutoGitService:
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    paths = getattr(resolved_services, "paths", None)
    state_path = (
        paths.settings_path.with_name("git_autogit_state.json")
        if paths is not None
        else settings.git_integration_settings_path.with_name("git_autogit_state.json")
    )
    return GitAutoGitService(
        state_path=state_path,
        checkpoint_service=_git_checkpoint_service(policy, services=resolved_services),
    )


def _git_workspace_policy(policy: dict[str, Any]) -> VersionedWorkspacePolicy:
    return VersionedWorkspacePolicy.from_settings(policy)


def _queue_autogit_event(event_type: str) -> None:
    try:
        policy = _git_policy()
        _git_autogit_service(policy).record_event(policy=policy, event_type=event_type)
    except Exception:
        # AutoGit should never block the canonical write path.
        pass


def _run_due_autogit(services: Any | None = None) -> dict[str, Any]:
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    policy = _git_policy(resolved_services)
    state = _git_autogit_service(policy, services=resolved_services).run_due(
        policy=policy,
        workspace_policy=_git_workspace_policy(policy),
    )
    if state.get("status") not in {"idle", "pending", "disabled"} and state.get("last_result"):
        result = state["last_result"]
        _git_activity_store(resolved_services).record(
            event_type="autogit",
            title=f"AutoGit {result.get('status') or state.get('status') or 'ran'}",
            message=str(result.get("message") or ""),
            status=str(result.get("status") or state.get("status") or "ok"),
            ref=(result.get("commit") or {}).get("hash") if isinstance(result.get("commit"), dict) else None,
            metadata={
                "event_type": result.get("event_type"),
                "event_count": result.get("event_count"),
            },
        )
    return state


scenario_engine = ScenarioEngine(
    years_to_retirement=settings.planner_years_to_retirement,
    annual_contribution_usd=settings.planner_annual_contribution_usd,
    baseline_return=settings.planner_expected_return_baseline,
    optimistic_return=settings.planner_expected_return_optimistic,
    conservative_return=settings.planner_expected_return_conservative,
    return_volatility=settings.planner_return_volatility,
    inflation=settings.planner_inflation,
    monte_carlo_runs=settings.planner_monte_carlo_runs,
    hsa_delta_default=settings.planner_hsa_delta_default,
    marginal_tax_rate=settings.planner_marginal_tax_rate,
)
research_service = OpenBBResearchService(provider=settings.openbb_provider)
benchmark_service = BuildWealthBenchmarkService(
    snapshot_store=snapshot_store,
    research_service=research_service,
    base_currency=settings.app_currency,
)
attribution_service = BuildWealthAttributionService(
    portfolio_store=portfolio_store,
    base_currency=settings.app_currency,
)


def benchmark_service_for_workspace(services: WorkspaceServices) -> BuildWealthBenchmarkService:
    return BuildWealthBenchmarkService(
        snapshot_store=services.snapshot_store,
        research_service=research_service,
        base_currency=settings.app_currency,
    )


def attribution_service_for_workspace(services: WorkspaceServices) -> BuildWealthAttributionService:
    return BuildWealthAttributionService(
        portfolio_store=services.portfolio_store,
        base_currency=settings.app_currency,
    )
plan_simulation_service = BuildWealthScenarioService(
    scenario_engine=scenario_engine,
)
coordinator = Coordinator()
conversation_store = ConversationStore(settings.conversation_dir)
plan_workspace = PlanWorkspace(settings.plans_dir)
financial_profile_store = FinancialProfileStore(settings.financial_profile_path)
recommendation_inbox = RecommendationInbox(settings.recommendations_path)
context_intelligence_service = ContextIntelligenceService.from_settings(
    settings,
    financial_profile_store=financial_profile_store,
    plan_workspace=plan_workspace,
    recommendation_inbox=recommendation_inbox,
    portfolio_store=portfolio_store,
    embedding_client=build_embedding_client_from_settings(settings),
)
context_assembler = ContextAssembler(context_service=context_intelligence_service)
workflow_runner = WorkflowRunner(
    scenario_engine=scenario_engine,
    default_annual_contribution_usd=settings.planner_annual_contribution_usd,
    default_years=settings.planner_years_to_retirement,
    default_hsa_delta=settings.planner_hsa_delta_default,
)


def _llm_config_from_payload(
    payload: dict[str, Any],
    explicit_keys: set[str] | None = None,
) -> LLMProviderConfig:
    def coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off"}:
                return False
        return default

    explicit = explicit_keys if explicit_keys is not None else {
        key
        for key, value in payload.items()
        if value not in ("", None)
    }
    provider = str(payload.get("llm_provider") or settings.llm_provider or "openai")
    legacy_api_key = payload.get("openai_api_key") or settings.openai_api_key
    legacy_model = payload.get("openai_model") or settings.openai_model or DEFAULT_OPENAI_MODEL
    legacy_base_url = payload.get("openai_base_url") or settings.openai_base_url or DEFAULT_OPENAI_BASE_URL
    if "llm_model" in explicit and payload.get("llm_model"):
        model = str(payload["llm_model"])
    else:
        model = str(legacy_model if provider == "openai" else default_model_for_provider(provider))
    if "llm_base_url" in explicit and payload.get("llm_base_url"):
        base_url = str(payload["llm_base_url"])
    else:
        base_url = str(legacy_base_url if provider == "openai" else default_base_url_for_provider(provider))
    return LLMProviderConfig(
        provider=provider,
        api_key=str(payload.get("llm_api_key") or legacy_api_key or ""),
        model=model,
        base_url=base_url,
        timeout_seconds=float(payload.get("llm_timeout_seconds") or settings.llm_timeout_seconds),
        max_tokens=int(payload.get("llm_max_tokens") or settings.llm_max_tokens),
        parallel_tool_calls=coerce_bool(
            payload.get("llm_parallel_tool_calls", settings.llm_parallel_tool_calls),
            settings.llm_parallel_tool_calls,
        ),
    )


_initial_llm_payload = {
    "llm_provider": settings.llm_provider,
    "llm_api_key": settings.llm_api_key,
    "llm_model": settings.llm_model,
    "llm_base_url": settings.llm_base_url,
    "llm_timeout_seconds": settings.llm_timeout_seconds,
    "llm_max_tokens": settings.llm_max_tokens,
    "llm_parallel_tool_calls": settings.llm_parallel_tool_calls,
    "openai_api_key": settings.openai_api_key,
    "openai_model": settings.openai_model,
    "openai_base_url": settings.openai_base_url,
}
for _key in _user_llm_override_keys:
    if _key in _user_cfg:
        _initial_llm_payload[_key] = _user_cfg[_key]
_initial_llm_explicit_keys = {
    key
    for key, value in _initial_llm_payload.items()
    if value not in ("", None)
} | _user_llm_override_keys
# Router owns per-task model resolution; the chat client is what the
# interactive Copilot uses and stays the default for everything unrouted.
# The usage ledger meters every routed completion locally.
llm_usage_ledger = LLMUsageLedger(settings.durable_storage_dir / "llm_usage_ledger.json")
llm_router = LLMRouter(
    _llm_config_from_payload(
        _initial_llm_payload,
        explicit_keys=_initial_llm_explicit_keys,
    ),
    extract_task_overrides(_user_cfg),
    usage_ledger=llm_usage_ledger,
)
llm_client = llm_router.client_for("chat")
copilot = FinancialCopilot(
    conversation_store=conversation_store,
    llm_client=llm_client,
    max_history_messages=settings.copilot_max_history_messages,
    max_tool_rounds=settings.copilot_max_tool_rounds,
    system_prompt=(
        "You are BuildWealth Copilot, a personal financial research and planning assistant.\n\n"
        "CORE PRINCIPLES:\n"
        "- Always use tools to ground answers in real data before making claims.\n"
        "- Be explicit about assumptions and uncertainty.\n"
        "- Do not provide legal or tax advice; provide analytical insights and scenarios.\n\n"
        "TOOL SELECTION GUIDE:\n"
        "- For a full cross-domain briefing (portfolio + plan + research + open decisions) → call get_buildwealth_context.\n"
        "- Default chat context includes Context Intelligence `retrieved_context`, `citations`, `conflicts`, "
        "`context_budget`, and `trace`; use those citations when explaining what you relied on.\n"
        "- If `conflicts` are present, explain them in plain language and avoid decision-grade advice until material "
        "items are resolved or confirmed.\n"
        "- After calling get_buildwealth_context, inspect `quality` and `warnings` fields before making recommendations. "
        "If `quality.freshness.snapshot_stale=true` or coverage is missing sections, call that out clearly and suggest refresh actions.\n"
        "- For 'how am I doing?' or 'what is my financial situation?' → call get_financial_health first.\n"
        "- For profile onboarding or filling out missing profile fields → call get_onboarding_status, "
        "ask one focused question at a time, then call draft_financial_profile_update before saving. "
        "Only call update_financial_profile after the user explicitly confirms the drafted changes.\n"
        "- Do not call draft_financial_profile_update just because the user casually mentions a possible profile fact. "
        "Treat incidental chat facts as unconfirmed; ask whether the user wants to review or update the profile first.\n"
        "- For account-level balances/cash breakdowns → call get_account_balances.\n"
        "- For allocation mix or rebalancing discussions → call get_asset_allocation.\n"
        "- For 'can I afford X?' → call assess_affordability with the monthly cost or purchase price. "
        "It computes the full impact on cash flow, savings rate, and DTI automatically.\n"
        "- For 'am I on track?' → call get_plan_tracking for plan assumptions, or get_goal_progress for specific goals.\n"
        "- For 'when will I reach my goal?' or 'what do I need to save?' → call get_goal_progress.\n"
        "- For federal tax estimates (income, capital gains, withholding) → call compute_tax.\n"
        "- For bounded Plan review from v2 Plan → call get_plan_review_context before discussing assumptions, "
        "scenario diffs, linked artifacts, or Plan health. Do not pull full artifact contents unless the user opens one.\n"
        "- For plan contribution allocation rules and defaults → call set_contribution_rules "
        "(or get_plan_contribution_rules to inspect current rules).\n"
        "- For comparing retirement withdrawal strategies across outcomes → call compare_withdrawal_strategies.\n"
        "- For adding a dated plan event (windfall, purchase, job change, retirement) → call add_timeline_event.\n"
        "- For 'what if I change my contributions?' → call run_plan_scenario_diff.\n"
        "- For life-event what-ifs (job loss, raise, new recurring costs) → call run_plan_scenario_branch.\n"
        "- For reusable life-event presets/templates → call get_plan_branch_templates or update_plan_branch_templates.\n"
        "- To move research watchlist thesis into planning branches → call pin_watchlist_research_to_plan.\n"
        "- For 'what should I do?' → call get_today_dashboard and list_recommendations.\n"
        "- Before applying a high-impact recommendation → call preview_recommendation to inspect scenario and action effects.\n"
        "- After recommendations are applied/rejected, record realized outcomes → call update_recommendation_outcome.\n"
        "- For recommendation calibration and closure tracking quality → call get_recommendation_closure_analytics.\n"
        "- To persist plan-scoped closure calibration reviews as artifacts/decision-log entries → "
        "call create_plan_recommendation_closure_summary.\n"
        "- For stock/investment research on one ticker → call research_quote or research_price_history.\n"
        "- For comparing multiple investment candidates → call research_compare, "
        "then call simulate_trade to show how a chosen trade would affect portfolio allocation.\n"
        "- For structured multi-symbol research memos with thesis/risks/catalysts and plan artifacts → call research_dossier.\n"
        "- To reuse saved dossier evidence and artifact references for recommendation rationale → call research_dossier_lookup.\n"
        "- For ranking watchlist candidates by momentum/trend/target/data quality → call research_watchlist_rank.\n"
        "- After an investment-fit discussion identifies a safe next review step, call "
        "draft_investment_research_recommendation to create a proposed review-only Inbox item. "
        "Never use it to create buy/sell instructions.\n"
        "- To revise a saved watchlist thesis, call draft_watchlist_thesis_revision for user review without saving. "
        "Only save thesis revisions after explicit user confirmation.\n"
        "- To revise a saved research dossier thesis, call draft_dossier_thesis_revision for user review without saving. "
        "Only save dossier thesis revisions after explicit user confirmation.\n"
        "- For 'what if I buy/sell X?' → call simulate_trade to show allocation and concentration impact.\n"
        "- For Import & Review evidence → call list_import_reports or get_import_report and cite the Import Report ID.\n"
        "- For daily reviews → call get_financial_health, get_plan_tracking, and get_today_dashboard.\n\n"
        "RESPONSE GUIDELINES:\n"
        "- Explicitly caveat recommendations when context quality is degraded (stale snapshot, missing coverage sections, or warning-heavy payloads).\n"
        "- If context quality is degraded, include the exact mitigation step (for example: run sync, use live snapshot, or refresh context).\n"
        "- When discussing portfolio holdings, reference specific symbols and allocation percentages.\n"
        "- When discussing cash flow, cite monthly income, expenses, and surplus figures.\n"
        "- When recommending actions, explain the quantitative impact (e.g., 'increasing contributions by "
        "$200/month would add ~$X to your projected retirement value').\n"
        "- For research-backed recommendations, include dossier artifact citations in recommendation evidence "
        "(symbols + artifact references).\n"
        "- Cite native evidence IDs when they matter: Simulation Run IDs, Saved Simulation IDs, Portfolio History transaction/import links, and Import Report IDs.\n"
        "- Keep Copilot as a draft and review helper. Do not present a mutation as complete unless a reviewed tool/API call actually completed.\n"
        "- Proactively flag risks you discover (high concentration, low emergency fund, negative cash flow)."
    ),
)
copilot_context_research_cache = ExpiringCache(max_entries=settings.copilot_context_cache_max_entries)
copilot_context_projection_cache = ExpiringCache(max_entries=settings.copilot_context_cache_max_entries)
current_copilot_workspace_services: ContextVar[WorkspaceServices | None] = ContextVar(
    "current_copilot_workspace_services",
    default=None,
)


def has_active_copilot_workspace_context() -> bool:
    return current_copilot_workspace_services.get() is not None


def resolve_copilot_tool_plan_id(
    requested_plan_id: object | None,
    *,
    services: WorkspaceServices,
) -> str:
    if has_active_copilot_workspace_context():
        return resolve_plan_id_or_active(requested_plan_id, workspace=services.plan_workspace)
    return resolve_plan_id_or_active(requested_plan_id)


today_research_evidence_cache = ExpiringCache(max_entries=64)
runtime_telemetry_tracker = RuntimeTelemetryTracker()

sync_lock = asyncio.Lock()
scheduler_task: asyncio.Task | None = None
autogit_task: asyncio.Task | None = None
sync_state: dict[str, object] = {
    "running": False,
    "runs_total": 0,
    "runs_failed": 0,
    "last_trigger": None,
    "last_started_at": None,
    "last_completed_at": None,
    "last_error": None,
    "last_snapshot_path": None,
    "last_plan_export_path": None,
}


@app.middleware("http")
async def telemetry_latency_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or path.startswith("/api/telemetry/"):
        return await call_next(request)

    started_at = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)
        runtime_telemetry_tracker.record_api_latency(
            method=request.method,
            path=str(route_path or path),
            status_code=int(getattr(response, "status_code", 500)),
            latency_ms=elapsed_ms,
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def build_live_snapshot(
    store: PortfolioStore | None = None,
) -> PortfolioSnapshot:
    """Refresh prices from OpenBB and build a snapshot from local portfolio store."""
    resolved_store = store or portfolio_store
    try:
        holdings_data = await refresh_portfolio(resolved_store, research_service)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Price refresh failed: {exc}") from exc
    return build_snapshot_from_holdings(holdings_data)


def get_sync_status() -> SyncStatusResponse:
    return SyncStatusResponse(**sync_state)


async def execute_sync(
    trigger: str,
    *,
    store: PortfolioStore | None = None,
    snapshots: SnapshotStore | None = None,
) -> dict[str, str | dict[str, str]]:
    resolved_store = store or portfolio_store
    resolved_snapshot_store = snapshots or snapshot_store
    async with sync_lock:
        sync_state["running"] = True
        sync_state["last_trigger"] = trigger
        sync_state["last_started_at"] = utc_now()
        sync_state["last_error"] = None

        try:
            snapshot = await build_live_snapshot(resolved_store)
            snapshot_path = resolved_snapshot_store.write(snapshot)

            sync_state["last_snapshot_path"] = str(snapshot_path)
            sync_state["last_completed_at"] = utc_now()

            return {
                "snapshot": str(snapshot_path),
            }
        except Exception as exc:
            sync_state["runs_failed"] = int(sync_state["runs_failed"]) + 1
            sync_state["last_error"] = str(exc)
            sync_state["last_completed_at"] = utc_now()
            raise
        finally:
            sync_state["runs_total"] = int(sync_state["runs_total"]) + 1
            sync_state["running"] = False


def restore_sync_state_from_disk(snapshots: SnapshotStore | None = None) -> bool:
    """Seed in-memory sync state from the newest snapshot on disk.

    sync_state resets on every restart; without this, status surfaces claim
    'never synced' while snapshots on disk prove otherwise — a small lie
    that costs trust. Returns True when a prior sync was restored.
    """
    resolved = snapshots or snapshot_store
    try:
        latest = resolved.latest()
    except Exception:
        return False
    as_of = latest.as_of if latest.as_of.tzinfo is not None else latest.as_of.replace(tzinfo=timezone.utc)
    sync_state["last_trigger"] = "restored"
    sync_state["last_completed_at"] = as_of
    sync_state["last_snapshot_path"] = None
    return True


def snapshot_age_seconds(snapshots: SnapshotStore | None = None) -> float | None:
    """Age of the latest snapshot, or None when no snapshot exists yet."""
    resolved = snapshots or snapshot_store
    try:
        as_of = resolved.latest().as_of
    except Exception:
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    return max(0.0, (utc_now() - as_of).total_seconds())


def scheduled_sync_is_due(age_seconds: float | None, interval_seconds: float) -> bool:
    return age_seconds is None or age_seconds >= interval_seconds


async def scheduled_sync_loop() -> None:
    """Heartbeat: keep prices and snapshots no staler than the sync interval.

    Wakes hourly (or faster for short intervals) and syncs only when the
    latest snapshot has aged past the interval — so restarts and laptop
    sleeps self-heal stale data without hammering market-data providers.
    """
    interval_seconds = max(60, int(settings.sync_interval_minutes * 60))
    poll_seconds = min(interval_seconds, 3600)

    while True:
        if scheduled_sync_is_due(snapshot_age_seconds(), interval_seconds):
            try:
                await execute_sync(trigger="scheduled")
            except Exception:
                # Failures are captured in sync_state for observability.
                pass
            try:
                # Measure first, nag second: outcomes the app can record
                # itself never become review entries in the Inbox.
                sweep_auto_measure_outcomes()
            except Exception:
                # Best-effort: sweeps must never kill the heartbeat.
                pass
            try:
                sweep_due_outcome_reviews()
            except Exception:
                pass
            try:
                sweep_allocation_drift()
            except Exception:
                pass

        await asyncio.sleep(poll_seconds)


def sweep_auto_measure_outcomes(*, limit: int = 10, now: datetime | None = None) -> int:
    """Record auto-measured outcomes for decisions whose review date passed.

    The outcome loop only teaches the ranking if outcomes actually get
    recorded, and most households will never fill a measurement form. When a
    decision's pre-mortem review date passes unmeasured and portfolio history
    can measure the observable delta, the heartbeat records it as the
    realized outcome — labeled as auto-measured with the attribution caveat
    (a portfolio delta includes contributions and market moves, not only the
    decision's effect), and a human can edit or override it at any time.

    Runs BEFORE sweep_due_outcome_reviews on purpose: what the app can
    measure itself never becomes a nag in the Inbox.
    """
    resolved_now = now or datetime.now(timezone.utc)
    measured = 0
    rows = recommendation_inbox.list(limit=None, status="applied", plan_id=None, sort="none")
    for row in rows:
        if measured >= max(1, limit):
            break
        action_payload = row.get("action_payload")
        closure = action_payload.get("decision_closure") if isinstance(action_payload, dict) else None
        if not isinstance(closure, dict):
            continue
        if str(closure.get("decision_status") or "").strip() != "accepted":
            continue
        if _factory_closure_outcome_measured(closure):
            continue
        pre_mortem = closure.get("pre_mortem")
        if not isinstance(pre_mortem, dict):
            continue
        review_date = _factory_parse_review_date(pre_mortem.get("review_date"))
        if review_date is None or review_date > resolved_now:
            continue

        recommendation_id = str(row.get("id") or "").strip()
        if not recommendation_id:
            continue
        try:
            prefill = build_recommendation_outcome_prefill_payload(recommendation_id, now=resolved_now)
        except Exception:
            continue
        if prefill.status != "ready" or prefill.suggested_future_value_delta_usd is None:
            continue

        try:
            update_recommendation_outcome(
                recommendation_id,
                RecommendationOutcomeUpdateRequest(
                    realized_delta_future_value_usd=prefill.suggested_future_value_delta_usd,
                    observed_at=resolved_now,
                    observation_window_days=prefill.observation_window_days,
                    measurement_source=f"auto:{prefill.measurement_source}",
                    note=(
                        "Measured automatically from portfolio history. This is the "
                        "observable portfolio change over the review window — it includes "
                        "contributions and market moves, not only this decision. Edit the "
                        "outcome if the attribution looks wrong."
                    ),
                ),
            )
        except Exception:
            continue
        measured += 1
    return measured


def sweep_due_outcome_reviews() -> int:
    """Turn due, unmeasured pre-mortem reviews into Inbox entries.

    Runs on the heartbeat for the default household workspace so review
    dates surface without requiring a visit to Today.
    """
    existing = recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_due_outcome_review_recommendations(
        existing_recommendations=existing,
        creator=recommendation_inbox,
        dry_run=False,
    )
    return len(result.created)


def sweep_allocation_drift() -> int:
    """Surface target-allocation drift in the Inbox on the heartbeat.

    Same contract as the outcome sweep: default household workspace,
    dedupe keys prevent nagging, silence when no targets are set.
    """
    profile_payload = get_financial_profile_payload(financial_profile_store)
    investment_policy = (
        profile_payload.get("investment_policy")
        if isinstance(profile_payload.get("investment_policy"), dict)
        else {}
    )
    existing = recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_allocation_drift_recommendations(
        holdings_payload=portfolio_store.get_holdings(),
        investment_policy=investment_policy,
        existing_recommendations=existing,
        creator=recommendation_inbox,
        dry_run=False,
    )
    return len(result.created)


async def autogit_checkpoint_loop() -> None:
    while True:
        try:
            _run_due_autogit()
        except Exception:
            # AutoGit failures are captured in the AutoGit state when possible.
            pass

        await asyncio.sleep(5)



def resolve_import_path(
    path_value: str,
    *,
    import_inbox_dir: Path | None = None,
    workspace_root: Path | None = None,
) -> Path:
    inbox_dir = import_inbox_dir or settings.import_inbox_dir
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (inbox_dir / candidate).resolve()

    if workspace_root is not None:
        resolved_root = workspace_root.resolve()
        try:
            resolved.relative_to(resolved_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Import file must belong to the active workspace") from exc

    return resolved



def normalize_upload_filename(file_name: str) -> str:
    stripped = Path(file_name).name
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", stripped)
    return safe or "upload.csv"



def unique_inbox_path(base_name: str, *, import_inbox_dir: Path | None = None) -> Path:
    inbox_dir = import_inbox_dir or settings.import_inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    candidate = inbox_dir / base_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix or ".csv"
    index = 1

    while True:
        with_index = inbox_dir / f"{stem}-{index}{suffix}"
        if not with_index.exists():
            return with_index
        index += 1


async def execute_csv_import(
    file_path: Path,
    request: CsvImportRequest,
    *,
    services: WorkspaceServices | None = None,
) -> CsvImportResponse:
    if len(request.delimiter) != 1:
        raise HTTPException(status_code=400, detail="Delimiter must be a single character")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"CSV file not found: {file_path}")

    resolved_portfolio_store = services.portfolio_store if services is not None else portfolio_store
    import_archive_dir = services.paths.import_archive_dir if services is not None else settings.import_archive_dir

    parsed = parse_transaction_csv(
        file_path=file_path,
        default_data_source=request.default_data_source or "YAHOO",
        default_currency=request.default_currency or settings.app_currency,
        delimiter=request.delimiter,
        account_ids_by_name=resolved_portfolio_store.account_ids_by_name(),
        broker_template=request.broker_template,
    )
    parsed = apply_existing_transaction_reconciliation(
        parsed,
        existing_transactions=resolved_portfolio_store.list_transactions(limit=1_000_000),
    )

    imported_activities = 0

    if parsed.activities:
        if not request.dry_run:
            items = []
            for act in parsed.activities:
                account_id = act.get("accountId")
                account_name = str(act.get("accountName") or "").strip()
                if not account_id and account_name:
                    account_record = resolved_portfolio_store.ensure_account(account_name)
                    account_id = account_record.get("id")
                items.append({
                    "date": act.get("date", ""),
                    "symbol": act.get("symbol", ""),
                    "action": act.get("type", "BUY"),
                    "quantity": float(act.get("quantity", 0)),
                    "unit_price": float(act.get("unitPrice", 0)),
                    "fee": float(act.get("fee", 0)),
                    "currency": act.get("currency", "USD"),
                    "account": account_id or "default",
                    "lot_method": act.get("lotMethod", "FIFO"),
                    "name": act.get("name"),
                    "asset_type": act.get("assetType"),
                    "asset_class": act.get("assetClass"),
                    "sector": act.get("sector"),
                    "region": act.get("region"),
                })
            imported_activities = resolved_portfolio_store.add_transactions_bulk(items)
    else:
        parsed.warnings.append("No valid activities were parsed from this CSV file.")

    if request.archive_after_success and not request.dry_run and not parsed.errors:
        archived_path = archive_import_file(file_path, import_archive_dir)
        parsed.warnings.append(f"Archived source CSV to {archived_path}")

    return CsvImportResponse(
        file_path=str(file_path),
        dry_run=request.dry_run,
        selected_template=parsed.selected_template,
        detected_template=parsed.detected_template,
        parsed_rows=parsed.parsed_rows,
        valid_activities=len(parsed.activities),
        imported_activities=imported_activities,
        warnings=parsed.warnings,
        errors=parsed.errors,
        reconciliation_report=parsed.reconciliation_report,
    )


def summarize_snapshot(snapshot: PortfolioSnapshot, holdings_limit: int = 10) -> dict[str, object]:
    top_holdings = []
    for holding in snapshot.holdings[:holdings_limit]:
        top_holdings.append(
            {
                "symbol": holding.symbol,
                "name": holding.name,
                "value_usd": round(holding.value_usd, 2),
                "allocation_percent": round(holding.allocation_percent, 2),
            }
        )

    return {
        "as_of": snapshot.as_of.isoformat(),
        "currency": snapshot.base_currency,
        "total_value_usd": round(snapshot.total_value_usd, 2),
        "total_investment_usd": round(snapshot.total_investment_usd, 2),
        "net_performance_usd": round(snapshot.net_performance_usd, 2),
        "net_performance_percent": round(snapshot.net_performance_percent, 4),
        "holdings_count": len(snapshot.holdings),
        "top_holdings": top_holdings,
    }


def parse_benchmark_symbols(
    raw_symbols: str | list[str] | None,
    *,
    default_symbols: str,
) -> list[str]:
    if isinstance(raw_symbols, list):
        candidates = [str(item).strip().upper() for item in raw_symbols]
    else:
        text = str(raw_symbols or "").strip() or str(default_symbols or "").strip()
        candidates = [item.strip().upper() for item in text.split(",")]

    unique: list[str] = []
    seen: set[str] = set()
    for symbol in candidates:
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        unique.append(symbol)

    return unique


PLAN_SETTINGS_FIELDS = (
    "annual_contribution_usd",
    "years",
    "hsa_extra_contribution_usd",
    "marginal_tax_rate",
    "state_tax_rate",
    "simulation_mode",
    "simulation_monte_carlo_variant",
    "simulation_historical_start_year",
    "simulation_seed",
    "household_mode",
    "household_partner_income_usd",
    "household_partner_income_growth_rate",
    "household_partner_retirement_age",
    "household_partner_social_security_annual_usd",
    "household_partner_social_security_claiming_age",
    "household_shared_goal_target_usd",
    "household_shared_goal_target_year",
    "filing_status",
    "drawdown_order",
    "roth_conversion_annual_amount_usd",
    "roth_conversion_start_age",
    "roth_conversion_end_age",
    "inflation_rate",
    "expected_return_baseline",
    "expected_return_optimistic",
    "expected_return_conservative",
)


def extract_plan_settings_updates(arguments: dict[str, object]) -> dict[str, object]:
    updates: dict[str, object] = {}
    for field in PLAN_SETTINGS_FIELDS:
        if field in arguments:
            updates[field] = arguments[field]
    return updates


def merge_plan_settings(base_settings: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_settings)
    for field in PLAN_SETTINGS_FIELDS:
        if field in updates:
            merged[field] = updates[field]
    return merged


def validate_plan_return_relationships(plan_settings: dict[str, Any]) -> None:
    baseline = plan_settings.get("expected_return_baseline")
    optimistic = plan_settings.get("expected_return_optimistic")
    conservative = plan_settings.get("expected_return_conservative")

    if baseline is not None and optimistic is not None and float(optimistic) < float(baseline):
        raise ValueError("expected_return_optimistic must be >= expected_return_baseline")
    if baseline is not None and conservative is not None and float(conservative) > float(baseline):
        raise ValueError("expected_return_conservative must be <= expected_return_baseline")
    if optimistic is not None and conservative is not None and float(conservative) > float(optimistic):
        raise ValueError("expected_return_conservative must be <= expected_return_optimistic")


def build_scenario_engine_for_plan_settings(plan_settings: dict[str, Any]) -> ScenarioEngine:
    baseline_return = plan_settings.get("expected_return_baseline")
    optimistic_return = plan_settings.get("expected_return_optimistic")
    conservative_return = plan_settings.get("expected_return_conservative")
    marginal_tax_rate = plan_settings.get("marginal_tax_rate")
    inflation_rate = plan_settings.get("inflation_rate")

    return ScenarioEngine(
        years_to_retirement=settings.planner_years_to_retirement,
        annual_contribution_usd=settings.planner_annual_contribution_usd,
        baseline_return=(
            float(baseline_return)
            if baseline_return is not None
            else settings.planner_expected_return_baseline
        ),
        optimistic_return=(
            float(optimistic_return)
            if optimistic_return is not None
            else settings.planner_expected_return_optimistic
        ),
        conservative_return=(
            float(conservative_return)
            if conservative_return is not None
            else settings.planner_expected_return_conservative
        ),
        return_volatility=settings.planner_return_volatility,
        inflation=(
            float(inflation_rate)
            if inflation_rate is not None
            else settings.planner_inflation
        ),
        monte_carlo_runs=settings.planner_monte_carlo_runs,
        hsa_delta_default=settings.planner_hsa_delta_default,
        marginal_tax_rate=(
            float(marginal_tax_rate)
            if marginal_tax_rate is not None
            else settings.planner_marginal_tax_rate
        ),
    )


def build_plan_simulation_service_for_plan_settings(plan_settings: dict[str, Any]) -> BuildWealthScenarioService:
    engine = build_scenario_engine_for_plan_settings(plan_settings)
    return BuildWealthScenarioService(
        scenario_engine=engine,
    )


def _coerce_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return fallback


def _context_filter_values(*values: Any) -> list[str]:
    resolved: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            raw_values = value.split(",")
        elif isinstance(value, (list, tuple, set)):
            raw_values = value
        else:
            raw_values = (value,)
        for raw_value in raw_values:
            token = str(raw_value or "").strip()
            if token and token not in resolved:
                resolved.append(token)
    return resolved


HOUSEHOLD_MODE_INDIVIDUAL = "individual"
HOUSEHOLD_MODE_COUPLE = "couple"
DEFAULT_COUPLE_FILING_STATUS = "married_filing_jointly"
VALID_FILING_STATUSES = {
    "single",
    "married_filing_jointly",
    "married_filing_separately",
    "head_of_household",
}


def _normalize_household_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"couple", "joint", "married", "household"}:
        return HOUSEHOLD_MODE_COUPLE
    return HOUSEHOLD_MODE_INDIVIDUAL


def _resolve_filing_status_for_household(
    *,
    filing_status: Any,
    household_mode: str,
) -> str | None:
    normalized = str(filing_status or "").strip().lower()
    if normalized in VALID_FILING_STATUSES:
        return normalized
    if household_mode == HOUSEHOLD_MODE_COUPLE:
        return DEFAULT_COUPLE_FILING_STATUS
    return None


def _normalize_optional_household_age(value: Any) -> int | None:
    if value is None:
        return None
    age_value = _coerce_int(value, -1)
    if age_value < 0 or age_value > 120:
        return None
    return age_value


def _normalize_optional_household_year(value: Any) -> int | None:
    if value is None:
        return None
    year_value = _coerce_int(value, -1)
    if year_value < 1900 or year_value > 2500:
        return None
    return year_value


def _resolve_household_settings(
    *,
    plan_settings: dict[str, Any],
    start_year: int,
    years: int,
) -> dict[str, Any]:
    household_mode = _normalize_household_mode(plan_settings.get("household_mode"))
    household_partner_income_usd = max(
        0.0,
        _coerce_float(plan_settings.get("household_partner_income_usd"), 0.0),
    )
    household_partner_income_growth_rate = max(
        -1.0,
        min(1.0, _coerce_float(plan_settings.get("household_partner_income_growth_rate"), 0.0)),
    )
    household_partner_retirement_age = _normalize_optional_household_age(
        plan_settings.get("household_partner_retirement_age"),
    )
    household_partner_social_security_annual_usd = max(
        0.0,
        _coerce_float(plan_settings.get("household_partner_social_security_annual_usd"), 0.0),
    )
    household_partner_social_security_claiming_age = _normalize_optional_household_age(
        plan_settings.get("household_partner_social_security_claiming_age"),
    )
    household_shared_goal_target_usd = max(
        0.0,
        _coerce_float(plan_settings.get("household_shared_goal_target_usd"), 0.0),
    )
    household_shared_goal_target_year = _normalize_optional_household_year(
        plan_settings.get("household_shared_goal_target_year"),
    )
    if household_shared_goal_target_usd > 0 and household_shared_goal_target_year is None:
        household_shared_goal_target_year = start_year + max(0, years - 1)

    return {
        "household_mode": household_mode,
        "household_partner_income_usd": household_partner_income_usd,
        "household_partner_income_growth_rate": household_partner_income_growth_rate,
        "household_partner_retirement_age": household_partner_retirement_age,
        "household_partner_social_security_annual_usd": household_partner_social_security_annual_usd,
        "household_partner_social_security_claiming_age": household_partner_social_security_claiming_age,
        "household_shared_goal_target_usd": household_shared_goal_target_usd,
        "household_shared_goal_target_year": household_shared_goal_target_year,
    }


def _apply_household_adjustments_to_projection_payloads(
    *,
    income_projection: dict[str, Any] | None,
    expense_projection: dict[str, Any] | None,
    household_settings: dict[str, Any],
    start_year: int,
    start_age: int,
    years: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    household_mode = str(household_settings.get("household_mode") or HOUSEHOLD_MODE_INDIVIDUAL)
    result_payload = {
        "mode": household_mode,
        "partner_income_added_first_year_usd": 0.0,
        "partner_income_added_total_usd": 0.0,
        "shared_goal_target_usd": 0.0,
        "shared_goal_target_year": None,
        "shared_goal_annual_funding_usd": 0.0,
    }
    if household_mode != HOUSEHOLD_MODE_COUPLE:
        return income_projection, expense_projection, result_payload

    adjusted_income = dict(income_projection) if isinstance(income_projection, dict) else None
    adjusted_expenses = dict(expense_projection) if isinstance(expense_projection, dict) else None

    partner_income = max(0.0, _coerce_float(household_settings.get("household_partner_income_usd"), 0.0))
    partner_growth = max(
        -1.0,
        min(1.0, _coerce_float(household_settings.get("household_partner_income_growth_rate"), 0.0)),
    )
    partner_retirement_age = _normalize_optional_household_age(
        household_settings.get("household_partner_retirement_age"),
    )
    partner_ss_income = max(
        0.0,
        _coerce_float(household_settings.get("household_partner_social_security_annual_usd"), 0.0),
    )
    partner_ss_claim_age = _normalize_optional_household_age(
        household_settings.get("household_partner_social_security_claiming_age"),
    )

    partner_income_added_total = 0.0
    partner_income_added_first_year = 0.0
    if adjusted_income is not None:
        projection_start_year = _coerce_int(adjusted_income.get("start_year"), start_year)
        projection_years = max(1, _coerce_int(adjusted_income.get("years"), years))
        raw_points = adjusted_income.get("yearly_points")
        yearly_points = [dict(item) for item in raw_points if isinstance(item, dict)] if isinstance(raw_points, list) else []
        if not yearly_points:
            first_year_income = max(0.0, _coerce_float(adjusted_income.get("first_year_gross_income_usd"), 0.0))
            yearly_points = [
                {
                    "year": projection_start_year + offset,
                    "gross_income_usd": first_year_income,
                    "pre_tax_income_usd": 0.0,
                    "post_tax_income_usd": first_year_income,
                    "active_income_items": 0,
                }
                for offset in range(projection_years)
            ]

        for point in yearly_points:
            year_value = _coerce_int(point.get("year"), projection_start_year)
            offset = max(0, year_value - start_year)
            age_value = start_age + offset
            additional_income = 0.0
            if partner_income > 0 and (
                partner_retirement_age is None or age_value < int(partner_retirement_age)
            ):
                additional_income += partner_income * ((1.0 + partner_growth) ** offset)
            if partner_ss_income > 0 and partner_ss_claim_age is not None and age_value >= int(partner_ss_claim_age):
                additional_income += partner_ss_income
            if additional_income <= 0:
                continue

            partner_income_added_total += additional_income
            if year_value == start_year:
                partner_income_added_first_year += additional_income

            point["gross_income_usd"] = max(0.0, _coerce_float(point.get("gross_income_usd"), 0.0) + additional_income)
            point["post_tax_income_usd"] = max(0.0, _coerce_float(point.get("post_tax_income_usd"), 0.0) + additional_income)
            point["active_income_items"] = max(0, _coerce_int(point.get("active_income_items"), 0)) + 1

        yearly_points.sort(key=lambda item: _coerce_int(item.get("year"), projection_start_year))
        gross_values = [max(0.0, _coerce_float(item.get("gross_income_usd"), 0.0)) for item in yearly_points]
        if gross_values:
            adjusted_income["first_year_gross_income_usd"] = gross_values[0]
            adjusted_income["final_year_gross_income_usd"] = gross_values[-1]
            adjusted_income["cumulative_gross_income_usd"] = float(sum(gross_values))
            if len(gross_values) > 1 and gross_values[0] > 0 and gross_values[-1] > 0:
                adjusted_income["annualized_income_growth_rate"] = (
                    (gross_values[-1] / gross_values[0]) ** (1.0 / (len(gross_values) - 1))
                ) - 1.0
        adjusted_income["yearly_points"] = yearly_points

    shared_goal_target_usd = max(
        0.0,
        _coerce_float(household_settings.get("household_shared_goal_target_usd"), 0.0),
    )
    shared_goal_target_year = _normalize_optional_household_year(
        household_settings.get("household_shared_goal_target_year"),
    )
    shared_goal_annual_funding = 0.0
    resolved_shared_goal_target_year: int | None = None
    if adjusted_expenses is not None:
        projection_start_year = _coerce_int(adjusted_expenses.get("start_year"), start_year)
        projection_years = max(1, _coerce_int(adjusted_expenses.get("years"), years))
        raw_points = adjusted_expenses.get("yearly_points")
        yearly_points = [dict(item) for item in raw_points if isinstance(item, dict)] if isinstance(raw_points, list) else []
        if not yearly_points:
            first_year_expenses = max(0.0, _coerce_float(adjusted_expenses.get("first_year_expenses_usd"), 0.0))
            yearly_points = [
                {
                    "year": projection_start_year + offset,
                    "total_expenses_usd": first_year_expenses,
                    "fixed_expenses_usd": first_year_expenses,
                    "variable_expenses_usd": 0.0,
                    "active_expense_items": 0,
                }
                for offset in range(projection_years)
            ]

        if shared_goal_target_usd > 0:
            if shared_goal_target_year is None:
                shared_goal_target_year = projection_start_year + projection_years - 1
            resolved_shared_goal_target_year = max(projection_start_year, int(shared_goal_target_year))
            runway_years = max(
                1,
                min(projection_years, resolved_shared_goal_target_year - projection_start_year + 1),
            )
            shared_goal_annual_funding = shared_goal_target_usd / float(runway_years)
            for point in yearly_points:
                year_value = _coerce_int(point.get("year"), projection_start_year)
                if year_value > resolved_shared_goal_target_year:
                    continue
                point["total_expenses_usd"] = max(
                    0.0,
                    _coerce_float(point.get("total_expenses_usd"), 0.0) + shared_goal_annual_funding,
                )

        yearly_points.sort(key=lambda item: _coerce_int(item.get("year"), projection_start_year))
        expense_values = [max(0.0, _coerce_float(item.get("total_expenses_usd"), 0.0)) for item in yearly_points]
        if expense_values:
            adjusted_expenses["first_year_expenses_usd"] = expense_values[0]
            adjusted_expenses["final_year_expenses_usd"] = expense_values[-1]
            adjusted_expenses["cumulative_expenses_usd"] = float(sum(expense_values))
            if len(expense_values) > 1 and expense_values[0] > 0 and expense_values[-1] > 0:
                adjusted_expenses["annualized_expense_growth_rate"] = (
                    (expense_values[-1] / expense_values[0]) ** (1.0 / (len(expense_values) - 1))
                ) - 1.0
        adjusted_expenses["yearly_points"] = yearly_points

    result_payload["partner_income_added_first_year_usd"] = round(partner_income_added_first_year, 2)
    result_payload["partner_income_added_total_usd"] = round(partner_income_added_total, 2)
    result_payload["shared_goal_target_usd"] = round(shared_goal_target_usd, 2)
    result_payload["shared_goal_target_year"] = resolved_shared_goal_target_year
    result_payload["shared_goal_annual_funding_usd"] = round(shared_goal_annual_funding, 2)
    return adjusted_income, adjusted_expenses, result_payload


def _build_household_response_context(
    *,
    household_settings: dict[str, Any],
    household_adjustments: dict[str, Any],
    filing_status: str | None,
    source: str,
) -> dict[str, Any]:
    mode = _normalize_household_mode(household_settings.get("household_mode"))
    return {
        "mode": mode,
        "source": str(source or "").strip() or None,
        "enabled": mode == HOUSEHOLD_MODE_COUPLE,
        "filing_status": str(filing_status).strip().lower() if filing_status else None,
        "partner_income_usd": max(
            0.0,
            _coerce_float(household_settings.get("household_partner_income_usd"), 0.0),
        ),
        "partner_income_growth_rate": max(
            -1.0,
            min(1.0, _coerce_float(household_settings.get("household_partner_income_growth_rate"), 0.0)),
        ),
        "partner_retirement_age": _normalize_optional_household_age(
            household_settings.get("household_partner_retirement_age"),
        ),
        "partner_social_security_annual_usd": max(
            0.0,
            _coerce_float(household_settings.get("household_partner_social_security_annual_usd"), 0.0),
        ),
        "partner_social_security_claiming_age": _normalize_optional_household_age(
            household_settings.get("household_partner_social_security_claiming_age"),
        ),
        "shared_goal_target_usd": max(
            0.0,
            _coerce_float(household_settings.get("household_shared_goal_target_usd"), 0.0),
        ),
        "shared_goal_target_year": _normalize_optional_household_year(
            household_settings.get("household_shared_goal_target_year"),
        ),
        "shared_goal_annual_funding_usd": max(
            0.0,
            _coerce_float(household_adjustments.get("shared_goal_annual_funding_usd"), 0.0),
        ),
        "partner_income_added_first_year_usd": max(
            0.0,
            _coerce_float(household_adjustments.get("partner_income_added_first_year_usd"), 0.0),
        ),
        "partner_income_added_total_usd": max(
            0.0,
            _coerce_float(household_adjustments.get("partner_income_added_total_usd"), 0.0),
        ),
    }


def _apply_household_context_to_planning_response(
    *,
    response: PlanningResponse,
    household_context: dict[str, Any],
) -> PlanningResponse:
    assumption_patch: dict[str, float | int | str | bool | None] = {
        "household_mode": str(household_context.get("mode") or HOUSEHOLD_MODE_INDIVIDUAL),
        "filing_status": str(household_context.get("filing_status")).strip().lower()
        if household_context.get("filing_status")
        else None,
        "household_partner_income_usd": round(
            _coerce_float(household_context.get("partner_income_usd"), 0.0),
            2,
        ),
        "household_partner_income_growth_rate": round(
            _coerce_float(household_context.get("partner_income_growth_rate"), 0.0),
            6,
        ),
        "household_partner_retirement_age": _normalize_optional_household_age(
            household_context.get("partner_retirement_age"),
        ),
        "household_partner_social_security_annual_usd": round(
            _coerce_float(household_context.get("partner_social_security_annual_usd"), 0.0),
            2,
        ),
        "household_partner_social_security_claiming_age": _normalize_optional_household_age(
            household_context.get("partner_social_security_claiming_age"),
        ),
        "household_shared_goal_target_usd": round(
            _coerce_float(household_context.get("shared_goal_target_usd"), 0.0),
            2,
        ),
        "household_shared_goal_target_year": _normalize_optional_household_year(
            household_context.get("shared_goal_target_year"),
        ),
        "household_shared_goal_annual_funding_usd": round(
            _coerce_float(household_context.get("shared_goal_annual_funding_usd"), 0.0),
            2,
        ),
        "household_partner_income_added_first_year_usd": round(
            _coerce_float(household_context.get("partner_income_added_first_year_usd"), 0.0),
            2,
        ),
        "household_partner_income_added_total_usd": round(
            _coerce_float(household_context.get("partner_income_added_total_usd"), 0.0),
            2,
        ),
    }

    updated_scenarios = []
    for scenario in response.scenarios:
        assumptions = (
            dict(scenario.assumptions)
            if isinstance(scenario.assumptions, dict)
            else {}
        )
        assumptions.update(assumption_patch)
        updated_scenarios.append(scenario.model_copy(update={"assumptions": assumptions}))

    return response.model_copy(
        update={
            "scenarios": updated_scenarios,
            "household": HouseholdPlanningContext(**household_context),
        }
    )


def _coerce_optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    try:
        if "T" in text:
            return datetime.fromisoformat(text).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def build_planning_accounts_from_portfolio(store: PortfolioStore | None = None) -> list[dict[str, Any]]:
    resolved_store = store or portfolio_store
    holdings_payload = resolved_store.get_holdings()
    account_totals = holdings_payload.get("account_totals", {})
    if not isinstance(account_totals, dict):
        account_totals = {}

    accounts: list[dict[str, Any]] = []
    for account in resolved_store.get_accounts():
        if not isinstance(account, dict):
            continue
        account_id = str(account.get("id") or "").strip()
        if not account_id:
            continue

        account_total = account_totals.get(account_id, {})
        if not isinstance(account_total, dict):
            account_total = {}

        accounts.append(
            {
                "account_id": account_id,
                "account_name": str(account.get("name") or account_id).strip() or account_id,
                "account_type": normalize_account_type(account.get("type") or account.get("account_type")),
                "balance_usd": max(
                    0.0,
                    _coerce_float(
                        account_total.get("total_value", account_total.get("market_value", account.get("balance", 0.0))),
                        0.0,
                    ),
                ),
            }
        )

    return accounts


def parse_contribution_rules_payload(raw_payload: Any) -> dict[str, Any]:
    if isinstance(raw_payload, str):
        text = raw_payload.strip()
        if not text:
            payload: Any = {}
        else:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}
    elif isinstance(raw_payload, dict):
        payload = raw_payload
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    base_rule = payload.get("base_rule")
    if not isinstance(base_rule, dict):
        base_rule = {"type": "save"}
    base_rule_type = str(base_rule.get("type") or "save").strip().lower()
    if base_rule_type not in {"save", "spend"}:
        base_rule_type = "save"
    base_rule = {"type": base_rule_type}

    rules = payload.get("rules")
    if not isinstance(rules, list):
        rules = []

    profile_id = str(payload.get("profile_id") or payload.get("default_profile") or "").strip() or None
    employer_match_target_usd = max(0.0, _coerce_float(payload.get("employer_match_target_usd"), 6000.0))
    age = _coerce_int(payload.get("age"), 35)
    if age < 0:
        age = 0
    if age > 120:
        age = 120

    return {
        "base_rule": base_rule,
        "rules": rules,
        "profile_id": profile_id,
        "employer_match_target_usd": employer_match_target_usd,
        "age": age,
    }


def resolve_plan_contribution_rules(detail: dict[str, Any]) -> dict[str, Any]:
    files = detail.get("files", {})
    raw_payload = files.get("contribution_rules_json") if isinstance(files, dict) else None
    return parse_contribution_rules_payload(raw_payload)


DEFAULT_WITHDRAWAL_STRATEGIES = [
    "cashflow_only",
    "four_percent_rule",
    "dynamic_guardrails",
    "bond_tent",
    "bucket_strategy",
]


def normalize_withdrawal_strategy_value(
    raw_value: Any,
    *,
    fallback: str | None = None,
) -> str | None:
    text = str(raw_value or "").strip().lower()
    if not text:
        return fallback
    return STRATEGY_ALIASES.get(text, fallback)


def normalize_withdrawal_strategies(
    raw_values: Any,
) -> tuple[list[str], list[str]]:
    if raw_values is None:
        return DEFAULT_WITHDRAWAL_STRATEGIES, []

    raw_items: list[str]
    if isinstance(raw_values, str):
        raw_items = [item.strip() for item in raw_values.split(",") if item.strip()]
    elif isinstance(raw_values, list):
        raw_items = [str(item).strip() for item in raw_values if str(item).strip()]
    else:
        raw_items = []

    if not raw_items:
        return DEFAULT_WITHDRAWAL_STRATEGIES, []

    resolved: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = STRATEGY_ALIASES.get(item.strip().lower())
        if not normalized:
            invalid.append(item)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)

    if not resolved:
        return DEFAULT_WITHDRAWAL_STRATEGIES, invalid
    return resolved, invalid


def _normalize_optional_simulation_mode(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip().lower()
    if not text:
        return None
    candidates = (
        text,
        text.replace("-", "_"),
        text.replace(" ", "_"),
        re.sub(r"[^a-z0-9_]+", "", text),
    )
    for candidate in candidates:
        normalized = SIMULATION_MODE_ALIASES.get(candidate)
        if normalized is not None:
            return normalized
    return None


def _normalize_optional_simulation_monte_carlo_variant(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip().lower()
    if not text:
        return None
    candidates = (
        text,
        text.replace("-", "_"),
        text.replace(" ", "_"),
        re.sub(r"[^a-z0-9_]+", "", text),
    )
    for candidate in candidates:
        normalized = MONTE_CARLO_VARIANT_ALIASES.get(candidate)
        if normalized is not None:
            return normalized
    return None


def _normalize_optional_simulation_int(
    raw_value: Any,
    *,
    minimum: int,
    maximum: int,
) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and not raw_value.strip():
        return None
    try:
        value = int(float(raw_value))
    except (TypeError, ValueError):
        return None
    if value < minimum or value > maximum:
        return None
    return value


def parse_assumption_sets_payload(raw_payload: Any) -> dict[str, Any]:
    fallback_sets = [
        {
            "id": "default",
            "name": "Default",
            "expected_return_baseline": None,
            "expected_return_optimistic": None,
            "expected_return_conservative": None,
            "inflation_rate": None,
            "marginal_tax_rate": None,
            "state_tax_rate": None,
            "simulation_mode": None,
            "simulation_monte_carlo_variant": None,
            "simulation_historical_start_year": None,
            "simulation_seed": None,
            "roth_conversion_annual_amount_usd": None,
            "roth_conversion_start_age": None,
            "roth_conversion_end_age": None,
        },
        {
            "id": "historical_average",
            "name": "Historical Average",
            "expected_return_baseline": 0.07,
            "expected_return_optimistic": 0.09,
            "expected_return_conservative": 0.05,
            "inflation_rate": 0.03,
            "marginal_tax_rate": None,
            "state_tax_rate": None,
            "simulation_mode": None,
            "simulation_monte_carlo_variant": None,
            "simulation_historical_start_year": None,
            "simulation_seed": None,
            "roth_conversion_annual_amount_usd": None,
            "roth_conversion_start_age": None,
            "roth_conversion_end_age": None,
        },
        {
            "id": "conservative",
            "name": "Conservative",
            "expected_return_baseline": 0.05,
            "expected_return_optimistic": 0.06,
            "expected_return_conservative": 0.04,
            "inflation_rate": 0.025,
            "marginal_tax_rate": None,
            "state_tax_rate": None,
            "simulation_mode": None,
            "simulation_monte_carlo_variant": None,
            "simulation_historical_start_year": None,
            "simulation_seed": None,
            "roth_conversion_annual_amount_usd": None,
            "roth_conversion_start_age": None,
            "roth_conversion_end_age": None,
        },
        {
            "id": "stagflation",
            "name": "Stagflation",
            "expected_return_baseline": 0.04,
            "expected_return_optimistic": 0.05,
            "expected_return_conservative": 0.02,
            "inflation_rate": 0.05,
            "marginal_tax_rate": None,
            "state_tax_rate": None,
            "simulation_mode": None,
            "simulation_monte_carlo_variant": None,
            "simulation_historical_start_year": None,
            "simulation_seed": None,
            "roth_conversion_annual_amount_usd": None,
            "roth_conversion_start_age": None,
            "roth_conversion_end_age": None,
        },
        {
            "id": "japan_scenario",
            "name": "Japan Scenario",
            "expected_return_baseline": 0.02,
            "expected_return_optimistic": 0.035,
            "expected_return_conservative": 0.0,
            "inflation_rate": 0.005,
            "marginal_tax_rate": None,
            "state_tax_rate": None,
            "simulation_mode": None,
            "simulation_monte_carlo_variant": None,
            "simulation_historical_start_year": None,
            "simulation_seed": None,
            "roth_conversion_annual_amount_usd": None,
            "roth_conversion_start_age": None,
            "roth_conversion_end_age": None,
        },
    ]

    if isinstance(raw_payload, str):
        text = raw_payload.strip()
        if not text:
            payload: Any = {}
        else:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}
    elif isinstance(raw_payload, dict):
        payload = raw_payload
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    def _normalize_optional_rate(
        raw_value: Any,
        *,
        minimum: float,
        maximum: float,
    ) -> float | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, str) and not raw_value.strip():
            return None
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None
        if value < minimum or value > maximum:
            return None
        return value

    def _normalize_optional_int(
        raw_value: Any,
        *,
        minimum: int,
        maximum: int,
    ) -> int | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, str) and not raw_value.strip():
            return None
        try:
            value = int(float(raw_value))
        except (TypeError, ValueError):
            return None
        if value < minimum or value > maximum:
            return None
        return value

    sets_raw = payload.get("sets")
    if not isinstance(sets_raw, list):
        sets_raw = fallback_sets

    sets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(sets_raw, start=1):
        if not isinstance(raw, dict):
            continue
        set_id = str(raw.get("id") or "").strip().lower()
        if not set_id:
            set_id = f"set-{index}"
        if set_id in seen_ids:
            continue
        seen_ids.add(set_id)
        baseline = _normalize_optional_rate(
            raw.get("expected_return_baseline"),
            minimum=-0.95,
            maximum=1.0,
        )
        optimistic = _normalize_optional_rate(
            raw.get("expected_return_optimistic"),
            minimum=-0.95,
            maximum=1.0,
        )
        conservative = _normalize_optional_rate(
            raw.get("expected_return_conservative"),
            minimum=-0.95,
            maximum=1.0,
        )
        inflation_rate = _normalize_optional_rate(
            raw.get("inflation_rate"),
            minimum=-1.0,
            maximum=1.0,
        )
        marginal_tax_rate = _normalize_optional_rate(
            raw.get("marginal_tax_rate"),
            minimum=0.0,
            maximum=1.0,
        )
        state_tax_rate = _normalize_optional_rate(
            raw.get("state_tax_rate"),
            minimum=0.0,
            maximum=1.0,
        )
        simulation_mode = _normalize_optional_simulation_mode(
            raw.get("simulation_mode")
        )
        simulation_monte_carlo_variant = _normalize_optional_simulation_monte_carlo_variant(
            raw.get("simulation_monte_carlo_variant")
        )
        simulation_historical_start_year = _normalize_optional_simulation_int(
            raw.get("simulation_historical_start_year"),
            minimum=min(HISTORICAL_YEARS),
            maximum=max(HISTORICAL_YEARS),
        )
        simulation_seed_value = raw.get("simulation_seed")
        if simulation_seed_value is None or (
            isinstance(simulation_seed_value, str) and not simulation_seed_value.strip()
        ):
            simulation_seed = None
        else:
            simulation_seed = _normalize_optional_simulation_int(
                simulation_seed_value,
                minimum=0,
                maximum=2_147_483_647,
            )
            if simulation_seed is None:
                simulation_seed = DEFAULT_SIMULATION_SEED
        roth_conversion_annual_amount_usd = _normalize_optional_rate(
            raw.get("roth_conversion_annual_amount_usd"),
            minimum=0.0,
            maximum=10_000_000.0,
        )
        roth_conversion_start_age = _normalize_optional_int(
            raw.get("roth_conversion_start_age"),
            minimum=0,
            maximum=120,
        )
        roth_conversion_end_age = _normalize_optional_int(
            raw.get("roth_conversion_end_age"),
            minimum=0,
            maximum=120,
        )
        if (
            roth_conversion_start_age is not None
            and roth_conversion_end_age is not None
            and roth_conversion_start_age > roth_conversion_end_age
        ):
            roth_conversion_start_age, roth_conversion_end_age = (
                roth_conversion_end_age,
                roth_conversion_start_age,
            )
        if baseline is not None and optimistic is not None and optimistic < baseline:
            optimistic = baseline
        if baseline is not None and conservative is not None and conservative > baseline:
            conservative = baseline
        if optimistic is not None and conservative is not None and conservative > optimistic:
            conservative = optimistic
        sets.append(
            {
                "id": set_id,
                "name": str(raw.get("name") or set_id).strip() or set_id,
                "expected_return_baseline": baseline,
                "expected_return_optimistic": optimistic,
                "expected_return_conservative": conservative,
                "inflation_rate": inflation_rate,
                "marginal_tax_rate": marginal_tax_rate,
                "state_tax_rate": state_tax_rate,
                "simulation_mode": simulation_mode,
                "simulation_monte_carlo_variant": simulation_monte_carlo_variant,
                "simulation_historical_start_year": simulation_historical_start_year,
                "simulation_seed": simulation_seed,
                "roth_conversion_annual_amount_usd": roth_conversion_annual_amount_usd,
                "roth_conversion_start_age": roth_conversion_start_age,
                "roth_conversion_end_age": roth_conversion_end_age,
            }
        )

    if not sets:
        sets = list(fallback_sets)
        seen_ids = {str(item.get("id") or "").strip() for item in sets}

    active_id = str(payload.get("active_assumption_set_id") or "default").strip().lower()
    if active_id not in seen_ids:
        active_id = str(sets[0].get("id") or "default")

    return {
        "schema_version": 2,
        "active_assumption_set_id": active_id,
        "sets": sets,
    }


def resolve_plan_assumption_sets(detail: dict[str, Any]) -> dict[str, Any]:
    files = detail.get("files", {})
    raw_payload = files.get("assumption_sets_json") if isinstance(files, dict) else None
    return parse_assumption_sets_payload(raw_payload)


def parse_branch_templates_payload(raw_payload: Any) -> dict[str, Any]:
    fallback_templates = [
        {
            "id": "job_loss_6_months",
            "name": "Job Loss (6 Months)",
            "description": "Temporary income interruption for six months.",
            "branch_name": "Job Loss 6 Months",
            "assumption_set_id": None,
            "compare_settings": {},
            "branch_events": [
                {
                    "label": "Temporary Job Loss",
                    "event_type": "job_change",
                    "impact_type": "income",
                    "amount_usd": -7500.0,
                    "recurring_frequency": "monthly",
                    "start_year_offset": 0,
                    "duration_months": 6,
                    "account_id": None,
                    "notes": "Modeled as gross monthly income loss.",
                }
            ],
        },
        {
            "id": "raise_20_percent",
            "name": "Raise (20%)",
            "description": "Ongoing promotion raise scenario.",
            "branch_name": "Raise 20 Percent",
            "assumption_set_id": None,
            "compare_settings": {},
            "branch_events": [
                {
                    "label": "Promotion Raise",
                    "event_type": "job_change",
                    "impact_type": "income",
                    "amount_usd": 18000.0,
                    "recurring_frequency": "yearly",
                    "start_year_offset": 0,
                    "duration_months": None,
                    "account_id": None,
                    "notes": "Annualized salary lift.",
                }
            ],
        },
        {
            "id": "new_child_costs",
            "name": "New Child Costs",
            "description": "One-time setup plus long-duration monthly childcare costs.",
            "branch_name": "Have a Kid",
            "assumption_set_id": None,
            "compare_settings": {},
            "branch_events": [
                {
                    "label": "Childcare Setup Costs",
                    "event_type": "purchase",
                    "impact_type": "expense",
                    "amount_usd": 15000.0,
                    "recurring_frequency": "one_time",
                    "start_year_offset": 0,
                    "duration_months": None,
                    "account_id": None,
                    "notes": "",
                },
                {
                    "label": "Ongoing Childcare Costs",
                    "event_type": "milestone",
                    "impact_type": "expense",
                    "amount_usd": 1200.0,
                    "recurring_frequency": "monthly",
                    "start_year_offset": 0,
                    "duration_months": 216,
                    "account_id": None,
                    "notes": "",
                },
            ],
        },
    ]

    if isinstance(raw_payload, str):
        text = raw_payload.strip()
        if not text:
            payload: Any = {}
        else:
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = {}
    elif isinstance(raw_payload, dict):
        payload = raw_payload
    else:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    templates_raw = payload.get("templates")
    if not isinstance(templates_raw, list):
        templates_raw = fallback_templates

    templates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(templates_raw, start=1):
        if not isinstance(raw, dict):
            continue
        template_id = str(raw.get("id") or "").strip().lower()
        if not template_id:
            template_id = f"branch-template-{index}"
        template_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", template_id).strip("-").lower() or f"branch-template-{index}"
        if template_id in seen_ids:
            continue
        seen_ids.add(template_id)

        compare_settings_raw = raw.get("compare_settings")
        compare_settings = compare_settings_raw if isinstance(compare_settings_raw, dict) else {}
        try:
            sanitized_compare_settings = plan_workspace._sanitize_settings_update(compare_settings)  # noqa: SLF001
        except ValueError:
            sanitized_compare_settings = {}
        try:
            validate_plan_return_relationships(sanitized_compare_settings)
        except ValueError:
            sanitized_compare_settings = {}

        branch_events_raw = raw.get("branch_events")
        branch_events = [
            item for item in branch_events_raw
            if isinstance(item, dict)
        ] if isinstance(branch_events_raw, list) else []
        if not branch_events and not sanitized_compare_settings:
            continue

        templates.append(
            {
                "id": template_id,
                "name": str(raw.get("name") or template_id).strip() or template_id,
                "description": str(raw.get("description") or "").strip(),
                "branch_name": str(raw.get("branch_name") or raw.get("name") or "What-If Branch").strip() or "What-If Branch",
                "assumption_set_id": (str(raw.get("assumption_set_id") or "").strip().lower() or None),
                "compare_settings": sanitized_compare_settings,
                "branch_events": branch_events,
            }
        )

    if not templates:
        templates = list(fallback_templates)
        seen_ids = {str(item.get("id") or "").strip() for item in templates if isinstance(item, dict)}

    default_template_id = str(payload.get("default_template_id") or "").strip().lower()
    if not default_template_id or default_template_id not in seen_ids:
        default_template_id = str(templates[0].get("id") or "") if templates else ""

    return {
        "schema_version": 2,
        "default_template_id": default_template_id or None,
        "templates": templates,
    }


RESEARCH_BRIDGE_TEMPLATE_ID = "research_watchlist_bridge"
RESEARCH_BRIDGE_TEMPLATE_NAME = "Research Watchlist Thesis"
RESEARCH_BRIDGE_NOTE_PREFIX = "[research-bridge]"


def _sanitize_branch_template_id(raw_template_id: Any, fallback: str = RESEARCH_BRIDGE_TEMPLATE_ID) -> str:
    template_id = str(raw_template_id or "").strip().lower()
    if not template_id:
        template_id = fallback
    template_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", template_id).strip("-").lower()
    return template_id or fallback


def _extract_watchlist_item_for_research_bridge(raw_item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(raw_item.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    tags_raw = raw_item.get("tags")
    tags: list[str] = []
    if isinstance(tags_raw, list):
        seen_tags: set[str] = set()
        for raw_tag in tags_raw:
            tag = str(raw_tag or "").strip()
            if not tag:
                continue
            normalized_tag = tag.lower()
            if normalized_tag in seen_tags:
                continue
            seen_tags.add(normalized_tag)
            tags.append(tag)

    target_price = raw_item.get("target_price_usd")
    target_price_usd: float | None
    if target_price is None:
        target_price_usd = None
    else:
        try:
            target_price_usd = float(target_price)
        except (TypeError, ValueError):
            target_price_usd = None
        if target_price_usd is not None and target_price_usd <= 0:
            target_price_usd = None

    return {
        "symbol": symbol,
        "data_source": str(raw_item.get("data_source") or "OPENBB").strip().upper() or "OPENBB",
        "thesis": str(raw_item.get("thesis") or "").strip(),
        "note": str(raw_item.get("note") or "").strip(),
        "target_price_usd": target_price_usd,
        "tags": tags,
    }


def select_research_bridge_watchlist_items(
    *,
    watchlist_items: list[dict[str, Any]] | None,
    requested_symbols: list[str] | None = None,
    max_symbols: int = 5,
) -> list[dict[str, Any]]:
    normalized_requested = normalize_research_symbols(requested_symbols or [], max_symbols=20)
    bounded_max_symbols = max(1, min(int(max_symbols), 20))

    by_symbol: dict[str, dict[str, Any]] = {}
    for raw in watchlist_items or []:
        if not isinstance(raw, dict):
            continue
        normalized_item = _extract_watchlist_item_for_research_bridge(raw)
        if not normalized_item:
            continue
        symbol = normalized_item["symbol"]
        if symbol not in by_symbol:
            by_symbol[symbol] = normalized_item

    if not by_symbol:
        return []

    if normalized_requested:
        selected = [by_symbol[symbol] for symbol in normalized_requested if symbol in by_symbol]
    else:
        selected = [by_symbol[symbol] for symbol in sorted(by_symbol.keys())]

    return selected[:bounded_max_symbols]


def _format_research_bridge_note(item: dict[str, Any]) -> str:
    parts = [f"{RESEARCH_BRIDGE_NOTE_PREFIX} symbol={item.get('symbol', '')}"]
    thesis = str(item.get("thesis") or "").strip()
    note = str(item.get("note") or "").strip()
    target_price_usd = item.get("target_price_usd")
    tags = item.get("tags")

    if thesis:
        parts.append(f"thesis: {thesis}")
    if note:
        parts.append(f"note: {note}")
    if target_price_usd is not None:
        parts.append(f"target_price_usd: {float(target_price_usd):.4f}")
    if isinstance(tags, list) and tags:
        parts.append("tags: " + ", ".join(str(tag) for tag in tags))
    return " | ".join(parts)


def build_research_bridge_branch_events(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Preserve Simulations-compatible branch event structure: the bridge uses
    # zero-impact milestone events to attach research context to scenario branches.
    events: list[dict[str, Any]] = []
    for item in items:
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        events.append(
            {
                "label": f"Research Thesis: {symbol}",
                "event_type": "milestone",
                "impact_type": "portfolio",
                "amount_usd": 0.0,
                "recurring_frequency": "one_time",
                "start_year_offset": 0,
                "duration_months": None,
                "account_id": None,
                "notes": _format_research_bridge_note(item),
            }
        )
    return events


def _is_research_bridge_event(raw_event: dict[str, Any]) -> bool:
    notes = str(raw_event.get("notes") or "").strip().lower()
    return RESEARCH_BRIDGE_NOTE_PREFIX in notes


def _build_research_bridge_pin_markdown(
    *,
    plan_id: str,
    template_id: str,
    template_name: str,
    branch_name: str,
    assumption_set_id: str | None,
    requested_symbols: list[str],
    pinned_items: list[PlanResearchBridgePinnedItem],
    retained_event_count: int,
    generated_event_count: int,
    pinned_at: str,
) -> str:
    pinned_symbols = [item.symbol for item in pinned_items]
    payload = {
        "plan_id": plan_id,
        "template_id": template_id,
        "template_name": template_name,
        "branch_name": branch_name,
        "assumption_set_id": assumption_set_id,
        "requested_symbols": requested_symbols,
        "pinned_symbols": pinned_symbols,
        "retained_non_bridge_event_count": retained_event_count,
        "generated_bridge_event_count": generated_event_count,
        "pinned_at": pinned_at,
    }
    lines = [
        f"# Research Bridge Pin: {template_name}",
        "",
        "## Summary",
        "",
        f"- Plan ID: `{plan_id}`",
        f"- Template ID: `{template_id}`",
        f"- Branch Name: `{branch_name}`",
        f"- Assumption Set: `{assumption_set_id or 'none'}`",
        f"- Requested Symbols: `{', '.join(requested_symbols) if requested_symbols else 'auto-select from watchlist'}`",
        f"- Pinned Symbols: `{', '.join(pinned_symbols)}`",
        f"- Pinned At: `{pinned_at}`",
        "",
        "## Pinned Watchlist Items",
        "",
    ]
    for item in pinned_items:
        details: list[str] = []
        if item.target_price_usd is not None:
            details.append(f"target {_format_currency_amount(item.target_price_usd)}")
        if item.tags:
            details.append(f"tags: {', '.join(item.tags)}")
        detail_suffix = f" ({'; '.join(details)})" if details else ""
        lines.append(f"- `{item.symbol}` [{item.data_source}]{detail_suffix}")
        if item.thesis:
            lines.append(f"  - thesis: {item.thesis}")
        if item.note:
            lines.append(f"  - note: {item.note}")

    lines.extend(
        [
            "",
            "## Branch Event Coverage",
            "",
            f"- Retained non-bridge event count: `{retained_event_count}`",
            f"- Generated bridge event count: `{generated_event_count}`",
            "",
            "## Structured Payload",
            "",
            "```json",
            json.dumps(payload, indent=2, default=str),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def resolve_plan_branch_templates(detail: dict[str, Any]) -> dict[str, Any]:
    files = detail.get("files", {})
    raw_payload = files.get("branch_templates_json") if isinstance(files, dict) else None
    return parse_branch_templates_payload(raw_payload)


def select_branch_template(
    *,
    branch_templates_payload: dict[str, Any] | None,
    branch_template_id: str | None,
) -> dict[str, Any] | None:
    if not isinstance(branch_templates_payload, dict):
        return None
    templates = branch_templates_payload.get("templates")
    if not isinstance(templates, list) or not templates:
        return None

    target_id = str(
        branch_template_id
        or branch_templates_payload.get("default_template_id")
        or ""
    ).strip().lower()

    selected: dict[str, Any] | None = None
    if target_id:
        for raw in templates:
            if not isinstance(raw, dict):
                continue
            candidate_id = str(raw.get("id") or "").strip().lower()
            if candidate_id and candidate_id == target_id:
                selected = raw
                break
        if selected is None:
            return None

    if selected is None:
        for raw in templates:
            if isinstance(raw, dict):
                selected = raw
                break

    return selected


def apply_assumption_set_to_settings(
    *,
    plan_settings: dict[str, Any],
    assumption_sets_payload: dict[str, Any] | None,
    assumption_set_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    merged = dict(plan_settings)
    if not isinstance(assumption_sets_payload, dict):
        return merged, None

    sets = assumption_sets_payload.get("sets")
    if not isinstance(sets, list) or not sets:
        return merged, None

    target_id = str(assumption_set_id or assumption_sets_payload.get("active_assumption_set_id") or "").strip().lower()
    selected: dict[str, Any] | None = None
    for raw in sets:
        if not isinstance(raw, dict):
            continue
        candidate_id = str(raw.get("id") or "").strip().lower()
        if candidate_id and candidate_id == target_id:
            selected = raw
            break

    if selected is None:
        for raw in sets:
            if isinstance(raw, dict):
                selected = raw
                break
    if selected is None:
        return merged, None

    for key in (
        "expected_return_baseline",
        "expected_return_optimistic",
        "expected_return_conservative",
        "inflation_rate",
        "marginal_tax_rate",
        "state_tax_rate",
        "simulation_mode",
        "simulation_monte_carlo_variant",
        "simulation_historical_start_year",
        "simulation_seed",
        "roth_conversion_annual_amount_usd",
        "roth_conversion_start_age",
        "roth_conversion_end_age",
    ):
        value = selected.get(key)
        if value is None:
            continue
        merged[key] = value

    merged["assumption_set_id"] = str(selected.get("id") or "").strip() or None
    merged["assumption_set_name"] = str(selected.get("name") or "").strip() or None
    return merged, selected


def build_contribution_allocation_for_plan_settings(
    *,
    plan_settings: dict[str, Any],
    contribution_rules_payload: dict[str, Any] | None = None,
    accounts_override: list[dict[str, Any]] | None = None,
) -> ContributionAllocationResponse | None:
    annual_contribution_raw = plan_settings.get("annual_contribution_usd")
    if annual_contribution_raw is None:
        return None

    annual_contribution_usd = max(0.0, _coerce_float(annual_contribution_raw, 0.0))
    accounts = accounts_override if accounts_override is not None else build_planning_accounts_from_portfolio()
    if not accounts:
        return None

    payload = contribution_rules_payload or {}
    rules = payload.get("rules") if isinstance(payload.get("rules"), list) else []
    base_rule = payload.get("base_rule") if isinstance(payload.get("base_rule"), dict) else {"type": "save"}
    profile_id = str(payload.get("profile_id") or "").strip() or None
    age = _coerce_int(payload.get("age"), 35)
    if age < 0:
        age = 0
    if age > 120:
        age = 120

    if not rules and (profile_id is None or profile_id == "tax_optimized_high_earner"):
        generated = build_tax_optimized_high_earner_rules(
            accounts,
            employer_match_target_usd=max(
                0.0,
                _coerce_float(payload.get("employer_match_target_usd"), 6000.0),
            ),
        )
        rules = generated.get("rules", [])
        base_rule = generated.get("base_rule", base_rule)
        profile_id = generated.get("profile_id", "tax_optimized_high_earner")

    allocation_payload = allocate_contributions(
        annual_contribution_usd=annual_contribution_usd,
        accounts=accounts,
        rules=rules,
        base_rule=base_rule,
        age=age,
        profile_id=profile_id,
    )
    return ContributionAllocationResponse(**allocation_payload)


def build_income_projection_from_profile(
    *,
    years: int,
    start_year: int | None = None,
    default_annual_growth_rate: float | None = None,
) -> IncomeProjectionResponse | None:
    profile_payload = get_financial_profile_payload()
    income_rows = profile_payload.get("income_items")
    if not isinstance(income_rows, list) or not income_rows:
        return None

    resolved_start_year = start_year or utc_now().year
    resolved_years = max(1, min(_coerce_int(years, settings.planner_years_to_retirement), 80))
    resolved_default_growth = (
        settings.planner_inflation
        if default_annual_growth_rate is None
        else max(-1.0, min(1.0, _coerce_float(default_annual_growth_rate, settings.planner_inflation)))
    )

    payload = project_income_schedule(
        income_rows,
        start_year=resolved_start_year,
        years=resolved_years,
        default_annual_growth_rate=resolved_default_growth,
    )
    return IncomeProjectionResponse(**payload)


def build_income_projection_for_plan_settings(plan_settings: dict[str, Any]) -> IncomeProjectionResponse | None:
    years = _coerce_int(plan_settings.get("years"), settings.planner_years_to_retirement)
    inflation_rate = (
        settings.planner_inflation
        if plan_settings.get("inflation_rate") is None
        else max(-1.0, min(1.0, _coerce_float(plan_settings.get("inflation_rate"), settings.planner_inflation)))
    )
    return build_income_projection_from_profile(
        years=years,
        start_year=utc_now().year,
        default_annual_growth_rate=inflation_rate,
    )


def build_expense_projection_from_profile(
    *,
    years: int,
    start_year: int | None = None,
    default_inflation_rate: float | None = None,
) -> ExpenseProjectionResponse | None:
    profile_payload = get_financial_profile_payload()
    expense_rows = profile_payload.get("expense_items")
    if not isinstance(expense_rows, list) or not expense_rows:
        return None

    resolved_start_year = start_year or utc_now().year
    resolved_years = max(1, min(_coerce_int(years, settings.planner_years_to_retirement), 80))
    resolved_default_rate = (
        settings.planner_inflation
        if default_inflation_rate is None
        else max(-1.0, min(1.0, _coerce_float(default_inflation_rate, settings.planner_inflation)))
    )

    payload = project_expense_schedule(
        expense_rows,
        start_year=resolved_start_year,
        years=resolved_years,
        default_inflation_rate=resolved_default_rate,
    )
    return ExpenseProjectionResponse(**payload)


def build_expense_projection_for_plan_settings(plan_settings: dict[str, Any]) -> ExpenseProjectionResponse | None:
    years = _coerce_int(plan_settings.get("years"), settings.planner_years_to_retirement)
    inflation_rate = (
        settings.planner_inflation
        if plan_settings.get("inflation_rate") is None
        else max(-1.0, min(1.0, _coerce_float(plan_settings.get("inflation_rate"), settings.planner_inflation)))
    )
    return build_expense_projection_from_profile(
        years=years,
        start_year=utc_now().year,
        default_inflation_rate=inflation_rate,
    )


def build_debt_projection_from_profile(
    *,
    max_years: int,
    start_date: date | None = None,
) -> DebtProjectionResponse | None:
    profile_payload = get_financial_profile_payload()
    debt_rows = profile_payload.get("debt_items")
    if not isinstance(debt_rows, list) or not debt_rows:
        return None

    resolved_years = max(1, min(_coerce_int(max_years, settings.planner_years_to_retirement), 80))
    resolved_start_date = start_date or utc_now().date().replace(day=1)

    preferred_strategy = "minimum"
    for debt in debt_rows:
        if not isinstance(debt, dict):
            continue
        strategy = str(debt.get("payoff_strategy") or "minimum").strip().lower()
        if strategy in {"snowball", "avalanche", "custom"}:
            preferred_strategy = strategy
            break

    payload = project_debt_payoff(
        debt_rows,
        start_date=resolved_start_date,
        max_years=resolved_years,
        strategy=preferred_strategy,  # type: ignore[arg-type]
        monthly_accelerated_payment_usd=0.0,
    )
    return DebtProjectionResponse(**payload)


def build_debt_projection_for_plan_settings(plan_settings: dict[str, Any]) -> DebtProjectionResponse | None:
    years = _coerce_int(plan_settings.get("years"), settings.planner_years_to_retirement)
    return build_debt_projection_from_profile(
        max_years=years,
        start_date=utc_now().date().replace(day=1),
    )


def build_social_security_projection_for_plan_settings(
    *,
    plan_settings: dict[str, Any],
    timeline_payload: dict[str, Any],
    income_projection: IncomeProjectionResponse | None,
    start_year: int,
    current_age: int = 35,
) -> SocialSecurityProjectionResponse | None:
    retirement_payload = timeline_payload.get("retirement")
    if not isinstance(retirement_payload, dict):
        return None

    years = max(1, min(_coerce_int(plan_settings.get("years"), settings.planner_years_to_retirement), 80))
    claiming_age_raw = retirement_payload.get("social_security_claiming_age")
    birth_year_raw = retirement_payload.get("social_security_birth_year")
    life_expectancy_raw = retirement_payload.get("social_security_life_expectancy_age")
    fra_monthly_raw = retirement_payload.get("social_security_fra_monthly_benefit_usd")
    estimated_earnings_raw = retirement_payload.get("social_security_estimated_annual_earnings_usd")

    claiming_age = None if claiming_age_raw is None else max(62, min(_coerce_int(claiming_age_raw, 67), 70))
    birth_year = None if birth_year_raw is None else max(1900, min(_coerce_int(birth_year_raw, 0), 2500))
    life_expectancy_age = (
        None if life_expectancy_raw is None else max(67, min(_coerce_int(life_expectancy_raw, 90), 120))
    )

    fra_monthly_benefit = (
        None
        if fra_monthly_raw is None
        else max(0.0, _coerce_float(fra_monthly_raw, 0.0))
    )
    estimated_annual_earnings = (
        None
        if estimated_earnings_raw is None
        else max(0.0, _coerce_float(estimated_earnings_raw, 0.0))
    )

    if estimated_annual_earnings is None and income_projection is not None:
        estimated_annual_earnings = max(0.0, float(income_projection.first_year_gross_income_usd))

    if (fra_monthly_benefit is None or fra_monthly_benefit <= 0) and (
        estimated_annual_earnings is None or estimated_annual_earnings <= 0
    ):
        return None

    payload = project_social_security_income(
        start_year=start_year,
        years=years,
        current_age=current_age,
        claiming_age=claiming_age,
        life_expectancy_age=life_expectancy_age,
        birth_year=birth_year,
        fra_monthly_benefit_usd=fra_monthly_benefit,
        estimated_annual_earnings_usd=estimated_annual_earnings,
        claim_age_options=[62, 67, 70],
        cola_rate=(
            settings.planner_inflation
            if plan_settings.get("inflation_rate") is None
            else max(-0.2, min(0.2, _coerce_float(plan_settings.get("inflation_rate"), settings.planner_inflation)))
        ),
    )
    return SocialSecurityProjectionResponse(**payload)


def build_rmd_projection_for_plan_settings(
    *,
    plan_settings: dict[str, Any],
    timeline_payload: dict[str, Any],
    start_year: int,
    current_age: int = 35,
    accounts_override: list[dict[str, Any]] | None = None,
) -> RmdProjectionResponse | None:
    accounts = accounts_override if accounts_override is not None else build_planning_accounts_from_portfolio()
    if not accounts:
        return None

    years = max(1, min(_coerce_int(plan_settings.get("years"), settings.planner_years_to_retirement), 80))
    retirement_payload = timeline_payload.get("retirement")
    if not isinstance(retirement_payload, dict):
        retirement_payload = {}

    rmd_birth_year_raw = retirement_payload.get("rmd_birth_year")
    if rmd_birth_year_raw is None:
        rmd_birth_year_raw = retirement_payload.get("social_security_birth_year")
    rmd_birth_year = (
        None
        if rmd_birth_year_raw is None
        else max(1900, min(_coerce_int(rmd_birth_year_raw, 0), 2500))
    )

    rmd_start_age_raw = retirement_payload.get("rmd_start_age")
    rmd_start_age = (
        None
        if rmd_start_age_raw is None
        else max(72, min(_coerce_int(rmd_start_age_raw, 73), 120))
    )

    expected_return_raw = plan_settings.get("expected_return_baseline")
    expected_return = (
        settings.planner_expected_return_baseline
        if expected_return_raw is None
        else max(-0.95, min(1.0, _coerce_float(expected_return_raw, settings.planner_expected_return_baseline)))
    )

    payload = project_rmd_schedule(
        accounts=accounts,
        start_year=start_year,
        years=years,
        current_age=max(0, min(_coerce_int(current_age, 35), 120)),
        birth_year=rmd_birth_year,
        expected_return=expected_return,
        start_age_override=rmd_start_age,
    )
    return RmdProjectionResponse(**payload)


def resolve_plan_timeline_payload(plan_detail: dict[str, Any]) -> dict[str, Any]:
    files_payload = plan_detail.get("files")
    if not isinstance(files_payload, dict):
        return {
            "schema_version": 2,
            "events": [],
            "retirement": {
                "target_retirement_age": None,
                "withdrawal_strategy": None,
                "drawdown_order": None,
                "social_security_birth_year": None,
                "social_security_claiming_age": None,
                "social_security_life_expectancy_age": None,
                "social_security_fra_monthly_benefit_usd": None,
                "social_security_estimated_annual_earnings_usd": None,
                "rmd_birth_year": None,
                "rmd_start_age": None,
            },
        }

    raw_timeline = files_payload.get("timeline_json")
    if not isinstance(raw_timeline, str):
        return {
            "schema_version": 2,
            "events": [],
            "retirement": {
                "target_retirement_age": None,
                "withdrawal_strategy": None,
                "drawdown_order": None,
                "social_security_birth_year": None,
                "social_security_claiming_age": None,
                "social_security_life_expectancy_age": None,
                "social_security_fra_monthly_benefit_usd": None,
                "social_security_estimated_annual_earnings_usd": None,
                "rmd_birth_year": None,
                "rmd_start_age": None,
            },
        }

    try:
        payload = json.loads(raw_timeline)
    except json.JSONDecodeError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}
    payload.setdefault("schema_version", 2)
    payload.setdefault("events", [])
    payload.setdefault(
        "retirement",
        {
            "target_retirement_age": None,
            "withdrawal_strategy": None,
            "drawdown_order": None,
            "social_security_birth_year": None,
            "social_security_claiming_age": None,
            "social_security_life_expectancy_age": None,
            "social_security_fra_monthly_benefit_usd": None,
            "social_security_estimated_annual_earnings_usd": None,
            "rmd_birth_year": None,
            "rmd_start_age": None,
        },
    )
    return payload


def resolve_timeline_retirement_age(timeline_payload: dict[str, Any]) -> int | None:
    retirement = timeline_payload.get("retirement")
    if not isinstance(retirement, dict):
        return None
    raw_age = retirement.get("target_retirement_age")
    if raw_age is None:
        return None
    age = _coerce_int(raw_age, -1)
    if age < 18 or age > 100:
        return None
    return age


def resolve_timeline_withdrawal_strategy(timeline_payload: dict[str, Any]) -> str | None:
    retirement = timeline_payload.get("retirement")
    if not isinstance(retirement, dict):
        return None
    strategy = str(retirement.get("withdrawal_strategy") or "").strip()
    return strategy or None


def resolve_timeline_drawdown_order(timeline_payload: dict[str, Any]) -> str | None:
    retirement = timeline_payload.get("retirement")
    if not isinstance(retirement, dict):
        return None
    drawdown_order = str(retirement.get("drawdown_order") or "").strip()
    return drawdown_order or None


def _add_months(anchor: date, months: int) -> date:
    safe_months = max(0, months)
    month_index = (anchor.year * 12) + (anchor.month - 1) + safe_months
    year = month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)


def normalize_branch_events_payload(
    *,
    raw_branch_events: list[dict[str, Any]] | None,
    start_year: int,
) -> list[dict[str, Any]]:
    if not raw_branch_events:
        return []

    normalized_events: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_branch_events, start=1):
        if not isinstance(raw, dict):
            continue

        label = str(raw.get("label") or "").strip()
        if not label:
            continue

        event_type = str(raw.get("event_type") or "milestone").strip().lower()
        if event_type not in TIMELINE_EVENT_TYPES:
            event_type = "milestone"

        impact_type = str(raw.get("impact_type") or "").strip().lower()
        if not impact_type:
            impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")
        if impact_type not in TIMELINE_IMPACT_TYPES:
            impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")
        if impact_type not in TIMELINE_IMPACT_TYPES:
            impact_type = "portfolio"

        recurring_frequency = str(raw.get("recurring_frequency") or "one_time").strip().lower()
        if recurring_frequency not in TIMELINE_FREQUENCIES:
            recurring_frequency = "one_time"

        amount_usd = _coerce_float(raw.get("amount_usd"), 0.0)
        if amount_usd == 0:
            continue

        start_year_offset = max(0, min(_coerce_int(raw.get("start_year_offset"), 0), 80))
        start_date = date(start_year + start_year_offset, 1, 1)

        duration_months_raw = raw.get("duration_months")
        duration_months: int | None = None
        if duration_months_raw is not None:
            resolved_duration_months = _coerce_int(duration_months_raw, 0)
            if resolved_duration_months > 0:
                duration_months = min(resolved_duration_months, 80 * 12)

        end_date: date | None = None
        if recurring_frequency != "one_time" and duration_months is not None:
            end_date = _add_months(start_date, duration_months - 1)

        event_id = str(raw.get("id") or f"branch-event-{index}").strip() or f"branch-event-{index}"
        normalized_events.append(
            {
                "id": event_id,
                "date": start_date.isoformat(),
                "label": label,
                "event_type": event_type,
                "impact_type": impact_type,
                "amount_usd": amount_usd,
                "recurring_frequency": recurring_frequency,
                "end_date": end_date.isoformat() if end_date is not None else None,
                "account_id": str(raw.get("account_id") or "").strip() or None,
                "notes": str(raw.get("notes") or "").strip(),
            }
        )

    return normalized_events


def build_branch_timeline_payload(
    *,
    base_timeline_payload: dict[str, Any],
    raw_branch_events: list[dict[str, Any]] | None,
    start_year: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized_branch_events = normalize_branch_events_payload(
        raw_branch_events=raw_branch_events,
        start_year=start_year,
    )

    base_events = base_timeline_payload.get("events")
    if not isinstance(base_events, list):
        base_events = []
    merged_events = [item for item in base_events if isinstance(item, dict)] + normalized_branch_events

    retirement_payload = base_timeline_payload.get("retirement")
    if not isinstance(retirement_payload, dict):
        retirement_payload = {}

    return (
        {
            "schema_version": 2,
            "events": merged_events,
            "retirement": retirement_payload,
        },
        normalized_branch_events,
    )


def build_timeline_projection_for_plan_settings(
    *,
    plan_settings: dict[str, Any],
    timeline_payload: dict[str, Any],
) -> TimelineImpactProjectionResponse | None:
    events = timeline_payload.get("events")
    if not isinstance(events, list) or not events:
        return None

    years = max(1, min(_coerce_int(plan_settings.get("years"), settings.planner_years_to_retirement), 80))
    payload = project_timeline_impacts(
        [item for item in events if isinstance(item, dict)],
        start_year=utc_now().year,
        years=years,
    )
    return TimelineImpactProjectionResponse(**payload)


async def run_scenarios_for_plan_settings(
    current_portfolio_value_usd: float,
    plan_settings: dict[str, Any],
    income_projection: IncomeProjectionResponse | None = None,
    expense_projection: ExpenseProjectionResponse | None = None,
    debt_projection: DebtProjectionResponse | None = None,
    timeline_projection: TimelineImpactProjectionResponse | None = None,
    contribution_allocation: ContributionAllocationResponse | None = None,
    social_security_projection: SocialSecurityProjectionResponse | None = None,
    rmd_projection: RmdProjectionResponse | None = None,
    assumption_set: dict[str, Any] | None = None,
    retirement_age: int | None = None,
    timeline_withdrawal_strategy: str | None = None,
    timeline_drawdown_order: str | None = None,
    household_source: str = "plan_settings",
) -> PlanningResponse:
    validate_plan_return_relationships(plan_settings)
    service = build_plan_simulation_service_for_plan_settings(plan_settings)
    annual_contribution = plan_settings.get("annual_contribution_usd")
    years = plan_settings.get("years")
    hsa_extra = plan_settings.get("hsa_extra_contribution_usd")
    resolved_years = int(years) if years is not None else int(service.scenario_engine.years_to_retirement)
    resolved_start_year = utc_now().year
    household_settings = _resolve_household_settings(
        plan_settings=plan_settings,
        start_year=resolved_start_year,
        years=resolved_years,
    )

    resolved_annual_contribution = (
        float(annual_contribution)
        if annual_contribution is not None
        else None
    )
    resolved_portfolio_value = float(current_portfolio_value_usd)
    planning_accounts: list[dict[str, Any]] | None = build_planning_accounts_from_portfolio() or None
    income_projection_payload: dict[str, Any] | None = None
    expense_projection_payload: dict[str, Any] | None = None
    debt_projection_payload: dict[str, Any] | None = None
    timeline_projection_payload: dict[str, Any] | None = None
    contribution_allocation_payload: dict[str, Any] | None = None
    social_security_projection_payload: dict[str, Any] | None = None
    rmd_projection_payload: dict[str, Any] | None = None

    if income_projection is not None:
        income_projection_payload = income_projection.model_dump(mode="json")

    if expense_projection is not None:
        expense_projection_payload = expense_projection.model_dump(mode="json")

    (
        income_projection_payload,
        expense_projection_payload,
        household_adjustments_payload,
    ) = _apply_household_adjustments_to_projection_payloads(
        income_projection=income_projection_payload,
        expense_projection=expense_projection_payload,
        household_settings=household_settings,
        start_year=resolved_start_year,
        start_age=35,
        years=resolved_years,
    )
    if income_projection_payload is not None:
        income_projection = IncomeProjectionResponse(**income_projection_payload)
    if expense_projection_payload is not None:
        expense_projection = ExpenseProjectionResponse(**expense_projection_payload)

    if debt_projection is not None:
        debt_projection_payload = debt_projection.model_dump(mode="json")

    if timeline_projection is not None:
        timeline_projection_payload = timeline_projection.model_dump(mode="json")
        resolved_portfolio_value = max(
            0.0,
            resolved_portfolio_value + float(timeline_projection.first_year_portfolio_impact_usd),
        )
        if resolved_annual_contribution is None:
            resolved_annual_contribution = float(
                annual_contribution
                if annual_contribution is not None
                else service.scenario_engine.annual_contribution_usd
            )
        resolved_annual_contribution = max(
            0.0,
            float(resolved_annual_contribution) + float(timeline_projection.first_year_contribution_impact_usd),
        )

    if contribution_allocation is not None:
        resolved_annual_contribution = float(contribution_allocation.total_contributions_usd)
        planning_accounts = []
        for item in contribution_allocation.allocations:
            planning_accounts.append(
                {
                    "account_id": item.account_id,
                    "account_type": item.account_type,
                    "balance_usd": item.balance_usd,
                    "annual_contribution_usd": item.total_contribution_usd,
                    "tax_treatment": tax_treatment_for_account_type(item.account_type),
                }
            )
        contribution_allocation_payload = contribution_allocation.model_dump(mode="json")
    if social_security_projection is not None:
        social_security_projection_payload = social_security_projection.model_dump(mode="json")
    if rmd_projection is not None:
        rmd_projection_payload = rmd_projection.model_dump(mode="json")

    filing_status = _resolve_filing_status_for_household(
        filing_status=plan_settings.get("filing_status"),
        household_mode=str(household_settings.get("household_mode") or HOUSEHOLD_MODE_INDIVIDUAL),
    )
    state_tax_rate_raw = plan_settings.get("state_tax_rate")
    state_tax_rate = (
        max(0.0, min(1.0, _coerce_float(state_tax_rate_raw, 0.0)))
        if state_tax_rate_raw is not None
        else None
    )
    include_irmaa = _coerce_bool(plan_settings.get("include_irmaa"), True)
    roth_conversion_annual_amount = max(
        0.0,
        _coerce_float(plan_settings.get("roth_conversion_annual_amount_usd"), 0.0),
    )
    roth_conversion_start_age: int | None = None
    roth_conversion_end_age: int | None = None
    if plan_settings.get("roth_conversion_start_age") is not None:
        roth_conversion_start_age = max(
            0,
            min(120, _coerce_int(plan_settings.get("roth_conversion_start_age"), 0)),
        )
    if plan_settings.get("roth_conversion_end_age") is not None:
        roth_conversion_end_age = max(
            0,
            min(120, _coerce_int(plan_settings.get("roth_conversion_end_age"), 0)),
        )
    if (
        roth_conversion_start_age is not None
        and roth_conversion_end_age is not None
        and roth_conversion_start_age > roth_conversion_end_age
    ):
        roth_conversion_start_age, roth_conversion_end_age = (
            roth_conversion_end_age,
            roth_conversion_start_age,
        )
    withdrawal_strategy = str(plan_settings.get("withdrawal_strategy") or "").strip() or None
    if not withdrawal_strategy:
        withdrawal_strategy = str(timeline_withdrawal_strategy or "").strip() or None
    drawdown_order = str(plan_settings.get("drawdown_order") or "").strip() or None
    if not drawdown_order:
        drawdown_order = str(timeline_drawdown_order or "").strip() or None
    result = await service.run(
        current_portfolio_value_usd=resolved_portfolio_value,
        annual_contribution_usd=resolved_annual_contribution,
        years=resolved_years,
        hsa_extra_contribution_usd=(float(hsa_extra) if hsa_extra is not None else None),
        accounts=planning_accounts,
        income_projection=income_projection_payload,
        expense_projection=expense_projection_payload,
        debt_projection=debt_projection_payload,
        timeline_projection=timeline_projection_payload,
        contribution_allocation=contribution_allocation_payload,
        social_security_projection=social_security_projection_payload,
        rmd_projection=rmd_projection_payload,
        filing_status=filing_status,
        state_tax_rate=state_tax_rate,
        include_irmaa=include_irmaa,
        roth_conversion_annual_amount_usd=roth_conversion_annual_amount,
        roth_conversion_start_age=roth_conversion_start_age,
        roth_conversion_end_age=roth_conversion_end_age,
        drawdown_order=drawdown_order,
        household_mode=str(household_settings.get("household_mode") or HOUSEHOLD_MODE_INDIVIDUAL),
        household_partner_income_usd=household_settings.get("household_partner_income_usd"),
        household_partner_income_growth_rate=household_settings.get("household_partner_income_growth_rate"),
        household_partner_retirement_age=household_settings.get("household_partner_retirement_age"),
        household_partner_social_security_annual_usd=household_settings.get("household_partner_social_security_annual_usd"),
        household_partner_social_security_claiming_age=household_settings.get("household_partner_social_security_claiming_age"),
        household_shared_goal_target_usd=household_settings.get("household_shared_goal_target_usd"),
        household_shared_goal_target_year=household_settings.get("household_shared_goal_target_year"),
        household_shared_goal_annual_funding_usd=household_adjustments_payload.get("shared_goal_annual_funding_usd"),
        household_partner_income_added_first_year_usd=household_adjustments_payload.get("partner_income_added_first_year_usd"),
        household_partner_income_added_total_usd=household_adjustments_payload.get("partner_income_added_total_usd"),
        start_year=resolved_start_year,
        withdrawal_strategy=withdrawal_strategy,
        retirement_age=retirement_age,
        simulation_mode=plan_settings.get("simulation_mode"),
        simulation_monte_carlo_variant=plan_settings.get("simulation_monte_carlo_variant"),
        simulation_historical_start_year=plan_settings.get("simulation_historical_start_year"),
        simulation_seed=plan_settings.get("simulation_seed"),
        assumption_set_id=(str(assumption_set.get("id")) if isinstance(assumption_set, dict) and assumption_set.get("id") else None),
        assumption_set_name=(str(assumption_set.get("name")) if isinstance(assumption_set, dict) and assumption_set.get("name") else None),
    )
    household_context = _build_household_response_context(
        household_settings=household_settings,
        household_adjustments=household_adjustments_payload,
        filing_status=filing_status,
        source=household_source,
    )
    return _apply_household_context_to_planning_response(
        response=result,
        household_context=household_context,
    )


def resolve_portfolio_value(
    current_portfolio_value_usd: float | None,
    *,
    store: SnapshotStore | None = None,
) -> float:
    if current_portfolio_value_usd is not None:
        return float(current_portfolio_value_usd)

    resolved_store = store or snapshot_store
    try:
        latest_snapshot = resolved_store.latest()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail="Provide current_portfolio_value_usd or create a snapshot first",
        ) from exc

    return float(latest_snapshot.total_value_usd)


def build_scenario_diff_payload(
    base_result: PlanningResponse,
    candidate_result: PlanningResponse,
) -> tuple[list[dict[str, Any]], dict[str, float | int | None], dict[str, Any]]:
    return _build_scenario_diff_payload(
        base_result=base_result,
        candidate_result=candidate_result,
        candidate_label="candidate",
    )


def _normalize_simulation_summary(raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        return {}

    mode = _normalize_optional_simulation_mode(raw_payload.get("mode"))
    timeline_mode = _normalize_optional_simulation_mode(raw_payload.get("timeline_mode"))
    monte_carlo_variant = _normalize_optional_simulation_monte_carlo_variant(
        raw_payload.get("monte_carlo_variant")
    )
    seed = _normalize_optional_simulation_int(
        raw_payload.get("seed"),
        minimum=0,
        maximum=2_147_483_647,
    )
    requested_historical_start_year = _normalize_optional_simulation_int(
        raw_payload.get("requested_historical_start_year"),
        minimum=min(HISTORICAL_YEARS),
        maximum=max(HISTORICAL_YEARS),
    )
    resolved_historical_raw = raw_payload.get("resolved_historical_start_year_by_scenario")
    resolved_historical: dict[str, int] = {}
    if isinstance(resolved_historical_raw, dict):
        for label, raw_value in resolved_historical_raw.items():
            normalized_year = _normalize_optional_simulation_int(
                raw_value,
                minimum=min(HISTORICAL_YEARS),
                maximum=max(HISTORICAL_YEARS),
            )
            if normalized_year is None:
                continue
            label_text = str(label or "").strip().lower()
            if not label_text:
                continue
            resolved_historical[label_text] = normalized_year

    normalized: dict[str, Any] = {}
    if mode is not None:
        normalized["mode"] = mode
    if timeline_mode is not None:
        normalized["timeline_mode"] = timeline_mode
    if monte_carlo_variant is not None:
        normalized["monte_carlo_variant"] = monte_carlo_variant
    if seed is not None:
        normalized["seed"] = seed
    if requested_historical_start_year is not None:
        normalized["requested_historical_start_year"] = requested_historical_start_year
    if resolved_historical:
        normalized["resolved_historical_start_year_by_scenario"] = resolved_historical

    resolved_mode = normalized.get("mode")
    resolved_timeline_mode = normalized.get("timeline_mode")
    if isinstance(resolved_mode, str) and not isinstance(resolved_timeline_mode, str):
        normalized["timeline_mode"] = "fixed" if resolved_mode == "monte_carlo" else resolved_mode
        resolved_timeline_mode = normalized.get("timeline_mode")

    if resolved_mode != "monte_carlo":
        normalized.pop("monte_carlo_variant", None)
    if resolved_mode == "fixed":
        normalized.pop("seed", None)
    if resolved_timeline_mode != "historical":
        normalized.pop("requested_historical_start_year", None)
        normalized.pop("resolved_historical_start_year_by_scenario", None)
    return normalized


def _build_simulation_delta_payload(
    *,
    base_result: PlanningResponse,
    candidate_result: PlanningResponse,
    candidate_label: str,
) -> dict[str, Any]:
    base_simulation = _normalize_simulation_summary(base_result.simulation)
    candidate_simulation = _normalize_simulation_summary(candidate_result.simulation)
    return {
        "base": base_simulation,
        candidate_label: candidate_simulation,
        "changed": base_simulation != candidate_simulation,
    }


def _build_scenario_diff_payload(
    *,
    base_result: PlanningResponse,
    candidate_result: PlanningResponse,
    candidate_label: str,
) -> tuple[list[dict[str, Any]], dict[str, float | int | None], dict[str, Any]]:
    scenario_deltas: list[dict[str, Any]] = []
    base_by_label = {item.label: item for item in base_result.scenarios}
    candidate_by_label = {item.label: item for item in candidate_result.scenarios}

    for label in ("baseline", "optimistic", "conservative", "hsa_delta"):
        base_scenario = base_by_label.get(label)
        candidate_scenario = candidate_by_label.get(label)
        if base_scenario is None or candidate_scenario is None:
            continue

        scenario_deltas.append(
            ScenarioComparisonRow(
                label=label,
                base_future_value_usd=float(base_scenario.future_value_usd),
                candidate_future_value_usd=float(candidate_scenario.future_value_usd),
                delta_future_value_usd=round(
                    float(candidate_scenario.future_value_usd) - float(base_scenario.future_value_usd),
                    2,
                ),
                base_real_value_usd=float(base_scenario.real_value_usd),
                candidate_real_value_usd=float(candidate_scenario.real_value_usd),
                delta_real_value_usd=round(
                    float(candidate_scenario.real_value_usd) - float(base_scenario.real_value_usd),
                    2,
                ),
            ).model_dump(mode="json")
        )

    monte_keys = ("p10_future_value_usd", "p50_future_value_usd", "p90_future_value_usd")
    monte_delta: dict[str, float | int | None] = {
        "runs": base_result.monte_carlo.get("runs"),
    }

    for key in monte_keys:
        base_value = base_result.monte_carlo.get(key)
        candidate_value = candidate_result.monte_carlo.get(key)
        base_float = float(base_value) if isinstance(base_value, (float, int)) else None
        candidate_float = float(candidate_value) if isinstance(candidate_value, (float, int)) else None
        monte_delta[f"base_{key}"] = base_float
        monte_delta[f"candidate_{key}"] = candidate_float
        if base_float is None or candidate_float is None:
            monte_delta[f"delta_{key}"] = None
        else:
            monte_delta[f"delta_{key}"] = round(candidate_float - base_float, 2)

    simulation_delta = _build_simulation_delta_payload(
        base_result=base_result,
        candidate_result=candidate_result,
        candidate_label=candidate_label,
    )

    return scenario_deltas, monte_delta, simulation_delta


async def compute_plan_scenario_branch(
    *,
    plan_id: str,
    branch_name: str,
    current_portfolio_value_usd: float | None,
    assumption_set_id: str | None,
    branch_template_id: str | None,
    compare_updates: dict[str, Any],
    raw_branch_events: list[dict[str, Any]] | None,
    services: WorkspaceServices | None = None,
) -> dict[str, Any]:
    resolved_services = workspace_services_or_legacy(services)
    detail = resolved_services.plan_workspace.get_plan(plan_id)
    timeline_payload = resolve_plan_timeline_payload(detail)
    retirement_age = resolve_timeline_retirement_age(timeline_payload)
    timeline_withdrawal_strategy = resolve_timeline_withdrawal_strategy(timeline_payload)
    timeline_drawdown_order = resolve_timeline_drawdown_order(timeline_payload)
    assumption_sets_payload = resolve_plan_assumption_sets(detail)
    branch_templates_payload = resolve_plan_branch_templates(detail)
    selected_branch_template = (
        select_branch_template(
            branch_templates_payload=branch_templates_payload,
            branch_template_id=branch_template_id,
        )
        if branch_template_id
        else None
    )
    if branch_template_id and selected_branch_template is None:
        raise ValueError(f"Unknown branch_template_id: {branch_template_id}")

    template_assumption_set_id = None
    template_compare_settings: dict[str, Any] = {}
    template_branch_events: list[dict[str, Any]] = []
    template_branch_name = None
    if isinstance(selected_branch_template, dict):
        template_assumption_set_id = (
            str(selected_branch_template.get("assumption_set_id") or "").strip() or None
        )
        template_branch_name = str(selected_branch_template.get("branch_name") or "").strip() or None
        raw_template_compare = selected_branch_template.get("compare_settings")
        if isinstance(raw_template_compare, dict):
            template_compare_settings = extract_plan_settings_updates(raw_template_compare)
        raw_template_events = selected_branch_template.get("branch_events")
        if isinstance(raw_template_events, list):
            template_branch_events = [item for item in raw_template_events if isinstance(item, dict)]

    base_settings_raw = detail.get("settings", {})
    if not isinstance(base_settings_raw, dict):
        base_settings_raw = {}
    resolved_assumption_set_id = assumption_set_id or template_assumption_set_id
    base_settings, active_assumption_set = apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=resolved_assumption_set_id,
    )
    merged_compare_updates = dict(template_compare_settings)
    merged_compare_updates.update(compare_updates)
    branch_settings = merge_plan_settings(base_settings, merged_compare_updates)

    start_year = utc_now().year
    merged_branch_events = [*template_branch_events]
    if raw_branch_events:
        merged_branch_events.extend(raw_branch_events)
    deduped_branch_events: list[dict[str, Any]] = []
    seen_branch_event_keys: set[str] = set()
    for item in merged_branch_events:
        if not isinstance(item, dict):
            continue
        dedupe_payload = {
            "label": item.get("label"),
            "event_type": item.get("event_type"),
            "impact_type": item.get("impact_type"),
            "amount_usd": item.get("amount_usd"),
            "recurring_frequency": item.get("recurring_frequency"),
            "start_year_offset": item.get("start_year_offset"),
            "duration_months": item.get("duration_months"),
            "account_id": item.get("account_id"),
            "notes": item.get("notes"),
        }
        dedupe_key = json.dumps(dedupe_payload, sort_keys=True, default=str)
        if dedupe_key in seen_branch_event_keys:
            continue
        seen_branch_event_keys.add(dedupe_key)
        deduped_branch_events.append(item)
    branch_timeline_payload, normalized_branch_events = build_branch_timeline_payload(
        base_timeline_payload=timeline_payload,
        raw_branch_events=deduped_branch_events,
        start_year=start_year,
    )
    if not normalized_branch_events and not merged_compare_updates:
        raise ValueError("Scenario branch requires branch_events and/or compare_settings overrides.")

    resolved_branch_name = str(branch_name or "").strip() or "What-If Branch"
    if resolved_branch_name == "What-If Branch" and template_branch_name:
        resolved_branch_name = template_branch_name

    base_income_projection = build_income_projection_for_plan_settings(base_settings)
    branch_income_projection = build_income_projection_for_plan_settings(branch_settings)
    base_expense_projection = build_expense_projection_for_plan_settings(base_settings)
    branch_expense_projection = build_expense_projection_for_plan_settings(branch_settings)
    base_debt_projection = build_debt_projection_for_plan_settings(base_settings)
    branch_debt_projection = build_debt_projection_for_plan_settings(branch_settings)
    base_timeline_projection = build_timeline_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
    )
    branch_timeline_projection = build_timeline_projection_for_plan_settings(
        plan_settings=branch_settings,
        timeline_payload=branch_timeline_payload,
    )

    contribution_rules_payload = resolve_plan_contribution_rules(detail)
    base_contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings=base_settings,
        contribution_rules_payload=contribution_rules_payload,
    )
    branch_contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings=branch_settings,
        contribution_rules_payload=contribution_rules_payload,
    )

    base_social_security_projection = build_social_security_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        income_projection=base_income_projection,
        start_year=start_year,
    )
    branch_social_security_projection = build_social_security_projection_for_plan_settings(
        plan_settings=branch_settings,
        timeline_payload=branch_timeline_payload,
        income_projection=branch_income_projection,
        start_year=start_year,
    )

    base_rmd_projection = build_rmd_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        start_year=start_year,
    )
    branch_rmd_projection = build_rmd_projection_for_plan_settings(
        plan_settings=branch_settings,
        timeline_payload=branch_timeline_payload,
        start_year=start_year,
    )

    current_value = resolve_portfolio_value(
        current_portfolio_value_usd,
        store=resolved_services.snapshot_store,
    )
    base_result = await run_scenarios_for_plan_settings(
        current_portfolio_value_usd=current_value,
        plan_settings=base_settings,
        income_projection=base_income_projection,
        expense_projection=base_expense_projection,
        debt_projection=base_debt_projection,
        timeline_projection=base_timeline_projection,
        contribution_allocation=base_contribution_allocation,
        social_security_projection=base_social_security_projection,
        rmd_projection=base_rmd_projection,
        assumption_set=active_assumption_set,
        retirement_age=retirement_age,
        timeline_withdrawal_strategy=timeline_withdrawal_strategy,
        timeline_drawdown_order=timeline_drawdown_order,
    )
    branch_result = await run_scenarios_for_plan_settings(
        current_portfolio_value_usd=current_value,
        plan_settings=branch_settings,
        income_projection=branch_income_projection,
        expense_projection=branch_expense_projection,
        debt_projection=branch_debt_projection,
        timeline_projection=branch_timeline_projection,
        contribution_allocation=branch_contribution_allocation,
        social_security_projection=branch_social_security_projection,
        rmd_projection=branch_rmd_projection,
        assumption_set=active_assumption_set,
        retirement_age=retirement_age,
        timeline_withdrawal_strategy=timeline_withdrawal_strategy,
        timeline_drawdown_order=timeline_drawdown_order,
    )
    scenario_deltas, monte_carlo_delta, simulation_delta = _build_scenario_diff_payload(
        base_result=base_result,
        candidate_result=branch_result,
        candidate_label="branch",
    )

    return {
        "plan_id": plan_id,
        "branch_name": resolved_branch_name,
        "branch_template_id": (
            str(selected_branch_template.get("id"))
            if isinstance(selected_branch_template, dict) and selected_branch_template.get("id")
            else None
        ),
        "branch_template_name": (
            str(selected_branch_template.get("name"))
            if isinstance(selected_branch_template, dict) and selected_branch_template.get("name")
            else None
        ),
        "current_portfolio_value_usd": current_value,
        "base_settings": base_settings,
        "branch_settings": branch_settings,
        "assumption_set": active_assumption_set,
        "branch_events": normalized_branch_events,
        "base_result": base_result.model_dump(mode="json"),
        "branch_result": branch_result.model_dump(mode="json"),
        "scenario_deltas": scenario_deltas,
        "monte_carlo_delta": monte_carlo_delta,
        "simulation_delta": simulation_delta,
    }


def resolve_plan_id_or_active(
    requested_plan_id: object | None,
    *,
    workspace: PlanWorkspace | None = None,
) -> str:
    resolved_workspace = workspace or plan_workspace
    plan_id = str(requested_plan_id).strip() if isinstance(requested_plan_id, str) else ""
    if plan_id:
        return plan_id

    active_plan_id = resolved_workspace.get_active_plan_id()
    if active_plan_id:
        return active_plan_id

    raise ValueError("No active plan is configured and no plan_id was provided.")


def summarize_holding_value_changes(
    latest_snapshot: PortfolioSnapshot,
    older_snapshot: PortfolioSnapshot | None,
    limit: int = 10,
) -> list[dict[str, object]]:
    if older_snapshot is None:
        return []

    previous_by_symbol: dict[str, dict[str, Any]] = {}
    for holding in older_snapshot.holdings:
        previous_by_symbol[holding.symbol] = {
            "value_usd": float(holding.value_usd),
            "allocation_percent": float(holding.allocation_percent),
        }

    changes: list[dict[str, object]] = []
    for holding in latest_snapshot.holdings:
        previous = previous_by_symbol.get(holding.symbol, {"value_usd": 0.0, "allocation_percent": 0.0})
        value_delta = float(holding.value_usd) - float(previous.get("value_usd", 0.0))
        allocation_delta = float(holding.allocation_percent) - float(previous.get("allocation_percent", 0.0))
        changes.append(
            {
                "symbol": holding.symbol,
                "name": holding.name,
                "latest_value_usd": round(float(holding.value_usd), 2),
                "previous_value_usd": round(float(previous.get("value_usd", 0.0)), 2),
                "delta_value_usd": round(value_delta, 2),
                "delta_allocation_percent": round(allocation_delta, 3),
            }
        )

    changes.sort(key=lambda item: abs(float(item.get("delta_value_usd", 0.0))), reverse=True)
    return changes[: max(1, limit)]


def build_snapshot_history_payload(
    limit: int = 30,
    *,
    store: SnapshotStore | None = None,
) -> SnapshotHistoryResponse:
    resolved_store = store or snapshot_store
    bounded_limit = max(2, min(int(limit), 365))
    history = resolved_store.recent(limit=bounded_limit)

    if not history:
        return SnapshotHistoryResponse(points=[], window_points=0)

    points = []
    for snapshot in history:
        points.append(
            {
                "as_of": snapshot.as_of,
                "total_value_usd": round(snapshot.total_value_usd, 2),
                "net_performance_usd": round(snapshot.net_performance_usd, 2),
                "net_performance_percent": round(snapshot.net_performance_percent, 4),
                "holdings_count": len(snapshot.holdings),
            }
        )

    latest = history[0]
    oldest = history[-1]
    delta_total_value = latest.total_value_usd - oldest.total_value_usd
    delta_percent = None
    if oldest.total_value_usd:
        delta_percent = (delta_total_value / oldest.total_value_usd) * 100

    return SnapshotHistoryResponse(
        points=points,
        window_points=len(points),
        latest_as_of=latest.as_of,
        oldest_as_of=oldest.as_of,
        delta_total_value_usd=round(delta_total_value, 2),
        delta_total_value_percent=(round(delta_percent, 4) if delta_percent is not None else None),
        delta_net_performance_usd=round(latest.net_performance_usd - oldest.net_performance_usd, 2),
        top_holding_value_changes=summarize_holding_value_changes(latest, oldest, limit=10),
    )


def resolve_active_plan_detail(*, workspace: PlanWorkspace | None = None) -> dict[str, Any] | None:
    resolved_workspace = workspace or plan_workspace
    active_plan_id = resolved_workspace.get_active_plan_id()
    if not active_plan_id:
        return None

    try:
        return resolved_workspace.get_plan(active_plan_id)
    except PlanNotFoundError:
        return None


def get_financial_profile_payload(
    profile_store: FinancialProfileStore | None = None,
) -> dict[str, Any]:
    resolved_store = profile_store or financial_profile_store
    payload = resolved_store.get()
    tax_profile = payload.get("tax_profile")
    if isinstance(tax_profile, dict) and not tax_profile.get("state"):
        tax_profile["state"] = settings.app_state
        payload["tax_profile"] = tax_profile
    return payload


def save_financial_profile_payload(
    request: FinancialProfileRequest,
    *,
    source: str = "profile_editor",
    profile_store: FinancialProfileStore | None = None,
) -> dict[str, Any]:
    resolved_store = profile_store or financial_profile_store
    payload = request.model_dump(mode="json")

    for key in ("income_items", "expense_items", "debt_items", "goal_items", "physical_assets"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            label_key = "label"
            label = str(row.get(label_key) or "").strip()
            row[label_key] = label or "Untitled"

    members = payload.get("household_members")
    if isinstance(members, list):
        for member in members:
            if not isinstance(member, dict):
                continue
            display_name = str(member.get("display_name") or "").strip()
            member["display_name"] = display_name or "Household member"

    tax_profile = payload.get("tax_profile")
    if isinstance(tax_profile, dict) and not tax_profile.get("state"):
        tax_profile["state"] = settings.app_state
        payload["tax_profile"] = tax_profile

    try:
        return resolved_store.save(payload, metadata_source=source)
    except TypeError:
        return resolved_store.save(payload)


PROFILE_AUDIT_SECTION_ORDER = [
    "household_members",
    "income_items",
    "expense_items",
    "debt_items",
    "goal_items",
    "physical_assets",
    "tax_profile",
    "investment_policy",
    "flags",
    "notes",
]


def _has_meaningful_profile_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value is True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    if isinstance(value, dict):
        return any(_has_meaningful_profile_value(item) for item in value.values())
    if hasattr(value, "model_dump"):
        return _has_meaningful_profile_value(value.model_dump(mode="json"))
    return True


def _profile_update_sections_from_payload(payload: Any) -> list[str]:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    if not isinstance(payload, dict):
        return []
    sections: list[str] = []
    for key in PROFILE_AUDIT_SECTION_ORDER:
        if key in payload and _has_meaningful_profile_value(payload.get(key)):
            sections.append(key)
    for key in payload:
        if key not in PROFILE_AUDIT_SECTION_ORDER and _has_meaningful_profile_value(payload.get(key)):
            sections.append(str(key))
    return sections


def _record_profile_update_activity(
    *,
    source: str,
    sections: list[str],
    via_copilot: bool = False,
) -> None:
    cleaned_sections = [str(section).strip() for section in sections if str(section).strip()]
    if not cleaned_sections:
        cleaned_sections = ["financial_profile"]
    event_type = "copilot_profile_update" if via_copilot else "profile_update"
    title = "Copilot profile update applied" if via_copilot else "Financial profile updated"
    section_label = ", ".join(section.replace("_", " ") for section in cleaned_sections[:5])
    if len(cleaned_sections) > 5:
        section_label = f"{section_label}, and {len(cleaned_sections) - 5} more"
    try:
        _git_activity_store().record(
            event_type=event_type,
            title=title,
            message=f"Updated profile sections: {section_label}.",
            status="applied",
            paths=["profile/financial_profile.json"],
            metadata={
                "source": str(source or ("copilot_tool" if via_copilot else "profile_editor")),
                "sections": cleaned_sections,
                "via_copilot": via_copilot,
            },
        )
    except Exception:
        pass


def _record_copilot_recommendation_apply_activity(result: Any, arguments: dict[str, object]) -> None:
    try:
        recommendation = getattr(result, "recommendation", None)
        recommendation_id = str(getattr(recommendation, "id", "") or arguments.get("recommendation_id") or "")
        title = str(getattr(recommendation, "title", "") or recommendation_id or "Recommendation")
        plan = getattr(result, "plan", None)
        plan_id = str(getattr(plan, "id", "") or arguments.get("plan_id") or "")
        paths = ["recommendations/inbox.json"]
        for artifact_attr in ("decision_packet_artifact", "decision_closure_artifact"):
            artifact = getattr(result, artifact_attr, None)
            file_name = getattr(artifact, "file_name", None)
            if file_name:
                paths.append(str(file_name))
        _git_activity_store().record(
            event_type="copilot_recommendation_apply",
            title="Copilot applied recommendation",
            message=str(getattr(result, "message", "") or f"Applied {title}."),
            status="applied",
            paths=paths,
            metadata={
                "source": "copilot_tool",
                "recommendation_id": recommendation_id,
                "recommendation_title": title,
                "plan_id": plan_id or None,
                "decision_status": str(arguments.get("decision_status") or "accepted"),
            },
        )
    except Exception:
        pass


def _recommendation_list(
    *,
    limit: int = 100,
    status: str | None = None,
    plan_id: str | None = None,
    include_archived: bool = False,
    sort: str | None = None,
    inbox: RecommendationInbox | None = None,
) -> list[dict[str, Any]]:
    resolved_inbox = inbox or recommendation_inbox
    cleaned_status = str(status or "").strip().lower() or None
    status_filter = None
    if cleaned_status in {"proposed", "applied", "rejected", "archived"}:
        status_filter = cleaned_status

    resolved_plan_id = plan_id.strip() if isinstance(plan_id, str) and plan_id.strip() else None
    raw_rows = resolved_inbox.list(
        limit=None,
        status=status_filter,  # type: ignore[arg-type]
        plan_id=resolved_plan_id,
        include_archived=include_archived,
        sort="none",
    )
    calibration_rows = resolved_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    return score_and_sort_recommendations(
        raw_rows,
        sort=normalize_recommendation_sort(sort),
        limit=max(1, min(int(limit), 500)),
        calibration_rows=calibration_rows,
    )


def _recommendation_item_from_row(row: dict[str, Any]) -> RecommendationItem:
    scored_rows = score_and_sort_recommendations([row], sort="created_at", limit=1)
    payload = scored_rows[0] if scored_rows else row
    return RecommendationItem(**payload)


def _normalized_recommendation_priority(value: Any) -> str:
    priority = str(value or "medium").strip().lower()
    if priority in {"high", "medium", "low"}:
        return priority
    return "medium"


def _normalized_recommendation_type(value: Any) -> str:
    recommendation_type = str(value or "general").strip().lower()
    if recommendation_type in {"plan_settings_update", "workflow_action", "general"}:
        return recommendation_type
    return "general"


def _quality_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _recommendation_quality_payload(row: dict[str, Any]) -> dict[str, Any]:
    action_payload = row.get("action_payload")
    if not isinstance(action_payload, dict):
        return {}
    quality = action_payload.get("quality")
    if isinstance(quality, dict):
        return quality
    return {}


def _recommendation_quality_summary(quality: dict[str, Any]) -> str | None:
    if not quality:
        return None
    impact = quality.get("impact") if isinstance(quality.get("impact"), dict) else {}
    parts = [
        f"{_quality_text(impact.get('level'))} impact" if _quality_text(impact.get("level")) else "",
        f"{_quality_text(quality.get('confidence_level'))} confidence" if _quality_text(quality.get("confidence_level")) else "",
        f"{_quality_text(quality.get('freshness_status'))} evidence" if _quality_text(quality.get("freshness_status")) else "",
        _quality_text(quality.get("actionability")),
        "decision-grade" if bool(quality.get("decision_grade")) else "",
    ]
    cleaned = [part for part in parts if part]
    return " · ".join(cleaned) if cleaned else None


def _top_action_hint_for_quality(quality: dict[str, Any]) -> str:
    actionability = _quality_text(quality.get("actionability"))
    if actionability == "previewable":
        return "Open Recommendation Inbox to preview before applying."
    if actionability == "context-gathering":
        return "Open Recommendation Inbox or Copilot to complete missing context."
    if actionability == "review-only":
        return "Open Recommendation Inbox to review."
    return "Open Recommendation Inbox to preview/apply."


def _as_top_next_action(row: dict[str, Any]) -> TopNextAction:
    score = row.get("score")
    score_payload = score if isinstance(score, dict) else {}
    raw_reasons = score_payload.get("reasons")
    score_reasons = [
        str(reason).strip()
        for reason in raw_reasons
        if str(reason).strip()
    ] if isinstance(raw_reasons, list) else []

    score_rank = score_payload.get("rank")
    normalized_rank = (
        int(score_rank)
        if isinstance(score_rank, int) and score_rank > 0
        else None
    )
    score_total = None
    if "total" in score_payload:
        score_total = round(_coerce_float(score_payload.get("total"), 0.0), 2)

    quality = _recommendation_quality_payload(row)
    blocking_context = quality.get("blocking_context") if isinstance(quality.get("blocking_context"), list) else []
    recommendation_id = str(row.get("id") or "").strip() or None
    return TopNextAction(
        recommendation_id=recommendation_id,
        title=str(row.get("title") or recommendation_id or "Recommendation").strip() or "Recommendation",
        detail=str(row.get("detail") or "").strip(),
        priority=_normalized_recommendation_priority(row.get("priority")),
        recommendation_type=_normalized_recommendation_type(row.get("recommendation_type")),
        source=str(row.get("source") or "manual").strip() or "manual",
        plan_id=(str(row.get("plan_id") or "").strip() or None),
        score_total=score_total,
        score_rank=normalized_rank,
        score_reasons=score_reasons[:3],
        quality_summary=_recommendation_quality_summary(quality),
        quality_actionability=_quality_text(quality.get("actionability")) or None,
        quality_decision_grade=bool(quality.get("decision_grade")) if quality else None,
        blocking_context=[str(item).strip() for item in blocking_context if str(item).strip()],
        action_hint=_top_action_hint_for_quality(quality),
    )


def _build_top_next_actions(
    *,
    plan_id: str | None = None,
    limit: int = 3,
    inbox: RecommendationInbox | None = None,
) -> list[TopNextAction]:
    try:
        bounded_limit = max(1, min(int(limit), 10))
    except Exception:
        bounded_limit = 3

    resolved_plan_id = str(plan_id or "").strip() or None
    try:
        ranked_rows = _recommendation_list(
            limit=500,
            status="proposed",
            sort="ranked",
            inbox=inbox,
        )
    except Exception:
        return []

    if not ranked_rows:
        return []

    scoped_rows: list[dict[str, Any]] = []
    for row in ranked_rows:
        if not resolved_plan_id:
            scoped_rows.append(row)
            continue
        row_plan_id = str(row.get("plan_id") or "").strip() or None
        if row_plan_id in {None, resolved_plan_id}:
            scoped_rows.append(row)

    selected_rows = scoped_rows if scoped_rows else ranked_rows
    return [_as_top_next_action(row) for row in selected_rows[:bounded_limit]]


def _build_today_command_cards(
    dashboard: TodayDashboardResponse,
    services: WorkspaceServices | None = None,
) -> list[TodayCommandCard]:
    resolved_services = workspace_services_or_legacy(services)
    cards = list(dashboard.command_cards)
    cards.append(_build_cash_runway_command_card(dashboard))
    investment_policy_card = _build_investment_policy_command_card(dashboard)
    if investment_policy_card is not None:
        cards.append(investment_policy_card)
    cards.append(_build_research_readiness_command_card(dashboard))
    cards.append(_build_trust_durability_command_card(resolved_services))
    try:
        proposed_rows = resolved_services.recommendation_inbox.list(
            limit=500,
            status="proposed",
            sort="created_at_desc",
        )
        closed_rows = resolved_services.recommendation_inbox.list(
            limit=500,
            include_archived=True,
            sort="created_at_desc",
        )
    except Exception:
        return _replace_enriched_what_changed_card(
            dashboard,
            cards,
            resolved_services.today_review_checkpoint_store.latest(),
        )

    stale_rows = [
        row for row in proposed_rows
        if str(row.get("source") or "").strip().lower() == "generator:stale_assumptions"
    ]
    first_stale_id = str(stale_rows[0].get("id") or "").strip() if stale_rows else ""
    cards.append(
        TodayCommandCard(
            id="stale-assumptions",
            title="Stale assumptions",
            status="warning" if stale_rows else "ready",
            detail=(
                f"{len(stale_rows)} assumption review(s) are open before advice can be fully trusted."
                if stale_rows
                else "No stale assumption reviews are currently open."
            ),
            metric_label="Open",
            metric_value=str(len(stale_rows)),
            action_label="Review assumptions" if stale_rows else "Open inbox",
            href=f"#inbox?focus={first_stale_id}" if first_stale_id else "#inbox",
        )
    )

    copilot_rows = [
        row for row in proposed_rows
        if str(row.get("source") or "").strip().lower().startswith("copilot:")
    ]
    first_copilot_id = str(copilot_rows[0].get("id") or "").strip() if copilot_rows else ""
    cards.append(_build_copilot_drafts_command_card(copilot_rows, first_copilot_id))

    pending_outcomes = [
        row for row in closed_rows
        if _recommendation_needs_outcome(row)
    ]
    pending_process_outcomes = [
        row for row in pending_outcomes
        if _recommendation_needs_process_outcome(row)
    ]
    pending_thesis_outcomes = [
        row for row in pending_process_outcomes
        if _recommendation_has_thesis_revision(row)
    ]
    pending_pre_mortem_outcomes = [
        row for row in pending_outcomes
        if _recommendation_pre_mortem(row)
    ]
    first_pending_id = str(pending_outcomes[0].get("id") or "").strip() if pending_outcomes else ""
    pending_detail = "Closed recommendations have no pending outcome capture."
    pending_action_label = "Log outcome" if pending_outcomes else "Review outcomes"
    if pending_pre_mortem_outcomes:
        first_pre_mortem = _recommendation_pre_mortem(pending_pre_mortem_outcomes[0])
        first_pending_id = str(pending_pre_mortem_outcomes[0].get("id") or "").strip() or first_pending_id
        risk = str(first_pre_mortem.get("main_risk") or "").strip()
        pending_detail = f"{len(pending_pre_mortem_outcomes)} pre-mortem check(s) are ready for outcome review."
        if risk:
            pending_detail = f"{pending_detail} First risk: {risk}"
        pending_action_label = "Check pre-mortem"
    elif pending_process_outcomes:
        pending_detail = (
            f"{len(pending_process_outcomes)} investment/research review(s) need decision-process calibration."
        )
    elif pending_outcomes:
        pending_detail = f"{len(pending_outcomes)} closed recommendation(s) still need realized outcome capture."
    cards.append(
        TodayCommandCard(
            id="outcome-loop",
            title="Outcome loop",
            status="warning" if pending_outcomes else "ready",
            detail=pending_detail,
            metric_label="Pending",
            metric_value=str(len(pending_outcomes)),
            action_label=pending_action_label,
            href=f"#inbox?focus={first_pending_id}" if first_pending_id else "#inbox",
        )
    )
    thesis_outcome_card = _build_thesis_outcome_command_card(pending_thesis_outcomes)
    if thesis_outcome_card is not None:
        cards.append(thesis_outcome_card)
    closure_analytics_payload = _build_today_closure_analytics_payload(
        resolved_services.recommendation_inbox,
    ) or {}
    investment_calibration_card = _build_investment_calibration_command_card(closure_analytics_payload)
    if investment_calibration_card is not None:
        cards.append(investment_calibration_card)
    thesis_calibration_card = _build_thesis_calibration_command_card(closure_analytics_payload)
    if thesis_calibration_card is not None:
        cards.append(thesis_calibration_card)

    return _replace_enriched_what_changed_card(
        dashboard,
        cards,
        resolved_services.today_review_checkpoint_store.latest(),
    )


def _replace_enriched_what_changed_card(
    dashboard: TodayDashboardResponse,
    cards: list[TodayCommandCard],
    last_review_checkpoint: dict[str, Any] | None,
) -> list[TodayCommandCard]:
    filtered_cards = [card for card in cards if card.id != "what-changed"]
    insert_at = min(5, len(filtered_cards))
    filtered_cards.insert(
        insert_at,
        _build_enriched_what_changed_card(
            dashboard,
            last_review_checkpoint,
            cards=filtered_cards,
        ),
    )
    return filtered_cards


def _build_enriched_what_changed_card(
    dashboard: TodayDashboardResponse,
    last_review_checkpoint: dict[str, Any] | None,
    *,
    cards: list[TodayCommandCard] | None = None,
) -> TodayCommandCard:
    if not last_review_checkpoint:
        return TodayCommandCard(
            id="what-changed",
            title="What changed",
            status="ready",
            detail="No completed daily review checkpoint yet. Mark today reviewed to make future changes visible.",
            metric_label="Changes",
            metric_value="New",
            action_label="Mark reviewed",
            href="#today?review=complete",
        )

    changes = _today_review_change_sentences(
        dashboard,
        last_review_checkpoint,
        cards=cards,
    )
    if not changes:
        return TodayCommandCard(
            id="what-changed",
            title="What changed",
            status="ready",
            detail="No meaningful changes since the last completed daily review.",
            metric_label="Changes",
            metric_value="0",
            action_label="Mark reviewed",
            href="#today?review=complete",
        )

    return TodayCommandCard(
        id="what-changed",
        title="What changed",
        status="warning",
        detail=" ".join(changes[:3]),
        metric_label="Changes",
        metric_value=str(len(changes)),
        action_label="Mark reviewed",
        href="#today?review=complete",
    )


def _today_review_change_sentences(
    dashboard: TodayDashboardResponse,
    last_review_checkpoint: dict[str, Any],
    *,
    cards: list[TodayCommandCard] | None = None,
) -> list[str]:
    changes: list[str] = []
    previous_total = _coerce_optional_float(last_review_checkpoint.get("total_value_usd"))
    if dashboard.total_value_usd is not None and previous_total is not None:
        delta = dashboard.total_value_usd - previous_total
        if abs(delta) >= 1000:
            direction = "higher" if delta > 0 else "lower"
            changes.append(f"Portfolio value is {_format_today_usd_delta(delta)} {direction} since last review.")

    previous_top_symbol = str(last_review_checkpoint.get("top_holding_symbol") or "").strip().upper()
    current_top_symbol = str(dashboard.top_holding_symbol or "").strip().upper()
    if previous_top_symbol and current_top_symbol and previous_top_symbol != current_top_symbol:
        changes.append(f"Top holding changed from {previous_top_symbol} to {current_top_symbol}.")
    else:
        previous_top_percent = _coerce_optional_float(last_review_checkpoint.get("top_holding_percent"))
        if dashboard.top_holding_percent is not None and previous_top_percent is not None:
            delta_points = dashboard.top_holding_percent - previous_top_percent
            if abs(delta_points) >= 5:
                symbol = current_top_symbol or "Top holding"
                direction = "higher" if delta_points > 0 else "lower"
                changes.append(f"{symbol} concentration is {abs(delta_points):.1f} points {direction}.")

    previous_runway = _coerce_optional_float(last_review_checkpoint.get("emergency_fund_months"))
    runway_changed = False
    if dashboard.emergency_fund_months is not None and previous_runway is not None:
        delta_runway = dashboard.emergency_fund_months - previous_runway
        if abs(delta_runway) >= 1:
            direction = "higher" if delta_runway > 0 else "lower"
            changes.append(f"Cash runway is {abs(delta_runway):.1f} months {direction}.")
            runway_changed = True
    previous_health = str(last_review_checkpoint.get("financial_health_status") or "").strip()
    current_health = str(dashboard.financial_health_status or "").strip()
    if not runway_changed and previous_health and current_health and previous_health != current_health:
        changes.append(
            f"Financial health changed from {previous_health.replace('_', ' ')} to {current_health.replace('_', ' ')}."
        )

    command_card_statuses = (
        last_review_checkpoint.get("command_card_statuses")
        if isinstance(last_review_checkpoint.get("command_card_statuses"), dict)
        else {}
    )
    current_card_statuses = _today_command_card_statuses(cards if cards is not None else dashboard.command_cards)
    research_change = _today_command_card_status_change(
        "research-readiness",
        "Research readiness",
        command_card_statuses,
        current_card_statuses,
    )
    if research_change:
        changes.append(research_change)

    copilot_delta = _today_card_metric_delta(
        "copilot-drafts",
        command_card_statuses,
        current_card_statuses,
    )
    if copilot_delta is not None and copilot_delta > 0:
        changes.append(f"{copilot_delta} new Copilot-drafted review(s) are waiting.")

    previous_top_action_ids = _string_list(last_review_checkpoint.get("top_next_action_ids"))
    current_top_action_ids = [
        str(action.recommendation_id or action.title or "").strip()
        for action in dashboard.top_next_actions[:3]
        if str(action.recommendation_id or action.title or "").strip()
    ]
    if previous_top_action_ids and current_top_action_ids and previous_top_action_ids[:3] != current_top_action_ids[:3]:
        title = dashboard.top_next_actions[0].title if dashboard.top_next_actions else "a new recommendation"
        changes.append(f"Top recommendation changed to {title}.")

    previous_inbox = _coerce_int(last_review_checkpoint.get("inbox_high_priority_count"), -1)
    if previous_inbox >= 0 and dashboard.inbox_high_priority_count != previous_inbox:
        delta_inbox = dashboard.inbox_high_priority_count - previous_inbox
        if delta_inbox > 0:
            changes.append(f"{delta_inbox} high-priority recommendation(s) are now open.")
        elif dashboard.inbox_high_priority_count == 0:
            changes.append("High-priority recommendation queue is clear.")
        else:
            changes.append(f"High-priority recommendation queue fell to {dashboard.inbox_high_priority_count}.")

    previous_profile = _coerce_optional_float(last_review_checkpoint.get("profile_completion_percent"))
    profile_percent = (
        dashboard.profile_readiness.completion_percent
        if dashboard.profile_readiness is not None
        else dashboard.onboarding_completion_percent
    )
    if previous_profile is not None:
        delta_profile = profile_percent - previous_profile
        if abs(delta_profile) >= 5:
            direction = "improved" if delta_profile > 0 else "fell"
            changes.append(f"Profile readiness {direction} to {round(profile_percent)}%.")

    previous_plan_id = str(last_review_checkpoint.get("active_plan_id") or "").strip()
    current_plan_id = str(dashboard.active_plan.id if dashboard.active_plan is not None else "").strip()
    previous_plan_updated = _parse_optional_datetime(last_review_checkpoint.get("active_plan_updated_at"))
    current_plan_updated = dashboard.active_plan.updated_at if dashboard.active_plan is not None else None
    if previous_plan_id and current_plan_id and previous_plan_id != current_plan_id:
        changes.append("Active plan changed since the last review.")
    elif previous_plan_updated is not None and current_plan_updated is not None and current_plan_updated > previous_plan_updated:
        changes.append("Active plan changed since the last review.")

    return changes


def _format_today_usd_delta(value: float) -> str:
    rounded = round(value)
    prefix = "-" if rounded < 0 else ""
    return f"{prefix}${abs(rounded):,}"


def _today_command_card_statuses(cards: list[TodayCommandCard]) -> dict[str, dict[str, str]]:
    tracked_ids = {"research-readiness", "copilot-drafts"}
    statuses: dict[str, dict[str, str]] = {}
    for card in cards:
        if card.id not in tracked_ids:
            continue
        statuses[card.id] = {
            "status": str(card.status or "ready"),
            "metric_value": str(card.metric_value or ""),
        }
    return statuses


def _today_command_card_status_change(
    card_id: str,
    label: str,
    previous: dict[str, Any],
    current: dict[str, dict[str, str]],
) -> str | None:
    previous_card = previous.get(card_id) if isinstance(previous.get(card_id), dict) else {}
    current_card = current.get(card_id) if isinstance(current.get(card_id), dict) else {}
    previous_status = str(previous_card.get("status") or "").strip()
    current_status = str(current_card.get("status") or "").strip()
    if previous_status and current_status and previous_status != current_status:
        return f"{label} changed from {previous_status} to {current_status}."
    previous_metric = str(previous_card.get("metric_value") or "").strip()
    current_metric = str(current_card.get("metric_value") or "").strip()
    if previous_metric and current_metric and previous_metric != current_metric:
        return f"{label} changed from {previous_metric} to {current_metric}."
    return None


def _today_card_metric_delta(
    card_id: str,
    previous: dict[str, Any],
    current: dict[str, dict[str, str]],
) -> int | None:
    previous_card = previous.get(card_id) if isinstance(previous.get(card_id), dict) else {}
    current_card = current.get(card_id) if isinstance(current.get(card_id), dict) else {}
    if not previous_card or not current_card:
        return None
    previous_metric = _coerce_int(previous_card.get("metric_value"), 0)
    current_metric = _coerce_int(current_card.get("metric_value"), 0)
    return current_metric - previous_metric


def _build_today_confidence_domains(dashboard: TodayDashboardResponse) -> list[TodayConfidenceDomain]:
    readiness = dashboard.profile_readiness
    profile_percent = (
        readiness.completion_percent
        if readiness is not None
        else dashboard.onboarding_completion_percent
    )
    profile_status = "missing_context"
    profile_detail = "Profile readiness is unavailable."
    if readiness is not None:
        if readiness.status == "ready":
            profile_status = "decision_grade"
            profile_detail = "Profile context is complete enough for daily decision support."
        elif readiness.status == "attention" and profile_percent >= 70:
            profile_status = "usable_with_caveats"
            gap = readiness.next_gap_title or "remaining profile gaps"
            profile_detail = f"Profile context is usable, but {gap} still limits advice quality."
        else:
            gap = readiness.next_gap_title or "profile context"
            profile_detail = f"Complete {gap} before relying on stronger recommendations."

    cash_status = "missing_context"
    cash_detail = "Cash runway is unavailable."
    if dashboard.emergency_fund_months is not None:
        months = dashboard.emergency_fund_months
        if dashboard.financial_health_status == "critical" or months < 3:
            cash_status = "degraded"
            cash_detail = "Cash runway is below the minimum target and should constrain advice."
        elif dashboard.financial_health_status == "needs_attention" or months < 6:
            cash_status = "usable_with_caveats"
            cash_detail = "Cash runway is usable, but below the preferred target."
        else:
            cash_status = "decision_grade"
            cash_detail = "Cash runway is strong enough for normal decision support."

    tax_section = _profile_readiness_section(readiness, "tax_profile")
    if tax_section is None:
        tax_status = "missing_context"
        tax_detail = "Tax profile is not available for fit and planning advice."
    elif tax_section.status == "complete":
        tax_status = "decision_grade"
        tax_detail = "Tax profile is available for investment-fit and planning decisions."
    else:
        tax_status = "missing_context"
        tax_detail = tax_section.detail or "Tax profile is incomplete."

    if dashboard.active_plan is None:
        plan_status = "missing_context"
        plan_detail = "No active plan is available to anchor recommendations."
        plan_metric = None
    else:
        completion = dashboard.active_plan.settings_completion_percent
        if completion >= 90:
            plan_status = "decision_grade"
            plan_detail = "Active plan assumptions are complete enough for decision support."
        elif completion >= 60:
            plan_status = "usable_with_caveats"
            plan_detail = "Active plan is usable, but some assumptions still limit confidence."
        else:
            plan_status = "missing_context"
            plan_detail = "Active plan assumptions need more work before advice is reliable."
        plan_metric = f"{round(completion)}%"

    if dashboard.total_value_usd is None:
        portfolio_status = "missing_context"
        portfolio_detail = "Portfolio snapshot is unavailable."
    elif dashboard.concentration_risk == "high":
        portfolio_status = "degraded"
        symbol = dashboard.top_holding_symbol or "top holding"
        portfolio_detail = f"{symbol} concentration is high and should constrain fit decisions."
    elif dashboard.concentration_risk == "medium" or dashboard.snapshot_points_30d < 5:
        portfolio_status = "usable_with_caveats"
        portfolio_detail = "Portfolio context is usable, with concentration or history caveats."
    else:
        portfolio_status = "decision_grade"
        portfolio_detail = "Portfolio context is current enough for decision support."

    research_card = _today_command_card_by_id(dashboard.command_cards, "research-readiness")
    if research_card is None:
        research_status = "missing_context"
        research_detail = "Research evidence readiness has not been checked yet."
        research_metric_label = None
        research_metric_value = None
        research_href = "#research"
    else:
        research_status = _confidence_status_from_command_card(research_card)
        research_detail = research_card.detail
        research_metric_label = research_card.metric_label
        research_metric_value = research_card.metric_value
        research_href = research_card.href

    trust_card = _today_command_card_by_id(dashboard.command_cards, "trust-durability")
    if trust_card is None:
        trust_status = "missing_context"
        trust_detail = "Trust and durability status has not been checked yet."
        trust_metric_label = None
        trust_metric_value = None
        trust_href = "#atelier?section=trust"
    else:
        trust_status = _confidence_status_from_command_card(trust_card)
        trust_detail = trust_card.detail
        trust_metric_label = trust_card.metric_label
        trust_metric_value = trust_card.metric_value
        trust_href = trust_card.href

    provider_status = "decision_grade"
    provider_detail = "Provider and snapshot data are current enough for Today."
    if dashboard.context_state == "critical":
        provider_status = "degraded"
        provider_detail = "Data context is degraded and should block high-confidence advice."
    elif dashboard.snapshot_age_minutes is None or dashboard.total_value_usd is None:
        provider_status = "missing_context"
        provider_detail = "Snapshot/provider freshness is unavailable."
    elif dashboard.snapshot_age_minutes > 24 * 60:
        provider_status = "stale"
        provider_detail = "Snapshot data is more than 24 hours old."
    elif dashboard.context_state == "warning" or dashboard.snapshot_points_30d < 5:
        provider_status = "usable_with_caveats"
        provider_detail = "Data is usable, but freshness or history coverage is limited."

    outcome_card = _today_command_card_by_id(dashboard.command_cards, "outcome-loop")
    recommendation_status = "decision_grade"
    recommendation_detail = "Recommendation loop is calibrated and clear."
    recommendation_metric_label = "High priority"
    recommendation_metric_value = str(dashboard.inbox_high_priority_count)
    recommendation_href = "#inbox"
    if outcome_card is not None and outcome_card.status != "ready":
        recommendation_status = _confidence_status_from_command_card(outcome_card)
        recommendation_detail = outcome_card.detail
        recommendation_metric_label = outcome_card.metric_label
        recommendation_metric_value = outcome_card.metric_value
        recommendation_href = outcome_card.href
    elif dashboard.inbox_high_priority_count > 0:
        recommendation_status = "usable_with_caveats"
        recommendation_detail = "High-priority recommendations are waiting for review."

    return [
        TodayConfidenceDomain(
            id="profile",
            label="Profile",
            status=profile_status,
            detail=profile_detail,
            metric_label="Ready",
            metric_value=f"{round(profile_percent)}%",
            href="#copilot?intent=complete-context" if profile_status != "decision_grade" else "#copilot",
        ),
        TodayConfidenceDomain(
            id="cash",
            label="Cash",
            status=cash_status,
            detail=cash_detail,
            metric_label="Runway",
            metric_value=(
                f"{dashboard.emergency_fund_months:.1f} mo"
                if dashboard.emergency_fund_months is not None
                else "Unknown"
            ),
            href="#inbox" if cash_status != "missing_context" else "#copilot?intent=complete-context",
        ),
        TodayConfidenceDomain(
            id="taxes",
            label="Taxes",
            status=tax_status,
            detail=tax_detail,
            metric_label="Profile",
            metric_value="Ready" if tax_status == "decision_grade" else "Missing",
            href="#copilot?intent=complete-context",
        ),
        TodayConfidenceDomain(
            id="plan",
            label="Plan",
            status=plan_status,
            detail=plan_detail,
            metric_label="Complete" if plan_metric else None,
            metric_value=plan_metric,
            href="#plan",
        ),
        TodayConfidenceDomain(
            id="portfolio",
            label="Portfolio",
            status=portfolio_status,
            detail=portfolio_detail,
            metric_label="Top holding" if dashboard.top_holding_percent is not None else None,
            metric_value=(
                f"{dashboard.top_holding_percent:.0f}%"
                if dashboard.top_holding_percent is not None
                else None
            ),
            href="#portfolio",
        ),
        TodayConfidenceDomain(
            id="research",
            label="Research",
            status=research_status,
            detail=research_detail,
            metric_label=research_metric_label,
            metric_value=research_metric_value,
            href=research_href,
        ),
        TodayConfidenceDomain(
            id="provider_data",
            label="Provider data",
            status=provider_status,
            detail=provider_detail,
            metric_label="Age" if dashboard.snapshot_age_minutes is not None else None,
            metric_value=(
                f"{dashboard.snapshot_age_minutes}m"
                if dashboard.snapshot_age_minutes is not None
                else None
            ),
            href="#atelier",
        ),
        TodayConfidenceDomain(
            id="trust",
            label="Trust",
            status=trust_status,
            detail=trust_detail,
            metric_label=trust_metric_label,
            metric_value=trust_metric_value,
            href=trust_href,
        ),
        TodayConfidenceDomain(
            id="recommendations",
            label="Recommendations",
            status=recommendation_status,
            detail=recommendation_detail,
            metric_label=recommendation_metric_label,
            metric_value=recommendation_metric_value,
            href=recommendation_href,
        ),
    ]


def _profile_readiness_section(
    readiness: ProfileReadinessSummary | None,
    key: str,
) -> ProfileReadinessSection | None:
    if readiness is None:
        return None
    return next((section for section in readiness.sections if section.key == key), None)


def _today_command_card_by_id(cards: list[TodayCommandCard], card_id: str) -> TodayCommandCard | None:
    return next((card for card in cards if card.id == card_id), None)


def _confidence_status_from_command_card(card: TodayCommandCard) -> str:
    if card.status == "critical":
        return "degraded"
    if card.status == "warning":
        return "usable_with_caveats"
    return "decision_grade"


def _build_trust_durability_command_card(
    services: WorkspaceServices | None = None,
) -> TodayCommandCard:
    readiness = (
        build_release_readiness_response(services=services)
        if services is not None
        else build_release_readiness_response()
    )
    status: Literal["ready", "warning", "critical"] = "ready"
    if readiness.status == "blocked":
        status = "critical"
    elif readiness.status == "warning":
        status = "warning"

    issues = readiness.blocking_gaps + readiness.warnings
    detail_parts = [readiness.summary]
    if issues:
        detail_parts.extend(issues[:2])

    return TodayCommandCard(
        id="trust-durability",
        title="Trust & durability",
        status=status,
        detail=" ".join(detail_parts),
        metric_label="Ready",
        metric_value=f"{readiness.ready_count}/{readiness.total_count}",
        action_label="Review trust",
        href="#atelier?section=trust",
    )


RELEASE_READINESS_BACKUP_MAX_AGE_HOURS = 72
RELEASE_READINESS_RESTORE_PREVIEW_MAX_AGE_HOURS = 168
RELEASE_READINESS_WORKFLOW_MAX_AGE_HOURS = 168
RELEASE_READINESS_PRODUCT_TESTING_CHECKLIST = "docs/PRODUCT_TESTING_CHECKLIST_2026-04-30.md"


def _release_readiness_action(
    action_kind: str,
    label: str,
    detail: str = "",
    href: str | None = "#atelier?section=trust",
) -> ReleaseReadinessRecommendedAction:
    return ReleaseReadinessRecommendedAction(
        action_kind=action_kind,
        label=label,
        detail=detail,
        href=href,
    )


def _release_readiness_check(
    *,
    id: str,
    title: str,
    status: str,
    detail: str,
    domain: str,
    action_kind: str | None = None,
    href: str | None = "#atelier?section=trust",
    last_verified_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> ReleaseReadinessCheck:
    normalized_status = status if status in {"ready", "warning", "blocked"} else "warning"
    return ReleaseReadinessCheck(
        id=id,
        title=title,
        status=normalized_status,  # type: ignore[arg-type]
        detail=detail,
        domain=domain,  # type: ignore[arg-type]
        action_kind=action_kind,
        href=href,
        last_verified_at=last_verified_at,
        metadata=metadata or {},
    )


def _service_status_snapshot_sync() -> ServiceStatusResponse:
    return build_native_service_status()


def _hosted_identity_relevant_for_release() -> bool:
    if _auth_mode() in {"hosted", "oidc"}:
        return True
    return any(
        str(value or "").strip()
        for value in (
            settings.auth_oidc_issuer_url,
            settings.auth_oidc_client_id,
            settings.auth_oidc_redirect_uri,
            settings.auth_oidc_authorization_endpoint,
            settings.auth_oidc_token_endpoint,
            settings.auth_oidc_userinfo_endpoint,
        )
    )


def _hosted_identity_readiness_snapshot_sync() -> dict[str, Any]:
    return asyncio.run(hosted_identity_provider.readiness_report())


def _hosted_identity_release_readiness_check() -> tuple[
    ReleaseReadinessCheck,
    ReleaseReadinessRecommendedAction | None,
]:
    report = _hosted_identity_readiness_snapshot_sync()
    provider = str(report.get("provider") or "Hosted identity").strip()
    status = str(report.get("status") or "warning").strip().lower()
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    ready_count = sum(1 for check in checks if isinstance(check, dict) and check.get("status") == "ready")
    warning_count = sum(1 for check in checks if isinstance(check, dict) and check.get("status") == "warning")
    blocked_count = sum(1 for check in checks if isinstance(check, dict) and check.get("status") == "blocked")
    non_ready = [
        check for check in checks
        if isinstance(check, dict) and str(check.get("status") or "") != "ready"
    ]
    first_gap = str(
        (non_ready[0].get("summary") if non_ready else "")
        or (non_ready[0].get("detail") if non_ready else "")
        or ""
    ).strip()
    detail = (
        f"{provider} hosted sign-in readiness checks are passing."
        if status == "ready"
        else f"{provider} hosted sign-in has {blocked_count} blocker(s) and {warning_count} warning(s)."
    )
    if first_gap:
        detail = f"{detail} First item: {first_gap}"
    check = _release_readiness_check(
        id="hosted_identity",
        title="Hosted identity provider",
        status=status,
        detail=detail,
        domain="provider",
        action_kind=None if status == "ready" else "review_hosted_identity",
        href="#settings",
        metadata={
            "provider": provider,
            "hosted_auth_enabled": bool(report.get("hosted_auth_enabled")),
            "ready_count": ready_count,
            "warning_count": warning_count,
            "blocked_count": blocked_count,
            "checks": checks,
        },
    )
    action = None
    if status != "ready":
        action = _release_readiness_action(
            "review_hosted_identity",
            "Review hosted sign-in",
            "Open Settings and resolve hosted identity provider readiness before inviting hosted users.",
            href="#settings",
        )
    return check, action


def build_native_service_status() -> ServiceStatusResponse:
    services = [
        {
            "name": "portfolio_benchmark",
            "enabled": True,
            "reachable": True,
            "last_checked_at": utc_now(),
        },
        {
            "name": "portfolio_attribution",
            "enabled": True,
            "reachable": True,
            "last_checked_at": utc_now(),
        },
        {
            "name": "plan_simulation",
            "enabled": True,
            "reachable": True,
            "last_checked_at": utc_now(),
        },
    ]
    return ServiceStatusResponse(
        as_of=utc_now(),
        enabled_count=len(services),
        reachable_count=len(services),
        degraded_count=0,
        services=services,
    )


def _latest_activity_event(events: list[dict[str, Any]], event_type: str) -> dict[str, Any] | None:
    cleaned_type = str(event_type or "").strip().lower()
    for event in events:
        if str(event.get("event_type") or "").strip().lower() == cleaned_type:
            return event
    return None


def _backup_readiness_check(
    backups_payload: dict[str, Any],
    *,
    now: datetime,
) -> tuple[ReleaseReadinessCheck, ReleaseReadinessRecommendedAction | None]:
    backups = backups_payload.get("backups") if isinstance(backups_payload, dict) else []
    backup_list = backups if isinstance(backups, list) else []
    if not backup_list:
        return (
            _release_readiness_check(
                id="backup",
                title="Backup available",
                status="blocked",
                detail="No local backup archive is available.",
                domain="storage",
                action_kind="create_backup",
            ),
            _release_readiness_action(
                "create_backup",
                "Create backup",
                "Create a local backup before relying on today’s app state.",
            ),
        )

    latest = backup_list[0] if isinstance(backup_list[0], dict) else {}
    created_at = _parse_optional_datetime(latest.get("created_at"))
    age_hours = ((now - created_at).total_seconds() / 3600) if created_at else None
    backup_id = str(latest.get("backup_id") or "latest backup")
    if age_hours is not None and age_hours > RELEASE_READINESS_BACKUP_MAX_AGE_HOURS:
        return (
            _release_readiness_check(
                id="backup",
                title="Backup available",
                status="warning",
                detail=f"Latest backup {backup_id} is {age_hours:.0f} hours old.",
                domain="storage",
                action_kind="create_backup",
                last_verified_at=created_at,
                metadata={"backup_id": backup_id, "age_hours": round(age_hours, 2)},
            ),
            _release_readiness_action(
                "create_backup",
                "Create fresh backup",
                "Refresh the local backup before a broad product-testing pass.",
            ),
        )

    return (
        _release_readiness_check(
            id="backup",
            title="Backup available",
            status="ready",
            detail=f"Latest backup {backup_id} is available.",
            domain="storage",
            last_verified_at=created_at,
            metadata={"backup_id": backup_id, "age_hours": round(age_hours, 2) if age_hours is not None else None},
        ),
        None,
    )


def _workflow_verification_readiness_check(
    activity_events: list[dict[str, Any]],
    *,
    now: datetime,
) -> tuple[ReleaseReadinessCheck, ReleaseReadinessRecommendedAction | None]:
    event = _latest_activity_event(activity_events, "product_workflow_verification")
    action = _release_readiness_action(
        "run_product_testing",
        "Run product testing",
        "Run the feature-by-feature product testing checklist and record the result.",
        href=f"/{RELEASE_READINESS_PRODUCT_TESTING_CHECKLIST}",
    )
    if not event:
        return (
            _release_readiness_check(
                id="workflow_verification",
                title="Critical workflow verification",
                status="warning",
                detail="No product workflow verification run is recorded.",
                domain="workflow",
                action_kind="run_product_testing",
                href=f"/{RELEASE_READINESS_PRODUCT_TESTING_CHECKLIST}",
            ),
            action,
        )

    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    verified_at = _parse_optional_datetime(event.get("created_at"))
    age_hours = ((now - verified_at).total_seconds() / 3600) if verified_at else None
    workflow = str(metadata.get("workflow") or "product_testing").strip() or "product_testing"
    passed_count = _coerce_int(metadata.get("passed_count"), 0)
    failed_count = _coerce_int(metadata.get("failed_count"), 0)
    status = str(event.get("status") or "").strip().lower()
    checklist_path = str(
        metadata.get("checklist_path") or RELEASE_READINESS_PRODUCT_TESTING_CHECKLIST
    ).strip()
    base_metadata = {
        "workflow": workflow,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "checklist_path": checklist_path,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
    }

    if status == "failed" or failed_count > 0:
        return (
            _release_readiness_check(
                id="workflow_verification",
                title="Critical workflow verification",
                status="blocked",
                detail=f"Latest product workflow verification found {failed_count or 1} failing item(s).",
                domain="workflow",
                action_kind="run_product_testing",
                href=f"/{checklist_path}",
                last_verified_at=verified_at,
                metadata=base_metadata,
            ),
            action,
        )

    if age_hours is not None and age_hours > RELEASE_READINESS_WORKFLOW_MAX_AGE_HOURS:
        return (
            _release_readiness_check(
                id="workflow_verification",
                title="Critical workflow verification",
                status="warning",
                detail=f"Latest product workflow verification is {age_hours:.0f} hours old.",
                domain="workflow",
                action_kind="run_product_testing",
                href=f"/{checklist_path}",
                last_verified_at=verified_at,
                metadata=base_metadata,
            ),
            action,
        )

    if status == "partial":
        return (
            _release_readiness_check(
                id="workflow_verification",
                title="Critical workflow verification",
                status="warning",
                detail="Latest product workflow verification was partial.",
                domain="workflow",
                action_kind="run_product_testing",
                href=f"/{checklist_path}",
                last_verified_at=verified_at,
                metadata=base_metadata,
            ),
            action,
        )

    return (
        _release_readiness_check(
            id="workflow_verification",
            title="Critical workflow verification",
            status="ready",
            detail=f"Latest product workflow verification passed with {passed_count} checked item(s).",
            domain="workflow",
            href=f"/{checklist_path}",
            last_verified_at=verified_at,
            metadata=base_metadata,
        ),
        None,
    )


def build_release_readiness_response(
    now: datetime | None = None,
    services: Any | None = None,
) -> ReleaseReadinessResponse:
    generated_at = now or utc_now()
    resolved_services = workspace_services_or_legacy(services) if services is not None else None
    durable_service = (
        durable_storage_service_for_workspace(resolved_services)
        if resolved_services is not None
        else durable_storage_service
    )
    backup_service = (
        backup_restore_service_for_workspace(resolved_services)
        if resolved_services is not None
        else backup_restore_service
    )
    protection_service = (
        data_protection_service_for_workspace(resolved_services)
        if resolved_services is not None
        else data_protection_service
    )
    checks: list[ReleaseReadinessCheck] = []
    actions: list[ReleaseReadinessRecommendedAction] = []

    try:
        durable = durable_service.get_status()
        if durable.get("database_exists"):
            checks.append(_release_readiness_check(
                id="durable_store",
                title="Durable store ready",
                status="ready",
                detail=f"Durable store is reachable with {_coerce_int(durable.get('document_count'), 0)} documents.",
                domain="storage",
                last_verified_at=_parse_optional_datetime(durable.get("latest_migration_at")),
                metadata={"document_count": _coerce_int(durable.get("document_count"), 0)},
            ))
        else:
            checks.append(_release_readiness_check(
                id="durable_store",
                title="Durable store ready",
                status="blocked",
                detail="Durable storage database has not been created or is unavailable.",
                domain="storage",
                href="#atelier",
            ))
    except Exception as exc:
        checks.append(_release_readiness_check(
            id="durable_store",
            title="Durable store ready",
            status="blocked",
            detail=f"Durable storage status unavailable: {exc}",
            domain="storage",
            href="#atelier",
        ))

    try:
        backup_check, backup_action = _backup_readiness_check(
            backup_service.list_backups(),
            now=generated_at,
        )
        checks.append(backup_check)
        if backup_action is not None:
            actions.append(backup_action)
    except Exception as exc:
        checks.append(_release_readiness_check(
            id="backup",
            title="Backup available",
            status="blocked",
            detail=f"Backup status unavailable: {exc}",
            domain="storage",
            action_kind="create_backup",
        ))
        actions.append(_release_readiness_action("create_backup", "Create backup", "Backup status could not be verified."))

    try:
        protection = protection_service.get_status()
        supported = bool(protection.get("supported", True)) if isinstance(protection, dict) else False
        issue_count = (
            _coerce_int(protection.get("total_non_compliant_files"), 0)
            + _coerce_int(protection.get("total_non_compliant_directories"), 0)
            if isinstance(protection, dict)
            else 0
        )
        if not supported:
            checks.append(_release_readiness_check(
                id="protection",
                title="Protection compliant",
                status="blocked",
                detail="Local protection checks are not supported on this system.",
                domain="protection",
                action_kind="review_protection",
            ))
        elif issue_count > 0:
            checks.append(_release_readiness_check(
                id="protection",
                title="Protection compliant",
                status="warning",
                detail=f"{issue_count} protection item(s) need attention.",
                domain="protection",
                action_kind="apply_protection",
                metadata={"issue_count": issue_count},
            ))
            actions.append(_release_readiness_action(
                "apply_protection",
                "Apply protection",
                "Apply local protection policy to reduce filesystem exposure.",
            ))
        else:
            checks.append(_release_readiness_check(
                id="protection",
                title="Protection compliant",
                status="ready",
                detail="Protection policy is compliant.",
                domain="protection",
                metadata={"issue_count": 0},
            ))
    except Exception as exc:
        checks.append(_release_readiness_check(
            id="protection",
            title="Protection compliant",
            status="blocked",
            detail=f"Protection status unavailable: {exc}",
            domain="protection",
            action_kind="apply_protection",
        ))
        actions.append(_release_readiness_action("apply_protection", "Apply protection", "Protection status could not be verified."))

    try:
        policy = _git_policy(resolved_services) if resolved_services is not None else _git_policy()
        git_repository = (
            _git_repository_service(policy, services=resolved_services)
            if resolved_services is not None
            else _git_repository_service(policy)
        )
        git_status = git_repository.status()
        changed_files = git_status.get("changed_files") if isinstance(git_status, dict) else []
        changed_count = len(changed_files) if isinstance(changed_files, list) else 0
        last_commit = git_status.get("last_commit") if isinstance(git_status, dict) else {}
        last_commit_date = _parse_optional_datetime(last_commit.get("date")) if isinstance(last_commit, dict) else None
        if str(git_status.get("status") or "") == "no_repo":
            checks.append(_release_readiness_check(
                id="checkpoint",
                title="Checkpoint clean",
                status="warning",
                detail="Versioned workspace has not been initialized.",
                domain="checkpoint",
                action_kind="create_checkpoint",
            ))
            actions.append(_release_readiness_action("create_checkpoint", "Create checkpoint", "Initialize/checkpoint the versioned workspace."))
        elif changed_count > 0:
            checks.append(_release_readiness_check(
                id="checkpoint",
                title="Checkpoint clean",
                status="warning",
                detail=f"{changed_count} uncheckpointed file(s) should be reviewed.",
                domain="checkpoint",
                action_kind="create_checkpoint",
                last_verified_at=last_commit_date,
                metadata={"changed_files": changed_count},
            ))
            actions.append(_release_readiness_action(
                "create_checkpoint",
                "Create checkpoint",
                "Create a checkpoint after reviewing current file changes.",
            ))
        else:
            checks.append(_release_readiness_check(
                id="checkpoint",
                title="Checkpoint clean",
                status="ready",
                detail="Versioned workspace has no uncheckpointed file changes.",
                domain="checkpoint",
                last_verified_at=last_commit_date,
                metadata={"changed_files": 0},
            ))
    except Exception as exc:
        checks.append(_release_readiness_check(
            id="checkpoint",
            title="Checkpoint clean",
            status="warning",
            detail=f"Checkpoint status unavailable: {exc}",
            domain="checkpoint",
            action_kind="create_checkpoint",
        ))
        actions.append(_release_readiness_action("create_checkpoint", "Create checkpoint", "Checkpoint status could not be verified."))

    activity_events: list[dict[str, Any]] = []
    try:
        activity_store = (
            _git_activity_store(resolved_services)
            if resolved_services is not None
            else _git_activity_store()
        )
        activity = activity_store.query(limit=50)
        activity_events = activity.get("events") if isinstance(activity.get("events"), list) else []
        summary = activity.get("summary") if isinstance(activity, dict) else {}
        total_matched = _coerce_int(summary.get("total_matched"), 0) if isinstance(summary, dict) else len(activity_events)
        if total_matched > 0:
            checks.append(_release_readiness_check(
                id="audit_feed",
                title="Audit feed present",
                status="ready",
                detail=f"{total_matched} recent audit event(s) are available.",
                domain="audit",
                metadata={"event_count": total_matched},
            ))
        else:
            checks.append(_release_readiness_check(
                id="audit_feed",
                title="Audit feed present",
                status="warning",
                detail="No recent audit events are available.",
                domain="audit",
                href="#atelier?section=trust",
            ))
    except Exception as exc:
        checks.append(_release_readiness_check(
            id="audit_feed",
            title="Audit feed present",
            status="warning",
            detail=f"Audit feed unavailable: {exc}",
            domain="audit",
            href="#atelier?section=trust",
        ))

    restore_preview = _latest_activity_event(activity_events, "restore_preview")
    restore_preview_at = _parse_optional_datetime(restore_preview.get("created_at")) if restore_preview else None
    restore_age_hours = ((generated_at - restore_preview_at).total_seconds() / 3600) if restore_preview_at else None
    if restore_preview_at and restore_age_hours is not None and restore_age_hours <= RELEASE_READINESS_RESTORE_PREVIEW_MAX_AGE_HOURS:
        checks.append(_release_readiness_check(
            id="restore_preview",
            title="Restore preview verified",
            status="ready",
            detail="A recent read-only restore preview is recorded.",
            domain="storage",
            last_verified_at=restore_preview_at,
            metadata={"age_hours": round(restore_age_hours, 2)},
        ))
    else:
        checks.append(_release_readiness_check(
            id="restore_preview",
            title="Restore preview verified",
            status="warning",
            detail="Run a read-only restore preview when you need recovery confidence.",
            domain="storage",
            action_kind="preview_restore",
            last_verified_at=restore_preview_at,
            metadata={"age_hours": round(restore_age_hours, 2) if restore_age_hours is not None else None},
        ))
        actions.append(_release_readiness_action(
            "preview_restore",
            "Preview restore",
            "Generate a read-only restore preview. No files are changed.",
        ))

    try:
        service_status = _service_status_snapshot_sync()
        degraded = [
            service for service in service_status.services
            if service.enabled and (not service.reachable or service.degraded_count > 0)
        ]
        if degraded:
            names = ", ".join(service.name for service in degraded[:3])
            checks.append(_release_readiness_check(
                id="providers",
                title="Provider and service readiness",
                status="blocked",
                detail=f"Provider or service issues are present: {names}.",
                domain="provider",
                action_kind="review_provider_status",
                last_verified_at=service_status.as_of,
                metadata={"degraded_services": [service.model_dump(mode="json") for service in degraded]},
            ))
            actions.append(_release_readiness_action(
                "review_provider_status",
                "Review provider and service readiness",
                "Provider or service issues should caveat advice before product testing.",
                href="#today",
            ))
        else:
            checks.append(_release_readiness_check(
                id="providers",
                title="Provider and service readiness",
                status="ready",
                detail="No enabled provider or service issues are currently recorded.",
                domain="provider",
                last_verified_at=service_status.as_of,
                metadata={"service_count": len(service_status.services)},
            ))
    except Exception as exc:
        checks.append(_release_readiness_check(
            id="providers",
            title="Provider and service readiness",
            status="warning",
            detail=f"Provider and service readiness unavailable: {exc}",
            domain="provider",
            action_kind="review_provider_status",
            href="#today",
        ))

    if _hosted_identity_relevant_for_release():
        try:
            hosted_identity_check, hosted_identity_action = _hosted_identity_release_readiness_check()
            checks.append(hosted_identity_check)
            if hosted_identity_action is not None:
                actions.append(hosted_identity_action)
        except Exception as exc:
            checks.append(_release_readiness_check(
                id="hosted_identity",
                title="Hosted identity provider",
                status="blocked",
                detail=f"Hosted identity readiness unavailable: {exc}",
                domain="provider",
                action_kind="review_hosted_identity",
                href="#settings",
            ))
            actions.append(_release_readiness_action(
                "review_hosted_identity",
                "Review hosted sign-in",
                "Hosted identity readiness could not be verified.",
                href="#settings",
            ))

    try:
        activity_store = (
            _git_activity_store(resolved_services)
            if resolved_services is not None
            else _git_activity_store()
        )
        workflow_activity = activity_store.query(
            limit=1,
            event_type="product_workflow_verification",
        )
        workflow_events = (
            workflow_activity.get("events")
            if isinstance(workflow_activity.get("events"), list)
            else []
        )
    except Exception:
        workflow_events = activity_events
    workflow_check, workflow_action = _workflow_verification_readiness_check(
        workflow_events,
        now=generated_at,
    )
    checks.append(workflow_check)
    if workflow_action is not None:
        actions.append(workflow_action)

    ready_count = sum(1 for check in checks if check.status == "ready")
    blocked = [check for check in checks if check.status == "blocked"]
    warning = [check for check in checks if check.status == "warning"]
    status = "blocked" if blocked else "warning" if warning else "ready"
    summary = (
        "Release readiness is blocked by trust or provider gaps."
        if blocked else
        "Release readiness has warnings to review before relying on the app today."
        if warning else
        "Release readiness checks are passing."
    )

    return ReleaseReadinessResponse(
        status=status,  # type: ignore[arg-type]
        ready_count=ready_count,
        total_count=len(checks),
        generated_at=generated_at,
        summary=summary,
        checks=checks,
        blocking_gaps=[check.detail for check in blocked],
        warnings=[check.detail for check in warning],
        recommended_actions=actions,
    )


def _build_trust_durability_snapshot() -> dict[str, Any]:
    errors: list[str] = []
    backup_count = 0
    protection_issue_count = 0
    protection_supported = True
    git_changed_files = 0
    audit_event_count = 0
    critical = False

    try:
        backups_payload = backup_restore_service.list_backups()
        backups = backups_payload.get("backups") if isinstance(backups_payload, dict) else []
        backup_count = len(backups) if isinstance(backups, list) else 0
        if backup_count == 0:
            critical = True
    except Exception as exc:
        critical = True
        errors.append(f"Backup status unavailable: {exc}")

    try:
        protection = data_protection_service.get_status()
        protection_supported = bool(protection.get("supported", True)) if isinstance(protection, dict) else False
        protection_issue_count = (
            _coerce_int(protection.get("total_non_compliant_files"), 0)
            + _coerce_int(protection.get("total_non_compliant_directories"), 0)
            if isinstance(protection, dict)
            else 0
        )
        if not protection_supported:
            critical = True
    except Exception as exc:
        critical = True
        errors.append(f"Protection status unavailable: {exc}")

    try:
        policy = _git_policy()
        git_status = _git_repository_service(policy).status()
        changed_files = git_status.get("changed_files") if isinstance(git_status, dict) else []
        git_changed_files = len(changed_files) if isinstance(changed_files, list) else 0
    except Exception as exc:
        errors.append(f"Git checkpoint status unavailable: {exc}")

    try:
        activity = _git_activity_store().query(limit=1)
        summary = activity.get("summary") if isinstance(activity, dict) else {}
        audit_event_count = _coerce_int(summary.get("total_matched"), 0) if isinstance(summary, dict) else 0
    except Exception as exc:
        errors.append(f"Audit status unavailable: {exc}")

    issue_count = 0
    if backup_count == 0:
        issue_count += 1
    if protection_issue_count > 0 or not protection_supported:
        issue_count += 1
    if git_changed_files > 0:
        issue_count += 1
    if errors:
        issue_count += 1

    return {
        "backup_count": backup_count,
        "protection_issue_count": protection_issue_count,
        "protection_supported": protection_supported,
        "git_changed_files": git_changed_files,
        "audit_event_count": audit_event_count,
        "issue_count": issue_count,
        "critical": critical,
        "error": " ".join(errors[:2]),
    }


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural or f"{singular}s"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _parse_optional_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _build_investment_policy_command_card(dashboard: TodayDashboardResponse) -> TodayCommandCard | None:
    readiness = dashboard.profile_readiness
    if readiness is None:
        return None
    policy_section = next(
        (section for section in readiness.sections if section.key == "investment_policy"),
        None,
    )
    if policy_section is None or policy_section.status == "complete":
        return None

    raw_detail = str(policy_section.detail or "").strip()
    detail = raw_detail or "Set personal investment guardrails before relying on stronger fit advice."
    if "investment-fit confidence" not in detail.lower():
        detail = f"{detail} Defining these guardrails improves investment-fit confidence."

    return TodayCommandCard(
        id="investment-policy",
        title="Investment policy",
        status="warning",
        detail=detail,
        metric_label="Guardrails",
        metric_value="Missing" if policy_section.status == "attention" else "Weak",
        action_label="Define policy",
        href="#copilot?intent=investment-policy",
    )


def _build_today_closure_analytics_payload(
    inbox: RecommendationInbox | None = None,
) -> dict[str, Any] | None:
    try:
        return build_recommendation_closure_analytics_payload(
            limit=500,
            statuses=["applied", "rejected"],
            include_pending_realized=True,
            inbox=inbox,
        )
    except Exception:
        return None


def _build_investment_calibration_command_card(payload: dict[str, Any] | None = None) -> TodayCommandCard | None:
    if payload is None:
        payload = _build_today_closure_analytics_payload()
    if not isinstance(payload, dict):
        return None
    summary = payload.get("process_calibration_summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        return None
    count = _coerce_int(summary.get("count"), 0)
    if count <= 0:
        return None
    useful = _coerce_int(summary.get("useful_count"), 0)
    weak = _coerce_int(summary.get("weak_count"), 0)
    useful_rate = _coerce_optional_float(summary.get("useful_rate_pct"))
    useful_rate_label = f"{int(round(useful_rate))}%" if useful_rate is not None else "n/a"
    status = "warning" if weak > useful or (useful_rate is not None and useful_rate < 50.0) else "ready"
    detail = f"{count} investment/research outcomes calibrated: {useful} useful"
    if weak:
        detail = f"{detail}, {weak} weak"
    detail = f"{detail}."
    return TodayCommandCard(
        id="investment-calibration",
        title="Investment calibration",
        status=status,
        detail=detail,
        metric_label="Useful",
        metric_value=useful_rate_label,
        action_label="Review quality",
        href="#inbox",
    )


def _build_thesis_outcome_command_card(rows: list[dict[str, Any]]) -> TodayCommandCard | None:
    if not rows:
        return None
    first = rows[0]
    first_id = str(first.get("id") or "").strip()
    revision = _extract_recommendation_thesis_revision(first)
    target = _thesis_revision_target_label(revision)
    count = len(rows)
    detail = f"{count} thesis revision outcome(s) need calibration."
    if target:
        detail = f"{detail} Start with {target}."
    return TodayCommandCard(
        id="thesis-outcome-loop",
        title="Thesis outcome",
        status="warning",
        detail=detail,
        metric_label="Pending",
        metric_value=str(count),
        action_label="Log thesis outcome",
        href=f"#inbox?focus={first_id}" if first_id else "#inbox",
    )


def _build_thesis_calibration_command_card(payload: dict[str, Any] | None = None) -> TodayCommandCard | None:
    if payload is None:
        payload = _build_today_closure_analytics_payload()
    if not isinstance(payload, dict):
        return None
    summary = payload.get("process_calibration_summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        return None
    count = _coerce_int(summary.get("thesis_revision_count"), 0)
    if count <= 0:
        return None
    useful = _coerce_int(summary.get("useful_thesis_revision_count"), 0)
    status = "warning" if useful <= 0 else "ready"
    return TodayCommandCard(
        id="thesis-calibration",
        title="Thesis calibration",
        status=status,
        detail=f"{count} thesis revision outcome(s) calibrated: {useful} useful.",
        metric_label="Useful",
        metric_value=f"{useful}/{count}",
        action_label="Review learning",
        href="#inbox",
    )


def _build_copilot_drafts_command_card(
    rows: list[dict[str, Any]],
    first_recommendation_id: str,
) -> TodayCommandCard:
    if not rows:
        return TodayCommandCard(
            id="copilot-drafts",
            title="Copilot prepared reviews",
            status="ready",
            detail="No Copilot-drafted reviews are waiting.",
            metric_label="Drafts",
            metric_value="0",
            action_label="Open Copilot",
            href="#copilot",
        )

    first = rows[0]
    action_payload = first.get("action_payload") if isinstance(first.get("action_payload"), dict) else {}
    evidence = action_payload.get("evidence") if isinstance(action_payload.get("evidence"), dict) else {}
    quality = action_payload.get("quality") if isinstance(action_payload.get("quality"), dict) else {}
    symbol = str(evidence.get("symbol") or "").strip().upper()
    freshness = _quality_text(quality.get("freshness_status") or evidence.get("freshness_status"))
    actionability = _quality_text(quality.get("actionability"))
    focus = " · ".join(
        [
            symbol,
            f"{freshness} evidence" if freshness else "",
            actionability.replace("_", "-") if actionability else "",
        ]
    ).strip(" ·")
    noun = "review is" if len(rows) == 1 else "reviews are"
    detail = f"{len(rows)} Copilot-drafted {noun} waiting"
    if focus:
        detail = f"{detail}: {focus}."
    else:
        detail = f"{detail}."

    return TodayCommandCard(
        id="copilot-drafts",
        title="Copilot prepared reviews",
        status="warning",
        detail=detail,
        metric_label="Drafts",
        metric_value=str(len(rows)),
        action_label="Review draft" if len(rows) == 1 else "Review drafts",
        href=f"#inbox?focus={first_recommendation_id}" if first_recommendation_id else "#inbox",
    )


TODAY_RESEARCH_EVIDENCE_CACHE_TTL_SECONDS = 15 * 60


def _research_evidence_cache_key(symbol: str, period: str = "6mo", interval: str = "1d") -> str:
    normalized_symbol = re.sub(r"[^A-Z0-9._-]+", "", str(symbol or "").strip().upper())
    return f"today-research-evidence:{normalized_symbol}:{period}:{interval}"


def _cached_research_evidence_packet(
    *,
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
    force_refresh: bool = False,
) -> tuple[ResearchEvidencePacket, datetime, bool]:
    cache_key = _research_evidence_cache_key(symbol, period=period, interval=interval)
    if not force_refresh:
        hit, cached_payload = today_research_evidence_cache.lookup(cache_key)
        if hit and isinstance(cached_payload, dict):
            packet_payload = cached_payload.get("packet")
            cached_at = _parse_utc_datetime(cached_payload.get("cached_at"))
            if isinstance(packet_payload, dict) and cached_at is not None:
                return ResearchEvidencePacket(**packet_payload), cached_at, True

    packet = research_service.evidence_packet(symbol=symbol, period=period, interval=interval)
    cached_at = utc_now()
    today_research_evidence_cache.set(
        cache_key,
        {
            "cached_at": cached_at.isoformat(),
            "packet": packet.model_dump(mode="json"),
        },
        ttl_seconds=TODAY_RESEARCH_EVIDENCE_CACHE_TTL_SECONDS,
    )
    return packet, cached_at, False


def _format_research_cache_age(cached_at_values: list[datetime]) -> str:
    if not cached_at_values:
        return "unknown"
    oldest_cached_at = min(cached_at_values)
    age_minutes = max(0, int((utc_now() - oldest_cached_at).total_seconds() // 60))
    if age_minutes < 1:
        return "<1m"
    if age_minutes < 60:
        return f"{age_minutes}m"
    age_hours = age_minutes // 60
    return f"{age_hours}h"


TODAY_THESIS_REVIEW_DAYS = 30
TODAY_MATERIAL_PRICE_MOVE_PCT = 15.0
THESIS_REVISION_HISTORY_LIMIT = 8
THESIS_REVISION_TEXT_LIMIT = 280
THESIS_REVISION_LIST_LIMIT = 5


def _research_readiness_symbol_label(symbols: list[str]) -> str:
    label = ", ".join(symbols[:3])
    if len(symbols) > 3:
        label = f"{label} +{len(symbols) - 3} more"
    return label


def _research_readiness_clean_symbol(raw_symbol: Any) -> str:
    return re.sub(r"[^A-Z0-9._-]+", "", str(raw_symbol or "").strip().upper())


def _watchlist_thesis_today_signal(
    item: dict[str, Any],
    *,
    current_price: float | None,
) -> dict[str, Any] | None:
    symbol = _research_readiness_clean_symbol(item.get("symbol"))
    if not symbol:
        return None
    if not str(item.get("thesis") or item.get("note") or "").strip():
        return None

    reference_price = _coerce_optional_float(
        item.get("thesis_reference_price_usd")
        or item.get("reference_price_usd")
        or item.get("price_at_review_usd")
    )
    if reference_price is not None and current_price is not None and reference_price > 0:
        change_pct = ((current_price - reference_price) / reference_price) * 100.0
        if abs(change_pct) >= TODAY_MATERIAL_PRICE_MOVE_PCT:
            return {
                "symbol": symbol,
                "reason": "material_price_change",
                "change_pct": round(change_pct, 2),
            }

    review = research_thesis_review_metadata(
        {
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "reviewed_at": item.get("thesis_reviewed_at") or item.get("reviewed_at"),
            "expires_at": item.get("thesis_expires_at") or item.get("expires_at"),
        },
        stale_after_days=TODAY_THESIS_REVIEW_DAYS,
    )
    if review.get("status") == "expired":
        return {
            "symbol": symbol,
            "reason": "watchlist_thesis_expired",
            "age_days": review.get("age_days"),
        }
    return None


def _saved_dossier_thesis_today_signals(symbols: list[str]) -> list[dict[str, Any]]:
    symbol_set = {symbol for symbol in symbols if symbol}
    try:
        lookup = build_research_dossier_lookup_payload(limit=10, include_content=False)
    except Exception:
        return []
    lookup_plan_id = str(lookup.get("plan_id") or "").strip()
    items = lookup.get("items") if isinstance(lookup.get("items"), list) else []
    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        review = item.get("thesis_review") if isinstance(item.get("thesis_review"), dict) else {}
        if review.get("status") != "expired":
            continue
        item_symbols = [
            str(symbol or "").strip().upper()
            for symbol in item.get("symbols", [])
            if str(symbol or "").strip()
        ] if isinstance(item.get("symbols"), list) else []
        if symbol_set and item_symbols and not symbol_set.intersection(item_symbols):
            continue
        label_symbol = next((symbol for symbol in item_symbols if symbol in symbol_set), None)
        label_symbol = label_symbol or (item_symbols[0] if item_symbols else str(item.get("title") or "Dossier"))
        artifact_id = str(item.get("artifact_id") or "").strip()
        key = artifact_id or label_symbol
        if key in seen:
            continue
        seen.add(key)
        signals.append(
            {
                "symbol": label_symbol,
                "reason": "saved_dossier_thesis_expired",
                "artifact_id": artifact_id,
                "plan_id": str(item.get("plan_id") or lookup_plan_id).strip(),
                "age_days": review.get("age_days"),
            }
        )
    return signals


def _proposed_thesis_review_today_signals() -> list[dict[str, Any]]:
    try:
        rows = recommendation_inbox.list(limit=200, status="proposed", sort="created_at_desc")
    except Exception:
        return []

    signals: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        action_payload = row.get("action_payload") if isinstance(row.get("action_payload"), dict) else {}
        suggested_action = (
            action_payload.get("suggested_action")
            if isinstance(action_payload.get("suggested_action"), dict)
            else {}
        )
        if str(suggested_action.get("kind") or "").strip() != "review_research_thesis":
            continue
        generator = action_payload.get("generator") if isinstance(action_payload.get("generator"), dict) else {}
        signal_key = str(generator.get("signal_key") or "").strip()
        reason = str(suggested_action.get("reason") or "").strip()
        if reason != "policy_material_change" and signal_key not in {
            "thesis_policy_material_change",
            "watchlist_thesis_policy_material_change",
        }:
            continue

        evidence = action_payload.get("evidence") if isinstance(action_payload.get("evidence"), dict) else {}
        artifact_id = str(
            suggested_action.get("artifact_id")
            or evidence.get("artifact_id")
            or ""
        ).strip()
        plan_id = str(
            suggested_action.get("plan_id")
            or evidence.get("plan_id")
            or row.get("plan_id")
            or ""
        ).strip()
        raw_symbols = suggested_action.get("symbols")
        if not isinstance(raw_symbols, list):
            raw_symbols = evidence.get("symbols") if isinstance(evidence.get("symbols"), list) else []
        symbols = [_research_readiness_clean_symbol(symbol) for symbol in raw_symbols]
        symbols = [symbol for symbol in symbols if symbol]
        symbol = symbols[0] if symbols else _research_readiness_clean_symbol(evidence.get("symbol"))
        dedupe_target = artifact_id or symbol or str(row.get("id") or "").strip()
        key = ("policy_material_change", dedupe_target)
        if not dedupe_target or key in seen:
            continue
        seen.add(key)
        signals.append(
            {
                "symbol": symbol or artifact_id,
                "reason": "policy_material_change",
                "artifact_id": artifact_id,
                "plan_id": plan_id,
                "recommendation_id": str(row.get("id") or "").strip(),
            }
        )
    return signals


def _merge_research_thesis_today_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for signal in signals:
        reason = str(signal.get("reason") or "").strip()
        target = str(signal.get("artifact_id") or signal.get("symbol") or "").strip()
        if not reason or not target:
            continue
        key = (reason, target)
        if key in seen:
            continue
        seen.add(key)
        merged.append(signal)
    return merged


def _research_thesis_today_href(signals: list[dict[str, Any]]) -> str:
    if len(signals) != 1:
        return "#research?dossiers=1"
    signal = signals[0]
    target = str(signal.get("artifact_id") or signal.get("symbol") or "").strip()
    if not target:
        return "#research?dossiers=1"
    href = f"#research?thesisReview={url_quote(target, safe='')}"
    plan_id = str(signal.get("plan_id") or "").strip()
    if plan_id and signal.get("artifact_id"):
        href = f"{href}&plan={url_quote(plan_id, safe='')}"
    return href


def _build_research_readiness_command_card(dashboard: TodayDashboardResponse) -> TodayCommandCard:
    symbols: list[str] = []
    seen: set[str] = set()
    watchlist_items: list[dict[str, Any]] = []
    proposed_thesis_signals = _proposed_thesis_review_today_signals()

    def add_symbol(raw_symbol: Any) -> None:
        symbol = _research_readiness_clean_symbol(raw_symbol)
        if not symbol or symbol in seen or len(symbols) >= 4:
            return
        seen.add(symbol)
        symbols.append(symbol)

    add_symbol(dashboard.top_holding_symbol)
    try:
        watchlist_items = [
            item for item in portfolio_store.list_watchlist()
            if isinstance(item, dict)
        ]
        for item in watchlist_items:
            if not isinstance(item, dict):
                continue
            add_symbol(item.get("symbol"))
            if len(symbols) >= 4:
                break
    except Exception:
        pass

    for signal in proposed_thesis_signals:
        add_symbol(signal.get("symbol"))

    if not symbols:
        return TodayCommandCard(
            id="research-readiness",
            title="Research readiness",
            status="warning",
            detail="Add portfolio holdings or watchlist symbols before investment research can be checked.",
            metric_label="Ready",
            metric_value="0/0",
            action_label="Open portfolio",
            href="#portfolio",
        )

    ready_symbols: list[str] = []
    weak_symbols: list[str] = []
    degraded_symbols: list[str] = []
    provider_failures: list[str] = []
    cached_at_values: list[datetime] = []
    packet_prices_by_symbol: dict[str, float] = {}
    for symbol in symbols:
        try:
            packet, cached_at, _cache_hit = _cached_research_evidence_packet(
                symbol=symbol,
                period="6mo",
                interval="1d",
            )
            cached_at_values.append(cached_at)
        except Exception:
            provider_failures.append(symbol)
            continue

        metrics = packet.metrics if isinstance(packet.metrics, dict) else {}
        price = _coerce_optional_float(metrics.get("last_price"))
        if price is not None:
            packet_prices_by_symbol[symbol] = price
        freshness = packet.freshness if isinstance(packet.freshness, dict) else {}
        quality = packet.quality if isinstance(packet.quality, dict) else {}
        status = str(freshness.get("status") or "").strip().lower()
        blocking_gaps = quality.get("blocking_gaps")
        has_blocking_gaps = isinstance(blocking_gaps, list) and bool(blocking_gaps)
        coverage = packet.coverage if isinstance(packet.coverage, dict) else {}
        quote_available = bool(coverage.get("quote_available"))
        history_available = bool(coverage.get("history_available"))
        if status == "degraded" or (not quote_available and not history_available):
            degraded_symbols.append(symbol)
            continue
        if status == "fresh" and not has_blocking_gaps:
            ready_symbols.append(symbol)
        else:
            weak_symbols.append(symbol)

    ready_count = len(ready_symbols)
    total_count = len(symbols)
    cache_age = _format_research_cache_age(cached_at_values)
    thesis_signals = _saved_dossier_thesis_today_signals(symbols)
    watchlist_thesis_signals: list[dict[str, Any]] = []
    for item in watchlist_items:
        symbol = _research_readiness_clean_symbol(item.get("symbol"))
        signal = _watchlist_thesis_today_signal(
            item,
            current_price=packet_prices_by_symbol.get(symbol),
        )
        if signal is not None:
            watchlist_thesis_signals.append(signal)
    thesis_signals.extend(watchlist_thesis_signals)
    thesis_signals.extend(proposed_thesis_signals)
    thesis_signals = _merge_research_thesis_today_signals(thesis_signals)
    if degraded_symbols:
        degraded_label = ", ".join(degraded_symbols[:3])
        extra = "" if len(degraded_symbols) <= 3 else f" +{len(degraded_symbols) - 3} more"
        return TodayCommandCard(
            id="research-readiness",
            title="Research readiness",
            status="critical",
            detail=(
                f"{len(degraded_symbols)} research symbol(s) have degraded provider/data coverage: "
                f"{degraded_label}{extra}."
            ),
            metric_label="Ready",
            metric_value=f"{ready_count}/{total_count}",
            action_label="Refresh research",
            href="#today?refresh=research",
        )

    if provider_failures:
        degraded_label = ", ".join(provider_failures[:3])
        extra = "" if len(provider_failures) <= 3 else f" +{len(provider_failures) - 3} more"
        return TodayCommandCard(
            id="research-readiness",
            title="Research readiness",
            status="critical",
            detail=(
                f"{len(provider_failures)} research symbol(s) hit provider/data failure: "
                f"{degraded_label}{extra}."
            ),
            metric_label="Ready",
            metric_value=f"{ready_count}/{total_count}",
            action_label="Refresh research",
            href="#today?refresh=research",
        )

    if weak_symbols:
        weak_label = ", ".join(weak_symbols[:3])
        extra = "" if len(weak_symbols) <= 3 else f" +{len(weak_symbols) - 3} more"
        noun = "symbol has" if len(weak_symbols) == 1 else "symbols have"
        return TodayCommandCard(
            id="research-readiness",
            title="Research readiness",
            status="warning",
            detail=(
                f"{len(weak_symbols)} research {noun} partial or degraded evidence: "
                f"{weak_label}{extra}."
            ),
            metric_label="Ready",
            metric_value=f"{ready_count}/{total_count}",
            action_label="Refresh research",
            href="#today?refresh=research",
        )

    if thesis_signals:
        policy_symbols = [
            str(signal.get("symbol") or "").strip().upper()
            for signal in thesis_signals
            if signal.get("reason") == "policy_material_change" and str(signal.get("symbol") or "").strip()
        ]
        material_symbols = [
            str(signal.get("symbol") or "").strip().upper()
            for signal in thesis_signals
            if signal.get("reason") == "material_price_change" and str(signal.get("symbol") or "").strip()
        ]
        due_symbols = [
            str(signal.get("symbol") or "").strip().upper()
            for signal in thesis_signals
            if signal.get("reason") not in {"material_price_change", "policy_material_change"}
            and str(signal.get("symbol") or "").strip()
        ]
        if policy_symbols:
            noun = "thesis has" if len(policy_symbols) == 1 else "theses have"
            detail = (
                f"{len(policy_symbols)} saved research {noun} policy context changed: "
                f"{_research_readiness_symbol_label(policy_symbols)}."
            )
        elif material_symbols:
            noun = "thesis has" if len(material_symbols) == 1 else "theses have"
            detail = (
                f"{len(material_symbols)} watchlist {noun} a material price move: "
                f"{_research_readiness_symbol_label(material_symbols)}."
            )
        else:
            noun = "review is" if len(due_symbols) == 1 else "reviews are"
            detail = (
                f"{len(due_symbols)} saved research thesis {noun} due: "
                f"{_research_readiness_symbol_label(due_symbols)}."
            )
        return TodayCommandCard(
            id="research-readiness",
            title="Research readiness",
            status="warning",
            detail=detail,
            metric_label="Ready",
            metric_value=f"{ready_count}/{total_count}",
            action_label="Review theses",
            href=_research_thesis_today_href(thesis_signals),
        )

    return TodayCommandCard(
        id="research-readiness",
        title="Research readiness",
        status="ready",
        detail=(
            f"Research evidence is fresh for {ready_count} tracked symbol(s). "
            f"Cached research age: {cache_age}."
        ),
        metric_label="Ready",
        metric_value=f"{ready_count}/{total_count}",
        action_label="Refresh research",
        href="#today?refresh=research",
    )


def _build_cash_runway_command_card(dashboard: TodayDashboardResponse) -> TodayCommandCard:
    months = dashboard.emergency_fund_months
    if months is None:
        return TodayCommandCard(
            id="cash-runway",
            title="Cash runway",
            status="warning",
            detail="Add expenses and cash context to estimate emergency-fund runway.",
            metric_label="Runway",
            metric_value="Unknown",
            action_label="Complete context",
            href="#copilot?intent=complete-context",
        )

    status: Literal["ready", "warning", "critical"] = "ready"
    detail = "Emergency-fund runway is at or above the 6-month target."
    if months < 3:
        status = "warning"
        detail = "Emergency-fund runway is below the 3-month minimum target."
    elif months < 6:
        status = "warning"
        detail = "Emergency-fund runway is between the 3-month floor and 6-month target."

    return TodayCommandCard(
        id="cash-runway",
        title="Cash runway",
        status=status,
        detail=detail,
        metric_label="Runway",
        metric_value=f"{months:.1f} mo",
        action_label="Review liquidity",
        href="#inbox",
    )


def _recommendation_needs_outcome(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status not in {"applied", "rejected"}:
        return False
    action_payload = row.get("action_payload")
    if not isinstance(action_payload, dict):
        return False
    closure = action_payload.get("decision_closure")
    if not isinstance(closure, dict):
        return False
    if _recommendation_needs_process_outcome(row):
        return True
    realized = closure.get("realized_outcome")
    if isinstance(realized, dict) and realized:
        return False
    expected_vs_realized = closure.get("expected_vs_realized")
    if isinstance(expected_vs_realized, dict):
        return str(expected_vs_realized.get("status") or "").strip().lower() == "pending_realized"
    return True


def _recommendation_pre_mortem(row: dict[str, Any]) -> dict[str, Any]:
    action_payload = row.get("action_payload")
    if not isinstance(action_payload, dict):
        return {}
    closure = action_payload.get("decision_closure")
    if not isinstance(closure, dict):
        return {}
    pre_mortem = closure.get("pre_mortem")
    return pre_mortem if isinstance(pre_mortem, dict) else {}


def _extract_recommendation_thesis_revision(row: dict[str, Any]) -> dict[str, Any]:
    action_payload = row.get("action_payload")
    if not isinstance(action_payload, dict):
        return {}
    revision = action_payload.get("thesis_revision")
    if isinstance(revision, dict) and revision:
        return revision
    closure = action_payload.get("decision_closure")
    if not isinstance(closure, dict):
        return {}
    calibration = closure.get("decision_process_calibration")
    if not isinstance(calibration, dict):
        return {}
    revision = calibration.get("thesis_revision")
    return revision if isinstance(revision, dict) else {}


def _recommendation_has_thesis_revision(row: dict[str, Any]) -> bool:
    revision = _extract_recommendation_thesis_revision(row)
    return bool(
        str(revision.get("event_id") or "").strip()
        or str(revision.get("symbol") or "").strip()
        or str(revision.get("artifact_id") or "").strip()
    )


def _thesis_revision_target_label(revision: dict[str, Any]) -> str:
    symbol = str(revision.get("symbol") or "").strip().upper()
    if symbol:
        return symbol
    artifact_id = str(revision.get("artifact_id") or "").strip()
    if artifact_id:
        return "saved dossier"
    target_type = str(revision.get("target_type") or "").strip().replace("_", " ")
    return target_type


def _recommendation_needs_process_outcome(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status not in {"applied", "rejected"}:
        return False
    action_payload = row.get("action_payload")
    if not isinstance(action_payload, dict):
        return False
    if not _tracks_investment_process_calibration(row, action_payload):
        return False
    closure = action_payload.get("decision_closure")
    if not isinstance(closure, dict):
        return False
    calibration = closure.get("decision_process_calibration")
    if not isinstance(calibration, dict):
        return True
    return not str(calibration.get("process_outcome") or "").strip()


def _build_plan_detail_response(detail: dict[str, Any]) -> PlanDetailResponse:
    payload = dict(detail)
    plan_id = str(payload.get("id") or "").strip() or None
    payload["top_next_actions"] = _build_top_next_actions(plan_id=plan_id, limit=3)
    return PlanDetailResponse(**payload)


def _build_recommendation_open_counts(
    inbox: RecommendationInbox | None = None,
) -> tuple[int, int]:
    resolved_inbox = inbox or recommendation_inbox
    rows = resolved_inbox.list(limit=500, status="proposed")
    high = [
        row
        for row in rows
        if str(row.get("priority", "")).strip().lower() == "high"
    ]
    return len(rows), len(high)


RECOMMENDATION_CITATION_MODEL_VERSION = "citation_v1"


def _recommendation_source_requires_dossier_citations(source: str) -> bool:
    normalized = str(source or "").strip().lower()
    if normalized == "copilot:investment_fit":
        return False
    return normalized.startswith("copilot")


def _coerce_symbol_list_from_raw(raw_value: Any) -> list[str]:
    if isinstance(raw_value, list):
        return [str(item or "").strip() for item in raw_value]
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",")]
    return []


def _extract_symbols_from_research_dossier_title(title: Any) -> list[str]:
    text = str(title or "").strip()
    lowered = text.lower()
    if lowered.startswith("research dossier:"):
        symbol_segment = text.split(":", 1)[1]
    elif lowered.startswith("research dossier -"):
        symbol_segment = text.split("-", 1)[1]
    else:
        return []
    normalized_segment = (
        symbol_segment.replace(" vs ", ",")
        .replace(" VS ", ",")
        .replace(" Vs ", ",")
        .replace("|", ",")
        .replace("/", ",")
    )
    return normalize_research_symbols(
        [item.strip() for item in normalized_segment.split(",") if item.strip()],
        max_symbols=20,
    )


def _list_research_dossier_artifacts(
    *,
    plan_id: str,
    limit: int = 5,
    include_content: bool = False,
    workspace: PlanWorkspace | None = None,
) -> list[dict[str, Any]]:
    resolved_workspace = workspace or plan_workspace
    plan_detail = resolved_workspace.get_plan(plan_id)
    artifacts_raw = plan_detail.get("artifacts")
    artifacts = artifacts_raw if isinstance(artifacts_raw, list) else []
    rows: list[dict[str, Any]] = []
    max_rows = max(1, min(int(limit), 25))

    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("id") or "").strip()
        if not artifact_id:
            continue
        file_name = str(artifact.get("file_name") or "").strip()
        title = str(artifact.get("title") or "").strip()
        title_lower = title.lower()
        if "-research-dossier-" not in file_name and not title_lower.startswith("research dossier"):
            continue
        row: dict[str, Any] = {
            "artifact_id": artifact_id,
            "file_name": file_name or f"{artifact_id}.md",
            "title": title or artifact_id,
            "created_at": artifact.get("created_at"),
            "plan_id": plan_id,
            "symbols": _extract_symbols_from_research_dossier_title(title),
            "content_preview": "",
        }
        row["thesis_review"] = research_thesis_review_metadata(row)
        if include_content:
            with suppress(Exception):
                artifact_payload = resolved_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
                content = str(artifact_payload.get("content") or "")
                row["content_preview"] = content[:1600]
                row.update(_extract_thesis_review_metadata_from_markdown(content))
                if not row["symbols"]:
                    row["symbols"] = _extract_symbols_from_research_dossier_title(
                        artifact_payload.get("title")
                    )
                row["thesis_review"] = research_thesis_review_metadata({**row, **artifact_payload})
        rows.append(row)
        if len(rows) >= max_rows:
            break
    return rows


def build_research_dossier_lookup_payload(
    *,
    plan_id: str | None = None,
    limit: int = 5,
    include_content: bool = False,
    workspace: PlanWorkspace | None = None,
) -> dict[str, Any]:
    resolved_workspace = workspace or plan_workspace
    requested_plan_id = str(plan_id or "").strip() or None
    resolved_plan_id = requested_plan_id or resolved_workspace.get_active_plan_id()
    warnings: list[str] = []
    if not resolved_plan_id:
        warnings.append("No plan_id provided and no active plan is set.")
        return {
            "plan_id": None,
            "count": 0,
            "items": [],
            "warnings": warnings,
            "updated_at": context_utc_now_iso(),
        }

    items: list[dict[str, Any]]
    try:
        items = _list_research_dossier_artifacts(
            plan_id=resolved_plan_id,
            limit=limit,
            include_content=include_content,
            workspace=resolved_workspace,
        )
    except PlanNotFoundError as exc:
        warnings.append(str(exc))
        items = []

    return {
        "plan_id": resolved_plan_id,
        "count": len(items),
        "items": items,
        "warnings": normalize_context_warnings(warnings, max_warnings=20),
        "updated_at": context_utc_now_iso(),
    }


def _extract_thesis_review_metadata_from_markdown(markdown: Any) -> dict[str, Any]:
    text = str(markdown or "")
    if "## Thesis Review Metadata" not in text:
        return {}
    metadata: dict[str, Any] = {}
    reviewed_match = re.search(r"-\s*Reviewed at:\s*`?([^`\n]+)`?", text, flags=re.IGNORECASE)
    expires_match = re.search(r"-\s*Expires at:\s*`?([^`\n]+)`?", text, flags=re.IGNORECASE)
    price_match = re.search(r"-\s*Reference price USD:\s*`?([^`\n]+)`?", text, flags=re.IGNORECASE)
    if reviewed_match:
        metadata["reviewed_at"] = reviewed_match.group(1).strip()
    if expires_match:
        metadata["expires_at"] = expires_match.group(1).strip()
    if price_match:
        metadata["reference_price_usd"] = _coerce_optional_float(price_match.group(1).strip())
    return metadata


def _build_thesis_review_metadata_section(
    *,
    reviewed_at: str,
    expires_at: str,
    reference_price_usd: float | None,
) -> str:
    lines = [
        "## Thesis Review Metadata",
        "",
        f"- Reviewed at: `{reviewed_at}`",
        f"- Expires at: `{expires_at}`",
    ]
    if reference_price_usd is not None:
        lines.append(f"- Reference price USD: `{round(float(reference_price_usd), 4)}`")
    return "\n".join(lines).strip()


def _replace_thesis_review_metadata_section(
    markdown: str,
    *,
    reviewed_at: str,
    expires_at: str,
    reference_price_usd: float | None,
) -> str:
    section = _build_thesis_review_metadata_section(
        reviewed_at=reviewed_at,
        expires_at=expires_at,
        reference_price_usd=reference_price_usd,
    )
    pattern = r"\n*## Thesis Review Metadata\n(?:.|\n)*?(?=\n## |\Z)"
    if re.search(pattern, markdown):
        return re.sub(pattern, f"\n\n{section}\n", markdown).strip() + "\n"
    return markdown.rstrip() + "\n\n" + section + "\n"


def _extract_markdown_section(markdown: Any, heading: str) -> str:
    escaped_heading = re.escape(str(heading or "").strip())
    if not escaped_heading:
        return ""
    pattern = rf"(?ims)^##\s+{escaped_heading}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, str(markdown or ""))
    if not match:
        return ""
    return match.group("body").strip()


def _replace_markdown_section(markdown: str, heading: str, body: str) -> str:
    title = str(heading or "").strip()
    section = f"## {title}\n\n{str(body or '').strip()}\n"
    pattern = rf"(?ims)\n*^##\s+{re.escape(title)}\s*$\n.*?(?=^##\s+|\Z)"
    if re.search(pattern, markdown):
        return re.sub(pattern, f"\n\n{section}", markdown).strip() + "\n"
    return markdown.rstrip() + "\n\n" + section


def _replace_thesis_revision_notes_section(markdown: str, rationale: str) -> str:
    text = str(rationale or "").strip()
    if not text:
        return markdown
    lines = [
        "## Thesis Revision Notes",
        "",
        f"- Rationale: {text}",
    ]
    section = "\n".join(lines).strip()
    pattern = r"\n*## Thesis Revision Notes\n(?:.|\n)*?(?=\n## |\Z)"
    if re.search(pattern, markdown):
        return re.sub(pattern, f"\n\n{section}\n", markdown).strip() + "\n"
    return markdown.rstrip() + "\n\n" + section + "\n"


def _compact_revision_text(value: Any, *, limit: int = THESIS_REVISION_TEXT_LIMIT) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _compact_revision_hash(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _compact_revision_list(value: Any, *, limit: int = THESIS_REVISION_LIST_LIMIT) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _compact_revision_text(item, limit=160)
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _compact_thesis_revision_event(
    *,
    target_type: str,
    previous_thesis: Any,
    revised_thesis: Any,
    reviewed_at: str,
    expires_at: str,
    reference_price_usd: float | None,
    review_window_days: int,
    request: dict[str, Any],
    symbol: str | None = None,
    data_source: str | None = None,
    plan_id: str | None = None,
    artifact_id: str | None = None,
) -> dict[str, Any]:
    previous_text = str(previous_thesis or "")
    revised_text = str(revised_thesis or "")
    event: dict[str, Any] = {
        "event_id": f"thesis-revision:{target_type}:{_compact_revision_hash(f'{reviewed_at}|{symbol or artifact_id}|{revised_text}')}",
        "target_type": str(target_type or "").strip() or "unknown",
        "source": str(request.get("source") or "copilot_review").strip() or "copilot_review",
        "reviewed_at": reviewed_at,
        "expires_at": expires_at,
        "reference_price_usd": round(float(reference_price_usd), 4) if reference_price_usd is not None else None,
        "review_window_days": int(review_window_days),
        "previous_thesis_excerpt": _compact_revision_text(previous_text),
        "revised_thesis_excerpt": _compact_revision_text(revised_text),
        "previous_thesis_hash": _compact_revision_hash(previous_text),
        "revised_thesis_hash": _compact_revision_hash(revised_text),
        "previous_thesis_chars": len(previous_text),
        "revised_thesis_chars": len(revised_text),
        "rationale_excerpt": _compact_revision_text(request.get("rationale")),
        "evidence_gaps": _compact_revision_list(request.get("evidence_gaps")),
        "warnings": _compact_revision_list(request.get("warnings")),
        "recommendation_id": str(request.get("recommendation_id") or "").strip(),
        "conversation_id": str(request.get("conversation_id") or "").strip(),
    }
    if symbol:
        event["symbol"] = symbol
    if data_source:
        event["data_source"] = data_source
    if plan_id:
        event["plan_id"] = plan_id
    if artifact_id:
        event["artifact_id"] = artifact_id
    return {key: value for key, value in event.items() if value not in ("", None, [])}


def _compact_thesis_revision_reference(event: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = [
        "event_id",
        "target_type",
        "symbol",
        "data_source",
        "plan_id",
        "artifact_id",
        "source",
        "reviewed_at",
        "expires_at",
        "reference_price_usd",
        "review_window_days",
        "previous_thesis_hash",
        "revised_thesis_hash",
        "previous_thesis_chars",
        "revised_thesis_chars",
        "rationale_excerpt",
        "evidence_gaps",
        "warnings",
        "recommendation_id",
        "conversation_id",
    ]
    reference = {key: event.get(key) for key in allowed_keys if event.get(key) not in ("", None, [])}
    return reference


def _link_thesis_revision_to_recommendation(
    recommendation_id: Any,
    event: dict[str, Any],
    *,
    inbox: RecommendationInbox | None = None,
) -> None:
    rec_id = str(recommendation_id or "").strip()
    if not rec_id:
        return
    resolved_inbox = inbox or recommendation_inbox
    try:
        recommendation = resolved_inbox.get(rec_id)
    except Exception:
        return
    action_payload = recommendation.get("action_payload")
    payload = dict(action_payload) if isinstance(action_payload, dict) else {}
    revision_reference = _compact_thesis_revision_reference(event)
    if not revision_reference:
        return
    payload["thesis_revision"] = revision_reference
    expected = payload.get("expected_outcome") if isinstance(payload.get("expected_outcome"), dict) else {}
    closure = payload.get("decision_closure") if isinstance(payload.get("decision_closure"), dict) else {}
    closure_expected = closure.get("expected_outcome") if isinstance(closure.get("expected_outcome"), dict) else {}
    if isinstance(expected, dict) and expected:
        expected_outcome = dict(expected)
    else:
        expected_outcome = dict(closure_expected)
    expected_outcome.setdefault("expected_delta_context_quality", "thesis_revised")
    expected_outcome.setdefault("expected_next_safe_action", "review_outcome_quality")
    if closure:
        closure["expected_outcome"] = expected_outcome
        payload["decision_closure"] = closure
    else:
        payload["expected_outcome"] = expected_outcome
    resolved_inbox.update(rec_id, updates={"action_payload": payload})


def _revision_history_inline(value: Any, *, limit: int = 140) -> str:
    return _compact_revision_text(value, limit=limit).replace("`", "'").replace("|", "/")


def _thesis_revision_history_line(event: dict[str, Any]) -> str:
    parts = [
        f"- Reviewed `{_revision_history_inline(event.get('reviewed_at'), limit=80)}`",
        f"source=`{_revision_history_inline(event.get('source'), limit=40)}`",
    ]
    if event.get("symbol"):
        parts.append(f"symbol=`{_revision_history_inline(event.get('symbol'), limit=20)}`")
    if event.get("artifact_id"):
        parts.append(f"artifact=`{_revision_history_inline(event.get('artifact_id'), limit=80)}`")
    if event.get("reference_price_usd") is not None:
        parts.append(f"ref=`{event.get('reference_price_usd')}`")
    if event.get("review_window_days"):
        parts.append(f"window=`{event.get('review_window_days')}d`")
    parts.extend([
        f"prior_hash=`{_revision_history_inline(event.get('previous_thesis_hash'), limit=20)}`",
        f"revised_hash=`{_revision_history_inline(event.get('revised_thesis_hash'), limit=20)}`",
        f"prior=`{_revision_history_inline(event.get('previous_thesis_excerpt'))}`",
        f"revised=`{_revision_history_inline(event.get('revised_thesis_excerpt'))}`",
    ])
    if event.get("rationale_excerpt"):
        parts.append(f"rationale=`{_revision_history_inline(event.get('rationale_excerpt'))}`")
    if event.get("evidence_gaps"):
        parts.append(f"gaps=`{_revision_history_inline('; '.join(event.get('evidence_gaps') or []))}`")
    if event.get("warnings"):
        parts.append(f"warnings=`{_revision_history_inline('; '.join(event.get('warnings') or []))}`")
    if event.get("recommendation_id"):
        parts.append(f"recommendation=`{_revision_history_inline(event.get('recommendation_id'), limit=80)}`")
    if event.get("conversation_id"):
        parts.append(f"conversation=`{_revision_history_inline(event.get('conversation_id'), limit=80)}`")
    return " ".join(parts)


def _extract_thesis_revision_history_lines(markdown: Any) -> list[str]:
    section = _extract_markdown_section(markdown, "Thesis Revision History")
    lines: list[str] = []
    for raw in section.splitlines():
        line = raw.strip()
        if line.startswith("- Reviewed `"):
            lines.append(line)
        if len(lines) >= THESIS_REVISION_HISTORY_LIMIT:
            break
    return lines


def _parse_thesis_revision_history_line(line: str) -> dict[str, Any]:
    text = str(line or "").strip()
    if not text.startswith("- Reviewed `"):
        return {}
    reviewed_match = re.match(r"- Reviewed `(?P<reviewed>[^`]*)`", text)
    pairs = dict(re.findall(r"([a-z_]+)=`([^`]*)`", text))
    event: dict[str, Any] = {
        "target_type": "dossier",
        "reviewed_at": reviewed_match.group("reviewed") if reviewed_match else "",
        "source": pairs.get("source", ""),
        "symbol": pairs.get("symbol", ""),
        "artifact_id": pairs.get("artifact", ""),
        "previous_thesis_hash": pairs.get("prior_hash", ""),
        "revised_thesis_hash": pairs.get("revised_hash", ""),
        "previous_thesis_excerpt": pairs.get("prior", ""),
        "revised_thesis_excerpt": pairs.get("revised", ""),
        "rationale_excerpt": pairs.get("rationale", ""),
        "recommendation_id": pairs.get("recommendation", ""),
        "conversation_id": pairs.get("conversation", ""),
    }
    if pairs.get("ref"):
        event["reference_price_usd"] = _coerce_optional_float(pairs.get("ref"))
    if pairs.get("window"):
        try:
            event["review_window_days"] = int(str(pairs.get("window") or "").rstrip("d"))
        except ValueError:
            pass
    if pairs.get("gaps"):
        event["evidence_gaps"] = [
            item.strip()
            for item in str(pairs.get("gaps") or "").split(";")
            if item.strip()
        ][:THESIS_REVISION_LIST_LIMIT]
    if pairs.get("warnings"):
        event["warnings"] = [
            item.strip()
            for item in str(pairs.get("warnings") or "").split(";")
            if item.strip()
        ][:THESIS_REVISION_LIST_LIMIT]
    return {key: value for key, value in event.items() if value not in ("", None, [])}


def _extract_thesis_revision_history(markdown: Any) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for line in _extract_thesis_revision_history_lines(markdown):
        event = _parse_thesis_revision_history_line(line)
        if event:
            history.append(event)
        if len(history) >= THESIS_REVISION_HISTORY_LIMIT:
            break
    return history


def _replace_thesis_revision_history_section(markdown: str, event: dict[str, Any]) -> str:
    line = _thesis_revision_history_line(event)
    existing = _extract_thesis_revision_history_lines(markdown)
    body = "\n".join([line] + existing[: max(0, THESIS_REVISION_HISTORY_LIMIT - 1)])
    return _replace_markdown_section(markdown, "Thesis Revision History", body)


def _normalize_recommendation_evidence_citations(raw_citations: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_citations, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_citations:
        if not isinstance(raw, dict):
            continue
        symbol = str(raw.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        source = str(raw.get("source") or "manual").strip().lower() or "manual"
        artifact_id = str(raw.get("artifact_id") or "").strip()
        artifact_title = str(raw.get("artifact_title") or "").strip()
        note = str(raw.get("note") or "").strip()
        key = (symbol, source, artifact_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "symbol": symbol,
                "source": source,
                "artifact_id": artifact_id or None,
                "artifact_title": artifact_title or None,
                "note": note,
            }
        )
        if len(normalized) >= 24:
            break
    return normalized


def _prepare_recommendation_action_payload(
    *,
    source: str,
    action_payload: dict[str, Any] | None,
    plan_id: str | None,
) -> dict[str, Any]:
    payload = dict(action_payload) if isinstance(action_payload, dict) else {}
    evidence_raw = payload.get("evidence")
    evidence = dict(evidence_raw) if isinstance(evidence_raw, dict) else {}
    payload["evidence"] = evidence

    symbol_candidates: list[str] = []
    for key in ("research_symbols", "symbols"):
        symbol_candidates.extend(_coerce_symbol_list_from_raw(payload.get(key)))
        symbol_candidates.extend(_coerce_symbol_list_from_raw(evidence.get(key)))
    required_symbols = normalize_research_symbols(symbol_candidates, max_symbols=12)

    if required_symbols:
        payload["research_symbols"] = required_symbols
        evidence["research_symbols"] = required_symbols

    citations = _normalize_recommendation_evidence_citations(evidence.get("citations"))
    citation_symbols = normalize_research_symbols(
        [str(item.get("symbol") or "").strip() for item in citations],
        max_symbols=12,
    )
    citation_symbols_set = set(citation_symbols)

    unresolved_symbols = [symbol for symbol in required_symbols if symbol not in citation_symbols_set]
    resolved_plan_id = str(plan_id or "").strip() or plan_workspace.get_active_plan_id()
    if unresolved_symbols and resolved_plan_id:
        lookup = build_research_dossier_lookup_payload(plan_id=resolved_plan_id, limit=3, include_content=False)
        lookup_items = lookup.get("items") if isinstance(lookup, dict) else []
        dossier_items = lookup_items if isinstance(lookup_items, list) else []
        for symbol in unresolved_symbols:
            matched: dict[str, Any] | None = None
            for item in dossier_items:
                if not isinstance(item, dict):
                    continue
                dossier_symbols = item.get("symbols")
                symbols = normalize_research_symbols(dossier_symbols, max_symbols=12) if isinstance(
                    dossier_symbols,
                    list,
                ) else []
                if symbols and symbol not in symbols:
                    continue
                matched = item
                break
            if matched is None:
                continue
            citations.append(
                {
                    "symbol": symbol,
                    "source": "research_dossier",
                    "artifact_id": str(matched.get("artifact_id") or "") or None,
                    "artifact_title": str(matched.get("title") or "") or None,
                    "note": "Auto-cited from latest plan research dossier.",
                }
            )

    citations = _normalize_recommendation_evidence_citations(citations)
    cited_symbols = normalize_research_symbols(
        [str(item.get("symbol") or "").strip() for item in citations],
        max_symbols=12,
    )
    cited_symbol_set = set(cited_symbols)
    missing_symbols = [symbol for symbol in required_symbols if symbol not in cited_symbol_set]
    dossier_cited_symbols = normalize_research_symbols(
        [
            str(item.get("symbol") or "").strip()
            for item in citations
            if str(item.get("artifact_id") or "").strip()
            or str(item.get("source") or "").strip().lower() == "research_dossier"
        ],
        max_symbols=12,
    )
    dossier_symbol_set = set(dossier_cited_symbols)
    missing_dossier_symbols = [symbol for symbol in required_symbols if symbol not in dossier_symbol_set]

    citation_status = "not_required"
    if required_symbols:
        if not citations:
            citation_status = "missing"
        elif missing_dossier_symbols:
            citation_status = "partial"
        else:
            citation_status = "satisfied"

    citation_required = _recommendation_source_requires_dossier_citations(source) and bool(required_symbols)
    evidence["citations"] = citations
    evidence["citation_quality"] = {
        "model_version": RECOMMENDATION_CITATION_MODEL_VERSION,
        "required": citation_required,
        "status": citation_status,
        "required_symbols": required_symbols,
        "cited_symbols": cited_symbols,
        "missing_symbols": missing_symbols,
        "missing_dossier_symbols": missing_dossier_symbols,
        "updated_at": context_utc_now_iso(),
    }
    if citation_required and citation_status != "satisfied":
        missing_label = ", ".join(missing_dossier_symbols or missing_symbols or required_symbols)
        raise ValueError(
            "Copilot research-backed recommendations require dossier-backed evidence citations "
            f"for symbols: {missing_label}. Run research_dossier with save_to_plan=true (or pass "
            "action_payload.evidence.citations with artifact_id references) and retry."
        )
    return payload


def _workflow_recommendation_payload(
    workflow_id: str,
    recommendation_text: str,
    plan_id: str | None = None,
    result_context: dict[str, Any] | None = None,
    inbox: RecommendationInbox | None = None,
) -> dict[str, Any]:
    resolved_inbox = inbox or recommendation_inbox
    text = recommendation_text.strip()
    context = result_context if isinstance(result_context, dict) else {}
    data_payload = context.get("data") if isinstance(context.get("data"), dict) else {}
    snapshot_as_of = (
        data_payload.get("snapshot_as_of")
        or data_payload.get("latest_snapshot_as_of")
        or data_payload.get("current_snapshot_as_of")
    )
    evidence = {
        "workflow_id": workflow_id,
        "generated_at": context.get("generated_at"),
        "summary": context.get("summary"),
        "snapshot_as_of": snapshot_as_of,
        "data_keys": sorted(list(data_payload.keys()))[:16],
    }
    action_payload = _prepare_recommendation_action_payload(
        source=f"workflow:{workflow_id}",
        action_payload={
            "workflow_id": workflow_id,
            "suggested_action": text,
            "evidence": evidence,
        },
        plan_id=plan_id,
    )

    return resolved_inbox.create(
        title=f"{workflow_id.replace('_', ' ').title()} Recommendation",
        detail=text,
        priority="medium",
        recommendation_type="workflow_action",
        source=f"workflow:{workflow_id}",
        plan_id=plan_id,
        action_payload=action_payload,
    )


def create_recommendations_from_workflow_result(
    workflow_id: str,
    result: dict[str, Any],
    plan_id: str | None = None,
    max_items: int = 4,
    inbox: RecommendationInbox | None = None,
) -> list[dict[str, Any]]:
    data = result.get("data")
    if not isinstance(data, dict):
        return []

    recommendations = data.get("recommendations")
    if not isinstance(recommendations, list):
        return []

    created: list[dict[str, Any]] = []
    for raw in recommendations[: max(1, max_items)]:
        text = str(raw or "").strip()
        if not text:
            continue
        created.append(
            _workflow_recommendation_payload(
                workflow_id=workflow_id,
                recommendation_text=text,
                plan_id=plan_id,
                result_context=result,
                inbox=inbox,
            )
        )
    return created


def _resolve_recommendation_plan_id(
    recommendation: dict[str, Any],
    requested_plan_id: str | None = None,
) -> str:
    if requested_plan_id and requested_plan_id.strip():
        return requested_plan_id.strip()

    recommendation_plan_id = str(recommendation.get("plan_id") or "").strip()
    if recommendation_plan_id:
        return recommendation_plan_id

    active_plan_id = plan_workspace.get_active_plan_id()
    if active_plan_id:
        return active_plan_id

    raise ValueError("No plan_id is available for applying this recommendation.")


def _extract_decision_packet_symbols(
    recommendation: dict[str, Any],
    request_symbols: list[str] | None = None,
    context_payload: dict[str, Any] | None = None,
) -> list[str]:
    candidates: list[Any] = []
    if isinstance(request_symbols, list):
        candidates.extend(request_symbols)

    action_payload = recommendation.get("action_payload")
    if isinstance(action_payload, dict):
        for key in ("research_symbols", "symbols"):
            raw = action_payload.get(key)
            if isinstance(raw, list):
                candidates.extend(raw)
        evidence = action_payload.get("evidence")
        if isinstance(evidence, dict):
            for key in ("research_symbols", "symbols"):
                raw = evidence.get(key)
                if isinstance(raw, list):
                    candidates.extend(raw)

    if isinstance(context_payload, dict):
        research_payload = context_payload.get("research")
        if isinstance(research_payload, dict):
            for key in ("requested_symbols", "symbols"):
                raw = research_payload.get(key)
                if isinstance(raw, list):
                    candidates.extend(raw)

    return normalize_research_symbols(candidates, max_symbols=16)


def _extract_recommendation_plan_settings_updates(
    recommendation: dict[str, Any],
    request_updates: dict[str, Any] | None = None,
) -> dict[str, object]:
    action_payload = recommendation.get("action_payload")
    payload_updates_raw = (
        action_payload.get("plan_settings_updates")
        if isinstance(action_payload, dict)
        else None
    )
    payload_updates = payload_updates_raw if isinstance(payload_updates_raw, dict) else {}
    merged_updates: dict[str, object] = {
        key: value
        for key, value in payload_updates.items()
        if isinstance(key, str)
    }
    if isinstance(request_updates, dict):
        merged_updates.update(
            {
                key: value
                for key, value in request_updates.items()
                if isinstance(key, str)
            }
        )
    return extract_plan_settings_updates(merged_updates)


def _summarize_recommendation_scenario_diff_preview(
    *,
    diff_payload: dict[str, Any],
    compare_updates: dict[str, object],
    assumption_set_id: str | None = None,
    candidate_assumption_set_id: str | None = None,
) -> dict[str, Any]:
    deltas_raw = diff_payload.get("scenario_deltas")
    summarized_deltas: list[dict[str, Any]] = []
    if isinstance(deltas_raw, list):
        for row in deltas_raw:
            if not isinstance(row, dict):
                continue
            summarized_deltas.append(
                {
                    "label": row.get("label"),
                    "delta_future_value_usd": row.get("delta_future_value_usd"),
                    "delta_real_value_usd": row.get("delta_real_value_usd"),
                }
            )

    monte_raw = diff_payload.get("monte_carlo_delta")
    monte_carlo_delta = monte_raw if isinstance(monte_raw, dict) else {}
    return {
        "status": "captured",
        "captured_at": context_utc_now_iso(),
        "plan_id": diff_payload.get("plan_id"),
        "current_portfolio_value_usd": diff_payload.get("current_portfolio_value_usd"),
        "compare_settings": compare_updates,
        "assumption_set_id": assumption_set_id,
        "candidate_assumption_set_id": candidate_assumption_set_id,
        "scenario_deltas": summarized_deltas,
        "monte_carlo_delta": monte_carlo_delta,
    }


def _format_currency_amount(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"${parsed:,.2f}"


def _scenario_diff_preview_summary_text(preview_payload: dict[str, Any] | None) -> str:
    if not isinstance(preview_payload, dict):
        return "Scenario preview unavailable."
    status = str(preview_payload.get("status") or "unknown").strip().lower()
    if status != "captured":
        reason = str(preview_payload.get("reason") or "").strip()
        if reason:
            return f"Scenario preview {status}: {reason}"
        return f"Scenario preview {status}."

    deltas_raw = preview_payload.get("scenario_deltas")
    deltas = [item for item in deltas_raw if isinstance(item, dict)] if isinstance(deltas_raw, list) else []
    baseline = next((item for item in deltas if str(item.get("label")) == "baseline"), deltas[0] if deltas else None)
    if not isinstance(baseline, dict):
        return "Scenario preview captured."
    return (
        "Scenario preview captured: baseline "
        f"future-value delta {_format_currency_amount(baseline.get('delta_future_value_usd'))}, "
        f"real-value delta {_format_currency_amount(baseline.get('delta_real_value_usd'))}."
    )


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _extract_scenario_baseline_delta(preview_payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(preview_payload, dict):
        return None
    status = str(preview_payload.get("status") or "").strip().lower()
    if status != "captured":
        return None
    deltas_raw = preview_payload.get("scenario_deltas")
    deltas = [item for item in deltas_raw if isinstance(item, dict)] if isinstance(deltas_raw, list) else []
    if not deltas:
        return None
    baseline = next((item for item in deltas if str(item.get("label") or "").strip().lower() == "baseline"), None)
    if isinstance(baseline, dict):
        return baseline
    candidate = deltas[0]
    return candidate if isinstance(candidate, dict) else None


def _build_expected_outcome_from_preview(preview_payload: dict[str, Any] | None) -> dict[str, Any]:
    baseline = _extract_scenario_baseline_delta(preview_payload)
    if not isinstance(preview_payload, dict):
        preview_payload = {}
    if baseline is None:
        return {
            "status": "unavailable",
            "source": "scenario_diff_preview",
            "captured_at": context_utc_now_iso(),
            "preview_status": str(preview_payload.get("status") or "unknown").strip().lower() or "unknown",
            "expected_delta_future_value_usd": None,
            "expected_delta_real_value_usd": None,
            "baseline_label": None,
        }

    return {
        "status": "captured",
        "source": "scenario_diff_preview",
        "captured_at": str(preview_payload.get("captured_at") or context_utc_now_iso()),
        "preview_status": "captured",
        "baseline_label": str(baseline.get("label") or "baseline"),
        "expected_delta_future_value_usd": _coerce_optional_float(baseline.get("delta_future_value_usd")),
        "expected_delta_real_value_usd": _coerce_optional_float(baseline.get("delta_real_value_usd")),
    }


def _same_direction(expected: float, realized: float) -> bool:
    if expected == 0.0 or realized == 0.0:
        return expected == realized
    return (expected > 0 and realized > 0) or (expected < 0 and realized < 0)


def _build_expected_vs_realized_metrics(
    *,
    expected_outcome: dict[str, Any] | None,
    realized_outcome: dict[str, Any] | None,
) -> dict[str, Any]:
    expected = expected_outcome if isinstance(expected_outcome, dict) else {}
    realized = realized_outcome if isinstance(realized_outcome, dict) else {}
    expected_future = _coerce_optional_float(expected.get("expected_delta_future_value_usd"))
    expected_real = _coerce_optional_float(expected.get("expected_delta_real_value_usd"))
    realized_future = _coerce_optional_float(realized.get("realized_delta_future_value_usd"))
    realized_real = _coerce_optional_float(realized.get("realized_delta_real_value_usd"))

    has_expected = expected_future is not None or expected_real is not None
    has_realized = realized_future is not None or realized_real is not None

    future_gap: float | None = None
    future_abs_error: float | None = None
    future_direction_match: bool | None = None
    if expected_future is not None and realized_future is not None:
        future_gap = realized_future - expected_future
        future_abs_error = abs(future_gap)
        future_direction_match = _same_direction(expected_future, realized_future)

    real_gap: float | None = None
    real_abs_error: float | None = None
    real_direction_match: bool | None = None
    if expected_real is not None and realized_real is not None:
        real_gap = realized_real - expected_real
        real_abs_error = abs(real_gap)
        real_direction_match = _same_direction(expected_real, realized_real)

    status = "unavailable"
    if has_expected and not has_realized:
        status = "pending_realized"
    elif has_expected and has_realized:
        status = "measured"
    elif (not has_expected) and has_realized:
        status = "realized_only"

    return {
        "status": status,
        "has_expected": has_expected,
        "has_realized": has_realized,
        "future_value_gap_usd": future_gap,
        "future_value_abs_error_usd": future_abs_error,
        "future_value_direction_match": future_direction_match,
        "real_value_gap_usd": real_gap,
        "real_value_abs_error_usd": real_abs_error,
        "real_value_direction_match": real_direction_match,
        "updated_at": context_utc_now_iso(),
    }


def _expected_vs_realized_summary_text(metrics: dict[str, Any] | None) -> str:
    if not isinstance(metrics, dict):
        return "Outcome tracking unavailable."
    status = str(metrics.get("status") or "unavailable").strip().lower() or "unavailable"
    if status == "measured":
        return (
            "Outcome measured: "
            f"future gap {_format_currency_amount(metrics.get('future_value_gap_usd'))}, "
            f"real gap {_format_currency_amount(metrics.get('real_value_gap_usd'))}."
        )
    if status == "pending_realized":
        return "Expected outcome captured; realized outcome pending."
    if status == "realized_only":
        return "Realized outcome captured without expected baseline."
    return "Expected vs realized outcome unavailable."


def _build_decision_pre_mortem_from_request(request: RecommendationApplyRequest) -> dict[str, Any]:
    payload = {
        "expected_benefit": str(request.premortem_expected_benefit or "").strip(),
        "main_risk": str(request.premortem_main_risk or "").strip(),
        "disconfirming_signal": str(request.premortem_disconfirming_signal or "").strip(),
        "monitoring_plan": str(request.premortem_monitoring_plan or "").strip(),
        "review_date": request.premortem_review_date.isoformat() if request.premortem_review_date else "",
    }
    return {key: value for key, value in payload.items() if value}


def _build_recommendation_closure_markdown(
    *,
    recommendation: dict[str, Any],
    decision_closure: dict[str, Any],
) -> str:
    preview_payload = (
        decision_closure.get("scenario_diff_preview")
        if isinstance(decision_closure.get("scenario_diff_preview"), dict)
        else {}
    )
    expected_outcome = (
        decision_closure.get("expected_outcome")
        if isinstance(decision_closure.get("expected_outcome"), dict)
        else {}
    )
    realized_outcome = (
        decision_closure.get("realized_outcome")
        if isinstance(decision_closure.get("realized_outcome"), dict)
        else {}
    )
    expected_vs_realized = (
        decision_closure.get("expected_vs_realized")
        if isinstance(decision_closure.get("expected_vs_realized"), dict)
        else {}
    )
    title = str(recommendation.get("title") or "Recommendation").strip() or "Recommendation"
    lines: list[str] = [
        f"# Recommendation Decision Closure: {title}",
        "",
        "## Recommendation",
        "",
        f"- Recommendation ID: `{recommendation.get('id')}`",
        f"- Type: `{recommendation.get('recommendation_type') or 'general'}`",
        f"- Priority: `{recommendation.get('priority') or 'medium'}`",
        f"- Source: `{recommendation.get('source') or 'manual'}`",
        "",
        "## Decision Closure",
        "",
        f"- Decision status: `{decision_closure.get('decision_status') or 'unknown'}`",
    ]
    if decision_closure.get("applied_at"):
        lines.append(f"- Applied at: `{decision_closure.get('applied_at')}`")
    if decision_closure.get("rejected_at"):
        lines.append(f"- Rejected at: `{decision_closure.get('rejected_at')}`")
    if decision_closure.get("rationale"):
        lines.append(f"- Rationale: {decision_closure.get('rationale')}")
    if decision_closure.get("reason"):
        lines.append(f"- Reason: {decision_closure.get('reason')}")

    pre_mortem = (
        decision_closure.get("pre_mortem")
        if isinstance(decision_closure.get("pre_mortem"), dict)
        else {}
    )
    if pre_mortem:
        lines.extend(["", "## Decision Pre-Mortem", ""])
        if pre_mortem.get("expected_benefit"):
            lines.append(f"- Expected benefit: {pre_mortem.get('expected_benefit')}")
        if pre_mortem.get("main_risk"):
            lines.append(f"- Main risk: {pre_mortem.get('main_risk')}")
        if pre_mortem.get("disconfirming_signal"):
            lines.append(f"- Disconfirming signal: {pre_mortem.get('disconfirming_signal')}")
        if pre_mortem.get("monitoring_plan"):
            lines.append(f"- Monitoring plan: {pre_mortem.get('monitoring_plan')}")
        if pre_mortem.get("review_date"):
            lines.append(f"- Review date: `{pre_mortem.get('review_date')}`")

    lines.extend(["", "## Outcome Tracking", ""])
    if expected_outcome:
        lines.append(
            f"- Expected future-value delta: {_format_currency_amount(expected_outcome.get('expected_delta_future_value_usd'))}"
        )
        lines.append(
            f"- Expected real-value delta: {_format_currency_amount(expected_outcome.get('expected_delta_real_value_usd'))}"
        )
    else:
        lines.append("- Expected outcome: unavailable")
    if realized_outcome:
        lines.append(
            f"- Realized future-value delta: {_format_currency_amount(realized_outcome.get('realized_delta_future_value_usd'))}"
        )
        lines.append(
            f"- Realized real-value delta: {_format_currency_amount(realized_outcome.get('realized_delta_real_value_usd'))}"
        )
        if realized_outcome.get("observed_at"):
            lines.append(f"- Observed at: `{realized_outcome.get('observed_at')}`")
        if realized_outcome.get("observation_window_days") is not None:
            lines.append(f"- Observation window days: `{realized_outcome.get('observation_window_days')}`")
        if realized_outcome.get("measurement_source"):
            lines.append(f"- Measurement source: `{realized_outcome.get('measurement_source')}`")
        if realized_outcome.get("note"):
            lines.append(f"- Outcome note: {realized_outcome.get('note')}")
    else:
        lines.append("- Realized outcome: pending")
    lines.append(f"- {_expected_vs_realized_summary_text(expected_vs_realized)}")

    lines.extend(
        [
            "",
            "## Scenario Preview",
            "",
            f"- {_scenario_diff_preview_summary_text(preview_payload if isinstance(preview_payload, dict) else {})}",
            "",
            "```json",
            json.dumps(
                {
                    "recommendation": {
                        "id": recommendation.get("id"),
                        "title": recommendation.get("title"),
                    },
                    "decision_closure": decision_closure,
                },
                indent=2,
                default=str,
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def persist_recommendation_closure_to_plan(
    *,
    plan_id: str,
    recommendation: dict[str, Any],
    decision_closure: dict[str, Any],
    workspace: PlanWorkspace | None = None,
) -> PlanArtifactSummary | None:
    if not plan_id:
        return None
    resolved_workspace = workspace or plan_workspace

    preview_payload = (
        decision_closure.get("scenario_diff_preview")
        if isinstance(decision_closure.get("scenario_diff_preview"), dict)
        else None
    )
    expected_vs_realized = (
        decision_closure.get("expected_vs_realized")
        if isinstance(decision_closure.get("expected_vs_realized"), dict)
        else {}
    )

    decision_status = str(decision_closure.get("decision_status") or "accepted").strip().lower() or "accepted"
    title = str(recommendation.get("title") or "Recommendation").strip() or "Recommendation"
    summary = f"Recommendation closure: {title} ({decision_status})"
    rationale_parts: list[str] = []
    if decision_closure.get("rationale"):
        rationale_parts.append(str(decision_closure.get("rationale")))
    if decision_closure.get("reason"):
        rationale_parts.append(f"Reason: {decision_closure.get('reason')}")
    rationale_parts.append(_expected_vs_realized_summary_text(expected_vs_realized))
    if preview_payload is not None:
        rationale_parts.append(_scenario_diff_preview_summary_text(preview_payload))
    resolved_workspace.append_decision(
        plan_id=plan_id,
        summary=summary,
        rationale=" ".join(part for part in rationale_parts if part).strip(),
        status=decision_status,
    )

    artifact_payload = resolved_workspace.write_artifact(
        plan_id=plan_id,
        title=f"Decision Closure - {title}",
        markdown=_build_recommendation_closure_markdown(
            recommendation=recommendation,
            decision_closure=decision_closure,
        ),
        kind="recommendation_decision_closure",
    )
    return PlanArtifactSummary(**artifact_payload)


async def build_recommendation_scenario_diff_preview(
    recommendation: dict[str, Any],
    *,
    requested_plan_id: str | None = None,
    request_updates: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    recommendation_type = str(recommendation.get("recommendation_type") or "").strip().lower()
    if recommendation_type != "plan_settings_update":
        return None

    compare_updates = _extract_recommendation_plan_settings_updates(
        recommendation,
        request_updates=request_updates,
    )
    if not compare_updates:
        return {
            "status": "skipped",
            "captured_at": context_utc_now_iso(),
            "reason": "No plan settings updates were available for scenario diff capture.",
        }

    try:
        plan_id = _resolve_recommendation_plan_id(recommendation, requested_plan_id)
    except ValueError as exc:
        return {
            "status": "skipped",
            "captured_at": context_utc_now_iso(),
            "reason": str(exc),
        }

    action_payload = recommendation.get("action_payload")
    assumption_set_id = None
    candidate_assumption_set_id = None
    if isinstance(action_payload, dict):
        assumption_set_id = str(action_payload.get("assumption_set_id") or "").strip() or None
        candidate_assumption_set_id = (
            str(action_payload.get("candidate_assumption_set_id") or "").strip() or None
        )

    arguments: dict[str, object] = {
        "plan_id": plan_id,
        **compare_updates,
    }
    if assumption_set_id:
        arguments["assumption_set_id"] = assumption_set_id
    if candidate_assumption_set_id:
        arguments["candidate_assumption_set_id"] = candidate_assumption_set_id

    try:
        diff_payload = await tool_run_plan_scenario_diff(arguments)
    except Exception as exc:
        return {
            "status": "error",
            "captured_at": context_utc_now_iso(),
            "plan_id": plan_id,
            "compare_settings": compare_updates,
            "assumption_set_id": assumption_set_id,
            "candidate_assumption_set_id": candidate_assumption_set_id,
            "reason": str(exc),
        }

    return _summarize_recommendation_scenario_diff_preview(
        diff_payload=diff_payload,
        compare_updates=compare_updates,
        assumption_set_id=assumption_set_id,
        candidate_assumption_set_id=candidate_assumption_set_id,
    )


def _build_pre_apply_action_preview(
    *,
    recommendation: dict[str, Any],
    recommendation_type: str,
    resolved_plan_id: str | None,
    decision_status: str,
    compare_updates: dict[str, object],
) -> dict[str, Any]:
    title = str(recommendation.get("title") or "Recommendation").strip() or "Recommendation"
    detail = str(recommendation.get("detail") or "").strip()
    action_payload = recommendation.get("action_payload")
    payload = action_payload if isinstance(action_payload, dict) else {}

    if recommendation_type == "plan_settings_update":
        return {
            "kind": "plan_settings_update",
            "plan_id": resolved_plan_id,
            "decision_status": decision_status,
            "updates_count": len(compare_updates),
            "proposed_plan_settings_updates": compare_updates,
            "decision_log_summary": (
                f"Would apply plan settings updates to plan `{resolved_plan_id}` "
                f"and append decision status `{decision_status}`."
                if resolved_plan_id
                else "Would apply plan settings updates, but no plan_id is currently resolved."
            ),
        }

    if recommendation_type == "workflow_action":
        workflow_id = str(payload.get("workflow_id") or "").strip() or None
        suggested_action = str(payload.get("suggested_action") or detail).strip()
        return {
            "kind": "workflow_action",
            "plan_id": resolved_plan_id,
            "decision_status": decision_status,
            "workflow_id": workflow_id,
            "suggested_action": suggested_action,
            "decision_log_summary": (
                f"Would append workflow recommendation decision `{title}` to plan `{resolved_plan_id}` "
                f"with status `{decision_status}`."
                if resolved_plan_id
                else f"Would append workflow recommendation decision `{title}`, but no plan_id is currently resolved."
            ),
        }

    return {
        "kind": "general",
        "plan_id": resolved_plan_id,
        "decision_status": decision_status,
        "decision_log_summary": (
            f"Would append recommendation decision `{title}` to plan `{resolved_plan_id}` with status `{decision_status}`."
            if resolved_plan_id
            else f"Would append recommendation decision `{title}`, but no plan_id is currently resolved."
        ),
        "detail_preview": detail,
    }


async def preview_recommendation(
    recommendation_id: str,
    request: RecommendationPreviewRequest,
    *,
    services: WorkspaceServices | None = None,
) -> RecommendationPreviewResponse:
    resolved_services = workspace_services_or_legacy(services)
    recommendation = resolved_services.recommendation_inbox.get(recommendation_id)
    current_status = str(recommendation.get("status", "proposed")).strip().lower()
    if current_status != "proposed":
        raise ValueError("Only proposed recommendations can be previewed before apply/reject.")

    recommendation_type = str(recommendation.get("recommendation_type") or "general").strip().lower() or "general"
    decision_status = str(request.decision_status or "accepted").strip() or "accepted"
    compare_updates = _extract_recommendation_plan_settings_updates(
        recommendation,
        request_updates=request.plan_settings_updates,
    )

    resolved_plan_id: str | None = None
    warnings: list[str] = []
    try:
        resolved_plan_id = _resolve_recommendation_plan_id(recommendation, request.plan_id)
    except ValueError as exc:
        warnings.append(str(exc))

    scenario_diff_preview: dict[str, Any]
    if request.capture_scenario_diff:
        captured = await build_recommendation_scenario_diff_preview(
            recommendation,
            requested_plan_id=request.plan_id,
            request_updates=request.plan_settings_updates,
        )
        if isinstance(captured, dict):
            scenario_diff_preview = captured
        else:
            scenario_diff_preview = {
                "status": "skipped",
                "captured_at": context_utc_now_iso(),
                "reason": "Scenario preview is available for plan_settings_update recommendations.",
            }
    else:
        scenario_diff_preview = {
            "status": "skipped",
            "captured_at": context_utc_now_iso(),
            "reason": "Scenario preview capture disabled by request.",
        }

    if recommendation_type == "plan_settings_update" and not compare_updates:
        warnings.append("No plan settings updates were found in recommendation payload or request overrides.")

    action_preview = _build_pre_apply_action_preview(
        recommendation=recommendation,
        recommendation_type=recommendation_type,
        resolved_plan_id=resolved_plan_id,
        decision_status=decision_status,
        compare_updates=compare_updates,
    )

    suggested_symbols = _extract_decision_packet_symbols(recommendation)
    preview_status = str(scenario_diff_preview.get("status") or "advisory").strip().lower() or "advisory"
    if recommendation_type != "plan_settings_update" and preview_status == "skipped":
        preview_status = "advisory"

    preview_payload: dict[str, Any] = {
        "status": preview_status,
        "captured_at": context_utc_now_iso(),
        "recommendation_id": recommendation_id,
        "recommendation_type": recommendation_type,
        "current_status": current_status,
        "decision_status": decision_status,
        "plan_id": resolved_plan_id,
        "action_preview": action_preview,
        "scenario_diff_preview": scenario_diff_preview,
        "warnings": warnings,
    }

    message = "Pre-apply preview generated."
    if recommendation_type == "plan_settings_update" and preview_status == "captured":
        message = "Pre-apply preview captured with scenario diff deltas."
    elif recommendation_type != "plan_settings_update":
        message = "Pre-apply advisory preview generated for non-plan-settings recommendation."

    return RecommendationPreviewResponse(
        recommendation=_recommendation_item_from_row(recommendation),
        preview=preview_payload,
        suggested_research_symbols=suggested_symbols,
        message=message,
    )


def _build_decision_packet_assumptions(
    plan_id: str,
    plan_detail: PlanDetailResponse | None,
    *,
    workspace: PlanWorkspace | None = None,
) -> dict[str, Any]:
    resolved_workspace = workspace or plan_workspace
    plan_settings: dict[str, Any] = {}
    if plan_detail is not None:
        plan_settings = {
            key: value
            for key, value in plan_detail.settings.model_dump(mode="json").items()
            if value is not None and key not in {"schema_version", "updated_at"}
        }

    active_assumption_set_id: str | None = None
    active_assumption_set: dict[str, Any] = {}
    assumption_set_count = 0
    try:
        payload = resolved_workspace.get_plan_assumption_sets(plan_id)
        sets = payload.get("sets")
        assumption_sets = [item for item in sets if isinstance(item, dict)] if isinstance(sets, list) else []
        assumption_set_count = len(assumption_sets)
        active_assumption_set_id = str(payload.get("active_assumption_set_id") or "").strip() or None
        if active_assumption_set_id:
            for item in assumption_sets:
                if str(item.get("id") or "").strip() != active_assumption_set_id:
                    continue
                active_assumption_set = {
                    key: value
                    for key, value in item.items()
                    if value is not None
                }
                break
    except Exception:
        active_assumption_set = {}

    return {
        "plan_settings": plan_settings,
        "active_assumption_set_id": active_assumption_set_id,
        "active_assumption_set": active_assumption_set,
        "assumption_sets_count": assumption_set_count,
    }


def _build_decision_packet_markdown(
    *,
    recommendation: dict[str, Any],
    plan_id: str,
    rationale: str,
    decision_status: str,
    cited_symbols: list[str],
    assumptions_payload: dict[str, Any],
    context_payload: dict[str, Any] | None = None,
    context_error: str | None = None,
) -> str:
    context = context_payload if isinstance(context_payload, dict) else {}
    context_scope = context.get("scope") if isinstance(context.get("scope"), dict) else {}
    context_quality = context.get("quality") if isinstance(context.get("quality"), dict) else {}
    context_freshness = (
        context_quality.get("freshness")
        if isinstance(context_quality.get("freshness"), dict)
        else {}
    )
    context_coverage = (
        context_quality.get("coverage")
        if isinstance(context_quality.get("coverage"), dict)
        else {}
    )
    context_warnings = context.get("warnings") if isinstance(context.get("warnings"), list) else []
    context_summary = str(context.get("summary") or "").strip()

    packet_payload = {
        "recommendation": {
            "id": recommendation.get("id"),
            "title": recommendation.get("title"),
            "priority": recommendation.get("priority"),
            "source": recommendation.get("source"),
            "recommendation_type": recommendation.get("recommendation_type"),
            "created_at": recommendation.get("created_at"),
            "resolved_at": recommendation.get("resolved_at"),
        },
        "decision": {
            "plan_id": plan_id,
            "decision_status": decision_status,
            "rationale": rationale,
            "cited_research_symbols": cited_symbols,
        },
        "assumptions": assumptions_payload,
        "context": {
            "generated_at": context.get("generated_at"),
            "scope": context_scope,
            "quality": {
                "freshness": context_freshness,
                "coverage": context_coverage,
                "warning_count": len(context_warnings),
            },
            "error": context_error,
        },
    }

    lines: list[str] = [
        f"# Decision Packet: {recommendation.get('title') or 'Recommendation'}",
        "",
        "## Recommendation",
        "",
        f"- Recommendation ID: `{recommendation.get('id')}`",
        f"- Plan ID: `{plan_id}`",
        f"- Type: `{recommendation.get('recommendation_type') or 'general'}`",
        f"- Priority: `{recommendation.get('priority') or 'medium'}`",
        f"- Source: `{recommendation.get('source') or 'manual'}`",
        f"- Decision Status: `{decision_status}`",
        f"- Rationale: {rationale or 'n/a'}",
        "",
        "## Cited Research Symbols",
        "",
    ]
    if cited_symbols:
        lines.append(f"- {', '.join(cited_symbols)}")
    else:
        lines.append("- None captured for this decision.")

    lines.extend(["", "## Unified Context Snapshot", ""])
    if context_error:
        lines.append(f"- Context generation warning: {context_error}")
    if context:
        lines.extend(
            [
                f"- Context generated at: `{context.get('generated_at')}`",
                f"- Context detail level: `{context_scope.get('detail_level')}`",
                f"- Coverage score: `{context_coverage.get('score_pct')}`",
                f"- Snapshot stale: `{context_freshness.get('snapshot_stale')}`",
                f"- Snapshot age seconds: `{context_freshness.get('snapshot_age_seconds')}`",
                f"- Warning count: `{len(context_warnings)}`",
            ]
        )
        if context_summary:
            lines.extend(["", "### Context Summary", "", context_summary])
        if context_warnings:
            lines.extend(["", "### Context Warnings", ""])
            lines.extend([f"- {str(item)}" for item in context_warnings[:8]])
    else:
        lines.append("- Unified context payload unavailable for this packet.")

    plan_settings = assumptions_payload.get("plan_settings")
    active_set = assumptions_payload.get("active_assumption_set")
    lines.extend(["", "## Selected Plan Assumptions", ""])
    if isinstance(plan_settings, dict) and plan_settings:
        lines.append("- Plan settings overrides in effect:")
        lines.extend([f"  - `{key}`: `{value}`" for key, value in sorted(plan_settings.items())])
    else:
        lines.append("- Plan settings overrides in effect: none")

    if isinstance(active_set, dict) and active_set:
        set_id = active_set.get("id")
        set_name = active_set.get("name")
        lines.append(f"- Active assumption set: `{set_name or set_id or 'unknown'}`")
        for key, value in sorted(active_set.items()):
            if key in {"id", "name"}:
                continue
            lines.append(f"  - `{key}`: `{value}`")
    else:
        active_set_id = assumptions_payload.get("active_assumption_set_id")
        lines.append(f"- Active assumption set: `{active_set_id or 'none'}`")

    lines.extend(
        [
            "",
            "## Structured Packet",
            "",
            "```json",
            json.dumps(packet_payload, indent=2, default=str),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


async def apply_recommendation_with_decision_packet(
    recommendation_id: str,
    request: RecommendationApplyRequest,
    *,
    services: WorkspaceServices | None = None,
) -> RecommendationActionResponse:
    resolved_services = workspace_services_or_legacy(services)
    pre_apply_recommendation = resolved_services.recommendation_inbox.get(recommendation_id)
    scenario_diff_preview: dict[str, Any] | None = None
    if request.capture_scenario_diff:
        scenario_diff_preview = await build_recommendation_scenario_diff_preview(
            pre_apply_recommendation,
            requested_plan_id=request.plan_id,
            request_updates=request.plan_settings_updates,
        )

    result = apply_recommendation(recommendation_id, request, services=resolved_services)
    recommendation_payload = result.recommendation.model_dump(mode="json")
    plan_id = str(result.plan.id) if result.plan is not None else ""

    context_payload: dict[str, Any] | None = None
    context_error: str | None = None
    requested_symbols = normalize_research_symbols(request.decision_packet_research_symbols, max_symbols=12)
    if request.create_decision_packet and plan_id:
        try:
            context_payload = await build_buildwealth_context_payload(
                use_live_snapshot=False,
                plan_id=plan_id,
                include_research=True,
                include_plan_projection=False,
                force_refresh=False,
                research_symbols=requested_symbols,
                max_recommendations=10,
                max_plan_decisions=8,
                summary_max_chars=1800,
                research_symbol_limit=max(DEFAULT_RESEARCH_SYMBOL_LIMIT, len(requested_symbols) or 0),
                detail_level="light",
            )
        except Exception as exc:
            context_error = str(exc)

    cited_symbols = _extract_decision_packet_symbols(
        recommendation_payload,
        request_symbols=requested_symbols,
        context_payload=context_payload,
    )
    suggested_symbols = normalize_research_symbols(cited_symbols, max_symbols=12)
    decision_closure_payload: dict[str, Any] = {
        "applied_at": context_utc_now_iso(),
        "decision_status": str(request.decision_status or "accepted").strip() or "accepted",
        "rationale": request.rationale.strip() if request.rationale else "",
    }
    pre_mortem_payload = _build_decision_pre_mortem_from_request(request)
    if pre_mortem_payload:
        decision_closure_payload["pre_mortem"] = pre_mortem_payload
    if scenario_diff_preview:
        decision_closure_payload["scenario_diff_preview"] = scenario_diff_preview
    expected_outcome = _build_expected_outcome_from_preview(scenario_diff_preview)
    decision_closure_payload["expected_outcome"] = expected_outcome
    decision_closure_payload["expected_vs_realized"] = _build_expected_vs_realized_metrics(
        expected_outcome=expected_outcome,
        realized_outcome={},
    )

    research_bridge_payload: dict[str, Any] = {}
    research_bridge_message_suffix = ""
    if result.plan is not None and request.pin_research_bridge:
        requested_bridge_symbols = normalize_research_symbols(request.research_bridge_symbols, max_symbols=12)
        candidate_bridge_symbols = requested_bridge_symbols or suggested_symbols
        try:
            research_bridge_response = pin_watchlist_research_bridge(
                plan_id=plan_id,
                request=PlanResearchBridgeRequest(
                    branch_template_id=request.research_bridge_template_id,
                    assumption_set_id=request.research_bridge_assumption_set_id,
                    symbols=candidate_bridge_symbols,
                    max_symbols=max(1, min(max(len(candidate_bridge_symbols), 5), 20)),
                ),
            )
            pinned_symbols = normalize_research_symbols(research_bridge_response.pinned_symbols, max_symbols=12)
            if pinned_symbols:
                suggested_symbols = pinned_symbols
            research_bridge_payload = {
                "status": "pinned",
                "template_id": research_bridge_response.template_id,
                "template_name": research_bridge_response.template_name,
                "pinned_symbols": pinned_symbols,
                "requested_symbols": candidate_bridge_symbols,
                "updated_at": context_utc_now_iso(),
            }
            research_bridge_message_suffix = (
                f" Pinned {len(pinned_symbols)} research symbol(s) into template "
                f"{research_bridge_response.template_id}."
            )
        except (PlanNotFoundError, ValueError) as exc:
            research_bridge_payload = {
                "status": "skipped",
                "reason": str(exc),
                "requested_symbols": candidate_bridge_symbols,
                "updated_at": context_utc_now_iso(),
            }
            research_bridge_message_suffix = f" Research bridge skipped: {exc}."

    artifact_summary: PlanArtifactSummary | None = None
    decision_packet_message_suffix = ""
    assumptions_payload: dict[str, Any] = {}
    if request.create_decision_packet and result.plan is not None:
        assumptions_payload = _build_decision_packet_assumptions(
            plan_id,
            result.plan,
            workspace=resolved_services.plan_workspace,
        )
        decision_status = str(request.decision_status or "accepted").strip() or "accepted"
        rationale = request.rationale.strip() if request.rationale else str(recommendation_payload.get("detail") or "")
        markdown = _build_decision_packet_markdown(
            recommendation=recommendation_payload,
            plan_id=plan_id,
            rationale=rationale,
            decision_status=decision_status,
            cited_symbols=suggested_symbols,
            assumptions_payload=assumptions_payload,
            context_payload=context_payload,
            context_error=context_error,
        )

        try:
            artifact_payload = resolved_services.plan_workspace.write_artifact(
                plan_id=plan_id,
                title=f"Decision Packet - {recommendation_payload.get('title') or recommendation_id}",
                markdown=markdown,
                kind="decision_packet",
            )
            artifact_summary = PlanArtifactSummary(**artifact_payload)
            decision_packet_message_suffix = " Decision packet saved to plan artifacts."
        except Exception as exc:
            decision_packet_message_suffix = f" Decision packet could not be written: {exc}"

    closure_artifact_summary: PlanArtifactSummary | None = None
    closure_message_suffix = ""
    if result.plan is not None and decision_closure_payload:
        try:
            closure_artifact_summary = persist_recommendation_closure_to_plan(
                plan_id=plan_id,
                recommendation=recommendation_payload,
                decision_closure=decision_closure_payload,
                workspace=resolved_services.plan_workspace,
            )
            if closure_artifact_summary is not None:
                closure_message_suffix = " Decision closure snapshot saved to plan artifacts."
        except Exception as exc:
            closure_message_suffix = f" Decision closure snapshot could not be written: {exc}"

    action_payload_raw = recommendation_payload.get("action_payload")
    action_payload = dict(action_payload_raw) if isinstance(action_payload_raw, dict) else {}
    thesis_review_payload: dict[str, Any] = {}
    try:
        thesis_review_payload = refresh_research_thesis_review_from_recommendation(
            recommendation_payload,
            plan_id=plan_id or None,
            services=resolved_services,
        )
    except Exception as exc:
        thesis_review_payload = {
            "status": "skipped",
            "reason": str(exc),
            "updated_at": context_utc_now_iso(),
        }
    if thesis_review_payload:
        action_payload["thesis_review"] = thesis_review_payload
    if suggested_symbols:
        action_payload["suggested_research_symbols"] = suggested_symbols
    if research_bridge_payload:
        action_payload["research_bridge"] = research_bridge_payload
    if decision_closure_payload:
        action_payload["decision_closure"] = decision_closure_payload
    if closure_artifact_summary is not None:
        action_payload["decision_closure_artifact"] = {
            "artifact_id": closure_artifact_summary.id,
            "file_name": closure_artifact_summary.file_name,
            "plan_id": plan_id,
            "created_at": closure_artifact_summary.created_at.isoformat(),
        }
    if artifact_summary is not None:
        decision_status = str(request.decision_status or "accepted").strip() or "accepted"
        action_payload["decision_packet"] = {
            "artifact_id": artifact_summary.id,
            "file_name": artifact_summary.file_name,
            "plan_id": plan_id,
            "created_at": artifact_summary.created_at.isoformat(),
            "decision_status": decision_status,
            "cited_research_symbols": suggested_symbols,
            "context_generated_at": context_payload.get("generated_at") if isinstance(context_payload, dict) else None,
            "assumption_set_id": assumptions_payload.get("active_assumption_set_id"),
        }

    updated_recommendation_payload = recommendation_payload
    if action_payload:
        updated_recommendation_payload = resolved_services.recommendation_inbox.update(
            recommendation_id,
            updates={"action_payload": action_payload},
        )
    refreshed_plan = (
        PlanDetailResponse(**resolved_services.plan_workspace.get_plan(plan_id))
        if result.plan is not None
        else None
    )

    return RecommendationActionResponse(
        recommendation=_recommendation_item_from_row(updated_recommendation_payload),
        plan=refreshed_plan,
        decision_packet_artifact=artifact_summary,
        decision_closure_artifact=closure_artifact_summary,
        suggested_research_symbols=suggested_symbols,
        research_bridge=research_bridge_payload,
        decision_closure=decision_closure_payload,
        message=(
            f"{result.message}{decision_packet_message_suffix}"
            f"{research_bridge_message_suffix}{closure_message_suffix}"
        ),
    )


def _thesis_review_action_context(recommendation: dict[str, Any]) -> dict[str, Any] | None:
    action_payload = recommendation.get("action_payload")
    if not isinstance(action_payload, dict):
        return None
    suggested_action = action_payload.get("suggested_action")
    if not isinstance(suggested_action, dict):
        return None
    if str(suggested_action.get("kind") or "").strip().lower() != "review_research_thesis":
        return None
    evidence = action_payload.get("evidence") if isinstance(action_payload.get("evidence"), dict) else {}
    return {
        "suggested_action": suggested_action,
        "evidence": evidence,
        "action_payload": action_payload,
    }


def _thesis_review_symbols(*, suggested_action: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for raw in (suggested_action.get("symbol"), evidence.get("symbol")):
        if raw:
            values.append(raw)
    for raw_list in (suggested_action.get("symbols"), evidence.get("symbols")):
        if isinstance(raw_list, list):
            values.extend(raw_list)
    return normalize_research_symbols(values, max_symbols=8)


def _resolve_thesis_review_reference_price(
    *,
    suggested_action: dict[str, Any],
    evidence: dict[str, Any],
    symbols: list[str],
) -> float | None:
    for key in (
        "current_price_usd",
        "current_price",
        "quote_price",
        "last_price",
        "reference_price_usd",
        "thesis_reference_price_usd",
    ):
        for source in (suggested_action, evidence):
            value = _coerce_optional_float(source.get(key))
            if value is not None and value > 0:
                return value
    if not symbols:
        return None
    with suppress(Exception):
        packet = research_service.evidence_packet(symbol=symbols[0], period="6mo", interval="1d")
        metrics = packet.metrics if isinstance(packet.metrics, dict) else {}
        value = _coerce_optional_float(metrics.get("last_price"))
        if value is not None and value > 0:
            return value
    return None


def refresh_research_thesis_review_from_recommendation(
    recommendation: dict[str, Any],
    *,
    plan_id: str | None,
    services: WorkspaceServices | None = None,
) -> dict[str, Any]:
    resolved_services = workspace_services_or_legacy(services)
    context = _thesis_review_action_context(recommendation)
    if context is None:
        return {}
    suggested_action = context["suggested_action"]
    evidence = context["evidence"]
    symbols = _thesis_review_symbols(suggested_action=suggested_action, evidence=evidence)
    reviewed_at_dt = utc_now()
    reviewed_at = reviewed_at_dt.isoformat()
    expires_at = (reviewed_at_dt + timedelta(days=TODAY_THESIS_REVIEW_DAYS)).isoformat()
    reference_price = _resolve_thesis_review_reference_price(
        suggested_action=suggested_action,
        evidence=evidence,
        symbols=symbols,
    )

    artifact_id = str(suggested_action.get("artifact_id") or evidence.get("artifact_id") or "").strip()
    resolved_plan_id = str(
        suggested_action.get("plan_id")
        or evidence.get("plan_id")
        or plan_id
        or recommendation.get("plan_id")
        or ""
    ).strip()
    if artifact_id and resolved_plan_id:
        artifact = resolved_services.plan_workspace.read_artifact(plan_id=resolved_plan_id, artifact_id=artifact_id)
        updated_content = _replace_thesis_review_metadata_section(
            str(artifact.get("content") or ""),
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_price,
        )
        updated_artifact = resolved_services.plan_workspace.update_artifact_content(
            plan_id=resolved_plan_id,
            artifact_id=artifact_id,
            markdown=updated_content,
        )
        return {
            "status": "refreshed",
            "target": "dossier",
            "artifact_id": updated_artifact.get("id") or artifact_id,
            "plan_id": resolved_plan_id,
            "symbols": symbols,
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "reference_price_usd": reference_price,
        }

    symbol = symbols[0] if symbols else ""
    if symbol:
        updated = resolved_services.portfolio_store.refresh_watchlist_thesis_review(
            symbol=symbol,
            data_source=str(suggested_action.get("data_source") or evidence.get("data_source") or "OPENBB"),
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_price,
        )
        return {
            "status": "refreshed",
            "target": "watchlist",
            "symbol": str(updated.get("symbol") or symbol),
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "reference_price_usd": reference_price,
        }

    return {
        "status": "skipped",
        "reason": "No dossier artifact or watchlist symbol was available for thesis review refresh.",
        "reviewed_at": reviewed_at,
    }


def apply_recommendation(
    recommendation_id: str,
    request: RecommendationApplyRequest,
    *,
    services: WorkspaceServices | None = None,
) -> RecommendationActionResponse:
    resolved_services = workspace_services_or_legacy(services)
    recommendation = resolved_services.recommendation_inbox.get(recommendation_id)
    current_status = str(recommendation.get("status", "proposed")).strip().lower()
    if current_status in {"applied", "rejected", "archived"}:
        raise ValueError(f"Recommendation status is '{current_status}' and cannot be applied.")

    recommendation_type = str(recommendation.get("recommendation_type", "general")).strip().lower()
    payload = recommendation.get("action_payload")
    action_payload = payload if isinstance(payload, dict) else {}
    plan_detail: PlanDetailResponse | None = None
    message = "Recommendation applied."

    if recommendation_type == "plan_settings_update":
        plan_id = _resolve_recommendation_plan_id(recommendation, request.plan_id)
        payload_updates = action_payload.get("plan_settings_updates")
        updates_from_payload = payload_updates if isinstance(payload_updates, dict) else {}
        merged_updates = dict(updates_from_payload)
        merged_updates.update(request.plan_settings_updates)
        if not merged_updates:
            raise ValueError(
                "No plan settings updates found. Provide plan_settings_updates in recommendation or request."
            )

        detail = resolved_services.plan_workspace.update_plan_settings(
            plan_id=plan_id,
            updates=merged_updates,
            rationale=request.rationale or recommendation.get("detail") or "Applied recommendation.",
            status=request.decision_status or "accepted",
            log_decision=True,
        )
        plan_detail = PlanDetailResponse(**detail)
        message = f"Applied plan settings recommendation to plan {plan_id}."
    else:
        plan_id = _resolve_recommendation_plan_id(recommendation, request.plan_id)
        summary = f"Applied recommendation: {recommendation.get('title', 'Recommendation')}"
        rationale = request.rationale or str(recommendation.get("detail") or "")
        resolved_services.plan_workspace.append_decision(
            plan_id=plan_id,
            summary=summary,
            rationale=rationale,
            status=request.decision_status or "accepted",
        )
        detail = resolved_services.plan_workspace.get_plan(plan_id)
        plan_detail = PlanDetailResponse(**detail)
        message = f"Logged recommendation application in plan {plan_id}."

    recommendation = resolved_services.recommendation_inbox.set_status(
        recommendation_id,
        status="applied",
        resolution_note=request.rationale.strip() if request.rationale else "",
    )
    suggested_symbols = _extract_decision_packet_symbols(recommendation, request_symbols=request.decision_packet_research_symbols)
    return RecommendationActionResponse(
        recommendation=_recommendation_item_from_row(recommendation),
        plan=plan_detail,
        suggested_research_symbols=suggested_symbols,
        message=message,
    )


async def reject_recommendation(
    recommendation_id: str,
    reason: str = "",
    *,
    plan_id: str | None = None,
    capture_scenario_diff: bool = True,
    create_decision_packet: bool = False,
    decision_packet_research_symbols: list[str] | None = None,
    services: WorkspaceServices | None = None,
) -> RecommendationActionResponse:
    resolved_services = workspace_services_or_legacy(services)
    recommendation = resolved_services.recommendation_inbox.get(recommendation_id)
    current_status = str(recommendation.get("status", "proposed")).strip().lower()
    if current_status in {"applied", "rejected"}:
        raise ValueError(f"Recommendation status is '{current_status}' and cannot be rejected.")

    scenario_diff_preview: dict[str, Any] | None = None
    if capture_scenario_diff:
        scenario_diff_preview = await build_recommendation_scenario_diff_preview(
            recommendation,
            requested_plan_id=plan_id,
        )

    updated = resolved_services.recommendation_inbox.set_status(
        recommendation_id,
        status="rejected",
        resolution_note=reason,
    )
    action_payload_raw = updated.get("action_payload")
    action_payload = dict(action_payload_raw) if isinstance(action_payload_raw, dict) else {}
    decision_closure_raw = action_payload.get("decision_closure")
    decision_closure = (
        dict(decision_closure_raw)
        if isinstance(decision_closure_raw, dict)
        else {}
    )
    decision_closure["rejected_at"] = context_utc_now_iso()
    decision_closure["decision_status"] = "rejected"
    decision_closure["reason"] = reason
    if scenario_diff_preview is not None:
        decision_closure["scenario_diff_preview"] = scenario_diff_preview
    expected_outcome_raw = decision_closure.get("expected_outcome")
    expected_outcome = (
        dict(expected_outcome_raw)
        if isinstance(expected_outcome_raw, dict)
        else _build_expected_outcome_from_preview(scenario_diff_preview)
    )
    decision_closure["expected_outcome"] = expected_outcome
    realized_outcome = (
        decision_closure.get("realized_outcome")
        if isinstance(decision_closure.get("realized_outcome"), dict)
        else {}
    )
    decision_closure["expected_vs_realized"] = _build_expected_vs_realized_metrics(
        expected_outcome=expected_outcome,
        realized_outcome=realized_outcome,
    )
    action_payload["decision_closure"] = decision_closure

    resolved_plan_id: str | None = None
    try:
        resolved_plan_id = _resolve_recommendation_plan_id(updated, plan_id)
    except ValueError:
        resolved_plan_id = None

    context_payload: dict[str, Any] | None = None
    context_error: str | None = None
    requested_symbols = normalize_research_symbols(decision_packet_research_symbols or [], max_symbols=12)
    if create_decision_packet and resolved_plan_id:
        try:
            context_payload = await build_buildwealth_context_payload(
                use_live_snapshot=False,
                plan_id=resolved_plan_id,
                include_research=True,
                include_plan_projection=False,
                force_refresh=False,
                research_symbols=requested_symbols,
                max_recommendations=10,
                max_plan_decisions=8,
                summary_max_chars=1800,
                research_symbol_limit=max(DEFAULT_RESEARCH_SYMBOL_LIMIT, len(requested_symbols) or 0),
                detail_level="light",
            )
        except Exception as exc:
            context_error = str(exc)

    suggested_symbols = _extract_decision_packet_symbols(
        updated,
        request_symbols=requested_symbols,
        context_payload=context_payload,
    )

    decision_packet_artifact: PlanArtifactSummary | None = None
    decision_packet_message_suffix = ""
    if create_decision_packet and resolved_plan_id:
        plan_detail_for_packet: PlanDetailResponse | None = None
        try:
            plan_detail_for_packet = PlanDetailResponse(**resolved_services.plan_workspace.get_plan(resolved_plan_id))
        except Exception:
            plan_detail_for_packet = None

        assumptions_payload = _build_decision_packet_assumptions(
            resolved_plan_id,
            plan_detail_for_packet,
            workspace=resolved_services.plan_workspace,
        )
        rationale = reason.strip() if reason.strip() else str(updated.get("detail") or "")
        markdown = _build_decision_packet_markdown(
            recommendation=updated,
            plan_id=resolved_plan_id,
            rationale=rationale,
            decision_status="rejected",
            cited_symbols=suggested_symbols,
            assumptions_payload=assumptions_payload,
            context_payload=context_payload,
            context_error=context_error,
        )
        try:
            artifact_payload = resolved_services.plan_workspace.write_artifact(
                plan_id=resolved_plan_id,
                title=f"Decision Packet - {updated.get('title') or recommendation_id} (Rejected)",
                markdown=markdown,
                kind="decision_packet",
            )
            decision_packet_artifact = PlanArtifactSummary(**artifact_payload)
            action_payload["decision_packet"] = {
                "artifact_id": decision_packet_artifact.id,
                "file_name": decision_packet_artifact.file_name,
                "plan_id": resolved_plan_id,
                "created_at": decision_packet_artifact.created_at.isoformat(),
                "decision_status": "rejected",
                "cited_research_symbols": suggested_symbols,
                "context_generated_at": context_payload.get("generated_at") if isinstance(context_payload, dict) else None,
                "assumption_set_id": assumptions_payload.get("active_assumption_set_id"),
            }
            decision_packet_message_suffix = " Decision packet saved to plan artifacts."
        except Exception as exc:
            decision_packet_message_suffix = f" Decision packet could not be written: {exc}"
    elif create_decision_packet and not resolved_plan_id:
        decision_packet_message_suffix = " Decision packet skipped: no plan_id is available."

    plan_detail: PlanDetailResponse | None = None
    closure_artifact_summary: PlanArtifactSummary | None = None
    closure_message_suffix = ""
    if resolved_plan_id:
        try:
            closure_artifact_summary = persist_recommendation_closure_to_plan(
                plan_id=resolved_plan_id,
                recommendation=updated,
                decision_closure=decision_closure,
                workspace=resolved_services.plan_workspace,
            )
            if closure_artifact_summary is not None:
                action_payload["decision_closure_artifact"] = {
                    "artifact_id": closure_artifact_summary.id,
                    "file_name": closure_artifact_summary.file_name,
                    "plan_id": resolved_plan_id,
                    "created_at": closure_artifact_summary.created_at.isoformat(),
                }
                plan_detail = PlanDetailResponse(**resolved_services.plan_workspace.get_plan(resolved_plan_id))
                closure_message_suffix = " Decision closure snapshot saved to plan artifacts."
        except (PlanNotFoundError, ValueError) as exc:
            closure_message_suffix = f" Decision closure snapshot could not be written: {exc}"

    if plan_detail is None and (decision_packet_artifact is not None) and resolved_plan_id:
        try:
            plan_detail = PlanDetailResponse(**resolved_services.plan_workspace.get_plan(resolved_plan_id))
        except Exception:
            plan_detail = None

    if suggested_symbols:
        action_payload["suggested_research_symbols"] = suggested_symbols
    updated = resolved_services.recommendation_inbox.update(
        recommendation_id,
        updates={"action_payload": action_payload},
    )

    decision_closure_payload = (
        action_payload.get("decision_closure")
        if isinstance(action_payload.get("decision_closure"), dict)
        else {}
    )
    return RecommendationActionResponse(
        recommendation=_recommendation_item_from_row(updated),
        plan=plan_detail,
        decision_packet_artifact=decision_packet_artifact,
        decision_closure_artifact=closure_artifact_summary,
        suggested_research_symbols=suggested_symbols,
        decision_closure=decision_closure_payload,
        message=f"Recommendation rejected.{decision_packet_message_suffix}{closure_message_suffix}",
    )


def _normalize_recommendation_closure_statuses(raw_statuses: list[str] | str | None) -> list[str]:
    valid = {"applied", "rejected"}
    normalized: list[str] = []
    if isinstance(raw_statuses, str):
        values = [item.strip().lower() for item in raw_statuses.split(",")]
    elif isinstance(raw_statuses, list):
        values = [str(item or "").strip().lower() for item in raw_statuses]
    else:
        values = []
    for value in values:
        if value in valid and value not in normalized:
            normalized.append(value)
    return normalized or ["applied", "rejected"]


RECOMMENDATION_CALIBRATION_MODEL_VERSION = "calibration_v1"


def _parse_utc_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _calibration_bias_from_gap(mean_gap: float | None) -> str:
    if mean_gap is None:
        return "unknown"
    if mean_gap > 25.0:
        return "underestimated"
    if mean_gap < -25.0:
        return "overestimated"
    return "neutral"


def _build_calibration_row(*, key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    with_expected_count = 0
    with_realized_count = 0
    pre_mortem_count = 0
    pre_mortem_realized_count = 0
    measured_count = 0
    pending_realized_count = 0
    direction_match_count = 0
    expected_future_total = 0.0
    realized_future_total = 0.0
    future_gap_total = 0.0
    future_abs_error_total = 0.0

    for row in rows:
        tracking_status = str(row.get("tracking_status") or "").strip().lower()
        if tracking_status == "pending_realized":
            pending_realized_count += 1

        expected_future = _coerce_optional_float(row.get("expected_delta_future_value_usd"))
        expected_real = _coerce_optional_float(row.get("expected_delta_real_value_usd"))
        realized_future = _coerce_optional_float(row.get("realized_delta_future_value_usd"))
        realized_real = _coerce_optional_float(row.get("realized_delta_real_value_usd"))
        has_expected = expected_future is not None or expected_real is not None
        has_realized = realized_future is not None or realized_real is not None
        if has_expected:
            with_expected_count += 1
        if has_realized:
            with_realized_count += 1
        if bool(row.get("has_pre_mortem")):
            pre_mortem_count += 1
            if has_realized:
                pre_mortem_realized_count += 1

        if expected_future is not None:
            expected_future_total += expected_future
        if realized_future is not None:
            realized_future_total += realized_future

        future_gap = _coerce_optional_float(row.get("future_value_gap_usd"))
        if future_gap is None:
            continue

        measured_count += 1
        future_gap_total += future_gap
        future_abs_error_total += abs(future_gap)

        future_direction_match = row.get("future_value_direction_match")
        if not isinstance(future_direction_match, bool):
            if expected_future is not None and realized_future is not None:
                future_direction_match = _same_direction(expected_future, realized_future)
            else:
                future_direction_match = None
        if bool(future_direction_match):
            direction_match_count += 1

    realized_coverage_pct = round((with_realized_count / count) * 100.0, 2) if count else 0.0
    mean_gap = round((future_gap_total / measured_count), 2) if measured_count else None
    mean_abs_error = round((future_abs_error_total / measured_count), 2) if measured_count else None
    direction_match_rate = round((direction_match_count / measured_count) * 100.0, 2) if measured_count else None

    return {
        "key": key,
        "count": count,
        "with_expected_count": with_expected_count,
        "with_realized_count": with_realized_count,
        "pre_mortem_count": pre_mortem_count,
        "pre_mortem_realized_count": pre_mortem_realized_count,
        "pre_mortem_pending_count": max(0, pre_mortem_count - pre_mortem_realized_count),
        "measured_count": measured_count,
        "pending_realized_count": pending_realized_count,
        "realized_coverage_pct": realized_coverage_pct,
        "future_value_direction_match_rate_pct": direction_match_rate,
        "mean_future_value_gap_usd": mean_gap,
        "mean_future_value_abs_error_usd": mean_abs_error,
        "future_value_bias": _calibration_bias_from_gap(mean_gap),
        "expected_future_value_total_usd": round(expected_future_total, 2),
        "realized_future_value_total_usd": round(realized_future_total, 2),
        "future_value_gap_total_usd": round(future_gap_total, 2),
        "future_value_abs_error_total_usd": round(future_abs_error_total, 2),
    }


def _build_segmented_calibration_rows(
    *,
    rows: list[dict[str, Any]],
    key_field: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(key_field) or "unknown").strip().lower() or "unknown"
        grouped.setdefault(key, []).append(row)

    summary_rows = [
        _build_calibration_row(key=key, rows=group_rows)
        for key, group_rows in grouped.items()
    ]
    summary_rows.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get("key") or "")))
    return summary_rows


def _build_calibration_windows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = utc_now()
    windows: list[tuple[str, int | None]] = [
        ("30d", 30),
        ("90d", 90),
        ("all", None),
    ]
    payload: list[dict[str, Any]] = []
    for window_label, days in windows:
        if days is None:
            window_rows = list(rows)
        else:
            cutoff = now - timedelta(days=days)
            window_rows = []
            for row in rows:
                resolved_at = _parse_utc_datetime(row.get("resolved_at") or row.get("updated_at"))
                if resolved_at is not None and resolved_at >= cutoff:
                    window_rows.append(row)
        summary = _build_calibration_row(key=window_label, rows=window_rows)
        summary["window"] = window_label
        summary["window_days"] = days
        payload.append(summary)
    return payload


INVESTMENT_RESEARCH_PROCESS_OUTCOMES = {
    "useful_review",
    "insufficient_evidence",
    "deferred",
    "acted_elsewhere",
    "not_useful",
}

INVESTMENT_RESEARCH_EVIDENCE_SUFFICIENCY = {
    "sufficient",
    "partial",
    "insufficient",
    "not_reviewed",
}


def _normalize_investment_process_outcome(value: Any) -> str | None:
    cleaned = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "useful": "useful_review",
        "helpful": "useful_review",
        "helpful_review": "useful_review",
        "evidence_insufficient": "insufficient_evidence",
        "not_enough_evidence": "insufficient_evidence",
        "acted_outside": "acted_elsewhere",
        "action_elsewhere": "acted_elsewhere",
        "unhelpful": "not_useful",
    }
    normalized = aliases.get(cleaned, cleaned)
    return normalized if normalized in INVESTMENT_RESEARCH_PROCESS_OUTCOMES else None


def _normalize_evidence_sufficiency(value: Any, *, process_outcome: str | None = None) -> str | None:
    cleaned = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "enough": "sufficient",
        "complete": "sufficient",
        "mixed": "partial",
        "incomplete": "partial",
        "not_enough": "insufficient",
        "missing": "insufficient",
        "none": "not_reviewed",
    }
    normalized = aliases.get(cleaned, cleaned)
    if normalized in INVESTMENT_RESEARCH_EVIDENCE_SUFFICIENCY:
        return normalized
    if process_outcome == "insufficient_evidence":
        return "insufficient"
    if process_outcome in {"useful_review", "acted_elsewhere"}:
        return "sufficient"
    return None


def _tracks_investment_process_calibration(recommendation: dict[str, Any], action_payload: dict[str, Any]) -> bool:
    source = str(recommendation.get("source") or "").strip().lower()
    if source in {INVESTMENT_RESEARCH_RECOMMENDATION_SOURCE, "generator:watchlist_research"}:
        return True
    quality = action_payload.get("quality") if isinstance(action_payload.get("quality"), dict) else {}
    calibration = quality.get("calibration") if isinstance(quality.get("calibration"), dict) else {}
    return str(calibration.get("domain") or "").strip().lower() == "investment_research"


def _build_decision_process_calibration(
    *,
    recommendation: dict[str, Any],
    action_payload: dict[str, Any],
    request: RecommendationOutcomeUpdateRequest,
) -> dict[str, Any] | None:
    if not _tracks_investment_process_calibration(recommendation, action_payload):
        return None
    process_outcome = _normalize_investment_process_outcome(request.process_outcome)
    if not process_outcome:
        return None

    evidence = action_payload.get("evidence") if isinstance(action_payload.get("evidence"), dict) else {}
    thesis_revision = (
        action_payload.get("thesis_revision")
        if isinstance(action_payload.get("thesis_revision"), dict)
        else {}
    )
    suggested_action = (
        action_payload.get("suggested_action")
        if isinstance(action_payload.get("suggested_action"), dict)
        else {}
    )
    evidence_sufficiency = _normalize_evidence_sufficiency(
        request.evidence_sufficiency,
        process_outcome=process_outcome,
    )
    payload = {
        "domain": "investment_research",
        "model_version": "investment_process_calibration_v1",
        "recorded_at": context_utc_now_iso(),
        "process_outcome": process_outcome,
        "evidence_sufficiency": evidence_sufficiency,
        "symbol": evidence.get("symbol") or suggested_action.get("symbol"),
        "research_evidence_packet_id": evidence.get("research_evidence_packet_id"),
        "fit_status": evidence.get("fit_status") or suggested_action.get("fit_status"),
        "suggested_action_kind": suggested_action.get("kind"),
        "measurement_source": str(request.measurement_source or "").strip() or None,
    }
    if thesis_revision:
        revision_reference = _compact_thesis_revision_reference(thesis_revision)
        if revision_reference:
            payload["thesis_revision"] = revision_reference
            payload["quality_effects"] = {
                "decision_clarity": (
                    "improved"
                    if process_outcome in {"useful_review", "acted_elsewhere"}
                    else "unclear"
                    if process_outcome == "deferred"
                    else "not_improved"
                ),
                "evidence_sufficiency": evidence_sufficiency,
                "blocking_gaps": (
                    "remaining"
                    if evidence_sufficiency in {"partial", "insufficient", "not_reviewed"}
                    else "not_blocking"
                ),
                "next_action": (
                    "clearer"
                    if process_outcome in {"useful_review", "acted_elsewhere"}
                    else "needs_review"
                ),
            }
    return {key: value for key, value in payload.items() if value is not None}


def _closure_for_outcome_prefill(
    recommendation: dict[str, Any],
    inbox: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve the decision closure to measure against.

    A due-outcome-review entry points at the original recommendation via
    evidence.source_recommendation_id; otherwise the closure lives on the
    recommendation itself.
    """
    payload = recommendation.get("action_payload") if isinstance(recommendation.get("action_payload"), dict) else {}
    closure = payload.get("decision_closure")
    if isinstance(closure, dict) and str(closure.get("applied_at") or "").strip():
        return closure, None
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    source_id = str(evidence.get("source_recommendation_id") or "").strip() or None
    if source_id:
        try:
            source = inbox.get(source_id)
        except Exception:
            return None, source_id
        source_payload = source.get("action_payload") if isinstance(source.get("action_payload"), dict) else {}
        source_closure = source_payload.get("decision_closure")
        if isinstance(source_closure, dict):
            return source_closure, source_id
    return None, source_id


def _expected_future_delta_for_prefill(closure: dict[str, Any]) -> float | None:
    expected = closure.get("expected_outcome")
    if isinstance(expected, dict):
        for key in ("delta_future_value_usd", "expected_delta_future_value_usd", "future_value_delta_usd"):
            value = expected.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    preview = closure.get("scenario_diff_preview")
    if isinstance(preview, dict):
        deltas = preview.get("scenario_deltas")
        if isinstance(deltas, list) and deltas and isinstance(deltas[0], dict):
            value = deltas[0].get("delta_future_value_usd")
            if isinstance(value, (int, float)):
                return float(value)
    return None


def build_recommendation_outcome_prefill_payload(
    recommendation_id: str,
    *,
    services: WorkspaceServices | None = None,
    now: datetime | None = None,
) -> RecommendationOutcomePrefillResponse:
    """Suggest measured outcome values from snapshot history.

    The suggestion is the observable portfolio-level change since the
    decision was applied — deliberately labeled with caveats, because a
    portfolio delta includes contributions and market moves, not only the
    decision's effect. The user confirms or edits; the app never pretends
    the attribution is exact.
    """
    resolved_services = workspace_services_or_legacy(services)
    resolved_now = now or datetime.now(timezone.utc)
    recommendation = resolved_services.recommendation_inbox.get(recommendation_id)

    def unavailable(detail: str, source_id: str | None = None) -> RecommendationOutcomePrefillResponse:
        return RecommendationOutcomePrefillResponse(
            recommendation_id=recommendation_id,
            source_recommendation_id=source_id,
            status="unavailable",
            detail=detail,
        )

    closure, source_id = _closure_for_outcome_prefill(recommendation, resolved_services.recommendation_inbox)
    if not isinstance(closure, dict):
        return unavailable("No applied decision closure found to measure against.", source_id)
    applied_at_text = str(closure.get("applied_at") or "").strip()
    try:
        applied_at = datetime.fromisoformat(applied_at_text.replace("Z", "+00:00"))
    except ValueError:
        return unavailable("The decision closure has no parseable applied_at date.", source_id)
    if applied_at.tzinfo is None:
        applied_at = applied_at.replace(tzinfo=timezone.utc)

    snapshots = resolved_services.snapshot_store.recent(limit=730)
    if len(snapshots) < 2:
        return unavailable("Not enough portfolio snapshots to measure a change.", source_id)

    def as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    current = snapshots[0]
    baseline = next((snap for snap in snapshots if as_utc(snap.as_of) <= applied_at), snapshots[-1])
    if as_utc(baseline.as_of) >= as_utc(current.as_of):
        return unavailable("No snapshot history spans the period since the decision.", source_id)

    warnings = [
        "Portfolio-level change includes contributions and market moves — attribute it to this decision with judgment.",
    ]
    baseline_gap_days = abs((as_utc(baseline.as_of) - applied_at).days)
    if baseline_gap_days > 7:
        warnings.append(
            f"Nearest baseline snapshot is {baseline_gap_days} days from the decision date; the measured change is approximate."
        )

    return RecommendationOutcomePrefillResponse(
        recommendation_id=recommendation_id,
        source_recommendation_id=source_id,
        status="ready",
        detail="Measured from portfolio snapshot history.",
        applied_at=applied_at,
        observation_window_days=max(0, (resolved_now - applied_at).days),
        baseline_snapshot_at=as_utc(baseline.as_of),
        baseline_value_usd=float(baseline.total_value_usd),
        current_snapshot_at=as_utc(current.as_of),
        current_value_usd=float(current.total_value_usd),
        suggested_future_value_delta_usd=round(float(current.total_value_usd) - float(baseline.total_value_usd), 2),
        expected_future_value_delta_usd=_expected_future_delta_for_prefill(closure),
        measurement_source="portfolio_sync",
        warnings=warnings,
    )


def update_recommendation_outcome(
    recommendation_id: str,
    request: RecommendationOutcomeUpdateRequest,
    *,
    services: WorkspaceServices | None = None,
) -> RecommendationActionResponse:
    resolved_services = workspace_services_or_legacy(services)
    recommendation = resolved_services.recommendation_inbox.get(recommendation_id)
    current_status = str(recommendation.get("status", "proposed")).strip().lower()
    if current_status not in {"applied", "rejected"}:
        raise ValueError("Only applied/rejected recommendations can record realized outcomes.")

    realized_future = _coerce_optional_float(request.realized_delta_future_value_usd)
    realized_real = _coerce_optional_float(request.realized_delta_real_value_usd)
    observed_at_value = request.observed_at.isoformat() if isinstance(request.observed_at, datetime) else None
    note = str(request.note or "").strip()
    measurement_source = str(request.measurement_source or "").strip()
    process_outcome = _normalize_investment_process_outcome(request.process_outcome)
    if (
        realized_future is None
        and realized_real is None
        and not observed_at_value
        and not note
        and not measurement_source
        and request.observation_window_days is None
        and not process_outcome
    ):
        raise ValueError("Provide at least one realized outcome field (delta, date, source, note, or window).")

    action_payload_raw = recommendation.get("action_payload")
    action_payload = dict(action_payload_raw) if isinstance(action_payload_raw, dict) else {}
    decision_closure_raw = action_payload.get("decision_closure")
    decision_closure = dict(decision_closure_raw) if isinstance(decision_closure_raw, dict) else {}
    if "decision_status" not in decision_closure:
        decision_closure["decision_status"] = current_status

    expected_outcome_raw = decision_closure.get("expected_outcome")
    expected_outcome = (
        dict(expected_outcome_raw)
        if isinstance(expected_outcome_raw, dict)
        else _build_expected_outcome_from_preview(
            decision_closure.get("scenario_diff_preview")
            if isinstance(decision_closure.get("scenario_diff_preview"), dict)
            else None
        )
    )
    decision_closure["expected_outcome"] = expected_outcome

    realized_outcome = {
        "recorded_at": context_utc_now_iso(),
        "observed_at": observed_at_value,
        "observation_window_days": request.observation_window_days,
        "measurement_source": measurement_source,
        "note": note,
        "realized_delta_future_value_usd": realized_future,
        "realized_delta_real_value_usd": realized_real,
    }
    decision_closure["realized_outcome"] = realized_outcome
    decision_closure["expected_vs_realized"] = _build_expected_vs_realized_metrics(
        expected_outcome=expected_outcome,
        realized_outcome=realized_outcome,
    )
    process_calibration = _build_decision_process_calibration(
        recommendation=recommendation,
        action_payload=action_payload,
        request=request,
    )
    if process_calibration is not None:
        decision_closure["decision_process_calibration"] = process_calibration
    action_payload["decision_closure"] = decision_closure

    resolved_plan_id = str(request.plan_id or "").strip() or str(recommendation.get("plan_id") or "").strip() or None
    if not resolved_plan_id:
        active_plan_id = resolved_services.plan_workspace.get_active_plan_id()
        resolved_plan_id = str(active_plan_id).strip() if active_plan_id else None

    closure_artifact_summary: PlanArtifactSummary | None = None
    closure_message_suffix = ""
    plan_detail: PlanDetailResponse | None = None
    if resolved_plan_id:
        try:
            closure_artifact_summary = persist_recommendation_closure_to_plan(
                plan_id=resolved_plan_id,
                recommendation=recommendation,
                decision_closure=decision_closure,
                workspace=resolved_services.plan_workspace,
            )
            if closure_artifact_summary is not None:
                action_payload["decision_closure_artifact"] = {
                    "artifact_id": closure_artifact_summary.id,
                    "file_name": closure_artifact_summary.file_name,
                    "plan_id": resolved_plan_id,
                    "created_at": closure_artifact_summary.created_at.isoformat(),
                }
                plan_detail = PlanDetailResponse(**resolved_services.plan_workspace.get_plan(resolved_plan_id))
                closure_message_suffix = " Outcome snapshot saved to plan artifacts."
        except (PlanNotFoundError, ValueError) as exc:
            closure_message_suffix = f" Outcome snapshot could not be written: {exc}"

    updated = resolved_services.recommendation_inbox.update(
        recommendation_id,
        updates={"action_payload": action_payload},
    )

    if plan_detail is None and resolved_plan_id:
        with suppress(Exception):
            plan_detail = PlanDetailResponse(**resolved_services.plan_workspace.get_plan(resolved_plan_id))

    return RecommendationActionResponse(
        recommendation=_recommendation_item_from_row(updated),
        plan=plan_detail,
        decision_closure_artifact=closure_artifact_summary,
        suggested_research_symbols=_extract_decision_packet_symbols(updated),
        decision_closure=decision_closure,
        message=f"Recommendation outcome recorded.{closure_message_suffix}",
    )


def build_recommendation_closure_analytics_payload(
    *,
    limit: int = 200,
    statuses: list[str] | str | None = None,
    include_pending_realized: bool = True,
    plan_id: str | None = None,
    inbox: RecommendationInbox | None = None,
) -> dict[str, Any]:
    status_filters = _normalize_recommendation_closure_statuses(statuses)
    resolved_plan_id = str(plan_id or "").strip() or None
    resolved_inbox = inbox or recommendation_inbox
    rows = resolved_inbox.list(
        limit=None,
        status=None,
        include_archived=True,
        sort="none",
    )
    closed_rows = [
        row
        for row in rows
        if str(row.get("status") or "").strip().lower() in set(status_filters)
    ]
    if resolved_plan_id is not None:
        closed_rows = [
            row
            for row in closed_rows
            if str(row.get("plan_id") or "").strip() == resolved_plan_id
        ]
    closed_rows.sort(
        key=lambda row: (
            str(row.get("resolved_at") or row.get("updated_at") or ""),
            str(row.get("id") or ""),
        ),
        reverse=True,
    )

    selected_rows: list[dict[str, Any]] = []
    max_rows = max(1, min(int(limit), 1000))
    for row in closed_rows:
        action_payload = row.get("action_payload")
        payload = action_payload if isinstance(action_payload, dict) else {}
        decision_closure = payload.get("decision_closure")
        closure = decision_closure if isinstance(decision_closure, dict) else {}
        expected_outcome = closure.get("expected_outcome") if isinstance(closure.get("expected_outcome"), dict) else {}
        realized_outcome = closure.get("realized_outcome") if isinstance(closure.get("realized_outcome"), dict) else {}
        expected_vs_realized = (
            closure.get("expected_vs_realized")
            if isinstance(closure.get("expected_vs_realized"), dict)
            else _build_expected_vs_realized_metrics(expected_outcome=expected_outcome, realized_outcome=realized_outcome)
        )
        pre_mortem = closure.get("pre_mortem") if isinstance(closure.get("pre_mortem"), dict) else {}
        process_calibration = (
            closure.get("decision_process_calibration")
            if isinstance(closure.get("decision_process_calibration"), dict)
            else {}
        )
        if (not include_pending_realized) and (str(expected_vs_realized.get("status") or "").strip().lower() != "measured"):
            continue

        expected_future = _coerce_optional_float(expected_outcome.get("expected_delta_future_value_usd"))
        expected_real = _coerce_optional_float(expected_outcome.get("expected_delta_real_value_usd"))
        realized_future = _coerce_optional_float(realized_outcome.get("realized_delta_future_value_usd"))
        realized_real = _coerce_optional_float(realized_outcome.get("realized_delta_real_value_usd"))
        selected_rows.append(
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "status": str(row.get("status") or "unknown"),
                "recommendation_type": str(row.get("recommendation_type") or "general"),
                "source": str(row.get("source") or "manual"),
                "plan_id": row.get("plan_id"),
                "resolved_at": row.get("resolved_at") or row.get("updated_at"),
                "expected_delta_future_value_usd": expected_future,
                "expected_delta_real_value_usd": expected_real,
                "realized_delta_future_value_usd": realized_future,
                "realized_delta_real_value_usd": realized_real,
                "future_value_gap_usd": _coerce_optional_float(expected_vs_realized.get("future_value_gap_usd")),
                "real_value_gap_usd": _coerce_optional_float(expected_vs_realized.get("real_value_gap_usd")),
                "future_value_direction_match": expected_vs_realized.get("future_value_direction_match"),
                "real_value_direction_match": expected_vs_realized.get("real_value_direction_match"),
                "tracking_status": expected_vs_realized.get("status"),
                "has_pre_mortem": bool(pre_mortem),
                "pre_mortem_main_risk": pre_mortem.get("main_risk"),
                "pre_mortem_disconfirming_signal": pre_mortem.get("disconfirming_signal"),
                "pre_mortem_review_date": pre_mortem.get("review_date"),
                "observation_window_days": realized_outcome.get("observation_window_days"),
                "measurement_source": realized_outcome.get("measurement_source"),
                "process_outcome": process_calibration.get("process_outcome"),
                "evidence_sufficiency": process_calibration.get("evidence_sufficiency"),
                "process_calibration_domain": process_calibration.get("domain"),
                "process_calibration_model_version": process_calibration.get("model_version"),
                "symbol": process_calibration.get("symbol"),
                "research_evidence_packet_id": process_calibration.get("research_evidence_packet_id"),
                "thesis_revision_event_id": (
                    process_calibration.get("thesis_revision", {}).get("event_id")
                    if isinstance(process_calibration.get("thesis_revision"), dict)
                    else None
                ),
                "thesis_revision_target_type": (
                    process_calibration.get("thesis_revision", {}).get("target_type")
                    if isinstance(process_calibration.get("thesis_revision"), dict)
                    else None
                ),
            }
        )
        if len(selected_rows) >= max_rows:
            break

    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    with_expected_count = 0
    with_realized_count = 0
    pre_mortem_count = 0
    pre_mortem_realized_count = 0
    measured_count = 0
    direction_match_count = 0
    process_counts: dict[str, int] = {}
    evidence_sufficiency_counts: dict[str, int] = {}
    process_count = 0
    useful_process_count = 0
    weak_process_count = 0
    thesis_revision_count = 0
    useful_thesis_revision_count = 0
    expected_future_total = 0.0
    realized_future_total = 0.0
    future_gap_total = 0.0
    future_abs_error_total = 0.0

    for row in selected_rows:
        status_key = str(row.get("status") or "unknown").strip().lower() or "unknown"
        type_key = str(row.get("recommendation_type") or "general").strip().lower() or "general"
        source_key = str(row.get("source") or "manual").strip().lower() or "manual"
        status_counts[status_key] = status_counts.get(status_key, 0) + 1
        type_counts[type_key] = type_counts.get(type_key, 0) + 1
        source_counts[source_key] = source_counts.get(source_key, 0) + 1

        expected_future = _coerce_optional_float(row.get("expected_delta_future_value_usd"))
        expected_real = _coerce_optional_float(row.get("expected_delta_real_value_usd"))
        realized_future = _coerce_optional_float(row.get("realized_delta_future_value_usd"))
        realized_real = _coerce_optional_float(row.get("realized_delta_real_value_usd"))
        has_expected = expected_future is not None or expected_real is not None
        has_realized = realized_future is not None or realized_real is not None
        if has_expected:
            with_expected_count += 1
        if has_realized:
            with_realized_count += 1
        if bool(row.get("has_pre_mortem")):
            pre_mortem_count += 1
            if has_realized:
                pre_mortem_realized_count += 1

        if expected_future is not None:
            expected_future_total += expected_future
        if realized_future is not None:
            realized_future_total += realized_future

        future_gap = _coerce_optional_float(row.get("future_value_gap_usd"))
        if future_gap is not None:
            measured_count += 1
            future_gap_total += future_gap
            future_abs_error_total += abs(future_gap)
            if bool(row.get("future_value_direction_match")):
                direction_match_count += 1

        process_outcome = str(row.get("process_outcome") or "").strip().lower()
        if process_outcome:
            process_count += 1
            process_counts[process_outcome] = process_counts.get(process_outcome, 0) + 1
            if process_outcome in {"useful_review", "acted_elsewhere"}:
                useful_process_count += 1
            elif process_outcome in {"insufficient_evidence", "not_useful"}:
                weak_process_count += 1
            if row.get("thesis_revision_event_id"):
                thesis_revision_count += 1
                if process_outcome in {"useful_review", "acted_elsewhere"}:
                    useful_thesis_revision_count += 1
        evidence_sufficiency = str(row.get("evidence_sufficiency") or "").strip().lower()
        if evidence_sufficiency:
            evidence_sufficiency_counts[evidence_sufficiency] = evidence_sufficiency_counts.get(evidence_sufficiency, 0) + 1

    count = len(selected_rows)
    coverage_pct = round((with_realized_count / count) * 100.0, 2) if count else 0.0
    direction_match_rate_pct = round((direction_match_count / measured_count) * 100.0, 2) if measured_count else None
    mean_abs_error = round((future_abs_error_total / measured_count), 2) if measured_count else None
    process_useful_rate_pct = round((useful_process_count / process_count) * 100.0, 2) if process_count else None
    pre_mortem_coverage_pct = round((pre_mortem_count / count) * 100.0, 2) if count else 0.0
    pre_mortem_realized_coverage_pct = (
        round((pre_mortem_realized_count / pre_mortem_count) * 100.0, 2)
        if pre_mortem_count
        else 0.0
    )
    calibration_summary = _build_calibration_row(key="all", rows=selected_rows)
    calibration_by_type = _build_segmented_calibration_rows(
        rows=selected_rows,
        key_field="recommendation_type",
    )
    calibration_by_source = _build_segmented_calibration_rows(
        rows=selected_rows,
        key_field="source",
    )
    calibration_windows = _build_calibration_windows(selected_rows)

    def _counter_to_rows(counter: dict[str, int]) -> list[dict[str, Any]]:
        return [
            {"key": key, "count": value}
            for key, value in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
        ]

    return {
        "generated_at": context_utc_now_iso(),
        "count": count,
        "plan_id": resolved_plan_id,
        "statuses": status_filters,
        "include_pending_realized": include_pending_realized,
        "calibration_model_version": RECOMMENDATION_CALIBRATION_MODEL_VERSION,
        "calibration_summary": calibration_summary,
        "calibration_by_type": calibration_by_type,
        "calibration_by_source": calibration_by_source,
        "calibration_windows": calibration_windows,
        "process_calibration_summary": {
            "count": process_count,
            "useful_count": useful_process_count,
            "weak_count": weak_process_count,
            "useful_rate_pct": process_useful_rate_pct,
            "thesis_revision_count": thesis_revision_count,
            "useful_thesis_revision_count": useful_thesis_revision_count,
        },
        "pre_mortem_summary": {
            "count": pre_mortem_count,
            "realized_count": pre_mortem_realized_count,
            "pending_count": max(0, pre_mortem_count - pre_mortem_realized_count),
            "coverage_pct": pre_mortem_coverage_pct,
            "realized_coverage_pct": pre_mortem_realized_coverage_pct,
        },
        "process_calibration_by_outcome": _counter_to_rows(process_counts),
        "process_calibration_by_evidence_sufficiency": _counter_to_rows(evidence_sufficiency_counts),
        "summary": {
            "closed_count": count,
            "with_expected_count": with_expected_count,
            "with_realized_count": with_realized_count,
            "pre_mortem_count": pre_mortem_count,
            "pre_mortem_realized_count": pre_mortem_realized_count,
            "pre_mortem_pending_count": max(0, pre_mortem_count - pre_mortem_realized_count),
            "measured_count": measured_count,
            "pending_realized_count": max(0, with_expected_count - measured_count),
            "realized_coverage_pct": coverage_pct,
            "expected_future_value_total_usd": round(expected_future_total, 2),
            "realized_future_value_total_usd": round(realized_future_total, 2),
            "future_value_gap_total_usd": round(future_gap_total, 2),
            "future_value_abs_error_total_usd": round(future_abs_error_total, 2),
            "mean_future_value_abs_error_usd": mean_abs_error,
            "future_value_direction_match_rate_pct": direction_match_rate_pct,
        },
        "by_status": _counter_to_rows(status_counts),
        "by_type": _counter_to_rows(type_counts),
        "by_source": _counter_to_rows(source_counts),
        "items": selected_rows,
    }


def _format_percent(value: Any) -> str:
    parsed = _coerce_optional_float(value)
    if parsed is None:
        return "n/a"
    return f"{parsed:.2f}%"


def _build_plan_recommendation_closure_markdown(
    *,
    plan_detail: dict[str, Any],
    analytics_payload: dict[str, Any],
) -> str:
    plan_id = str(plan_detail.get("id") or "").strip()
    plan_title = str(plan_detail.get("title") or "Untitled Plan").strip() or "Untitled Plan"
    summary = analytics_payload.get("summary") if isinstance(analytics_payload.get("summary"), dict) else {}
    calibration_summary = (
        analytics_payload.get("calibration_summary")
        if isinstance(analytics_payload.get("calibration_summary"), dict)
        else {}
    )
    calibration_by_type = (
        analytics_payload.get("calibration_by_type")
        if isinstance(analytics_payload.get("calibration_by_type"), list)
        else []
    )
    calibration_by_source = (
        analytics_payload.get("calibration_by_source")
        if isinstance(analytics_payload.get("calibration_by_source"), list)
        else []
    )
    calibration_windows = (
        analytics_payload.get("calibration_windows")
        if isinstance(analytics_payload.get("calibration_windows"), list)
        else []
    )
    items = analytics_payload.get("items") if isinstance(analytics_payload.get("items"), list) else []
    measured_items = [
        item
        for item in items
        if isinstance(item, dict) and _coerce_optional_float(item.get("future_value_gap_usd")) is not None
    ]
    measured_items.sort(
        key=lambda item: abs(_coerce_optional_float(item.get("future_value_gap_usd")) or 0.0),
        reverse=True,
    )

    lines = [
        f"# Recommendation Closure Analytics - {plan_title}",
        "",
        f"- Plan ID: `{plan_id}`",
        f"- Generated At: `{analytics_payload.get('generated_at')}`",
        f"- Statuses: `{', '.join(analytics_payload.get('statuses') or []) or 'n/a'}`",
        f"- Closed Count: `{summary.get('closed_count', 0)}`",
        f"- Measured Count: `{summary.get('measured_count', 0)}`",
        f"- Realized Coverage: `{_format_percent(summary.get('realized_coverage_pct'))}`",
        f"- Direction Match Rate: `{_format_percent(summary.get('future_value_direction_match_rate_pct'))}`",
        f"- Mean Absolute Error (Future Value): `{_format_currency_amount(summary.get('mean_future_value_abs_error_usd'))}`",
        f"- Calibration Bias: `{calibration_summary.get('future_value_bias') or 'unknown'}`",
        "",
        "## Calibration by Type",
        "",
        "| Type | Count | Measured | Pending | Match Rate | Mean Abs Error |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    if calibration_by_type:
        for row in calibration_by_type[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| `{row.get('key')}` | {int(row.get('count') or 0)} | {int(row.get('measured_count') or 0)} | "
                f"{int(row.get('pending_realized_count') or 0)} | {_format_percent(row.get('future_value_direction_match_rate_pct'))} | "
                f"{_format_currency_amount(row.get('mean_future_value_abs_error_usd'))} |"
            )
    else:
        lines.append("| `n/a` | 0 | 0 | 0 | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Calibration by Source",
            "",
            "| Source | Count | Measured | Pending | Match Rate | Mean Abs Error |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if calibration_by_source:
        for row in calibration_by_source[:8]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| `{row.get('key')}` | {int(row.get('count') or 0)} | {int(row.get('measured_count') or 0)} | "
                f"{int(row.get('pending_realized_count') or 0)} | {_format_percent(row.get('future_value_direction_match_rate_pct'))} | "
                f"{_format_currency_amount(row.get('mean_future_value_abs_error_usd'))} |"
            )
    else:
        lines.append("| `n/a` | 0 | 0 | 0 | n/a | n/a |")

    lines.extend(
        [
            "",
            "## Calibration Windows",
            "",
            "| Window | Count | Measured | Match Rate | Mean Abs Error |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    if calibration_windows:
        for row in calibration_windows[:6]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"| `{row.get('window') or row.get('key')}` | {int(row.get('count') or 0)} | "
                f"{int(row.get('measured_count') or 0)} | {_format_percent(row.get('future_value_direction_match_rate_pct'))} | "
                f"{_format_currency_amount(row.get('mean_future_value_abs_error_usd'))} |"
            )
    else:
        lines.append("| `n/a` | 0 | 0 | n/a | n/a |")

    lines.extend(["", "## Largest Measured Future-Value Gaps", ""])
    if measured_items:
        for item in measured_items[:10]:
            lines.append(
                f"- `{item.get('id')}` {item.get('title')}: "
                f"gap {_format_currency_amount(item.get('future_value_gap_usd'))}, "
                f"expected {_format_currency_amount(item.get('expected_delta_future_value_usd'))}, "
                f"realized {_format_currency_amount(item.get('realized_delta_future_value_usd'))}, "
                f"type `{item.get('recommendation_type')}`, source `{item.get('source')}`."
            )
    else:
        lines.append("- No measured future-value gaps yet.")

    return "\n".join(lines)


def create_plan_recommendation_closure_summary(
    *,
    plan_id: str,
    request: PlanRecommendationClosureSummaryRequest,
    services: WorkspaceServices | None = None,
) -> PlanRecommendationClosureSummaryResponse:
    resolved_services = workspace_services_or_legacy(services)
    plan_detail = resolved_services.plan_workspace.get_plan(plan_id)
    analytics_payload = build_recommendation_closure_analytics_payload(
        limit=request.limit,
        statuses=request.statuses,
        include_pending_realized=request.include_pending_realized,
        plan_id=plan_id,
        inbox=resolved_services.recommendation_inbox,
    )
    analytics = RecommendationClosureAnalyticsResponse(**analytics_payload)

    decision_summary = (
        "Generated recommendation closure analytics summary "
        f"({analytics.summary.get('closed_count', 0)} closed, {analytics.summary.get('measured_count', 0)} measured)."
    )

    artifact_summary: PlanArtifactSummary | None = None
    if request.write_artifact:
        markdown = _build_plan_recommendation_closure_markdown(
            plan_detail=plan_detail,
            analytics_payload=analytics_payload,
        )
        artifact_payload = resolved_services.plan_workspace.write_artifact(
            plan_id=plan_id,
            title=f"Recommendation Closure Analytics ({utc_now().date().isoformat()})",
            markdown=markdown,
            kind="recommendation_closure_analytics",
        )
        artifact_summary = PlanArtifactSummary(**artifact_payload)
        resolved_services.plan_workspace.append_decision(
            plan_id=plan_id,
            summary=decision_summary,
            rationale=(
                "Captured closure calibration metrics by type/source and trend windows "
                "for longitudinal decision-review workflows."
            ),
            status="accepted",
        )

    return PlanRecommendationClosureSummaryResponse(
        plan_id=plan_id,
        analytics=analytics,
        artifact=artifact_summary,
        decision_summary=decision_summary,
    )


def archive_recommendation(
    recommendation_id: str,
    note: str = "",
    *,
    services: WorkspaceServices | None = None,
) -> RecommendationActionResponse:
    resolved_services = workspace_services_or_legacy(services)
    recommendation = resolved_services.recommendation_inbox.set_status(
        recommendation_id,
        status="archived",
        resolution_note=note,
    )
    return RecommendationActionResponse(
        recommendation=_recommendation_item_from_row(recommendation),
        plan=None,
        message="Recommendation archived.",
    )


def _plan_settings_completion_percent(active_plan_detail: dict[str, Any] | None) -> float:
    if not active_plan_detail:
        return 0.0

    settings_payload = active_plan_detail.get("settings")
    if not isinstance(settings_payload, dict):
        return 0.0

    set_count = 0
    for key in PLAN_SETTINGS_FIELDS:
        if settings_payload.get(key) is not None:
            set_count += 1

    return round((set_count / len(PLAN_SETTINGS_FIELDS)) * 100, 1)


def _build_profile_readiness_summary(
    *,
    income_items: list[Any],
    expense_items: list[Any],
    debt_items: list[Any],
    goal_items: list[Any],
    physical_assets: list[Any],
    flags: dict[str, Any],
    tax_profile: dict[str, Any],
    investment_policy: dict[str, Any],
    profile_metadata: dict[str, Any] | None = None,
) -> ProfileReadinessSummary:
    metadata_payload = {
        "tax_profile": tax_profile,
        "investment_policy": investment_policy,
        "profile_metadata": profile_metadata or {},
    }
    filing_status = str(tax_profile.get("filing_status") or "").strip()
    marginal_tax_rate = tax_profile.get("marginal_tax_rate")
    tax_review_fields = profile_metadata_review_field_paths(
        metadata_payload,
        prefixes=("tax_profile.",),
    )
    policy_review_fields = profile_metadata_review_field_paths(
        metadata_payload,
        prefixes=("investment_policy.",),
    )
    single_symbol_cap = investment_policy.get("max_single_symbol_exposure_pct")
    single_symbol_cap_value: float | None
    try:
        single_symbol_cap_value = float(single_symbol_cap)
    except (TypeError, ValueError):
        single_symbol_cap_value = None
    policy_complete = single_symbol_cap_value is not None

    sections = [
        ProfileReadinessSection(
            key="income",
            title="Income profile",
            status="complete" if len(income_items) > 0 else "incomplete",
            detail=f"{len(income_items)} income item(s) configured.",
            required_for=["cash_flow", "planning", "affordability"],
            blocking_recommendations=len(income_items) == 0,
        ),
        ProfileReadinessSection(
            key="expenses",
            title="Expense profile",
            status="complete" if len(expense_items) > 0 else "incomplete",
            detail=f"{len(expense_items)} expense item(s) configured.",
            required_for=["cash_flow", "liquidity", "affordability"],
            blocking_recommendations=len(expense_items) == 0,
        ),
        ProfileReadinessSection(
            key="debt",
            title="Debt profile",
            status="complete" if len(debt_items) > 0 or bool(flags.get("no_debt")) else "attention",
            detail=(
                f"{len(debt_items)} debt item(s) configured."
                if len(debt_items) > 0
                else "Marked as no current debt."
                if bool(flags.get("no_debt"))
                else "Add debt balances or mark that you currently have no debt."
            ),
            required_for=["cash_flow", "liquidity", "affordability"],
            blocking_recommendations=len(debt_items) == 0 and not bool(flags.get("no_debt")),
        ),
        ProfileReadinessSection(
            key="goals",
            title="Goals profile",
            status="complete" if len(goal_items) > 0 or bool(flags.get("no_goals")) else "attention",
            detail=(
                f"{len(goal_items)} goal item(s) configured."
                if len(goal_items) > 0
                else "Goals deferred for now."
                if bool(flags.get("no_goals"))
                else "Add at least one financial goal or mark goals as deferred."
            ),
            required_for=["planning", "investment_fit", "recommendation_ranking"],
            blocking_recommendations=len(goal_items) == 0 and not bool(flags.get("no_goals")),
        ),
        ProfileReadinessSection(
            key="tax_profile",
            title="Tax profile",
            status=(
                "attention"
                if filing_status and marginal_tax_rate is not None and tax_review_fields
                else "complete"
                if filing_status and marginal_tax_rate is not None
                else "incomplete"
            ),
            detail=(
                "Review tax profile fields before relying on tax-sensitive advice."
                if filing_status and marginal_tax_rate is not None and tax_review_fields
                else (
                    "Filing status and marginal tax rate are configured."
                    if filing_status and marginal_tax_rate is not None
                    else "Set filing status and marginal tax rate."
                )
            ),
            required_for=["tax_planning", "investment_fit", "withdrawal_strategy"],
            blocking_recommendations=not (filing_status and marginal_tax_rate is not None) or bool(tax_review_fields),
        ),
        ProfileReadinessSection(
            key="investment_policy",
            title="Investment policy",
            status="attention" if policy_review_fields else "complete" if policy_complete else "attention",
            detail=(
                "Review investment policy fields before relying on investment-fit advice."
                if policy_review_fields
                else (
                    f"Single-symbol exposure cap is {single_symbol_cap_value:g}%."
                    if policy_complete
                    else "Set personal investment guardrails such as max single-symbol exposure."
                )
            ),
            required_for=["investment_fit", "recommendation_ranking", "research_review"],
            blocking_recommendations=bool(policy_review_fields),
        ),
        ProfileReadinessSection(
            key="physical_assets",
            title="Physical assets",
            status="complete" if physical_assets else "attention",
            detail=(
                f"{len(physical_assets)} physical asset(s) configured."
                if physical_assets
                else "Add physical assets if they matter to net worth or planning."
            ),
            required_for=["net_worth", "planning"],
            blocking_recommendations=False,
        ),
    ]

    required_sections = [section for section in sections if section.blocking_recommendations]
    complete_count = sum(1 for section in sections if section.status == "complete")
    completion_percent = round((complete_count / len(sections)) * 100, 1) if sections else 0.0
    next_gap = next((section for section in sections if section.blocking_recommendations), None)
    blocking_sources: list[str] = []
    if any(section.blocking_recommendations for section in sections):
        blocking_sources.append("profile_completeness")
    if any(section.key == "tax_profile" and section.blocking_recommendations for section in sections):
        blocking_sources.append("tax_planning")
    if any(section.key in {"income", "expenses", "debt"} and section.blocking_recommendations for section in sections):
        blocking_sources.append("cash_liquidity")
    if any(section.key == "goals" and section.blocking_recommendations for section in sections):
        blocking_sources.append("investment_fit")
    if any(section.key == "investment_policy" and section.blocking_recommendations for section in sections):
        blocking_sources.append("investment_fit")

    if not required_sections:
        status = "ready"
    elif any(section.status == "incomplete" for section in required_sections):
        status = "incomplete"
    else:
        status = "attention"

    return ProfileReadinessSummary(
        completion_percent=completion_percent,
        status=status,
        next_gap_key=next_gap.key if next_gap else None,
        next_gap_title=next_gap.title if next_gap else None,
        next_gap_detail=next_gap.detail if next_gap else None,
        blocking_recommendation_sources=blocking_sources,
        sections=sections,
    )


def build_onboarding_status_response(
    profile_payload: dict[str, Any] | None = None,
    latest_snapshot: PortfolioSnapshot | None = None,
    active_plan_detail: dict[str, Any] | None = None,
    load_fallbacks: bool = True,
) -> OnboardingStatusResponse:
    profile = profile_payload or get_financial_profile_payload()
    flags = profile.get("flags") if isinstance(profile.get("flags"), dict) else {}
    tax_profile = profile.get("tax_profile") if isinstance(profile.get("tax_profile"), dict) else {}
    investment_policy = (
        profile.get("investment_policy")
        if isinstance(profile.get("investment_policy"), dict)
        else {}
    )
    profile_metadata = profile.get("profile_metadata") if isinstance(profile.get("profile_metadata"), dict) else {}

    if latest_snapshot is None and load_fallbacks:
        try:
            latest_snapshot = snapshot_store.latest()
        except FileNotFoundError:
            latest_snapshot = None

    if active_plan_detail is None and load_fallbacks:
        active_plan_detail = resolve_active_plan_detail()

    steps = []

    if latest_snapshot is None:
        steps.append(
            {
                "id": "snapshot",
                "title": "Portfolio data connected",
                "status": "incomplete",
                "detail": "Run first sync to load portfolio context.",
            }
        )
    else:
        age_minutes = int((utc_now() - latest_snapshot.as_of).total_seconds() // 60)
        if age_minutes > 24 * 60:
            status = "attention"
            detail = f"Snapshot is {age_minutes // 60}h old."
        else:
            status = "complete"
            detail = "Snapshot is fresh."
        steps.append(
            {
                "id": "snapshot",
                "title": "Portfolio data connected",
                "status": status,
                "detail": detail,
            }
        )

    income_items = profile.get("income_items") if isinstance(profile.get("income_items"), list) else []
    expense_items = profile.get("expense_items") if isinstance(profile.get("expense_items"), list) else []
    debt_items = profile.get("debt_items") if isinstance(profile.get("debt_items"), list) else []
    goal_items = profile.get("goal_items") if isinstance(profile.get("goal_items"), list) else []
    physical_assets = profile.get("physical_assets") if isinstance(profile.get("physical_assets"), list) else []
    profile_readiness = _build_profile_readiness_summary(
        income_items=income_items,
        expense_items=expense_items,
        debt_items=debt_items,
        goal_items=goal_items,
        physical_assets=physical_assets,
        flags=flags,
        tax_profile=tax_profile,
        investment_policy=investment_policy,
        profile_metadata=profile_metadata,
    )

    steps.append(
        {
            "id": "income",
            "title": "Income profile",
            "status": "complete" if len(income_items) > 0 else "incomplete",
            "detail": f"{len(income_items)} income item(s) configured.",
        }
    )
    steps.append(
        {
            "id": "expenses",
            "title": "Expense profile",
            "status": "complete" if len(expense_items) > 0 else "incomplete",
            "detail": f"{len(expense_items)} expense item(s) configured.",
        }
    )

    if len(debt_items) > 0 or bool(flags.get("no_debt")):
        debt_status = "complete"
        debt_detail = (
            f"{len(debt_items)} debt item(s) configured."
            if len(debt_items) > 0
            else "Marked as no current debt."
        )
    else:
        debt_status = "attention"
        debt_detail = "Add debt balances or mark that you currently have no debt."
    steps.append(
        {
            "id": "debt",
            "title": "Debt profile",
            "status": debt_status,
            "detail": debt_detail,
        }
    )

    if len(goal_items) > 0 or bool(flags.get("no_goals")):
        goal_status = "complete"
        goal_detail = (
            f"{len(goal_items)} goal item(s) configured."
            if len(goal_items) > 0
            else "Goals deferred for now."
        )
    else:
        goal_status = "attention"
        goal_detail = "Add at least one financial goal or mark goals as deferred."
    steps.append(
        {
            "id": "goals",
            "title": "Goals profile",
            "status": goal_status,
            "detail": goal_detail,
        }
    )

    filing_status = str(tax_profile.get("filing_status") or "").strip()
    marginal_tax_rate = tax_profile.get("marginal_tax_rate")
    tax_complete = bool(filing_status) and marginal_tax_rate is not None
    steps.append(
        {
            "id": "tax_profile",
            "title": "Tax profile",
            "status": "complete" if tax_complete else "incomplete",
            "detail": "Filing status and marginal tax rate are configured."
            if tax_complete
            else "Set filing status and marginal tax rate.",
        }
    )

    plan_exists = active_plan_detail is not None
    settings_completion = _plan_settings_completion_percent(active_plan_detail)
    steps.append(
        {
            "id": "active_plan",
            "title": "Active plan",
            "status": "complete" if plan_exists else "incomplete",
            "detail": "Active plan selected." if plan_exists else "Create or activate a plan.",
        }
    )
    if not plan_exists:
        steps.append(
            {
                "id": "plan_assumptions",
                "title": "Plan assumptions",
                "status": "incomplete",
                "detail": "No active plan assumptions available.",
            }
        )
    elif settings_completion >= 57:
        steps.append(
            {
                "id": "plan_assumptions",
                "title": "Plan assumptions",
                "status": "complete",
                "detail": f"Settings completion is {settings_completion:.1f}%.",
            }
        )
    else:
        steps.append(
            {
                "id": "plan_assumptions",
                "title": "Plan assumptions",
                "status": "attention",
                "detail": f"Settings completion is {settings_completion:.1f}%. Fill missing assumptions.",
            }
        )

    complete_count = sum(1 for item in steps if item["status"] == "complete")
    completion_percent = round((complete_count / len(steps)) * 100, 1) if steps else 0.0
    ready_for_daily_review = all(item["status"] == "complete" for item in steps)

    return OnboardingStatusResponse(
        completion_percent=completion_percent,
        ready_for_daily_review=ready_for_daily_review,
        steps=steps,
        profile_readiness=profile_readiness,
    )


def build_today_dashboard_response(
    services: WorkspaceServices | None = None,
) -> TodayDashboardResponse:
    resolved_services = workspace_services_or_legacy(services)
    latest_snapshot = None
    try:
        latest_snapshot = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        latest_snapshot = None

    history = build_snapshot_history_payload(limit=30, store=resolved_services.snapshot_store)
    sync_status = get_sync_status()
    active_plan_detail = resolve_active_plan_detail(workspace=resolved_services.plan_workspace)
    profile_payload = get_financial_profile_payload(resolved_services.financial_profile_store)
    onboarding_status = build_onboarding_status_response(
        profile_payload=profile_payload,
        latest_snapshot=latest_snapshot,
        active_plan_detail=active_plan_detail,
        load_fallbacks=False,
    )
    inbox_open_count, inbox_high_priority_count = _build_recommendation_open_counts(
        resolved_services.recommendation_inbox,
    )
    last_review_checkpoint = resolved_services.today_review_checkpoint_store.latest()

    dashboard = build_today_dashboard_payload(
        now=utc_now(),
        currency=settings.app_currency,
        state=settings.app_state,
        sync_status=sync_status,
        latest_snapshot=latest_snapshot,
        snapshot_history=history,
        active_plan_detail=active_plan_detail,
        onboarding_completion_percent=onboarding_status.completion_percent,
        onboarding_ready_for_daily_review=onboarding_status.ready_for_daily_review,
        profile_readiness=onboarding_status.profile_readiness,
        inbox_open_count=inbox_open_count,
        inbox_high_priority_count=inbox_high_priority_count,
        last_review_checkpoint=last_review_checkpoint,
    )

    # Enrich with financial health summary
    try:
        from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem

        health = compute_financial_health(
            income_items=[IncomeItem(**i) for i in profile_payload.get("income_items", [])],
            expense_items=[ExpenseItem(**e) for e in profile_payload.get("expense_items", [])],
            debt_items=[DebtItem(**d) for d in profile_payload.get("debt_items", [])],
            goal_items=[GoalItem(**g) for g in profile_payload.get("goal_items", [])],
            physical_assets=[PhysicalAssetItem(**a) for a in profile_payload.get("physical_assets", [])],
            snapshot=latest_snapshot,
        )
        dashboard.net_worth_usd = health.net_worth_usd
        dashboard.monthly_surplus_usd = health.monthly_surplus_usd
        dashboard.savings_rate_pct = health.savings_rate_pct
        dashboard.emergency_fund_months = health.emergency_fund_months
        dashboard.financial_health_status = health.status
    except Exception:
        pass

    top_next_actions = _build_top_next_actions(
        plan_id=(dashboard.active_plan.id if dashboard.active_plan is not None else None),
        limit=3,
        inbox=resolved_services.recommendation_inbox,
    )
    if top_next_actions:
        dashboard.top_next_actions = top_next_actions
    else:
        dashboard.top_next_actions = [
            TopNextAction(
                recommendation_id=item.id,
                title=item.title,
                detail=item.detail,
                priority=item.priority,
                recommendation_type="general",
                source="today-dashboard-heuristic",
                action_hint="Use Today workflow or Recommendation Inbox.",
            )
            for item in dashboard.recommendations[:3]
        ]

    dashboard.command_cards = _build_today_command_cards(dashboard, resolved_services)
    dashboard.confidence_domains = _build_today_confidence_domains(dashboard)

    return dashboard


def _today_review_checkpoint_from_dashboard(dashboard: TodayDashboardResponse) -> dict[str, Any]:
    profile_percent = None
    if dashboard.profile_readiness is not None:
        profile_percent = dashboard.profile_readiness.completion_percent
    elif dashboard.onboarding_completion_percent is not None:
        profile_percent = dashboard.onboarding_completion_percent

    active_plan_updated_at = None
    if dashboard.active_plan is not None and dashboard.active_plan.updated_at is not None:
        active_plan_updated_at = dashboard.active_plan.updated_at.isoformat()

    return {
        "recorded_at": utc_now().isoformat(),
        "dashboard_generated_at": dashboard.generated_at.isoformat(),
        "total_value_usd": dashboard.total_value_usd,
        "top_holding_symbol": dashboard.top_holding_symbol,
        "top_holding_percent": dashboard.top_holding_percent,
        "emergency_fund_months": dashboard.emergency_fund_months,
        "financial_health_status": dashboard.financial_health_status,
        "profile_completion_percent": profile_percent,
        "inbox_high_priority_count": dashboard.inbox_high_priority_count,
        "active_plan_id": dashboard.active_plan.id if dashboard.active_plan is not None else None,
        "active_plan_updated_at": active_plan_updated_at,
        "context_state": dashboard.context_state,
        "command_card_statuses": _today_command_card_statuses(dashboard.command_cards),
        "top_next_action_ids": [
            str(action.recommendation_id or action.title or "").strip()
            for action in dashboard.top_next_actions[:3]
            if str(action.recommendation_id or action.title or "").strip()
        ],
        "top_next_action_titles": [
            str(action.title or "").strip()
            for action in dashboard.top_next_actions[:3]
            if str(action.title or "").strip()
        ],
    }


def _extract_numeric_field(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in payload:
            continue
        try:
            return float(payload.get(key))
        except (TypeError, ValueError):
            continue
    return None


def _compute_price_history_change(records: list[dict[str, Any]]) -> tuple[float | None, float | None, float | None]:
    closes: list[float] = []
    for row in records:
        close_value = _extract_numeric_field(row, ("close", "adj_close", "last", "price"))
        if close_value is not None:
            closes.append(close_value)
    if len(closes) < 2:
        return None, None, None

    first_close = closes[0]
    last_close = closes[-1]
    if first_close == 0:
        return first_close, last_close, None

    return first_close, last_close, ((last_close - first_close) / first_close) * 100.0


def _extract_history_date_key(payload: dict[str, Any]) -> str:
    for key in ("date", "datetime", "timestamp", "as_of"):
        raw = payload.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        return text[:10]
    return ""


def _history_close_series_desc(records: list[dict[str, Any]]) -> list[float]:
    rows: list[tuple[str, float]] = []
    for row in records:
        close_value = _extract_numeric_field(row, ("close", "adj_close", "last", "price"))
        if close_value is None:
            continue
        rows.append((_extract_history_date_key(row), close_value))

    rows.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in rows]


# Trend and market-condition rules implemented for BuildWealth portfolio workflows:
# apps/api/src/services/benchmark/benchmark.service.ts
# libs/common/src/lib/helper.ts (calculateBenchmarkTrend)
def _calculate_benchmark_trend(*, closes_desc: list[float], days: int) -> str:
    if len(closes_desc) < 2 * days:
        return "UNKNOWN"
    recent_avg = sum(closes_desc[:days]) / float(days)
    past_avg = sum(closes_desc[days : 2 * days]) / float(days)
    if recent_avg > past_avg:
        return "UP"
    if recent_avg < past_avg:
        return "DOWN"
    return "NEUTRAL"


def _market_condition_from_all_time_high(performance_percent: float | None) -> str:
    if performance_percent is None:
        return "UNKNOWN"
    if performance_percent >= 0:
        return "ALL_TIME_HIGH"
    if performance_percent <= -20.0:
        return "BEAR_MARKET"
    return "NEUTRAL_MARKET"


def _bool_from_payload(payload: dict[str, Any], key: str) -> bool:
    return bool(payload.get(key))


def _list_from_payload(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    return value if isinstance(value, list) else []


def _watchlist_market_payload_from_evidence_packet(
    *,
    symbol: str,
    period: str,
    interval: str,
) -> dict[str, Any]:
    packet = research_service.evidence_packet(symbol=symbol, period=period, interval=interval)
    coverage = packet.coverage if isinstance(packet.coverage, dict) else {}
    freshness = packet.freshness if isinstance(packet.freshness, dict) else {}
    metrics = packet.metrics if isinstance(packet.metrics, dict) else {}
    risk = packet.risk if isinstance(packet.risk, dict) else {}
    quality = packet.quality if isinstance(packet.quality, dict) else {}
    provenance = packet.provenance if isinstance(packet.provenance, dict) else {}

    history_records = int(_coerce_float(provenance.get("history_records"), 0.0))
    quote_price = _extract_numeric_field(metrics, ("last_price", "quote_price", "price"))
    all_time_high = _extract_numeric_field(risk, ("all_time_high",))
    drawdown_from_high_pct = _extract_numeric_field(risk, ("drawdown_from_high_pct",))
    if quote_price is not None and drawdown_from_high_pct is not None and drawdown_from_high_pct > -100:
        denominator = 1.0 + (drawdown_from_high_pct / 100.0)
        if all_time_high is None and denominator > 0:
            all_time_high = quote_price / denominator

    warnings = [
        str(item).strip()
        for item in [
            *_list_from_payload(coverage, "warnings"),
            *_list_from_payload(provenance, "warnings"),
        ]
        if str(item).strip()
    ]

    return {
        "quote_available": _bool_from_payload(coverage, "quote_available"),
        "quote_message": str(coverage.get("quote_message") or ""),
        "quote_price": quote_price,
        "quote_change_pct": _extract_numeric_field(metrics, ("day_change_pct", "quote_change_pct")),
        "history_available": _bool_from_payload(coverage, "history_available"),
        "history_message": str(coverage.get("history_message") or ""),
        "period_first_close": _extract_numeric_field(metrics, ("period_first_close",)),
        "period_last_close": _extract_numeric_field(metrics, ("period_last_close",)),
        "period_change_pct": _extract_numeric_field(metrics, ("period_change_pct",)),
        "all_time_high": all_time_high,
        "performance_from_high_pct": drawdown_from_high_pct,
        "trend50d": str(risk.get("trend50d") or "UNKNOWN"),
        "trend200d": str(risk.get("trend200d") or "UNKNOWN"),
        "history_records": history_records,
        "research_evidence_packet_id": packet.packet_id,
        "research_provider": packet.provider,
        "research_freshness_status": str(freshness.get("status") or ""),
        "research_confidence": str(quality.get("confidence") or ""),
        "research_coverage_score": _extract_numeric_field(quality, ("coverage_score",)),
        "research_blocking_gaps": [str(item) for item in _list_from_payload(quality, "blocking_gaps")],
        "provider_coverage": {
            "provider": coverage.get("provider") or packet.provider,
            "provider_status": coverage.get("provider_status"),
            "endpoint_statuses": coverage.get("endpoint_statuses")
            if isinstance(coverage.get("endpoint_statuses"), list)
            else [],
            "available_endpoint_count": coverage.get("available_endpoint_count"),
            "attempted_endpoint_count": coverage.get("attempted_endpoint_count"),
            "warnings": warnings,
        },
        "warnings": warnings,
    }


def _watchlist_market_payload_from_legacy_research(
    *,
    symbol: str,
    period: str,
    interval: str,
) -> dict[str, Any]:
    quote_response = research_service.quote(symbol=symbol)
    quote_row = quote_response.records[0] if quote_response.records else {}
    if not isinstance(quote_row, dict):
        quote_row = {}
    quote_price = _extract_numeric_field(
        quote_row,
        (
            "last",
            "price",
            "close",
            "adj_close",
            "regular_market_price",
            "post_market_price",
        ),
    )
    quote_change_pct = _extract_numeric_field(
        quote_row,
        (
            "change_percent",
            "change_pct",
            "percent_change",
            "regular_market_change_percent",
        ),
    )

    history_response = research_service.price_history(
        symbol=symbol,
        period=period,
        interval=interval,
    )
    history_records = [row for row in history_response.records if isinstance(row, dict)]
    first_close, last_close, period_change_pct = _compute_price_history_change(history_records)
    close_series_desc = _history_close_series_desc(history_records)
    trend_50d = _calculate_benchmark_trend(closes_desc=close_series_desc, days=50)
    trend_200d = _calculate_benchmark_trend(closes_desc=close_series_desc, days=200)
    all_time_high = max(close_series_desc) if close_series_desc else None
    performance_from_high_pct = None
    if all_time_high and quote_price is not None and all_time_high > 0:
        performance_from_high_pct = ((quote_price - all_time_high) / all_time_high) * 100.0

    warnings: list[str] = []
    if not quote_response.available:
        warnings.append(f"{symbol}: quote unavailable ({quote_response.message})")
    if not history_response.available:
        warnings.append(f"{symbol}: history unavailable ({history_response.message})")

    return {
        "quote_available": quote_response.available,
        "quote_message": quote_response.message,
        "quote_price": quote_price,
        "quote_change_pct": quote_change_pct,
        "history_available": history_response.available,
        "history_message": history_response.message,
        "period_first_close": first_close,
        "period_last_close": last_close,
        "period_change_pct": period_change_pct,
        "all_time_high": all_time_high,
        "performance_from_high_pct": performance_from_high_pct,
        "trend50d": trend_50d,
        "trend200d": trend_200d,
        "history_records": len(history_records),
        "research_evidence_packet_id": None,
        "research_provider": None,
        "research_freshness_status": None,
        "research_confidence": None,
        "research_coverage_score": None,
        "research_blocking_gaps": [],
        "provider_coverage": {
            "provider": getattr(research_service, "provider", None),
            "provider_status": "available" if quote_response.available or history_response.available else "unavailable",
            "endpoint_statuses": [],
            "warnings": warnings,
        },
        "warnings": warnings,
    }


def _build_watchlist_market_payload(
    *,
    symbol: str,
    period: str,
    interval: str,
) -> dict[str, Any]:
    try:
        return _watchlist_market_payload_from_evidence_packet(
            symbol=symbol,
            period=period,
            interval=interval,
        )
    except AttributeError:
        return _watchlist_market_payload_from_legacy_research(
            symbol=symbol,
            period=period,
            interval=interval,
        )


WATCHLIST_SCORE_MODEL_VERSION = "watchlist_v1"


def _normalize_watchlist_sort(raw_sort: str | None) -> str:
    normalized = str(raw_sort or "").strip().lower()
    if normalized in {"ranked", "symbol", "updated_at"}:
        return normalized
    return "ranked"


def _score_from_percent(
    value: float | None,
    *,
    floor: float,
    ceil: float,
    default_score: float = 50.0,
) -> float:
    if value is None:
        return float(default_score)
    if ceil <= floor:
        return float(default_score)
    clipped = max(floor, min(ceil, float(value)))
    return ((clipped - floor) / (ceil - floor)) * 100.0


def _trend_signal_score(signal: str) -> float:
    normalized = str(signal or "").strip().upper()
    if normalized == "UP":
        return 100.0
    if normalized == "DOWN":
        return 20.0
    if normalized == "NEUTRAL":
        return 55.0
    return 40.0


def _build_watchlist_rank_score(
    *,
    quote_available: bool,
    history_available: bool,
    quote_price: float | None,
    quote_change_pct: float | None,
    period_change_pct: float | None,
    trend_50d: str,
    trend_200d: str,
    target_price_usd: float | None,
    performance_from_high_pct: float | None,
    history_records: int,
) -> dict[str, Any]:
    reasons: list[str] = []

    period_score = _score_from_percent(period_change_pct, floor=-30.0, ceil=30.0, default_score=50.0)
    day_score = _score_from_percent(quote_change_pct, floor=-8.0, ceil=8.0, default_score=50.0)
    momentum_score = (period_score * 0.75) + (day_score * 0.25)

    trend_50d_score = _trend_signal_score(trend_50d)
    trend_200d_score = _trend_signal_score(trend_200d)
    trend_score = (trend_50d_score * 0.4) + (trend_200d_score * 0.6)
    if trend_50d == "UP" and trend_200d == "UP":
        reasons.append("trend_up_50d_200d")
    elif trend_50d == "DOWN" and trend_200d == "DOWN":
        reasons.append("trend_down_50d_200d")

    upside_to_target_pct: float | None = None
    target_score = 50.0
    if target_price_usd is not None and quote_price is not None and quote_price > 0:
        upside_to_target_pct = ((target_price_usd - quote_price) / quote_price) * 100.0
        target_score = _score_from_percent(upside_to_target_pct, floor=-20.0, ceil=30.0, default_score=50.0)
        if upside_to_target_pct >= 15.0:
            reasons.append("target_upside_high")
        elif upside_to_target_pct <= -10.0:
            reasons.append("price_above_target")
    elif target_price_usd is not None:
        reasons.append("target_present_price_missing")
    else:
        reasons.append("target_missing")

    data_quality_score = 15.0
    if quote_available and history_available:
        data_quality_score = 100.0
    elif quote_available or history_available:
        data_quality_score = 65.0
    if history_records < 60:
        data_quality_score = max(20.0, data_quality_score - 20.0)
        reasons.append("history_shallow")
    if not quote_available:
        reasons.append("quote_unavailable")
    if not history_available:
        reasons.append("history_unavailable")

    risk_score = _score_from_percent(performance_from_high_pct, floor=-50.0, ceil=10.0, default_score=55.0)
    if performance_from_high_pct is not None and performance_from_high_pct <= -20.0:
        reasons.append("drawdown_deep")
    elif performance_from_high_pct is not None and performance_from_high_pct >= -5.0:
        reasons.append("near_high")

    total = (
        (momentum_score * 0.30)
        + (trend_score * 0.20)
        + (target_score * 0.20)
        + (data_quality_score * 0.20)
        + (risk_score * 0.10)
    )

    return {
        "model_version": WATCHLIST_SCORE_MODEL_VERSION,
        "total": round(max(0.0, min(100.0, total)), 2),
        "momentum": round(max(0.0, min(100.0, momentum_score)), 2),
        "trend": round(max(0.0, min(100.0, trend_score)), 2),
        "target_gap": round(max(0.0, min(100.0, target_score)), 2),
        "data_quality": round(max(0.0, min(100.0, data_quality_score)), 2),
        "risk_balance": round(max(0.0, min(100.0, risk_score)), 2),
        "upside_to_target_pct": round(upside_to_target_pct, 2) if upside_to_target_pct is not None else None,
        "reasons": reasons[:8],
    }


def build_portfolio_watchlist_payload(
    *,
    period: str = "2y",
    interval: str = "1d",
    sort: str = "ranked",
    limit: int = 200,
    store: PortfolioStore | None = None,
) -> dict[str, Any]:
    period_value = str(period or "2y").strip() or "2y"
    interval_value = str(interval or "1d").strip() or "1d"
    sort_value = _normalize_watchlist_sort(sort)
    limit_value = max(1, min(int(limit), 500))
    resolved_store = store or portfolio_store
    items_payload = resolved_store.list_watchlist()
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in items_payload:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue

        market_payload = _build_watchlist_market_payload(
            symbol=symbol,
            period=period_value,
            interval=interval_value,
        )
        warnings.extend(str(item) for item in market_payload.get("warnings", []) if str(item).strip())

        target_price = _extract_numeric_field(
            item,
            (
                "target_price_usd",
                "target_price",
                "target",
            ),
        )
        score_payload = _build_watchlist_rank_score(
            quote_available=bool(market_payload.get("quote_available")),
            history_available=bool(market_payload.get("history_available")),
            quote_price=market_payload.get("quote_price"),
            quote_change_pct=market_payload.get("quote_change_pct"),
            period_change_pct=market_payload.get("period_change_pct"),
            trend_50d=str(market_payload.get("trend50d") or "UNKNOWN"),
            trend_200d=str(market_payload.get("trend200d") or "UNKNOWN"),
            target_price_usd=target_price,
            performance_from_high_pct=market_payload.get("performance_from_high_pct"),
            history_records=int(market_payload.get("history_records") or 0),
        )

        rows.append(
            {
                "symbol": symbol,
                "data_source": str(item.get("data_source") or "OPENBB").strip().upper() or "OPENBB",
                "note": str(item.get("note") or ""),
                "thesis": str(item.get("thesis") or ""),
                "thesis_reviewed_at": str(item.get("thesis_reviewed_at") or ""),
                "thesis_expires_at": str(item.get("thesis_expires_at") or ""),
                "thesis_reference_price_usd": _coerce_optional_float(item.get("thesis_reference_price_usd")),
                "thesis_revision_history": (
                    item.get("thesis_revision_history")
                    if isinstance(item.get("thesis_revision_history"), list)
                    else []
                ),
                "target_price_usd": target_price,
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "created_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "quote_available": bool(market_payload.get("quote_available")),
                "quote_message": str(market_payload.get("quote_message") or ""),
                "quote_price": market_payload.get("quote_price"),
                "quote_change_pct": market_payload.get("quote_change_pct"),
                "history_available": bool(market_payload.get("history_available")),
                "history_message": str(market_payload.get("history_message") or ""),
                "period_label": period_value,
                "period_first_close": market_payload.get("period_first_close"),
                "period_last_close": market_payload.get("period_last_close"),
                "period_change_pct": market_payload.get("period_change_pct"),
                "all_time_high": market_payload.get("all_time_high"),
                "performance_from_high_pct": market_payload.get("performance_from_high_pct"),
                "market_condition": _market_condition_from_all_time_high(
                    market_payload.get("performance_from_high_pct")
                ),
                "trend50d": str(market_payload.get("trend50d") or "UNKNOWN"),
                "trend200d": str(market_payload.get("trend200d") or "UNKNOWN"),
                "history_records": int(market_payload.get("history_records") or 0),
                "research_evidence_packet_id": market_payload.get("research_evidence_packet_id"),
                "research_provider": market_payload.get("research_provider"),
                "research_freshness_status": market_payload.get("research_freshness_status"),
                "research_confidence": market_payload.get("research_confidence"),
                "research_coverage_score": market_payload.get("research_coverage_score"),
                "research_blocking_gaps": market_payload.get("research_blocking_gaps")
                if isinstance(market_payload.get("research_blocking_gaps"), list)
                else [],
                "provider_coverage": market_payload.get("provider_coverage")
                if isinstance(market_payload.get("provider_coverage"), dict)
                else {},
                "watchlist_rank": None,
                "watchlist_score_total": score_payload.get("total"),
                "watchlist_score": score_payload,
                "watchlist_score_reasons": score_payload.get("reasons"),
            }
        )

    if sort_value == "symbol":
        rows.sort(key=lambda item: str(item.get("symbol") or ""))
    elif sort_value == "updated_at":
        rows.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    else:
        rows.sort(
            key=lambda item: (
                -float(item.get("watchlist_score_total") or 0.0),
                str(item.get("symbol") or ""),
            )
        )
        for index, row in enumerate(rows, start=1):
            row["watchlist_rank"] = index

    deduped_warnings = normalize_context_warnings(warnings, max_warnings=80)
    rows = rows[:limit_value]
    return {
        "period": period_value,
        "interval": interval_value,
        "score_model": WATCHLIST_SCORE_MODEL_VERSION,
        "sorted_by": sort_value,
        "count": len(rows),
        "items": rows,
        "warnings": deduped_warnings,
        "updated_at": context_utc_now_iso(),
    }


def _build_context_cache_key(prefix: str, payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{prefix}:{serialized}"


def _resolve_context_plan_detail(
    plan_id: str | None,
    *,
    workspace: PlanWorkspace | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    resolved_workspace = workspace or plan_workspace
    if plan_id:
        detail = resolved_workspace.get_plan(plan_id)
        return detail, str(detail.get("id") or plan_id)

    detail = resolve_active_plan_detail(workspace=resolved_workspace)
    if not isinstance(detail, dict):
        return None, None
    return detail, str(detail.get("id") or "") or None


async def build_buildwealth_context_payload(
    *,
    use_live_snapshot: bool = False,
    plan_id: str | None = None,
    include_research: bool = True,
    force_refresh: bool = False,
    research_symbols: list[str] | None = None,
    research_period: str = "6mo",
    research_interval: str = "1d",
    include_plan_projection: bool = True,
    max_recommendations: int = 10,
    max_plan_decisions: int = 8,
    summary_max_chars: int = DEFAULT_CONTEXT_SUMMARY_MAX_CHARS,
    research_symbol_limit: int = DEFAULT_RESEARCH_SYMBOL_LIMIT,
    detail_level: str = DEFAULT_CONTEXT_DETAIL_LEVEL,
    services: WorkspaceServices | None = None,
) -> dict[str, Any]:
    scoped_services = services is not None
    resolved_services = workspace_services_or_legacy(services)
    warnings: list[str] = []
    resolved_detail_level = normalize_context_detail_level(detail_level)
    resolved_snapshot: PortfolioSnapshot | None = None
    cache_globally_enabled = bool(settings.copilot_context_cache_enabled)
    cache_reads_enabled = cache_globally_enabled and not force_refresh
    cache_writes_enabled = cache_globally_enabled
    research_cache_hit = False
    research_cache_written = False
    projection_cache_hit = False
    projection_cache_written = False

    snapshot_summary_payload: dict[str, Any]
    try:
        if use_live_snapshot:
            resolved_snapshot = await build_live_snapshot(resolved_services.portfolio_store)
        else:
            resolved_snapshot = resolved_services.snapshot_store.latest()
        snapshot_summary_payload = summarize_snapshot(resolved_snapshot)
    except FileNotFoundError:
        snapshot_summary_payload = {"note": "No local snapshot yet. Run sync or fetch live snapshot."}
    except Exception as exc:
        snapshot_summary_payload = {"note": f"Snapshot context unavailable: {exc}"}
        warnings.append(str(snapshot_summary_payload["note"]))

    try:
        if scoped_services:
            snapshot_history_payload = build_snapshot_history_payload(
                limit=30,
                store=resolved_services.snapshot_store,
            ).model_dump(mode="json")
        else:
            snapshot_history_payload = build_snapshot_history_payload(limit=30).model_dump(mode="json")
    except Exception as exc:
        snapshot_history_payload = {"note": f"Snapshot history context unavailable: {exc}"}
        warnings.append(str(snapshot_history_payload["note"]))

    try:
        today_dashboard_response = (
            build_today_dashboard_response(resolved_services)
            if scoped_services
            else build_today_dashboard_response()
        )
        today_dashboard_payload = today_dashboard_response.model_dump(mode="json")
    except Exception as exc:
        today_dashboard_payload = {"note": f"Today dashboard context unavailable: {exc}"}
        warnings.append(str(today_dashboard_payload["note"]))

    try:
        profile_source = (
            get_financial_profile_payload(resolved_services.financial_profile_store)
            if scoped_services
            else get_financial_profile_payload()
        )
        financial_profile_payload = FinancialProfileResponse(
            **profile_source
        ).model_dump(mode="json")
    except Exception as exc:
        financial_profile_payload = {"note": f"Financial profile context unavailable: {exc}"}
        warnings.append(str(financial_profile_payload["note"]))

    try:
        if scoped_services:
            onboarding_response = build_onboarding_status_response(
                profile_payload=get_financial_profile_payload(resolved_services.financial_profile_store),
                latest_snapshot=resolved_snapshot,
                active_plan_detail=resolve_active_plan_detail(workspace=resolved_services.plan_workspace),
                load_fallbacks=False,
            )
        else:
            onboarding_response = build_onboarding_status_response()
        onboarding_payload = onboarding_response.model_dump(mode="json")
    except Exception as exc:
        onboarding_payload = {"note": f"Onboarding context unavailable: {exc}"}
        warnings.append(str(onboarding_payload["note"]))

    try:
        watchlist_items = resolved_services.portfolio_store.list_watchlist()
        watchlist_payload = {
            "count": len(watchlist_items),
            "symbols_preview": [
                str(item.get("symbol") or "").strip().upper()
                for item in watchlist_items[:8]
                if isinstance(item, dict) and str(item.get("symbol") or "").strip()
            ],
            "items": watchlist_items,
            "updated_at": context_utc_now_iso(),
        }
    except Exception as exc:
        watchlist_payload = {"note": f"Watchlist context unavailable: {exc}", "items": []}
        warnings.append(str(watchlist_payload["note"]))

    recommendation_limit = max(1, min(_coerce_int(max_recommendations, 10), 50))
    recommendations_payload: dict[str, Any]
    recommendation_rows: list[dict[str, Any]]
    try:
        if scoped_services:
            recommendation_rows = _recommendation_list(
                limit=recommendation_limit,
                status="proposed",
                inbox=resolved_services.recommendation_inbox,
            )
        else:
            recommendation_rows = _recommendation_list(
                limit=recommendation_limit,
                status="proposed",
            )
        recommendations_payload = {
            "open_count": len(recommendation_rows),
            "high_priority_count": len(
                [
                    row
                    for row in recommendation_rows
                    if str(row.get("priority", "")).strip().lower() == "high"
                ]
            ),
            "items": recommendation_rows,
        }
    except Exception as exc:
        recommendation_rows = []
        recommendations_payload = {"note": f"Recommendation context unavailable: {exc}", "items": []}
        warnings.append(str(recommendations_payload["note"]))

    resolved_plan_detail: dict[str, Any] | None = None
    resolved_plan_id: str | None = None
    plan_context_payload: dict[str, Any] = {"note": "No active plan is configured."}
    plan_assumption_sets_payload: dict[str, Any] = {}
    plan_timeline_payload: dict[str, Any] = {}
    plan_contribution_rules_payload: dict[str, Any] = {}
    plan_contribution_allocation_preview_payload: dict[str, Any] | None = None
    plan_branch_templates_payload: dict[str, Any] = {}
    plan_withdrawal_strategy_payload: dict[str, Any] = {
        "active": "cashflow_only",
        "source": "default",
        "options": DEFAULT_WITHDRAWAL_STRATEGIES,
    }
    plan_household_payload: dict[str, Any] = {
        "mode": HOUSEHOLD_MODE_INDIVIDUAL,
        "source": "default",
        "filing_status": "single",
        "partner_income_usd": 0.0,
        "partner_income_growth_rate": 0.0,
        "partner_retirement_age": None,
        "partner_social_security_annual_usd": 0.0,
        "partner_social_security_claiming_age": None,
        "shared_goal_target_usd": 0.0,
        "shared_goal_target_year": None,
    }
    plan_tracking_payload: dict[str, Any] = {}
    plan_decisions_payload: list[dict[str, Any]] = []
    baseline_projection_payload: dict[str, Any] | None = None

    try:
        if scoped_services:
            resolved_plan_detail, resolved_plan_id = _resolve_context_plan_detail(
                plan_id,
                workspace=resolved_services.plan_workspace,
            )
        else:
            resolved_plan_detail, resolved_plan_id = _resolve_context_plan_detail(plan_id)
    except PlanNotFoundError as exc:
        warnings.append(str(exc))
    except Exception as exc:
        warnings.append(f"Plan resolution failed: {exc}")

    if isinstance(resolved_plan_detail, dict) and resolved_plan_id:
        try:
            plan_context_payload = resolved_services.plan_workspace.get_context_payload(plan_id=resolved_plan_id)
        except Exception as exc:
            plan_context_payload = {"note": f"Plan context unavailable: {exc}"}
            warnings.append(str(plan_context_payload["note"]))

        try:
            plan_assumption_sets_payload = resolved_services.plan_workspace.get_plan_assumption_sets(resolved_plan_id)
            plan_timeline_payload = resolved_services.plan_workspace.get_plan_timeline(resolved_plan_id)
            plan_contribution_rules_payload = resolved_services.plan_workspace.get_plan_contribution_rules(resolved_plan_id)
            plan_branch_templates_payload = resolved_services.plan_workspace.get_plan_branch_templates(resolved_plan_id)
        except Exception as exc:
            warnings.append(f"Plan model payload unavailable: {exc}")

        try:
            raw_settings = resolved_plan_detail.get("settings", {})
            if not isinstance(raw_settings, dict):
                raw_settings = {}
            household_mode = _normalize_household_mode(raw_settings.get("household_mode"))
            household_source = (
                "settings"
                if any(
                    raw_settings.get(field) not in {None, ""}
                    for field in (
                        "household_mode",
                        "household_partner_income_usd",
                        "household_partner_income_growth_rate",
                        "household_partner_retirement_age",
                        "household_partner_social_security_annual_usd",
                        "household_partner_social_security_claiming_age",
                        "household_shared_goal_target_usd",
                        "household_shared_goal_target_year",
                        "filing_status",
                    )
                )
                else "default"
            )
            settings_strategy = normalize_withdrawal_strategy_value(raw_settings.get("withdrawal_strategy"))
            settings_drawdown_order = str(raw_settings.get("drawdown_order") or "").strip() or None
            timeline_retirement_payload = (
                plan_timeline_payload.get("retirement")
                if isinstance(plan_timeline_payload.get("retirement"), dict)
                else {}
            )
            timeline_strategy = normalize_withdrawal_strategy_value(
                timeline_retirement_payload.get("withdrawal_strategy")
            )
            timeline_drawdown_order = str(timeline_retirement_payload.get("drawdown_order") or "").strip() or None
            active_strategy = (
                settings_strategy
                or timeline_strategy
                or normalize_withdrawal_strategy_value(None, fallback="cashflow_only")
                or "cashflow_only"
            )
            source = "settings" if settings_strategy else ("timeline" if timeline_strategy else "default")
            active_drawdown_order = settings_drawdown_order or timeline_drawdown_order or "age_aware"
            drawdown_source = (
                "settings"
                if settings_drawdown_order
                else ("timeline" if timeline_drawdown_order else "default")
            )
            plan_withdrawal_strategy_payload = {
                "active": active_strategy,
                "source": source,
                "options": DEFAULT_WITHDRAWAL_STRATEGIES,
                "drawdown_order": active_drawdown_order,
                "drawdown_order_source": drawdown_source,
            }
            plan_household_payload = {
                "mode": household_mode,
                "source": household_source,
                "filing_status": _resolve_filing_status_for_household(
                    filing_status=raw_settings.get("filing_status"),
                    household_mode=household_mode,
                ) or "single",
                "partner_income_usd": max(0.0, _coerce_float(raw_settings.get("household_partner_income_usd"), 0.0)),
                "partner_income_growth_rate": max(
                    -1.0,
                    min(1.0, _coerce_float(raw_settings.get("household_partner_income_growth_rate"), 0.0)),
                ),
                "partner_retirement_age": _normalize_optional_household_age(
                    raw_settings.get("household_partner_retirement_age"),
                ),
                "partner_social_security_annual_usd": max(
                    0.0,
                    _coerce_float(raw_settings.get("household_partner_social_security_annual_usd"), 0.0),
                ),
                "partner_social_security_claiming_age": _normalize_optional_household_age(
                    raw_settings.get("household_partner_social_security_claiming_age"),
                ),
                "shared_goal_target_usd": max(
                    0.0,
                    _coerce_float(raw_settings.get("household_shared_goal_target_usd"), 0.0),
                ),
                "shared_goal_target_year": _normalize_optional_household_year(
                    raw_settings.get("household_shared_goal_target_year"),
                ),
            }
        except Exception as exc:
            warnings.append(f"Withdrawal strategy context unavailable: {exc}")

        planner_defaults = {
            "annual_contribution_usd": settings.planner_annual_contribution_usd,
            "expected_return_baseline": settings.planner_expected_return_baseline,
            "hsa_extra_contribution_usd": settings.planner_hsa_delta_default,
        }
        try:
            plan_settings = PlanSettings(**resolved_plan_detail.get("settings", {}))
            tracking_response = compute_plan_tracking(
                plan_id=resolved_plan_id,
                plan_title=str(resolved_plan_detail.get("title") or ""),
                plan_settings=plan_settings,
                planner_defaults=planner_defaults,
                snapshots=resolved_services.snapshot_store.recent(limit=90),
                transactions=resolved_services.portfolio_store.list_transactions(limit=10_000),
            )
            plan_tracking_payload = tracking_response.model_dump(mode="json")
        except Exception as exc:
            plan_tracking_payload = {"note": f"Plan tracking context unavailable: {exc}"}
            warnings.append(str(plan_tracking_payload["note"]))

        decisions_limit = max(1, min(_coerce_int(max_plan_decisions, 8), 30))
        raw_decisions = resolved_plan_detail.get("decisions")
        if isinstance(raw_decisions, list):
            for item in raw_decisions[:decisions_limit]:
                if not isinstance(item, dict):
                    continue
                plan_decisions_payload.append(
                    {
                        "id": item.get("id"),
                        "status": item.get("status"),
                        "summary": item.get("summary"),
                        "rationale": item.get("rationale"),
                        "created_at": item.get("created_at"),
                    }
                )

        try:
            raw_settings = resolved_plan_detail.get("settings", {})
            if not isinstance(raw_settings, dict):
                raw_settings = {}
            preview = build_contribution_allocation_for_plan_settings(
                plan_settings=raw_settings,
                contribution_rules_payload=plan_contribution_rules_payload,
            )
            if preview is not None:
                plan_contribution_allocation_preview_payload = preview.model_dump(mode="json")
        except Exception as exc:
            warnings.append(f"Contribution allocation preview unavailable: {exc}")

        if include_plan_projection and resolved_snapshot is not None:
            projection_cache_key: str | None = None
            if cache_reads_enabled and resolved_plan_id and not use_live_snapshot:
                projection_cache_key = _build_context_cache_key(
                    "baseline_projection",
                    {
                        "workspace_id": resolved_services.record.id,
                        "plan_id": resolved_plan_id,
                        "plan_updated_at": resolved_plan_detail.get("updated_at"),
                        "snapshot_as_of": resolved_snapshot.as_of.isoformat(),
                        "snapshot_total_value_usd": round(float(resolved_snapshot.total_value_usd), 2),
                        "currency": settings.app_currency,
                    },
                )
                projection_cache_hit, cached_projection_payload = copilot_context_projection_cache.lookup(
                    projection_cache_key
                )
                if projection_cache_hit and isinstance(cached_projection_payload, dict):
                    baseline_projection_payload = cached_projection_payload
            elif cache_writes_enabled and resolved_plan_id and not use_live_snapshot:
                projection_cache_key = _build_context_cache_key(
                    "baseline_projection",
                    {
                        "workspace_id": resolved_services.record.id,
                        "plan_id": resolved_plan_id,
                        "plan_updated_at": resolved_plan_detail.get("updated_at"),
                        "snapshot_as_of": resolved_snapshot.as_of.isoformat(),
                        "snapshot_total_value_usd": round(float(resolved_snapshot.total_value_usd), 2),
                        "currency": settings.app_currency,
                    },
                )

            if baseline_projection_payload is None:
                try:
                    base_settings_raw = resolved_plan_detail.get("settings", {})
                    if not isinstance(base_settings_raw, dict):
                        base_settings_raw = {}
                    assumption_sets_payload = resolve_plan_assumption_sets(resolved_plan_detail)
                    projection_settings, active_assumption_set = apply_assumption_set_to_settings(
                        plan_settings=base_settings_raw,
                        assumption_sets_payload=assumption_sets_payload,
                    )
                    timeline_payload = resolve_plan_timeline_payload(resolved_plan_detail)
                    timeline_retirement_age = resolve_timeline_retirement_age(timeline_payload)
                    timeline_withdrawal_strategy = resolve_timeline_withdrawal_strategy(timeline_payload)
                    timeline_drawdown_order = resolve_timeline_drawdown_order(timeline_payload)
                    income_projection = build_income_projection_for_plan_settings(projection_settings)
                    expense_projection = build_expense_projection_for_plan_settings(projection_settings)
                    debt_projection = build_debt_projection_for_plan_settings(projection_settings)
                    timeline_projection = build_timeline_projection_for_plan_settings(
                        plan_settings=projection_settings,
                        timeline_payload=timeline_payload,
                    )
                    contribution_allocation = build_contribution_allocation_for_plan_settings(
                        plan_settings=projection_settings,
                    )
                    social_security_projection = build_social_security_projection_for_plan_settings(
                        plan_settings=projection_settings,
                        timeline_payload=timeline_payload,
                        income_projection=income_projection,
                        start_year=utc_now().year,
                    )
                    rmd_projection = build_rmd_projection_for_plan_settings(
                        plan_settings=projection_settings,
                        timeline_payload=timeline_payload,
                        start_year=utc_now().year,
                    )
                    baseline_projection = await run_scenarios_for_plan_settings(
                        current_portfolio_value_usd=float(resolved_snapshot.total_value_usd),
                        plan_settings=projection_settings,
                        income_projection=income_projection,
                        expense_projection=expense_projection,
                        debt_projection=debt_projection,
                        timeline_projection=timeline_projection,
                        contribution_allocation=contribution_allocation,
                        social_security_projection=social_security_projection,
                        rmd_projection=rmd_projection,
                        assumption_set=active_assumption_set,
                        retirement_age=timeline_retirement_age,
                        timeline_withdrawal_strategy=timeline_withdrawal_strategy,
                        timeline_drawdown_order=timeline_drawdown_order,
                    )
                    baseline_projection_payload = baseline_projection.model_dump(mode="json")
                    if (
                        cache_writes_enabled
                        and projection_cache_key
                        and isinstance(baseline_projection_payload, dict)
                    ):
                        copilot_context_projection_cache.set(
                            projection_cache_key,
                            baseline_projection_payload,
                            ttl_seconds=settings.copilot_context_projection_cache_ttl_seconds,
                        )
                        projection_cache_written = True
                except Exception as exc:
                    warnings.append(f"Baseline projection context unavailable: {exc}")

    research_period_value = str(research_period or "").strip() or "6mo"
    research_interval_value = str(research_interval or "").strip() or "1d"
    requested_symbols = normalize_research_symbols(
        research_symbols or [],
        max_symbols=max(0, min(_coerce_int(research_symbol_limit, DEFAULT_RESEARCH_SYMBOL_LIMIT), 20)),
    )
    watchlist_symbols_for_context = []
    if isinstance(watchlist_payload, dict):
        symbols_preview = watchlist_payload.get("symbols_preview")
        if isinstance(symbols_preview, list):
            watchlist_symbols_for_context = symbols_preview
    research_symbols_for_context = derive_research_symbols(
        requested_symbols=requested_symbols,
        snapshot_summary=snapshot_summary_payload,
        watchlist_symbols=watchlist_symbols_for_context,
        max_symbols=max(0, min(_coerce_int(research_symbol_limit, DEFAULT_RESEARCH_SYMBOL_LIMIT), 20)),
    )
    research_items: list[dict[str, Any]] = []
    research_warnings: list[str] = []
    research_cache_key: str | None = None

    if include_research:
        research_cache_key = _build_context_cache_key(
            "research",
            {
                "workspace_id": resolved_services.record.id,
                "provider": settings.openbb_provider,
                "period": research_period_value,
                "interval": research_interval_value,
                "symbols": research_symbols_for_context,
            },
        )
        if cache_reads_enabled:
            research_cache_hit, cached_research_payload = copilot_context_research_cache.lookup(
                research_cache_key
            )
            if research_cache_hit and isinstance(cached_research_payload, dict):
                cached_items = cached_research_payload.get("items")
                cached_warnings = cached_research_payload.get("warnings")
                if isinstance(cached_items, list):
                    research_items = [item for item in cached_items if isinstance(item, dict)]
                if isinstance(cached_warnings, list):
                    research_warnings = [str(item) for item in cached_warnings]

        if not research_cache_hit:
            for symbol in research_symbols_for_context:
                quote_response = research_service.quote(symbol=symbol)
                quote_row = quote_response.records[0] if quote_response.records else {}
                if not isinstance(quote_row, dict):
                    quote_row = {}
                quote_price = _extract_numeric_field(
                    quote_row,
                    (
                        "last",
                        "price",
                        "close",
                        "adj_close",
                        "regular_market_price",
                        "post_market_price",
                    ),
                )
                quote_change_pct = _extract_numeric_field(
                    quote_row,
                    (
                        "change_percent",
                        "change_pct",
                        "percent_change",
                        "regular_market_change_percent",
                    ),
                )

                history_response = research_service.price_history(
                    symbol=symbol,
                    period=research_period_value,
                    interval=research_interval_value,
                )
                history_records = [row for row in history_response.records if isinstance(row, dict)]
                first_close, last_close, period_change_pct = _compute_price_history_change(history_records)
                research_items.append(
                    {
                        "symbol": symbol,
                        "quote_available": quote_response.available,
                        "quote_price": quote_price,
                        "quote_change_pct": quote_change_pct,
                        "quote_message": quote_response.message,
                        "history_available": history_response.available,
                        "history_message": history_response.message,
                        "period_label": research_period_value,
                        "period_first_close": first_close,
                        "period_last_close": last_close,
                        "period_change_pct": period_change_pct,
                    }
                )
                if not quote_response.available:
                    research_warnings.append(f"{symbol}: quote unavailable ({quote_response.message})")
                if not history_response.available:
                    research_warnings.append(f"{symbol}: history unavailable ({history_response.message})")

            if cache_writes_enabled and research_cache_key:
                copilot_context_research_cache.set(
                    research_cache_key,
                    {
                        "items": research_items,
                        "warnings": research_warnings,
                    },
                    ttl_seconds=settings.copilot_context_research_cache_ttl_seconds,
                )
                research_cache_written = True

    context_payload: dict[str, Any] = {
        "generated_at": context_utc_now_iso(),
        "scope": {
            "plan_id": resolved_plan_id,
            "use_live_snapshot": bool(use_live_snapshot),
            "include_research": bool(include_research),
            "include_plan_projection": bool(include_plan_projection),
            "detail_level": resolved_detail_level,
        },
        "cache": {
            "enabled": bool(cache_globally_enabled),
            "read_enabled": bool(cache_reads_enabled),
            "write_enabled": bool(cache_writes_enabled),
            "force_refresh": bool(force_refresh),
            "bypass_reason": (
                "force_refresh"
                if cache_globally_enabled and force_refresh
                else ("disabled" if not cache_globally_enabled else None)
            ),
            "research": {
                "hit": bool(research_cache_hit),
                "written": bool(research_cache_written),
                "ttl_seconds": float(settings.copilot_context_research_cache_ttl_seconds),
            },
            "baseline_projection": {
                "hit": bool(projection_cache_hit),
                "written": bool(projection_cache_written),
                "ttl_seconds": float(settings.copilot_context_projection_cache_ttl_seconds),
            },
        },
        "location_state": settings.app_state,
        "currency": settings.app_currency,
        "warnings": normalize_context_warnings([*warnings, *research_warnings]),
        "planning_defaults": {
            "years_to_retirement": settings.planner_years_to_retirement,
            "annual_contribution_usd": settings.planner_annual_contribution_usd,
            "returns": {
                "baseline": settings.planner_expected_return_baseline,
                "optimistic": settings.planner_expected_return_optimistic,
                "conservative": settings.planner_expected_return_conservative,
            },
            "inflation": settings.planner_inflation,
            "marginal_tax_rate": settings.planner_marginal_tax_rate,
            "hsa_delta_default": settings.planner_hsa_delta_default,
        },
        "financial_picture": {
            "sync_status": get_sync_status().model_dump(mode="json"),
            "snapshot_summary": snapshot_summary_payload,
            "snapshot_history": snapshot_history_payload,
            "today_dashboard": today_dashboard_payload,
            "financial_profile": financial_profile_payload,
            "onboarding_status": onboarding_payload,
            "watchlist": watchlist_payload,
        },
        "planning": {
            "active_plan": (
                {
                    "id": resolved_plan_id,
                    "title": resolved_plan_detail.get("title"),
                    "description": resolved_plan_detail.get("description"),
                    "updated_at": resolved_plan_detail.get("updated_at"),
                    "settings": resolved_plan_detail.get("settings", {}),
                }
                if isinstance(resolved_plan_detail, dict) and resolved_plan_id
                else None
            ),
            "plan_context": plan_context_payload,
            "tracking": plan_tracking_payload,
            "assumption_sets": plan_assumption_sets_payload,
            "timeline": plan_timeline_payload,
            "contribution_rules": plan_contribution_rules_payload,
            "contribution_allocation_preview": plan_contribution_allocation_preview_payload,
            "withdrawal_strategy": plan_withdrawal_strategy_payload,
            "household": plan_household_payload,
            "branch_templates": plan_branch_templates_payload,
            "baseline_projection": baseline_projection_payload,
        },
        "research": {
            "provider": settings.openbb_provider,
            "requested_symbols": requested_symbols,
            "symbols": research_symbols_for_context,
            "period": research_period_value,
            "interval": research_interval_value,
            "items": research_items,
        },
        "decisions": {
            "recommendations": recommendations_payload,
            "plan_decisions_recent": plan_decisions_payload,
        },
    }
    summary_text, summary_metadata = build_context_summary_with_metadata(
        context_payload=context_payload,
        max_chars=summary_max_chars,
    )
    context_payload["summary"] = summary_text
    context_payload["quality"] = build_context_quality(
        context_payload=context_payload,
        summary_metadata=summary_metadata,
        snapshot_stale_after_seconds=settings.copilot_context_snapshot_stale_after_seconds,
    )

    freshness_payload = context_payload["quality"].get("freshness", {})
    if (
        isinstance(freshness_payload, dict)
        and freshness_payload.get("snapshot_stale") is True
    ):
        stale_age_seconds = _coerce_float(freshness_payload.get("snapshot_age_seconds"), 0.0)
        stale_hours = max(0.0, stale_age_seconds / 3600.0)
        stale_warning = (
            "Portfolio snapshot is stale "
            f"({stale_hours:.1f}h old). Run sync or request live snapshot."
        )
        context_payload["warnings"] = normalize_context_warnings(
            [*context_payload["warnings"], stale_warning]
        )
        context_payload["quality"] = build_context_quality(
            context_payload=context_payload,
            summary_metadata=summary_metadata,
            snapshot_stale_after_seconds=settings.copilot_context_snapshot_stale_after_seconds,
        )

    shaped_payload = shape_context_payload(
        context_payload=context_payload,
        detail_level=resolved_detail_level,
    )
    validated_payload = CopilotContextResponse(**shaped_payload).model_dump(mode="json")
    runtime_telemetry_tracker.record_context_payload(validated_payload)
    return validated_payload


async def build_contextual_brief(
    use_live_snapshot: bool = False,
    plan_id: str | None = None,
    include_research: bool = False,
    include_plan_projection: bool = False,
    force_refresh: bool = False,
    research_symbols: list[str] | None = None,
    research_period: str = "6mo",
    research_interval: str = "1d",
    research_symbol_limit: int = DEFAULT_RESEARCH_SYMBOL_LIMIT,
    summary_max_chars: int = 1800,
    detail_level: str = "light",
) -> str:
    payload = await build_buildwealth_context_payload(
        use_live_snapshot=use_live_snapshot,
        plan_id=plan_id,
        include_research=include_research,
        include_plan_projection=include_plan_projection,
        force_refresh=force_refresh,
        research_symbols=research_symbols,
        research_period=research_period,
        research_interval=research_interval,
        research_symbol_limit=research_symbol_limit,
        max_recommendations=8,
        summary_max_chars=summary_max_chars,
        detail_level=detail_level,
    )
    return json.dumps(payload, indent=2, default=str)


async def assemble_copilot_context_payload(
    *,
    question: str,
    use_live_snapshot: bool = False,
    plan_id: str | None = None,
    include_research: bool = False,
    include_plan_projection: bool = False,
    force_refresh: bool = False,
    research_symbols: list[str] | None = None,
    research_period: str = "6mo",
    research_interval: str = "1d",
    research_symbol_limit: int = DEFAULT_RESEARCH_SYMBOL_LIMIT,
    summary_max_chars: int = 1800,
    detail_level: str = "light",
    services: WorkspaceServices | None = None,
) -> dict[str, Any]:
    resolved_services = workspace_services_or_legacy(services)
    symbols = normalize_research_symbols(
        research_symbols or [],
        max_symbols=max(0, min(_coerce_int(research_symbol_limit, DEFAULT_RESEARCH_SYMBOL_LIMIT), 20)),
    )
    resolved_assembler = (
        ContextAssembler(
            context_service=resolved_services.context_intelligence_service,
        )
        if isinstance(services, WorkspaceServices)
        else context_assembler
    )
    assembled = await resolved_assembler.assemble_context(
        question=question,
        plan_id=plan_id,
        symbols=symbols,
        intent=None,
        structured_context_builder=build_buildwealth_context_payload,
        builder_options={
            "use_live_snapshot": use_live_snapshot,
            "plan_id": plan_id,
            "include_research": include_research,
            "include_plan_projection": include_plan_projection,
            "force_refresh": force_refresh,
            "research_symbols": symbols,
            "research_period": research_period,
            "research_interval": research_interval,
            "research_symbol_limit": research_symbol_limit,
            "max_recommendations": 8,
            "summary_max_chars": summary_max_chars,
            "detail_level": detail_level,
            "services": resolved_services,
        },
    )
    return CopilotContextResponse(**assembled).model_dump(mode="json")


async def resolve_snapshots_for_workflow(
    use_live_snapshot: bool,
    *,
    services: WorkspaceServices | None = None,
) -> tuple[PortfolioSnapshot, PortfolioSnapshot | None]:
    resolved_services = workspace_services_or_legacy(services)
    if use_live_snapshot:
        current = await build_live_snapshot(resolved_services.portfolio_store)
        history = resolved_services.snapshot_store.recent(limit=1)
        previous = history[0] if history else None
        return current, previous

    history = resolved_services.snapshot_store.recent(limit=2)
    if not history:
        raise HTTPException(
            status_code=400,
            detail=(
                "No local snapshot is available. Run portfolio sync first or set use_live_snapshot=true."
            ),
        )

    current = history[0]
    previous = history[1] if len(history) > 1 else None
    return current, previous


async def tool_get_latest_snapshot(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    snapshot = services.snapshot_store.latest()
    return summarize_snapshot(snapshot)


async def tool_get_live_snapshot(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    snapshot = await build_live_snapshot(services.portfolio_store)
    return summarize_snapshot(snapshot)


async def tool_get_snapshot_history(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    limit_value = arguments.get("limit", 30)
    try:
        limit = max(2, min(int(limit_value), 365))
    except Exception:
        limit = 30
    return build_snapshot_history_payload(limit=limit, store=services.snapshot_store).model_dump(mode="json")


async def tool_list_import_reports(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    limit_value = arguments.get("limit", 10)
    try:
        limit = max(1, min(int(limit_value), 50))
    except Exception:
        limit = 10
    reports = services.import_workbench_store.list_reports(limit=limit)
    return {
        "reports": [
            {
                "report_id": report.get("report_id"),
                "created_at": report.get("created_at"),
                "source_file": report.get("source_file"),
                "summary": report.get("summary"),
                "imported_activities": report.get("imported_activities"),
                "affected_links": report.get("affected_links"),
            }
            for report in reports
        ]
    }


async def tool_get_import_report(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    report_id = str(arguments.get("report_id") or "").strip()
    if not report_id:
        raise ValueError("report_id is required.")
    return services.import_workbench_store.load_report(report_id)


async def tool_get_today_dashboard(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    return build_today_dashboard_response(services).model_dump(mode="json")


async def tool_get_buildwealth_context(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id_raw = arguments.get("plan_id")
    plan_id = str(plan_id_raw).strip() if isinstance(plan_id_raw, str) else ""
    use_live_snapshot = _coerce_bool(arguments.get("use_live_snapshot"), False)
    include_research = _coerce_bool(arguments.get("include_research"), True)
    include_plan_projection = _coerce_bool(arguments.get("include_plan_projection"), True)
    force_refresh = _coerce_bool(arguments.get("force_refresh"), False)
    detail_level = normalize_context_detail_level(arguments.get("detail_level"))

    symbol_limit = max(
        0,
        min(_coerce_int(arguments.get("research_symbol_limit"), DEFAULT_RESEARCH_SYMBOL_LIMIT), 20),
    )
    summary_max_chars = max(
        300,
        min(_coerce_int(arguments.get("summary_max_chars"), DEFAULT_CONTEXT_SUMMARY_MAX_CHARS), 12_000),
    )
    max_recommendations = max(1, min(_coerce_int(arguments.get("max_recommendations"), 10), 50))
    max_plan_decisions = max(1, min(_coerce_int(arguments.get("max_plan_decisions"), 8), 30))

    raw_symbols = arguments.get("research_symbols")
    if isinstance(raw_symbols, list):
        symbol_inputs = [str(item) for item in raw_symbols]
    elif isinstance(raw_symbols, str):
        symbol_inputs = [item.strip() for item in raw_symbols.split(",") if item.strip()]
    else:
        symbol_inputs = []

    payload = await build_buildwealth_context_payload(
        use_live_snapshot=use_live_snapshot,
        plan_id=(plan_id or None),
        include_research=include_research,
        force_refresh=force_refresh,
        research_symbols=normalize_research_symbols(symbol_inputs, max_symbols=symbol_limit),
        research_period=str(arguments.get("research_period") or "6mo"),
        research_interval=str(arguments.get("research_interval") or "1d"),
        include_plan_projection=include_plan_projection,
        max_recommendations=max_recommendations,
        max_plan_decisions=max_plan_decisions,
        summary_max_chars=summary_max_chars,
        research_symbol_limit=symbol_limit,
        detail_level=detail_level,
        services=services,
    )
    return payload


async def tool_search_context(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    return services.context_intelligence_service.search_context(
        query=str(arguments.get("query") or arguments.get("q") or ""),
        domains=_context_filter_values(arguments.get("domains"), arguments.get("domain")),
        plan_id=str(arguments.get("plan_id") or "").strip() or None,
        symbols=_context_filter_values(arguments.get("symbols"), arguments.get("symbol")),
        entity_types=_context_filter_values(arguments.get("entity_types"), arguments.get("entity_type")),
        recommendation_status=str(arguments.get("recommendation_status") or "").strip() or None,
        field_path=str(arguments.get("field_path") or "").strip() or None,
        limit=max(1, min(_coerce_int(arguments.get("limit"), 20), 100)),
        rebuild_if_empty=_coerce_bool(arguments.get("rebuild_if_empty"), True),
    )


async def tool_get_financial_profile(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    profile = FinancialProfileResponse(**get_financial_profile_payload(services.financial_profile_store))
    return profile.model_dump(mode="json")


async def tool_get_financial_health(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem

    profile = services.financial_profile_store.load()
    try:
        snap = services.snapshot_store.latest()
    except FileNotFoundError:
        snap = None
    return compute_financial_health(
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
        goal_items=[GoalItem(**g) for g in profile.get("goal_items", [])],
        physical_assets=[PhysicalAssetItem(**a) for a in profile.get("physical_assets", [])],
        snapshot=snap,
    ).model_dump(mode="json")


async def tool_get_goal_progress(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem

    profile = services.financial_profile_store.load()
    try:
        portfolio_value = services.snapshot_store.latest().total_value_usd
    except FileNotFoundError:
        portfolio_value = 0.0
    income_items = [IncomeItem(**i) for i in profile.get("income_items", [])]
    expense_items = [ExpenseItem(**e) for e in profile.get("expense_items", [])]
    debt_items = [DebtItem(**d) for d in profile.get("debt_items", [])]
    goal_items = [GoalItem(**g) for g in profile.get("goal_items", [])]
    monthly_surplus = (
        sum(i.monthly_amount_usd for i in income_items)
        - sum(e.monthly_amount_usd for e in expense_items)
        - sum(d.minimum_payment_usd or 0.0 for d in debt_items)
    )
    return compute_goal_progress(
        goals=goal_items,
        monthly_surplus_usd=monthly_surplus,
        portfolio_value_usd=portfolio_value,
    ).model_dump(mode="json")


async def tool_simulate_trade(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    request = SimulateTradeRequest(
        symbol=str(arguments.get("symbol", "")),
        action=str(arguments.get("action", "buy")),
        amount_usd=float(arguments.get("amount_usd", 0)),
        name=arguments.get("name"),
    )
    try:
        snap = services.snapshot_store.latest()
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="No portfolio snapshot available. Run sync first.")
    return simulate_trade(
        snapshot=snap,
        symbol=request.symbol,
        action=request.action,
        amount_usd=request.amount_usd,
        name=request.name,
    ).model_dump(mode="json")


async def tool_assess_portfolio_fit(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    request = PortfolioFitAssessmentRequest(
        symbol=str(arguments.get("symbol") or ""),
        amount_usd=(
            _coerce_float(arguments.get("amount_usd"), 0.0)
            if arguments.get("amount_usd") is not None
            else None
        ),
        proposed_account_id=(
            str(arguments.get("proposed_account_id") or "").strip()
            if arguments.get("proposed_account_id") is not None
            else None
        ),
        period=str(arguments.get("period") or "6mo"),
        interval=str(arguments.get("interval") or "1d"),
    )
    return build_portfolio_fit_assessment_payload(request, services=services).model_dump(mode="json")


async def tool_assess_affordability(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    request = AffordabilityRequest(
        description=str(arguments.get("description") or ""),
        monthly_amount_usd=arguments.get("monthly_amount_usd"),
        purchase_price_usd=arguments.get("purchase_price_usd"),
        loan_rate_pct=arguments.get("loan_rate_pct"),
        loan_term_years=arguments.get("loan_term_years"),
        down_payment_pct=arguments.get("down_payment_pct"),
    )
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, IncomeItem

    profile = services.financial_profile_store.load()
    return assess_affordability(
        description=request.description,
        monthly_amount_usd=request.monthly_amount_usd,
        purchase_price_usd=request.purchase_price_usd,
        loan_rate_pct=request.loan_rate_pct,
        loan_term_years=request.loan_term_years,
        down_payment_pct=request.down_payment_pct,
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
    ).model_dump(mode="json")


async def tool_get_onboarding_status(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    profile = get_financial_profile_payload(services.financial_profile_store)
    try:
        latest_snapshot = services.snapshot_store.latest()
    except FileNotFoundError:
        latest_snapshot = None
    return build_onboarding_status_response(
        profile_payload=profile,
        latest_snapshot=latest_snapshot,
        active_plan_detail=resolve_active_plan_detail(workspace=services.plan_workspace),
        load_fallbacks=False,
    ).model_dump(mode="json")


PROFILE_UPDATE_LIST_KEYS = (
    "income_items",
    "expense_items",
    "debt_items",
    "goal_items",
    "physical_assets",
)
PROFILE_UPDATE_ITEM_ID_PREFIXES = {
    "income_items": "income",
    "expense_items": "expense",
    "debt_items": "debt",
    "goal_items": "goal",
    "physical_assets": "asset",
}


def _normalize_profile_update_items(key: str, value: list[object]) -> list[object]:
    prefix = PROFILE_UPDATE_ITEM_ID_PREFIXES.get(key, "item")
    normalized: list[object] = []
    for raw_item in value:
        if not isinstance(raw_item, dict):
            normalized.append(raw_item)
            continue
        item = dict(raw_item)
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            item["id"] = f"{prefix}-{uuid.uuid4().hex[:10]}"
        normalized.append(item)
    return normalized


def _build_financial_profile_update_draft(
    arguments: dict[str, object],
    *,
    services: WorkspaceServices | None = None,
) -> dict[str, object]:
    resolved_services = workspace_services_or_legacy(services)
    profile_payload = get_financial_profile_payload(resolved_services.financial_profile_store)
    proposed_payload = dict(profile_payload)
    patch_payload: dict[str, object] = {}
    section_counts: dict[str, int] = {}

    for key in PROFILE_UPDATE_LIST_KEYS:
        value = arguments.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        normalized_value = _normalize_profile_update_items(key, value)
        proposed_payload[key] = normalized_value
        patch_payload[key] = normalized_value
        section_counts[key] = len(normalized_value)

    notes = arguments.get("notes")
    if notes is not None:
        proposed_payload["notes"] = str(notes)
        patch_payload["notes"] = str(notes)
        section_counts["notes"] = 1

    tax_profile = arguments.get("tax_profile")
    if tax_profile is not None:
        if not isinstance(tax_profile, dict):
            raise ValueError("tax_profile must be an object")
        merged_tax = dict(proposed_payload.get("tax_profile", {}))
        merged_tax.update(tax_profile)
        proposed_payload["tax_profile"] = merged_tax
        patch_payload["tax_profile"] = tax_profile
        section_counts["tax_profile"] = len(tax_profile)

    investment_policy = arguments.get("investment_policy")
    if investment_policy is not None:
        if not isinstance(investment_policy, dict):
            raise ValueError("investment_policy must be an object")
        merged_policy = dict(proposed_payload.get("investment_policy", {}))
        merged_policy.update(investment_policy)
        proposed_payload["investment_policy"] = merged_policy
        patch_payload["investment_policy"] = investment_policy
        section_counts["investment_policy"] = len(investment_policy)

    flags = arguments.get("flags")
    if flags is not None:
        if not isinstance(flags, dict):
            raise ValueError("flags must be an object")
        merged_flags = dict(proposed_payload.get("flags", {}))
        merged_flags.update(flags)
        proposed_payload["flags"] = merged_flags
        patch_payload["flags"] = flags
        section_counts["flags"] = len(flags)

    validated = FinancialProfileRequest(**proposed_payload)
    validated_payload = validated.model_dump(mode="json")
    draft_field_paths = patch_material_profile_field_paths(patch_payload)
    if draft_field_paths:
        validated_payload = merge_profile_metadata(
            validated_payload,
            field_paths=draft_field_paths,
            source="copilot_profile_draft",
            status="copilot_drafted",
            confidence="medium",
        )
    response_payload = {
        **validated_payload,
        "schema_version": int(profile_payload.get("schema_version") or 1),
        "updated_at": profile_payload.get("updated_at"),
    }
    proposed_profile = FinancialProfileResponse(**response_payload).model_dump(mode="json")
    section_labels = ", ".join(key.replace("_", " ") for key in section_counts) or "no sections"
    return {
        "draft_kind": "financial_profile_update",
        "summary": f"Drafted financial profile updates for {section_labels}.",
        "section_counts": section_counts,
        "patch_payload": patch_payload,
        "proposed_profile": proposed_profile,
        "current_profile": FinancialProfileResponse(**profile_payload).model_dump(mode="json"),
        "requires_confirmation": True,
    }


async def tool_draft_financial_profile_update(arguments: dict[str, object]) -> dict[str, object]:
    return _build_financial_profile_update_draft(
        arguments,
        services=workspace_services_or_legacy(None),
    )


async def tool_update_financial_profile(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    profile_payload = get_financial_profile_payload(services.financial_profile_store)

    def _merge_list(key: str) -> None:
        value = arguments.get(key)
        if value is None:
            return
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        profile_payload[key] = _normalize_profile_update_items(key, value)

    _merge_list("income_items")
    _merge_list("expense_items")
    _merge_list("debt_items")
    _merge_list("goal_items")
    _merge_list("physical_assets")

    notes = arguments.get("notes")
    if notes is not None:
        profile_payload["notes"] = str(notes)

    tax_profile = arguments.get("tax_profile")
    if tax_profile is not None:
        if not isinstance(tax_profile, dict):
            raise ValueError("tax_profile must be an object")
        merged_tax = dict(profile_payload.get("tax_profile", {}))
        merged_tax.update(tax_profile)
        profile_payload["tax_profile"] = merged_tax

    investment_policy = arguments.get("investment_policy")
    if investment_policy is not None:
        if not isinstance(investment_policy, dict):
            raise ValueError("investment_policy must be an object")
        merged_policy = dict(profile_payload.get("investment_policy", {}))
        merged_policy.update(investment_policy)
        profile_payload["investment_policy"] = merged_policy

    flags = arguments.get("flags")
    if flags is not None:
        if not isinstance(flags, dict):
            raise ValueError("flags must be an object")
        merged_flags = dict(profile_payload.get("flags", {}))
        merged_flags.update(flags)
        profile_payload["flags"] = merged_flags

    validated = FinancialProfileRequest(**profile_payload)
    saved = save_financial_profile_payload(
        validated,
        source="copilot_tool",
        profile_store=services.financial_profile_store,
    )
    _record_profile_update_activity(
        source="copilot_tool",
        sections=_profile_update_sections_from_payload(arguments),
        via_copilot=True,
    )
    return FinancialProfileResponse(**saved).model_dump(mode="json")


async def tool_list_recommendations(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    limit_value = arguments.get("limit", 50)
    try:
        limit = max(1, min(int(limit_value), 500))
    except Exception:
        limit = 50

    status = str(arguments.get("status") or "").strip().lower() or None
    plan_id = str(arguments.get("plan_id") or "").strip() or None
    include_archived = bool(arguments.get("include_archived", False))
    sort = str(arguments.get("sort") or "").strip().lower() or None
    rows = _recommendation_list(
        limit=limit,
        status=status,
        plan_id=plan_id,
        include_archived=include_archived,
        sort=sort,
        inbox=services.recommendation_inbox,
    )
    return {
        "count": len(rows),
        "recommendations": rows,
    }


async def tool_create_recommendation(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    title = str(arguments.get("title") or "").strip()
    detail = str(arguments.get("detail") or "").strip()
    if not title or not detail:
        raise ValueError("title and detail are required")

    source = str(arguments.get("source") or "copilot").strip().lower() or "copilot"
    plan_id = str(arguments.get("plan_id") or "").strip() or None
    action_payload = arguments.get("action_payload")
    payload = _prepare_recommendation_action_payload(
        source=source,
        action_payload=(action_payload if isinstance(action_payload, dict) else {}),
        plan_id=plan_id,
    )

    recommendation = services.recommendation_inbox.create(
        title=title,
        detail=detail,
        priority=str(arguments.get("priority") or "medium").strip().lower() or "medium",
        recommendation_type=str(arguments.get("recommendation_type") or "general").strip().lower() or "general",
        source=source,
        plan_id=plan_id,
        action_payload=payload,
    )
    return {"recommendation": _recommendation_item_from_row(recommendation).model_dump(mode="json")}


INVESTMENT_RESEARCH_RECOMMENDATION_SOURCE = "copilot:investment_fit"
INVESTMENT_RESEARCH_SAFE_ACTION_KINDS = {
    "review_portfolio_fit",
    "refresh_research_evidence",
    "research_dossier",
    "research_compare",
    "simulate_trade",
    "discuss_in_copilot",
    "update_profile_context",
}


def _investment_research_action_kind(value: Any) -> str:
    kind = str(value or "review_portfolio_fit").strip().lower()
    if kind not in INVESTMENT_RESEARCH_SAFE_ACTION_KINDS:
        raise ValueError(
            "Investment research recommendations must use review, compare, simulate, refresh, discuss, "
            "or context actions."
        )
    return kind


def _investment_research_text_list(value: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


async def tool_draft_investment_research_recommendation(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    symbols = normalize_research_symbols([arguments.get("symbol")], max_symbols=1)
    if not symbols:
        raise ValueError("symbol is required")
    symbol = symbols[0]

    suggested_action_kind = _investment_research_action_kind(arguments.get("suggested_action_kind"))
    priority = _normalized_recommendation_priority(arguments.get("priority"))
    plan_id = str(arguments.get("plan_id") or "").strip() or services.plan_workspace.get_active_plan_id()
    fit_status = str(arguments.get("fit_status") or "").strip().lower()
    freshness_status = str(arguments.get("freshness_status") or "").strip().lower() or "unknown"
    confidence = str(arguments.get("confidence") or "").strip().lower() or "medium"
    blocking_gaps = _investment_research_text_list(arguments.get("blocking_gaps"))
    actionability = (
        "context_gathering"
        if suggested_action_kind in {"refresh_research_evidence", "update_profile_context"}
        else "review_only"
    )
    quality_blocking_context = blocking_gaps if actionability == "context_gathering" else []
    fit_reasons = _investment_research_text_list(arguments.get("fit_reasons"))
    fit_risks = _investment_research_text_list(arguments.get("fit_risks"))
    source_recommendation_id = str(arguments.get("source_recommendation_id") or "").strip() or None
    detail = str(arguments.get("detail") or "").strip()
    if not detail:
        detail = (
            f"Review {symbol} with portfolio-fit context, research evidence freshness, and any blocking gaps "
            "before making a portfolio decision."
        )
    title = str(arguments.get("title") or "").strip() or f"Review investment fit for {symbol}"
    generated_at = context_utc_now_iso()

    evidence = {
        "summary": detail,
        "data_keys": [
            "portfolio.fit_assessment",
            "research.evidence_packet",
            "copilot.investment_fit_discussion",
        ],
        "symbol": symbol,
        "research_symbols": [symbol],
        "research_evidence_packet_id": str(arguments.get("research_evidence_packet_id") or "").strip() or None,
        "provider": str(arguments.get("provider") or "").strip() or None,
        "freshness_status": freshness_status,
        "confidence": confidence,
        "coverage_score": arguments.get("coverage_score"),
        "fit_status": fit_status or None,
        "fit_score": arguments.get("fit_score"),
        "fit_reasons": fit_reasons,
        "fit_risks": fit_risks,
        "blocking_gaps": blocking_gaps,
        "source_recommendation_id": source_recommendation_id,
    }
    evidence = {key: value for key, value in evidence.items() if value is not None}
    suggested_action = {
        "kind": suggested_action_kind,
        "symbol": symbol,
        "fit_status": fit_status or None,
        "source": "copilot_investment_fit_discussion",
    }
    suggested_action = {key: value for key, value in suggested_action.items() if value is not None}
    expected_outcome = {
        "expected_delta_context_quality": "research_or_fit_reviewed",
        "expected_next_safe_action": suggested_action_kind,
    }
    quality = {
        "schema_version": 1,
        "source": INVESTMENT_RESEARCH_RECOMMENDATION_SOURCE,
        "confidence_level": confidence if confidence in {"high", "medium", "low"} else "medium",
        "confidence_score": {"high": 0.85, "medium": 0.65, "low": 0.4}.get(confidence, 0.65),
        "confidence_reasons": [
            "Drafted by Copilot from an investment-fit discussion.",
            "Action is limited to review, compare, simulate, refresh, discuss, or context gathering.",
        ],
        "freshness_status": freshness_status,
        "freshness_reasons": [
            f"Research evidence freshness was reported as {freshness_status}.",
        ],
        "actionability": actionability,
        "actionability_reasons": [
            "This recommendation should be reviewed before any portfolio state change is made."
            if actionability == "review_only"
            else "This recommendation gathers or refreshes context before stronger advice is generated."
        ],
        "reversibility": "high",
        "impact": {
            "level": "high" if priority == "high" else ("medium" if priority == "medium" else "low"),
            "summary": detail,
        },
        "blocking_context": quality_blocking_context,
        "decision_grade": (
            freshness_status not in {"unknown", "stale", "degraded", "unavailable"}
            and not quality_blocking_context
        ),
        "suggested_action_kind": suggested_action_kind,
        "calibration": {
            "domain": "investment_research",
            "track_process_outcome": True,
            "process_outcomes": sorted(INVESTMENT_RESEARCH_PROCESS_OUTCOMES),
        },
    }
    action_payload = {
        "generator": {
            "id": "copilot_investment_fit_draft",
            "version": "v1",
            "generated_at": generated_at,
            "signal_type": "investment_fit_discussion",
            "signal_key": f"{symbol}:{suggested_action_kind}",
            "source_recommendation_id": source_recommendation_id,
        },
        "evidence": evidence,
        "suggested_action": suggested_action,
        "expected_outcome": expected_outcome,
        "quality": quality,
        "research_symbols": [symbol],
    }
    prepared_payload = _prepare_recommendation_action_payload(
        source=INVESTMENT_RESEARCH_RECOMMENDATION_SOURCE,
        action_payload=action_payload,
        plan_id=plan_id,
    )
    recommendation = services.recommendation_inbox.create(
        title=title,
        detail=detail,
        priority=priority,
        recommendation_type="workflow_action",
        source=INVESTMENT_RESEARCH_RECOMMENDATION_SOURCE,
        plan_id=plan_id,
        action_payload=prepared_payload,
    )
    return {
        "draft_kind": "investment_research_recommendation",
        "requires_review": True,
        "safe_action_kinds": sorted(INVESTMENT_RESEARCH_SAFE_ACTION_KINDS),
        "recommendation": _recommendation_item_from_row(recommendation).model_dump(mode="json"),
    }


def _watchlist_item_for_symbol(
    symbol: str,
    data_source: str = "OPENBB",
    *,
    store: PortfolioStore | None = None,
) -> dict[str, Any] | None:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_source = str(data_source or "OPENBB").strip().upper() or "OPENBB"
    if not normalized_symbol:
        return None
    resolved_store = store or portfolio_store
    for item in resolved_store.list_watchlist():
        if not isinstance(item, dict):
            continue
        if str(item.get("symbol") or "").strip().upper() != normalized_symbol:
            continue
        if str(item.get("data_source") or "OPENBB").strip().upper() != normalized_source:
            continue
        return item
    return None


def _revision_text_list(value: Any, *, limit: int = 6) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
        if len(out) >= limit:
            break
    return out


async def tool_draft_watchlist_thesis_revision(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    symbols = normalize_research_symbols([arguments.get("symbol")], max_symbols=1)
    if not symbols:
        raise ValueError("symbol is required")
    symbol = symbols[0]
    proposed_thesis = str(arguments.get("proposed_thesis") or "").strip()
    if not proposed_thesis:
        raise ValueError("proposed_thesis is required")
    data_source = str(arguments.get("data_source") or "OPENBB").strip().upper() or "OPENBB"
    current = _watchlist_item_for_symbol(symbol, data_source, store=services.portfolio_store) or {}

    proposed: dict[str, Any] = {
        "thesis": proposed_thesis,
        "note": str(arguments.get("proposed_note") or "").strip(),
        "reference_price_usd": _coerce_optional_float(arguments.get("reference_price_usd")),
        "review_window_days": max(1, min(int(arguments.get("review_window_days") or TODAY_THESIS_REVIEW_DAYS), 3650)),
    }
    proposed = {key: value for key, value in proposed.items() if value not in (None, "")}
    tags = arguments.get("tags")
    if isinstance(tags, list):
        proposed["tags"] = [str(item).strip().lower() for item in tags if str(item).strip()][:20]

    return {
        "draft_kind": "watchlist_thesis_revision",
        "requires_confirmation": True,
        "target": {
            "type": "watchlist",
            "symbol": symbol,
            "data_source": data_source,
        },
        "current": {
            "thesis": str(current.get("thesis") or ""),
            "note": str(current.get("note") or ""),
            "reference_price_usd": _coerce_optional_float(current.get("thesis_reference_price_usd")),
            "reviewed_at": str(current.get("thesis_reviewed_at") or ""),
            "expires_at": str(current.get("thesis_expires_at") or ""),
            "tags": current.get("tags") if isinstance(current.get("tags"), list) else [],
        },
        "proposed": proposed,
        "rationale": str(arguments.get("rationale") or "").strip(),
        "evidence_gaps": _revision_text_list(arguments.get("evidence_gaps")),
        "warnings": _revision_text_list(arguments.get("warnings")),
    }


async def tool_draft_dossier_thesis_revision(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = str(arguments.get("plan_id") or "").strip()
    artifact_id = str(arguments.get("artifact_id") or "").strip()
    proposed_thesis = str(arguments.get("proposed_thesis") or "").strip()
    if not plan_id:
        raise ValueError("plan_id is required")
    if not artifact_id:
        raise ValueError("artifact_id is required")
    if not proposed_thesis:
        raise ValueError("proposed_thesis is required")

    artifact = services.plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
    metadata = _extract_thesis_review_metadata_from_markdown(artifact.get("content"))
    proposed: dict[str, Any] = {
        "thesis": proposed_thesis,
        "reference_price_usd": _coerce_optional_float(arguments.get("reference_price_usd")),
        "review_window_days": max(1, min(int(arguments.get("review_window_days") or TODAY_THESIS_REVIEW_DAYS), 3650)),
    }
    proposed = {key: value for key, value in proposed.items() if value not in (None, "")}
    return {
        "draft_kind": "dossier_thesis_revision",
        "requires_confirmation": True,
        "target": {
            "type": "dossier",
            "plan_id": plan_id,
            "artifact_id": artifact_id,
            "title": artifact.get("title") or artifact_id,
        },
        "current": {
            "thesis": _extract_markdown_section(artifact.get("content"), "Thesis"),
            "reference_price_usd": _coerce_optional_float(metadata.get("reference_price_usd")),
            "reviewed_at": str(metadata.get("reviewed_at") or ""),
            "expires_at": str(metadata.get("expires_at") or ""),
        },
        "proposed": proposed,
        "rationale": str(arguments.get("rationale") or "").strip(),
        "evidence_gaps": _revision_text_list(arguments.get("evidence_gaps")),
        "warnings": _revision_text_list(arguments.get("warnings")),
    }


async def tool_apply_recommendation(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    recommendation_id = str(arguments.get("recommendation_id") or "").strip()
    if not recommendation_id:
        raise ValueError("recommendation_id is required")

    payload = RecommendationApplyRequest(
        plan_id=(str(arguments.get("plan_id") or "").strip() or None),
        plan_settings_updates=(
            arguments.get("plan_settings_updates")
            if isinstance(arguments.get("plan_settings_updates"), dict)
            else {}
        ),
        rationale=str(arguments.get("rationale") or ""),
        decision_status=str(arguments.get("decision_status") or "accepted"),
        create_decision_packet=_coerce_bool(arguments.get("create_decision_packet"), True),
        capture_scenario_diff=_coerce_bool(arguments.get("capture_scenario_diff"), True),
        decision_packet_research_symbols=(
            [str(item) for item in arguments.get("decision_packet_research_symbols")]
            if isinstance(arguments.get("decision_packet_research_symbols"), list)
            else []
        ),
        pin_research_bridge=_coerce_bool(arguments.get("pin_research_bridge"), True),
        research_bridge_symbols=(
            [str(item) for item in arguments.get("research_bridge_symbols")]
            if isinstance(arguments.get("research_bridge_symbols"), list)
            else []
        ),
        research_bridge_template_id=(str(arguments.get("research_bridge_template_id") or "").strip() or None),
        research_bridge_assumption_set_id=(
            str(arguments.get("research_bridge_assumption_set_id") or "").strip() or None
        ),
    )
    result = (
        await apply_recommendation_with_decision_packet(recommendation_id, payload, services=services)
        if has_active_copilot_workspace_context()
        else await apply_recommendation_with_decision_packet(recommendation_id, payload)
    )
    _record_copilot_recommendation_apply_activity(result, arguments)
    return result.model_dump(mode="json")


async def tool_preview_recommendation(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    recommendation_id = str(arguments.get("recommendation_id") or "").strip()
    if not recommendation_id:
        raise ValueError("recommendation_id is required")

    payload = RecommendationPreviewRequest(
        plan_id=(str(arguments.get("plan_id") or "").strip() or None),
        plan_settings_updates=(
            arguments.get("plan_settings_updates")
            if isinstance(arguments.get("plan_settings_updates"), dict)
            else {}
        ),
        capture_scenario_diff=_coerce_bool(arguments.get("capture_scenario_diff"), True),
        decision_status=str(arguments.get("decision_status") or "accepted").strip() or "accepted",
    )
    result = (
        await preview_recommendation(recommendation_id, payload, services=services)
        if has_active_copilot_workspace_context()
        else await preview_recommendation(recommendation_id, payload)
    )
    return result.model_dump(mode="json")


async def tool_reject_recommendation(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    recommendation_id = str(arguments.get("recommendation_id") or "").strip()
    if not recommendation_id:
        raise ValueError("recommendation_id is required")
    reason = str(arguments.get("reason") or "").strip()
    reject_kwargs = {
        "plan_id": (str(arguments.get("plan_id") or "").strip() or None),
        "reason": reason,
        "capture_scenario_diff": _coerce_bool(arguments.get("capture_scenario_diff"), True),
        "create_decision_packet": _coerce_bool(arguments.get("create_decision_packet"), False),
        "decision_packet_research_symbols": (
            [str(item) for item in arguments.get("decision_packet_research_symbols")]
            if isinstance(arguments.get("decision_packet_research_symbols"), list)
            else []
        ),
    }
    if has_active_copilot_workspace_context():
        reject_kwargs["services"] = services
    result = await reject_recommendation(recommendation_id, **reject_kwargs)
    return result.model_dump(mode="json")


async def tool_update_recommendation_outcome(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    recommendation_id = str(arguments.get("recommendation_id") or "").strip()
    if not recommendation_id:
        raise ValueError("recommendation_id is required")

    request = RecommendationOutcomeUpdateRequest(
        plan_id=(str(arguments.get("plan_id") or "").strip() or None),
        realized_delta_future_value_usd=_coerce_optional_float(arguments.get("realized_delta_future_value_usd")),
        realized_delta_real_value_usd=_coerce_optional_float(arguments.get("realized_delta_real_value_usd")),
        observed_at=(
            datetime.fromisoformat(str(arguments.get("observed_at")).replace("Z", "+00:00"))
            if arguments.get("observed_at")
            else None
        ),
        observation_window_days=(
            _coerce_int(arguments.get("observation_window_days"), 0)
            if arguments.get("observation_window_days") is not None
            else None
        ),
        measurement_source=str(arguments.get("measurement_source") or ""),
        note=str(arguments.get("note") or ""),
        process_outcome=str(arguments.get("process_outcome") or ""),
        evidence_sufficiency=str(arguments.get("evidence_sufficiency") or ""),
    )
    result = (
        update_recommendation_outcome(recommendation_id, request, services=services)
        if has_active_copilot_workspace_context()
        else update_recommendation_outcome(recommendation_id, request)
    )
    return result.model_dump(mode="json")


async def tool_get_recommendation_closure_analytics(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    limit = max(1, min(_coerce_int(arguments.get("limit"), 200), 1000))
    raw_statuses = arguments.get("statuses")
    statuses: list[str] | str | None
    if isinstance(raw_statuses, list):
        statuses = [str(item or "") for item in raw_statuses]
    elif isinstance(raw_statuses, str):
        statuses = raw_statuses
    else:
        statuses = None
    include_pending_realized = _coerce_bool(arguments.get("include_pending_realized"), True)
    kwargs: dict[str, Any] = {
        "limit": limit,
        "statuses": statuses,
        "include_pending_realized": include_pending_realized,
    }
    plan_id = str(arguments.get("plan_id") or "").strip()
    if plan_id:
        kwargs["plan_id"] = plan_id
    if has_active_copilot_workspace_context():
        kwargs["inbox"] = services.recommendation_inbox
    return build_recommendation_closure_analytics_payload(**kwargs)


async def tool_create_plan_recommendation_closure_summary(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_copilot_tool_plan_id(arguments.get("plan_id"), services=services)
    limit = max(1, min(_coerce_int(arguments.get("limit"), 200), 1000))
    raw_statuses = arguments.get("statuses")
    statuses: list[str] = []
    if isinstance(raw_statuses, list):
        statuses = [str(item or "") for item in raw_statuses]
    elif isinstance(raw_statuses, str):
        statuses = [item.strip() for item in raw_statuses.split(",") if item.strip()]
    if not statuses:
        statuses = ["applied", "rejected"]

    request = PlanRecommendationClosureSummaryRequest(
        limit=limit,
        statuses=statuses,
        include_pending_realized=_coerce_bool(arguments.get("include_pending_realized"), True),
        write_artifact=_coerce_bool(arguments.get("write_artifact"), True),
    )
    response = (
        create_plan_recommendation_closure_summary(plan_id=plan_id, request=request, services=services)
        if has_active_copilot_workspace_context()
        else create_plan_recommendation_closure_summary(plan_id=plan_id, request=request)
    )
    return response.model_dump(mode="json")


async def tool_pin_watchlist_research_to_plan(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_copilot_tool_plan_id(arguments.get("plan_id"), services=services)
    raw_symbols = arguments.get("symbols")
    symbols: list[str]
    if isinstance(raw_symbols, list):
        symbols = [str(item) for item in raw_symbols]
    elif isinstance(raw_symbols, str):
        symbols = [item.strip() for item in raw_symbols.split(",") if item.strip()]
    else:
        symbols = []

    request = PlanResearchBridgeRequest(
            branch_template_id=(str(arguments.get("branch_template_id") or "").strip() or None),
            template_name=(str(arguments.get("template_name") or "").strip() or None),
            branch_name=(str(arguments.get("branch_name") or "").strip() or None),
            assumption_set_id=(str(arguments.get("assumption_set_id") or "").strip() or None),
            symbols=symbols,
            max_symbols=max(1, min(_coerce_int(arguments.get("max_symbols"), 5), 20)),
    )
    response = (
        pin_watchlist_research_bridge(plan_id=plan_id, request=request, services=services)
        if has_active_copilot_workspace_context()
        else pin_watchlist_research_bridge(plan_id=plan_id, request=request)
    )
    return response.model_dump(mode="json")


async def tool_run_sync(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    async with sync_lock:
        sync_state["running"] = True
        sync_state["last_trigger"] = "copilot-tool"
        sync_state["last_started_at"] = utc_now()
        sync_state["last_error"] = None
        try:
            snapshot = await build_live_snapshot(services.portfolio_store)
            snapshot_path = services.snapshot_store.write(snapshot)
            sync_state["last_snapshot_path"] = str(snapshot_path)
            sync_state["last_completed_at"] = utc_now()
            return {"snapshot": str(snapshot_path)}
        except Exception as exc:
            sync_state["runs_failed"] = int(sync_state["runs_failed"]) + 1
            sync_state["last_error"] = str(exc)
            sync_state["last_completed_at"] = utc_now()
            raise
        finally:
            sync_state["runs_total"] = int(sync_state["runs_total"]) + 1
            sync_state["running"] = False


async def tool_get_sync_status(_: dict[str, object]) -> dict[str, object]:
    return get_sync_status().model_dump(mode="json")


async def tool_run_planning(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    current_value = arguments.get("current_portfolio_value_usd")
    annual_contribution = arguments.get("annual_contribution_usd")
    years = arguments.get("years")
    hsa_extra = arguments.get("hsa_extra_contribution_usd")
    state_tax_rate = arguments.get("state_tax_rate")
    include_irmaa = _coerce_bool(arguments.get("include_irmaa"), True)
    roth_conversion_annual_amount = arguments.get("roth_conversion_annual_amount_usd")
    roth_conversion_start_age = arguments.get("roth_conversion_start_age")
    roth_conversion_end_age = arguments.get("roth_conversion_end_age")
    drawdown_order = str(arguments.get("drawdown_order") or "").strip() or None
    simulation_mode = _normalize_optional_simulation_mode(arguments.get("simulation_mode"))
    simulation_monte_carlo_variant = _normalize_optional_simulation_monte_carlo_variant(
        arguments.get("simulation_monte_carlo_variant")
    )
    simulation_historical_start_year = _normalize_optional_simulation_int(
        arguments.get("simulation_historical_start_year"),
        minimum=min(HISTORICAL_YEARS),
        maximum=max(HISTORICAL_YEARS),
    )
    simulation_seed_raw = arguments.get("simulation_seed")
    if simulation_seed_raw is None or (
        isinstance(simulation_seed_raw, str) and not simulation_seed_raw.strip()
    ):
        simulation_seed = None
    else:
        simulation_seed = _normalize_optional_simulation_int(
            simulation_seed_raw,
            minimum=0,
            maximum=2_147_483_647,
        )
        if simulation_seed is None:
            simulation_seed = DEFAULT_SIMULATION_SEED

    if current_value is None:
        current_value = services.snapshot_store.latest().total_value_usd

    resolved_roth_conversion_start_age: int | None = None
    resolved_roth_conversion_end_age: int | None = None
    if roth_conversion_start_age is not None:
        resolved_roth_conversion_start_age = max(
            0,
            min(120, _coerce_int(roth_conversion_start_age, 0)),
        )
    if roth_conversion_end_age is not None:
        resolved_roth_conversion_end_age = max(
            0,
            min(120, _coerce_int(roth_conversion_end_age, 0)),
        )
    if (
        resolved_roth_conversion_start_age is not None
        and resolved_roth_conversion_end_age is not None
        and resolved_roth_conversion_start_age > resolved_roth_conversion_end_age
    ):
        resolved_roth_conversion_start_age, resolved_roth_conversion_end_age = (
            resolved_roth_conversion_end_age,
            resolved_roth_conversion_start_age,
        )

    result = scenario_engine.run(
        current_portfolio_value_usd=float(current_value),
        annual_contribution_usd=(float(annual_contribution) if annual_contribution is not None else None),
        years=(int(years) if years is not None else None),
        hsa_extra_contribution_usd=(float(hsa_extra) if hsa_extra is not None else None),
        state_tax_rate=(
            max(0.0, min(1.0, _coerce_float(state_tax_rate, 0.0)))
            if state_tax_rate is not None
            else None
        ),
        include_irmaa=include_irmaa,
        roth_conversion_annual_amount_usd=(
            max(0.0, _coerce_float(roth_conversion_annual_amount, 0.0))
            if roth_conversion_annual_amount is not None
            else None
        ),
        roth_conversion_start_age=resolved_roth_conversion_start_age,
        roth_conversion_end_age=resolved_roth_conversion_end_age,
        drawdown_order=drawdown_order,
        simulation_mode=simulation_mode,
        simulation_monte_carlo_variant=simulation_monte_carlo_variant,
        simulation_historical_start_year=simulation_historical_start_year,
        simulation_seed=simulation_seed,
    )
    return result.model_dump(mode="json")


async def tool_project_income(arguments: dict[str, object]) -> dict[str, object]:
    years_raw = arguments.get("years")
    years = _coerce_int(years_raw, settings.planner_years_to_retirement)
    years = max(1, min(years, 80))

    start_year_raw = arguments.get("start_year")
    start_year = _coerce_int(start_year_raw, utc_now().year)
    start_year = max(1900, min(start_year, 2500))

    default_growth_raw = arguments.get("default_annual_growth_rate")
    default_growth = settings.planner_inflation if default_growth_raw is None else _coerce_float(
        default_growth_raw,
        settings.planner_inflation,
    )
    default_growth = max(-1.0, min(1.0, default_growth))

    income_items_raw = arguments.get("income_items")
    if isinstance(income_items_raw, list):
        income_items = [item for item in income_items_raw if isinstance(item, dict)]
    else:
        profile_payload = get_financial_profile_payload()
        profile_items = profile_payload.get("income_items")
        income_items = profile_items if isinstance(profile_items, list) else []

    payload = project_income_schedule(
        income_items,
        start_year=start_year,
        years=years,
        default_annual_growth_rate=default_growth,
    )
    return IncomeProjectionResponse(**payload).model_dump(mode="json")


async def tool_project_expenses(arguments: dict[str, object]) -> dict[str, object]:
    years_raw = arguments.get("years")
    years = _coerce_int(years_raw, settings.planner_years_to_retirement)
    years = max(1, min(years, 80))

    start_year_raw = arguments.get("start_year")
    start_year = _coerce_int(start_year_raw, utc_now().year)
    start_year = max(1900, min(start_year, 2500))

    default_rate_raw = arguments.get("default_inflation_rate")
    default_rate = settings.planner_inflation if default_rate_raw is None else _coerce_float(
        default_rate_raw,
        settings.planner_inflation,
    )
    default_rate = max(-1.0, min(1.0, default_rate))

    expense_items_raw = arguments.get("expense_items")
    if isinstance(expense_items_raw, list):
        expense_items = [item for item in expense_items_raw if isinstance(item, dict)]
    else:
        profile_payload = get_financial_profile_payload()
        profile_items = profile_payload.get("expense_items")
        expense_items = profile_items if isinstance(profile_items, list) else []

    payload = project_expense_schedule(
        expense_items,
        start_year=start_year,
        years=years,
        default_inflation_rate=default_rate,
    )
    return ExpenseProjectionResponse(**payload).model_dump(mode="json")


async def tool_project_debt_payoff(arguments: dict[str, object]) -> dict[str, object]:
    max_years_raw = arguments.get("max_years")
    max_years = _coerce_int(max_years_raw, settings.planner_years_to_retirement)
    max_years = max(1, min(max_years, 80))

    start_date_value = arguments.get("start_date")
    start_date = _coerce_optional_date(start_date_value) or utc_now().date().replace(day=1)

    strategy = str(arguments.get("strategy") or "minimum").strip().lower() or "minimum"
    if strategy not in {"minimum", "snowball", "avalanche", "custom"}:
        raise ValueError("strategy must be one of: minimum, snowball, avalanche, custom")

    extra_payment = _coerce_float(arguments.get("monthly_accelerated_payment_usd"), 0.0)
    extra_payment = max(0.0, extra_payment)

    debt_items_raw = arguments.get("debt_items")
    if isinstance(debt_items_raw, list):
        debt_items = [item for item in debt_items_raw if isinstance(item, dict)]
    else:
        profile_payload = get_financial_profile_payload()
        profile_items = profile_payload.get("debt_items")
        debt_items = profile_items if isinstance(profile_items, list) else []

    payload = project_debt_payoff(
        debt_items,
        start_date=start_date,
        max_years=max_years,
        strategy=strategy,  # type: ignore[arg-type]
        monthly_accelerated_payment_usd=extra_payment,
    )
    return DebtProjectionResponse(**payload).model_dump(mode="json")


async def tool_project_social_security(arguments: dict[str, object]) -> dict[str, object]:
    years_raw = arguments.get("years")
    years = _coerce_int(years_raw, settings.planner_years_to_retirement)
    years = max(1, min(years, 80))

    start_year_raw = arguments.get("start_year")
    start_year = _coerce_int(start_year_raw, utc_now().year)
    start_year = max(1900, min(start_year, 2500))

    current_age = _coerce_int(arguments.get("current_age"), 35)
    current_age = max(0, min(current_age, 120))

    claiming_age_raw = arguments.get("claiming_age")
    claiming_age = (
        None
        if claiming_age_raw is None
        else max(62, min(_coerce_int(claiming_age_raw, 67), 70))
    )

    birth_year_raw = arguments.get("birth_year")
    birth_year = (
        None
        if birth_year_raw is None
        else max(1900, min(_coerce_int(birth_year_raw, 0), 2500))
    )

    life_expectancy_raw = arguments.get("life_expectancy_age")
    life_expectancy_age = (
        None
        if life_expectancy_raw is None
        else max(67, min(_coerce_int(life_expectancy_raw, 90), 120))
    )

    fra_monthly_raw = arguments.get("fra_monthly_benefit_usd")
    fra_monthly_benefit_usd = (
        None
        if fra_monthly_raw is None
        else max(0.0, _coerce_float(fra_monthly_raw, 0.0))
    )

    estimated_earnings_raw = arguments.get("estimated_annual_earnings_usd")
    estimated_annual_earnings_usd = (
        None
        if estimated_earnings_raw is None
        else max(0.0, _coerce_float(estimated_earnings_raw, 0.0))
    )

    earnings_history_raw = arguments.get("earnings_history")
    earnings_history = [item for item in earnings_history_raw if isinstance(item, dict)] if isinstance(
        earnings_history_raw, list
    ) else []

    if estimated_annual_earnings_usd is None and not earnings_history:
        profile_payload = get_financial_profile_payload()
        income_rows = profile_payload.get("income_items")
        if isinstance(income_rows, list):
            estimated_annual_earnings_usd = max(
                0.0,
                sum(
                    max(0.0, _coerce_float(item.get("monthly_amount_usd"), 0.0))
                    for item in income_rows
                    if isinstance(item, dict)
                )
                * 12.0,
            )

    claim_age_options_raw = arguments.get("claim_age_options")
    claim_age_options = None
    if isinstance(claim_age_options_raw, list):
        claim_age_options = [max(62, min(_coerce_int(item, 67), 70)) for item in claim_age_options_raw]

    cola_rate = _coerce_float(arguments.get("cola_rate"), settings.planner_inflation)
    pia_bend_point_1_usd = max(1.0, _coerce_float(arguments.get("pia_bend_point_1_usd"), 1226.0))
    pia_bend_point_2_usd = max(
        pia_bend_point_1_usd,
        _coerce_float(arguments.get("pia_bend_point_2_usd"), 7391.0),
    )

    payload = project_social_security_income(
        start_year=start_year,
        years=years,
        current_age=current_age,
        claiming_age=claiming_age,
        life_expectancy_age=life_expectancy_age,
        birth_year=birth_year,
        fra_monthly_benefit_usd=fra_monthly_benefit_usd,
        estimated_annual_earnings_usd=estimated_annual_earnings_usd,
        earnings_history=earnings_history,
        cola_rate=cola_rate,
        claim_age_options=claim_age_options,
        pia_bend_point_1_usd=pia_bend_point_1_usd,
        pia_bend_point_2_usd=pia_bend_point_2_usd,
    )
    return SocialSecurityProjectionResponse(**payload).model_dump(mode="json")


async def tool_project_rmd(arguments: dict[str, object]) -> dict[str, object]:
    years_raw = arguments.get("years")
    years = _coerce_int(years_raw, settings.planner_years_to_retirement)
    years = max(1, min(years, 80))

    start_year_raw = arguments.get("start_year")
    start_year = _coerce_int(start_year_raw, utc_now().year)
    start_year = max(1900, min(start_year, 2500))

    current_age = _coerce_int(arguments.get("current_age"), 35)
    current_age = max(0, min(current_age, 120))

    birth_year_raw = arguments.get("birth_year")
    birth_year = (
        None
        if birth_year_raw is None
        else max(1900, min(_coerce_int(birth_year_raw, 0), 2500))
    )

    start_age_override_raw = arguments.get("start_age_override")
    start_age_override = (
        None
        if start_age_override_raw is None
        else max(72, min(_coerce_int(start_age_override_raw, 73), 120))
    )

    expected_return = _coerce_float(arguments.get("expected_return"), settings.planner_expected_return_baseline)
    expected_return = max(-0.95, min(expected_return, 1.0))

    accounts_raw = arguments.get("accounts")
    if isinstance(accounts_raw, list):
        accounts = [item for item in accounts_raw if isinstance(item, dict)]
    else:
        accounts = build_planning_accounts_from_portfolio()

    payload = project_rmd_schedule(
        accounts=accounts,
        start_year=start_year,
        years=years,
        current_age=current_age,
        birth_year=birth_year,
        expected_return=expected_return,
        start_age_override=start_age_override,
    )
    return RmdProjectionResponse(**payload).model_dump(mode="json")


async def tool_research_options_chain(arguments: dict[str, object]) -> dict[str, object]:
    symbol = str(arguments.get("symbol", "AAPL")).strip().upper()
    result = research_service.options_chain(symbol).model_dump(mode="json")
    records = result.get("records", [])
    if isinstance(records, list):
        result["records"] = records[:25]
        result["records_truncated"] = max(0, len(records) - 25)
    return result


async def tool_research_quote(arguments: dict[str, object]) -> dict[str, object]:
    symbol = str(arguments.get("symbol", "AAPL")).strip().upper()
    result = research_service.quote(symbol).model_dump(mode="json")
    records = result.get("records", [])
    if isinstance(records, list):
        result["records"] = records[:25]
        result["records_truncated"] = max(0, len(records) - 25)
    return result


async def tool_research_price_history(arguments: dict[str, object]) -> dict[str, object]:
    symbol = str(arguments.get("symbol", "AAPL")).strip().upper()
    period = str(arguments.get("period", "1y")).strip() or "1y"
    interval = str(arguments.get("interval", "1d")).strip() or "1d"
    result = research_service.price_history(
        symbol=symbol,
        period=period,
        interval=interval,
    ).model_dump(mode="json")
    records = result.get("records", [])
    if isinstance(records, list):
        result["records"] = records[:50]
        result["records_truncated"] = max(0, len(records) - 50)
    return result


async def tool_research_compare(arguments: dict[str, object]) -> dict[str, object]:
    symbols_raw = arguments.get("symbols")
    symbols: list[str] = []
    if isinstance(symbols_raw, list):
        symbols = [str(item or "").strip().upper() for item in symbols_raw]
    elif isinstance(symbols_raw, str):
        symbols = [item.strip().upper() for item in symbols_raw.split(",")]

    symbols = [symbol for symbol in symbols if symbol]
    if len(symbols) < 2:
        symbols = ["AAPL", "MSFT"]

    period = str(arguments.get("period", "6mo")).strip() or "6mo"
    interval = str(arguments.get("interval", "1d")).strip() or "1d"
    baseline_symbol = str(arguments.get("baseline_symbol") or "").strip().upper() or None

    result = research_service.compare(
        symbols=symbols,
        period=period,
        interval=interval,
        baseline_symbol=baseline_symbol,
    ).model_dump(mode="json")
    items = result.get("items", [])
    if isinstance(items, list):
        result["items"] = items[:20]
        result["items_truncated"] = max(0, len(items) - 20)
    return result


def _portfolio_symbol_weights_pct(
    store: PortfolioStore | None = None,
) -> dict[str, float]:
    resolved_store = store or portfolio_store
    holdings_payload = resolved_store.get_holdings()
    by_symbol_raw = holdings_payload.get("holdings_by_symbol")
    by_symbol = by_symbol_raw if isinstance(by_symbol_raw, dict) else {}

    total_value = _coerce_float(holdings_payload.get("total_portfolio_value"), 0.0)
    if total_value <= 0:
        total_value = sum(
            _coerce_float(item.get("current_value"), 0.0)
            for item in by_symbol.values()
            if isinstance(item, dict)
        )
    if total_value <= 0:
        return {}

    weights: dict[str, float] = {}
    for raw_symbol, raw_row in by_symbol.items():
        row = raw_row if isinstance(raw_row, dict) else {}
        symbol = str(raw_symbol or row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        value = _coerce_float(row.get("current_value"), 0.0)
        if value <= 0:
            continue
        weights[symbol] = round((value / total_value) * 100.0, 4)
    return weights


def build_research_dossier_payload(
    *,
    symbols: list[str],
    period: str,
    interval: str,
    baseline_symbol: str | None,
    thesis: str,
    risks: list[str],
    catalysts: list[str],
    plan_id: str | None,
    save_to_plan: bool,
    include_portfolio_fit: bool,
    services: WorkspaceServices | None = None,
) -> ResearchDossierResponse:
    resolved_services = workspace_services_or_legacy(services)
    portfolio_weights_pct = (
        _portfolio_symbol_weights_pct(resolved_services.portfolio_store)
        if include_portfolio_fit
        else {}
    )

    response = research_service.dossier(
        symbols=symbols,
        period=period,
        interval=interval,
        baseline_symbol=baseline_symbol,
        thesis=thesis,
        risks=risks,
        catalysts=catalysts,
        include_portfolio_fit=include_portfolio_fit,
        portfolio_weights_pct=portfolio_weights_pct,
    )

    if not save_to_plan:
        return response

    artifact_warnings = list(response.warnings)
    resolved_plan_id: str | None = None
    if plan_id:
        resolved_plan_id = plan_id
    else:
        try:
            resolved_plan_id = resolve_plan_id_or_active(
                None,
                workspace=resolved_services.plan_workspace,
            )
        except ValueError as exc:
            artifact_warnings.append(f"Dossier not saved to plan: {exc}")

    if resolved_plan_id:
        try:
            artifact_payload = resolved_services.plan_workspace.write_artifact(
                plan_id=resolved_plan_id,
                title=f"Research Dossier - {' vs '.join(response.symbols[:3])}",
                markdown=response.dossier_markdown,
                kind="research_dossier",
            )
            artifact_payload["plan_id"] = resolved_plan_id
            response.artifact = artifact_payload
        except PlanNotFoundError as exc:
            artifact_warnings.append(f"Dossier not saved to plan: {exc}")

    response.warnings = normalize_context_warnings(artifact_warnings, max_warnings=80)
    return response


def _normalize_text_list_argument(raw_value: object, *, limit: int = 12) -> list[str]:
    values: list[str] = []
    if isinstance(raw_value, list):
        values = [str(item or "").strip() for item in raw_value]
    elif isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",")]
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(value)
        if len(normalized) >= max(1, min(int(limit), 30)):
            break
    return normalized


async def tool_research_dossier(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    symbols_raw = arguments.get("symbols")
    symbols: list[str] = []
    if isinstance(symbols_raw, list):
        symbols = [str(item or "").strip() for item in symbols_raw]
    elif isinstance(symbols_raw, str):
        symbols = [item.strip() for item in symbols_raw.split(",")]
    symbols = normalize_research_symbols(symbols, max_symbols=20)
    if len(symbols) < 2:
        symbols = ["AAPL", "MSFT"]

    period = str(arguments.get("period", "6mo")).strip() or "6mo"
    interval = str(arguments.get("interval", "1d")).strip() or "1d"
    baseline_symbol = str(arguments.get("baseline_symbol") or "").strip().upper() or None
    thesis = str(arguments.get("thesis") or "").strip()
    risks = _normalize_text_list_argument(arguments.get("risks"), limit=12)
    catalysts = _normalize_text_list_argument(arguments.get("catalysts"), limit=12)
    plan_id = str(arguments.get("plan_id") or "").strip() or None
    save_to_plan = _coerce_bool(arguments.get("save_to_plan"), True)
    include_portfolio_fit = _coerce_bool(arguments.get("include_portfolio_fit"), True)

    result = build_research_dossier_payload(
        symbols=symbols,
        period=period,
        interval=interval,
        baseline_symbol=baseline_symbol,
        thesis=thesis,
        risks=risks,
        catalysts=catalysts,
        plan_id=plan_id,
        save_to_plan=save_to_plan,
        include_portfolio_fit=include_portfolio_fit,
        services=services,
    ).model_dump(mode="json")
    compare_payload = result.get("compare")
    if isinstance(compare_payload, dict):
        items = compare_payload.get("items")
        if isinstance(items, list):
            compare_payload["items"] = items[:20]
            compare_payload["items_truncated"] = max(0, len(items) - 20)
    return result


async def tool_research_dossier_lookup(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = str(arguments.get("plan_id") or "").strip() or None
    limit = max(1, min(_coerce_int(arguments.get("limit"), 5), 25))
    include_content = _coerce_bool(arguments.get("include_content"), False)
    kwargs: dict[str, Any] = {
        "plan_id": plan_id,
        "limit": limit,
        "include_content": include_content,
    }
    if has_active_copilot_workspace_context():
        kwargs["workspace"] = services.plan_workspace
    return build_research_dossier_lookup_payload(**kwargs)


async def tool_research_watchlist_rank(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    period = str(arguments.get("period", "2y")).strip() or "2y"
    interval = str(arguments.get("interval", "1d")).strip() or "1d"
    limit = max(1, min(_coerce_int(arguments.get("limit"), 100), 500))
    kwargs: dict[str, Any] = {
        "period": period,
        "interval": interval,
        "sort": "ranked",
        "limit": limit,
    }
    if has_active_copilot_workspace_context():
        kwargs["store"] = services.portfolio_store
    payload = build_portfolio_watchlist_payload(**kwargs)
    return payload


def _normalize_account_total_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]]
    if isinstance(payload, dict):
        rows = [item for item in payload.values() if isinstance(item, dict)]
    elif isinstance(payload, list):
        rows = [item for item in payload if isinstance(item, dict)]
    else:
        rows = []

    normalized: list[dict[str, Any]] = []
    for row in rows:
        account_id = str(row.get("account_id") or row.get("id") or "").strip()
        if not account_id:
            continue
        normalized.append(
            {
                "account_id": account_id,
                "name": str(row.get("name") or account_id),
                "type": str(row.get("type") or "unknown"),
                "currency": str(row.get("currency") or settings.app_currency),
                "market_value": round(_coerce_float(row.get("market_value"), 0.0), 2),
                "cash_balance": round(_coerce_float(row.get("cash_balance"), 0.0), 2),
                "cost_basis": round(_coerce_float(row.get("cost_basis"), 0.0), 2),
                "total_value": round(_coerce_float(row.get("total_value"), 0.0), 2),
                "net_performance": round(_coerce_float(row.get("net_performance"), 0.0), 2),
                "net_performance_pct": round(_coerce_float(row.get("net_performance_pct"), 0.0), 2),
                "holdings_count": max(0, _coerce_int(row.get("holdings_count"), 0)),
            }
        )

    normalized.sort(key=lambda item: _coerce_float(item.get("total_value"), 0.0), reverse=True)
    return normalized


def _normalize_allocation_rows(rows: Any, *, top_n: int) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        normalized.append(
            {
                "key": key,
                "value": round(_coerce_float(item.get("value"), 0.0), 2),
                "allocation_pct": round(_coerce_float(item.get("allocation_pct"), 0.0), 2),
            }
        )

    normalized.sort(key=lambda item: _coerce_float(item.get("value"), 0.0), reverse=True)
    return normalized[:top_n]


async def tool_get_account_balances(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    use_live_snapshot = _coerce_bool(arguments.get("use_live_snapshot"), False)
    include_holdings = _coerce_bool(arguments.get("include_holdings"), False)
    holdings_limit_per_account = max(1, min(_coerce_int(arguments.get("holdings_limit_per_account"), 8), 25))

    if use_live_snapshot:
        await build_live_snapshot(services.portfolio_store)

    holdings_payload = services.portfolio_store.get_holdings()
    account_rows = _normalize_account_total_rows(holdings_payload.get("account_totals"))

    response: dict[str, Any] = {
        "as_of": holdings_payload.get("updated_at"),
        "base_currency": str(holdings_payload.get("base_currency") or settings.app_currency),
        "count": len(account_rows),
        "total_portfolio_value": round(_coerce_float(holdings_payload.get("total_portfolio_value"), 0.0), 2),
        "total_cash": round(_coerce_float(holdings_payload.get("total_cash"), 0.0), 2),
        "accounts": account_rows,
    }

    if not include_holdings:
        return response

    holdings_by_account: dict[str, list[dict[str, Any]]] = {}
    holdings_rows = holdings_payload.get("holdings")
    if isinstance(holdings_rows, dict):
        for row in holdings_rows.values():
            if not isinstance(row, dict):
                continue
            account_id = str(row.get("account") or "").strip()
            symbol = str(row.get("symbol") or "").strip().upper()
            if not account_id or not symbol:
                continue
            holdings_by_account.setdefault(account_id, []).append(
                {
                    "symbol": symbol,
                    "name": row.get("name"),
                    "quantity": round(_coerce_float(row.get("quantity"), 0.0), 8),
                    "current_value": round(_coerce_float(row.get("current_value"), 0.0), 2),
                    "allocation_percent": round(_coerce_float(row.get("allocation_percent"), 0.0), 2),
                    "net_performance": round(_coerce_float(row.get("net_performance"), 0.0), 2),
                    "asset_class": row.get("asset_class"),
                    "sector": row.get("sector"),
                    "region": row.get("region"),
                }
            )

    for account_id, rows in holdings_by_account.items():
        rows.sort(key=lambda item: _coerce_float(item.get("current_value"), 0.0), reverse=True)
        holdings_by_account[account_id] = rows[:holdings_limit_per_account]

    response["holdings_by_account"] = holdings_by_account
    return response


async def tool_get_asset_allocation(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    use_live_snapshot = _coerce_bool(arguments.get("use_live_snapshot"), False)
    dimension = str(arguments.get("dimension") or "asset_class").strip().lower()
    if dimension not in {"asset_class", "sector", "region", "all"}:
        raise ValueError("dimension must be one of: asset_class, sector, region, all")
    top_n = max(1, min(_coerce_int(arguments.get("top_n"), 10), 100))

    if use_live_snapshot:
        await build_live_snapshot(services.portfolio_store)

    holdings_payload = services.portfolio_store.get_holdings()
    breakdowns_raw = holdings_payload.get("allocation_breakdowns")
    if not isinstance(breakdowns_raw, dict):
        breakdowns_raw = {}

    dimensions = ("asset_class", "sector", "region") if dimension == "all" else (dimension,)
    breakdowns: dict[str, list[dict[str, Any]]] = {}
    for key in dimensions:
        breakdowns[key] = _normalize_allocation_rows(breakdowns_raw.get(key), top_n=top_n)

    return {
        "as_of": holdings_payload.get("updated_at"),
        "base_currency": str(holdings_payload.get("base_currency") or settings.app_currency),
        "dimension": dimension,
        "top_n": top_n,
        "breakdowns": breakdowns,
    }


async def tool_compute_tax(arguments: dict[str, object]) -> dict[str, object]:
    filing_status = str(arguments.get("filing_status") or "single").strip().lower() or "single"
    if filing_status not in {
        "single",
        "married_filing_jointly",
        "married_filing_separately",
        "head_of_household",
    }:
        raise ValueError(
            "filing_status must be one of: single, married_filing_jointly, "
            "married_filing_separately, head_of_household"
        )

    tax_year = max(1900, min(_coerce_int(arguments.get("tax_year"), utc_now().year), 2500))

    payload = estimate_federal_tax(
        tax_year=tax_year,
        filing_status=filing_status,
        earned_income_usd=_coerce_float(arguments.get("earned_income_usd"), 0.0),
        ordinary_income_usd=_coerce_float(arguments.get("ordinary_income_usd"), 0.0),
        short_term_capital_gains_usd=_coerce_float(arguments.get("short_term_capital_gains_usd"), 0.0),
        long_term_capital_gains_usd=_coerce_float(arguments.get("long_term_capital_gains_usd"), 0.0),
        qualified_dividends_usd=_coerce_float(arguments.get("qualified_dividends_usd"), 0.0),
        interest_income_usd=_coerce_float(arguments.get("interest_income_usd"), 0.0),
        social_security_income_usd=_coerce_float(arguments.get("social_security_income_usd"), 0.0),
        tax_exempt_interest_income_usd=max(0.0, _coerce_float(arguments.get("tax_exempt_interest_income_usd"), 0.0)),
        pre_tax_contributions_usd=max(0.0, _coerce_float(arguments.get("pre_tax_contributions_usd"), 0.0)),
        state_tax_rate=max(0.0, min(1.0, _coerce_float(arguments.get("state_tax_rate"), 0.0))),
        state_tax_deduction_usd=max(0.0, _coerce_float(arguments.get("state_tax_deduction_usd"), 0.0)),
        age=(
            max(0, min(120, _coerce_int(arguments.get("age"), 0)))
            if arguments.get("age") is not None
            else None
        ),
        include_irmaa=_coerce_bool(arguments.get("include_irmaa"), True),
        medicare_months_covered=max(0, min(12, _coerce_int(arguments.get("medicare_months_covered"), 12))),
        tax_withholding_usd=max(0.0, _coerce_float(arguments.get("tax_withholding_usd"), 0.0)),
    )
    return TaxEstimateResponse(**payload).model_dump(mode="json")


async def tool_list_accounts(_: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    accounts = services.portfolio_store.get_accounts()
    return {"count": len(accounts), "accounts": accounts}


async def tool_list_plans(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    limit_value = arguments.get("limit", 20)
    try:
        limit = max(1, min(int(limit_value), 200))
    except Exception:
        limit = 20
    plans = services.plan_workspace.list_plans(limit=limit)
    return {"count": len(plans), "plans": plans}


async def tool_get_plan_context(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = arguments.get("plan_id")
    resolved = str(plan_id).strip() if isinstance(plan_id, str) and plan_id.strip() else None
    return services.plan_workspace.get_context_payload(plan_id=resolved)


async def tool_get_plan_review_context(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    detail = services.plan_workspace.get_plan(plan_id)
    settings_payload = detail.get("settings", {})
    settings_dict = settings_payload if isinstance(settings_payload, dict) else {}
    assumption_sets = services.plan_workspace.get_plan_assumption_sets(plan_id)
    active_assumption_set = summarize_active_assumption_set(assumption_sets)
    try:
        max_health_signals = max(1, min(int(arguments.get("max_health_signals", 5)), 10))
    except Exception:
        max_health_signals = 5
    health_signals = build_plan_review_health_signals(
        plan_id=plan_id,
        settings=settings_dict,
        max_signals=max_health_signals,
        inbox=services.recommendation_inbox,
    )
    selected_artifacts = build_selected_plan_artifact_summaries(
        plan_id=plan_id,
        artifacts=detail.get("artifacts", []),
        selected_artifact_ids=arguments.get("selected_artifact_ids"),
    )
    scenario_diff_summary = summarize_plan_review_scenario_diff(arguments.get("scenario_diff_result"))
    next_section = "assumptions"
    if health_signals:
        next_section = str(health_signals[0].get("section") or "assumptions")
    elif scenario_diff_summary:
        next_section = "scenarios"
    elif selected_artifacts:
        next_section = "artifacts"

    return {
        "plan_id": plan_id,
        "title": detail.get("title"),
        "active_assumption_set": active_assumption_set,
        "health_signals": health_signals,
        "selected_artifacts": selected_artifacts,
        "scenario_diff_summary": scenario_diff_summary,
        "suggested_next_step": {
            "label": plan_review_next_step_label(next_section),
            "section": next_section,
        },
        "context_scope": {
            "bounded": True,
            "max_health_signals": max_health_signals,
            "full_artifact_contents_included": False,
            "long_decision_history_included": False,
        },
    }


def summarize_active_assumption_set(assumption_sets: dict[str, Any]) -> dict[str, Any]:
    active_id = str(assumption_sets.get("active_assumption_set_id") or "default").strip() or "default"
    sets = assumption_sets.get("sets")
    rows = sets if isinstance(sets, list) else []
    active = next(
        (row for row in rows if isinstance(row, dict) and str(row.get("id") or "").strip() == active_id),
        rows[0] if rows and isinstance(rows[0], dict) else {},
    )
    active_settings = active.get("settings") if isinstance(active, dict) else {}
    settings_dict = active_settings if isinstance(active_settings, dict) else {}
    summary_keys = [
        "annual_contribution_usd",
        "years",
        "expected_return_baseline",
        "inflation_rate",
        "marginal_tax_rate",
        "withdrawal_strategy",
        "drawdown_order",
        "simulation_mode",
    ]
    return {
        "id": str(active.get("id") or active_id).strip() or active_id,
        "name": str(active.get("name") or active_id).strip() or active_id,
        "description": str(active.get("description") or "").strip(),
        "summary": {
            key: settings_dict.get(key)
            for key in summary_keys
            if key in settings_dict
        },
    }


def build_plan_review_health_signals(
    *,
    plan_id: str,
    settings: dict[str, Any],
    max_signals: int,
    inbox: RecommendationInbox | None = None,
) -> list[dict[str, Any]]:
    resolved_inbox = inbox or recommendation_inbox
    signals: list[dict[str, Any]] = []
    if settings.get("marginal_tax_rate") is None or settings.get("marginal_tax_rate") == "":
        signals.append(
            {
                "id": "tax-assumptions",
                "severity": "weak",
                "title": "Tax assumptions need review",
                "detail": "Marginal tax rate is missing, so plan advice and investment-fit checks carry lower confidence.",
                "section": "assumptions",
            }
        )
    if settings.get("annual_contribution_usd") is None or _coerce_float(settings.get("annual_contribution_usd"), 0.0) <= 0:
        signals.append(
            {
                "id": "contribution-assumptions",
                "severity": "weak",
                "title": "Contribution assumptions need review",
                "detail": "Annual contribution is missing or zero, which weakens plan trajectory and recommendation quality.",
                "section": "assumptions",
            }
        )
    if settings.get("expected_return_baseline") is None or settings.get("expected_return_baseline") == "":
        signals.append(
            {
                "id": "return-assumptions",
                "severity": "review",
                "title": "Expected return assumption needs review",
                "detail": "Expected return is missing, so scenario diffs and long-horizon projections need more context.",
                "section": "assumptions",
            }
        )
    try:
        rows = resolved_inbox.list(
            limit=100,
            status="proposed",
            plan_id=plan_id,
            sort="created_at_desc",
        )
    except Exception:
        rows = []
    stale_rows = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("source") or "").strip().lower() == "generator:stale_assumptions"
    ]
    if stale_rows:
        signals.append(
            {
                "id": "open-stale-assumptions",
                "severity": "review",
                "title": "Open stale-assumption reviews",
                "detail": f"{len(stale_rows)} stale-assumption review{'s' if len(stale_rows) != 1 else ''} should be resolved before advice is fully trusted.",
                "section": "assumptions",
                "recommendation_id": stale_rows[0].get("id"),
            }
        )
    thesis_rows = [
        row for row in rows
        if isinstance(row, dict) and str(row.get("source") or "").strip().lower() == "generator:research_thesis_expiration"
    ]
    if thesis_rows:
        signals.append(
            {
                "id": "open-research-thesis-reviews",
                "severity": "review",
                "title": "Open research thesis reviews",
                "detail": f"{len(thesis_rows)} linked research thesis review{'s' if len(thesis_rows) != 1 else ''} should be resolved before evidence guides plan decisions.",
                "section": "artifacts",
                "recommendation_id": thesis_rows[0].get("id"),
            }
        )
    return signals[:max_signals]


def build_selected_plan_artifact_summaries(
    *,
    plan_id: str,
    artifacts: Any,
    selected_artifact_ids: object,
    workspace: PlanWorkspace | None = None,
) -> list[dict[str, Any]]:
    resolved_workspace = workspace or plan_workspace
    if isinstance(selected_artifact_ids, str):
        requested_ids = [selected_artifact_ids]
    elif isinstance(selected_artifact_ids, list):
        requested_ids = [str(item or "").strip() for item in selected_artifact_ids]
    else:
        requested_ids = []
    requested = [item for item in requested_ids if item]
    if not requested:
        return []
    rows = artifacts if isinstance(artifacts, list) else []
    summaries: list[dict[str, Any]] = []
    for artifact_id in requested[:4]:
        summary = next(
            (
                row for row in rows
                if isinstance(row, dict) and str(row.get("id") or "").strip() == artifact_id
            ),
            {"id": artifact_id},
        )
        content = ""
        try:
            artifact_detail = resolved_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
            if isinstance(artifact_detail, dict):
                content = str(artifact_detail.get("content") or "")
        except Exception:
            content = ""
        summaries.append(
            {
                "id": artifact_id,
                "title": str(summary.get("title") or summary.get("file_name") or artifact_id).strip(),
                "file_name": str(summary.get("file_name") or "").strip(),
                "citations": extract_research_citations(content),
            }
        )
    return summaries


def extract_research_citations(content: str) -> list[str]:
    citations: list[str] = []
    for match in re.findall(r"research-evidence:[A-Za-z0-9_.:-]+", content or ""):
        cleaned = match.rstrip(".,);]")
        if cleaned and cleaned not in citations:
            citations.append(cleaned)
    return citations[:8]


def summarize_plan_review_scenario_diff(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    deltas_raw = value.get("scenario_deltas")
    deltas = deltas_raw if isinstance(deltas_raw, list) else []
    monte_raw = value.get("monte_carlo_delta")
    simulation_raw = value.get("simulation_delta")
    warnings_raw = value.get("warnings")
    return {
        "deltas": [
            {
                "label": str(row.get("label") or "scenario"),
                "delta_future_value_usd": row.get("delta_future_value_usd"),
                "delta_real_value_usd": row.get("delta_real_value_usd"),
            }
            for row in deltas[:3]
            if isinstance(row, dict)
        ],
        "monte_carlo_delta": (
            {
                key: monte_raw.get(key)
                for key in ["success_probability_delta", "p50_future_value_delta_usd", "p10_future_value_delta_usd"]
                if isinstance(monte_raw, dict) and key in monte_raw
            }
            if isinstance(monte_raw, dict)
            else {}
        ),
        "simulation_delta": (
            {
                key: simulation_raw.get(key)
                for key in ["status", "summary"]
                if isinstance(simulation_raw, dict) and key in simulation_raw
            }
            if isinstance(simulation_raw, dict)
            else {}
        ),
        "warnings": [
            str(item)
            for item in (warnings_raw if isinstance(warnings_raw, list) else [])
            if str(item).strip()
        ][:5],
    }


def plan_review_next_step_label(section: str) -> str:
    normalized = str(section or "").strip().lower()
    if normalized == "scenarios":
        return "Open scenario workspace"
    if normalized == "artifacts":
        return "Open Plan evidence"
    if normalized == "decisions":
        return "Open decision ledger"
    return "Review assumptions"


async def tool_get_plan_settings(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    detail = services.plan_workspace.get_plan(plan_id)
    return {
        "plan_id": plan_id,
        "title": detail.get("title"),
        "settings": detail.get("settings", {}),
        "updated_at": detail.get("updated_at"),
    }


async def tool_update_plan_settings(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    updates = extract_plan_settings_updates(arguments)
    rationale = str(arguments.get("rationale") or "").strip()
    status = str(arguments.get("status") or "accepted").strip().lower() or "accepted"

    detail = services.plan_workspace.update_plan_settings(
        plan_id=plan_id,
        updates=updates,
        rationale=rationale or None,
        status=status,
        log_decision=True,
    )
    return {
        "plan_id": plan_id,
        "settings": detail.get("settings", {}),
        "updated_at": detail.get("updated_at"),
    }


async def tool_get_plan_timeline(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    timeline = services.plan_workspace.get_plan_timeline(plan_id)
    return {
        "plan_id": plan_id,
        "timeline": timeline,
    }


async def tool_update_plan_timeline(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    timeline_raw = arguments.get("timeline")
    if not isinstance(timeline_raw, dict):
        raise ValueError("timeline must be an object with events and optional retirement fields.")

    timeline = services.plan_workspace.update_plan_timeline(
        plan_id=plan_id,
        timeline_payload=timeline_raw,
        rationale=str(arguments.get("rationale") or "").strip() or "Updated via copilot tool.",
        status=str(arguments.get("status") or "accepted").strip().lower() or "accepted",
        log_decision=True,
    )
    return {
        "plan_id": plan_id,
        "timeline": timeline,
    }


async def tool_add_timeline_event(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)

    date_value = str(arguments.get("date") or "").strip()
    if not date_value:
        raise ValueError("date is required (YYYY-MM-DD).")
    label = str(arguments.get("label") or "").strip()
    if not label:
        raise ValueError("label is required.")

    event_type = str(arguments.get("event_type") or "milestone").strip().lower() or "milestone"
    if event_type not in TIMELINE_EVENT_TYPES:
        allowed_event_types = ", ".join(TIMELINE_EVENT_TYPE_VALUES)
        raise ValueError(f"event_type must be one of: {allowed_event_types}")

    impact_type_raw = str(arguments.get("impact_type") or "").strip().lower()
    impact_type = impact_type_raw or TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")
    if impact_type not in TIMELINE_IMPACT_TYPES:
        allowed_impact_types = ", ".join(TIMELINE_IMPACT_TYPE_VALUES)
        raise ValueError(f"impact_type must be one of: {allowed_impact_types}")

    recurring_frequency = str(arguments.get("recurring_frequency") or "one_time").strip().lower() or "one_time"
    if recurring_frequency not in TIMELINE_FREQUENCIES:
        allowed_frequencies = ", ".join(sorted(TIMELINE_FREQUENCIES))
        raise ValueError(f"recurring_frequency must be one of: {allowed_frequencies}")

    timeline_payload = services.plan_workspace.get_plan_timeline(plan_id)
    existing_events_raw = timeline_payload.get("events")
    existing_events = list(existing_events_raw) if isinstance(existing_events_raw, list) else []
    existing_ids = {
        str(item.get("id")).strip()
        for item in existing_events
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }

    added_event: dict[str, Any] = {
        "date": date_value,
        "label": label,
        "event_type": event_type,
        "impact_type": impact_type,
        "amount_usd": _coerce_float(arguments.get("amount_usd"), 0.0),
        "recurring_frequency": recurring_frequency,
    }

    event_id = str(arguments.get("event_id") or arguments.get("id") or "").strip()
    if event_id:
        added_event["id"] = event_id

    end_date = str(arguments.get("end_date") or "").strip()
    if end_date:
        added_event["end_date"] = end_date
    account_id = str(arguments.get("account_id") or "").strip()
    if account_id:
        added_event["account_id"] = account_id
    notes = str(arguments.get("notes") or "").strip()
    if notes:
        added_event["notes"] = notes

    existing_events.append(added_event)
    existing_events.sort(key=lambda item: str(item.get("date") or ""))

    timeline = services.plan_workspace.update_plan_timeline(
        plan_id=plan_id,
        timeline_payload={
            "events": existing_events,
            "retirement": (
                timeline_payload.get("retirement")
                if isinstance(timeline_payload.get("retirement"), dict)
                else {}
            ),
        },
        rationale=str(arguments.get("rationale") or "").strip() or "Added timeline event via copilot tool.",
        status=str(arguments.get("status") or "accepted").strip().lower() or "accepted",
        log_decision=_coerce_bool(arguments.get("log_decision"), True),
    )

    resolved_event: dict[str, Any] | None = None
    updated_events = timeline.get("events")
    if isinstance(updated_events, list):
        if event_id:
            for item in updated_events:
                if isinstance(item, dict) and str(item.get("id") or "").strip() == event_id:
                    resolved_event = item
                    break
        if resolved_event is None:
            for item in reversed(updated_events):
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "").strip()
                if item_id and item_id not in existing_ids:
                    resolved_event = item
                    break
        if resolved_event is None and updated_events:
            last_item = updated_events[-1]
            if isinstance(last_item, dict):
                resolved_event = last_item

    return {
        "plan_id": plan_id,
        "event": resolved_event or {},
        "timeline": timeline,
    }


async def tool_get_plan_contribution_rules(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    contribution_rules = services.plan_workspace.get_plan_contribution_rules(plan_id)
    return {
        "plan_id": plan_id,
        "contribution_rules": contribution_rules,
    }


async def tool_set_contribution_rules(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)

    payload_raw = arguments.get("contribution_rules")
    payload = dict(payload_raw) if isinstance(payload_raw, dict) else {}
    shorthand_base_rule = arguments.get("base_rule")
    if isinstance(shorthand_base_rule, dict):
        payload["base_rule"] = shorthand_base_rule
    shorthand_rules = arguments.get("rules")
    if isinstance(shorthand_rules, list):
        payload["rules"] = [item for item in shorthand_rules if isinstance(item, dict)]
    if arguments.get("profile_id") is not None:
        payload["profile_id"] = str(arguments.get("profile_id") or "").strip() or None

    employer_match_target_usd = max(
        0.0,
        _coerce_float(
            arguments.get("employer_match_target_usd", payload.get("employer_match_target_usd", 6000.0)),
            6000.0,
        ),
    )
    age = max(
        0,
        min(
            _coerce_int(arguments.get("age", payload.get("age", 35)), 35),
            120,
        ),
    )
    payload["employer_match_target_usd"] = employer_match_target_usd
    payload["age"] = age

    has_explicit_payload = (
        isinstance(payload_raw, dict)
        or isinstance(shorthand_rules, list)
        or isinstance(shorthand_base_rule, dict)
    )
    use_default_profile = _coerce_bool(arguments.get("use_default_profile"), False) or not has_explicit_payload
    if use_default_profile:
        generated = build_tax_optimized_high_earner_rules(
            build_planning_accounts_from_portfolio(services.portfolio_store),
            employer_match_target_usd=employer_match_target_usd,
        )
        if not isinstance(payload.get("base_rule"), dict):
            payload["base_rule"] = generated.get("base_rule", {"type": "save"})
        if not isinstance(payload.get("rules"), list) or not payload.get("rules"):
            payload["rules"] = generated.get("rules", [])
        if not payload.get("profile_id"):
            payload["profile_id"] = generated.get("profile_id", "tax_optimized_high_earner")

    contribution_rules = services.plan_workspace.update_plan_contribution_rules(
        plan_id=plan_id,
        contribution_rules_payload=payload,
        rationale=str(arguments.get("rationale") or "").strip() or "Updated via copilot tool.",
        status=str(arguments.get("status") or "accepted").strip().lower() or "accepted",
        log_decision=True,
    )

    allocation_preview: dict[str, Any] | None = None
    allocation_warning: str | None = None
    try:
        detail = services.plan_workspace.get_plan(plan_id)
        plan_settings = detail.get("settings", {})
        if not isinstance(plan_settings, dict):
            plan_settings = {}
        preview = build_contribution_allocation_for_plan_settings(
            plan_settings=plan_settings,
            contribution_rules_payload=contribution_rules,
        )
        allocation_preview = preview.model_dump(mode="json")
    except Exception as exc:
        allocation_warning = f"Contribution allocation preview unavailable: {exc}"

    response: dict[str, Any] = {
        "plan_id": plan_id,
        "contribution_rules": contribution_rules,
    }
    if allocation_preview is not None:
        response["allocation_preview"] = allocation_preview
    if allocation_warning:
        response["warnings"] = [allocation_warning]
    return response


async def tool_compare_withdrawal_strategies(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    detail = services.plan_workspace.get_plan(plan_id)
    if not isinstance(detail, dict):
        raise ValueError(f"Plan not found: {plan_id}")

    current_portfolio_value_raw = arguments.get("current_portfolio_value_usd")
    current_portfolio_value = resolve_portfolio_value(
        float(current_portfolio_value_raw) if current_portfolio_value_raw is not None else None,
        store=services.snapshot_store,
    )

    strategies, invalid_strategies = normalize_withdrawal_strategies(arguments.get("strategies"))
    include_raw_results = _coerce_bool(arguments.get("include_raw_results"), False)
    assumption_set_id = str(arguments.get("assumption_set_id") or "").strip() or None

    base_settings_raw = detail.get("settings", {})
    if not isinstance(base_settings_raw, dict):
        base_settings_raw = {}

    assumption_sets_payload = resolve_plan_assumption_sets(detail)
    projection_settings, active_assumption_set = apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=assumption_set_id,
    )
    timeline_payload = resolve_plan_timeline_payload(detail)
    timeline_retirement_age = resolve_timeline_retirement_age(timeline_payload)
    timeline_withdrawal_strategy = resolve_timeline_withdrawal_strategy(timeline_payload)
    timeline_drawdown_order = resolve_timeline_drawdown_order(timeline_payload)
    contribution_rules_payload = resolve_plan_contribution_rules(detail)

    income_projection = build_income_projection_for_plan_settings(projection_settings)
    expense_projection = build_expense_projection_for_plan_settings(projection_settings)
    debt_projection = build_debt_projection_for_plan_settings(projection_settings)
    timeline_projection = build_timeline_projection_for_plan_settings(
        plan_settings=projection_settings,
        timeline_payload=timeline_payload,
    )
    contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings=projection_settings,
        contribution_rules_payload=contribution_rules_payload,
    )
    social_security_projection = build_social_security_projection_for_plan_settings(
        plan_settings=projection_settings,
        timeline_payload=timeline_payload,
        income_projection=income_projection,
        start_year=utc_now().year,
    )
    rmd_projection = build_rmd_projection_for_plan_settings(
        plan_settings=projection_settings,
        timeline_payload=timeline_payload,
        start_year=utc_now().year,
    )

    comparisons: list[dict[str, Any]] = []
    raw_results: dict[str, Any] = {}
    warnings: list[str] = []
    if invalid_strategies:
        warnings.append(f"Ignored invalid strategies: {', '.join(invalid_strategies)}")

    for strategy in strategies:
        strategy_settings = {**projection_settings, "withdrawal_strategy": strategy}
        result = await run_scenarios_for_plan_settings(
            current_portfolio_value_usd=current_portfolio_value,
            plan_settings=strategy_settings,
            income_projection=income_projection,
            expense_projection=expense_projection,
            debt_projection=debt_projection,
            timeline_projection=timeline_projection,
            contribution_allocation=contribution_allocation,
            social_security_projection=social_security_projection,
            rmd_projection=rmd_projection,
            assumption_set=active_assumption_set,
            retirement_age=timeline_retirement_age,
            timeline_withdrawal_strategy=timeline_withdrawal_strategy,
            timeline_drawdown_order=timeline_drawdown_order,
        )

        baseline_scenario = next((item for item in result.scenarios if item.label == "baseline"), None)
        assumptions = baseline_scenario.assumptions if baseline_scenario else {}
        if not isinstance(assumptions, dict):
            assumptions = {}
        timeline_points = baseline_scenario.timeline_points if baseline_scenario else []
        total_withdrawals_usd = round(sum(float(point.withdrawals_usd) for point in timeline_points), 2)
        total_taxes_usd = round(sum(float(point.taxes_usd) for point in timeline_points), 2)
        total_federal_taxes_usd = round(
            _coerce_float(
                assumptions.get("total_federal_taxes_paid_usd"),
                sum(_coerce_float(getattr(point, "federal_taxes_usd", 0.0), 0.0) for point in timeline_points),
            ),
            2,
        )
        total_state_taxes_usd = round(
            _coerce_float(
                assumptions.get("total_state_taxes_paid_usd"),
                sum(_coerce_float(getattr(point, "state_taxes_usd", 0.0), 0.0) for point in timeline_points),
            ),
            2,
        )
        total_irmaa_surcharges_usd = round(
            _coerce_float(
                assumptions.get("total_irmaa_surcharges_paid_usd"),
                sum(_coerce_float(getattr(point, "irmaa_surcharges_usd", 0.0), 0.0) for point in timeline_points),
            ),
            2,
        )
        total_roth_conversions_usd = round(
            _coerce_float(
                assumptions.get("total_roth_conversions_usd"),
                sum(_coerce_float(getattr(point, "roth_conversions_usd", 0.0), 0.0) for point in timeline_points),
            ),
            2,
        )
        total_rmds_usd = round(sum(float(point.rmds_usd) for point in timeline_points), 2)
        terminal_age = timeline_points[-1].age if timeline_points else None
        terminal_balance_usd = (
            round(float(timeline_points[-1].ending_balance_usd), 2)
            if timeline_points
            else None
        )

        monte_carlo = result.monte_carlo if isinstance(result.monte_carlo, dict) else {}
        simulation_raw = getattr(result, "simulation", None)
        simulation = simulation_raw if isinstance(simulation_raw, dict) else {}
        comparisons.append(
            {
                "strategy": strategy,
                "baseline_future_value_usd": (
                    round(float(baseline_scenario.future_value_usd), 2) if baseline_scenario is not None else None
                ),
                "baseline_real_value_usd": (
                    round(float(baseline_scenario.real_value_usd), 2) if baseline_scenario is not None else None
                ),
                "total_withdrawals_usd": total_withdrawals_usd,
                "total_taxes_usd": total_taxes_usd,
                "total_federal_taxes_usd": total_federal_taxes_usd,
                "total_state_taxes_usd": total_state_taxes_usd,
                "total_irmaa_surcharges_usd": total_irmaa_surcharges_usd,
                "total_roth_conversions_usd": total_roth_conversions_usd,
                "total_rmds_usd": total_rmds_usd,
                "terminal_age": terminal_age,
                "terminal_balance_usd": terminal_balance_usd,
                "monte_carlo_p10_future_value_usd": _coerce_float(
                    monte_carlo.get("p10_future_value_usd"),
                    0.0,
                ),
                "monte_carlo_p50_future_value_usd": _coerce_float(
                    monte_carlo.get("p50_future_value_usd"),
                    0.0,
                ),
                "monte_carlo_p90_future_value_usd": _coerce_float(
                    monte_carlo.get("p90_future_value_usd"),
                    0.0,
                ),
                "simulation_mode": (
                    _normalize_optional_simulation_mode(simulation.get("mode"))
                    or _normalize_optional_simulation_mode(assumptions.get("simulation_mode"))
                ),
                "simulation_monte_carlo_variant": (
                    _normalize_optional_simulation_monte_carlo_variant(
                        simulation.get("monte_carlo_variant")
                    )
                    or _normalize_optional_simulation_monte_carlo_variant(
                        assumptions.get("simulation_monte_carlo_variant")
                    )
                ),
                "average_effective_tax_rate": assumptions.get("average_effective_tax_rate"),
                "engine": result.engine,
                "engine_status": result.engine_status,
                "fallback_method": result.fallback_method,
                "warnings": list(result.warnings),
            }
        )
        warnings.extend(result.warnings)
        if include_raw_results:
            raw_results[strategy] = result.model_dump(mode="json")

    comparisons.sort(
        key=lambda item: _coerce_float(item.get("baseline_future_value_usd"), 0.0),
        reverse=True,
    )

    def _best_strategy(metric: str) -> str | None:
        best: dict[str, Any] | None = None
        for row in comparisons:
            value = _coerce_float(row.get(metric), float("-inf"))
            if best is None or value > _coerce_float(best.get(metric), float("-inf")):
                best = row
        return str(best.get("strategy")) if isinstance(best, dict) and best.get("strategy") else None

    response: dict[str, Any] = {
        "plan_id": plan_id,
        "current_portfolio_value_usd": current_portfolio_value,
        "assumption_set": active_assumption_set,
        "strategies": strategies,
        "comparisons": comparisons,
        "best_strategy_by_metric": {
            "future_value": _best_strategy("baseline_future_value_usd"),
            "real_value": _best_strategy("baseline_real_value_usd"),
            "monte_carlo_p50": _best_strategy("monte_carlo_p50_future_value_usd"),
        },
        "warnings": warnings,
    }
    response["explanation"] = explain_withdrawal_strategy_comparison(response)
    if include_raw_results:
        response["raw_results"] = raw_results
    return response


async def tool_get_plan_assumption_sets(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    assumption_sets = services.plan_workspace.get_plan_assumption_sets(plan_id)
    return {
        "plan_id": plan_id,
        "assumption_sets": assumption_sets,
    }


async def tool_update_plan_assumption_sets(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    payload_raw = arguments.get("assumption_sets")
    if not isinstance(payload_raw, dict):
        raise ValueError("assumption_sets must be an object with active_assumption_set_id and sets.")

    assumption_sets = services.plan_workspace.update_plan_assumption_sets(
        plan_id=plan_id,
        assumption_sets_payload=payload_raw,
        rationale=str(arguments.get("rationale") or "").strip() or "Updated via copilot tool.",
        status=str(arguments.get("status") or "accepted").strip().lower() or "accepted",
        log_decision=True,
    )
    return {
        "plan_id": plan_id,
        "assumption_sets": assumption_sets,
    }


async def tool_get_plan_branch_templates(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    branch_templates = services.plan_workspace.get_plan_branch_templates(plan_id)
    return {
        "plan_id": plan_id,
        "branch_templates": branch_templates,
    }


async def tool_update_plan_branch_templates(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    payload_raw = arguments.get("branch_templates")
    if not isinstance(payload_raw, dict):
        raise ValueError("branch_templates must be an object with default_template_id and templates.")

    branch_templates = services.plan_workspace.update_plan_branch_templates(
        plan_id=plan_id,
        branch_templates_payload=payload_raw,
        rationale=str(arguments.get("rationale") or "").strip() or "Updated via copilot tool.",
        status=str(arguments.get("status") or "accepted").strip().lower() or "accepted",
        log_decision=True,
    )
    return {
        "plan_id": plan_id,
        "branch_templates": branch_templates,
    }


async def tool_get_plan_tracking(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    detail = services.plan_workspace.get_plan(plan_id)
    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = services.snapshot_store.recent(limit=90)
    transactions = services.portfolio_store.list_transactions(limit=10_000)
    planner_defaults = {
        "annual_contribution_usd": settings.planner_annual_contribution_usd,
        "expected_return_baseline": settings.planner_expected_return_baseline,
        "hsa_extra_contribution_usd": settings.planner_hsa_delta_default,
    }
    result = compute_plan_tracking(
        plan_id=plan_id,
        plan_title=detail.get("title", ""),
        plan_settings=plan_settings,
        planner_defaults=planner_defaults,
        snapshots=snapshots,
        transactions=transactions,
    )
    return result.model_dump(mode="json")


async def tool_run_plan_scenario_diff(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    detail = services.plan_workspace.get_plan(plan_id)
    timeline_payload = resolve_plan_timeline_payload(detail)
    retirement_age = resolve_timeline_retirement_age(timeline_payload)
    timeline_withdrawal_strategy = resolve_timeline_withdrawal_strategy(timeline_payload)
    timeline_drawdown_order = resolve_timeline_drawdown_order(timeline_payload)
    assumption_sets_payload = resolve_plan_assumption_sets(detail)
    requested_assumption_set_id = str(arguments.get("assumption_set_id") or "").strip() or None
    requested_candidate_assumption_set_id = (
        str(arguments.get("candidate_assumption_set_id") or "").strip() or None
    )
    base_settings_raw = detail.get("settings", {})
    if not isinstance(base_settings_raw, dict):
        base_settings_raw = {}
    base_settings, base_assumption_set = apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=requested_assumption_set_id,
    )
    compare_updates = extract_plan_settings_updates(arguments)
    candidate_set_id = requested_candidate_assumption_set_id or requested_assumption_set_id
    candidate_base_settings, candidate_assumption_set = apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=candidate_set_id,
    )
    candidate_settings = merge_plan_settings(candidate_base_settings, compare_updates)
    base_income_projection = build_income_projection_for_plan_settings(base_settings)
    candidate_income_projection = build_income_projection_for_plan_settings(candidate_settings)
    base_expense_projection = build_expense_projection_for_plan_settings(base_settings)
    candidate_expense_projection = build_expense_projection_for_plan_settings(candidate_settings)
    base_debt_projection = build_debt_projection_for_plan_settings(base_settings)
    candidate_debt_projection = build_debt_projection_for_plan_settings(candidate_settings)
    base_timeline_projection = build_timeline_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
    )
    candidate_timeline_projection = build_timeline_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
    )
    contribution_rules_payload = resolve_plan_contribution_rules(detail)
    base_contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings=base_settings,
        contribution_rules_payload=contribution_rules_payload,
    )
    candidate_contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings=candidate_settings,
        contribution_rules_payload=contribution_rules_payload,
    )
    base_social_security_projection = build_social_security_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        income_projection=base_income_projection,
        start_year=utc_now().year,
    )
    candidate_social_security_projection = build_social_security_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
        income_projection=candidate_income_projection,
        start_year=utc_now().year,
    )
    base_rmd_projection = build_rmd_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        start_year=utc_now().year,
    )
    candidate_rmd_projection = build_rmd_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
        start_year=utc_now().year,
    )

    current_value_raw = arguments.get("current_portfolio_value_usd")
    current_value = resolve_portfolio_value(
        float(current_value_raw) if current_value_raw is not None else None,
        store=services.snapshot_store,
    )

    base_result = await run_scenarios_for_plan_settings(
        current_portfolio_value_usd=current_value,
        plan_settings=base_settings,
        income_projection=base_income_projection,
        expense_projection=base_expense_projection,
        debt_projection=base_debt_projection,
        timeline_projection=base_timeline_projection,
        contribution_allocation=base_contribution_allocation,
        social_security_projection=base_social_security_projection,
        rmd_projection=base_rmd_projection,
        assumption_set=base_assumption_set,
        retirement_age=retirement_age,
        timeline_withdrawal_strategy=timeline_withdrawal_strategy,
        timeline_drawdown_order=timeline_drawdown_order,
    )
    candidate_result = await run_scenarios_for_plan_settings(
        current_portfolio_value_usd=current_value,
        plan_settings=candidate_settings,
        income_projection=candidate_income_projection,
        expense_projection=candidate_expense_projection,
        debt_projection=candidate_debt_projection,
        timeline_projection=candidate_timeline_projection,
        contribution_allocation=candidate_contribution_allocation,
        social_security_projection=candidate_social_security_projection,
        rmd_projection=candidate_rmd_projection,
        assumption_set=candidate_assumption_set,
        retirement_age=retirement_age,
        timeline_withdrawal_strategy=timeline_withdrawal_strategy,
        timeline_drawdown_order=timeline_drawdown_order,
    )
    scenario_deltas, monte_carlo_delta, simulation_delta = build_scenario_diff_payload(
        base_result,
        candidate_result,
    )

    apply_to_plan = bool(arguments.get("apply_to_plan", False))
    applied = False
    if apply_to_plan:
        if not compare_updates:
            raise ValueError("apply_to_plan=true requires at least one plan settings override.")
        rationale = str(arguments.get("rationale") or "").strip() or "Applied from scenario-diff action."
        status = str(arguments.get("status") or "accepted").strip().lower() or "accepted"
        updated = services.plan_workspace.update_plan_settings(
            plan_id=plan_id,
            updates=compare_updates,
            rationale=rationale,
            status=status,
            log_decision=True,
        )
        candidate_settings = updated.get("settings", candidate_settings)
        applied = True

    return {
        "plan_id": plan_id,
        "current_portfolio_value_usd": current_value,
        "base_settings": base_settings,
        "candidate_settings": candidate_settings,
        "base_assumption_set": base_assumption_set,
        "candidate_assumption_set": candidate_assumption_set,
        "base_result": base_result.model_dump(mode="json"),
        "candidate_result": candidate_result.model_dump(mode="json"),
        "scenario_deltas": scenario_deltas,
        "monte_carlo_delta": monte_carlo_delta,
        "simulation_delta": simulation_delta,
        "applied_to_plan": applied,
    }


async def tool_run_plan_scenario_branch(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    branch_name = str(arguments.get("branch_name") or "What-If Branch").strip() or "What-If Branch"
    assumption_set_id = str(arguments.get("assumption_set_id") or "").strip() or None
    branch_template_id = str(arguments.get("branch_template_id") or "").strip() or None
    compare_updates = extract_plan_settings_updates(arguments)

    raw_branch_events = arguments.get("branch_events")
    if raw_branch_events is None:
        branch_events: list[dict[str, Any]] = []
    elif isinstance(raw_branch_events, list):
        branch_events = [item for item in raw_branch_events if isinstance(item, dict)]
    else:
        raise ValueError("branch_events must be a list of branch event objects.")

    current_value_raw = arguments.get("current_portfolio_value_usd")
    current_value = float(current_value_raw) if current_value_raw is not None else None

    return await compute_plan_scenario_branch(
        plan_id=plan_id,
        branch_name=branch_name,
        current_portfolio_value_usd=current_value,
        assumption_set_id=assumption_set_id,
        branch_template_id=branch_template_id,
        compare_updates=compare_updates,
        raw_branch_events=branch_events,
        services=services,
    )


async def tool_list_plan_saved_simulations(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    limit_raw = arguments.get("limit")
    limit = int(limit_raw) if limit_raw is not None else 10
    return services.plan_workspace.list_saved_simulations(plan_id=plan_id, limit=limit)


async def tool_get_plan_saved_simulation_context(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    saved_simulation_id = str(arguments.get("saved_simulation_id") or "").strip()
    if not saved_simulation_id:
        raise ValueError("saved_simulation_id is required.")
    saved_simulation = services.plan_workspace.get_saved_simulation(
        plan_id=plan_id,
        saved_simulation_id=saved_simulation_id,
    )
    return {
        "plan_id": plan_id,
        "saved_simulation_id": saved_simulation_id,
        "saved_simulation": saved_simulation,
    }


async def tool_compare_plan_saved_simulation_current(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"), workspace=services.plan_workspace)
    saved_simulation_id = str(arguments.get("saved_simulation_id") or "").strip()
    if not saved_simulation_id:
        raise ValueError("saved_simulation_id is required.")
    detail = services.plan_workspace.get_plan(plan_id)
    saved_simulation = services.plan_workspace.get_saved_simulation(
        plan_id=plan_id,
        saved_simulation_id=saved_simulation_id,
    )
    current_settings = detail.get("settings") if isinstance(detail.get("settings"), dict) else {}
    return compare_saved_simulation_to_current_plan(
        plan_id=plan_id,
        saved_simulation=saved_simulation,
        current_settings=current_settings,
    )


async def tool_append_plan_decision(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    plan_id = str(arguments.get("plan_id") or "").strip()
    summary = str(arguments.get("summary") or "").strip()
    rationale = str(arguments.get("rationale") or "").strip()
    status = str(arguments.get("status") or "proposed").strip().lower()
    action_payload = arguments.get("action_payload")
    if not isinstance(action_payload, dict):
        action_payload = None

    if not plan_id:
        active_payload = services.plan_workspace.get_context_payload()
        plan_id = str(active_payload.get("id") or "").strip()

    if not plan_id:
        raise ValueError("No active plan is configured and no plan_id was provided.")

    decision = services.plan_workspace.append_decision(
        plan_id=plan_id,
        summary=summary,
        rationale=rationale,
        status=status or "proposed",
        action_payload=action_payload,
    )
    return {"plan_id": plan_id, "decision": decision}


async def tool_list_workflow_templates(_: dict[str, object]) -> dict[str, object]:
    templates = workflow_runner.templates()
    return {"count": len(templates), "templates": templates}


async def tool_run_workflow(arguments: dict[str, object]) -> dict[str, object]:
    services = workspace_services_or_legacy(None)
    workflow_id = str(arguments.get("workflow_id") or "").strip()
    if not workflow_id:
        raise ValueError("workflow_id is required")

    use_live_snapshot = bool(arguments.get("use_live_snapshot", False))
    params_value = arguments.get("params")
    params = params_value if isinstance(params_value, dict) else {}

    snapshot, previous_snapshot = await resolve_snapshots_for_workflow(
        use_live_snapshot=use_live_snapshot,
        services=services,
    )
    result = workflow_runner.run(
        workflow_id=workflow_id,
        snapshot=snapshot,
        params=params,
        previous_snapshot=previous_snapshot,
    )

    requested_plan_id = arguments.get("plan_id")
    plan_id = str(requested_plan_id).strip() if isinstance(requested_plan_id, str) else ""
    if not plan_id:
        active_id = services.plan_workspace.get_active_plan_id()
        plan_id = active_id or ""

    save_to_plan = bool(arguments.get("save_to_plan", True))
    if save_to_plan and plan_id:
        artifact = services.plan_workspace.write_artifact(
            plan_id=plan_id,
            title=f"{workflow_id.replace('_', ' ').title()} Report",
            markdown=result.get("report_markdown", ""),
            kind=workflow_id,
        )
        result["artifact"] = artifact

    create_recommendations = bool(arguments.get("create_recommendations", True))
    if create_recommendations:
        result["recommendations"] = create_recommendations_from_workflow_result(
            workflow_id=workflow_id,
            result=result,
            plan_id=plan_id or None,
            inbox=services.recommendation_inbox,
        )
    else:
        result["recommendations"] = []

    return result


def configure_copilot_tools() -> None:
    empty_schema: dict[str, object] = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    plan_settings_properties: dict[str, object] = {
        "annual_contribution_usd": {"type": "number"},
        "years": {"type": "integer"},
        "hsa_extra_contribution_usd": {"type": "number"},
        "marginal_tax_rate": {"type": "number"},
        "state_tax_rate": {"type": "number"},
        "simulation_mode": {
            "type": "string",
            "enum": ["fixed", "stochastic", "historical", "monte_carlo"],
        },
        "simulation_monte_carlo_variant": {
            "type": "string",
            "enum": ["p10", "p50", "p90"],
        },
        "simulation_historical_start_year": {"type": "integer"},
        "simulation_seed": {"type": "integer"},
        "household_mode": {"type": "string"},
        "household_partner_income_usd": {"type": "number"},
        "household_partner_income_growth_rate": {"type": "number"},
        "household_partner_retirement_age": {"type": "integer"},
        "household_partner_social_security_annual_usd": {"type": "number"},
        "household_partner_social_security_claiming_age": {"type": "integer"},
        "household_shared_goal_target_usd": {"type": "number"},
        "household_shared_goal_target_year": {"type": "integer"},
        "filing_status": {"type": "string"},
        "drawdown_order": {"type": "string"},
        "roth_conversion_annual_amount_usd": {"type": "number"},
        "roth_conversion_start_age": {"type": "integer"},
        "roth_conversion_end_age": {"type": "integer"},
        "inflation_rate": {"type": "number"},
        "expected_return_baseline": {"type": "number"},
        "expected_return_optimistic": {"type": "number"},
        "expected_return_conservative": {"type": "number"},
    }

    copilot.register_tool(
        name="get_latest_snapshot",
        description="Get the latest locally saved portfolio snapshot summary.",
        parameters=empty_schema,
        handler=tool_get_latest_snapshot,
    )
    copilot.register_tool(
        name="get_live_snapshot",
        description="Refresh market data, build a live BuildWealth portfolio snapshot, and summarize it.",
        parameters=empty_schema,
        handler=tool_get_live_snapshot,
    )
    copilot.register_tool(
        name="get_snapshot_history",
        description="Read Portfolio History snapshots and summarize trend deltas across a time window.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "additionalProperties": False,
        },
        handler=tool_get_snapshot_history,
    )
    copilot.register_tool(
        name="list_import_reports",
        description="List recent BuildWealth Import Reports with IDs, summaries, and native Portfolio History links.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "additionalProperties": False,
        },
        handler=tool_list_import_reports,
    )
    copilot.register_tool(
        name="get_import_report",
        description="Read one BuildWealth Import Report by report_id for audit, reconciliation, and review evidence.",
        parameters={
            "type": "object",
            "properties": {"report_id": {"type": "string"}},
            "required": ["report_id"],
            "additionalProperties": False,
        },
        handler=tool_get_import_report,
    )
    copilot.register_tool(
        name="get_today_dashboard",
        description="Read the daily dashboard summary, checklist, and prioritized recommendations.",
        parameters=empty_schema,
        handler=tool_get_today_dashboard,
    )
    copilot.register_tool(
        name="get_buildwealth_context",
        description=(
            "Build a unified context package for LLM planning decisions across portfolio state, "
            "plan tracking/projections, research highlights, and open recommendations. "
            "Includes cache metadata, warnings, and quality/freshness coverage fields for caveated decision support."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "use_live_snapshot": {"type": "boolean"},
                "include_research": {"type": "boolean"},
                "force_refresh": {"type": "boolean"},
                "detail_level": {
                    "type": "string",
                    "enum": ["light", "full"],
                },
                "research_symbols": {"type": "array", "items": {"type": "string"}},
                "research_period": {"type": "string"},
                "research_interval": {"type": "string"},
                "research_symbol_limit": {"type": "integer"},
                "include_plan_projection": {"type": "boolean"},
                "max_recommendations": {"type": "integer"},
                "max_plan_decisions": {"type": "integer"},
                "summary_max_chars": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_get_buildwealth_context,
    )
    copilot.register_tool(
        name="search_context",
        description=(
            "Search the Context Intelligence registry for field-level profile facts, plan decisions, "
            "research artifacts, watchlist theses, and recommendations. Supports exact filters for "
            "domain, plan_id, symbol, recommendation_status, entity_type, and field_path; use before "
            "giving decision-grade advice that depends on durable user context."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "domain": {"type": "string"},
                "domains": {"type": "array", "items": {"type": "string"}},
                "plan_id": {"type": "string"},
                "symbol": {"type": "string"},
                "symbols": {"type": "array", "items": {"type": "string"}},
                "entity_type": {"type": "string"},
                "entity_types": {"type": "array", "items": {"type": "string"}},
                "recommendation_status": {"type": "string"},
                "field_path": {"type": "string"},
                "limit": {"type": "integer"},
                "rebuild_if_empty": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=tool_search_context,
    )
    copilot.register_tool(
        name="get_financial_profile",
        description="Read the unified financial profile (income, expenses, debt, goals, tax settings).",
        parameters=empty_schema,
        handler=tool_get_financial_profile,
    )
    copilot.register_tool(
        name="get_financial_health",
        description=(
            "Compute a financial health summary with net worth, monthly cash flow, savings rate, "
            "debt-to-income ratio, emergency fund coverage, and an overall health assessment. "
            "Use this to answer questions like 'how am I doing financially?', 'what is my net worth?', "
            "'what is my monthly cash flow?', or 'can I afford this?'."
        ),
        parameters=empty_schema,
        handler=tool_get_financial_health,
    )
    copilot.register_tool(
        name="assess_affordability",
        description=(
            "Assess whether a proposed expense or purchase is affordable given current income, "
            "expenses, and debt. Provide either monthly_amount_usd for recurring expenses, or "
            "purchase_price_usd for large purchases (auto-estimates loan payment). "
            "Optional: loan_rate_pct, loan_term_years, down_payment_pct for custom loan terms. "
            "Returns current vs projected cash flow, savings rate, DTI impact, and an "
            "affordable/stretch/not_affordable assessment."
        ),
        parameters={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What the user wants to buy or spend on"},
                "monthly_amount_usd": {"type": "number", "description": "Monthly cost for recurring expenses"},
                "purchase_price_usd": {"type": "number", "description": "Total price for large purchases (triggers loan estimate)"},
                "loan_rate_pct": {"type": "number", "description": "Annual interest rate as percentage (default 6.5%)"},
                "loan_term_years": {"type": "integer", "description": "Loan term in years (default 30)"},
                "down_payment_pct": {"type": "number", "description": "Down payment as percentage of price (default 20%)"},
            },
            "additionalProperties": False,
        },
        handler=tool_assess_affordability,
    )
    copilot.register_tool(
        name="get_goal_progress",
        description=(
            "Track progress toward financial goals. Shows per-goal progress percentage, "
            "months to target at current savings rate, required monthly savings to hit deadline, "
            "and on_track/ahead/behind/achieved status. Use this for questions like "
            "'when will I reach my goal?', 'am I on track for my down payment?', "
            "or 'what do I need to save monthly to hit $X by date?'."
        ),
        parameters=empty_schema,
        handler=tool_get_goal_progress,
    )
    copilot.register_tool(
        name="simulate_trade",
        description=(
            "Simulate a buy or sell trade against the current portfolio WITHOUT executing it. "
            "Shows how the trade would change allocation, concentration risk, and top holdings. "
            "Use this for questions like 'what if I buy $10k of AAPL?', "
            "'what happens if I sell half my MSFT?', or 'would buying TSLA increase my risk?'."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol (e.g. AAPL, MSFT)"},
                "action": {"type": "string", "enum": ["buy", "sell"], "description": "Buy or sell"},
                "amount_usd": {"type": "number", "description": "Dollar amount to buy or sell"},
                "name": {"type": "string", "description": "Company name (optional, for display)"},
            },
            "required": ["symbol", "action", "amount_usd"],
            "additionalProperties": False,
        },
        handler=tool_simulate_trade,
    )
    copilot.register_tool(
        name="assess_portfolio_fit",
        description=(
            "Review whether an investment candidate fits the user's current portfolio, plan horizon, "
            "cash runway, profile readiness, and research evidence. This is decision support only: "
            "it does not execute trades and should not be presented as hidden buy/sell advice."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol to review, such as AAPL or VTI."},
                "amount_usd": {
                    "type": "number",
                    "description": "Optional dollar amount to include in a bounded portfolio-impact simulation.",
                },
                "proposed_account_id": {
                    "type": "string",
                    "description": "Optional local account id when reviewing account-location fit.",
                },
                "period": {"type": "string", "description": "Research lookback period, default 6mo."},
                "interval": {"type": "string", "description": "Research interval, default 1d."},
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        handler=tool_assess_portfolio_fit,
    )
    copilot.register_tool(
        name="draft_investment_research_recommendation",
        description=(
            "Create a proposed, review-only investment/research recommendation from an investment-fit discussion. "
            "Use only after fit or research context has been inspected. This creates an Inbox item for review and "
            "does not create buy/sell actions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol discussed in the fit review."},
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                "plan_id": {"type": "string"},
                "fit_status": {"type": "string"},
                "fit_score": {"type": "number"},
                "fit_reasons": {"type": "array", "items": {"type": "string"}},
                "fit_risks": {"type": "array", "items": {"type": "string"}},
                "blocking_gaps": {"type": "array", "items": {"type": "string"}},
                "research_evidence_packet_id": {"type": "string"},
                "provider": {"type": "string"},
                "freshness_status": {"type": "string"},
                "confidence": {"type": "string"},
                "coverage_score": {"type": "number"},
                "suggested_action_kind": {
                    "type": "string",
                    "enum": [
                        "review_portfolio_fit",
                        "refresh_research_evidence",
                        "research_dossier",
                        "research_compare",
                        "simulate_trade",
                        "discuss_in_copilot",
                        "update_profile_context",
                    ],
                },
                "source_recommendation_id": {"type": "string"},
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        handler=tool_draft_investment_research_recommendation,
    )
    copilot.register_tool(
        name="draft_watchlist_thesis_revision",
        description=(
            "Draft a structured watchlist thesis revision for user review without saving it. "
            "Use after inspecting research evidence, portfolio fit, or thesis freshness. "
            "The user must explicitly save the reviewed draft."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Watchlist ticker symbol."},
                "data_source": {"type": "string", "description": "Watchlist data source, default OPENBB."},
                "proposed_thesis": {"type": "string", "description": "Revised thesis text to review."},
                "proposed_note": {"type": "string", "description": "Optional supporting note."},
                "reference_price_usd": {"type": "number", "description": "Optional refreshed thesis reference price."},
                "review_window_days": {"type": "integer", "description": "Days until the revised thesis should be reviewed again."},
                "rationale": {"type": "string", "description": "Why the thesis changed."},
                "evidence_gaps": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["symbol", "proposed_thesis"],
            "additionalProperties": False,
        },
        handler=tool_draft_watchlist_thesis_revision,
    )
    copilot.register_tool(
        name="draft_dossier_thesis_revision",
        description=(
            "Draft a structured saved research dossier thesis revision for user review without saving it. "
            "Use after inspecting dossier evidence, packet freshness, or thesis expiration. "
            "The user must explicitly save the reviewed draft."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan id that owns the saved dossier artifact."},
                "artifact_id": {"type": "string", "description": "Saved dossier artifact id."},
                "proposed_thesis": {"type": "string", "description": "Revised dossier thesis text to review."},
                "reference_price_usd": {"type": "number", "description": "Optional refreshed thesis reference price."},
                "review_window_days": {"type": "integer", "description": "Days until the revised thesis should be reviewed again."},
                "rationale": {"type": "string", "description": "Why the thesis changed."},
                "evidence_gaps": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["plan_id", "artifact_id", "proposed_thesis"],
            "additionalProperties": False,
        },
        handler=tool_draft_dossier_thesis_revision,
    )
    copilot.register_tool(
        name="get_onboarding_status",
        description="Read onboarding completion status for unified financial context.",
        parameters=empty_schema,
        handler=tool_get_onboarding_status,
    )
    copilot.register_tool(
        name="draft_financial_profile_update",
        description=(
            "Draft financial profile changes for user review without saving them. "
            "Use this during guided onboarding before calling update_financial_profile."
        ),
        parameters={
            "type": "object",
            "properties": {
                "income_items": {"type": "array", "items": {"type": "object"}},
                "expense_items": {"type": "array", "items": {"type": "object"}},
                "debt_items": {"type": "array", "items": {"type": "object"}},
                "goal_items": {"type": "array", "items": {"type": "object"}},
                "physical_assets": {"type": "array", "items": {"type": "object"}},
                "tax_profile": {"type": "object"},
                "investment_policy": {"type": "object"},
                "flags": {"type": "object"},
                "notes": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=tool_draft_financial_profile_update,
    )
    copilot.register_tool(
        name="update_financial_profile",
        description=(
            "Update financial profile collections and tax settings. "
            "You may provide any subset of income_items, expense_items, debt_items, goal_items, "
            "physical_assets, tax_profile, investment_policy, flags, and notes. Only use after explicit user confirmation."
        ),
        parameters={
            "type": "object",
            "properties": {
                "income_items": {"type": "array", "items": {"type": "object"}},
                "expense_items": {"type": "array", "items": {"type": "object"}},
                "debt_items": {"type": "array", "items": {"type": "object"}},
                "goal_items": {"type": "array", "items": {"type": "object"}},
                "physical_assets": {"type": "array", "items": {"type": "object"}},
                "tax_profile": {"type": "object"},
                "investment_policy": {"type": "object"},
                "flags": {"type": "object"},
                "notes": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=tool_update_financial_profile,
    )
    copilot.register_tool(
        name="list_recommendations",
        description=(
            "List recommendation inbox items. Optional fields: status, plan_id, limit, "
            "include_archived, sort (ranked or created_at)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "plan_id": {"type": "string"},
                "limit": {"type": "integer"},
                "include_archived": {"type": "boolean"},
                "sort": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=tool_list_recommendations,
    )
    copilot.register_tool(
        name="create_recommendation",
        description=(
            "Create a recommendation inbox item. "
            "Required: title, detail. Optional: priority, recommendation_type, source, plan_id, action_payload. "
            "For copilot research-backed recommendations, action_payload should include "
            "research symbols and evidence citations tied to research dossier artifacts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "detail": {"type": "string"},
                "priority": {"type": "string"},
                "recommendation_type": {"type": "string"},
                "source": {"type": "string"},
                "plan_id": {"type": "string"},
                "action_payload": {"type": "object"},
            },
            "required": ["title", "detail"],
            "additionalProperties": False,
        },
        handler=tool_create_recommendation,
    )
    copilot.register_tool(
        name="apply_recommendation",
        description=(
            "Apply a recommendation. For plan_settings_update recommendations, may include plan_settings_updates overrides. "
            "By default this also writes a decision packet artifact with context, assumptions, and cited research symbols, "
            "and attempts to pin research symbols into branch templates."
        ),
        parameters={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "plan_settings_updates": {"type": "object"},
                "rationale": {"type": "string"},
                "decision_status": {"type": "string"},
                "create_decision_packet": {"type": "boolean"},
                "capture_scenario_diff": {"type": "boolean"},
                "decision_packet_research_symbols": {"type": "array", "items": {"type": "string"}},
                "pin_research_bridge": {"type": "boolean"},
                "research_bridge_symbols": {"type": "array", "items": {"type": "string"}},
                "research_bridge_template_id": {"type": "string"},
                "research_bridge_assumption_set_id": {"type": "string"},
            },
            "required": ["recommendation_id"],
            "additionalProperties": False,
        },
        handler=tool_apply_recommendation,
    )
    copilot.register_tool(
        name="preview_recommendation",
        description=(
            "Preview a recommendation before apply/reject. Returns action summary and "
            "scenario-diff preview when applicable."
        ),
        parameters={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "plan_settings_updates": {"type": "object"},
                "capture_scenario_diff": {"type": "boolean"},
                "decision_status": {"type": "string"},
            },
            "required": ["recommendation_id"],
            "additionalProperties": False,
        },
        handler=tool_preview_recommendation,
    )
    copilot.register_tool(
        name="reject_recommendation",
        description=(
            "Reject a recommendation inbox item with an optional reason. "
            "By default captures a scenario-diff preview for plan-setting recommendations. "
            "Optionally write a decision-packet-style rationale artifact."
        ),
        parameters={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "reason": {"type": "string"},
                "capture_scenario_diff": {"type": "boolean"},
                "create_decision_packet": {"type": "boolean"},
                "decision_packet_research_symbols": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["recommendation_id"],
            "additionalProperties": False,
        },
        handler=tool_reject_recommendation,
    )
    copilot.register_tool(
        name="update_recommendation_outcome",
        description=(
            "Record realized outcomes for an applied/rejected recommendation and compute expected-vs-realized "
            "or decision-process calibration."
        ),
        parameters={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "realized_delta_future_value_usd": {"type": "number"},
                "realized_delta_real_value_usd": {"type": "number"},
                "observed_at": {"type": "string"},
                "observation_window_days": {"type": "integer"},
                "measurement_source": {"type": "string"},
                "note": {"type": "string"},
                "process_outcome": {
                    "type": "string",
                    "enum": sorted(INVESTMENT_RESEARCH_PROCESS_OUTCOMES),
                },
                "evidence_sufficiency": {
                    "type": "string",
                    "enum": sorted(INVESTMENT_RESEARCH_EVIDENCE_SUFFICIENCY),
                },
            },
            "required": ["recommendation_id"],
            "additionalProperties": False,
        },
        handler=tool_update_recommendation_outcome,
    )
    copilot.register_tool(
        name="get_recommendation_closure_analytics",
        description=(
            "Summarize expected-vs-realized outcome calibration across closed recommendations."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "plan_id": {"type": "string"},
                "statuses": {"type": "array", "items": {"type": "string"}},
                "include_pending_realized": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=tool_get_recommendation_closure_analytics,
    )
    copilot.register_tool(
        name="create_plan_recommendation_closure_summary",
        description=(
            "Generate a plan-scoped recommendation closure calibration summary and optionally "
            "persist it as a plan artifact for longitudinal decision-review workflows."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "limit": {"type": "integer"},
                "statuses": {"type": "array", "items": {"type": "string"}},
                "include_pending_realized": {"type": "boolean"},
                "write_artifact": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=tool_create_plan_recommendation_closure_summary,
    )
    copilot.register_tool(
        name="run_sync",
        description="Run a full portfolio sync pipeline and regenerate downstream payloads.",
        parameters=empty_schema,
        handler=tool_run_sync,
    )
    copilot.register_tool(
        name="get_sync_status",
        description="Read sync process status, counters, and latest run timestamps.",
        parameters=empty_schema,
        handler=tool_get_sync_status,
    )
    copilot.register_tool(
        name="run_planning_scenarios",
        description=(
            "Run baseline/optimistic/conservative/HSA planning scenarios. "
            "Optional fields: current_portfolio_value_usd, annual_contribution_usd, years, "
            "hsa_extra_contribution_usd, state_tax_rate, include_irmaa, "
            "roth_conversion_annual_amount_usd, roth_conversion_start_age, roth_conversion_end_age, drawdown_order, "
            "simulation_mode, simulation_monte_carlo_variant, simulation_historical_start_year, simulation_seed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "current_portfolio_value_usd": {"type": "number"},
                "annual_contribution_usd": {"type": "number"},
                "years": {"type": "integer"},
                "hsa_extra_contribution_usd": {"type": "number"},
                "state_tax_rate": {"type": "number"},
                "include_irmaa": {"type": "boolean"},
                "roth_conversion_annual_amount_usd": {"type": "number"},
                "roth_conversion_start_age": {"type": "integer"},
                "roth_conversion_end_age": {"type": "integer"},
                "drawdown_order": {"type": "string"},
                "simulation_mode": {
                    "type": "string",
                    "enum": ["fixed", "stochastic", "historical", "monte_carlo"],
                },
                "simulation_monte_carlo_variant": {
                    "type": "string",
                    "enum": ["p10", "p50", "p90"],
                },
                "simulation_historical_start_year": {"type": "integer"},
                "simulation_seed": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_run_planning,
    )
    copilot.register_tool(
        name="compute_tax",
        description=(
            "Compute a tax estimate (federal ordinary/capital/NIIT/FICA plus optional state tax and IRMAA surcharges) "
            "for a given tax-year and filing-status assumption."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tax_year": {"type": "integer"},
                "filing_status": {"type": "string"},
                "earned_income_usd": {"type": "number"},
                "ordinary_income_usd": {"type": "number"},
                "short_term_capital_gains_usd": {"type": "number"},
                "long_term_capital_gains_usd": {"type": "number"},
                "qualified_dividends_usd": {"type": "number"},
                "interest_income_usd": {"type": "number"},
                "social_security_income_usd": {"type": "number"},
                "tax_exempt_interest_income_usd": {"type": "number"},
                "pre_tax_contributions_usd": {"type": "number"},
                "state_tax_rate": {"type": "number"},
                "state_tax_deduction_usd": {"type": "number"},
                "age": {"type": "integer"},
                "include_irmaa": {"type": "boolean"},
                "medicare_months_covered": {"type": "integer"},
                "tax_withholding_usd": {"type": "number"},
            },
            "additionalProperties": False,
        },
        handler=tool_compute_tax,
    )
    copilot.register_tool(
        name="project_income_growth",
        description=(
            "Project annual income over time using income-item growth rates and optional start/end dates. "
            "If income_items are omitted, uses the current financial profile."
        ),
        parameters={
            "type": "object",
            "properties": {
                "start_year": {"type": "integer"},
                "years": {"type": "integer"},
                "default_annual_growth_rate": {"type": "number"},
                "income_items": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        handler=tool_project_income,
    )
    copilot.register_tool(
        name="project_expense_inflation",
        description=(
            "Project annual expenses over time using expense-item inflation rates and optional start/end dates. "
            "If expense_items are omitted, uses the current financial profile."
        ),
        parameters={
            "type": "object",
            "properties": {
                "start_year": {"type": "integer"},
                "years": {"type": "integer"},
                "default_inflation_rate": {"type": "number"},
                "expense_items": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        handler=tool_project_expenses,
    )
    copilot.register_tool(
        name="project_debt_payoff",
        description=(
            "Project debt payoff schedules with minimum/snowball/avalanche/custom strategies. "
            "If debt_items are omitted, uses the current financial profile."
        ),
        parameters={
            "type": "object",
            "properties": {
                "start_date": {"type": "string"},
                "max_years": {"type": "integer"},
                "strategy": {"type": "string"},
                "monthly_accelerated_payment_usd": {"type": "number"},
                "debt_items": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        handler=tool_project_debt_payoff,
    )
    copilot.register_tool(
        name="project_social_security",
        description=(
            "Estimate Social Security retirement benefits and compare claiming ages (default 62/67/70). "
            "Uses fra_monthly_benefit_usd directly when provided, otherwise estimates from earnings_history "
            "or estimated_annual_earnings_usd/profile income."
        ),
        parameters={
            "type": "object",
            "properties": {
                "start_year": {"type": "integer"},
                "years": {"type": "integer"},
                "current_age": {"type": "integer"},
                "birth_year": {"type": "integer"},
                "claiming_age": {"type": "integer"},
                "life_expectancy_age": {"type": "integer"},
                "fra_monthly_benefit_usd": {"type": "number"},
                "estimated_annual_earnings_usd": {"type": "number"},
                "earnings_history": {"type": "array", "items": {"type": "object"}},
                "cola_rate": {"type": "number"},
                "claim_age_options": {"type": "array", "items": {"type": "integer"}},
                "pia_bend_point_1_usd": {"type": "number"},
                "pia_bend_point_2_usd": {"type": "number"},
            },
            "additionalProperties": False,
        },
        handler=tool_project_social_security,
    )
    copilot.register_tool(
        name="project_rmd_schedule",
        description=(
            "Project required minimum distributions (RMDs) for eligible tax-deferred accounts "
            "(401k, 403b, IRA) using SECURE 2.0 start-age rules and IRS Uniform Lifetime factors."
        ),
        parameters={
            "type": "object",
            "properties": {
                "start_year": {"type": "integer"},
                "years": {"type": "integer"},
                "current_age": {"type": "integer"},
                "birth_year": {"type": "integer"},
                "start_age_override": {"type": "integer"},
                "expected_return": {"type": "number"},
                "accounts": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        handler=tool_project_rmd,
    )
    copilot.register_tool(
        name="research_options_chain",
        description="Fetch options chain records for a ticker via OpenBB tooling.",
        parameters={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
            "additionalProperties": False,
        },
        handler=tool_research_options_chain,
    )
    copilot.register_tool(
        name="research_quote",
        description="Fetch latest quote/snapshot fields for a ticker via OpenBB tooling.",
        parameters={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
            "additionalProperties": False,
        },
        handler=tool_research_quote,
    )
    copilot.register_tool(
        name="research_price_history",
        description=(
            "Fetch historical price rows and summary change for a ticker. "
            "Optional fields: period (e.g. 1mo, 6mo, 1y), interval (e.g. 1d, 1wk)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "period": {"type": "string"},
                "interval": {"type": "string"},
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        handler=tool_research_price_history,
    )
    copilot.register_tool(
        name="research_compare",
        description=(
            "Compare multiple tickers using quote + historical-return context. "
            "Returns ranked symbols with period return, volatility, and baseline-relative deltas."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "period": {"type": "string"},
                "interval": {"type": "string"},
                "baseline_symbol": {"type": "string"},
            },
            "required": ["symbols"],
            "additionalProperties": False,
        },
        handler=tool_research_compare,
    )
    copilot.register_tool(
        name="research_dossier",
        description=(
            "Build a research dossier for multiple symbols with thesis, risks, catalysts, "
            "freshness metadata, and optional plan artifact persistence."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "period": {"type": "string"},
                "interval": {"type": "string"},
                "baseline_symbol": {"type": "string"},
                "thesis": {"type": "string"},
                "risks": {"type": "array", "items": {"type": "string"}},
                "catalysts": {"type": "array", "items": {"type": "string"}},
                "plan_id": {"type": "string"},
                "save_to_plan": {"type": "boolean"},
                "include_portfolio_fit": {"type": "boolean"},
            },
            "required": ["symbols"],
            "additionalProperties": False,
        },
        handler=tool_research_dossier,
    )
    copilot.register_tool(
        name="research_dossier_lookup",
        description=(
            "List saved research dossier artifacts for a plan so recommendations can cite evidence "
            "with artifact references."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "limit": {"type": "integer"},
                "include_content": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=tool_research_dossier_lookup,
    )
    copilot.register_tool(
        name="research_watchlist_rank",
        description=(
            "Rank watchlist symbols by a composite score (momentum, trend, target gap, data quality, risk balance). "
            "Returns ranked watchlist rows and score breakdown."
        ),
        parameters={
            "type": "object",
            "properties": {
                "period": {"type": "string"},
                "interval": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_research_watchlist_rank,
    )
    copilot.register_tool(
        name="list_accounts",
        description="List known BuildWealth portfolio accounts with balances and metadata.",
        parameters=empty_schema,
        handler=tool_list_accounts,
    )
    copilot.register_tool(
        name="get_account_balances",
        description=(
            "Read account-level balances (market value, cash, cost basis, performance). "
            "Optional: include per-account top holdings and refresh prices first."
        ),
        parameters={
            "type": "object",
            "properties": {
                "use_live_snapshot": {"type": "boolean"},
                "include_holdings": {"type": "boolean"},
                "holdings_limit_per_account": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_get_account_balances,
    )
    copilot.register_tool(
        name="get_asset_allocation",
        description=(
            "Read allocation breakdowns by asset_class, sector, or region from local holdings metadata."
        ),
        parameters={
            "type": "object",
            "properties": {
                "use_live_snapshot": {"type": "boolean"},
                "dimension": {"type": "string"},
                "top_n": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_get_asset_allocation,
    )
    copilot.register_tool(
        name="list_plans",
        description="List available financial plans in the local Plan Workspace.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "additionalProperties": False,
        },
        handler=tool_list_plans,
    )
    copilot.register_tool(
        name="get_plan_context",
        description="Read context summary for a specific plan or the active plan if omitted.",
        parameters={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=tool_get_plan_context,
    )
    copilot.register_tool(
        name="get_plan_review_context",
        description=(
            "Return bounded v2 Plan review context: active assumption set, top health signals, "
            "selected artifact ids/citations, and optional scenario diff summary. Does not return "
            "full artifact contents or long decision history."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "selected_artifact_ids": {"type": "array", "items": {"type": "string"}},
                "scenario_diff_result": {"type": "object"},
                "max_health_signals": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_get_plan_review_context,
    )
    copilot.register_tool(
        name="get_plan_settings",
        description="Read planning assumptions/settings for a plan or active plan by default.",
        parameters={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=tool_get_plan_settings,
    )
    copilot.register_tool(
        name="get_plan_timeline",
        description="Read timeline events and retirement timeline settings for a plan or active plan by default.",
        parameters={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=tool_get_plan_timeline,
    )
    copilot.register_tool(
        name="get_plan_contribution_rules",
        description="Read contribution allocation rules for a plan or active plan by default.",
        parameters={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=tool_get_plan_contribution_rules,
    )
    copilot.register_tool(
        name="get_plan_assumption_sets",
        description="Read assumption sets for a plan (active set + named sets) or active plan by default.",
        parameters={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=tool_get_plan_assumption_sets,
    )
    copilot.register_tool(
        name="get_plan_branch_templates",
        description="Read saved scenario branch templates/presets for a plan or active plan by default.",
        parameters={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=tool_get_plan_branch_templates,
    )
    copilot.register_tool(
        name="get_plan_tracking",
        description=(
            "Compare plan assumptions against actual portfolio performance. "
            "Returns annualized actual vs expected return, contribution pace, "
            "projected vs actual value, and an on-track/ahead/behind assessment. "
            "Use this to answer 'am I on track?' questions."
        ),
        parameters={
            "type": "object",
            "properties": {"plan_id": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=tool_get_plan_tracking,
    )
    copilot.register_tool(
        name="update_plan_settings",
        description=(
            "Update planning assumptions/settings for a plan and record a decision trail. "
            "Optional fields include annual contribution, years, HSA delta, and return/tax assumptions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                **plan_settings_properties,
                "rationale": {"type": "string"},
                "status": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=tool_update_plan_settings,
    )
    copilot.register_tool(
        name="update_plan_timeline",
        description=(
            "Update timeline events and retirement timeline settings for a plan and record a decision trail. "
            "Provide timeline as an object with events plus optional retirement fields."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "timeline": {"type": "object"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["timeline"],
            "additionalProperties": False,
        },
        handler=tool_update_plan_timeline,
    )
    copilot.register_tool(
        name="add_timeline_event",
        description=(
            "Append a single dated timeline event to a plan using the existing timeline + retirement payload. "
            "Useful for quick life-event modeling without rewriting the full timeline object."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "date": {"type": "string"},
                "label": {"type": "string"},
                "event_type": {"type": "string"},
                "impact_type": {"type": "string"},
                "amount_usd": {"type": "number"},
                "recurring_frequency": {"type": "string"},
                "end_date": {"type": "string"},
                "account_id": {"type": "string"},
                "notes": {"type": "string"},
                "event_id": {"type": "string"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
                "log_decision": {"type": "boolean"},
            },
            "required": ["date", "label"],
            "additionalProperties": False,
        },
        handler=tool_add_timeline_event,
    )
    copilot.register_tool(
        name="set_contribution_rules",
        description=(
            "Set or replace plan contribution-allocation rules. "
            "Supports explicit contribution_rules payload or auto-generating the default "
            "tax-optimized profile from current accounts."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "contribution_rules": {"type": "object"},
                "base_rule": {"type": "object"},
                "rules": {"type": "array", "items": {"type": "object"}},
                "profile_id": {"type": "string"},
                "employer_match_target_usd": {"type": "number"},
                "age": {"type": "integer"},
                "use_default_profile": {"type": "boolean"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=tool_set_contribution_rules,
    )
    copilot.register_tool(
        name="update_plan_assumption_sets",
        description=(
            "Update named assumption sets (active set id + set list) for a plan and record a decision trail."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "assumption_sets": {"type": "object"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["assumption_sets"],
            "additionalProperties": False,
        },
        handler=tool_update_plan_assumption_sets,
    )
    copilot.register_tool(
        name="update_plan_branch_templates",
        description=(
            "Update saved scenario branch templates/presets (default template id + template list) "
            "for a plan and record a decision trail."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "branch_templates": {"type": "object"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
            },
            "required": ["branch_templates"],
            "additionalProperties": False,
        },
        handler=tool_update_plan_branch_templates,
    )
    copilot.register_tool(
        name="pin_watchlist_research_to_plan",
        description=(
            "Pin watchlist thesis/target/tags into a plan branch template so research context is "
            "available in scenario branch workflows."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "branch_template_id": {"type": "string"},
                "template_name": {"type": "string"},
                "branch_name": {"type": "string"},
                "assumption_set_id": {"type": "string"},
                "symbols": {"type": "array", "items": {"type": "string"}},
                "max_symbols": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_pin_watchlist_research_to_plan,
    )
    copilot.register_tool(
        name="run_plan_scenario_diff",
        description=(
            "Run scenario diff between current plan settings and provided overrides. "
            "Optional apply_to_plan=true to commit overrides and log a decision."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "current_portfolio_value_usd": {"type": "number"},
                "assumption_set_id": {"type": "string"},
                "candidate_assumption_set_id": {"type": "string"},
                **plan_settings_properties,
                "apply_to_plan": {"type": "boolean"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=tool_run_plan_scenario_diff,
    )
    copilot.register_tool(
        name="compare_withdrawal_strategies",
        description=(
            "Compare retirement withdrawal strategies (cashflow-only, 4% rule, dynamic guardrails, "
            "bond tent, bucket) against the current plan assumptions and return ranked outcomes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "current_portfolio_value_usd": {"type": "number"},
                "assumption_set_id": {"type": "string"},
                "strategies": {
                    "oneOf": [
                        {"type": "array", "items": {"type": "string"}},
                        {"type": "string"},
                    ]
                },
                "include_raw_results": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=tool_compare_withdrawal_strategies,
    )
    copilot.register_tool(
        name="run_plan_scenario_branch",
        description=(
            "Run a life-event branch from current plan assumptions (e.g., temporary job loss, raise, child costs) "
            "and compare branch outcomes versus the base plan."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "branch_name": {"type": "string"},
                "current_portfolio_value_usd": {"type": "number"},
                "assumption_set_id": {"type": "string"},
                "branch_template_id": {"type": "string"},
                **plan_settings_properties,
                "branch_events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "event_type": {"type": "string"},
                            "impact_type": {"type": "string"},
                            "amount_usd": {"type": "number"},
                            "recurring_frequency": {"type": "string"},
                            "start_year_offset": {"type": "integer"},
                            "duration_months": {"type": "integer"},
                            "account_id": {"type": "string"},
                            "notes": {"type": "string"},
                        },
                        "required": ["label", "amount_usd"],
                        "additionalProperties": False,
                    },
                },
            },
            "additionalProperties": False,
        },
        handler=tool_run_plan_scenario_branch,
    )
    copilot.register_tool(
        name="list_plan_saved_simulations",
        description=(
            "List Saved Simulations for a plan so prior experiments can be reviewed, compared, "
            "or reopened from the Plan scenarios workspace."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        handler=tool_list_plan_saved_simulations,
    )
    copilot.register_tool(
        name="get_plan_saved_simulation",
        description="Read one Saved Simulation by id with its saved inputs and results.",
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "saved_simulation_id": {"type": "string"},
            },
            "required": ["saved_simulation_id"],
            "additionalProperties": False,
        },
        handler=tool_get_plan_saved_simulation_context,
    )
    copilot.register_tool(
        name="compare_plan_saved_simulation_current",
        description=(
            "Compare a Saved Simulation against the current active plan assumptions before relying on it "
            "for a decision."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "saved_simulation_id": {"type": "string"},
            },
            "required": ["saved_simulation_id"],
            "additionalProperties": False,
        },
        handler=tool_compare_plan_saved_simulation_current,
    )
    copilot.register_tool(
        name="append_plan_decision",
        description=(
            "Append a decision entry to plan history. Fields: summary (required), optional plan_id, "
            "rationale, status, and action_payload for structured links such as saved_simulation_id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "summary": {"type": "string"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
                "action_payload": {"type": "object"},
            },
            "required": ["summary"],
            "additionalProperties": False,
        },
        handler=tool_append_plan_decision,
    )
    copilot.register_tool(
        name="list_workflow_templates",
        description="List available financial workflow templates and their default parameters.",
        parameters=empty_schema,
        handler=tool_list_workflow_templates,
    )
    copilot.register_tool(
        name="run_workflow_template",
        description=(
            "Run a workflow template and optionally save a markdown report artifact to a plan. "
            "Fields: workflow_id (required), optional plan_id, use_live_snapshot, save_to_plan, "
            "create_recommendations, params object."
        ),
        parameters={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "use_live_snapshot": {"type": "boolean"},
                "save_to_plan": {"type": "boolean"},
                "create_recommendations": {"type": "boolean"},
                "params": {"type": "object"},
            },
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        handler=tool_run_workflow,
    )


configure_copilot_tools()


@app.get("/api/context/registry/status")
def get_context_registry_status(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(services, permission="copilot.use")
    return resolved_services.context_intelligence_service.get_status()


@app.post("/api/context/registry/rebuild")
def rebuild_context_registry(
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    return resolved_services.context_intelligence_service.rebuild_registry()


@app.post("/api/context/embeddings/rebuild")
def rebuild_context_embeddings(
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    return resolved_services.context_intelligence_service.rebuild_embeddings()


@app.get("/api/context/search")
def search_context_endpoint(
    q: str = "",
    domain: str | None = None,
    domains: str | None = None,
    plan_id: str | None = None,
    symbol: str | None = None,
    symbols: str | None = None,
    recommendation_status: str | None = None,
    entity_type: str | None = None,
    entity_types: str | None = None,
    field_path: str | None = None,
    limit: int = 20,
    rebuild_if_empty: bool = True,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(services, permission="copilot.use")
    return resolved_services.context_intelligence_service.search_context(
        query=q,
        domains=_context_filter_values(domains, domain),
        plan_id=plan_id,
        symbols=_context_filter_values(symbols, symbol),
        entity_types=_context_filter_values(entity_types, entity_type),
        recommendation_status=recommendation_status,
        field_path=field_path,
        limit=max(1, min(int(limit), 100)),
        rebuild_if_empty=rebuild_if_empty,
    )


@app.get("/api/context/candidates")
def list_context_candidates(
    lifecycle_state: str | None = None,
    include_archived: bool = False,
    limit: int = 100,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(services, permission="copilot.use")
    return {
        "items": resolved_services.context_intelligence_service.list_context_candidates(
            lifecycle_state=lifecycle_state,
            include_archived=include_archived,
            limit=max(1, min(int(limit), 5000)),
        )
    }


@app.post("/api/context/candidates")
def draft_context_candidate(
    request: dict[str, Any],
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    return resolved_services.context_intelligence_service.draft_context_candidate(
        source_domain=str(request.get("source_domain") or "manual"),
        source_ref=str(request.get("source_ref") or "manual/context_candidate"),
        extracted_claim=str(request.get("extracted_claim") or ""),
        target_domain=str(request.get("target_domain") or "conversation"),
        target_area=str(request.get("target_area") or "general"),
        target_field=(
            str(request.get("target_field") or "").strip()
            if request.get("target_field") is not None
            else None
        ),
        target_value=request.get("target_value"),
        confidence=str(request.get("confidence") or "medium"),
        metadata=request.get("metadata") if isinstance(request.get("metadata"), dict) else {},
        lifecycle_state=str(request.get("lifecycle_state") or "pending_review"),
        prompt_influence=(
            str(request.get("prompt_influence") or "").strip()
            if request.get("prompt_influence") is not None
            else None
        ),
    )


@app.post("/api/context/candidates/detect-chat")
def detect_chat_context_candidates(
    request: dict[str, Any],
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    items = resolved_services.context_intelligence_service.detect_chat_context_candidates(
        message=str(request.get("message") or ""),
        conversation_id=str(request.get("conversation_id") or "").strip() or None,
        message_index=(
            _coerce_int(request.get("message_index"), 0)
            if request.get("message_index") is not None
            else None
        ),
    )
    return {"count": len(items), "items": items}


@app.post("/api/context/candidates/conversation-summary")
def summarize_conversation_context_candidate(
    request: dict[str, Any],
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    conversation_id = str(request.get("conversation_id") or "").strip()
    if conversation_id:
        try:
            conversation = resolved_services.conversation_store.get(conversation_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        conversation = request.get("conversation")
        if not isinstance(conversation, dict):
            raise HTTPException(status_code=400, detail="conversation or conversation_id is required")
    candidate = resolved_services.context_intelligence_service.summarize_conversation_candidate(
        conversation=conversation,
        min_messages=max(1, min(_coerce_int(request.get("min_messages"), 8), 100)),
    )
    return {"created": candidate is not None, "candidate": candidate}


@app.patch("/api/context/candidates/{candidate_id}/lifecycle")
def update_context_candidate_lifecycle(
    candidate_id: str,
    request: dict[str, Any],
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(
        services,
        permission="copilot.use",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        return resolved_services.context_intelligence_service.update_context_candidate_lifecycle(
            candidate_id,
            lifecycle_state=str(request.get("lifecycle_state") or "pending_review"),
            prompt_influence=(
                str(request.get("prompt_influence") or "").strip()
                if request.get("prompt_influence") is not None
                else None
            ),
            metadata_patch=request.get("metadata") if isinstance(request.get("metadata"), dict) else {},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/context/candidates/{candidate_id}/events")
def list_context_candidate_events(
    candidate_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(services, permission="copilot.use")
    return {"items": resolved_services.context_intelligence_service.list_context_candidate_events(candidate_id)}


@app.get("/api/storage/durable/status", response_model=DurableStorageStatusResponse)
def get_durable_storage_status(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> DurableStorageStatusResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    return DurableStorageStatusResponse.model_validate(
        durable_storage_service_for_workspace(resolved_services).get_status()
    )


@app.post("/api/storage/durable/migrate", response_model=DurableStorageMigrationResponse)
def migrate_durable_storage(
    request: DurableStorageMigrationRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> DurableStorageMigrationResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = durable_storage_service_for_workspace(resolved_services).run_upgrade(
            run_rollback_check=request.run_rollback_check
        )
    except DurableStorageMigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DurableStorageMigrationResponse.model_validate(report)


@app.post("/api/storage/durable/rollback", response_model=DurableStorageRollbackResponse)
def rollback_durable_storage(
    request: DurableStorageRollbackRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> DurableStorageRollbackResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = durable_storage_service_for_workspace(resolved_services).rollback_latest_migration(
            migration_id=request.migration_id
        )
    except DurableStorageMigrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DurableStorageMigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DurableStorageRollbackResponse.model_validate(report)


@app.get("/api/storage/backups", response_model=BackupListResponse)
def list_backups(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> BackupListResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    return BackupListResponse.model_validate(
        backup_restore_service_for_workspace(resolved_services).list_backups()
    )


@app.post("/api/storage/backups", response_model=BackupCreateResponse)
def create_backup(
    request: BackupCreateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> BackupCreateResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = backup_restore_service_for_workspace(resolved_services).create_backup(reason=request.reason)
    except BackupRestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BackupCreateResponse.model_validate(report)


@app.post("/api/storage/backups/restore", response_model=BackupRestoreResponse)
def restore_backup(
    request: BackupRestoreRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> BackupRestoreResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = backup_restore_service_for_workspace(resolved_services).restore_backup(
            backup_id=request.backup_id,
            create_pre_restore_backup=request.create_pre_restore_backup,
        )
    except BackupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BackupRestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BackupRestoreResponse.model_validate(report)


@app.get("/api/storage/protection/status", response_model=StorageProtectionStatusResponse)
def get_storage_protection_status(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> StorageProtectionStatusResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    return StorageProtectionStatusResponse.model_validate(
        data_protection_service_for_workspace(resolved_services).get_status()
    )


@app.get("/api/release-readiness", response_model=ReleaseReadinessResponse)
def get_release_readiness(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> ReleaseReadinessResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    return build_release_readiness_response(services=resolved_services)


@app.post("/api/release-readiness/workflow-verification", response_model=GitActivityEvent)
def record_release_workflow_verification(
    request: ReleaseWorkflowVerificationRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitActivityEvent:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    activity_store = (
        _git_activity_store(resolved_services)
        if hasattr(services, "context")
        else _git_activity_store()
    )
    workflow = str(request.workflow or "product_testing").strip() or "product_testing"
    failed_count = int(request.failed_count or 0)
    passed_count = int(request.passed_count or 0)
    status = request.status
    title_status = "passed" if status == "passed" and failed_count == 0 else status
    event = activity_store.record(
        event_type="product_workflow_verification",
        title=f"Product workflow verification {title_status}",
        message=str(request.notes or "").strip(),
        status=status,
        metadata={
            "workflow": workflow,
            "passed_count": passed_count,
            "failed_count": failed_count,
            "checklist_path": request.checklist_path or RELEASE_READINESS_PRODUCT_TESTING_CHECKLIST,
        },
    )
    return GitActivityEvent.model_validate(event)


@app.put("/api/storage/protection/policy", response_model=StorageProtectionPolicyResponse)
def update_storage_protection_policy(
    request: StorageProtectionPolicyUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> StorageProtectionPolicyResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        policy = data_protection_service_for_workspace(resolved_services).update_policy(
            request.model_dump(exclude_none=True)
        )
    except DataProtectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("protection_policy_updated")
    return StorageProtectionPolicyResponse.model_validate(policy)


@app.post("/api/storage/protection/apply", response_model=StorageProtectionApplyResponse)
def apply_storage_protection(
    request: StorageProtectionApplyRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> StorageProtectionApplyResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        report = data_protection_service_for_workspace(resolved_services).apply_protection(
            request.model_dump(exclude_none=True)
        )
    except DataProtectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageProtectionApplyResponse.model_validate(report)


@app.get("/api/git/policy", response_model=GitPolicyResponse)
def get_git_policy(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitPolicyResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    return GitPolicyResponse.model_validate(_git_policy(resolved_services))


@app.put("/api/git/policy", response_model=GitPolicyResponse)
def update_git_policy(
    request: GitPolicyUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitPolicyResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = git_integration_settings_store_for_workspace(resolved_services).save(
        request.model_dump(exclude_none=True)
    )
    return GitPolicyResponse.model_validate(policy)


@app.post("/api/git/init", response_model=GitInitResponse)
def initialize_git_repository(
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitInitResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = _git_policy(resolved_services)
    try:
        result = _git_checkpoint_service(policy, services=resolved_services).initialize(_git_workspace_policy(policy))
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store(resolved_services).record(
        event_type="repository_initialized",
        title="Git repository initialized",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "initialized"),
        metadata={"workspace_dir": result.get("workspace_dir")},
    )
    return GitInitResponse.model_validate(result)


@app.get("/api/git/status", response_model=GitStatusResponse)
def get_git_status(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitStatusResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    policy = _git_policy(resolved_services)
    try:
        status = _git_repository_service(policy, services=resolved_services).status()
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitStatusResponse.model_validate(status)


@app.get("/api/git/history", response_model=GitHistoryResponse)
def get_git_history(
    limit: int = 20,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitHistoryResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    policy = _git_policy(resolved_services)
    try:
        commits = _git_repository_service(policy, services=resolved_services).history(limit=limit)
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitHistoryResponse.model_validate({"commits": commits})


@app.get("/api/git/diff", response_model=GitDiffResponse)
def get_git_diff(
    ref: str | None = None,
    path: str | None = None,
    max_chars: int = 200_000,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitDiffResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    policy = _git_policy(resolved_services)
    try:
        diff = _git_repository_service(policy, services=resolved_services).diff(
            ref=ref,
            path=path,
            max_chars=max_chars,
        )
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitDiffResponse.model_validate(diff)


@app.get("/api/git/restore-preview", response_model=GitRestorePreviewResponse)
def get_git_restore_preview(
    ref: str,
    path: str | None = None,
    max_chars: int = 120_000,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitRestorePreviewResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    policy = _git_policy(resolved_services)
    try:
        _versioned_workspace_service(policy, services=resolved_services).materialize(_git_workspace_policy(policy))
        preview = _git_repository_service(policy, services=resolved_services).restore_preview(
            ref=ref,
            path=path,
            max_chars=max_chars,
        )
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = _git_restore_preview_token_store(resolved_services).create(preview=preview)
    preview["preview_token"] = token["token"]
    preview["preview_expires_at"] = token["expires_at"]
    _git_activity_store(resolved_services).record(
        event_type="restore_preview",
        title="Restore preview generated",
        message=str(preview.get("message") or ""),
        status=str(preview.get("status") or "ok"),
        ref=preview.get("ref"),
        paths=[item.get("path") for item in preview.get("files", []) if isinstance(item, dict)],
        metadata={
            "path": preview.get("path"),
            "total_files": preview.get("total_files"),
            "read_only": preview.get("read_only"),
        },
    )
    return GitRestorePreviewResponse.model_validate(preview)


@app.post("/api/git/restore-apply", response_model=GitRestoreApplyResponse)
def apply_git_restore(
    request: GitRestoreApplyRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitRestoreApplyResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = _git_policy(resolved_services)
    try:
        if request.preview_token:
            token_store = _git_restore_preview_token_store(resolved_services)
            token_payload = token_store.get(request.preview_token)
            preview_path = token_payload.get("path") if isinstance(token_payload, dict) else None
            _versioned_workspace_service(policy, services=resolved_services).materialize(_git_workspace_policy(policy))
            current_preview = _git_repository_service(policy, services=resolved_services).restore_preview(
                ref=request.ref,
                path=preview_path,
                max_chars=120_000,
            )
            token_store.validate(
                token=request.preview_token,
                ref=request.ref,
                paths=request.paths,
                current_preview=current_preview,
            )
        result = _git_restore_apply_service(policy, services=resolved_services).apply(
            ref=request.ref,
            paths=request.paths,
            confirmation=request.confirmation,
            rationale=request.rationale,
            create_checkpoint_before_apply=request.create_checkpoint_before_apply,
            create_checkpoint_after_apply=request.create_checkpoint_after_apply,
        )
    except (GitRepositoryError, GitRestoreApplyError, GitRestorePreviewTokenError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store(resolved_services).record(
        event_type="restore_apply",
        title="Restore apply completed",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "applied"),
        ref=result.get("ref"),
        paths=[item.get("path") for item in result.get("files", []) if isinstance(item, dict)],
        metadata={
            "applied_files": result.get("applied_files"),
            "before_checkpoint": (result.get("before_checkpoint") or {}).get("commit"),
            "after_checkpoint": (result.get("after_checkpoint") or {}).get("commit"),
        },
    )
    return GitRestoreApplyResponse.model_validate(result)


@app.post("/api/git/checkpoint", response_model=GitCheckpointResponse)
def create_git_checkpoint(
    request: GitCheckpointRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitCheckpointResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = _git_policy(resolved_services)
    try:
        result = _git_checkpoint_service(policy, services=resolved_services).checkpoint(
            policy=_git_workspace_policy(policy),
            event_type=request.event_type,
            message=request.message,
        )
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store(resolved_services).record(
        event_type="checkpoint",
        title=result.get("commit", {}).get("message") if isinstance(result.get("commit"), dict) else "Git checkpoint",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "ok"),
        ref=(result.get("commit") or {}).get("hash") if isinstance(result.get("commit"), dict) else None,
        metadata={
            "files_written": result.get("files_written"),
            "files_removed": result.get("files_removed"),
            "sections": result.get("sections"),
        },
    )
    return GitCheckpointResponse.model_validate(result)


@app.get("/api/git/autogit", response_model=GitAutoGitStateResponse)
def get_git_autogit_state(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitAutoGitStateResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    policy = _git_policy(resolved_services)
    state = _git_autogit_service(policy, services=resolved_services).state(policy=policy)
    return GitAutoGitStateResponse.model_validate(state)


@app.post("/api/git/autogit/run-due", response_model=GitAutoGitStateResponse)
def run_due_git_autogit(
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitAutoGitStateResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    state = _run_due_autogit(resolved_services)
    return GitAutoGitStateResponse.model_validate(state)


@app.get("/api/git/activity", response_model=GitActivityResponse)
def get_git_activity(
    limit: int = 50,
    event_type: str | None = None,
    status: str | None = None,
    ref: str | None = None,
    search: str | None = None,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitActivityResponse:
    resolved_services = route_workspace_services(services, permission="backup.read")
    result = _git_activity_store(resolved_services).query(
        limit=limit,
        event_type=event_type,
        status=status,
        ref=ref,
        search=search,
    )
    return GitActivityResponse.model_validate(result)


@app.post("/api/git/activity/cleanup", response_model=GitActivityCleanupResponse)
def cleanup_git_activity(
    request: GitActivityCleanupRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitActivityCleanupResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        result = _git_activity_store(resolved_services).cleanup(
            dry_run=request.dry_run,
            max_events=request.max_events,
            max_age_days=request.max_age_days,
            include_protected=request.include_protected,
            export_confirmed=request.export_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitActivityCleanupResponse.model_validate(result)


@app.post("/api/git/remote/connect", response_model=GitRemoteOperationResponse)
def connect_git_remote(
    request: GitRemoteConnectRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitRemoteOperationResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = _git_policy(resolved_services)
    try:
        result = _git_repository_service(policy, services=resolved_services).connect_remote(
            remote_url=request.remote_url,
            name=request.remote_name,
        )
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store(resolved_services).record(
        event_type="remote_connect",
        title="Git remote connected",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "connected"),
        metadata={
            "remote_name": result.get("remote_name"),
            "remote": result.get("remote"),
        },
    )
    return GitRemoteOperationResponse.model_validate(result)


@app.post("/api/git/push", response_model=GitRemoteOperationResponse)
def push_git_remote(
    request: GitRemoteOperationRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitRemoteOperationResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = _git_policy(resolved_services)
    try:
        result = _git_repository_service(policy, services=resolved_services).push(remote_name=request.remote_name)
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store(resolved_services).record(
        event_type="remote_push",
        title="Git push completed",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "pushed"),
        metadata={
            "remote_name": result.get("remote_name"),
            "remote": result.get("remote"),
        },
    )
    return GitRemoteOperationResponse.model_validate(result)


@app.post("/api/git/pull", response_model=GitRemoteOperationResponse)
def pull_git_remote(
    request: GitRemoteOperationRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GitRemoteOperationResponse:
    resolved_services = route_workspace_services(
        services,
        permission="backup.write",
        http_request=http_request,
        require_write_token=True,
    )
    policy = _git_policy(resolved_services)
    try:
        result = _git_repository_service(policy, services=resolved_services).pull(remote_name=request.remote_name)
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store(resolved_services).record(
        event_type="remote_pull",
        title="Git pull completed",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "pulled"),
        metadata={
            "remote_name": result.get("remote_name"),
            "remote": result.get("remote"),
        },
    )
    return GitRemoteOperationResponse.model_validate(result)


@app.get("/api/auth/config")
def auth_config() -> dict[str, Any]:
    hosted_enabled = _hosted_auth_enabled()
    return {
        "auth_mode": _auth_mode(),
        "local_auth_enabled": _local_auth_enabled(),
        "hosted_auth_enabled": hosted_enabled,
        "hosted_provider_name": hosted_identity_provider.provider_name,
        "hosted_login_url": "/api/auth/hosted/login" if hosted_enabled else "",
        "hosted_logout_url": "/api/auth/hosted/logout" if hosted_enabled and _hosted_logout_redirect_url() else "",
        "id_token_validation_required": bool(getattr(settings, "auth_oidc_require_id_token", True)),
        "mfa_required": bool(getattr(settings, "auth_oidc_require_mfa", False)),
        "password_reset_managed_by_provider": hosted_enabled,
        "mfa_managed_by_provider": hosted_enabled,
        "passkeys_managed_by_provider": hosted_enabled,
        "account_management_url": str(settings.auth_account_management_url or "").strip(),
        "password_reset_url": str(settings.auth_password_reset_url or "").strip(),
        "mfa_enrollment_url": str(settings.auth_mfa_enrollment_url or "").strip(),
        "passkey_enrollment_url": str(settings.auth_passkey_enrollment_url or "").strip(),
    }


@app.get("/api/auth/hosted/readiness")
async def hosted_auth_readiness() -> dict[str, Any]:
    return await hosted_identity_provider.readiness_report()


@app.get("/api/auth/hosted/login")
async def hosted_login(redirect_to: str = "") -> Response:
    if not _hosted_auth_enabled():
        raise HTTPException(status_code=404, detail="Hosted identity is not configured")
    code_verifier = generate_code_verifier()
    nonce = generate_nonce()
    flow = control_plane_store.create_hosted_login_flow(
        provider=hosted_identity_provider.provider_name,
        code_verifier=code_verifier,
        nonce=nonce,
        redirect_to=_safe_post_login_redirect(redirect_to),
    )
    try:
        authorization_url = await hosted_identity_provider.authorization_url(
            state=flow["state"],
            nonce=nonce,
            code_challenge=code_challenge_for(code_verifier),
        )
    except (HostedIdentityConfigError, httpx.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"Hosted identity login is unavailable: {exc}") from exc
    return RedirectResponse(url=authorization_url, status_code=307)


@app.get("/api/auth/hosted/callback")
async def hosted_callback(
    request: Request,
    response: Response,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
) -> Response:
    if not _hosted_auth_enabled():
        return _auth_error_redirect("Hosted identity is not configured")
    if error:
        detail = error_description or error
        return _auth_error_redirect(f"Hosted identity rejected sign-in: {detail}")
    if not code or not state:
        return _auth_error_redirect("Hosted identity callback is missing code or state")
    try:
        flow = control_plane_store.consume_hosted_login_flow(
            provider=hosted_identity_provider.provider_name,
            state=state,
        )
        profile = await hosted_identity_provider.exchange_code_for_profile(
            code=code,
            code_verifier=flow["code_verifier"],
            expected_nonce=flow["nonce"],
        )
        user = control_plane_store.upsert_hosted_owner_user(
            provider=profile.provider,
            subject=profile.subject,
            email=profile.email,
            display_name=profile.display_name,
            email_verified=profile.email_verified,
            mfa_enabled=profile.mfa_enabled,
            workspace_root_dir=settings.workspace_root_dir,
        )
    except (AuthenticationError, HostedIdentityExchangeError) as exc:
        return _auth_error_redirect(str(exc))
    except (HostedIdentityConfigError, httpx.HTTPError) as exc:
        return _auth_error_redirect(f"Hosted identity callback failed: {exc}")

    workspace = control_plane_store.default_workspace_for_user(str(user["id"]))
    session = control_plane_store.create_session(
        user_id=str(user["id"]),
        active_workspace_id=workspace.id,
        ttl_days=settings.auth_session_days,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response = RedirectResponse(url=flow["redirect_to"], status_code=307)
    response.set_cookie(
        settings.auth_session_cookie_name,
        session["session_token"],
        **_session_cookie_kwargs(),
    )
    return response


@app.post("/api/auth/register")
def register_owner(request: Request, response: Response, payload: dict[str, Any]) -> dict[str, Any]:
    if not _local_auth_enabled():
        raise HTTPException(status_code=403, detail="Local registration is disabled")
    _enforce_auth_rate_limit(
        request,
        key=f"register:ip:{_client_ip(request)}",
        limit=5,
        window_seconds=3600,
        action="register",
    )
    # A private instance registers its owner on first visit and then closes
    # the door: strangers who find the URL must not get accounts. Households
    # that want more members set AUTH_ALLOW_OPEN_REGISTRATION=true.
    if (
        _auth_mode() == "secure"
        and not settings.auth_allow_open_registration
        and control_plane_store.count_active_local_users() > 0
    ):
        raise HTTPException(status_code=403, detail="Registration is closed on this instance")
    try:
        user = control_plane_store.create_owner_user(
            email=str(payload.get("email") or ""),
            password=str(payload.get("password") or ""),
            display_name=str(payload.get("display_name") or ""),
            workspace_root_dir=settings.workspace_root_dir,
        )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="User already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    workspace = control_plane_store.default_workspace_for_user(str(user["id"]))
    session = control_plane_store.create_session(
        user_id=str(user["id"]),
        active_workspace_id=workspace.id,
        ttl_days=settings.auth_session_days,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        settings.auth_session_cookie_name,
        session["session_token"],
        **_session_cookie_kwargs(),
    )
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or "",
            "auth_provider": user.get("auth_provider") or "local",
            "mfa_enabled": bool(user.get("mfa_enabled")),
        },
        "workspace_id": workspace.id,
        "csrf_token": session["csrf_token"],
    }


@app.post("/api/auth/login")
def login(request: Request, response: Response, payload: dict[str, Any]) -> dict[str, Any]:
    if not _local_auth_enabled():
        raise HTTPException(status_code=403, detail="Local password login is disabled")
    email = str(payload.get("email") or "")
    email_key = f"login:email:{control_plane_store.normalize_email(email)}"
    _enforce_auth_rate_limit(
        request,
        key=f"login:ip:{_client_ip(request)}",
        limit=10,
        window_seconds=60,
        action="login",
    )
    # Per-account window counts attempts and is cleared on success, so only
    # sustained failures accumulate — credential stuffing hits this wall.
    _enforce_auth_rate_limit(
        request,
        key=email_key,
        limit=8,
        window_seconds=900,
        action="login",
    )
    try:
        user = control_plane_store.authenticate_local(
            email=email,
            password=str(payload.get("password") or ""),
        )
    except AuthenticationError as exc:
        _audit_event(
            "auth.login_failed",
            outcome="denied",
            target_type="user_email",
            target_id=control_plane_store.normalize_email(email),
            metadata_json=json.dumps({"ip": _client_ip(request)}),
        )
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    auth_rate_limiter.clear(email_key)
    workspace = control_plane_store.default_workspace_for_user(str(user["id"]))
    session = control_plane_store.create_session(
        user_id=str(user["id"]),
        active_workspace_id=workspace.id,
        ttl_days=settings.auth_session_days,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    response.set_cookie(
        settings.auth_session_cookie_name,
        session["session_token"],
        **_session_cookie_kwargs(),
    )
    return {
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or "",
            "auth_provider": user.get("auth_provider") or "local",
            "mfa_enabled": bool(user.get("mfa_enabled")),
        },
        "workspace_id": workspace.id,
        "csrf_token": session["csrf_token"],
    }


@app.post("/api/auth/logout")
def logout(request: Request, response: Response) -> dict[str, Any]:
    control_plane_store.revoke_session(request.cookies.get(settings.auth_session_cookie_name) or "")
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    return {"ok": True, "redirect_to": _hosted_logout_redirect_url() if _hosted_auth_enabled() else ""}


@app.post("/api/auth/logout-all")
def logout_all(
    request: Request,
    response: Response,
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    """Sign out everywhere: revoke every live session for the current user,
    including this one. The control for a lost device or a suspected leak."""
    require_csrf(request)
    revoked = control_plane_store.revoke_all_sessions_for_user(context.user_id)
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    _audit_event(
        "auth.logout_all",
        actor_user_id=context.user_id,
        metadata_json=json.dumps({"revoked_sessions": revoked}),
    )
    return {"ok": True, "revoked_sessions": revoked, "requires_login": True}


@app.get("/api/auth/hosted/logout")
def hosted_logout(request: Request) -> Response:
    control_plane_store.revoke_session(request.cookies.get(settings.auth_session_cookie_name) or "")
    redirect_to = _hosted_logout_redirect_url() or "/v2"
    response = RedirectResponse(url=redirect_to, status_code=307)
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    return response


@app.get("/api/auth/session")
def auth_session(
    request: Request,
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    workspace, _role = control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
    )
    user = control_plane_store.get_user(context.user_id)
    payload = {
        "authenticated": True,
        "auth_mode": context.auth_mode,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or "",
            "auth_provider": user.get("auth_provider") or "local",
            "mfa_enabled": bool(user.get("mfa_enabled")),
        },
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "workspace_type": workspace.workspace_type,
            "is_demo": context.is_demo_workspace,
        },
        "role": context.role,
        "permissions": sorted(context.permissions),
    }
    session_token = request.cookies.get(settings.auth_session_cookie_name) or ""
    if session_token:
        try:
            payload["csrf_token"] = control_plane_store.rotate_csrf_token(session_token)
        except AuthenticationError:
            pass
    return payload


@app.post("/api/account/password")
def change_account_password(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_csrf(request)
    try:
        control_plane_store.change_local_password(
            user_id=context.user_id,
            current_password=str(payload.get("current_password") or ""),
            new_password=str(payload.get("new_password") or ""),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # A password change means the old credential may be compromised — every
    # session dies with it, not just this device's.
    revoked = control_plane_store.revoke_all_sessions_for_user(context.user_id)
    _audit_event(
        "auth.password_changed",
        actor_user_id=context.user_id,
        metadata_json=json.dumps({"revoked_sessions": revoked}),
    )
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    return {
        "ok": True,
        "requires_login": True,
        "message": "Password changed. Sign in again on all devices.",
    }


@app.get("/api/account/export")
def export_account_bundle(context: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    require_permission(context, "account.export")
    return control_plane_store.export_account_bundle(context.user_id)


@app.get("/api/account/data-deletion/preview")
def preview_account_data_deletion(
    scope: str = "workspace",
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_permission(context, "account.delete")
    try:
        return build_account_data_deletion_preview(
            control_plane=control_plane_store,
            workspace_service_factory=workspace_service_factory,
            context=context,
            scope=scope,
            recovery_window_days=RECOVERY_WINDOW_DAYS,
        )
    except (AuthorizationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/account/data-deletion/requests")
def list_account_data_deletion_requests(
    account_user: dict[str, Any] = Depends(get_authenticated_account_user),
) -> dict[str, Any]:
    requests = control_plane_store.list_account_data_deletion_requests_for_user(
        user_id=str(account_user["id"]),
    )
    return {"items": [serialize_deletion_request(request) for request in requests]}


@app.post("/api/account/data-deletion/request")
def request_account_data_deletion(
    request: Request,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(context, "account.delete")
    scope = str(payload.get("scope") or "workspace").strip().lower()
    phrase = required_confirmation_phrase(scope)
    if str(payload.get("confirm") or "").strip().lower() != phrase:
        raise HTTPException(status_code=400, detail=f'Type "{phrase}" to confirm data deletion request')
    try:
        preview = build_account_data_deletion_preview(
            control_plane=control_plane_store,
            workspace_service_factory=workspace_service_factory,
            context=context,
            scope=scope,
            recovery_window_days=RECOVERY_WINDOW_DAYS,
        )
        if not preview.get("can_request"):
            raise ValueError("No active workspace data is available for deletion")
        deletion_request = control_plane_store.create_account_data_deletion_request(
            user_id=context.user_id,
            requested_by_user_id=context.user_id,
            organization_id=context.organization_id,
            workspace_id=context.workspace_id if preview["scope"] == "workspace" else None,
            scope=str(preview["scope"]),
            purge_after=str(preview["purge_after"] or purge_after_for_recovery_window()),
            preview=preview,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": "Data deletion scheduled. You can cancel during the recovery window.",
        "request": serialize_deletion_request(deletion_request),
    }


@app.post("/api/account/data-deletion/{request_id}/cancel")
def cancel_account_data_deletion(
    request_id: str,
    request: Request,
    account_user: dict[str, Any] = Depends(get_authenticated_account_user),
) -> dict[str, Any]:
    require_csrf(request)
    try:
        deletion_request = control_plane_store.cancel_account_data_deletion_request(
            request_id=request_id,
            canceled_by_user_id=str(account_user["id"]),
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "message": "Data deletion canceled.",
        "request": serialize_deletion_request(deletion_request),
    }


@app.delete("/api/account")
def deactivate_account(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(context, "account.delete")
    if str(payload.get("confirm") or "").strip().lower() != "deactivate":
        raise HTTPException(status_code=400, detail='Type "deactivate" to confirm account deactivation')
    try:
        control_plane_store.deactivate_user_account(
            user_id=context.user_id,
            current_password=str(payload.get("current_password") or ""),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    return {
        "ok": True,
        "requires_login": True,
        "message": "Account deactivated. Local workspace files were left in place for manual recovery.",
    }


@app.post("/api/account/hosted/close")
def close_hosted_account_access(
    request: Request,
    response: Response,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(context, "account.delete")
    try:
        control_plane_store.close_hosted_user_access(
            user_id=context.user_id,
            confirm=str(payload.get("confirm") or ""),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.delete_cookie(settings.auth_session_cookie_name, path="/")
    return {
        "ok": True,
        "requires_login": True,
        "message": (
            "BuildWealth access closed. Workspace files, backups, and audit records were retained "
            "under the current hosted retention policy."
        ),
    }


@app.get("/api/security/secrets/rotation/preview")
def preview_secret_key_rotation(
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_permission(context, "workspace.manage")
    return workspace_service_factory.preview_secret_key_rotation()


@app.post("/api/security/secrets/rotation/apply")
def apply_secret_key_rotation(
    request: Request,
    payload: dict[str, Any],
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(context, "workspace.manage")
    if str(payload.get("confirm") or "").strip().lower() != "rotate":
        raise HTTPException(status_code=400, detail='Type "rotate" to confirm secret key rotation')
    result = workspace_service_factory.rotate_secret_key()
    control_plane_store.record_audit_event(
        action="security.workspace_secret_key_rotated",
        actor_user_id=context.user_id,
        organization_id=context.organization_id,
        workspace_id=context.workspace_id,
        target_type="secret_key",
        target_id="workspace_secret_key",
        metadata_json=json.dumps(
            {
                "workspace_count": result.get("workspace_count"),
                "secret_count": result.get("secret_count"),
            }
        ),
    )
    return result


@app.get("/api/workspaces")
def list_workspaces(context: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    workspaces = control_plane_store.list_workspaces_for_user(context.user_id)
    return {
        "active_workspace_id": context.workspace_id,
        "items": [
            {
                "id": workspace.id,
                "name": workspace.name,
                "workspace_type": workspace.workspace_type,
                "is_demo": workspace.workspace_type == "demo",
            }
            for workspace in workspaces
        ],
    }


@app.get("/api/workspaces/current")
def current_workspace(context: RequestContext = Depends(get_request_context)) -> dict[str, Any]:
    workspace, _role = control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
    )
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "is_demo": workspace.workspace_type == "demo",
        "role": context.role,
        "permissions": sorted(context.permissions),
    }


@app.post("/api/workspaces/{workspace_id}/select")
def select_workspace(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_csrf(request)
    workspace, role = control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=workspace_id,
    )
    control_plane_store.select_workspace_for_session(
        token=request.cookies.get(settings.auth_session_cookie_name) or "",
        workspace_id=workspace.id,
    )
    return {
        "id": workspace.id,
        "name": workspace.name,
        "workspace_type": workspace.workspace_type,
        "is_demo": workspace.workspace_type == "demo",
        "role": role,
    }


@app.post("/api/workspaces/{workspace_id}/demo/reset")
def reset_demo_workspace(
    workspace_id: str,
    request: Request,
    context: RequestContext = Depends(get_request_context),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(context, "demo.reset")
    workspace, _role = control_plane_store.get_workspace_for_user(
        user_id=context.user_id,
        workspace_id=workspace_id,
    )
    if workspace.workspace_type != "demo":
        raise HTTPException(status_code=400, detail="Only demo workspaces can be reset")
    paths = workspace_service_factory.paths_for_record(workspace)
    if paths.root.exists():
        shutil.rmtree(paths.root)
    paths.root.mkdir(parents=True, exist_ok=True)
    try:
        summary = _seed_demo_workspace_data(paths.root)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Demo workspace reset failed: {exc}") from exc
    control_plane_store.record_audit_event(
        action="demo_workspace.reset",
        actor_user_id=context.user_id,
        organization_id=context.organization_id,
        workspace_id=workspace.id,
        target_type="workspace",
        target_id=workspace.id,
    )
    return {
        "ok": True,
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "workspace_type": workspace.workspace_type,
            "is_demo": True,
        },
        "summary": summary,
    }


@app.get("/api/settings")
def get_user_settings(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "settings.read")
    return services.settings_store.load_masked()


@app.put("/api/settings")
def update_user_settings(
    payload: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    global llm_client, llm_router

    require_csrf(http_request)
    require_permission(services.context, "settings.write")
    saved = services.settings_store.save(payload)

    # Hot-reload affected services
    saved_explicit_keys = {
        key
        for key in services.settings_store.load_stored_raw()
        if key.startswith("llm_") or key.startswith("openai_")
    }
    llm_router = LLMRouter(
        _llm_config_from_payload(
            saved,
            explicit_keys=saved_explicit_keys,
        ),
        extract_task_overrides(saved),
        usage_ledger=llm_usage_ledger,
    )
    llm_client = llm_router.client_for("chat")
    copilot.llm_client = llm_client

    # Hot-reload context-embedding settings if any embedding key changed.
    # Apply to the running settings object first, then rebuild the embedding
    # client so the next embed_text() call uses the new provider/model/url.
    embedding_changed = any(
        key.startswith("context_embedding") or key == "context_embeddings_enabled"
        for key in payload
    )
    if embedding_changed:
        _apply_context_embedding_settings(saved)
        try:
            services.context_intelligence_service.embedding_client = build_embedding_client_from_settings(settings)
        except Exception:
            # The new client may fail to build (bad URL, missing model). Fall
            # back to a disabled client rather than crash the request — the
            # user can fix and resave.
            services.context_intelligence_service.embedding_client = (
                build_embedding_client_from_settings(settings, force_disabled=True)
                if False
                else services.context_intelligence_service.embedding_client
            )

    return services.settings_store.load_masked()


def _apply_context_embedding_settings(saved: dict[str, Any]) -> None:
    """Push saved user-settings into the live `settings` object so the next
    embedding-client build sees them. Called from PUT /api/settings."""
    apply_context_embedding_overrides(settings, saved)


def _settings_payload_for_probe(
    request: dict[str, Any],
    settings_store: Any | None = None,
) -> tuple[dict[str, Any], set[str]]:
    resolved_store = settings_store or user_settings_store
    current = resolved_store.load_raw()
    payload = dict(current)
    masked_sensitive_keys: set[str] = set()
    provider_changed = False
    provider_transition_keys: set[str] = set()
    explicit_keys: set[str] = {
        key
        for key in resolved_store.load_stored_raw()
        if key.startswith("llm_") or key.startswith("openai_")
    }
    original_provider = str(current.get("llm_provider") or "openai")
    for key, value in request.items():
        if key not in resolved_store.DEFAULTS:
            continue
        if key in resolved_store.SENSITIVE_KEYS and isinstance(value, str) and value.startswith(MASKED_PLACEHOLDER):
            masked_sensitive_keys.add(key)
            continue
        if value is not None:
            payload[key] = value
            if key.startswith("llm_") or key.startswith("openai_"):
                explicit_keys.add(key)
                provider_transition_keys.add(key)
    requested_provider = str(request.get("llm_provider") or payload.get("llm_provider") or "openai")
    current_provider = original_provider
    if requested_provider != current_provider:
        provider_changed = True
        previous_model = default_model_for_provider(current_provider)
        previous_base_url = default_base_url_for_provider(current_provider)
        next_model = default_model_for_provider(requested_provider)
        next_base_url = default_base_url_for_provider(requested_provider)
        request_model = request.get("llm_model")
        request_base_url = request.get("llm_base_url")
        if (
            "llm_model" not in request
            or request_model in ("", previous_model)
            or str(request_model) in provider_default_model_ids(current_provider)
        ):
            payload["llm_model"] = next_model
            explicit_keys.add("llm_model")
        if "llm_base_url" not in request or request_base_url in ("", previous_base_url):
            payload["llm_base_url"] = next_base_url
            explicit_keys.add("llm_base_url")
        if "llm_api_key" not in request or "llm_api_key" in masked_sensitive_keys:
            payload["llm_api_key"] = ""
            explicit_keys.add("llm_api_key")
    if provider_changed:
        explicit_keys.update(provider_transition_keys - {"llm_model", "llm_base_url"})
    return payload, explicit_keys


def _llm_probe_failure_response(payload: dict[str, Any], client: Any, stage: str, detail: str) -> dict[str, Any]:
    return {
        "ok": False,
        "provider": getattr(client, "provider", payload.get("llm_provider", "unknown")),
        "model": getattr(client, "model", payload.get("llm_model")),
        "stage": stage,
        "detail": detail,
        "tool_calls": [],
        "answer": "",
    }


@app.post("/api/settings/test-llm")
async def test_llm_settings(
    request: dict[str, Any],
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = workspace_services_or_legacy(services)
    require_permission(resolved_services.context, "settings.read")
    payload, explicit_keys = _settings_payload_for_probe(request, resolved_services.settings_store)
    client = build_llm_client(
        _llm_config_from_payload(
            payload,
            explicit_keys=explicit_keys,
        )
    )
    try:
        result = await run_tool_call_probe(client)
        if not result.get("ok"):
            raise HTTPException(status_code=400, detail=result)
        return result
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        raise HTTPException(
            status_code=502,
            detail=_llm_probe_failure_response(payload, client, "provider_http_error", detail),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_llm_probe_failure_response(payload, client, "provider_error", str(exc)),
        ) from exc


@app.post("/api/settings/test-embedding")
def test_embedding_settings(
    request: dict[str, Any],
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Probe the embedding provider with the supplied (or saved) settings.

    Builds a transient settings object, instantiates the embedding client,
    and runs a small embed_text() against a fixed string. Returns the
    provider/model used and the embedded vector length on success.
    """
    require_permission(services.context, "settings.read")
    from copy import copy

    probe_settings = copy(settings)
    if request.get("context_embeddings_enabled") is not None:
        val = request["context_embeddings_enabled"]
        probe_settings.context_embeddings_enabled = (
            val.strip().lower() in {"true", "1", "yes", "on"}
            if isinstance(val, str) else bool(val)
        )
    if request.get("context_embedding_provider"):
        probe_settings.context_embedding_provider = str(request["context_embedding_provider"])
    if request.get("context_embedding_model"):
        probe_settings.context_embedding_model = str(request["context_embedding_model"])
    if request.get("context_embedding_base_url"):
        probe_settings.context_embedding_base_url = str(request["context_embedding_base_url"])
    if request.get("context_embedding_timeout_seconds") is not None:
        try:
            probe_settings.context_embedding_timeout_seconds = float(request["context_embedding_timeout_seconds"])
        except (TypeError, ValueError):
            pass

    try:
        client = build_embedding_client_from_settings(probe_settings)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "ok": False,
                "stage": "build_client",
                "detail": str(exc),
                "provider": probe_settings.context_embedding_provider,
                "model": probe_settings.context_embedding_model,
            },
        ) from exc

    if not getattr(client, "enabled", False):
        return {
            "ok": True,
            "enabled": False,
            "provider": getattr(client, "provider", "disabled"),
            "model": getattr(client, "model", ""),
            "detail": "Embeddings are disabled — narrative search will fall back to structured data.",
        }

    try:
        vector = client.embed_text("BuildWealth handshake probe")
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "ok": False,
                "stage": "embed_text",
                "detail": str(exc)[:500],
                "provider": getattr(client, "provider", probe_settings.context_embedding_provider),
                "model": getattr(client, "model", probe_settings.context_embedding_model),
            },
        ) from exc

    return {
        "ok": True,
        "enabled": True,
        "provider": getattr(client, "provider", probe_settings.context_embedding_provider),
        "model": getattr(client, "model", probe_settings.context_embedding_model),
        "vector_length": len(vector) if vector is not None else 0,
        "detail": "Embedding handshake succeeded.",
    }


@app.get("/api/peer-benchmark")
def get_peer_benchmark(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Where the household stands versus US households its age (SCF 2022),
    computed locally from public survey data — no peer network involved."""
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem

    resolved_services = route_workspace_services(services, permission="profile.read")
    profile = resolved_services.financial_profile_store.load()
    try:
        snap = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        snap = None
    health = compute_financial_health(
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
        goal_items=[GoalItem(**g) for g in profile.get("goal_items", [])],
        physical_assets=[PhysicalAssetItem(**a) for a in profile.get("physical_assets", [])],
        snapshot=snap,
    )
    return build_peer_benchmark(
        net_worth_usd=health.net_worth_usd,
        profile_payload=profile,
        current_year=datetime.now(timezone.utc).year,
    )


@app.get("/api/settings/llm-routing")
def get_llm_routing(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Which model serves which task class, after inheritance is resolved."""
    require_permission(services.context, "settings.read")
    return {"tasks": llm_router.describe()}


@app.get("/api/settings/llm-usage")
def get_llm_usage(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Local token ledger: what the household's key spent, by model and task."""
    require_permission(services.context, "settings.read")
    return llm_usage_ledger.summary()


@app.get("/api/settings/context")
def get_context_settings(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Read-only summary of context-intelligence + embedding configuration.

    These knobs are env-driven today (CONTEXT_EMBEDDING_*), not user-editable
    via the user_settings store. The v2 Settings page renders this read-only
    so users can see what's configured without needing to know the env-var
    names. Editing is deferred until Slice 6 wires UserSettingsStore support.
    """
    require_permission(services.context, "settings.read")
    registry_status = services.context_intelligence_service.get_status()
    # Report the client the workspace actually uses — global settings can lag
    # behind the workspace store after a restart.
    embedding_client = getattr(services.context_intelligence_service, "embedding_client", None)
    client_enabled = bool(getattr(embedding_client, "enabled", False))
    return {
        "context_engine_enabled": True,
        "embeddings_enabled": client_enabled,
        "embedding_provider": (
            str(getattr(embedding_client, "provider", "disabled"))
            if client_enabled
            else settings.context_embedding_provider
        ),
        "embedding_model": (
            str(getattr(embedding_client, "model", ""))
            if client_enabled
            else settings.context_embedding_model
        ),
        "embedding_base_url": str(
            getattr(embedding_client, "base_url", settings.context_embedding_base_url)
        ),
        "embedding_timeout_seconds": float(
            getattr(embedding_client, "timeout_seconds", settings.context_embedding_timeout_seconds)
        ),
        "registry": {
            "item_count": int(registry_status.get("item_count", 0) or 0),
            "embedded_count": int(((registry_status.get("embeddings") or {}).get("embedded_count")) or 0),
            "candidate_count": int(((registry_status.get("candidates") or {}).get("candidate_count")) or 0),
            "pending_review_count": int(((registry_status.get("candidates") or {}).get("pending_review_count")) or 0),
            "latest_rebuild_at": registry_status.get("latest_rebuild_at"),
        },
    }


async def on_startup() -> None:
    settings.control_db_path.parent.mkdir(parents=True, exist_ok=True)
    settings.workspace_root_dir.mkdir(parents=True, exist_ok=True)
    settings.secret_key_path.parent.mkdir(parents=True, exist_ok=True)
    settings.import_inbox_dir.mkdir(parents=True, exist_ok=True)
    settings.import_archive_dir.mkdir(parents=True, exist_ok=True)
    settings.import_workbench_dir.mkdir(parents=True, exist_ok=True)
    settings.import_reports_dir.mkdir(parents=True, exist_ok=True)
    settings.durable_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.backup_archive_dir.mkdir(parents=True, exist_ok=True)
    settings.protection_policy_path.parent.mkdir(parents=True, exist_ok=True)
    settings.conversation_dir.mkdir(parents=True, exist_ok=True)
    settings.plans_dir.mkdir(parents=True, exist_ok=True)
    settings.financial_profile_path.parent.mkdir(parents=True, exist_ok=True)
    settings.recommendations_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        protection_policy = data_protection_service.get_policy()
        if protection_policy.get("auto_apply_on_startup"):
            data_protection_service.apply_protection()
    except DataProtectionError as exc:
        print(f"Data protection auto-apply skipped: {exc}")

    global scheduler_task, autogit_task

    _reload_llm_router_from_default_workspace()
    restore_sync_state_from_disk()
    if settings.sync_interval_minutes > 0:
        scheduler_task = asyncio.create_task(scheduled_sync_loop())
    autogit_task = asyncio.create_task(autogit_checkpoint_loop())


def _reload_llm_router_from_default_workspace() -> None:
    """Rebuild the global LLM router from the default household's saved settings.

    PUT /api/settings persists to the workspace settings store (encrypted keys
    included), but the module-level router was built from env + the legacy
    user store — so saved provider, key, and task routing silently vanished on
    restart. Local single-household concern: in hosted auth modes the default
    context can't be resolved and the boot configuration stands.
    """
    global llm_client, llm_router
    try:
        context = control_plane_store.dev_request_context(auth_mode=_auth_mode())
        services = workspace_service_factory.for_context(context)
        saved = services.settings_store.load_raw()
        explicit_keys = {
            key
            for key in services.settings_store.load_stored_raw()
            if key.startswith("llm_") or key.startswith("openai_")
        }
    except Exception:
        return
    llm_router = LLMRouter(
        _llm_config_from_payload(saved, explicit_keys=explicit_keys),
        extract_task_overrides(saved),
        usage_ledger=llm_usage_ledger,
    )
    llm_client = llm_router.client_for("chat")
    copilot.llm_client = llm_client


async def on_shutdown() -> None:
    global scheduler_task, autogit_task
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        scheduler_task = None

    if autogit_task is not None:
        autogit_task.cancel()
        with suppress(asyncio.CancelledError):
            await autogit_task
        autogit_task = None


@app.get("/", include_in_schema=False)
def ui_root() -> Response:
    """Send root visitors to the canonical v2 product surface."""
    v2_index = web_v2_dir / "index.html"
    if v2_index.exists():
        return RedirectResponse(url="/v2", status_code=307)
    return HTMLResponse(
        "<h1>BuildWealth v2 UI not found</h1><p>Expected index.html in orchestrator web-v2 directory.</p>",
        status_code=500,
    )


@app.get("/v2", include_in_schema=False)
@app.get("/v2/", include_in_schema=False)
def ui_root_v2() -> Response:
    index_file = web_v2_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return HTMLResponse(
        "<h1>BuildWealth v2 UI not found</h1><p>Expected index.html in orchestrator web-v2 directory.</p>",
        status_code=500,
    )


def _hosted_static_page(filename: str, title: str) -> Response:
    page_file = web_v2_dir / filename
    if page_file.exists():
        return FileResponse(page_file)
    return HTMLResponse(
        f"<h1>{title} not found</h1><p>Expected {filename} in orchestrator web-v2 directory.</p>",
        status_code=500,
    )


@app.get("/privacy", include_in_schema=False)
@app.get("/privacy/", include_in_schema=False)
def privacy_notice_page() -> Response:
    return _hosted_static_page("privacy.html", "BuildWealth privacy notice")


@app.get("/terms", include_in_schema=False)
@app.get("/terms/", include_in_schema=False)
def terms_page() -> Response:
    return _hosted_static_page("terms.html", "BuildWealth terms")


@app.get("/ai-disclosure", include_in_schema=False)
@app.get("/ai-disclosure/", include_in_schema=False)
def ai_disclosure_page() -> Response:
    return _hosted_static_page("ai-disclosure.html", "BuildWealth AI disclosure")


@app.get("/health")
def health(response: Response) -> dict[str, Any]:
    """Liveness that means something: database answers, data dir writable,
    disk has headroom. Degraded → 503, which flips the Docker healthcheck
    and any uptime monitor watching this URL."""
    report = build_health_report(
        connect=control_plane_store.database.connect,
        data_dir=settings.control_db_path.parent.parent,
    )
    if report["status"] != "ok":
        response.status_code = 503
    return report


@app.get("/api/services/status", response_model=ServiceStatusResponse)
async def get_service_status(refresh: bool = False) -> ServiceStatusResponse:
    return build_native_service_status()


def _fallback_context_freshness_payload() -> dict[str, Any]:
    now = utc_now()
    stale_after = float(settings.copilot_context_snapshot_stale_after_seconds)
    payload: dict[str, Any] = {
        "as_of": now,
        "last_context_generated_at": None,
        "snapshot_as_of": None,
        "snapshot_age_seconds": None,
        "snapshot_stale": None,
        "snapshot_stale_threshold_seconds": stale_after,
        "coverage_score_pct": None,
        "missing_sections": [],
        "warning_count": 0,
    }
    try:
        latest_snapshot = snapshot_store.latest()
    except FileNotFoundError:
        return payload
    except Exception:
        return payload

    snapshot_as_of = latest_snapshot.as_of
    if isinstance(snapshot_as_of, datetime) and snapshot_as_of.tzinfo is None:
        snapshot_as_of = snapshot_as_of.replace(tzinfo=timezone.utc)

    snapshot_age_seconds = max(0.0, (now - snapshot_as_of).total_seconds())
    payload["snapshot_as_of"] = snapshot_as_of
    payload["snapshot_age_seconds"] = round(snapshot_age_seconds, 2)
    payload["snapshot_stale"] = snapshot_age_seconds > stale_after
    return payload


def _build_runtime_telemetry_response() -> RuntimeTelemetryResponse:
    research_stats = copilot_context_research_cache.stats()
    projection_stats = copilot_context_projection_cache.stats()

    context_payload = runtime_telemetry_tracker.context_snapshot()
    fallback_context_payload = _fallback_context_freshness_payload()
    for key, value in fallback_context_payload.items():
        if context_payload.get(key) is None:
            context_payload[key] = value

    cache_quality_payload = summarize_cache_quality(
        enabled=bool(settings.copilot_context_cache_enabled),
        stores=[
            {"name": "research", **research_stats},
            {"name": "baseline_projection", **projection_stats},
        ],
    )
    return RuntimeTelemetryResponse(
        as_of=utc_now(),
        api_latency=runtime_telemetry_tracker.latency_snapshot(top_routes=8),
        context_freshness=context_payload,
        cache_quality=cache_quality_payload,
    )


@app.get("/api/telemetry/runtime", response_model=RuntimeTelemetryResponse)
def get_runtime_telemetry() -> RuntimeTelemetryResponse:
    return _build_runtime_telemetry_response()


@app.get("/api/dashboard/today", response_model=TodayDashboardResponse)
def today_dashboard(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> TodayDashboardResponse:
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(services, permission="workspace.read")
        return build_today_dashboard_response(resolved_services)
    return build_today_dashboard_response()


@app.post("/api/dashboard/today/research-readiness/refresh", response_model=TodayDashboardResponse)
def refresh_today_research_readiness(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> TodayDashboardResponse:
    today_research_evidence_cache.clear()
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(services, permission="workspace.read")
        return build_today_dashboard_response(resolved_services)
    return build_today_dashboard_response()


@app.post("/api/dashboard/today/review-checkpoint", response_model=TodayDashboardResponse)
def record_today_review_checkpoint(
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> TodayDashboardResponse:
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(
            services,
            permission="workspace.read",
            http_request=http_request,
            require_write_token=True,
        )
        dashboard = build_today_dashboard_response(resolved_services)
        resolved_services.today_review_checkpoint_store.save(
            _today_review_checkpoint_from_dashboard(dashboard)
        )
        return build_today_dashboard_response(resolved_services)
    dashboard = build_today_dashboard_response()
    today_review_checkpoint_store.save(_today_review_checkpoint_from_dashboard(dashboard))
    return build_today_dashboard_response()


@app.get("/api/financial-profile", response_model=FinancialProfileResponse)
def get_financial_profile(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> FinancialProfileResponse:
    require_permission(services.context, "profile.read")
    return FinancialProfileResponse(**get_financial_profile_payload(services.financial_profile_store))


@app.put("/api/financial-profile", response_model=FinancialProfileResponse)
def update_financial_profile(
    request: FinancialProfileRequest,
    http_request: Request = Depends(get_current_request),
    source: str | None = None,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> FinancialProfileResponse:
    scoped_services = hasattr(services, "context")
    if http_request is not None:
        require_csrf(http_request)
    if scoped_services:
        require_permission(services.context, "profile.write")
    source_label = str(source or "profile_editor").strip() or "profile_editor"
    saved = save_financial_profile_payload(
        request,
        source=source_label,
        profile_store=services.financial_profile_store if scoped_services else financial_profile_store,
    )
    _record_profile_update_activity(
        source=source_label,
        sections=_profile_update_sections_from_payload(request),
        via_copilot=source_label.startswith("copilot"),
    )
    _queue_autogit_event("financial_profile_updated")
    return FinancialProfileResponse(**saved)


@app.get("/api/onboarding/status", response_model=OnboardingStatusResponse)
def onboarding_status(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> OnboardingStatusResponse:
    require_permission(services.context, "profile.read")
    try:
        latest_snapshot = services.snapshot_store.latest()
    except FileNotFoundError:
        latest_snapshot = None
    active_plan_detail = None
    active_plan_id = services.plan_workspace.get_active_plan_id()
    if active_plan_id:
        try:
            active_plan_detail = services.plan_workspace.get_plan(active_plan_id)
        except PlanNotFoundError:
            active_plan_detail = None
    return build_onboarding_status_response(
        profile_payload=get_financial_profile_payload(services.financial_profile_store),
        latest_snapshot=latest_snapshot,
        active_plan_detail=active_plan_detail,
        load_fallbacks=False,
    )


@app.get("/api/financial-health", response_model=FinancialHealthResponse)
def get_financial_health(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> FinancialHealthResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem

    resolved_services = route_workspace_services(services, permission="profile.read")
    require_permission(resolved_services.context, "portfolio.read")
    profile = resolved_services.financial_profile_store.load()
    try:
        snap = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        snap = None
    return compute_financial_health(
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
        goal_items=[GoalItem(**g) for g in profile.get("goal_items", [])],
        physical_assets=[PhysicalAssetItem(**a) for a in profile.get("physical_assets", [])],
        snapshot=snap,
    )


@app.post("/api/affordability", response_model=AffordabilityResponse)
def check_affordability(
    request: AffordabilityRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> AffordabilityResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, IncomeItem

    resolved_services = route_workspace_services(services, permission="profile.read")
    profile = resolved_services.financial_profile_store.load()
    return assess_affordability(
        description=request.description,
        monthly_amount_usd=request.monthly_amount_usd,
        purchase_price_usd=request.purchase_price_usd,
        loan_rate_pct=request.loan_rate_pct,
        loan_term_years=request.loan_term_years,
        down_payment_pct=request.down_payment_pct,
        income_items=[IncomeItem(**i) for i in profile.get("income_items", [])],
        expense_items=[ExpenseItem(**e) for e in profile.get("expense_items", [])],
        debt_items=[DebtItem(**d) for d in profile.get("debt_items", [])],
    )


@app.post("/api/import/statement")
async def upload_statement(
    file: UploadFile = File(...),
    delimiter: str = Form(","),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Upload a bank/credit card CSV statement and get expense/income suggestions."""
    require_permission(services.context, "imports.read")
    raw = (await file.read()).decode("utf-8", errors="replace")
    result = parse_statement_csv(raw, delimiter=delimiter)
    return {
        "file_name": file.filename,
        "transaction_count": len(result.transactions),
        "date_range_start": result.date_range_start.isoformat() if result.date_range_start else None,
        "date_range_end": result.date_range_end.isoformat() if result.date_range_end else None,
        "months_covered": result.months_covered,
        "total_monthly_expenses": result.total_expenses,
        "total_monthly_income": result.total_income,
        "expense_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "category": s.category,
                "is_fixed": s.is_fixed,
                "transaction_count": s.transaction_count,
                "sample_descriptions": s.sample_descriptions,
            }
            for s in result.expense_suggestions
        ],
        "income_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "source_type": s.source_type,
                "transaction_count": s.transaction_count,
            }
            for s in result.income_suggestions
        ],
        "parse_errors": result.parse_errors,
    }


@app.post("/api/import/statement-vision")
async def upload_statement_image(
    file: UploadFile = File(...),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Read a statement screenshot/photo with the 'extract' vision model and
    return the same reviewable suggestions as a CSV upload — nothing is saved
    until the user applies them."""
    require_permission(services.context, "imports.read")
    image_bytes = await file.read()
    result = await extract_statement_from_image(
        image_bytes,
        str(file.content_type or "").strip().lower(),
        llm_client=llm_router.client_for("extract"),
    )
    if result.status != "ready":
        return {
            "status": result.status,
            "detail": result.detail,
            "file_name": file.filename,
            "warnings": result.warnings,
        }

    parsed = result.parse_result
    return {
        "status": "ready",
        "file_name": file.filename,
        "measurement_source": "ai_vision_extraction",
        "review_note": (
            "Read by AI from your image — check the numbers against the statement "
            "before applying. Nothing is saved until you apply."
        ),
        "account_name": result.account_name,
        "account_type": result.account_type,
        "institution": result.institution,
        "ending_balance_usd": result.ending_balance_usd,
        "statement_period_start": result.statement_period_start,
        "statement_period_end": result.statement_period_end,
        "transaction_count": len(parsed.transactions),
        "date_range_start": parsed.date_range_start.isoformat() if parsed.date_range_start else None,
        "date_range_end": parsed.date_range_end.isoformat() if parsed.date_range_end else None,
        "months_covered": parsed.months_covered,
        "total_monthly_expenses": parsed.total_expenses,
        "total_monthly_income": parsed.total_income,
        "expense_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "category": s.category,
                "is_fixed": s.is_fixed,
                "transaction_count": s.transaction_count,
                "sample_descriptions": s.sample_descriptions,
            }
            for s in parsed.expense_suggestions
        ],
        "income_suggestions": [
            {
                "label": s.label,
                "monthly_amount_usd": s.monthly_amount_usd,
                "source_type": s.source_type,
                "transaction_count": s.transaction_count,
            }
            for s in parsed.income_suggestions
        ],
        "warnings": [*result.warnings, *parsed.parse_errors],
    }


@app.post("/api/import/statement/apply")
def apply_statement_suggestions(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    """Apply selected expense/income suggestions to the financial profile."""
    require_csrf(http_request)
    require_permission(services.context, "profile.write")
    profile = services.financial_profile_store.load()
    added_expenses = 0
    added_income = 0

    for item in request.get("expenses", []):
        from buildwealth_orchestrator.services.statement_importer import _normalize_merchant
        item_id = f"stmt-{_normalize_merchant(item['label'])[:20].replace(' ', '-')}"
        profile.setdefault("expense_items", []).append({
            "id": item_id,
            "label": item["label"],
            "monthly_amount_usd": item["monthly_amount_usd"],
            "category": item.get("category", "general"),
            "is_fixed": item.get("is_fixed", True),
        })
        added_expenses += 1

    for item in request.get("income", []):
        item_id = f"stmt-{item['label'][:20].lower().replace(' ', '-')}"
        profile.setdefault("income_items", []).append({
            "id": item_id,
            "label": item["label"],
            "monthly_amount_usd": item["monthly_amount_usd"],
            "source_type": item.get("source_type", "other"),
            "is_pre_tax": item.get("is_pre_tax", False),
        })
        added_income += 1

    services.financial_profile_store.save(profile)

    return {
        "added_expenses": added_expenses,
        "added_income": added_income,
        "total_expense_items": len(profile.get("expense_items", [])),
        "total_income_items": len(profile.get("income_items", [])),
    }


@app.get("/api/portfolio/holdings")
def get_portfolio_holdings(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_holdings()


@app.get("/api/portfolio/transactions")
def get_portfolio_transactions(
    limit: int = 200,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> list[dict[str, Any]]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.list_transactions(limit=limit)


@app.post("/api/portfolio/transactions")
def add_portfolio_transaction(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    return services.portfolio_store.add_transaction(
        date=request.get("date", ""),
        symbol=request.get("symbol", ""),
        action=request.get("action", "BUY"),
        quantity=float(request.get("quantity", 0)),
        unit_price=float(request.get("unit_price", 0)),
        fee=float(request.get("fee", 0)),
        account=request.get("account", "default"),
        currency=request.get("currency", "USD"),
        note=request.get("note", ""),
        lot_method=request.get("lot_method", "FIFO"),
        name=request.get("name"),
        asset_type=request.get("asset_type"),
        asset_class=request.get("asset_class"),
        sector=request.get("sector"),
        region=request.get("region"),
    )


@app.delete("/api/portfolio/transactions/{transaction_id}")
def delete_portfolio_transaction(
    transaction_id: str,
    request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.delete_transaction(transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {"deleted": True, "id": transaction_id}


@app.post("/api/portfolio/refresh-prices")
async def refresh_portfolio_prices(
    request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(services.context, "portfolio.write")
    holdings_data = await refresh_portfolio(services.portfolio_store, research_service)
    snapshot = build_snapshot_from_holdings(holdings_data)
    services.snapshot_store.write(snapshot)
    return {
        "total_value": holdings_data.get("total_value", 0),
        "holdings_count": len(holdings_data.get("holdings", {})),
        "prices_updated_at": holdings_data.get("prices_updated_at"),
    }


@app.get("/api/portfolio/benchmark", response_model=PortfolioBenchmarkResponse)
async def get_portfolio_benchmark(
    symbols: str | None = None,
    limit: int = 180,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioBenchmarkResponse:
    require_permission(services.context, "portfolio.read")
    resolved_symbols = parse_benchmark_symbols(
        symbols,
        default_symbols=settings.portfolio_benchmark_default_symbols,
    )
    if not resolved_symbols:
        raise HTTPException(status_code=400, detail="At least one benchmark symbol is required.")

    bounded_limit = max(2, min(int(limit), 3650))
    try:
        return await benchmark_service_for_workspace(services).compare(
            benchmark_symbols=resolved_symbols,
            limit=bounded_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/portfolio/attribution", response_model=PortfolioAttributionResponse)
async def get_portfolio_attribution(
    top_n: int = 5,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioAttributionResponse:
    require_permission(services.context, "portfolio.read")
    bounded_top_n = max(1, min(int(top_n), 50))
    try:
        return await attribution_service_for_workspace(services).analyze(
            top_n=bounded_top_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/portfolio/analytics", response_model=PortfolioAnalyticsResponse)
async def get_portfolio_analytics(
    symbols: str | None = None,
    limit: int = 180,
    top_n: int = 5,
    period: str = "1y",
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioAnalyticsResponse:
    require_permission(services.context, "portfolio.read")
    holdings_payload = services.portfolio_store.get_holdings()
    benchmark_response: PortfolioBenchmarkResponse | None = None
    benchmark_error = ""
    attribution_response: PortfolioAttributionResponse | None = None
    attribution_error = ""

    resolved_symbols = parse_benchmark_symbols(
        symbols,
        default_symbols=settings.portfolio_benchmark_default_symbols,
    )
    period_limits = {
        "today": 2,
        "wtd": 7,
        "mtd": 31,
        "ytd": 370,
        "1y": 370,
        "5y": 1826,
        "max": 3650,
    }
    normalized_period = str(period or "1y").strip().lower()
    benchmark_limit = period_limits.get(normalized_period, max(2, min(int(limit), 3650)))
    if resolved_symbols:
        try:
            benchmark_response = await benchmark_service_for_workspace(services).compare(
                benchmark_symbols=resolved_symbols,
                limit=max(2, min(benchmark_limit, 3650)),
            )
        except ValueError as exc:
            benchmark_error = str(exc)

    try:
        attribution_response = await attribution_service_for_workspace(services).analyze(
            top_n=max(1, min(int(top_n), 50)),
        )
    except ValueError as exc:
        attribution_error = str(exc)

    registry_payload = services.asset_registry.search(limit=500)
    profile_payload = services.financial_profile_store.get()
    return PortfolioAnalyticsResponse(
        **build_portfolio_analytics_payload(
            holdings_payload=holdings_payload,
            benchmark_response=benchmark_response,
            benchmark_error=benchmark_error,
            attribution_response=attribution_response,
            attribution_error=attribution_error,
            period=normalized_period,
            snapshot_limit=benchmark_limit,
            registry_rows=registry_payload.get("items") if isinstance(registry_payload, dict) else None,
            debt_items=profile_payload.get("debt_items") if isinstance(profile_payload, dict) else None,
            physical_assets=profile_payload.get("physical_assets") if isinstance(profile_payload, dict) else None,
        )
    )


@app.get("/api/portfolio/accounts")
def get_portfolio_accounts(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> list[dict[str, Any]]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_accounts()


@app.get("/api/portfolio/audit", response_model=PortfolioAuditResponse)
def get_portfolio_audit(
    limit: int = 25,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioAuditResponse:
    require_permission(services.context, "portfolio.read")
    bounded_limit = max(1, min(int(limit), 100))
    payload = build_portfolio_audit_payload(
        import_reports=services.import_workbench_store.list_reports(limit=bounded_limit),
        asset_registry_payload=services.asset_registry.search(limit=500),
        accounts=services.portfolio_store.get_accounts(),
        transactions=services.portfolio_store.list_transactions(limit=500),
        manual_prices_payload=services.portfolio_store.get_manual_prices(),
        cost_basis_payload=services.portfolio_store.get_cost_basis_methods(),
        recommendations=services.recommendation_inbox.list(
            limit=500,
            include_archived=False,
            sort="created_at_desc",
        ),
    )
    return PortfolioAuditResponse(**payload)


@app.get("/api/portfolio/export-bundle")
def get_portfolio_export_bundle(
    limit: int = 10_000,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "export.create")
    bounded_limit = max(1, min(int(limit), 50_000))
    transactions = services.portfolio_store.list_transactions(limit=bounded_limit)
    holdings_payload = services.portfolio_store.get_holdings()
    import_reports = services.import_workbench_store.list_reports(limit=200)
    audit_report = build_portfolio_audit_payload(
        import_reports=import_reports,
        asset_registry_payload=services.asset_registry.search(limit=500),
        accounts=services.portfolio_store.get_accounts(),
        transactions=transactions,
        manual_prices_payload=services.portfolio_store.get_manual_prices(),
        cost_basis_payload=services.portfolio_store.get_cost_basis_methods(),
        recommendations=services.recommendation_inbox.list(
            limit=500,
            include_archived=False,
            sort="created_at_desc",
        ),
    )
    holdings_by_symbol = holdings_payload.get("holdings_by_symbol") if isinstance(holdings_payload.get("holdings_by_symbol"), dict) else {}
    lots = [
        {
            "symbol": symbol,
            **lot,
        }
        for symbol, holding in holdings_by_symbol.items()
        if isinstance(holding, dict)
        for lot in (holding.get("lots") if isinstance(holding.get("lots"), list) else [])
        if isinstance(lot, dict)
    ]
    return {
        "schema_version": 1,
        "generated_at": utc_now().isoformat(),
        "summary": {
            "transactions": len(transactions),
            "holdings": len(holdings_by_symbol),
            "lots": len(lots),
            "import_reports": len(import_reports),
            "audit_events": len(audit_report.get("audit_events", [])),
        },
        "transactions": transactions,
        "holdings": holdings_payload,
        "lots": lots,
        "asset_metadata": services.portfolio_store.get_asset_metadata_map(),
        "manual_prices": services.portfolio_store.get_manual_prices(),
        "fx_rates": services.portfolio_store.get_fx_rates(),
        "fx_rate_history": services.portfolio_store.get_fx_rates_history(),
        "cost_basis_methods": services.portfolio_store.get_cost_basis_methods(),
        "import_reports": import_reports,
        "audit_report": audit_report,
        "recovery_posture": {
            "manual_changes": "Manual metadata, price, FX, and cost-basis changes are local records that can be edited or cleared in Portfolio maintenance.",
            "imports": "Applied import rows are preserved with an Import Report ID so Portfolio History can be traced back to the source file.",
            "destructive_changes": "Before cleanup or removal work, export this bundle and create a Data & Recovery checkpoint.",
        },
    }


@app.get("/api/portfolio/assets/search", response_model=AssetRegistrySearchResponse)
def search_portfolio_assets(
    q: str = "",
    limit: int = 100,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> AssetRegistrySearchResponse:
    require_permission(services.context, "portfolio.read")
    payload = services.asset_registry.search(query=q, limit=limit)
    return AssetRegistrySearchResponse(**payload)


@app.get("/api/portfolio/assets/{symbol}", response_model=AssetRegistryItem)
def get_portfolio_asset(
    symbol: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> AssetRegistryItem:
    require_permission(services.context, "portfolio.read")
    item = services.asset_registry.detail(symbol)
    if item is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    return AssetRegistryItem(**item)


@app.put("/api/portfolio/assets/{symbol}/metadata", response_model=AssetRegistryItem)
def update_portfolio_asset_metadata(
    symbol: str,
    request: AssetMetadataUpdateRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> AssetRegistryItem:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    updates = request.model_dump(exclude_unset=True)
    try:
        item = services.asset_registry.update_metadata(symbol, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AssetRegistryItem(**item)


@app.post("/api/portfolio/accounts")
def add_portfolio_account(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    name = str(request.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Account name is required.")
    return services.portfolio_store.add_account(
        name=name,
        account_type=str(request.get("type") or "taxable"),
        currency=str(request.get("currency") or "USD"),
    )


@app.get("/api/portfolio/watchlist", response_model=WatchlistRankResponse)
def get_portfolio_watchlist(
    period: str = "2y",
    interval: str = "1d",
    sort: str = "ranked",
    limit: int = 200,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> WatchlistRankResponse:
    require_permission(services.context, "portfolio.read")
    payload = build_portfolio_watchlist_payload(
        period=period,
        interval=interval,
        sort=sort,
        limit=limit,
        store=services.portfolio_store,
    )
    return WatchlistRankResponse(**payload)


@app.get("/api/research/watchlist-rank", response_model=WatchlistRankResponse)
def get_research_watchlist_rank(
    period: str = "2y",
    interval: str = "1d",
    limit: int = 200,
) -> WatchlistRankResponse:
    payload = build_portfolio_watchlist_payload(
        period=period,
        interval=interval,
        sort="ranked",
        limit=limit,
    )
    return WatchlistRankResponse(**payload)


@app.post("/api/portfolio/watchlist")
def upsert_portfolio_watchlist_item(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    symbol = str(request.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")

    target_price_raw = request.get("target_price_usd")
    target_price_value: float | None = None
    if target_price_raw not in (None, "", "null"):
        try:
            target_price_value = float(target_price_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="target_price_usd must be a number") from exc
    thesis_reference_raw = request.get("thesis_reference_price_usd")
    thesis_reference_value: float | None = None
    if thesis_reference_raw not in (None, "", "null"):
        try:
            thesis_reference_value = float(thesis_reference_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="thesis_reference_price_usd must be a number") from exc

    try:
        item = services.portfolio_store.upsert_watchlist_item(
            symbol=symbol,
            data_source=str(request.get("data_source") or "OPENBB"),
            note=request.get("note"),
            thesis=request.get("thesis"),
            thesis_reference_price_usd=thesis_reference_value,
            target_price_usd=target_price_value,
            tags=request.get("tags"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@app.put("/api/portfolio/watchlist/{symbol}/thesis")
def save_portfolio_watchlist_thesis_revision(
    symbol: str,
    request: dict[str, Any],
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    scoped_services = hasattr(services, "context")
    if http_request is not None:
        require_csrf(http_request)
    if scoped_services:
        require_permission(services.context, "portfolio.write")
    resolved_portfolio_store = services.portfolio_store if scoped_services else portfolio_store
    resolved_recommendation_inbox = services.recommendation_inbox if scoped_services else recommendation_inbox
    normalized_symbol = str(symbol or request.get("symbol") or "").strip().upper()
    if not normalized_symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    thesis = str(request.get("thesis") or request.get("proposed_thesis") or "").strip()
    if not thesis:
        raise HTTPException(status_code=400, detail="thesis is required")
    note = request.get("note")
    data_source = str(request.get("data_source") or "OPENBB").strip().upper() or "OPENBB"
    reference_raw = (
        request.get("thesis_reference_price_usd")
        if request.get("thesis_reference_price_usd") is not None
        else request.get("reference_price_usd")
    )
    reference_value: float | None = None
    if reference_raw not in (None, "", "null"):
        try:
            reference_value = float(reference_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="thesis_reference_price_usd must be a number") from exc
        if reference_value <= 0:
            raise HTTPException(status_code=400, detail="thesis_reference_price_usd must be greater than 0")

    try:
        review_window_days = max(1, min(int(request.get("review_window_days") or TODAY_THESIS_REVIEW_DAYS), 3650))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="review_window_days must be an integer") from exc

    reviewed_at_dt = utc_now()
    reviewed_at = reviewed_at_dt.isoformat()
    expires_at = str(request.get("thesis_expires_at") or request.get("expires_at") or "").strip()
    if not expires_at:
        expires_at = (reviewed_at_dt + timedelta(days=review_window_days)).isoformat()

    try:
        current = _watchlist_item_for_symbol(
            normalized_symbol,
            data_source,
            store=resolved_portfolio_store,
        ) or {}
        revision_event = _compact_thesis_revision_event(
            target_type="watchlist",
            symbol=normalized_symbol,
            data_source=data_source,
            previous_thesis=current.get("thesis"),
            revised_thesis=thesis,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
            review_window_days=review_window_days,
            request=request,
        )
        resolved_portfolio_store.upsert_watchlist_item(
            symbol=normalized_symbol,
            data_source=data_source,
            thesis=thesis,
            note=str(note) if note is not None else None,
            thesis_reference_price_usd=reference_value,
            tags=request.get("tags") if isinstance(request.get("tags"), list) else None,
        )
        item = resolved_portfolio_store.refresh_watchlist_thesis_review(
            symbol=normalized_symbol,
            data_source=data_source,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
        )
        item = resolved_portfolio_store.append_watchlist_thesis_revision_event(
            symbol=normalized_symbol,
            data_source=data_source,
            event=revision_event,
            limit=THESIS_REVISION_HISTORY_LIMIT,
        )
        _link_thesis_revision_to_recommendation(
            request.get("recommendation_id"),
            revision_event,
            inbox=resolved_recommendation_inbox,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    review = research_thesis_review_metadata(
        {
            "reviewed_at": item.get("thesis_reviewed_at"),
            "expires_at": item.get("thesis_expires_at"),
            "reference_price_usd": item.get("thesis_reference_price_usd"),
        }
    )
    return {
        "item": item,
        "thesis_review": {
            "status": review.get("status") or "current",
            "target": "watchlist",
            "symbol": normalized_symbol,
            "data_source": data_source,
            "reviewed_at": item.get("thesis_reviewed_at"),
            "expires_at": item.get("thesis_expires_at"),
            "reference_price_usd": item.get("thesis_reference_price_usd"),
            "age_days": review.get("age_days"),
        },
    }


@app.delete("/api/portfolio/watchlist/{symbol}")
def delete_portfolio_watchlist_item(
    symbol: str,
    request: Request,
    data_source: str | None = None,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.delete_watchlist_item(symbol, data_source=data_source)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    return {
        "deleted": True,
        "symbol": str(symbol or "").strip().upper(),
        "data_source": str(data_source or "").strip().upper() or None,
    }


@app.get("/api/portfolio/risk-policy")
def get_portfolio_risk_policy(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_risk_policy()


@app.put("/api/portfolio/risk-policy")
def set_portfolio_risk_policy(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    allowed_fields = {
        "single_holding_max_pct",
        "top3_holdings_max_pct",
        "account_max_pct",
        "asset_class_max_pct",
        "sector_max_pct",
        "region_max_pct",
        "hhi_max",
        "effective_positions_min",
    }
    updates: dict[str, float] = {}
    for key in allowed_fields:
        if key not in request:
            continue
        try:
            updates[key] = float(request.get(key))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"{key} must be a number") from exc
    if not updates:
        raise HTTPException(status_code=400, detail="At least one risk threshold field is required.")
    return services.portfolio_store.set_risk_policy_thresholds(updates=updates)


def create_portfolio_review_packet(
    request: PortfolioReviewPacketRequest,
    services: Any | None = None,
) -> PortfolioReviewPacketResponse:
    if not hasattr(services, "portfolio_store"):
        from types import SimpleNamespace

        services = SimpleNamespace(
            context=SimpleNamespace(permissions=ControlPlaneStore.OWNER_PERMISSIONS),
            portfolio_store=portfolio_store,
            snapshot_store=snapshot_store,
            recommendation_inbox=recommendation_inbox,
            plan_workspace=plan_workspace,
            portfolio_review_packet_store=portfolio_review_packet_store,
        )
    require_permission(services.context, "portfolio.write")
    plan_detail: dict[str, Any] | None = None
    if request.plan_id:
        try:
            plan_detail = services.plan_workspace.get_plan(request.plan_id)
        except PlanNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    holdings_payload = services.portfolio_store.get_holdings()
    transactions = services.portfolio_store.list_transactions(limit=request.include_transactions_limit)
    snapshots = services.snapshot_store.recent(limit=request.include_snapshot_history_limit)
    watchlist_items = services.portfolio_store.list_watchlist()
    recommendations = services.recommendation_inbox.list(
        limit=request.include_recommendations_limit,
        plan_id=request.plan_id,
        include_archived=request.include_archived_recommendations,
        sort="created_at_desc",
    )
    generated_at = context_utc_now_iso()

    packet = build_portfolio_review_packet(
        generated_at=generated_at,
        period_days=request.period_days,
        holdings_payload=holdings_payload,
        transactions=transactions,
        snapshots=snapshots,
        watchlist_items=watchlist_items,
        recommendations=recommendations,
        plan_detail=plan_detail,
    )

    default_title = f"Portfolio Review Packet ({packet.get('meta', {}).get('period_end') or generated_at[:10]})"
    resolved_title = str(request.title or "").strip() or default_title
    packet_meta = packet.get("meta") if isinstance(packet.get("meta"), dict) else {}
    packet_meta["title"] = resolved_title
    packet["meta"] = packet_meta
    packet_summary = packet.get("summary") if isinstance(packet.get("summary"), dict) else {}
    packet_summary["title"] = resolved_title
    packet["summary"] = packet_summary

    markdown = build_portfolio_review_packet_markdown(title=resolved_title, packet=packet)
    summary_payload = services.portfolio_review_packet_store.write(
        packet_payload=packet,
        markdown=markdown,
        title=resolved_title,
    )

    plan_artifact: PlanArtifactSummary | None = None
    if request.plan_id and request.save_to_plan_artifacts:
        try:
            artifact_payload = services.plan_workspace.write_artifact(
                plan_id=request.plan_id,
                title=resolved_title,
                markdown=markdown,
                kind="portfolio_review_packet",
            )
            plan_artifact = PlanArtifactSummary(**artifact_payload)
        except PlanNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        stored = services.portfolio_review_packet_store.read(str(summary_payload.get("packet_id") or ""))
    except FileNotFoundError:
        stored = {
            "summary": summary_payload,
            "packet": packet,
            "markdown": markdown,
        }

    _queue_autogit_event("portfolio_review_packet_created")
    return PortfolioReviewPacketResponse(
        summary=stored["summary"],
        packet=stored["packet"],
        markdown=stored["markdown"],
        plan_artifact=plan_artifact,
    )


@app.post("/api/portfolio/review-packets", response_model=PortfolioReviewPacketResponse)
def create_portfolio_review_packet_route(
    request: PortfolioReviewPacketRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioReviewPacketResponse:
    require_csrf(http_request)
    return create_portfolio_review_packet(request, services=services)


@app.get("/api/portfolio/review-packets", response_model=PortfolioReviewPacketListResponse)
def list_portfolio_review_packets(
    limit: int = 20,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioReviewPacketListResponse:
    require_permission(services.context, "portfolio.read")
    items = services.portfolio_review_packet_store.list(limit=max(1, min(int(limit), 200)))
    return PortfolioReviewPacketListResponse(items=items)


@app.get("/api/portfolio/review-packets/{packet_id}", response_model=PortfolioReviewPacketResponse)
def get_portfolio_review_packet(
    packet_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioReviewPacketResponse:
    require_permission(services.context, "portfolio.read")
    try:
        payload = services.portfolio_review_packet_store.read(packet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PortfolioReviewPacketResponse(
        summary=payload["summary"],
        packet=payload["packet"],
        markdown=payload["markdown"],
    )


@app.get("/api/portfolio/cost-basis-methods")
def get_portfolio_cost_basis_methods(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_cost_basis_methods()


@app.put("/api/portfolio/cost-basis-methods")
def set_portfolio_cost_basis_method(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    method = str(request.get("method") or "").strip().upper()
    if not method:
        raise HTTPException(status_code=400, detail="method is required")
    try:
        return services.portfolio_store.set_cost_basis_method(
            method=method,
            account=request.get("account"),
            symbol=request.get("symbol"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/portfolio/manual-prices")
def get_portfolio_manual_prices(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_manual_prices()


@app.put("/api/portfolio/manual-prices")
def set_portfolio_manual_price(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    symbol = str(request.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    try:
        price = float(request.get("price"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="price must be a number") from exc
    note = str(request.get("note") or "")
    try:
        return services.portfolio_store.set_manual_price(symbol=symbol, price=price, note=note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/portfolio/manual-prices/{symbol}")
def clear_portfolio_manual_price(
    symbol: str,
    request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.clear_manual_price(symbol)
    if not deleted:
        raise HTTPException(status_code=404, detail="Manual price override not found.")
    return {"deleted": True, "symbol": str(symbol).upper()}


@app.get("/api/portfolio/fx-rates")
def get_portfolio_fx_rates(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_fx_rates()


@app.get("/api/portfolio/fx-rates/history")
def get_portfolio_fx_rate_history(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.get_fx_rates_history()


@app.put("/api/portfolio/fx-rates")
def set_portfolio_fx_rate(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    currency = str(request.get("currency") or "").strip().upper()
    if not currency:
        raise HTTPException(status_code=400, detail="currency is required")
    try:
        rate = float(request.get("rate"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="rate must be a number") from exc
    base_currency = request.get("base_currency")
    try:
        return services.portfolio_store.set_fx_rate(
            currency=currency,
            rate=rate,
            base_currency=str(base_currency).strip().upper() if base_currency is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/portfolio/fx-rates/history")
def set_portfolio_fx_rate_history(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    currency = str(request.get("currency") or "").strip().upper()
    if not currency:
        raise HTTPException(status_code=400, detail="currency is required")
    rates_by_date = request.get("rates_by_date")
    if not isinstance(rates_by_date, dict):
        raise HTTPException(status_code=400, detail="rates_by_date must be an object of date->rate")
    base_currency = request.get("base_currency")
    try:
        return services.portfolio_store.set_fx_rate_history(
            currency=currency,
            rates_by_date=rates_by_date,
            base_currency=str(base_currency).strip().upper() if base_currency is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/portfolio/fx-rates/{currency}")
def clear_portfolio_fx_rate(
    currency: str,
    request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(request)
    require_permission(services.context, "portfolio.write")
    deleted = services.portfolio_store.clear_fx_rate(currency)
    if not deleted:
        raise HTTPException(status_code=404, detail="FX rate not found or cannot clear base currency.")
    return {"deleted": True, "currency": str(currency).upper()}


@app.get("/api/portfolio/custom-assets")
def get_portfolio_custom_assets(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> list[dict[str, Any]]:
    require_permission(services.context, "portfolio.read")
    return services.portfolio_store.list_custom_assets()


@app.post("/api/portfolio/custom-assets")
def create_portfolio_custom_asset(
    request: dict[str, Any],
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_csrf(http_request)
    require_permission(services.context, "portfolio.write")
    name = str(request.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        value = float(request.get("value"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="value must be a number") from exc

    try:
        return services.portfolio_store.create_custom_asset(
            name=name,
            value=value,
            account=str(request.get("account") or "default"),
            asset_type=str(request.get("asset_type") or "custom_asset"),
            asset_class=request.get("asset_class"),
            sector=request.get("sector"),
            region=request.get("region"),
            symbol=request.get("symbol"),
            date=request.get("date"),
            note=str(request.get("note") or ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/portfolio/simulate-trade", response_model=SimulateTradeResponse)
def simulate_portfolio_trade(
    request: SimulateTradeRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> SimulateTradeResponse:
    resolved_services = route_workspace_services(services, permission="portfolio.read")
    try:
        snap = resolved_services.snapshot_store.latest()
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="No portfolio snapshot available. Run sync first.")
    return simulate_trade(
        snapshot=snap,
        symbol=request.symbol,
        action=request.action,
        amount_usd=request.amount_usd,
        name=request.name,
    )


def build_portfolio_fit_assessment_payload(
    request: PortfolioFitAssessmentRequest,
    *,
    services: WorkspaceServices | None = None,
) -> PortfolioFitAssessmentResponse:
    if not request.symbol:
        raise ValueError("Portfolio-fit assessment requires a symbol.")
    resolved_snapshot_store = services.snapshot_store if services is not None else snapshot_store
    resolved_portfolio_store = services.portfolio_store if services is not None else portfolio_store
    resolved_profile_store = services.financial_profile_store if services is not None else financial_profile_store
    resolved_plan_workspace = services.plan_workspace if services is not None else plan_workspace

    try:
        snap = resolved_snapshot_store.latest()
    except FileNotFoundError:
        snap = None

    holdings_payload: dict[str, Any] = {}
    try:
        holdings_payload = resolved_portfolio_store.get_holdings()
    except Exception:
        holdings_payload = {}

    profile_payload = (
        get_financial_profile_payload(resolved_profile_store)
        if services is not None
        else get_financial_profile_payload()
    )
    investment_policy = (
        profile_payload.get("investment_policy")
        if isinstance(profile_payload.get("investment_policy"), dict)
        else {}
    )
    if investment_policy:
        holdings_payload = dict(holdings_payload)
        holdings_payload["investment_policy"] = investment_policy
    profile_readiness = _build_profile_readiness_summary(
        income_items=profile_payload.get("income_items") if isinstance(profile_payload.get("income_items"), list) else [],
        expense_items=profile_payload.get("expense_items") if isinstance(profile_payload.get("expense_items"), list) else [],
        debt_items=profile_payload.get("debt_items") if isinstance(profile_payload.get("debt_items"), list) else [],
        goal_items=profile_payload.get("goal_items") if isinstance(profile_payload.get("goal_items"), list) else [],
        physical_assets=profile_payload.get("physical_assets") if isinstance(profile_payload.get("physical_assets"), list) else [],
        flags=profile_payload.get("flags") if isinstance(profile_payload.get("flags"), dict) else {},
        tax_profile=profile_payload.get("tax_profile") if isinstance(profile_payload.get("tax_profile"), dict) else {},
        investment_policy=investment_policy,
        profile_metadata=profile_payload.get("profile_metadata")
        if isinstance(profile_payload.get("profile_metadata"), dict)
        else {},
    )

    emergency_fund_months: float | None = None
    try:
        from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem

        health = compute_financial_health(
            income_items=[IncomeItem(**i) for i in profile_payload.get("income_items", [])],
            expense_items=[ExpenseItem(**e) for e in profile_payload.get("expense_items", [])],
            debt_items=[DebtItem(**d) for d in profile_payload.get("debt_items", [])],
            goal_items=[GoalItem(**g) for g in profile_payload.get("goal_items", [])],
            physical_assets=[PhysicalAssetItem(**a) for a in profile_payload.get("physical_assets", [])],
            snapshot=snap,
        )
        emergency_fund_months = health.emergency_fund_months
    except Exception:
        emergency_fund_months = None

    try:
        evidence_packet = research_service.evidence_packet(
            symbol=request.symbol,
            period=request.period,
            interval=request.interval,
        )
    except ValueError:
        raise
    except Exception:
        evidence_packet = None

    return assess_portfolio_fit(
        symbol=request.symbol,
        amount_usd=request.amount_usd,
        proposed_account_id=request.proposed_account_id,
        evidence_packet=evidence_packet,
        snapshot=snap,
        holdings_payload=holdings_payload,
        profile_readiness_payload=profile_readiness.model_dump(mode="json"),
        emergency_fund_months=emergency_fund_months,
        active_plan_detail=(
            resolve_active_plan_detail(workspace=resolved_plan_workspace)
            if services is not None
            else resolve_active_plan_detail()
        ),
    )


@app.post("/api/portfolio/fit-assessment", response_model=PortfolioFitAssessmentResponse)
def portfolio_fit_assessment(
    request: PortfolioFitAssessmentRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioFitAssessmentResponse:
    require_permission(services.context, "portfolio.read")
    try:
        return build_portfolio_fit_assessment_payload(request, services=services)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/goals/progress", response_model=GoalProgressResponse)
def get_goal_progress(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> GoalProgressResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem

    resolved_services = route_workspace_services(services, permission="profile.read")
    require_permission(resolved_services.context, "portfolio.read")
    profile = resolved_services.financial_profile_store.load()
    try:
        snap = resolved_services.snapshot_store.latest()
        portfolio_value = snap.total_value_usd
    except FileNotFoundError:
        portfolio_value = 0.0

    income_items = [IncomeItem(**i) for i in profile.get("income_items", [])]
    expense_items = [ExpenseItem(**e) for e in profile.get("expense_items", [])]
    debt_items = [DebtItem(**d) for d in profile.get("debt_items", [])]
    goal_items = [GoalItem(**g) for g in profile.get("goal_items", [])]

    gross_income = sum(i.monthly_amount_usd for i in income_items)
    total_expenses = sum(e.monthly_amount_usd for e in expense_items)
    total_debt_payments = sum(d.minimum_payment_usd or 0.0 for d in debt_items)
    monthly_surplus = gross_income - total_expenses - total_debt_payments

    return compute_goal_progress(
        goals=goal_items,
        monthly_surplus_usd=monthly_surplus,
        portfolio_value_usd=portfolio_value,
    )


@app.get("/api/recommendations", response_model=list[RecommendationItem])
def list_recommendations(
    limit: int = 100,
    status: str | None = None,
    plan_id: str | None = None,
    include_archived: bool = False,
    sort: str = "ranked",
    services: WorkspaceServices = Depends(get_workspace_services),
) -> list[RecommendationItem]:
    require_permission(services.context, "recommendations.read")
    rows = _recommendation_list(
        limit=limit,
        status=status,
        plan_id=plan_id,
        include_archived=include_archived,
        sort=sort,
        inbox=services.recommendation_inbox,
    )
    return [RecommendationItem(**row) for row in rows]


@app.get("/api/recommendations/closure-analytics", response_model=RecommendationClosureAnalyticsResponse)
def get_recommendation_closure_analytics(
    limit: int = 200,
    statuses: str = "applied,rejected",
    include_pending_realized: bool = True,
    plan_id: str | None = None,
) -> RecommendationClosureAnalyticsResponse:
    payload = build_recommendation_closure_analytics_payload(
        limit=limit,
        statuses=statuses,
        include_pending_realized=include_pending_realized,
        plan_id=plan_id,
    )
    return RecommendationClosureAnalyticsResponse(**payload)


@app.post("/api/recommendations/generate/portfolio-risk", response_model=RecommendationFactoryResponse)
def generate_portfolio_risk_recommendation_candidates(
    request: PortfolioRiskRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    holdings_payload = services.portfolio_store.get_holdings()
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_portfolio_risk_recommendations(
        holdings_payload=holdings_payload,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
        accounts=services.portfolio_store.get_accounts(),
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("portfolio_risk_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/plan-tracking", response_model=RecommendationFactoryResponse)
def generate_plan_tracking_recommendation_candidates(
    request: PlanTrackingRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        plan_id = resolve_plan_id_or_active(request.plan_id, workspace=services.plan_workspace)
        detail = services.plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = services.snapshot_store.recent(limit=90)
    transactions = services.portfolio_store.list_transactions(limit=10_000)
    planner_defaults = {
        "annual_contribution_usd": settings.planner_annual_contribution_usd,
        "expected_return_baseline": settings.planner_expected_return_baseline,
        "hsa_extra_contribution_usd": settings.planner_hsa_delta_default,
    }
    tracking_payload = compute_plan_tracking(
        plan_id=plan_id,
        plan_title=detail.get("title", ""),
        plan_settings=plan_settings,
        planner_defaults=planner_defaults,
        snapshots=snapshots,
        transactions=transactions,
    ).model_dump(mode="json")
    tracking_payload["plan_settings"] = plan_settings.model_dump(mode="json", exclude_none=True)
    tracking_payload["planner_defaults"] = planner_defaults
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_plan_tracking_recommendations(
        plan_tracking_payload=tracking_payload,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("plan_tracking_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/cash-liquidity", response_model=RecommendationFactoryResponse)
def generate_cash_liquidity_recommendation_candidates(
    request: CashLiquidityRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    holdings_payload = services.portfolio_store.get_holdings()
    financial_profile_payload = get_financial_profile_payload(services.financial_profile_store)
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_cash_liquidity_recommendations(
        holdings_payload=holdings_payload,
        financial_profile_payload=financial_profile_payload,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("cash_liquidity_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/profile-completeness", response_model=RecommendationFactoryResponse)
def generate_profile_completeness_recommendation_candidates(
    request: ProfileCompletenessRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    profile_payload = get_financial_profile_payload(services.financial_profile_store)
    profile_readiness = build_onboarding_status_response(
        profile_payload=profile_payload,
        load_fallbacks=False,
    ).profile_readiness
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_profile_completeness_recommendations(
        profile_readiness_payload=profile_readiness.model_dump(mode="json") if profile_readiness else {},
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("profile_completeness_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/stale-assumptions", response_model=RecommendationFactoryResponse)
def generate_stale_assumption_recommendation_candidates(
    request: StaleAssumptionRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        plan_id = resolve_plan_id_or_active(request.plan_id, workspace=services.plan_workspace)
        detail = services.plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = services.snapshot_store.recent(limit=90)
    transactions = services.portfolio_store.list_transactions(limit=10_000)
    planner_defaults = {
        "annual_contribution_usd": settings.planner_annual_contribution_usd,
        "expected_return_baseline": settings.planner_expected_return_baseline,
        "hsa_extra_contribution_usd": settings.planner_hsa_delta_default,
    }
    tracking_payload = compute_plan_tracking(
        plan_id=plan_id,
        plan_title=detail.get("title", ""),
        plan_settings=plan_settings,
        planner_defaults=planner_defaults,
        snapshots=snapshots,
        transactions=transactions,
    ).model_dump(mode="json")
    tracking_payload["plan_settings"] = plan_settings.model_dump(mode="json", exclude_none=True)
    tracking_payload["planner_defaults"] = planner_defaults

    profile_payload = get_financial_profile_payload(services.financial_profile_store)
    profile_readiness = build_onboarding_status_response(
        profile_payload=profile_payload,
        latest_snapshot=None,
        active_plan_detail=detail,
        load_fallbacks=False,
    ).profile_readiness
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_stale_assumption_recommendations(
        plan_detail_payload=detail,
        plan_tracking_payload=tracking_payload,
        profile_readiness_payload=profile_readiness.model_dump(mode="json") if profile_readiness else {},
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("stale_assumption_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/allocation-drift", response_model=RecommendationFactoryResponse)
def generate_allocation_drift_recommendation_candidates(
    request: AllocationDriftRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    holdings_payload = services.portfolio_store.get_holdings()
    profile_payload = get_financial_profile_payload(services.financial_profile_store)
    investment_policy = (
        profile_payload.get("investment_policy")
        if isinstance(profile_payload.get("investment_policy"), dict)
        else {}
    )
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_allocation_drift_recommendations(
        holdings_payload=holdings_payload,
        investment_policy=investment_policy,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("allocation_drift_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/fund-overlap", response_model=RecommendationFactoryResponse)
def generate_fund_overlap_recommendation_candidates(
    request: FundOverlapRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_fund_overlap_recommendations(
        holdings_payload=services.portfolio_store.get_holdings(),
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("fund_overlap_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/due-outcome-review", response_model=RecommendationFactoryResponse)
def generate_due_outcome_review_recommendation_candidates(
    request: DueOutcomeReviewRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_due_outcome_review_recommendations(
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("due_outcome_review_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/watchlist-research", response_model=RecommendationFactoryResponse)
def generate_watchlist_research_recommendation_candidates(
    request: WatchlistResearchRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        watchlist_payload = build_portfolio_watchlist_payload(
            period=request.period,
            interval=request.interval,
            limit=request.limit,
            sort="ranked",
            store=services.portfolio_store,
        )
    except AttributeError:
        watchlist_payload = {
            "period": request.period,
            "interval": request.interval,
            "count": 0,
            "items": [],
            "warnings": ["Portfolio store does not expose watchlist items."],
        }

    fit_assessments_by_symbol: dict[str, dict[str, Any]] = {}
    items = watchlist_payload.get("items") if isinstance(watchlist_payload.get("items"), list) else []
    for item in items[: request.limit]:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip()
        if not symbol:
            continue
        try:
            fit_assessments_by_symbol[symbol.upper()] = build_portfolio_fit_assessment_payload(
                PortfolioFitAssessmentRequest(symbol=symbol, period=request.period, interval=request.interval),
                services=services,
            ).model_dump(mode="json")
        except Exception as exc:
            fit_assessments_by_symbol[symbol.upper()] = {
                "symbol": symbol.upper(),
                "fit_status": "needs_more_context",
                "fit_score": 0.0,
                "fit_reasons": [],
                "fit_risks": [f"Portfolio-fit assessment unavailable: {exc}"],
                "blocking_gaps": ["portfolio_fit"],
                "recommended_next_step": "research_more",
            }

    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_watchlist_research_recommendations(
        watchlist_rank_payload=watchlist_payload,
        fit_assessments_by_symbol=fit_assessments_by_symbol,
        existing_recommendations=existing_recommendations,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("watchlist_research_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/research-thesis-expiration", response_model=RecommendationFactoryResponse)
def generate_research_thesis_expiration_recommendation_candidates(
    request: ResearchThesisExpirationRecommendationGenerateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        plan_id = resolve_plan_id_or_active(request.plan_id, workspace=services.plan_workspace)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    lookup = build_research_dossier_lookup_payload(
        plan_id=plan_id,
        limit=request.limit,
        include_content=True,
        workspace=services.plan_workspace,
    )
    dossier_items = lookup.get("items") if isinstance(lookup.get("items"), list) else []
    fit_assessments_by_symbol: dict[str, dict[str, Any]] = {}
    dossier_symbols: list[str] = []
    for item in dossier_items:
        if not isinstance(item, dict):
            continue
        symbols = item.get("symbols") if isinstance(item.get("symbols"), list) else []
        for raw_symbol in symbols:
            symbol = str(raw_symbol or "").strip().upper()
            if symbol and symbol not in dossier_symbols and len(dossier_symbols) < request.limit:
                dossier_symbols.append(symbol)
    for symbol in dossier_symbols:
        try:
            try:
                fit_assessments_by_symbol[symbol] = build_portfolio_fit_assessment_payload(
                    PortfolioFitAssessmentRequest(symbol=symbol),
                    services=services,
                ).model_dump(mode="json")
            except TypeError:
                fit_assessments_by_symbol[symbol] = build_portfolio_fit_assessment_payload(
                    PortfolioFitAssessmentRequest(symbol=symbol)
                ).model_dump(mode="json")
        except Exception as exc:
            fit_assessments_by_symbol[symbol] = {
                "symbol": symbol,
                "fit_status": "needs_more_context",
                "fit_score": 0.0,
                "fit_reasons": [],
                "fit_risks": [f"Portfolio-fit assessment unavailable: {exc}"],
                "blocking_gaps": ["portfolio_fit"],
                "recommended_next_step": "research_more",
            }
    existing_recommendations = services.recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_research_thesis_expiration_recommendations(
        dossier_artifacts=dossier_items,
        existing_recommendations=existing_recommendations,
        fit_assessments_by_symbol=fit_assessments_by_symbol,
        creator=services.recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=plan_id,
        limit=request.limit,
        stale_after_days=request.stale_after_days,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("research_thesis_expiration_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/run-all", response_model=RecommendationFactoryRunAllResponse)
def run_all_recommendation_factories(
    request: RecommendationFactoryRunAllRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationFactoryRunAllResponse:
    services = workspace_services_or_legacy(services)
    if http_request is not None:
        require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    factories: dict[str, RecommendationFactoryResponse] = {}
    errors: list[dict[str, Any]] = []

    try:
        factories["portfolio_risk"] = generate_portfolio_risk_recommendation_candidates(
            PortfolioRiskRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "portfolio_risk", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "portfolio_risk", "reason": str(exc)})

    try:
        factories["plan_tracking"] = generate_plan_tracking_recommendation_candidates(
            PlanTrackingRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "plan_tracking", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "plan_tracking", "reason": str(exc)})

    try:
        factories["cash_liquidity"] = generate_cash_liquidity_recommendation_candidates(
            CashLiquidityRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "cash_liquidity", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "cash_liquidity", "reason": str(exc)})

    try:
        factories["profile_completeness"] = generate_profile_completeness_recommendation_candidates(
            ProfileCompletenessRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "profile_completeness", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "profile_completeness", "reason": str(exc)})

    try:
        factories["stale_assumptions"] = generate_stale_assumption_recommendation_candidates(
            StaleAssumptionRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "stale_assumptions", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "stale_assumptions", "reason": str(exc)})

    try:
        factories["allocation_drift"] = generate_allocation_drift_recommendation_candidates(
            AllocationDriftRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "allocation_drift", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "allocation_drift", "reason": str(exc)})

    try:
        factories["fund_overlap"] = generate_fund_overlap_recommendation_candidates(
            FundOverlapRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "fund_overlap", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "fund_overlap", "reason": str(exc)})

    try:
        factories["due_outcome_review"] = generate_due_outcome_review_recommendation_candidates(
            DueOutcomeReviewRecommendationGenerateRequest(
                dry_run=request.dry_run,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "due_outcome_review", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "due_outcome_review", "reason": str(exc)})

    try:
        factories["watchlist_research"] = generate_watchlist_research_recommendation_candidates(
            WatchlistResearchRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "watchlist_research", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "watchlist_research", "reason": str(exc)})

    try:
        factories["research_thesis_expiration"] = generate_research_thesis_expiration_recommendation_candidates(
            ResearchThesisExpirationRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            ),
            http_request=http_request,
            services=services,
        )
    except HTTPException as exc:
        errors.append({"factory": "research_thesis_expiration", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "research_thesis_expiration", "reason": str(exc)})

    generated_count = sum(factory.generated_count for factory in factories.values())
    skipped_count = sum(factory.skipped_count for factory in factories.values())
    refreshed_count = sum(factory.refreshed_count for factory in factories.values())
    if not request.dry_run and (generated_count or refreshed_count):
        _queue_autogit_event("recommendation_factories_generated")

    return RecommendationFactoryRunAllResponse(
        generated_count=generated_count,
        skipped_count=skipped_count,
        refreshed_count=refreshed_count,
        factory_count=len(factories),
        factories=factories,
        errors=errors,
        dry_run=request.dry_run,
    )


@app.post("/api/recommendations", response_model=RecommendationItem)
def create_recommendation(
    request: RecommendationCreateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationItem:
    resolved_services = route_workspace_services(
        services,
        permission="recommendations.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        prepared_payload = _prepare_recommendation_action_payload(
            source=request.source,
            action_payload=request.action_payload,
            plan_id=request.plan_id,
        )
        recommendation = resolved_services.recommendation_inbox.create(
            title=request.title,
            detail=request.detail,
            priority=request.priority,
            recommendation_type=request.recommendation_type,
            source=request.source,
            plan_id=request.plan_id,
            action_payload=prepared_payload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("recommendation_created")
    return _recommendation_item_from_row(recommendation)


@app.get("/api/recommendations/{recommendation_id}", response_model=RecommendationItem)
def get_recommendation(
    recommendation_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationItem:
    require_permission(services.context, "recommendations.read")
    try:
        recommendation = services.recommendation_inbox.get(recommendation_id)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _recommendation_item_from_row(recommendation)


@app.put("/api/recommendations/{recommendation_id}", response_model=RecommendationItem)
def update_recommendation(
    recommendation_id: str,
    request: RecommendationUpdateRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationItem:
    require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")

    try:
        recommendation = services.recommendation_inbox.update(recommendation_id, updates=updates)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _queue_autogit_event("recommendation_updated")
    return _recommendation_item_from_row(recommendation)


@app.post("/api/recommendations/{recommendation_id}/preview", response_model=RecommendationPreviewResponse)
async def preview_recommendation_route(
    recommendation_id: str,
    request: RecommendationPreviewRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationPreviewResponse:
    require_csrf(http_request)
    require_permission(services.context, "recommendations.read")
    try:
        return await preview_recommendation(recommendation_id, request, services=services)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recommendations/{recommendation_id}/apply", response_model=RecommendationActionResponse)
async def apply_recommendation_route(
    recommendation_id: str,
    request: RecommendationApplyRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationActionResponse:
    require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        response = await apply_recommendation_with_decision_packet(recommendation_id, request, services=services)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("recommendation_applied")
    return response


@app.post("/api/recommendations/{recommendation_id}/reject", response_model=RecommendationActionResponse)
async def reject_recommendation_route(
    recommendation_id: str,
    request: RecommendationRejectRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationActionResponse:
    require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        response = await reject_recommendation(
            recommendation_id,
            plan_id=request.plan_id,
            reason=request.reason,
            capture_scenario_diff=request.capture_scenario_diff,
            create_decision_packet=request.create_decision_packet,
            decision_packet_research_symbols=request.decision_packet_research_symbols,
            services=services,
        )
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("recommendation_rejected")
    return response


@app.post("/api/recommendations/{recommendation_id}/outcome", response_model=RecommendationActionResponse)
def update_recommendation_outcome_route(
    recommendation_id: str,
    request: RecommendationOutcomeUpdateRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationActionResponse:
    require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        response = update_recommendation_outcome(recommendation_id, request, services=services)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("recommendation_outcome_updated")
    return response


@app.get(
    "/api/recommendations/{recommendation_id}/outcome/prefill",
    response_model=RecommendationOutcomePrefillResponse,
)
def get_recommendation_outcome_prefill(
    recommendation_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationOutcomePrefillResponse:
    require_permission(services.context, "recommendations.read")
    try:
        return build_recommendation_outcome_prefill_payload(recommendation_id, services=services)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/recommendations/{recommendation_id}/archive", response_model=RecommendationActionResponse)
def archive_recommendation_route(
    recommendation_id: str,
    request: RecommendationRejectRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RecommendationActionResponse:
    require_csrf(http_request)
    require_permission(services.context, "recommendations.write")
    try:
        response = archive_recommendation(recommendation_id, note=request.reason, services=services)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("recommendation_archived")
    return response


@app.get("/api/sync/status", response_model=SyncStatusResponse)
def sync_status() -> SyncStatusResponse:
    return get_sync_status()


@app.get("/api/import/files")
def list_import_files(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "imports.read")
    files = []
    inbox_dir = services.paths.import_inbox_dir
    inbox_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(inbox_dir.glob("*.csv"), key=lambda item: item.name.lower()):
        stat = path.stat()
        files.append(
            {
                "name": path.name,
                "filename": path.name,
                "path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            }
        )
    return {
        "items": files,
        "files": [item["name"] for item in files],
    }


@app.get("/api/import/csv-templates")
def list_import_csv_templates() -> dict[str, list[CsvTemplateOption]]:
    templates = [CsvTemplateOption(**item) for item in list_csv_templates()]
    return {"templates": templates}


@app.get("/api/plans", response_model=list[PlanSummary])
def list_plans(
    limit: int = 100,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> list[PlanSummary]:
    resolved_services = route_workspace_services(services, permission="plan.read")
    summaries = resolved_services.plan_workspace.list_plans(limit=max(1, min(limit, 500)))
    return [PlanSummary(**summary) for summary in summaries]


@app.post("/api/plans", response_model=PlanDetailResponse)
def create_plan(
    request: PlanCreateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanDetailResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        detail = resolved_services.plan_workspace.create_plan(title=request.title, description=request.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_created")
    return _build_plan_detail_response(detail)


@app.get("/api/plans/{plan_id}", response_model=PlanDetailResponse)
def get_plan(
    plan_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanDetailResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_plan_detail_response(detail)


@app.put("/api/plans/{plan_id}", response_model=PlanDetailResponse)
def update_plan(
    plan_id: str,
    request: PlanUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanDetailResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        detail = resolved_services.plan_workspace.update_plan_files(
            plan_id=plan_id,
            plan_markdown=request.plan_markdown,
            tasks_markdown=request.tasks_markdown,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_updated")
    return _build_plan_detail_response(detail)


@app.patch("/api/plans/{plan_id}/settings", response_model=PlanDetailResponse)
def update_plan_settings(
    plan_id: str,
    request: PlanSettingsUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanDetailResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one settings field to update")

    try:
        detail = resolved_services.plan_workspace.update_plan_settings(
            plan_id=plan_id,
            updates=updates,
            rationale="Updated via Plan Workspace settings.",
            status="accepted",
            log_decision=True,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_settings_updated")
    return _build_plan_detail_response(detail)


@app.get("/api/plans/{plan_id}/timeline", response_model=PlanTimelineResponse)
def get_plan_timeline(
    plan_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanTimelineResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        timeline = resolved_services.plan_workspace.get_plan_timeline(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanTimelineResponse(**timeline)


@app.put("/api/plans/{plan_id}/timeline", response_model=PlanTimelineResponse)
def update_plan_timeline(
    plan_id: str,
    request: PlanTimelineUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanTimelineResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        timeline = resolved_services.plan_workspace.update_plan_timeline(
            plan_id=plan_id,
            timeline_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace timeline editor.",
            status="accepted",
            log_decision=True,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_timeline_updated")
    return PlanTimelineResponse(**timeline)


@app.get("/api/plans/{plan_id}/contribution-rules", response_model=PlanContributionRulesResponse)
def get_plan_contribution_rules(
    plan_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanContributionRulesResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_plan_contribution_rules(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_contribution_rules_updated")
    return PlanContributionRulesResponse(**payload)


@app.put("/api/plans/{plan_id}/contribution-rules", response_model=PlanContributionRulesResponse)
def update_plan_contribution_rules(
    plan_id: str,
    request: PlanContributionRulesUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanContributionRulesResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        payload = resolved_services.plan_workspace.update_plan_contribution_rules(
            plan_id=plan_id,
            contribution_rules_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace contribution rules editor.",
            status="accepted",
            log_decision=True,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlanContributionRulesResponse(**payload)


@app.get("/api/plans/{plan_id}/assumption-sets", response_model=PlanAssumptionSetsResponse)
def get_plan_assumption_sets(
    plan_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanAssumptionSetsResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_plan_assumption_sets(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_assumption_sets_updated")
    return PlanAssumptionSetsResponse(**payload)


@app.put("/api/plans/{plan_id}/assumption-sets", response_model=PlanAssumptionSetsResponse)
def update_plan_assumption_sets(
    plan_id: str,
    request: PlanAssumptionSetsUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanAssumptionSetsResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        payload = resolved_services.plan_workspace.update_plan_assumption_sets(
            plan_id=plan_id,
            assumption_sets_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace assumption sets editor.",
            status="accepted",
            log_decision=True,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlanAssumptionSetsResponse(**payload)


@app.get("/api/plans/{plan_id}/branch-templates", response_model=PlanScenarioBranchTemplatesResponse)
def get_plan_branch_templates(
    plan_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanScenarioBranchTemplatesResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_plan_branch_templates(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_branch_templates_updated")
    return PlanScenarioBranchTemplatesResponse(**payload)


@app.put("/api/plans/{plan_id}/branch-templates", response_model=PlanScenarioBranchTemplatesResponse)
def update_plan_branch_templates(
    plan_id: str,
    request: PlanScenarioBranchTemplatesUpdateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanScenarioBranchTemplatesResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        payload = resolved_services.plan_workspace.update_plan_branch_templates(
            plan_id=plan_id,
            branch_templates_payload=request.model_dump(mode="json"),
            rationale="Updated via Plan Workspace branch templates editor.",
            status="accepted",
            log_decision=True,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PlanScenarioBranchTemplatesResponse(**payload)


@app.post("/api/plans/{plan_id}/simulation-explain", response_model=PlanSimulationExplainResponse)
def explain_plan_simulation_result(
    plan_id: str,
    request: PlanSimulationExplainRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSimulationExplainResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        resolved_services.plan_workspace.get_plan(plan_id)
        payload = explain_plan_simulation(
            plan_id=plan_id,
            source=request.source,
            input_payload=request.input_payload,
            result_payload=request.result_payload,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanSimulationExplainResponse(**payload)


@app.post("/api/plans/{plan_id}/what-if-review-level", response_model=PlanWhatIfReviewLevelResponse)
def classify_plan_what_if_review_level(
    plan_id: str,
    request: PlanWhatIfReviewLevelRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanWhatIfReviewLevelResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        resolved_services.plan_workspace.get_plan(plan_id)
        payload = classify_plan_lever_impact(
            plan_id=plan_id,
            source=request.source,
            input_payload=request.input_payload,
            result_payload=request.result_payload,
            explanation_payload=request.explanation_payload,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanWhatIfReviewLevelResponse(**payload)


@app.get("/api/plans/{plan_id}/simulations/saved", response_model=PlanSavedSimulationsResponse)
def list_plan_saved_simulations(
    plan_id: str,
    limit: int = 50,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSavedSimulationsResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.list_saved_simulations(plan_id=plan_id, limit=limit)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanSavedSimulationsResponse(**payload)


@app.post("/api/plans/{plan_id}/simulations/saved", response_model=PlanSavedSimulation)
def create_plan_saved_simulation(
    plan_id: str,
    request: PlanSavedSimulationCreateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSavedSimulation:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        payload = resolved_services.plan_workspace.save_simulation(
            plan_id=plan_id,
            simulation_payload=request.model_dump(mode="json"),
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_saved_simulation_created")
    return PlanSavedSimulation(**payload)


@app.get("/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}", response_model=PlanSavedSimulation)
def get_plan_saved_simulation(
    plan_id: str,
    saved_simulation_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSavedSimulation:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        payload = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanSavedSimulation(**payload)


@app.get(
    "/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/compare-current",
    response_model=PlanSavedSimulationCompareResponse,
)
def compare_plan_saved_simulation_to_current(
    plan_id: str,
    saved_simulation_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSavedSimulationCompareResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
        simulation = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
        settings_payload = detail.get("settings")
        current_settings = settings_payload if isinstance(settings_payload, dict) else {}
        payload = compare_saved_simulation_to_current_plan(
            plan_id=plan_id,
            saved_simulation=simulation,
            current_settings=current_settings,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanSavedSimulationCompareResponse(**payload)


@app.post(
    "/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/rerun",
    response_model=PlanSavedSimulationRerunResponse,
)
async def rerun_plan_saved_simulation(
    plan_id: str,
    saved_simulation_id: str,
    request: PlanSavedSimulationRerunRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSavedSimulationRerunResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write" if request.save_result else "plan.read",
        http_request=http_request,
        require_write_token=request.save_result,
    )
    try:
        simulation = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
        source = str(simulation.get("source") or "").strip().lower()
        input_payload = simulation.get("input_payload") if isinstance(simulation.get("input_payload"), dict) else {}

        if source == "scenario_diff":
            result_model = await run_plan_scenario_diff(
                plan_id,
                PlanScenarioDiffRequest(**input_payload),
                services=resolved_services,
            )
            result_payload = result_model.model_dump(mode="json")
            explanation = explain_plan_simulation(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
            )
            review_level = classify_plan_lever_impact(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
                explanation_payload=explanation,
            )
        elif source == "scenario_branch":
            result_model = await run_plan_scenario_branch(
                plan_id,
                PlanScenarioBranchRequest(**input_payload),
                services=resolved_services,
            )
            result_payload = result_model.model_dump(mode="json")
            explanation = explain_plan_simulation(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
            )
            review_level = classify_plan_lever_impact(
                plan_id=plan_id,
                source=source,
                input_payload=input_payload,
                result_payload=result_payload,
                explanation_payload=explanation,
            )
        elif source == "withdrawal_strategy":
            result_model = await compare_plan_withdrawal_strategies(
                plan_id,
                PlanWithdrawalStrategyCompareRequest(**input_payload),
                services=resolved_services,
            )
            result_payload = result_model.model_dump(mode="json")
            explanation = result_payload.get("explanation") if isinstance(result_payload.get("explanation"), dict) else {}
            review_level = {}
        else:
            raise ValueError("Only simulation, what-if, and strategy comparison Saved Simulations can be rerun.")

        saved_payload = None
        if request.save_result:
            summary = str(explanation.get("summary") or "").strip() if isinstance(explanation, dict) else ""
            saved_payload = resolved_services.plan_workspace.save_simulation(
                plan_id=plan_id,
                simulation_payload={
                    "title": str(request.title or "").strip() or f"Rerun: {simulation.get('title') or saved_simulation_id}",
                    "source": source,
                    "summary": summary,
                    "notes": request.notes,
                    "input_payload": input_payload,
                    "result_payload": result_payload,
                },
            )
            _queue_autogit_event("plan_saved_simulation_rerun_saved")
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlanSavedSimulationRerunResponse(
        plan_id=plan_id,
        saved_simulation_id=saved_simulation_id,
        source=source,
        input_payload=input_payload,
        result_payload=result_payload,
        explanation=explanation if isinstance(explanation, dict) else {},
        review_level=review_level if isinstance(review_level, dict) else {},
        saved_simulation=PlanSavedSimulation(**saved_payload) if isinstance(saved_payload, dict) else None,
    )


@app.post(
    "/api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/decision",
    response_model=PlanSavedSimulationDecisionResponse,
)
def create_plan_saved_simulation_decision(
    plan_id: str,
    saved_simulation_id: str,
    request: PlanSavedSimulationDecisionRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSavedSimulationDecisionResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        simulation = resolved_services.plan_workspace.get_saved_simulation(
            plan_id=plan_id,
            saved_simulation_id=saved_simulation_id,
        )
        summary = (
            str(request.summary or "").strip()
            or f"Reviewed saved simulation: {simulation.get('title') or saved_simulation_id}"
        )
        rationale = (
            str(request.rationale or "").strip()
            or str(simulation.get("summary") or "").strip()
            or "Saved simulation reviewed before changing the active plan."
        )
        decision = resolved_services.plan_workspace.append_decision(
            plan_id=plan_id,
            summary=summary,
            rationale=f"{rationale} Saved simulation id: {saved_simulation_id}.",
            status=request.status,
            action_payload={
                "plan_id": plan_id,
                "saved_simulation_id": saved_simulation_id,
                "saved_simulation_title": simulation.get("title"),
                "source": "saved_simulation_decision",
            },
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_saved_simulation_decision_added")
    return PlanSavedSimulationDecisionResponse(
        plan_id=plan_id,
        saved_simulation_id=saved_simulation_id,
        simulation=PlanSavedSimulation(**simulation),
        decision=decision,
    )


def pin_watchlist_research_bridge(
    plan_id: str,
    request: PlanResearchBridgeRequest,
    services: WorkspaceServices | None = None,
) -> PlanResearchBridgeResponse:
    resolved_services = workspace_services_or_legacy(services)
    branch_templates_payload = resolved_services.plan_workspace.get_plan_branch_templates(plan_id)

    selected_items = select_research_bridge_watchlist_items(
        watchlist_items=resolved_services.portfolio_store.list_watchlist(),
        requested_symbols=request.symbols,
        max_symbols=request.max_symbols,
    )

    requested_symbols = normalize_research_symbols(request.symbols, max_symbols=20)
    if requested_symbols and not selected_items:
        raise ValueError(
            "None of the requested symbols are present in the watchlist. "
            "Add them to watchlist first or omit symbols to pin current watchlist entries."
        )
    if not selected_items:
        raise ValueError(
            "Watchlist is empty. Add watchlist items before pinning research into plan branch templates."
        )

    resolved_template_id = _sanitize_branch_template_id(request.branch_template_id)
    assumption_set_id = str(request.assumption_set_id or "").strip().lower() or None
    if assumption_set_id:
        assumption_sets_payload = resolved_services.plan_workspace.get_plan_assumption_sets(plan_id)
        valid_assumption_set_ids = {
            str(item.get("id") or "").strip().lower()
            for item in assumption_sets_payload.get("sets", [])
            if isinstance(item, dict)
        }
        if assumption_set_id not in valid_assumption_set_ids:
            raise ValueError(
                f"Unknown assumption_set_id '{assumption_set_id}'. "
                f"Valid IDs: {', '.join(sorted(valid_assumption_set_ids)) or 'none'}."
            )

    templates_raw = branch_templates_payload.get("templates")
    templates = [item for item in templates_raw if isinstance(item, dict)] if isinstance(templates_raw, list) else []

    existing_index = None
    existing_template: dict[str, Any] = {}
    for index, item in enumerate(templates):
        candidate_id = _sanitize_branch_template_id(item.get("id"), fallback="")
        if candidate_id == resolved_template_id:
            existing_index = index
            existing_template = item
            break

    existing_events_raw = existing_template.get("branch_events")
    existing_events = [event for event in existing_events_raw if isinstance(event, dict)] if isinstance(existing_events_raw, list) else []
    retained_events = [event for event in existing_events if not _is_research_bridge_event(event)]
    generated_events = build_research_bridge_branch_events(selected_items)

    template_name = (
        str(request.template_name or "").strip()
        or str(existing_template.get("name") or "").strip()
        or RESEARCH_BRIDGE_TEMPLATE_NAME
    )
    branch_name = (
        str(request.branch_name or "").strip()
        or str(existing_template.get("branch_name") or "").strip()
        or "Research Thesis Branch"
    )
    description_prefix = (
        str(existing_template.get("description") or "").strip()
        or "Watchlist research symbols and thesis notes pinned for scenario branch analysis."
    )
    pinned_at = context_utc_now_iso()
    description = f"{description_prefix} Last pinned {len(generated_events)} symbol(s) on {pinned_at}."

    compare_settings_raw = existing_template.get("compare_settings")
    compare_settings = compare_settings_raw if isinstance(compare_settings_raw, dict) else {}
    resolved_assumption_set_id = (
        assumption_set_id
        or str(existing_template.get("assumption_set_id") or "").strip().lower()
        or None
    )

    next_template = {
        "id": resolved_template_id,
        "name": template_name,
        "description": description,
        "branch_name": branch_name,
        "assumption_set_id": resolved_assumption_set_id,
        "compare_settings": compare_settings,
        "branch_events": [*retained_events, *generated_events],
    }

    if existing_index is None:
        templates.append(next_template)
    else:
        templates[existing_index] = next_template

    default_template_id = str(branch_templates_payload.get("default_template_id") or "").strip().lower() or None
    if not default_template_id:
        default_template_id = resolved_template_id
    update_payload = {
        "default_template_id": default_template_id,
        "templates": templates,
    }

    updated_templates_payload = resolved_services.plan_workspace.update_plan_branch_templates(
        plan_id=plan_id,
        branch_templates_payload=update_payload,
        rationale=(
            "Pinned watchlist research symbols/thesis notes into scenario branch templates "
            "(research-to-planning bridge)."
        ),
        status="accepted",
        log_decision=False,
    )

    updated_templates = updated_templates_payload.get("templates")
    if isinstance(updated_templates, list):
        for item in updated_templates:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("id") or "").strip().lower()
            if candidate_id == resolved_template_id:
                template_name = str(item.get("name") or template_name).strip() or template_name
                break

    pinned_items = [PlanResearchBridgePinnedItem(**item) for item in selected_items]
    pinned_symbols = [item.symbol for item in pinned_items]
    symbol_preview = ", ".join(pinned_symbols[:5]) + ("..." if len(pinned_symbols) > 5 else "")
    decision_summary = f"Pinned research bridge symbols: {symbol_preview} -> {resolved_template_id}"
    decision_rationale = (
        f"Pinned {len(pinned_symbols)} watchlist symbol(s) into branch template "
        f"{resolved_template_id} ({template_name})"
        f"{f' using assumption set {resolved_assumption_set_id}' if resolved_assumption_set_id else ''}."
    )
    resolved_services.plan_workspace.append_decision(
        plan_id=plan_id,
        summary=decision_summary,
        rationale=decision_rationale,
        status="accepted",
    )
    artifact_title = f"Research Bridge Pin - {template_name}"
    artifact_payload = resolved_services.plan_workspace.write_artifact(
        plan_id=plan_id,
        title=artifact_title,
        markdown=_build_research_bridge_pin_markdown(
            plan_id=plan_id,
            template_id=resolved_template_id,
            template_name=template_name,
            branch_name=branch_name,
            assumption_set_id=resolved_assumption_set_id,
            requested_symbols=requested_symbols,
            pinned_items=pinned_items,
            retained_event_count=len(retained_events),
            generated_event_count=len(generated_events),
            pinned_at=pinned_at,
        ),
        kind="research_bridge",
    )
    return PlanResearchBridgeResponse(
        plan_id=plan_id,
        template_id=resolved_template_id,
        template_name=template_name,
        pinned_symbols=pinned_symbols,
        pinned_items=pinned_items,
        decision_summary=decision_summary,
        artifact_id=str(artifact_payload.get("id") or "") or None,
        artifact_title=str(artifact_payload.get("title") or artifact_title),
        pinned_at=pinned_at,
        branch_templates=PlanScenarioBranchTemplatesResponse(**updated_templates_payload),
    )


@app.post("/api/plans/{plan_id}/branch-templates/pin-watchlist", response_model=PlanResearchBridgeResponse)
def pin_watchlist_research_to_plan_branch_template(
    plan_id: str,
    request: PlanResearchBridgeRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanResearchBridgeResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        return pin_watchlist_research_bridge(plan_id=plan_id, request=request, services=resolved_services)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/plans/{plan_id}/scenario-diff", response_model=PlanScenarioDiffResponse)
async def run_plan_scenario_diff(
    plan_id: str,
    request: PlanScenarioDiffRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanScenarioDiffResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    compare_updates = request.compare_settings.model_dump(exclude_unset=True)

    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    timeline_payload = resolve_plan_timeline_payload(detail)
    retirement_age = resolve_timeline_retirement_age(timeline_payload)
    timeline_withdrawal_strategy = resolve_timeline_withdrawal_strategy(timeline_payload)
    timeline_drawdown_order = resolve_timeline_drawdown_order(timeline_payload)
    assumption_sets_payload = resolve_plan_assumption_sets(detail)
    requested_assumption_set_id = str(request.assumption_set_id or "").strip() or None
    requested_candidate_assumption_set_id = str(request.candidate_assumption_set_id or "").strip() or None
    base_settings_raw = detail.get("settings", {})
    if not isinstance(base_settings_raw, dict):
        base_settings_raw = {}
    base_settings, base_assumption_set = apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=requested_assumption_set_id,
    )
    candidate_set_id = requested_candidate_assumption_set_id or requested_assumption_set_id
    candidate_base_settings, candidate_assumption_set = apply_assumption_set_to_settings(
        plan_settings=base_settings_raw,
        assumption_sets_payload=assumption_sets_payload,
        assumption_set_id=candidate_set_id,
    )
    candidate_settings = merge_plan_settings(candidate_base_settings, compare_updates)
    base_income_projection = build_income_projection_for_plan_settings(base_settings)
    candidate_income_projection = build_income_projection_for_plan_settings(candidate_settings)
    base_expense_projection = build_expense_projection_for_plan_settings(base_settings)
    candidate_expense_projection = build_expense_projection_for_plan_settings(candidate_settings)
    base_debt_projection = build_debt_projection_for_plan_settings(base_settings)
    candidate_debt_projection = build_debt_projection_for_plan_settings(candidate_settings)
    base_timeline_projection = build_timeline_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
    )
    candidate_timeline_projection = build_timeline_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
    )
    contribution_rules_payload = resolve_plan_contribution_rules(detail)
    base_contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings=base_settings,
        contribution_rules_payload=contribution_rules_payload,
    )
    candidate_contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings=candidate_settings,
        contribution_rules_payload=contribution_rules_payload,
    )
    base_social_security_projection = build_social_security_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        income_projection=base_income_projection,
        start_year=utc_now().year,
    )
    candidate_social_security_projection = build_social_security_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
        income_projection=candidate_income_projection,
        start_year=utc_now().year,
    )
    base_rmd_projection = build_rmd_projection_for_plan_settings(
        plan_settings=base_settings,
        timeline_payload=timeline_payload,
        start_year=utc_now().year,
    )
    candidate_rmd_projection = build_rmd_projection_for_plan_settings(
        plan_settings=candidate_settings,
        timeline_payload=timeline_payload,
        start_year=utc_now().year,
    )

    try:
        current_value = resolve_portfolio_value(
            request.current_portfolio_value_usd,
            store=resolved_services.snapshot_store,
        )
        base_result = await run_scenarios_for_plan_settings(
            current_portfolio_value_usd=current_value,
            plan_settings=base_settings,
            income_projection=base_income_projection,
            expense_projection=base_expense_projection,
            debt_projection=base_debt_projection,
            timeline_projection=base_timeline_projection,
            contribution_allocation=base_contribution_allocation,
            social_security_projection=base_social_security_projection,
            rmd_projection=base_rmd_projection,
            assumption_set=base_assumption_set,
            retirement_age=retirement_age,
            timeline_withdrawal_strategy=timeline_withdrawal_strategy,
            timeline_drawdown_order=timeline_drawdown_order,
        )
        candidate_result = await run_scenarios_for_plan_settings(
            current_portfolio_value_usd=current_value,
            plan_settings=candidate_settings,
            income_projection=candidate_income_projection,
            expense_projection=candidate_expense_projection,
            debt_projection=candidate_debt_projection,
            timeline_projection=candidate_timeline_projection,
            contribution_allocation=candidate_contribution_allocation,
            social_security_projection=candidate_social_security_projection,
            rmd_projection=candidate_rmd_projection,
            assumption_set=candidate_assumption_set,
            retirement_age=retirement_age,
            timeline_withdrawal_strategy=timeline_withdrawal_strategy,
            timeline_drawdown_order=timeline_drawdown_order,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scenario_deltas, monte_carlo_delta, simulation_delta = build_scenario_diff_payload(
        base_result,
        candidate_result,
    )

    return PlanScenarioDiffResponse(
        plan_id=plan_id,
        current_portfolio_value_usd=current_value,
        base_settings=PlanSettings(**base_settings),
        candidate_settings=PlanSettings(**candidate_settings),
        base_assumption_set=base_assumption_set,
        candidate_assumption_set=candidate_assumption_set,
        base_result=base_result,
        candidate_result=candidate_result,
        scenario_deltas=[ScenarioComparisonRow(**item) for item in scenario_deltas],
        monte_carlo_delta=monte_carlo_delta,
        simulation_delta=simulation_delta,
    )


@app.post(
    "/api/plans/{plan_id}/withdrawal-strategy-compare",
    response_model=PlanWithdrawalStrategyCompareResponse,
)
async def compare_plan_withdrawal_strategies(
    plan_id: str,
    request: PlanWithdrawalStrategyCompareRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanWithdrawalStrategyCompareResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    arguments: dict[str, Any] = {
        "plan_id": plan_id,
        "current_portfolio_value_usd": request.current_portfolio_value_usd,
        "assumption_set_id": request.assumption_set_id,
        "strategies": request.strategies,
        "include_raw_results": request.include_raw_results,
    }
    try:
        token = current_copilot_workspace_services.set(resolved_services)
        try:
            payload = await tool_compare_withdrawal_strategies(arguments)
        finally:
            current_copilot_workspace_services.reset(token)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Withdrawal strategy comparison failed: {exc}",
        ) from exc
    return PlanWithdrawalStrategyCompareResponse(**payload)


@app.post("/api/plans/{plan_id}/scenario-branch", response_model=PlanScenarioBranchResponse)
async def run_plan_scenario_branch(
    plan_id: str,
    request: PlanScenarioBranchRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanScenarioBranchResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    compare_updates = request.compare_settings.model_dump(exclude_unset=True)
    raw_branch_events = [item.model_dump(mode="json") for item in request.branch_events]

    try:
        payload = await compute_plan_scenario_branch(
            plan_id=plan_id,
            branch_name=str(request.branch_name or "").strip() or "What-If Branch",
            current_portfolio_value_usd=request.current_portfolio_value_usd,
            assumption_set_id=str(request.assumption_set_id or "").strip() or None,
            branch_template_id=str(request.branch_template_id or "").strip() or None,
            compare_updates=compare_updates,
            raw_branch_events=raw_branch_events,
            services=resolved_services,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlanScenarioBranchResponse(**payload)


@app.get("/api/plans/{plan_id}/tracking", response_model=PlanTrackingResponse)
def get_plan_tracking(
    plan_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanTrackingResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = resolved_services.snapshot_store.recent(limit=90)
    transactions = resolved_services.portfolio_store.list_transactions(limit=10_000)

    planner_defaults = {
        "annual_contribution_usd": settings.planner_annual_contribution_usd,
        "expected_return_baseline": settings.planner_expected_return_baseline,
        "hsa_extra_contribution_usd": settings.planner_hsa_delta_default,
    }

    return compute_plan_tracking(
        plan_id=plan_id,
        plan_title=detail.get("title", ""),
        plan_settings=plan_settings,
        planner_defaults=planner_defaults,
        snapshots=snapshots,
        transactions=transactions,
    )


@app.post("/api/plans/{plan_id}/activate", response_model=PlanSummary)
def activate_plan(
    plan_id: str,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanSummary:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        summary = resolved_services.plan_workspace.set_active_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _queue_autogit_event("plan_activated")
    return PlanSummary(**summary)


@app.post(
    "/api/plans/{plan_id}/recommendation-closure-summary",
    response_model=PlanRecommendationClosureSummaryResponse,
)
def create_plan_recommendation_closure_summary_route(
    plan_id: str,
    request: PlanRecommendationClosureSummaryRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanRecommendationClosureSummaryResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write" if request.write_artifact else "plan.read",
        http_request=http_request,
        require_write_token=request.write_artifact,
    )
    try:
        response = create_plan_recommendation_closure_summary(
            plan_id=plan_id,
            request=request,
            services=resolved_services,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_recommendation_closure_summary_created")
    return response


@app.post("/api/plans/{plan_id}/decisions", response_model=PlanDetailResponse)
def append_plan_decision(
    plan_id: str,
    request: PlanDecisionCreateRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanDetailResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        resolved_services.plan_workspace.append_decision(
            plan_id=plan_id,
            summary=request.summary,
            rationale=request.rationale,
            status=request.status,
            action_payload=request.action_payload,
        )
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_decision_added")
    return _build_plan_detail_response(detail)


@app.post("/api/plans/{plan_id}/refresh-context", response_model=PlanDetailResponse)
def refresh_plan_context(
    plan_id: str,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanDetailResponse:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    try:
        resolved_services.plan_workspace.refresh_context(plan_id)
        detail = resolved_services.plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _queue_autogit_event("plan_context_refreshed")
    return _build_plan_detail_response(detail)


@app.get("/api/plans/{plan_id}/artifacts/{artifact_id}", response_model=PlanArtifactResponse)
def read_plan_artifact(
    plan_id: str,
    artifact_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanArtifactResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    try:
        artifact = resolved_services.plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if str(artifact.get("title") or "").lower().startswith("research dossier") or "-research-dossier-" in str(artifact.get("file_name") or ""):
        artifact.update(_extract_thesis_review_metadata_from_markdown(artifact.get("content")))
        artifact["thesis_review"] = research_thesis_review_metadata(artifact)
        artifact["thesis_revision_history"] = _extract_thesis_revision_history(artifact.get("content"))
    return PlanArtifactResponse(**artifact)


@app.put("/api/plans/{plan_id}/artifacts/{artifact_id}/thesis")
def save_plan_artifact_thesis_revision(
    plan_id: str,
    artifact_id: str,
    request: dict[str, Any],
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_services = route_workspace_services(
        services,
        permission="plan.write",
        http_request=http_request,
        require_write_token=True,
    )
    thesis = str(request.get("thesis") or request.get("proposed_thesis") or "").strip()
    if not thesis:
        raise HTTPException(status_code=400, detail="thesis is required")

    reference_raw = (
        request.get("reference_price_usd")
        if request.get("reference_price_usd") is not None
        else request.get("thesis_reference_price_usd")
    )
    reference_value = _coerce_optional_float(reference_raw)
    if reference_raw not in (None, "", "null") and reference_value is None:
        raise HTTPException(status_code=400, detail="reference_price_usd must be a number")
    if reference_value is not None and reference_value <= 0:
        raise HTTPException(status_code=400, detail="reference_price_usd must be greater than 0")

    try:
        review_window_days = max(1, min(int(request.get("review_window_days") or TODAY_THESIS_REVIEW_DAYS), 3650))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="review_window_days must be an integer") from exc

    reviewed_at_dt = utc_now()
    reviewed_at = reviewed_at_dt.isoformat()
    expires_at = str(request.get("expires_at") or "").strip() or (reviewed_at_dt + timedelta(days=review_window_days)).isoformat()

    try:
        artifact = resolved_services.plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
        previous_thesis = _extract_markdown_section(artifact.get("content"), "Thesis")
        revision_event = _compact_thesis_revision_event(
            target_type="dossier",
            plan_id=plan_id,
            artifact_id=artifact_id,
            previous_thesis=previous_thesis,
            revised_thesis=thesis,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
            review_window_days=review_window_days,
            request=request,
        )
        updated = _replace_markdown_section(str(artifact.get("content") or ""), "Thesis", thesis)
        updated = _replace_thesis_revision_notes_section(updated, str(request.get("rationale") or ""))
        updated = _replace_thesis_review_metadata_section(
            updated,
            reviewed_at=reviewed_at,
            expires_at=expires_at,
            reference_price_usd=reference_value,
        )
        updated = _replace_thesis_revision_history_section(updated, revision_event)
        saved = resolved_services.plan_workspace.update_artifact_content(
            plan_id=plan_id,
            artifact_id=artifact_id,
            markdown=updated,
        )
        _link_thesis_revision_to_recommendation(
            request.get("recommendation_id"),
            revision_event,
            inbox=resolved_services.recommendation_inbox,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    history_lines = _extract_thesis_revision_history_lines(saved.get("content"))
    review = research_thesis_review_metadata(
        {
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "reference_price_usd": reference_value,
        }
    )
    return {
        "artifact": saved,
        "thesis_review": {
            "status": review.get("status") or "current",
            "target": "dossier",
            "plan_id": plan_id,
            "artifact_id": saved.get("id") or artifact_id,
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "reference_price_usd": reference_value,
            "age_days": review.get("age_days"),
        },
        "thesis_revision_history": [
            revision_event,
            *({"summary": line} for line in history_lines[1:THESIS_REVISION_HISTORY_LIMIT]),
        ],
    }


@app.get("/api/workflows/templates", response_model=list[WorkflowTemplateResponse])
def list_workflow_templates() -> list[WorkflowTemplateResponse]:
    templates = workflow_runner.templates()
    return [WorkflowTemplateResponse(**item) for item in templates]


@app.post("/api/workflows/run", response_model=WorkflowRunResponse)
async def run_workflow(
    request: WorkflowRunRequest,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> WorkflowRunResponse:
    requires_write = bool(request.save_to_plan or request.create_recommendations)
    resolved_services = route_workspace_services(
        services,
        permission="plan.write" if requires_write else "portfolio.read",
        http_request=http_request,
        require_write_token=requires_write,
    )
    snapshot, previous_snapshot = await resolve_snapshots_for_workflow(
        use_live_snapshot=request.use_live_snapshot,
        services=resolved_services,
    )

    try:
        result = workflow_runner.run(
            workflow_id=request.workflow_id,
            snapshot=snapshot,
            params=request.params,
            previous_snapshot=previous_snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resolved_plan_id = request.plan_id or resolved_services.plan_workspace.get_active_plan_id()

    artifact_payload: dict[str, object] | None = None
    if request.save_to_plan:
        if resolved_plan_id:
            try:
                artifact_payload = resolved_services.plan_workspace.write_artifact(
                    plan_id=resolved_plan_id,
                    title=f"{request.workflow_id.replace('_', ' ').title()} Report",
                    markdown=result.get("report_markdown", ""),
                    kind=request.workflow_id,
                )
            except PlanNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    result["artifact"] = artifact_payload
    if request.create_recommendations:
        result["recommendations"] = create_recommendations_from_workflow_result(
            workflow_id=request.workflow_id,
            result=result,
            plan_id=resolved_plan_id,
            inbox=resolved_services.recommendation_inbox,
        )
    else:
        result["recommendations"] = []
    return WorkflowRunResponse(**result)


@app.get("/api/copilot/context", response_model=CopilotContextResponse)
async def get_copilot_context(
    use_live_snapshot: bool = False,
    plan_id: str | None = None,
    include_research: bool = True,
    include_plan_projection: bool = True,
    force_refresh: bool = False,
    research_symbols: str | None = None,
    research_period: str = "6mo",
    research_interval: str = "1d",
    research_symbol_limit: int = DEFAULT_RESEARCH_SYMBOL_LIMIT,
    max_recommendations: int = 10,
    max_plan_decisions: int = 8,
    summary_max_chars: int = DEFAULT_CONTEXT_SUMMARY_MAX_CHARS,
    detail_level: str = DEFAULT_CONTEXT_DETAIL_LEVEL,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    require_permission(services.context, "copilot.use")
    symbols_input = [
        item.strip()
        for item in str(research_symbols or "").split(",")
        if item.strip()
    ]
    return await build_buildwealth_context_payload(
        use_live_snapshot=use_live_snapshot,
        plan_id=plan_id,
        include_research=include_research,
        force_refresh=force_refresh,
        research_symbols=symbols_input,
        research_period=research_period,
        research_interval=research_interval,
        include_plan_projection=include_plan_projection,
        max_recommendations=max_recommendations,
        max_plan_decisions=max_plan_decisions,
        summary_max_chars=summary_max_chars,
        research_symbol_limit=research_symbol_limit,
        detail_level=detail_level,
        services=services,
    )


@app.get("/api/copilot/context/cache", response_model=CopilotContextCacheStatusResponse)
def get_copilot_context_cache_status() -> CopilotContextCacheStatusResponse:
    research_stats = copilot_context_research_cache.stats()
    projection_stats = copilot_context_projection_cache.stats()
    return CopilotContextCacheStatusResponse(
        as_of=utc_now(),
        enabled=bool(settings.copilot_context_cache_enabled),
        stores=[
            {
                "name": "research",
                **research_stats,
            },
            {
                "name": "baseline_projection",
                **projection_stats,
            },
        ],
    )


@app.post("/api/copilot/context/cache/reset", response_model=CopilotContextCacheStatusResponse)
def reset_copilot_context_cache(
    target: str = "all",
    reset_metrics: bool = True,
) -> CopilotContextCacheStatusResponse:
    target_value = str(target or "all").strip().lower()
    valid_targets = {"all", "research", "baseline_projection"}
    if target_value not in valid_targets:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported cache target '{target}'. Expected one of: all, research, baseline_projection.",
        )

    if target_value in {"all", "research"}:
        copilot_context_research_cache.clear(reset_metrics=reset_metrics)
    if target_value in {"all", "baseline_projection"}:
        copilot_context_projection_cache.clear(reset_metrics=reset_metrics)

    return get_copilot_context_cache_status()


@app.get("/api/copilot/conversations", response_model=list[CopilotConversationSummary])
def list_copilot_conversations(
    limit: int = 30,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> list[CopilotConversationSummary]:
    require_permission(services.context, "copilot.use")
    summaries = services.conversation_store.list(limit=max(1, min(limit, 200)))
    return [CopilotConversationSummary(**summary) for summary in summaries]


@app.get("/api/copilot/conversations/{conversation_id}", response_model=CopilotConversationResponse)
def get_copilot_conversation(
    conversation_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> CopilotConversationResponse:
    require_permission(services.context, "copilot.use")
    try:
        conversation = services.conversation_store.get(conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return CopilotConversationResponse(**conversation)


@app.post("/api/copilot/chat", response_model=CopilotChatResponse)
async def copilot_chat(
    request: CopilotChatRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> CopilotChatResponse:
    scoped_services = hasattr(services, "context")
    resolved_services = services if scoped_services else workspace_services_or_legacy(None)
    if scoped_services:
        require_permission(resolved_services.context, "copilot.use")
    context_options = request.context_options
    context_symbols = normalize_research_symbols(
        context_options.research_symbols,
        max_symbols=context_options.research_symbol_limit,
    )
    token = current_copilot_workspace_services.set(resolved_services) if scoped_services else None
    try:
        assembled_context = await assemble_copilot_context_payload(
            question=request.question,
            use_live_snapshot=request.use_live_snapshot,
            plan_id=request.plan_id,
            include_research=context_options.include_research,
            include_plan_projection=context_options.include_plan_projection,
            force_refresh=context_options.force_refresh,
            detail_level=context_options.detail_level,
            research_symbols=context_symbols,
            research_period=context_options.research_period,
            research_interval=context_options.research_interval,
            research_symbol_limit=context_options.research_symbol_limit,
            summary_max_chars=context_options.summary_max_chars,
            services=resolved_services if scoped_services else None,
        )
        contextual_brief = json.dumps(assembled_context, indent=2, default=str)
        try:
            result = await copilot.chat(
                question=request.question,
                conversation_id=request.conversation_id,
                contextual_brief=contextual_brief,
                context_trace=assembled_context.get("trace") if isinstance(assembled_context, dict) else {},
                conversation_store=resolved_services.conversation_store,
            )
            captured_candidates = resolved_services.context_intelligence_service.detect_chat_context_candidates(
                message=request.question,
                conversation_id=str(result.get("conversation_id") or "").strip() or None,
                message_index=None,
            )
            context_trace = result.get("context_trace") if isinstance(result.get("context_trace"), dict) else {}
            context_trace["captured_context_candidates"] = [
                {
                    "id": candidate.get("id"),
                    "target_domain": candidate.get("target_domain"),
                    "target_field": candidate.get("target_field"),
                    "lifecycle_state": candidate.get("lifecycle_state"),
                    "prompt_influence": candidate.get("prompt_influence"),
                    "review_item": candidate.get("review_item"),
                }
                for candidate in captured_candidates
            ]
            result["context_trace"] = context_trace
            conversation_id = str(result.get("conversation_id") or "").strip()
            if conversation_id:
                resolved_services.conversation_store.update_latest_assistant_metadata(
                    conversation_id,
                    {"context_trace": context_trace},
                )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            detail = f"LLM provider error: {exc.response.text}"
            raise HTTPException(status_code=502, detail=detail) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Copilot failed: {exc}") from exc
    finally:
        if token is not None:
            current_copilot_workspace_services.reset(token)

    return CopilotChatResponse(**result)


@app.get("/api/snapshot/live", response_model=PortfolioSnapshot)
async def get_live_snapshot(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioSnapshot:
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(services, permission="portfolio.read")
        return await build_live_snapshot(resolved_services.portfolio_store)
    return await build_live_snapshot()


@app.post("/api/snapshot/sync")
async def sync_snapshot(
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, str | dict[str, str]]:
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(
            services,
            permission="portfolio.write",
            http_request=http_request,
            require_write_token=True,
        )
        try:
            return await execute_sync(
                trigger="manual",
                store=resolved_services.portfolio_store,
                snapshots=resolved_services.snapshot_store,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc
    try:
        return await execute_sync(trigger="manual")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc


@app.get("/api/snapshot/latest", response_model=PortfolioSnapshot)
def get_latest_snapshot(
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PortfolioSnapshot:
    resolved_store = snapshot_store
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(services, permission="portfolio.read")
        resolved_store = resolved_services.snapshot_store
    try:
        return resolved_store.latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/snapshot/history", response_model=SnapshotHistoryResponse)
def get_snapshot_history(
    limit: int = 30,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> SnapshotHistoryResponse:
    resolved_store = None
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(services, permission="portfolio.read")
        resolved_store = resolved_services.snapshot_store
    return build_snapshot_history_payload(limit=max(2, min(limit, 365)), store=resolved_store)


@app.post("/api/snapshot/backfill-history")
def backfill_snapshot_history_route(
    request: dict[str, Any] | None = None,
    http_request: Request = Depends(get_current_request),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> dict[str, Any]:
    resolved_portfolio_store = portfolio_store
    resolved_snapshot_store = snapshot_store
    if hasattr(services, "context"):
        resolved_services = route_workspace_services(
            services,
            permission="portfolio.write",
            http_request=http_request,
            require_write_token=True,
        )
        resolved_portfolio_store = resolved_services.portfolio_store
        resolved_snapshot_store = resolved_services.snapshot_store
    payload = request or {}
    raw_days = payload.get("days")
    days: int | None = None
    if raw_days is not None:
        try:
            parsed_days = int(raw_days)
            if parsed_days > 0:
                days = min(parsed_days, 3650)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="days must be a positive integer")

    overwrite = bool(payload.get("overwrite", True))

    start_date_value = payload.get("start_date")
    end_date_value = payload.get("end_date")

    def _parse_optional_date(raw: Any, field: str) -> date | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text[:10]).date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD") from exc

    start_date = _parse_optional_date(start_date_value, "start_date")
    end_date = _parse_optional_date(end_date_value, "end_date")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    return backfill_snapshot_history(
        portfolio_store=resolved_portfolio_store,
        snapshot_store=resolved_snapshot_store,
        research=research_service,
        start_date=start_date,
        end_date=end_date,
        days=days,
        overwrite=overwrite,
    )


@app.post("/api/import/csv", response_model=CsvImportResponse)
async def import_csv_transactions(
    request: CsvImportRequest,
    http_request: Request,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> CsvImportResponse:
    require_csrf(http_request)
    require_permission(services.context, "imports.write")
    file_path = resolve_import_path(
        request.path,
        import_inbox_dir=services.paths.import_inbox_dir,
        workspace_root=services.paths.root,
    )
    return await execute_csv_import(file_path=file_path, request=request, services=services)


@app.post("/api/import/upload-csv", response_model=CsvImportResponse)
async def import_uploaded_csv(
    http_request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Form(True),
    delimiter: str = Form(","),
    broker_template: str = Form("auto"),
    default_data_source: str | None = Form(None),
    default_currency: str | None = Form(None),
    archive_after_success: bool = Form(False),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> CsvImportResponse:
    require_csrf(http_request)
    require_permission(services.context, "imports.write")
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    inbox_name = normalize_upload_filename(file.filename)
    destination = unique_inbox_path(inbox_name, import_inbox_dir=services.paths.import_inbox_dir)

    try:
        content = await file.read()
        destination.write_bytes(content)
    finally:
        await file.close()

    request = CsvImportRequest(
        path=str(destination),
        dry_run=dry_run,
        delimiter=delimiter,
        broker_template=broker_template,
        default_data_source=default_data_source,
        default_currency=default_currency,
        archive_after_success=archive_after_success,
    )

    return await execute_csv_import(file_path=destination, request=request, services=services)


@app.post("/api/import/workbench/preview", response_model=ImportWorkbenchPreviewResponse)
async def preview_import_workbench(
    http_request: Request,
    file: UploadFile = File(...),
    delimiter: str = Form(","),
    broker_template: str = Form("auto"),
    default_data_source: str | None = Form(None),
    default_currency: str | None = Form(None),
    services: WorkspaceServices = Depends(get_workspace_services),
) -> ImportWorkbenchPreviewResponse:
    require_csrf(http_request)
    require_permission(services.context, "imports.write")
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    inbox_name = normalize_upload_filename(file.filename)
    destination = unique_inbox_path(inbox_name, import_inbox_dir=services.paths.import_inbox_dir)

    try:
        content = await file.read()
        destination.write_bytes(content)
    finally:
        await file.close()

    request = CsvImportRequest(
        path=str(destination),
        dry_run=True,
        delimiter=delimiter,
        broker_template=broker_template,
        default_data_source=default_data_source,
        default_currency=default_currency,
        archive_after_success=False,
    )
    preview = await execute_csv_import(file_path=destination, request=request, services=services)
    session = services.import_workbench_store.create_session(
        file_path=destination,
        original_file_name=file.filename,
        options=request.model_dump(mode="json"),
        preview_response=preview,
    )
    return ImportWorkbenchPreviewResponse.model_validate(session)


def _create_import_review_items(
    report: dict[str, Any],
    *,
    inbox: RecommendationInbox | None = None,
) -> list[dict[str, Any]]:
    resolved_inbox = inbox or recommendation_inbox
    created: list[dict[str, Any]] = []
    draft_items = report.get("review_items") if isinstance(report.get("review_items"), list) else []
    for draft in draft_items:
        if not isinstance(draft, dict):
            continue
        try:
            created.append(
                resolved_inbox.create(
                    title=str(draft.get("title") or "Asset needs review"),
                    detail=str(draft.get("detail") or "Review this imported row before relying on it."),
                    priority=str(draft.get("priority") or "medium"),
                    recommendation_type=str(draft.get("recommendation_type") or "general"),
                    source=str(draft.get("source") or "import_workbench"),
                    action_payload=draft.get("action_payload") if isinstance(draft.get("action_payload"), dict) else {},
                )
            )
        except ValueError:
            continue
    return created


@app.post("/api/import/workbench/{session_id}/apply", response_model=ImportWorkbenchApplyResponse)
async def apply_import_workbench_session(
    session_id: str,
    http_request: Request,
    request: ImportWorkbenchApplyRequest | None = None,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> ImportWorkbenchApplyResponse:
    require_csrf(http_request)
    require_permission(services.context, "imports.write")
    apply_request = request or ImportWorkbenchApplyRequest()
    try:
        session = services.import_workbench_store.load_session(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if session.get("status") == "applied" and session.get("report_id"):
        raise HTTPException(
            status_code=409,
            detail=f"Import workbench session has already been applied: {session.get('report_id')}",
        )

    source_file = session.get("source_file") if isinstance(session.get("source_file"), dict) else {}
    file_path = resolve_import_path(
        str(source_file.get("path") or ""),
        import_inbox_dir=services.paths.import_inbox_dir,
        workspace_root=services.paths.root,
    )
    options = session.get("options") if isinstance(session.get("options"), dict) else {}
    import_request = CsvImportRequest(
        path=str(file_path),
        dry_run=False,
        delimiter=str(options.get("delimiter") or ","),
        broker_template=str(options.get("broker_template") or "auto"),
        default_data_source=options.get("default_data_source"),
        default_currency=options.get("default_currency"),
        archive_after_success=bool(apply_request.archive_after_success),
    )
    response = await execute_csv_import(file_path=file_path, request=import_request, services=services)
    report = services.import_workbench_store.create_report(
        session=session,
        apply_response=response,
        operator=apply_request.operator,
    )
    _create_import_review_items(report, inbox=services.recommendation_inbox)
    updated_session = services.import_workbench_store.update_session_after_apply(
        session_id,
        apply_response=response,
        report=report,
    )
    _queue_autogit_event("import_workbench_applied")
    return ImportWorkbenchApplyResponse(
        session=ImportWorkbenchPreviewResponse.model_validate(updated_session),
        report=ImportReportResponse.model_validate(report),
    )


@app.get("/api/import/reports", response_model=ImportReportListResponse)
def list_import_reports(
    limit: int = 50,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> ImportReportListResponse:
    require_permission(services.context, "imports.read")
    reports = [
        ImportReportResponse.model_validate(report)
        for report in services.import_workbench_store.list_reports(limit=limit)
    ]
    return ImportReportListResponse(reports=reports)


@app.get("/api/import/reports/{report_id}", response_model=ImportReportResponse)
def get_import_report(
    report_id: str,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> ImportReportResponse:
    require_permission(services.context, "imports.read")
    try:
        report = services.import_workbench_store.load_report(report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ImportReportResponse.model_validate(report)


@app.post("/api/planning/scenarios", response_model=PlanningResponse)
async def plan_scenarios(
    request: ScenarioRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> PlanningResponse:
    resolved_services = route_workspace_services(services, permission="plan.read")
    require_permission(resolved_services.context, "portfolio.read")
    require_permission(resolved_services.context, "profile.read")
    current_value = request.current_portfolio_value_usd
    if current_value is None:
        try:
            latest_snapshot = resolved_services.snapshot_store.latest()
            current_value = latest_snapshot.total_value_usd
        except FileNotFoundError as exc:
            raise HTTPException(
                status_code=400,
                detail="Provide current_portfolio_value_usd or create a snapshot first",
            ) from exc

    resolved_years = (
        int(request.years)
        if request.years is not None
        else int(scenario_engine.years_to_retirement)
    )
    planning_settings_for_run: dict[str, Any] = {"years": resolved_years}
    if request.state_tax_rate is not None:
        planning_settings_for_run["state_tax_rate"] = request.state_tax_rate
    if request.roth_conversion_annual_amount_usd is not None:
        planning_settings_for_run["roth_conversion_annual_amount_usd"] = request.roth_conversion_annual_amount_usd
    if request.roth_conversion_start_age is not None:
        planning_settings_for_run["roth_conversion_start_age"] = request.roth_conversion_start_age
    if request.roth_conversion_end_age is not None:
        planning_settings_for_run["roth_conversion_end_age"] = request.roth_conversion_end_age
    if request.drawdown_order is not None:
        planning_settings_for_run["drawdown_order"] = request.drawdown_order
    if request.simulation_mode is not None:
        planning_settings_for_run["simulation_mode"] = request.simulation_mode
    if request.simulation_monte_carlo_variant is not None:
        planning_settings_for_run["simulation_monte_carlo_variant"] = request.simulation_monte_carlo_variant
    if request.simulation_historical_start_year is not None:
        planning_settings_for_run["simulation_historical_start_year"] = request.simulation_historical_start_year
    if request.simulation_seed is not None:
        planning_settings_for_run["simulation_seed"] = request.simulation_seed
    if request.household_mode is not None:
        planning_settings_for_run["household_mode"] = request.household_mode
    if request.household_partner_income_usd is not None:
        planning_settings_for_run["household_partner_income_usd"] = request.household_partner_income_usd
    if request.household_partner_income_growth_rate is not None:
        planning_settings_for_run["household_partner_income_growth_rate"] = request.household_partner_income_growth_rate
    if request.household_partner_retirement_age is not None:
        planning_settings_for_run["household_partner_retirement_age"] = request.household_partner_retirement_age
    if request.household_partner_social_security_annual_usd is not None:
        planning_settings_for_run["household_partner_social_security_annual_usd"] = (
            request.household_partner_social_security_annual_usd
        )
    if request.household_partner_social_security_claiming_age is not None:
        planning_settings_for_run["household_partner_social_security_claiming_age"] = (
            request.household_partner_social_security_claiming_age
        )
    if request.household_shared_goal_target_usd is not None:
        planning_settings_for_run["household_shared_goal_target_usd"] = request.household_shared_goal_target_usd
    if request.household_shared_goal_target_year is not None:
        planning_settings_for_run["household_shared_goal_target_year"] = request.household_shared_goal_target_year
    if request.filing_status is not None:
        planning_settings_for_run["filing_status"] = request.filing_status
    request_household_overrides_provided = any(
        value is not None
        for value in (
            request.household_mode,
            request.household_partner_income_usd,
            request.household_partner_income_growth_rate,
            request.household_partner_retirement_age,
            request.household_partner_social_security_annual_usd,
            request.household_partner_social_security_claiming_age,
            request.household_shared_goal_target_usd,
            request.household_shared_goal_target_year,
            request.filing_status,
        )
    )
    active_assumption_set: dict[str, Any] | None = None
    service = plan_simulation_service
    timeline_projection: TimelineImpactProjectionResponse | None = None
    active_timeline_payload: dict[str, Any] | None = None
    active_withdrawal_strategy: str | None = None
    active_drawdown_order: str | None = None
    active_retirement_age: int | None = None
    active_plan_detail: dict[str, Any] | None = None
    active_plan_id = resolved_services.plan_workspace.get_active_plan_id()
    if active_plan_id:
        try:
            active_plan_detail = resolved_services.plan_workspace.get_plan(active_plan_id)
            active_timeline = resolve_plan_timeline_payload(active_plan_detail)
            active_timeline_payload = active_timeline
            active_retirement_age = resolve_timeline_retirement_age(active_timeline)
            timeline_strategy = resolve_timeline_withdrawal_strategy(active_timeline)
            timeline_drawdown_order = resolve_timeline_drawdown_order(active_timeline)
            active_settings = active_plan_detail.get("settings")
            if isinstance(active_settings, dict):
                active_withdrawal_strategy = str(active_settings.get("withdrawal_strategy") or "").strip() or None
                active_drawdown_order = str(active_settings.get("drawdown_order") or "").strip() or None
                planning_settings_for_run.update(active_settings)
            planning_settings_for_run["years"] = resolved_years
            assumption_sets_payload = resolve_plan_assumption_sets(active_plan_detail)
            planning_settings_for_run, active_assumption_set = apply_assumption_set_to_settings(
                plan_settings=planning_settings_for_run,
                assumption_sets_payload=assumption_sets_payload,
                assumption_set_id=None,
            )
            service = build_plan_simulation_service_for_plan_settings(planning_settings_for_run)
            if not active_withdrawal_strategy:
                active_withdrawal_strategy = timeline_strategy
            if not active_drawdown_order:
                active_drawdown_order = timeline_drawdown_order
            timeline_projection = build_timeline_projection_for_plan_settings(
                plan_settings=planning_settings_for_run,
                timeline_payload=active_timeline,
            )
        except PlanNotFoundError:
            timeline_projection = None
            active_plan_detail = None
            active_timeline_payload = None
            active_withdrawal_strategy = None
            active_drawdown_order = None
            active_retirement_age = None

    if request.simulation_mode is not None:
        planning_settings_for_run["simulation_mode"] = request.simulation_mode
    if request.simulation_monte_carlo_variant is not None:
        planning_settings_for_run["simulation_monte_carlo_variant"] = request.simulation_monte_carlo_variant
    if request.simulation_historical_start_year is not None:
        planning_settings_for_run["simulation_historical_start_year"] = request.simulation_historical_start_year
    if request.simulation_seed is not None:
        planning_settings_for_run["simulation_seed"] = request.simulation_seed

    resolved_start_year = utc_now().year
    household_settings = _resolve_household_settings(
        plan_settings=planning_settings_for_run,
        start_year=resolved_start_year,
        years=resolved_years,
    )

    income_projection = build_income_projection_for_plan_settings(planning_settings_for_run)
    expense_projection = build_expense_projection_for_plan_settings(planning_settings_for_run)
    debt_projection = build_debt_projection_for_plan_settings(planning_settings_for_run)
    income_projection_payload = income_projection.model_dump(mode="json") if income_projection is not None else None
    expense_projection_payload = expense_projection.model_dump(mode="json") if expense_projection is not None else None
    (
        income_projection_payload,
        expense_projection_payload,
        household_adjustments_payload,
    ) = _apply_household_adjustments_to_projection_payloads(
        income_projection=income_projection_payload,
        expense_projection=expense_projection_payload,
        household_settings=household_settings,
        start_year=resolved_start_year,
        start_age=35,
        years=resolved_years,
    )

    resolved_annual_contribution = (
        float(request.annual_contribution_usd)
        if request.annual_contribution_usd is not None
        else float(service.scenario_engine.annual_contribution_usd)
    )
    resolved_current_value = float(current_value)
    if timeline_projection is not None:
        resolved_current_value = max(
            0.0,
            resolved_current_value + float(timeline_projection.first_year_portfolio_impact_usd),
        )
        resolved_annual_contribution = max(
            0.0,
            resolved_annual_contribution + float(timeline_projection.first_year_contribution_impact_usd),
        )

    contribution_rules_payload: dict[str, Any] | None = None
    if active_plan_detail is not None:
        contribution_rules_payload = resolve_plan_contribution_rules(active_plan_detail)
    contribution_allocation = build_contribution_allocation_for_plan_settings(
        plan_settings={
            **planning_settings_for_run,
            "annual_contribution_usd": resolved_annual_contribution,
        },
        contribution_rules_payload=contribution_rules_payload,
    )
    social_security_projection: SocialSecurityProjectionResponse | None = None
    rmd_projection: RmdProjectionResponse | None = None
    if active_timeline_payload is not None:
        social_security_projection = build_social_security_projection_for_plan_settings(
            plan_settings=planning_settings_for_run,
            timeline_payload=active_timeline_payload,
            income_projection=income_projection,
            start_year=utc_now().year,
        )
        rmd_projection = build_rmd_projection_for_plan_settings(
            plan_settings=planning_settings_for_run,
            timeline_payload=active_timeline_payload,
            start_year=utc_now().year,
            accounts_override=build_planning_accounts_from_portfolio(resolved_services.portfolio_store),
        )

    profile_payload = get_financial_profile_payload(resolved_services.financial_profile_store)
    tax_profile = profile_payload.get("tax_profile")
    filing_status: str | None = None
    state_tax_rate: float | None = None
    include_irmaa = bool(request.include_irmaa)
    if isinstance(tax_profile, dict):
        filing_status = _resolve_filing_status_for_household(
            filing_status=tax_profile.get("filing_status"),
            household_mode=str(household_settings.get("household_mode") or HOUSEHOLD_MODE_INDIVIDUAL),
        )
        if tax_profile.get("state_tax_rate") is not None:
            state_tax_rate = max(
                0.0,
                min(1.0, _coerce_float(tax_profile.get("state_tax_rate"), 0.0)),
            )

    if planning_settings_for_run.get("filing_status"):
        filing_status = _resolve_filing_status_for_household(
            filing_status=planning_settings_for_run.get("filing_status"),
            household_mode=str(household_settings.get("household_mode") or HOUSEHOLD_MODE_INDIVIDUAL),
        )
    if filing_status is None:
        filing_status = _resolve_filing_status_for_household(
            filing_status=None,
            household_mode=str(household_settings.get("household_mode") or HOUSEHOLD_MODE_INDIVIDUAL),
        )
    if planning_settings_for_run.get("state_tax_rate") is not None:
        state_tax_rate = max(
            0.0,
            min(1.0, _coerce_float(planning_settings_for_run.get("state_tax_rate"), 0.0)),
        )
    roth_conversion_annual_amount = max(
        0.0,
        _coerce_float(planning_settings_for_run.get("roth_conversion_annual_amount_usd"), 0.0),
    )
    roth_conversion_start_age: int | None = None
    roth_conversion_end_age: int | None = None
    if planning_settings_for_run.get("roth_conversion_start_age") is not None:
        roth_conversion_start_age = max(
            0,
            min(120, _coerce_int(planning_settings_for_run.get("roth_conversion_start_age"), 0)),
        )
    if planning_settings_for_run.get("roth_conversion_end_age") is not None:
        roth_conversion_end_age = max(
            0,
            min(120, _coerce_int(planning_settings_for_run.get("roth_conversion_end_age"), 0)),
        )
    if (
        roth_conversion_start_age is not None
        and roth_conversion_end_age is not None
        and roth_conversion_start_age > roth_conversion_end_age
    ):
        roth_conversion_start_age, roth_conversion_end_age = (
            roth_conversion_end_age,
            roth_conversion_start_age,
        )
    if not active_drawdown_order:
        active_drawdown_order = str(planning_settings_for_run.get("drawdown_order") or "").strip() or None
    requested_drawdown_order = str(request.drawdown_order or "").strip() or None
    if requested_drawdown_order is not None:
        active_drawdown_order = requested_drawdown_order

    result = await service.run(
        current_portfolio_value_usd=resolved_current_value,
        annual_contribution_usd=resolved_annual_contribution,
        years=request.years,
        hsa_extra_contribution_usd=request.hsa_extra_contribution_usd,
        accounts=build_planning_accounts_from_portfolio(resolved_services.portfolio_store),
        income_projection=income_projection_payload,
        expense_projection=expense_projection_payload,
        debt_projection=debt_projection.model_dump(mode="json") if debt_projection is not None else None,
        timeline_projection=timeline_projection.model_dump(mode="json") if timeline_projection is not None else None,
        contribution_allocation=(
            contribution_allocation.model_dump(mode="json")
            if contribution_allocation is not None
            else None
        ),
        social_security_projection=(
            social_security_projection.model_dump(mode="json")
            if social_security_projection is not None
            else None
        ),
        rmd_projection=(
            rmd_projection.model_dump(mode="json")
            if rmd_projection is not None
            else None
        ),
        filing_status=filing_status,
        state_tax_rate=state_tax_rate,
        include_irmaa=include_irmaa,
        roth_conversion_annual_amount_usd=roth_conversion_annual_amount,
        roth_conversion_start_age=roth_conversion_start_age,
        roth_conversion_end_age=roth_conversion_end_age,
        drawdown_order=active_drawdown_order,
        household_mode=str(household_settings.get("household_mode") or HOUSEHOLD_MODE_INDIVIDUAL),
        household_partner_income_usd=household_settings.get("household_partner_income_usd"),
        household_partner_income_growth_rate=household_settings.get("household_partner_income_growth_rate"),
        household_partner_retirement_age=household_settings.get("household_partner_retirement_age"),
        household_partner_social_security_annual_usd=household_settings.get("household_partner_social_security_annual_usd"),
        household_partner_social_security_claiming_age=household_settings.get("household_partner_social_security_claiming_age"),
        household_shared_goal_target_usd=household_settings.get("household_shared_goal_target_usd"),
        household_shared_goal_target_year=household_settings.get("household_shared_goal_target_year"),
        household_shared_goal_annual_funding_usd=household_adjustments_payload.get("shared_goal_annual_funding_usd"),
        household_partner_income_added_first_year_usd=household_adjustments_payload.get("partner_income_added_first_year_usd"),
        household_partner_income_added_total_usd=household_adjustments_payload.get("partner_income_added_total_usd"),
        start_year=resolved_start_year,
        withdrawal_strategy=active_withdrawal_strategy,
        retirement_age=active_retirement_age,
        simulation_mode=planning_settings_for_run.get("simulation_mode"),
        simulation_monte_carlo_variant=planning_settings_for_run.get("simulation_monte_carlo_variant"),
        simulation_historical_start_year=planning_settings_for_run.get("simulation_historical_start_year"),
        simulation_seed=planning_settings_for_run.get("simulation_seed"),
        assumption_set_id=(
            str(active_assumption_set.get("id"))
            if isinstance(active_assumption_set, dict) and active_assumption_set.get("id")
            else None
        ),
        assumption_set_name=(
            str(active_assumption_set.get("name"))
            if isinstance(active_assumption_set, dict) and active_assumption_set.get("name")
            else None
        ),
    )
    if request_household_overrides_provided:
        household_source = "scenario_request_overrides"
    elif active_plan_detail is not None:
        household_source = "active_plan_settings"
    else:
        household_source = "scenario_request_defaults"
    household_context = _build_household_response_context(
        household_settings=household_settings,
        household_adjustments=household_adjustments_payload,
        filing_status=filing_status,
        source=household_source,
    )
    return _apply_household_context_to_planning_response(
        response=result,
        household_context=household_context,
    )


@app.post("/api/planning/income-projection", response_model=IncomeProjectionResponse)
def planning_income_projection(
    request: IncomeProjectionRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> IncomeProjectionResponse:
    resolved_services = route_workspace_services(services, permission="profile.read")
    if request.income_items is not None:
        income_items = [item.model_dump(mode="json") for item in request.income_items]
    else:
        profile_payload = get_financial_profile_payload(resolved_services.financial_profile_store)
        raw_items = profile_payload.get("income_items")
        income_items = raw_items if isinstance(raw_items, list) else []

    payload = project_income_schedule(
        income_items,
        start_year=request.start_year or utc_now().year,
        years=request.years,
        default_annual_growth_rate=(
            settings.planner_inflation
            if request.default_annual_growth_rate is None
            else float(request.default_annual_growth_rate)
        ),
    )
    return IncomeProjectionResponse(**payload)


@app.post("/api/planning/expense-projection", response_model=ExpenseProjectionResponse)
def planning_expense_projection(
    request: ExpenseProjectionRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> ExpenseProjectionResponse:
    resolved_services = route_workspace_services(services, permission="profile.read")
    if request.expense_items is not None:
        expense_items = [item.model_dump(mode="json") for item in request.expense_items]
    else:
        profile_payload = get_financial_profile_payload(resolved_services.financial_profile_store)
        raw_items = profile_payload.get("expense_items")
        expense_items = raw_items if isinstance(raw_items, list) else []

    payload = project_expense_schedule(
        expense_items,
        start_year=request.start_year or utc_now().year,
        years=request.years,
        default_inflation_rate=(
            settings.planner_inflation
            if request.default_inflation_rate is None
            else float(request.default_inflation_rate)
        ),
    )
    return ExpenseProjectionResponse(**payload)


@app.post("/api/planning/debt-projection", response_model=DebtProjectionResponse)
def planning_debt_projection(
    request: DebtProjectionRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> DebtProjectionResponse:
    resolved_services = route_workspace_services(services, permission="profile.read")
    if request.debt_items is not None:
        debt_items = [item.model_dump(mode="json") for item in request.debt_items]
    else:
        profile_payload = get_financial_profile_payload(resolved_services.financial_profile_store)
        raw_items = profile_payload.get("debt_items")
        debt_items = raw_items if isinstance(raw_items, list) else []

    payload = project_debt_payoff(
        debt_items,
        start_date=request.start_date or utc_now().date().replace(day=1),
        max_years=request.max_years,
        strategy=request.strategy,
        monthly_accelerated_payment_usd=request.monthly_accelerated_payment_usd,
    )
    return DebtProjectionResponse(**payload)


@app.post("/api/planning/social-security-projection", response_model=SocialSecurityProjectionResponse)
def planning_social_security_projection(
    request: SocialSecurityProjectionRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> SocialSecurityProjectionResponse:
    resolved_services = route_workspace_services(services, permission="profile.read")
    earnings_history = (
        [item.model_dump(mode="json") for item in request.earnings_history]
        if request.earnings_history is not None
        else []
    )

    estimated_annual_earnings_usd = request.estimated_annual_earnings_usd
    if estimated_annual_earnings_usd is None and not earnings_history:
        profile_payload = get_financial_profile_payload(resolved_services.financial_profile_store)
        income_rows = profile_payload.get("income_items")
        if isinstance(income_rows, list):
            estimated_annual_earnings_usd = max(
                0.0,
                sum(
                    max(0.0, _coerce_float(item.get("monthly_amount_usd"), 0.0))
                    for item in income_rows
                    if isinstance(item, dict)
                )
                * 12.0,
            )

    payload = project_social_security_income(
        start_year=request.start_year or utc_now().year,
        years=request.years,
        current_age=request.current_age,
        birth_year=request.birth_year,
        claiming_age=request.claiming_age,
        life_expectancy_age=request.life_expectancy_age,
        fra_monthly_benefit_usd=request.fra_monthly_benefit_usd,
        estimated_annual_earnings_usd=estimated_annual_earnings_usd,
        earnings_history=earnings_history,
        cola_rate=request.cola_rate,
        claim_age_options=request.claim_age_options,
        pia_bend_point_1_usd=request.pia_bend_point_1_usd,
        pia_bend_point_2_usd=request.pia_bend_point_2_usd,
    )
    return SocialSecurityProjectionResponse(**payload)


@app.post("/api/planning/rmd-projection", response_model=RmdProjectionResponse)
def planning_rmd_projection(
    request: RmdProjectionRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> RmdProjectionResponse:
    resolved_services = route_workspace_services(services, permission="portfolio.read")
    if request.accounts is not None:
        accounts = [item.model_dump(mode="json") for item in request.accounts]
    else:
        accounts = build_planning_accounts_from_portfolio(resolved_services.portfolio_store)

    payload = project_rmd_schedule(
        accounts=accounts,
        start_year=request.start_year or utc_now().year,
        years=request.years,
        current_age=request.current_age,
        birth_year=request.birth_year,
        expected_return=request.expected_return,
        start_age_override=request.start_age_override,
    )
    return RmdProjectionResponse(**payload)


@app.post("/api/planning/tax-estimate", response_model=TaxEstimateResponse)
def planning_tax_estimate(request: TaxEstimateRequest) -> TaxEstimateResponse:
    return TaxEstimateResponse(
        **estimate_federal_tax(
            tax_year=request.tax_year,
            filing_status=request.filing_status,
            earned_income_usd=request.earned_income_usd,
            ordinary_income_usd=request.ordinary_income_usd,
            short_term_capital_gains_usd=request.short_term_capital_gains_usd,
            long_term_capital_gains_usd=request.long_term_capital_gains_usd,
            qualified_dividends_usd=request.qualified_dividends_usd,
            interest_income_usd=request.interest_income_usd,
            social_security_income_usd=request.social_security_income_usd,
            tax_exempt_interest_income_usd=request.tax_exempt_interest_income_usd,
            pre_tax_contributions_usd=request.pre_tax_contributions_usd,
            state_tax_rate=request.state_tax_rate,
            state_tax_deduction_usd=request.state_tax_deduction_usd,
            age=request.age,
            include_irmaa=request.include_irmaa,
            medicare_months_covered=request.medicare_months_covered,
            tax_withholding_usd=request.tax_withholding_usd,
        )
    )


@app.post("/api/planning/contribution-allocation", response_model=ContributionAllocationResponse)
def planning_contribution_allocation(
    request: ContributionAllocationRequest,
    services: WorkspaceServices = Depends(get_workspace_services),
) -> ContributionAllocationResponse:
    resolved_services = route_workspace_services(services, permission="portfolio.read")
    accounts = [item.model_dump(mode="json") for item in request.accounts] or build_planning_accounts_from_portfolio(
        resolved_services.portfolio_store,
    )
    if not accounts:
        raise HTTPException(status_code=400, detail="No accounts available to allocate contributions.")

    base_rule = request.base_rule if isinstance(request.base_rule, dict) else {"type": "save"}
    rules = list(request.rules)
    profile_id = request.profile_id

    if not rules and (profile_id is None or profile_id == "tax_optimized_high_earner"):
        generated = build_tax_optimized_high_earner_rules(
            accounts,
            employer_match_target_usd=request.employer_match_target_usd,
        )
        rules = generated.get("rules", [])
        base_rule = generated.get("base_rule", base_rule)
        profile_id = generated.get("profile_id", "tax_optimized_high_earner")

    payload = allocate_contributions(
        annual_contribution_usd=request.annual_contribution_usd,
        age=request.age,
        accounts=accounts,
        rules=rules,
        base_rule=base_rule,
        profile_id=profile_id,
    )
    return ContributionAllocationResponse(**payload)


@app.post("/api/research/options-chain", response_model=ResearchResponse)
def options_chain(request: OptionsChainRequest) -> ResearchResponse:
    return research_service.options_chain(request.symbol)


@app.post("/api/research/quote", response_model=ResearchResponse)
def quote(request: OptionsChainRequest) -> ResearchResponse:
    return research_service.quote(request.symbol)


@app.post("/api/research/price-history", response_model=ResearchResponse)
def price_history(request: PriceHistoryRequest) -> ResearchResponse:
    return research_service.price_history(
        symbol=request.symbol,
        period=request.period,
        interval=request.interval,
    )


@app.post("/api/research/compare", response_model=ResearchCompareResponse)
def research_compare(request: ResearchCompareRequest) -> ResearchCompareResponse:
    if len(request.symbols) < 2:
        raise HTTPException(status_code=400, detail="Research compare requires at least 2 symbols.")

    return research_service.compare(
        symbols=request.symbols,
        period=request.period,
        interval=request.interval,
        baseline_symbol=request.baseline_symbol,
    )


@app.post("/api/research/evidence-packet", response_model=ResearchEvidencePacket)
def research_evidence_packet(request: ResearchEvidencePacketRequest) -> ResearchEvidencePacket:
    if not request.symbol:
        raise HTTPException(status_code=400, detail="Research evidence packet requires a symbol.")

    try:
        return research_service.evidence_packet(
            symbol=request.symbol,
            period=request.period,
            interval=request.interval,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/research/dossier", response_model=ResearchDossierResponse)
def research_dossier(request: ResearchDossierRequest) -> ResearchDossierResponse:
    if len(request.symbols) < 2:
        raise HTTPException(status_code=400, detail="Research dossier requires at least 2 symbols.")

    try:
        return build_research_dossier_payload(
            symbols=request.symbols,
            period=request.period,
            interval=request.interval,
            baseline_symbol=request.baseline_symbol,
            thesis=request.thesis,
            risks=request.risks,
            catalysts=request.catalysts,
            plan_id=request.plan_id,
            save_to_plan=request.save_to_plan,
            include_portfolio_fit=request.include_portfolio_fit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/research/dossiers", response_model=ResearchDossierLookupResponse)
def research_dossier_lookup(
    plan_id: str | None = None,
    limit: int = 5,
    include_content: bool = False,
) -> ResearchDossierLookupResponse:
    payload = build_research_dossier_lookup_payload(
        plan_id=plan_id,
        limit=limit,
        include_content=include_content,
    )
    return ResearchDossierLookupResponse(**payload)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if request.refresh_snapshot:
        snapshot = await build_live_snapshot()
        snapshot_store.write(snapshot)
    else:
        try:
            snapshot = snapshot_store.latest()
        except FileNotFoundError:
            snapshot = await build_live_snapshot()
            snapshot_store.write(snapshot)

    planning = scenario_engine.run(current_portfolio_value_usd=snapshot.total_value_usd).model_dump()
    research = None

    if any(token in request.question.lower() for token in ["option", "options", "chain", "research"]):
        # Default demo symbol until a ticker is requested explicitly.
        research = research_service.options_chain("AAPL").model_dump()

    return coordinator.answer(
        question=request.question,
        snapshot=snapshot,
        planning=planning,
        research=research,
    )

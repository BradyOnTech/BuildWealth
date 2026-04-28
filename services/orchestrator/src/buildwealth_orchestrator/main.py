from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
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
    RecommendationOutcomeUpdateRequest,
    CashLiquidityRecommendationGenerateRequest,
    PlanTrackingRecommendationGenerateRequest,
    ProfileCompletenessRecommendationGenerateRequest,
    PortfolioRiskRecommendationGenerateRequest,
    RecommendationFactoryResponse,
    RecommendationFactoryRunAllRequest,
    RecommendationFactoryRunAllResponse,
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
    EngineStatusResponse,
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
    RuntimeTelemetryResponse,
    TodayCommandCard,
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
    OpenAIChatToolClient,
)
from buildwealth_orchestrator.services.csv_importer import (
    apply_existing_transaction_reconciliation,
    archive_import_file,
    list_csv_templates,
    parse_transaction_csv,
)
from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.ignidash_exporter import (
    IgnidashExportStore,
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
from buildwealth_orchestrator.services.portfolio_simulator import simulate_trade
from buildwealth_orchestrator.services.portfolio_fit import assess_portfolio_fit
from buildwealth_orchestrator.services.goal_tracker import compute_goal_progress
from buildwealth_orchestrator.services.financial_health import compute_financial_health
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
from buildwealth_orchestrator.services.engine_adapter import SidecarAdapter
from buildwealth_orchestrator.services.portfolio_benchmark import (
    GHOSTFOLIO_BENCHMARK_CONTRACT_VERSION,
    GhostfolioBenchmarkService,
)
from buildwealth_orchestrator.services.portfolio_attribution import (
    GHOSTFOLIO_ATTRIBUTION_CONTRACT_VERSION,
    GhostfolioAttributionService,
)
from buildwealth_orchestrator.services.planning_sidecar import (
    IGNIDASH_SCENARIO_CONTRACT_VERSION,
    IgnidashScenarioService,
)
from buildwealth_orchestrator.services.engine_status import EngineProbeConfig, EngineStatusTracker
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
from buildwealth_orchestrator.services.versioned_workspace import (
    VersionedWorkspacePolicy,
    VersionedWorkspaceService,
)
from buildwealth_orchestrator.services.tax_engine import estimate_federal_tax
from buildwealth_orchestrator.services.today_dashboard import build_today_dashboard_payload
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
from buildwealth_orchestrator.services.runtime_telemetry import (
    RuntimeTelemetryTracker,
    summarize_cache_quality,
)
from buildwealth_orchestrator.services.workflow_runner import WorkflowRunner
from buildwealth_orchestrator.services.plan_workspace import (
    PlanNotFoundError,
    PlanWorkspace,
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
    generate_cash_liquidity_recommendations,
    generate_plan_tracking_recommendations,
    generate_portfolio_risk_recommendations,
    generate_profile_completeness_recommendations,
    generate_stale_assumption_recommendations,
    generate_watchlist_research_recommendations,
)
from buildwealth_orchestrator.services.user_settings import UserSettingsStore
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

# Apply user settings over env defaults
_user_cfg = user_settings_store.load_raw()
if _user_cfg.get("openai_api_key"):
    settings.openai_api_key = _user_cfg["openai_api_key"]
if _user_cfg.get("openai_model"):
    settings.openai_model = _user_cfg["openai_model"]
if _user_cfg.get("openai_base_url"):
    settings.openai_base_url = _user_cfg["openai_base_url"]


def parse_path_candidates(raw_value: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    values = tuple(
        item.strip()
        for item in str(raw_value or "").split(",")
        if item.strip()
    )
    return values or fallback


snapshot_store = SnapshotStore(settings.snapshot_dir)
portfolio_store = PortfolioStore(settings.snapshot_dir.parent / "portfolio")
durable_storage_service = DurableStorageMigrationService.from_settings(settings)
backup_restore_service = BackupRestoreService.from_settings(settings)
data_protection_service = DataProtectionService.from_settings(settings)
ignidash_export_store = IgnidashExportStore(settings.ignidash_export_dir)
portfolio_review_packet_store = PortfolioReviewPacketStore(settings.portfolio_review_packet_dir)


def _git_policy() -> dict[str, Any]:
    return git_integration_settings_store.load()


def _versioned_workspace_service(policy: dict[str, Any]) -> VersionedWorkspaceService:
    return VersionedWorkspaceService(
        workspace_dir=Path(str(policy.get("workspace_dir") or settings.versioned_workspace_dir)),
        plans_dir=settings.plans_dir,
        recommendations_path=settings.recommendations_path,
        review_packet_dir=settings.portfolio_review_packet_dir,
        protection_policy_path=settings.protection_policy_path,
        financial_profile_path=settings.financial_profile_path,
    )


def _git_repository_service(policy: dict[str, Any]) -> GitRepositoryService:
    return GitRepositoryService(Path(str(policy.get("workspace_dir") or settings.versioned_workspace_dir)))


def _git_checkpoint_service(policy: dict[str, Any]) -> GitCheckpointService:
    workspace_service = _versioned_workspace_service(policy)
    return GitCheckpointService(
        workspace_service=workspace_service,
        git_repository=_git_repository_service(policy),
    )


def _git_restore_apply_service(policy: dict[str, Any]) -> GitRestoreApplyService:
    return GitRestoreApplyService(
        git_repository=_git_repository_service(policy),
        checkpoint_service=_git_checkpoint_service(policy),
        workspace_policy=_git_workspace_policy(policy),
        plan_workspace=plan_workspace,
        recommendation_inbox=recommendation_inbox,
        review_packet_store=portfolio_review_packet_store,
    )


def _git_activity_store() -> GitActivityStore:
    return GitActivityStore(settings.git_integration_settings_path.with_name("git_activity.jsonl"))


def _git_restore_preview_token_store() -> GitRestorePreviewTokenStore:
    return GitRestorePreviewTokenStore(
        settings.git_integration_settings_path.with_name("git_restore_preview_tokens.jsonl")
    )


def _git_autogit_service(policy: dict[str, Any]) -> GitAutoGitService:
    return GitAutoGitService(
        state_path=settings.git_integration_settings_path.with_name("git_autogit_state.json"),
        checkpoint_service=_git_checkpoint_service(policy),
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


def _run_due_autogit() -> dict[str, Any]:
    policy = _git_policy()
    state = _git_autogit_service(policy).run_due(
        policy=policy,
        workspace_policy=_git_workspace_policy(policy),
    )
    if state.get("status") not in {"idle", "pending", "disabled"} and state.get("last_result"):
        result = state["last_result"]
        _git_activity_store().record(
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
ghostfolio_sidecar_adapter = SidecarAdapter(
    base_url=settings.ghostfolio_sidecar_base_url,
    timeout_seconds=settings.engine_sidecar_timeout_seconds,
    max_retries=settings.engine_sidecar_retry_count,
)
benchmark_service = GhostfolioBenchmarkService(
    snapshot_store=snapshot_store,
    research_service=research_service,
    sidecar_adapter=ghostfolio_sidecar_adapter,
    sidecar_enabled=settings.enable_ghostfolio_benchmark_sidecar,
    sidecar_path=settings.ghostfolio_benchmark_sidecar_path,
    base_currency=settings.app_currency,
)
attribution_service = GhostfolioAttributionService(
    portfolio_store=portfolio_store,
    sidecar_adapter=ghostfolio_sidecar_adapter,
    sidecar_enabled=settings.enable_ghostfolio_attribution_sidecar,
    sidecar_path=settings.ghostfolio_attribution_sidecar_path,
    base_currency=settings.app_currency,
)
ignidash_sidecar_adapter = SidecarAdapter(
    base_url=settings.ignidash_sidecar_base_url,
    timeout_seconds=settings.engine_sidecar_timeout_seconds,
    max_retries=settings.engine_sidecar_retry_count,
)
ignidash_scenario_service = IgnidashScenarioService(
    scenario_engine=scenario_engine,
    sidecar_adapter=ignidash_sidecar_adapter,
    sidecar_enabled=settings.enable_ignidash_scenario_sidecar,
    sidecar_path=settings.ignidash_scenario_sidecar_path,
    currency=settings.app_currency,
    default_tax_rate=settings.planner_marginal_tax_rate,
)
engine_status_tracker = EngineStatusTracker(
    configs=[
        EngineProbeConfig(
            name="ghostfolio_benchmark",
            base_url=settings.ghostfolio_sidecar_base_url,
            enabled=settings.enable_ghostfolio_benchmark_sidecar,
            health_paths=parse_path_candidates(
                settings.ghostfolio_sidecar_health_paths,
                fallback=("/health", "/api/v1/health"),
            ),
            version_paths=parse_path_candidates(
                settings.engine_sidecar_version_paths,
                fallback=("/version",),
            ),
            expected_contract_version=(
                settings.ghostfolio_sidecar_contract_version
                if settings.ghostfolio_sidecar_contract_version > 0
                else GHOSTFOLIO_BENCHMARK_CONTRACT_VERSION
            ),
        ),
        EngineProbeConfig(
            name="ghostfolio_attribution",
            base_url=settings.ghostfolio_sidecar_base_url,
            enabled=settings.enable_ghostfolio_attribution_sidecar,
            health_paths=parse_path_candidates(
                settings.ghostfolio_sidecar_health_paths,
                fallback=("/health", "/api/v1/health"),
            ),
            version_paths=parse_path_candidates(
                settings.engine_sidecar_version_paths,
                fallback=("/version",),
            ),
            expected_contract_version=(
                settings.ghostfolio_sidecar_contract_version
                if settings.ghostfolio_sidecar_contract_version > 0
                else GHOSTFOLIO_ATTRIBUTION_CONTRACT_VERSION
            ),
        ),
        EngineProbeConfig(
            name="ignidash_scenario",
            base_url=settings.ignidash_sidecar_base_url,
            enabled=settings.enable_ignidash_scenario_sidecar,
            health_paths=parse_path_candidates(
                settings.ignidash_sidecar_health_paths,
                fallback=("/health", "/api/health"),
            ),
            version_paths=parse_path_candidates(
                settings.engine_sidecar_version_paths,
                fallback=("/version",),
            ),
            expected_contract_version=(
                settings.ignidash_sidecar_contract_version
                if settings.ignidash_sidecar_contract_version > 0
                else IGNIDASH_SCENARIO_CONTRACT_VERSION
            ),
        ),
    ],
    timeout_seconds=settings.engine_sidecar_timeout_seconds,
)
coordinator = Coordinator()
conversation_store = ConversationStore(settings.conversation_dir)
plan_workspace = PlanWorkspace(settings.plans_dir)
financial_profile_store = FinancialProfileStore(settings.financial_profile_path)
recommendation_inbox = RecommendationInbox(settings.recommendations_path)
workflow_runner = WorkflowRunner(
    scenario_engine=scenario_engine,
    default_annual_contribution_usd=settings.planner_annual_contribution_usd,
    default_years=settings.planner_years_to_retirement,
    default_hsa_delta=settings.planner_hsa_delta_default,
)
openai_tool_client = OpenAIChatToolClient(
    api_key=settings.openai_api_key,
    model=settings.openai_model,
    base_url=settings.openai_base_url,
)
copilot = FinancialCopilot(
    conversation_store=conversation_store,
    llm_client=openai_tool_client,
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
        "- After calling get_buildwealth_context, inspect `quality` and `warnings` fields before making recommendations. "
        "If `quality.freshness.snapshot_stale=true` or coverage is missing sections, call that out clearly and suggest refresh actions.\n"
        "- For 'how am I doing?' or 'what is my financial situation?' → call get_financial_health first.\n"
        "- For profile onboarding or filling out missing profile fields → call get_onboarding_status, "
        "ask one focused question at a time, then call draft_financial_profile_update before saving. "
        "Only call update_financial_profile after the user explicitly confirms the drafted changes.\n"
        "- For account-level balances/cash breakdowns → call get_account_balances.\n"
        "- For allocation mix or rebalancing discussions → call get_asset_allocation.\n"
        "- For 'can I afford X?' → call assess_affordability with the monthly cost or purchase price. "
        "It computes the full impact on cash flow, savings rate, and DTI automatically.\n"
        "- For 'am I on track?' → call get_plan_tracking for plan assumptions, or get_goal_progress for specific goals.\n"
        "- For 'when will I reach my goal?' or 'what do I need to save?' → call get_goal_progress.\n"
        "- For federal tax estimates (income, capital gains, withholding) → call compute_tax.\n"
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
        "- For 'what if I buy/sell X?' → call simulate_trade to show allocation and concentration impact.\n"
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
        "- Proactively flag risks you discover (high concentration, low emergency fund, negative cash flow)."
    ),
)
copilot_context_research_cache = ExpiringCache(max_entries=settings.copilot_context_cache_max_entries)
copilot_context_projection_cache = ExpiringCache(max_entries=settings.copilot_context_cache_max_entries)
today_research_evidence_cache = ExpiringCache(max_entries=64)
runtime_telemetry_tracker = RuntimeTelemetryTracker()

sync_lock = asyncio.Lock()
scheduler_task: asyncio.Task | None = None
engine_health_task: asyncio.Task | None = None
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
    "last_ignidash_payload_path": None,
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


async def sidecar_contract_guard_reason(engine_name: str) -> str | None:
    try:
        return await engine_status_tracker.sidecar_guard_reason(engine_name)
    except Exception:
        return None


async def build_live_snapshot() -> PortfolioSnapshot:
    """Refresh prices from OpenBB and build a snapshot from local portfolio store."""
    try:
        holdings_data = await refresh_portfolio(portfolio_store, research_service)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Price refresh failed: {exc}") from exc
    return build_snapshot_from_holdings(holdings_data)


def get_sync_status() -> SyncStatusResponse:
    return SyncStatusResponse(**sync_state)


async def execute_sync(trigger: str) -> dict[str, str | dict[str, str]]:
    async with sync_lock:
        sync_state["running"] = True
        sync_state["last_trigger"] = trigger
        sync_state["last_started_at"] = utc_now()
        sync_state["last_error"] = None

        try:
            snapshot = await build_live_snapshot()
            snapshot_path = snapshot_store.write(snapshot)

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


async def scheduled_sync_loop() -> None:
    interval_seconds = max(60, int(settings.sync_interval_minutes * 60))

    while True:
        try:
            await execute_sync(trigger="scheduled")
        except Exception:
            # Failures are captured in sync_state for observability.
            pass

        await asyncio.sleep(interval_seconds)


async def engine_probe_loop() -> None:
    interval_seconds = max(10, int(settings.engine_health_probe_interval_seconds))

    while True:
        try:
            await engine_status_tracker.probe_all()
        except Exception:
            # Probe failures are reflected in tracker state where possible.
            pass

        await asyncio.sleep(interval_seconds)


async def autogit_checkpoint_loop() -> None:
    while True:
        try:
            _run_due_autogit()
        except Exception:
            # AutoGit failures are captured in the AutoGit state when possible.
            pass

        await asyncio.sleep(5)



def resolve_import_path(path_value: str) -> Path:
    candidate = Path(path_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    return (settings.import_inbox_dir / candidate).resolve()



def normalize_upload_filename(file_name: str) -> str:
    stripped = Path(file_name).name
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", stripped)
    return safe or "upload.csv"



def unique_inbox_path(base_name: str) -> Path:
    candidate = settings.import_inbox_dir / base_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix or ".csv"
    index = 1

    while True:
        with_index = settings.import_inbox_dir / f"{stem}-{index}{suffix}"
        if not with_index.exists():
            return with_index
        index += 1


async def execute_csv_import(file_path: Path, request: CsvImportRequest) -> CsvImportResponse:
    if len(request.delimiter) != 1:
        raise HTTPException(status_code=400, detail="Delimiter must be a single character")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"CSV file not found: {file_path}")

    parsed = parse_transaction_csv(
        file_path=file_path,
        default_data_source=request.default_data_source or "YAHOO",
        default_currency=request.default_currency or settings.app_currency,
        delimiter=request.delimiter,
        account_ids_by_name=portfolio_store.account_ids_by_name(),
        broker_template=request.broker_template,
    )
    parsed = apply_existing_transaction_reconciliation(
        parsed,
        existing_transactions=portfolio_store.list_transactions(limit=1_000_000),
    )

    imported_activities = 0

    if parsed.activities:
        if not request.dry_run:
            items = []
            for act in parsed.activities:
                account_id = act.get("accountId")
                account_name = str(act.get("accountName") or "").strip()
                if not account_id and account_name:
                    account_record = portfolio_store.ensure_account(account_name)
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
            imported_activities = portfolio_store.add_transactions_bulk(items)
    else:
        parsed.warnings.append("No valid activities were parsed from this CSV file.")

    if request.archive_after_success and not request.dry_run and not parsed.errors:
        archived_path = archive_import_file(file_path, settings.import_archive_dir)
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
        ghostfolio_response=None,
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


def build_ignidash_service_for_plan_settings(plan_settings: dict[str, Any]) -> IgnidashScenarioService:
    engine = build_scenario_engine_for_plan_settings(plan_settings)
    marginal_tax_rate = _coerce_float(
        plan_settings.get("marginal_tax_rate"),
        settings.planner_marginal_tax_rate,
    )
    state_tax_rate = _coerce_float(plan_settings.get("state_tax_rate"), 0.0)
    blended_effective_tax_rate = max(0.0, min(1.0, marginal_tax_rate + state_tax_rate))
    return IgnidashScenarioService(
        scenario_engine=engine,
        sidecar_adapter=ignidash_sidecar_adapter,
        sidecar_enabled=settings.enable_ignidash_scenario_sidecar,
        sidecar_path=settings.ignidash_scenario_sidecar_path,
        currency=settings.app_currency,
        default_tax_rate=blended_effective_tax_rate,
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


def build_planning_accounts_from_portfolio() -> list[dict[str, Any]]:
    holdings_payload = portfolio_store.get_holdings()
    account_totals = holdings_payload.get("account_totals", {})
    if not isinstance(account_totals, dict):
        account_totals = {}

    accounts: list[dict[str, Any]] = []
    for account in portfolio_store.get_accounts():
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
    # Preserve Ignidash-compatible branch event structure: the bridge uses
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
    service = build_ignidash_service_for_plan_settings(plan_settings)
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
    sidecar_accounts: list[dict[str, Any]] | None = build_planning_accounts_from_portfolio() or None
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
        sidecar_accounts = []
        for item in contribution_allocation.allocations:
            sidecar_accounts.append(
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
    scenario_guard_reason = await sidecar_contract_guard_reason("ignidash_scenario")

    result = await service.run(
        current_portfolio_value_usd=resolved_portfolio_value,
        annual_contribution_usd=resolved_annual_contribution,
        years=resolved_years,
        hsa_extra_contribution_usd=(float(hsa_extra) if hsa_extra is not None else None),
        accounts=sidecar_accounts,
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
        sidecar_guard_reason=scenario_guard_reason,
        assumption_set_id=(str(assumption_set.get("id")) if isinstance(assumption_set, dict) and assumption_set.get("id") else None),
        assumption_set_name=(str(assumption_set.get("name")) if isinstance(assumption_set, dict) and assumption_set.get("name") else None),
    )
    if result.engine_status == "degraded":
        await engine_status_tracker.increment_degraded(
            "ignidash_scenario",
            reason=result.warnings[0] if result.warnings else None,
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
) -> float:
    if current_portfolio_value_usd is not None:
        return float(current_portfolio_value_usd)

    try:
        latest_snapshot = snapshot_store.latest()
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
) -> dict[str, Any]:
    detail = plan_workspace.get_plan(plan_id)
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

    current_value = resolve_portfolio_value(current_portfolio_value_usd)
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


def resolve_plan_id_or_active(requested_plan_id: object | None) -> str:
    plan_id = str(requested_plan_id).strip() if isinstance(requested_plan_id, str) else ""
    if plan_id:
        return plan_id

    active_plan_id = plan_workspace.get_active_plan_id()
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


def build_snapshot_history_payload(limit: int = 30) -> SnapshotHistoryResponse:
    bounded_limit = max(2, min(int(limit), 365))
    history = snapshot_store.recent(limit=bounded_limit)

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


def resolve_active_plan_detail() -> dict[str, Any] | None:
    active_plan_id = plan_workspace.get_active_plan_id()
    if not active_plan_id:
        return None

    try:
        return plan_workspace.get_plan(active_plan_id)
    except PlanNotFoundError:
        return None


def get_financial_profile_payload() -> dict[str, Any]:
    payload = financial_profile_store.get()
    tax_profile = payload.get("tax_profile")
    if isinstance(tax_profile, dict) and not tax_profile.get("state"):
        tax_profile["state"] = settings.app_state
        payload["tax_profile"] = tax_profile
    return payload


def save_financial_profile_payload(request: FinancialProfileRequest) -> dict[str, Any]:
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

    tax_profile = payload.get("tax_profile")
    if isinstance(tax_profile, dict) and not tax_profile.get("state"):
        tax_profile["state"] = settings.app_state
        payload["tax_profile"] = tax_profile

    return financial_profile_store.save(payload)


def _recommendation_list(
    *,
    limit: int = 100,
    status: str | None = None,
    plan_id: str | None = None,
    include_archived: bool = False,
    sort: str | None = None,
) -> list[dict[str, Any]]:
    cleaned_status = str(status or "").strip().lower() or None
    status_filter = None
    if cleaned_status in {"proposed", "applied", "rejected", "archived"}:
        status_filter = cleaned_status

    resolved_plan_id = plan_id.strip() if isinstance(plan_id, str) and plan_id.strip() else None
    raw_rows = recommendation_inbox.list(
        limit=None,
        status=status_filter,  # type: ignore[arg-type]
        plan_id=resolved_plan_id,
        include_archived=include_archived,
        sort="none",
    )
    calibration_rows = recommendation_inbox.list(
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


def _build_today_command_cards(dashboard: TodayDashboardResponse) -> list[TodayCommandCard]:
    cards = list(dashboard.command_cards)
    cards.append(_build_cash_runway_command_card(dashboard))
    cards.append(_build_research_readiness_command_card(dashboard))
    try:
        proposed_rows = recommendation_inbox.list(limit=500, status="proposed", sort="created_at_desc")
        closed_rows = recommendation_inbox.list(limit=500, include_archived=True, sort="created_at_desc")
    except Exception:
        return cards

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

    pending_outcomes = [
        row for row in closed_rows
        if _recommendation_needs_outcome(row)
    ]
    first_pending_id = str(pending_outcomes[0].get("id") or "").strip() if pending_outcomes else ""
    cards.append(
        TodayCommandCard(
            id="outcome-loop",
            title="Outcome loop",
            status="warning" if pending_outcomes else "ready",
            detail=(
                f"{len(pending_outcomes)} closed recommendation(s) still need realized outcome capture."
                if pending_outcomes
                else "Closed recommendations have no pending outcome capture."
            ),
            metric_label="Pending",
            metric_value=str(len(pending_outcomes)),
            action_label="Log outcome" if pending_outcomes else "Review outcomes",
            href=f"#inbox?focus={first_pending_id}" if first_pending_id else "#inbox",
        )
    )

    return cards


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


def _build_research_readiness_command_card(dashboard: TodayDashboardResponse) -> TodayCommandCard:
    symbols: list[str] = []
    seen: set[str] = set()

    def add_symbol(raw_symbol: Any) -> None:
        symbol = re.sub(r"[^A-Z0-9._-]+", "", str(raw_symbol or "").strip().upper())
        if not symbol or symbol in seen or len(symbols) >= 4:
            return
        seen.add(symbol)
        symbols.append(symbol)

    add_symbol(dashboard.top_holding_symbol)
    try:
        for item in portfolio_store.list_watchlist():
            if not isinstance(item, dict):
                continue
            add_symbol(item.get("symbol"))
            if len(symbols) >= 4:
                break
    except Exception:
        pass

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
    realized = closure.get("realized_outcome")
    if isinstance(realized, dict) and realized:
        return False
    expected_vs_realized = closure.get("expected_vs_realized")
    if isinstance(expected_vs_realized, dict):
        return str(expected_vs_realized.get("status") or "").strip().lower() == "pending_realized"
    return True


def _build_plan_detail_response(detail: dict[str, Any]) -> PlanDetailResponse:
    payload = dict(detail)
    plan_id = str(payload.get("id") or "").strip() or None
    payload["top_next_actions"] = _build_top_next_actions(plan_id=plan_id, limit=3)
    return PlanDetailResponse(**payload)


def _build_recommendation_open_counts() -> tuple[int, int]:
    rows = recommendation_inbox.list(limit=500, status="proposed")
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
) -> list[dict[str, Any]]:
    plan_detail = plan_workspace.get_plan(plan_id)
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
        if include_content:
            with suppress(Exception):
                artifact_payload = plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
                content = str(artifact_payload.get("content") or "")
                row["content_preview"] = content[:1600]
                if not row["symbols"]:
                    row["symbols"] = _extract_symbols_from_research_dossier_title(
                        artifact_payload.get("title")
                    )
        rows.append(row)
        if len(rows) >= max_rows:
            break
    return rows


def build_research_dossier_lookup_payload(
    *,
    plan_id: str | None = None,
    limit: int = 5,
    include_content: bool = False,
) -> dict[str, Any]:
    requested_plan_id = str(plan_id or "").strip() or None
    resolved_plan_id = requested_plan_id or plan_workspace.get_active_plan_id()
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
) -> dict[str, Any]:
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

    return recommendation_inbox.create(
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
) -> PlanArtifactSummary | None:
    if not plan_id:
        return None

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
    plan_workspace.append_decision(
        plan_id=plan_id,
        summary=summary,
        rationale=" ".join(part for part in rationale_parts if part).strip(),
        status=decision_status,
    )

    artifact_payload = plan_workspace.write_artifact(
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
) -> RecommendationPreviewResponse:
    recommendation = recommendation_inbox.get(recommendation_id)
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
) -> dict[str, Any]:
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
        payload = plan_workspace.get_plan_assumption_sets(plan_id)
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
) -> RecommendationActionResponse:
    pre_apply_recommendation = recommendation_inbox.get(recommendation_id)
    scenario_diff_preview: dict[str, Any] | None = None
    if request.capture_scenario_diff:
        scenario_diff_preview = await build_recommendation_scenario_diff_preview(
            pre_apply_recommendation,
            requested_plan_id=request.plan_id,
            request_updates=request.plan_settings_updates,
        )

    result = apply_recommendation(recommendation_id, request)
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
        assumptions_payload = _build_decision_packet_assumptions(plan_id, result.plan)
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
            artifact_payload = plan_workspace.write_artifact(
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
            )
            if closure_artifact_summary is not None:
                closure_message_suffix = " Decision closure snapshot saved to plan artifacts."
        except Exception as exc:
            closure_message_suffix = f" Decision closure snapshot could not be written: {exc}"

    action_payload_raw = recommendation_payload.get("action_payload")
    action_payload = dict(action_payload_raw) if isinstance(action_payload_raw, dict) else {}
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
        updated_recommendation_payload = recommendation_inbox.update(
            recommendation_id,
            updates={"action_payload": action_payload},
        )
    refreshed_plan = (
        PlanDetailResponse(**plan_workspace.get_plan(plan_id))
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


def apply_recommendation(
    recommendation_id: str,
    request: RecommendationApplyRequest,
) -> RecommendationActionResponse:
    recommendation = recommendation_inbox.get(recommendation_id)
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

        detail = plan_workspace.update_plan_settings(
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
        plan_workspace.append_decision(
            plan_id=plan_id,
            summary=summary,
            rationale=rationale,
            status=request.decision_status or "accepted",
        )
        detail = plan_workspace.get_plan(plan_id)
        plan_detail = PlanDetailResponse(**detail)
        message = f"Logged recommendation application in plan {plan_id}."

    recommendation = recommendation_inbox.set_status(
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
) -> RecommendationActionResponse:
    recommendation = recommendation_inbox.get(recommendation_id)
    current_status = str(recommendation.get("status", "proposed")).strip().lower()
    if current_status in {"applied", "rejected"}:
        raise ValueError(f"Recommendation status is '{current_status}' and cannot be rejected.")

    scenario_diff_preview: dict[str, Any] | None = None
    if capture_scenario_diff:
        scenario_diff_preview = await build_recommendation_scenario_diff_preview(
            recommendation,
            requested_plan_id=plan_id,
        )

    updated = recommendation_inbox.set_status(
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
            plan_detail_for_packet = PlanDetailResponse(**plan_workspace.get_plan(resolved_plan_id))
        except Exception:
            plan_detail_for_packet = None

        assumptions_payload = _build_decision_packet_assumptions(resolved_plan_id, plan_detail_for_packet)
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
            artifact_payload = plan_workspace.write_artifact(
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
            )
            if closure_artifact_summary is not None:
                action_payload["decision_closure_artifact"] = {
                    "artifact_id": closure_artifact_summary.id,
                    "file_name": closure_artifact_summary.file_name,
                    "plan_id": resolved_plan_id,
                    "created_at": closure_artifact_summary.created_at.isoformat(),
                }
                plan_detail = PlanDetailResponse(**plan_workspace.get_plan(resolved_plan_id))
                closure_message_suffix = " Decision closure snapshot saved to plan artifacts."
        except (PlanNotFoundError, ValueError) as exc:
            closure_message_suffix = f" Decision closure snapshot could not be written: {exc}"

    if plan_detail is None and (decision_packet_artifact is not None) and resolved_plan_id:
        try:
            plan_detail = PlanDetailResponse(**plan_workspace.get_plan(resolved_plan_id))
        except Exception:
            plan_detail = None

    if suggested_symbols:
        action_payload["suggested_research_symbols"] = suggested_symbols
    updated = recommendation_inbox.update(
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


def update_recommendation_outcome(
    recommendation_id: str,
    request: RecommendationOutcomeUpdateRequest,
) -> RecommendationActionResponse:
    recommendation = recommendation_inbox.get(recommendation_id)
    current_status = str(recommendation.get("status", "proposed")).strip().lower()
    if current_status not in {"applied", "rejected"}:
        raise ValueError("Only applied/rejected recommendations can record realized outcomes.")

    realized_future = _coerce_optional_float(request.realized_delta_future_value_usd)
    realized_real = _coerce_optional_float(request.realized_delta_real_value_usd)
    observed_at_value = request.observed_at.isoformat() if isinstance(request.observed_at, datetime) else None
    note = str(request.note or "").strip()
    measurement_source = str(request.measurement_source or "").strip()
    if (
        realized_future is None
        and realized_real is None
        and not observed_at_value
        and not note
        and not measurement_source
        and request.observation_window_days is None
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
    action_payload["decision_closure"] = decision_closure

    resolved_plan_id = str(request.plan_id or "").strip() or str(recommendation.get("plan_id") or "").strip() or None
    if not resolved_plan_id:
        active_plan_id = plan_workspace.get_active_plan_id()
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
            )
            if closure_artifact_summary is not None:
                action_payload["decision_closure_artifact"] = {
                    "artifact_id": closure_artifact_summary.id,
                    "file_name": closure_artifact_summary.file_name,
                    "plan_id": resolved_plan_id,
                    "created_at": closure_artifact_summary.created_at.isoformat(),
                }
                plan_detail = PlanDetailResponse(**plan_workspace.get_plan(resolved_plan_id))
                closure_message_suffix = " Outcome snapshot saved to plan artifacts."
        except (PlanNotFoundError, ValueError) as exc:
            closure_message_suffix = f" Outcome snapshot could not be written: {exc}"

    updated = recommendation_inbox.update(
        recommendation_id,
        updates={"action_payload": action_payload},
    )

    if plan_detail is None and resolved_plan_id:
        with suppress(Exception):
            plan_detail = PlanDetailResponse(**plan_workspace.get_plan(resolved_plan_id))

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
) -> dict[str, Any]:
    status_filters = _normalize_recommendation_closure_statuses(statuses)
    resolved_plan_id = str(plan_id or "").strip() or None
    rows = recommendation_inbox.list(
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
                "observation_window_days": realized_outcome.get("observation_window_days"),
                "measurement_source": realized_outcome.get("measurement_source"),
            }
        )
        if len(selected_rows) >= max_rows:
            break

    status_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    with_expected_count = 0
    with_realized_count = 0
    measured_count = 0
    direction_match_count = 0
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

    count = len(selected_rows)
    coverage_pct = round((with_realized_count / count) * 100.0, 2) if count else 0.0
    direction_match_rate_pct = round((direction_match_count / measured_count) * 100.0, 2) if measured_count else None
    mean_abs_error = round((future_abs_error_total / measured_count), 2) if measured_count else None
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
        "summary": {
            "closed_count": count,
            "with_expected_count": with_expected_count,
            "with_realized_count": with_realized_count,
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
) -> PlanRecommendationClosureSummaryResponse:
    plan_detail = plan_workspace.get_plan(plan_id)
    analytics_payload = build_recommendation_closure_analytics_payload(
        limit=request.limit,
        statuses=request.statuses,
        include_pending_realized=request.include_pending_realized,
        plan_id=plan_id,
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
        artifact_payload = plan_workspace.write_artifact(
            plan_id=plan_id,
            title=f"Recommendation Closure Analytics ({utc_now().date().isoformat()})",
            markdown=markdown,
            kind="recommendation_closure_analytics",
        )
        artifact_summary = PlanArtifactSummary(**artifact_payload)
        plan_workspace.append_decision(
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


def archive_recommendation(recommendation_id: str, note: str = "") -> RecommendationActionResponse:
    recommendation = recommendation_inbox.set_status(
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
) -> ProfileReadinessSummary:
    filing_status = str(tax_profile.get("filing_status") or "").strip()
    marginal_tax_rate = tax_profile.get("marginal_tax_rate")

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
            status="complete" if filing_status and marginal_tax_rate is not None else "incomplete",
            detail=(
                "Filing status and marginal tax rate are configured."
                if filing_status and marginal_tax_rate is not None
                else "Set filing status and marginal tax rate."
            ),
            required_for=["tax_planning", "investment_fit", "withdrawal_strategy"],
            blocking_recommendations=not (filing_status and marginal_tax_rate is not None),
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


def build_today_dashboard_response() -> TodayDashboardResponse:
    latest_snapshot = None
    try:
        latest_snapshot = snapshot_store.latest()
    except FileNotFoundError:
        latest_snapshot = None

    history = build_snapshot_history_payload(limit=30)
    sync_status = get_sync_status()
    active_plan_detail = resolve_active_plan_detail()
    profile_payload = get_financial_profile_payload()
    onboarding_status = build_onboarding_status_response(
        profile_payload=profile_payload,
        latest_snapshot=latest_snapshot,
        active_plan_detail=active_plan_detail,
    )
    inbox_open_count, inbox_high_priority_count = _build_recommendation_open_counts()

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

    dashboard.command_cards = _build_today_command_cards(dashboard)

    return dashboard


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


# Trend and market-condition rules adapted from Ghostfolio (MIT):
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
) -> dict[str, Any]:
    period_value = str(period or "2y").strip() or "2y"
    interval_value = str(interval or "1d").strip() or "1d"
    sort_value = _normalize_watchlist_sort(sort)
    limit_value = max(1, min(int(limit), 500))
    items_payload = portfolio_store.list_watchlist()
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


def _resolve_context_plan_detail(plan_id: str | None) -> tuple[dict[str, Any] | None, str | None]:
    if plan_id:
        detail = plan_workspace.get_plan(plan_id)
        return detail, str(detail.get("id") or plan_id)

    detail = resolve_active_plan_detail()
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
) -> dict[str, Any]:
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
            resolved_snapshot = await build_live_snapshot()
        else:
            resolved_snapshot = snapshot_store.latest()
        snapshot_summary_payload = summarize_snapshot(resolved_snapshot)
    except FileNotFoundError:
        snapshot_summary_payload = {"note": "No local snapshot yet. Run sync or fetch live snapshot."}
    except Exception as exc:
        snapshot_summary_payload = {"note": f"Snapshot context unavailable: {exc}"}
        warnings.append(str(snapshot_summary_payload["note"]))

    try:
        snapshot_history_payload = build_snapshot_history_payload(limit=30).model_dump(mode="json")
    except Exception as exc:
        snapshot_history_payload = {"note": f"Snapshot history context unavailable: {exc}"}
        warnings.append(str(snapshot_history_payload["note"]))

    try:
        today_dashboard_payload = build_today_dashboard_response().model_dump(mode="json")
    except Exception as exc:
        today_dashboard_payload = {"note": f"Today dashboard context unavailable: {exc}"}
        warnings.append(str(today_dashboard_payload["note"]))

    try:
        financial_profile_payload = FinancialProfileResponse(**get_financial_profile_payload()).model_dump(mode="json")
    except Exception as exc:
        financial_profile_payload = {"note": f"Financial profile context unavailable: {exc}"}
        warnings.append(str(financial_profile_payload["note"]))

    try:
        onboarding_payload = build_onboarding_status_response().model_dump(mode="json")
    except Exception as exc:
        onboarding_payload = {"note": f"Onboarding context unavailable: {exc}"}
        warnings.append(str(onboarding_payload["note"]))

    try:
        watchlist_items = portfolio_store.list_watchlist()
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
        recommendation_rows = _recommendation_list(limit=recommendation_limit, status="proposed")
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
        resolved_plan_detail, resolved_plan_id = _resolve_context_plan_detail(plan_id)
    except PlanNotFoundError as exc:
        warnings.append(str(exc))
    except Exception as exc:
        warnings.append(f"Plan resolution failed: {exc}")

    if isinstance(resolved_plan_detail, dict) and resolved_plan_id:
        try:
            plan_context_payload = plan_workspace.get_context_payload(plan_id=resolved_plan_id)
        except Exception as exc:
            plan_context_payload = {"note": f"Plan context unavailable: {exc}"}
            warnings.append(str(plan_context_payload["note"]))

        try:
            plan_assumption_sets_payload = plan_workspace.get_plan_assumption_sets(resolved_plan_id)
            plan_timeline_payload = plan_workspace.get_plan_timeline(resolved_plan_id)
            plan_contribution_rules_payload = plan_workspace.get_plan_contribution_rules(resolved_plan_id)
            plan_branch_templates_payload = plan_workspace.get_plan_branch_templates(resolved_plan_id)
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
                snapshots=snapshot_store.recent(limit=90),
                transactions=portfolio_store.list_transactions(limit=10_000),
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


async def resolve_snapshots_for_workflow(
    use_live_snapshot: bool,
) -> tuple[PortfolioSnapshot, PortfolioSnapshot | None]:
    if use_live_snapshot:
        current = await build_live_snapshot()
        history = snapshot_store.recent(limit=1)
        previous = history[0] if history else None
        return current, previous

    history = snapshot_store.recent(limit=2)
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
    snapshot = snapshot_store.latest()
    return summarize_snapshot(snapshot)


async def tool_get_live_snapshot(_: dict[str, object]) -> dict[str, object]:
    snapshot = await build_live_snapshot()
    return summarize_snapshot(snapshot)


async def tool_get_snapshot_history(arguments: dict[str, object]) -> dict[str, object]:
    limit_value = arguments.get("limit", 30)
    try:
        limit = max(2, min(int(limit_value), 365))
    except Exception:
        limit = 30
    return build_snapshot_history_payload(limit=limit).model_dump(mode="json")


async def tool_get_today_dashboard(_: dict[str, object]) -> dict[str, object]:
    return build_today_dashboard_response().model_dump(mode="json")


async def tool_get_buildwealth_context(arguments: dict[str, object]) -> dict[str, object]:
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
    )
    return payload


async def tool_get_financial_profile(_: dict[str, object]) -> dict[str, object]:
    profile = FinancialProfileResponse(**get_financial_profile_payload())
    return profile.model_dump(mode="json")


async def tool_get_financial_health(_: dict[str, object]) -> dict[str, object]:
    return get_financial_health().model_dump(mode="json")


async def tool_get_goal_progress(_: dict[str, object]) -> dict[str, object]:
    return get_goal_progress().model_dump(mode="json")


async def tool_simulate_trade(arguments: dict[str, object]) -> dict[str, object]:
    request = SimulateTradeRequest(
        symbol=str(arguments.get("symbol", "")),
        action=str(arguments.get("action", "buy")),
        amount_usd=float(arguments.get("amount_usd", 0)),
        name=arguments.get("name"),
    )
    return simulate_portfolio_trade(request).model_dump(mode="json")


async def tool_assess_portfolio_fit(arguments: dict[str, object]) -> dict[str, object]:
    request = PortfolioFitAssessmentRequest(
        symbol=str(arguments.get("symbol") or ""),
        amount_usd=(
            _coerce_float(arguments.get("amount_usd"), 0.0)
            if arguments.get("amount_usd") is not None
            else None
        ),
        period=str(arguments.get("period") or "6mo"),
        interval=str(arguments.get("interval") or "1d"),
    )
    return build_portfolio_fit_assessment_payload(request).model_dump(mode="json")


async def tool_assess_affordability(arguments: dict[str, object]) -> dict[str, object]:
    request = AffordabilityRequest(
        description=str(arguments.get("description") or ""),
        monthly_amount_usd=arguments.get("monthly_amount_usd"),
        purchase_price_usd=arguments.get("purchase_price_usd"),
        loan_rate_pct=arguments.get("loan_rate_pct"),
        loan_term_years=arguments.get("loan_term_years"),
        down_payment_pct=arguments.get("down_payment_pct"),
    )
    return check_affordability(request).model_dump(mode="json")


async def tool_get_onboarding_status(_: dict[str, object]) -> dict[str, object]:
    return build_onboarding_status_response().model_dump(mode="json")


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


def _build_financial_profile_update_draft(arguments: dict[str, object]) -> dict[str, object]:
    profile_payload = get_financial_profile_payload()
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
    response_payload = {
        **validated.model_dump(mode="json"),
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
    return _build_financial_profile_update_draft(arguments)


async def tool_update_financial_profile(arguments: dict[str, object]) -> dict[str, object]:
    profile_payload = get_financial_profile_payload()

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

    flags = arguments.get("flags")
    if flags is not None:
        if not isinstance(flags, dict):
            raise ValueError("flags must be an object")
        merged_flags = dict(profile_payload.get("flags", {}))
        merged_flags.update(flags)
        profile_payload["flags"] = merged_flags

    validated = FinancialProfileRequest(**profile_payload)
    saved = save_financial_profile_payload(validated)
    return FinancialProfileResponse(**saved).model_dump(mode="json")


async def tool_list_recommendations(arguments: dict[str, object]) -> dict[str, object]:
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
    )
    return {
        "count": len(rows),
        "recommendations": rows,
    }


async def tool_create_recommendation(arguments: dict[str, object]) -> dict[str, object]:
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

    recommendation = recommendation_inbox.create(
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
    symbols = normalize_research_symbols([arguments.get("symbol")], max_symbols=1)
    if not symbols:
        raise ValueError("symbol is required")
    symbol = symbols[0]

    suggested_action_kind = _investment_research_action_kind(arguments.get("suggested_action_kind"))
    priority = _normalized_recommendation_priority(arguments.get("priority"))
    plan_id = str(arguments.get("plan_id") or "").strip() or plan_workspace.get_active_plan_id()
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
    recommendation = recommendation_inbox.create(
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


async def tool_apply_recommendation(arguments: dict[str, object]) -> dict[str, object]:
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
    result = await apply_recommendation_with_decision_packet(recommendation_id, payload)
    return result.model_dump(mode="json")


async def tool_preview_recommendation(arguments: dict[str, object]) -> dict[str, object]:
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
    result = await preview_recommendation(recommendation_id, payload)
    return result.model_dump(mode="json")


async def tool_reject_recommendation(arguments: dict[str, object]) -> dict[str, object]:
    recommendation_id = str(arguments.get("recommendation_id") or "").strip()
    if not recommendation_id:
        raise ValueError("recommendation_id is required")
    reason = str(arguments.get("reason") or "").strip()
    result = await reject_recommendation(
        recommendation_id,
        plan_id=(str(arguments.get("plan_id") or "").strip() or None),
        reason=reason,
        capture_scenario_diff=_coerce_bool(arguments.get("capture_scenario_diff"), True),
        create_decision_packet=_coerce_bool(arguments.get("create_decision_packet"), False),
        decision_packet_research_symbols=(
            [str(item) for item in arguments.get("decision_packet_research_symbols")]
            if isinstance(arguments.get("decision_packet_research_symbols"), list)
            else []
        ),
    )
    return result.model_dump(mode="json")


async def tool_update_recommendation_outcome(arguments: dict[str, object]) -> dict[str, object]:
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
    )
    result = update_recommendation_outcome(recommendation_id, request)
    return result.model_dump(mode="json")


async def tool_get_recommendation_closure_analytics(arguments: dict[str, object]) -> dict[str, object]:
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
    return build_recommendation_closure_analytics_payload(
        **kwargs,
    )


async def tool_create_plan_recommendation_closure_summary(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
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
    response = create_plan_recommendation_closure_summary(
        plan_id=plan_id,
        request=request,
    )
    return response.model_dump(mode="json")


async def tool_pin_watchlist_research_to_plan(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    raw_symbols = arguments.get("symbols")
    symbols: list[str]
    if isinstance(raw_symbols, list):
        symbols = [str(item) for item in raw_symbols]
    elif isinstance(raw_symbols, str):
        symbols = [item.strip() for item in raw_symbols.split(",") if item.strip()]
    else:
        symbols = []

    response = pin_watchlist_research_bridge(
        plan_id=plan_id,
        request=PlanResearchBridgeRequest(
            branch_template_id=(str(arguments.get("branch_template_id") or "").strip() or None),
            template_name=(str(arguments.get("template_name") or "").strip() or None),
            branch_name=(str(arguments.get("branch_name") or "").strip() or None),
            assumption_set_id=(str(arguments.get("assumption_set_id") or "").strip() or None),
            symbols=symbols,
            max_symbols=max(1, min(_coerce_int(arguments.get("max_symbols"), 5), 20)),
        ),
    )
    return response.model_dump(mode="json")


async def tool_run_sync(_: dict[str, object]) -> dict[str, object]:
    return await execute_sync(trigger="copilot-tool")


async def tool_get_sync_status(_: dict[str, object]) -> dict[str, object]:
    return get_sync_status().model_dump(mode="json")


async def tool_run_planning(arguments: dict[str, object]) -> dict[str, object]:
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
        current_value = snapshot_store.latest().total_value_usd

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


def _portfolio_symbol_weights_pct() -> dict[str, float]:
    holdings_payload = portfolio_store.get_holdings()
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
) -> ResearchDossierResponse:
    portfolio_weights_pct = _portfolio_symbol_weights_pct() if include_portfolio_fit else {}

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
            resolved_plan_id = resolve_plan_id_or_active(None)
        except ValueError as exc:
            artifact_warnings.append(f"Dossier not saved to plan: {exc}")

    if resolved_plan_id:
        try:
            artifact_payload = plan_workspace.write_artifact(
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
    ).model_dump(mode="json")
    compare_payload = result.get("compare")
    if isinstance(compare_payload, dict):
        items = compare_payload.get("items")
        if isinstance(items, list):
            compare_payload["items"] = items[:20]
            compare_payload["items_truncated"] = max(0, len(items) - 20)
    return result


async def tool_research_dossier_lookup(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = str(arguments.get("plan_id") or "").strip() or None
    limit = max(1, min(_coerce_int(arguments.get("limit"), 5), 25))
    include_content = _coerce_bool(arguments.get("include_content"), False)
    return build_research_dossier_lookup_payload(
        plan_id=plan_id,
        limit=limit,
        include_content=include_content,
    )


async def tool_research_watchlist_rank(arguments: dict[str, object]) -> dict[str, object]:
    period = str(arguments.get("period", "2y")).strip() or "2y"
    interval = str(arguments.get("interval", "1d")).strip() or "1d"
    limit = max(1, min(_coerce_int(arguments.get("limit"), 100), 500))
    payload = build_portfolio_watchlist_payload(
        period=period,
        interval=interval,
        sort="ranked",
        limit=limit,
    )
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
    use_live_snapshot = _coerce_bool(arguments.get("use_live_snapshot"), False)
    include_holdings = _coerce_bool(arguments.get("include_holdings"), False)
    holdings_limit_per_account = max(1, min(_coerce_int(arguments.get("holdings_limit_per_account"), 8), 25))

    if use_live_snapshot:
        await build_live_snapshot()

    holdings_payload = portfolio_store.get_holdings()
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
    use_live_snapshot = _coerce_bool(arguments.get("use_live_snapshot"), False)
    dimension = str(arguments.get("dimension") or "asset_class").strip().lower()
    if dimension not in {"asset_class", "sector", "region", "all"}:
        raise ValueError("dimension must be one of: asset_class, sector, region, all")
    top_n = max(1, min(_coerce_int(arguments.get("top_n"), 10), 100))

    if use_live_snapshot:
        await build_live_snapshot()

    holdings_payload = portfolio_store.get_holdings()
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
    accounts = portfolio_store.get_accounts()
    return {"count": len(accounts), "accounts": accounts}


async def tool_list_plans(arguments: dict[str, object]) -> dict[str, object]:
    limit_value = arguments.get("limit", 20)
    try:
        limit = max(1, min(int(limit_value), 200))
    except Exception:
        limit = 20
    plans = plan_workspace.list_plans(limit=limit)
    return {"count": len(plans), "plans": plans}


async def tool_get_plan_context(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = arguments.get("plan_id")
    resolved = str(plan_id).strip() if isinstance(plan_id, str) and plan_id.strip() else None
    return plan_workspace.get_context_payload(plan_id=resolved)


async def tool_get_plan_settings(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    detail = plan_workspace.get_plan(plan_id)
    return {
        "plan_id": plan_id,
        "title": detail.get("title"),
        "settings": detail.get("settings", {}),
        "updated_at": detail.get("updated_at"),
    }


async def tool_update_plan_settings(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    updates = extract_plan_settings_updates(arguments)
    rationale = str(arguments.get("rationale") or "").strip()
    status = str(arguments.get("status") or "accepted").strip().lower() or "accepted"

    detail = plan_workspace.update_plan_settings(
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    timeline = plan_workspace.get_plan_timeline(plan_id)
    return {
        "plan_id": plan_id,
        "timeline": timeline,
    }


async def tool_update_plan_timeline(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    timeline_raw = arguments.get("timeline")
    if not isinstance(timeline_raw, dict):
        raise ValueError("timeline must be an object with events and optional retirement fields.")

    timeline = plan_workspace.update_plan_timeline(
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))

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

    timeline_payload = plan_workspace.get_plan_timeline(plan_id)
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

    timeline = plan_workspace.update_plan_timeline(
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    contribution_rules = plan_workspace.get_plan_contribution_rules(plan_id)
    return {
        "plan_id": plan_id,
        "contribution_rules": contribution_rules,
    }


async def tool_set_contribution_rules(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))

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
            build_planning_accounts_from_portfolio(),
            employer_match_target_usd=employer_match_target_usd,
        )
        if not isinstance(payload.get("base_rule"), dict):
            payload["base_rule"] = generated.get("base_rule", {"type": "save"})
        if not isinstance(payload.get("rules"), list) or not payload.get("rules"):
            payload["rules"] = generated.get("rules", [])
        if not payload.get("profile_id"):
            payload["profile_id"] = generated.get("profile_id", "tax_optimized_high_earner")

    contribution_rules = plan_workspace.update_plan_contribution_rules(
        plan_id=plan_id,
        contribution_rules_payload=payload,
        rationale=str(arguments.get("rationale") or "").strip() or "Updated via copilot tool.",
        status=str(arguments.get("status") or "accepted").strip().lower() or "accepted",
        log_decision=True,
    )

    allocation_preview: dict[str, Any] | None = None
    allocation_warning: str | None = None
    try:
        detail = plan_workspace.get_plan(plan_id)
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    detail = plan_workspace.get_plan(plan_id)
    if not isinstance(detail, dict):
        raise ValueError(f"Plan not found: {plan_id}")

    current_portfolio_value_raw = arguments.get("current_portfolio_value_usd")
    current_portfolio_value = resolve_portfolio_value(
        float(current_portfolio_value_raw) if current_portfolio_value_raw is not None else None
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
    if include_raw_results:
        response["raw_results"] = raw_results
    return response


async def tool_get_plan_assumption_sets(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    assumption_sets = plan_workspace.get_plan_assumption_sets(plan_id)
    return {
        "plan_id": plan_id,
        "assumption_sets": assumption_sets,
    }


async def tool_update_plan_assumption_sets(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    payload_raw = arguments.get("assumption_sets")
    if not isinstance(payload_raw, dict):
        raise ValueError("assumption_sets must be an object with active_assumption_set_id and sets.")

    assumption_sets = plan_workspace.update_plan_assumption_sets(
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    branch_templates = plan_workspace.get_plan_branch_templates(plan_id)
    return {
        "plan_id": plan_id,
        "branch_templates": branch_templates,
    }


async def tool_update_plan_branch_templates(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    payload_raw = arguments.get("branch_templates")
    if not isinstance(payload_raw, dict):
        raise ValueError("branch_templates must be an object with default_template_id and templates.")

    branch_templates = plan_workspace.update_plan_branch_templates(
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    detail = plan_workspace.get_plan(plan_id)
    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = snapshot_store.recent(limit=90)
    transactions = portfolio_store.list_transactions(limit=10_000)
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    detail = plan_workspace.get_plan(plan_id)
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
        float(current_value_raw) if current_value_raw is not None else None
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
        updated = plan_workspace.update_plan_settings(
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
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
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
    )


async def tool_append_plan_decision(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = str(arguments.get("plan_id") or "").strip()
    summary = str(arguments.get("summary") or "").strip()
    rationale = str(arguments.get("rationale") or "").strip()
    status = str(arguments.get("status") or "proposed").strip().lower()

    if not plan_id:
        active_payload = plan_workspace.get_context_payload()
        plan_id = str(active_payload.get("id") or "").strip()

    if not plan_id:
        raise ValueError("No active plan is configured and no plan_id was provided.")

    decision = plan_workspace.append_decision(
        plan_id=plan_id,
        summary=summary,
        rationale=rationale,
        status=status or "proposed",
    )
    return {"plan_id": plan_id, "decision": decision}


async def tool_list_workflow_templates(_: dict[str, object]) -> dict[str, object]:
    templates = workflow_runner.templates()
    return {"count": len(templates), "templates": templates}


async def tool_run_workflow(arguments: dict[str, object]) -> dict[str, object]:
    workflow_id = str(arguments.get("workflow_id") or "").strip()
    if not workflow_id:
        raise ValueError("workflow_id is required")

    use_live_snapshot = bool(arguments.get("use_live_snapshot", False))
    params_value = arguments.get("params")
    params = params_value if isinstance(params_value, dict) else {}

    snapshot, previous_snapshot = await resolve_snapshots_for_workflow(
        use_live_snapshot=use_live_snapshot
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
        active_id = plan_workspace.get_active_plan_id()
        plan_id = active_id or ""

    save_to_plan = bool(arguments.get("save_to_plan", True))
    if save_to_plan and plan_id:
        artifact = plan_workspace.write_artifact(
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
        description="Fetch a live portfolio snapshot from Ghostfolio and summarize it.",
        parameters=empty_schema,
        handler=tool_get_live_snapshot,
    )
    copilot.register_tool(
        name="get_snapshot_history",
        description="Read historical local snapshots and summarize trend deltas across a time window.",
        parameters={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "additionalProperties": False,
        },
        handler=tool_get_snapshot_history,
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
            "physical_assets, tax_profile, flags, and notes. Only use after explicit user confirmation."
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
            "Record realized outcomes for an applied/rejected recommendation and compute expected-vs-realized deltas."
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
        description="Read sync engine status, counters, and latest run timestamps.",
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
        description="List known Ghostfolio accounts with balances and metadata.",
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
        name="append_plan_decision",
        description=(
            "Append a decision entry to plan history. "
            "Fields: summary (required), optional plan_id, rationale, status."
        ),
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string"},
                "summary": {"type": "string"},
                "rationale": {"type": "string"},
                "status": {"type": "string"},
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


@app.get("/api/storage/durable/status", response_model=DurableStorageStatusResponse)
def get_durable_storage_status() -> DurableStorageStatusResponse:
    return DurableStorageStatusResponse.model_validate(durable_storage_service.get_status())


@app.post("/api/storage/durable/migrate", response_model=DurableStorageMigrationResponse)
def migrate_durable_storage(
    request: DurableStorageMigrationRequest,
) -> DurableStorageMigrationResponse:
    try:
        report = durable_storage_service.run_upgrade(run_rollback_check=request.run_rollback_check)
    except DurableStorageMigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DurableStorageMigrationResponse.model_validate(report)


@app.post("/api/storage/durable/rollback", response_model=DurableStorageRollbackResponse)
def rollback_durable_storage(
    request: DurableStorageRollbackRequest,
) -> DurableStorageRollbackResponse:
    try:
        report = durable_storage_service.rollback_latest_migration(migration_id=request.migration_id)
    except DurableStorageMigrationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DurableStorageMigrationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DurableStorageRollbackResponse.model_validate(report)


@app.get("/api/storage/backups", response_model=BackupListResponse)
def list_backups() -> BackupListResponse:
    return BackupListResponse.model_validate(backup_restore_service.list_backups())


@app.post("/api/storage/backups", response_model=BackupCreateResponse)
def create_backup(request: BackupCreateRequest) -> BackupCreateResponse:
    try:
        report = backup_restore_service.create_backup(reason=request.reason)
    except BackupRestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BackupCreateResponse.model_validate(report)


@app.post("/api/storage/backups/restore", response_model=BackupRestoreResponse)
def restore_backup(request: BackupRestoreRequest) -> BackupRestoreResponse:
    try:
        report = backup_restore_service.restore_backup(
            backup_id=request.backup_id,
            create_pre_restore_backup=request.create_pre_restore_backup,
        )
    except BackupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BackupRestoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BackupRestoreResponse.model_validate(report)


@app.get("/api/storage/protection/status", response_model=StorageProtectionStatusResponse)
def get_storage_protection_status() -> StorageProtectionStatusResponse:
    return StorageProtectionStatusResponse.model_validate(data_protection_service.get_status())


@app.put("/api/storage/protection/policy", response_model=StorageProtectionPolicyResponse)
def update_storage_protection_policy(
    request: StorageProtectionPolicyUpdateRequest,
) -> StorageProtectionPolicyResponse:
    try:
        policy = data_protection_service.update_policy(request.model_dump(exclude_none=True))
    except DataProtectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("protection_policy_updated")
    return StorageProtectionPolicyResponse.model_validate(policy)


@app.post("/api/storage/protection/apply", response_model=StorageProtectionApplyResponse)
def apply_storage_protection(
    request: StorageProtectionApplyRequest,
) -> StorageProtectionApplyResponse:
    try:
        report = data_protection_service.apply_protection(request.model_dump(exclude_none=True))
    except DataProtectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageProtectionApplyResponse.model_validate(report)


@app.get("/api/git/policy", response_model=GitPolicyResponse)
def get_git_policy() -> GitPolicyResponse:
    return GitPolicyResponse.model_validate(_git_policy())


@app.put("/api/git/policy", response_model=GitPolicyResponse)
def update_git_policy(request: GitPolicyUpdateRequest) -> GitPolicyResponse:
    policy = git_integration_settings_store.save(request.model_dump(exclude_none=True))
    return GitPolicyResponse.model_validate(policy)


@app.post("/api/git/init", response_model=GitInitResponse)
def initialize_git_repository() -> GitInitResponse:
    policy = _git_policy()
    try:
        result = _git_checkpoint_service(policy).initialize(_git_workspace_policy(policy))
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store().record(
        event_type="repository_initialized",
        title="Git repository initialized",
        message=str(result.get("message") or ""),
        status=str(result.get("status") or "initialized"),
        metadata={"workspace_dir": result.get("workspace_dir")},
    )
    return GitInitResponse.model_validate(result)


@app.get("/api/git/status", response_model=GitStatusResponse)
def get_git_status() -> GitStatusResponse:
    policy = _git_policy()
    try:
        status = _git_repository_service(policy).status()
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitStatusResponse.model_validate(status)


@app.get("/api/git/history", response_model=GitHistoryResponse)
def get_git_history(limit: int = 20) -> GitHistoryResponse:
    policy = _git_policy()
    try:
        commits = _git_repository_service(policy).history(limit=limit)
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitHistoryResponse.model_validate({"commits": commits})


@app.get("/api/git/diff", response_model=GitDiffResponse)
def get_git_diff(
    ref: str | None = None,
    path: str | None = None,
    max_chars: int = 200_000,
) -> GitDiffResponse:
    policy = _git_policy()
    try:
        diff = _git_repository_service(policy).diff(ref=ref, path=path, max_chars=max_chars)
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GitDiffResponse.model_validate(diff)


@app.get("/api/git/restore-preview", response_model=GitRestorePreviewResponse)
def get_git_restore_preview(
    ref: str,
    path: str | None = None,
    max_chars: int = 120_000,
) -> GitRestorePreviewResponse:
    policy = _git_policy()
    try:
        _versioned_workspace_service(policy).materialize(_git_workspace_policy(policy))
        preview = _git_repository_service(policy).restore_preview(
            ref=ref,
            path=path,
            max_chars=max_chars,
        )
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    token = _git_restore_preview_token_store().create(preview=preview)
    preview["preview_token"] = token["token"]
    preview["preview_expires_at"] = token["expires_at"]
    _git_activity_store().record(
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
def apply_git_restore(request: GitRestoreApplyRequest) -> GitRestoreApplyResponse:
    policy = _git_policy()
    try:
        if request.preview_token:
            token_store = _git_restore_preview_token_store()
            token_payload = token_store.get(request.preview_token)
            preview_path = token_payload.get("path") if isinstance(token_payload, dict) else None
            _versioned_workspace_service(policy).materialize(_git_workspace_policy(policy))
            current_preview = _git_repository_service(policy).restore_preview(
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
        result = _git_restore_apply_service(policy).apply(
            ref=request.ref,
            paths=request.paths,
            confirmation=request.confirmation,
            rationale=request.rationale,
            create_checkpoint_before_apply=request.create_checkpoint_before_apply,
            create_checkpoint_after_apply=request.create_checkpoint_after_apply,
        )
    except (GitRepositoryError, GitRestoreApplyError, GitRestorePreviewTokenError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store().record(
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
def create_git_checkpoint(request: GitCheckpointRequest) -> GitCheckpointResponse:
    policy = _git_policy()
    try:
        result = _git_checkpoint_service(policy).checkpoint(
            policy=_git_workspace_policy(policy),
            event_type=request.event_type,
            message=request.message,
        )
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store().record(
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
def get_git_autogit_state() -> GitAutoGitStateResponse:
    policy = _git_policy()
    state = _git_autogit_service(policy).state(policy=policy)
    return GitAutoGitStateResponse.model_validate(state)


@app.post("/api/git/autogit/run-due", response_model=GitAutoGitStateResponse)
def run_due_git_autogit() -> GitAutoGitStateResponse:
    state = _run_due_autogit()
    return GitAutoGitStateResponse.model_validate(state)


@app.get("/api/git/activity", response_model=GitActivityResponse)
def get_git_activity(
    limit: int = 50,
    event_type: str | None = None,
    status: str | None = None,
    ref: str | None = None,
    search: str | None = None,
) -> GitActivityResponse:
    result = _git_activity_store().query(
        limit=limit,
        event_type=event_type,
        status=status,
        ref=ref,
        search=search,
    )
    return GitActivityResponse.model_validate(result)


@app.post("/api/git/activity/cleanup", response_model=GitActivityCleanupResponse)
def cleanup_git_activity(request: GitActivityCleanupRequest) -> GitActivityCleanupResponse:
    try:
        result = _git_activity_store().cleanup(
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
def connect_git_remote(request: GitRemoteConnectRequest) -> GitRemoteOperationResponse:
    policy = _git_policy()
    try:
        result = _git_repository_service(policy).connect_remote(
            remote_url=request.remote_url,
            name=request.remote_name,
        )
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store().record(
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
def push_git_remote(request: GitRemoteOperationRequest) -> GitRemoteOperationResponse:
    policy = _git_policy()
    try:
        result = _git_repository_service(policy).push(remote_name=request.remote_name)
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store().record(
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
def pull_git_remote(request: GitRemoteOperationRequest) -> GitRemoteOperationResponse:
    policy = _git_policy()
    try:
        result = _git_repository_service(policy).pull(remote_name=request.remote_name)
    except GitRepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _git_activity_store().record(
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


@app.get("/api/settings")
def get_user_settings() -> dict[str, Any]:
    return user_settings_store.load_masked()


@app.put("/api/settings")
def update_user_settings(request: dict[str, Any]) -> dict[str, Any]:
    global openai_tool_client

    saved = user_settings_store.save(request)

    # Hot-reload affected services
    if saved.get("openai_api_key"):
        openai_tool_client = OpenAIChatToolClient(
            api_key=saved["openai_api_key"],
            model=saved.get("openai_model") or settings.openai_model,
            base_url=saved.get("openai_base_url") or settings.openai_base_url,
        )
        copilot.llm_client = openai_tool_client

    return user_settings_store.load_masked()


async def on_startup() -> None:
    settings.import_inbox_dir.mkdir(parents=True, exist_ok=True)
    settings.import_archive_dir.mkdir(parents=True, exist_ok=True)
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

    global scheduler_task, engine_health_task, autogit_task
    await engine_status_tracker.probe_all()

    if settings.sync_interval_minutes > 0:
        scheduler_task = asyncio.create_task(scheduled_sync_loop())
    if settings.engine_health_probe_interval_seconds > 0:
        engine_health_task = asyncio.create_task(engine_probe_loop())
    autogit_task = asyncio.create_task(autogit_checkpoint_loop())


async def on_shutdown() -> None:
    global scheduler_task, engine_health_task, autogit_task
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        scheduler_task = None

    if engine_health_task is not None:
        engine_health_task.cancel()
        with suppress(asyncio.CancelledError):
            await engine_health_task
        engine_health_task = None

    if autogit_task is not None:
        autogit_task.cancel()
        with suppress(asyncio.CancelledError):
            await autogit_task
        autogit_task = None


@app.get("/", include_in_schema=False)
def ui_root() -> Response:
    index_file = web_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return HTMLResponse(
        "<h1>BuildWealth UI not found</h1><p>Expected index.html in orchestrator web directory.</p>",
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/engines/status", response_model=EngineStatusResponse)
async def get_engine_status(refresh: bool = False) -> EngineStatusResponse:
    if refresh:
        await engine_status_tracker.probe_all()
    return await engine_status_tracker.snapshot()


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
def today_dashboard() -> TodayDashboardResponse:
    return build_today_dashboard_response()


@app.post("/api/dashboard/today/research-readiness/refresh", response_model=TodayDashboardResponse)
def refresh_today_research_readiness() -> TodayDashboardResponse:
    today_research_evidence_cache.clear()
    return build_today_dashboard_response()


@app.get("/api/financial-profile", response_model=FinancialProfileResponse)
def get_financial_profile() -> FinancialProfileResponse:
    return FinancialProfileResponse(**get_financial_profile_payload())


@app.put("/api/financial-profile", response_model=FinancialProfileResponse)
def update_financial_profile(request: FinancialProfileRequest) -> FinancialProfileResponse:
    saved = save_financial_profile_payload(request)
    _queue_autogit_event("financial_profile_updated")
    return FinancialProfileResponse(**saved)


@app.get("/api/onboarding/status", response_model=OnboardingStatusResponse)
def onboarding_status() -> OnboardingStatusResponse:
    return build_onboarding_status_response()


@app.get("/api/financial-health", response_model=FinancialHealthResponse)
def get_financial_health() -> FinancialHealthResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem, PhysicalAssetItem

    profile = financial_profile_store.load()
    try:
        snap = snapshot_store.latest()
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
def check_affordability(request: AffordabilityRequest) -> AffordabilityResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, IncomeItem

    profile = financial_profile_store.load()
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
) -> dict[str, Any]:
    """Upload a bank/credit card CSV statement and get expense/income suggestions."""
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


@app.post("/api/import/statement/apply")
def apply_statement_suggestions(request: dict[str, Any]) -> dict[str, Any]:
    """Apply selected expense/income suggestions to the financial profile."""
    profile = financial_profile_store.load()
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

    financial_profile_store.save(profile)

    return {
        "added_expenses": added_expenses,
        "added_income": added_income,
        "total_expense_items": len(profile.get("expense_items", [])),
        "total_income_items": len(profile.get("income_items", [])),
    }


@app.get("/api/portfolio/holdings")
def get_portfolio_holdings() -> dict[str, Any]:
    return portfolio_store.get_holdings()


@app.get("/api/portfolio/transactions")
def get_portfolio_transactions(limit: int = 200) -> list[dict[str, Any]]:
    return portfolio_store.list_transactions(limit=limit)


@app.post("/api/portfolio/transactions")
def add_portfolio_transaction(request: dict[str, Any]) -> dict[str, Any]:
    return portfolio_store.add_transaction(
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
def delete_portfolio_transaction(transaction_id: str) -> dict[str, Any]:
    deleted = portfolio_store.delete_transaction(transaction_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return {"deleted": True, "id": transaction_id}


@app.post("/api/portfolio/refresh-prices")
async def refresh_portfolio_prices() -> dict[str, Any]:
    holdings_data = await refresh_portfolio(portfolio_store, research_service)
    snapshot = build_snapshot_from_holdings(holdings_data)
    snapshot_store.write(snapshot)
    return {
        "total_value": holdings_data.get("total_value", 0),
        "holdings_count": len(holdings_data.get("holdings", {})),
        "prices_updated_at": holdings_data.get("prices_updated_at"),
    }


@app.get("/api/portfolio/benchmark", response_model=PortfolioBenchmarkResponse)
async def get_portfolio_benchmark(symbols: str | None = None, limit: int = 180) -> PortfolioBenchmarkResponse:
    resolved_symbols = parse_benchmark_symbols(
        symbols,
        default_symbols=settings.portfolio_benchmark_default_symbols,
    )
    if not resolved_symbols:
        raise HTTPException(status_code=400, detail="At least one benchmark symbol is required.")

    bounded_limit = max(2, min(int(limit), 3650))
    try:
        guard_reason = await sidecar_contract_guard_reason("ghostfolio_benchmark")
        result = await benchmark_service.compare(
            benchmark_symbols=resolved_symbols,
            limit=bounded_limit,
            sidecar_guard_reason=guard_reason,
        )
        if result.engine_status == "degraded":
            await engine_status_tracker.increment_degraded(
                "ghostfolio_benchmark",
                reason=result.warnings[0] if result.warnings else None,
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/portfolio/attribution", response_model=PortfolioAttributionResponse)
async def get_portfolio_attribution(top_n: int = 5) -> PortfolioAttributionResponse:
    bounded_top_n = max(1, min(int(top_n), 50))
    try:
        guard_reason = await sidecar_contract_guard_reason("ghostfolio_attribution")
        result = await attribution_service.analyze(
            top_n=bounded_top_n,
            sidecar_guard_reason=guard_reason,
        )
        if result.engine_status == "degraded":
            await engine_status_tracker.increment_degraded(
                "ghostfolio_attribution",
                reason=result.warnings[0] if result.warnings else None,
            )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/portfolio/accounts")
def get_portfolio_accounts() -> list[dict[str, Any]]:
    return portfolio_store.get_accounts()


@app.post("/api/portfolio/accounts")
def add_portfolio_account(request: dict[str, Any]) -> dict[str, Any]:
    name = str(request.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Account name is required.")
    return portfolio_store.add_account(
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
) -> WatchlistRankResponse:
    payload = build_portfolio_watchlist_payload(
        period=period,
        interval=interval,
        sort=sort,
        limit=limit,
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
def upsert_portfolio_watchlist_item(request: dict[str, Any]) -> dict[str, Any]:
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

    try:
        item = portfolio_store.upsert_watchlist_item(
            symbol=symbol,
            data_source=str(request.get("data_source") or "OPENBB"),
            note=request.get("note"),
            thesis=request.get("thesis"),
            target_price_usd=target_price_value,
            tags=request.get("tags"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@app.delete("/api/portfolio/watchlist/{symbol}")
def delete_portfolio_watchlist_item(symbol: str, data_source: str | None = None) -> dict[str, Any]:
    deleted = portfolio_store.delete_watchlist_item(symbol, data_source=data_source)
    if not deleted:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    return {
        "deleted": True,
        "symbol": str(symbol or "").strip().upper(),
        "data_source": str(data_source or "").strip().upper() or None,
    }


@app.get("/api/portfolio/risk-policy")
def get_portfolio_risk_policy() -> dict[str, Any]:
    return portfolio_store.get_risk_policy()


@app.put("/api/portfolio/risk-policy")
def set_portfolio_risk_policy(request: dict[str, Any]) -> dict[str, Any]:
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
    return portfolio_store.set_risk_policy_thresholds(updates=updates)


@app.post("/api/portfolio/review-packets", response_model=PortfolioReviewPacketResponse)
def create_portfolio_review_packet(request: PortfolioReviewPacketRequest) -> PortfolioReviewPacketResponse:
    plan_detail: dict[str, Any] | None = None
    if request.plan_id:
        try:
            plan_detail = plan_workspace.get_plan(request.plan_id)
        except PlanNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    holdings_payload = portfolio_store.get_holdings()
    transactions = portfolio_store.list_transactions(limit=request.include_transactions_limit)
    snapshots = snapshot_store.recent(limit=request.include_snapshot_history_limit)
    watchlist_items = portfolio_store.list_watchlist()
    recommendations = recommendation_inbox.list(
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
    summary_payload = portfolio_review_packet_store.write(
        packet_payload=packet,
        markdown=markdown,
        title=resolved_title,
    )

    plan_artifact: PlanArtifactSummary | None = None
    if request.plan_id and request.save_to_plan_artifacts:
        try:
            artifact_payload = plan_workspace.write_artifact(
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
        stored = portfolio_review_packet_store.read(str(summary_payload.get("packet_id") or ""))
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


@app.get("/api/portfolio/review-packets", response_model=PortfolioReviewPacketListResponse)
def list_portfolio_review_packets(limit: int = 20) -> PortfolioReviewPacketListResponse:
    items = portfolio_review_packet_store.list(limit=max(1, min(int(limit), 200)))
    return PortfolioReviewPacketListResponse(items=items)


@app.get("/api/portfolio/review-packets/{packet_id}", response_model=PortfolioReviewPacketResponse)
def get_portfolio_review_packet(packet_id: str) -> PortfolioReviewPacketResponse:
    try:
        payload = portfolio_review_packet_store.read(packet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PortfolioReviewPacketResponse(
        summary=payload["summary"],
        packet=payload["packet"],
        markdown=payload["markdown"],
    )


@app.get("/api/portfolio/cost-basis-methods")
def get_portfolio_cost_basis_methods() -> dict[str, Any]:
    return portfolio_store.get_cost_basis_methods()


@app.put("/api/portfolio/cost-basis-methods")
def set_portfolio_cost_basis_method(request: dict[str, Any]) -> dict[str, Any]:
    method = str(request.get("method") or "").strip().upper()
    if not method:
        raise HTTPException(status_code=400, detail="method is required")
    try:
        return portfolio_store.set_cost_basis_method(
            method=method,
            account=request.get("account"),
            symbol=request.get("symbol"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/portfolio/manual-prices")
def get_portfolio_manual_prices() -> dict[str, Any]:
    return portfolio_store.get_manual_prices()


@app.put("/api/portfolio/manual-prices")
def set_portfolio_manual_price(request: dict[str, Any]) -> dict[str, Any]:
    symbol = str(request.get("symbol") or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="symbol is required")
    try:
        price = float(request.get("price"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="price must be a number") from exc
    note = str(request.get("note") or "")
    try:
        return portfolio_store.set_manual_price(symbol=symbol, price=price, note=note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/portfolio/manual-prices/{symbol}")
def clear_portfolio_manual_price(symbol: str) -> dict[str, Any]:
    deleted = portfolio_store.clear_manual_price(symbol)
    if not deleted:
        raise HTTPException(status_code=404, detail="Manual price override not found.")
    return {"deleted": True, "symbol": str(symbol).upper()}


@app.get("/api/portfolio/fx-rates")
def get_portfolio_fx_rates() -> dict[str, Any]:
    return portfolio_store.get_fx_rates()


@app.get("/api/portfolio/fx-rates/history")
def get_portfolio_fx_rate_history() -> dict[str, Any]:
    return portfolio_store.get_fx_rates_history()


@app.put("/api/portfolio/fx-rates")
def set_portfolio_fx_rate(request: dict[str, Any]) -> dict[str, Any]:
    currency = str(request.get("currency") or "").strip().upper()
    if not currency:
        raise HTTPException(status_code=400, detail="currency is required")
    try:
        rate = float(request.get("rate"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="rate must be a number") from exc
    base_currency = request.get("base_currency")
    try:
        return portfolio_store.set_fx_rate(
            currency=currency,
            rate=rate,
            base_currency=str(base_currency).strip().upper() if base_currency is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/portfolio/fx-rates/history")
def set_portfolio_fx_rate_history(request: dict[str, Any]) -> dict[str, Any]:
    currency = str(request.get("currency") or "").strip().upper()
    if not currency:
        raise HTTPException(status_code=400, detail="currency is required")
    rates_by_date = request.get("rates_by_date")
    if not isinstance(rates_by_date, dict):
        raise HTTPException(status_code=400, detail="rates_by_date must be an object of date->rate")
    base_currency = request.get("base_currency")
    try:
        return portfolio_store.set_fx_rate_history(
            currency=currency,
            rates_by_date=rates_by_date,
            base_currency=str(base_currency).strip().upper() if base_currency is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/portfolio/fx-rates/{currency}")
def clear_portfolio_fx_rate(currency: str) -> dict[str, Any]:
    deleted = portfolio_store.clear_fx_rate(currency)
    if not deleted:
        raise HTTPException(status_code=404, detail="FX rate not found or cannot clear base currency.")
    return {"deleted": True, "currency": str(currency).upper()}


@app.get("/api/portfolio/custom-assets")
def get_portfolio_custom_assets() -> list[dict[str, Any]]:
    return portfolio_store.list_custom_assets()


@app.post("/api/portfolio/custom-assets")
def create_portfolio_custom_asset(request: dict[str, Any]) -> dict[str, Any]:
    name = str(request.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        value = float(request.get("value"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="value must be a number") from exc

    try:
        return portfolio_store.create_custom_asset(
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
def simulate_portfolio_trade(request: SimulateTradeRequest) -> SimulateTradeResponse:
    try:
        snap = snapshot_store.latest()
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
) -> PortfolioFitAssessmentResponse:
    if not request.symbol:
        raise ValueError("Portfolio-fit assessment requires a symbol.")
    try:
        snap = snapshot_store.latest()
    except FileNotFoundError:
        snap = None

    holdings_payload: dict[str, Any] = {}
    try:
        holdings_payload = portfolio_store.get_holdings()
    except Exception:
        holdings_payload = {}

    profile_payload = get_financial_profile_payload()
    profile_readiness = _build_profile_readiness_summary(
        income_items=profile_payload.get("income_items") if isinstance(profile_payload.get("income_items"), list) else [],
        expense_items=profile_payload.get("expense_items") if isinstance(profile_payload.get("expense_items"), list) else [],
        debt_items=profile_payload.get("debt_items") if isinstance(profile_payload.get("debt_items"), list) else [],
        goal_items=profile_payload.get("goal_items") if isinstance(profile_payload.get("goal_items"), list) else [],
        physical_assets=profile_payload.get("physical_assets") if isinstance(profile_payload.get("physical_assets"), list) else [],
        flags=profile_payload.get("flags") if isinstance(profile_payload.get("flags"), dict) else {},
        tax_profile=profile_payload.get("tax_profile") if isinstance(profile_payload.get("tax_profile"), dict) else {},
    )

    emergency_fund_months: float | None = None
    try:
        emergency_fund_months = get_financial_health().emergency_fund_months
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
        evidence_packet=evidence_packet,
        snapshot=snap,
        holdings_payload=holdings_payload,
        profile_readiness_payload=profile_readiness.model_dump(mode="json"),
        emergency_fund_months=emergency_fund_months,
        active_plan_detail=resolve_active_plan_detail(),
    )


@app.post("/api/portfolio/fit-assessment", response_model=PortfolioFitAssessmentResponse)
def portfolio_fit_assessment(request: PortfolioFitAssessmentRequest) -> PortfolioFitAssessmentResponse:
    try:
        return build_portfolio_fit_assessment_payload(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/goals/progress", response_model=GoalProgressResponse)
def get_goal_progress() -> GoalProgressResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem

    profile = financial_profile_store.load()
    try:
        snap = snapshot_store.latest()
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
) -> list[RecommendationItem]:
    rows = _recommendation_list(
        limit=limit,
        status=status,
        plan_id=plan_id,
        include_archived=include_archived,
        sort=sort,
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
) -> RecommendationFactoryResponse:
    holdings_payload = portfolio_store.get_holdings()
    existing_recommendations = recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_portfolio_risk_recommendations(
        holdings_payload=holdings_payload,
        existing_recommendations=existing_recommendations,
        creator=recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("portfolio_risk_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/plan-tracking", response_model=RecommendationFactoryResponse)
def generate_plan_tracking_recommendation_candidates(
    request: PlanTrackingRecommendationGenerateRequest,
) -> RecommendationFactoryResponse:
    try:
        plan_id = resolve_plan_id_or_active(request.plan_id)
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = snapshot_store.recent(limit=90)
    transactions = portfolio_store.list_transactions(limit=10_000)
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
    existing_recommendations = recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_plan_tracking_recommendations(
        plan_tracking_payload=tracking_payload,
        existing_recommendations=existing_recommendations,
        creator=recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("plan_tracking_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/cash-liquidity", response_model=RecommendationFactoryResponse)
def generate_cash_liquidity_recommendation_candidates(
    request: CashLiquidityRecommendationGenerateRequest,
) -> RecommendationFactoryResponse:
    holdings_payload = portfolio_store.get_holdings()
    financial_profile_payload = get_financial_profile_payload()
    existing_recommendations = recommendation_inbox.list(
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
        creator=recommendation_inbox if not request.dry_run else None,
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
) -> RecommendationFactoryResponse:
    profile_payload = get_financial_profile_payload()
    profile_readiness = build_onboarding_status_response(
        profile_payload=profile_payload,
        load_fallbacks=False,
    ).profile_readiness
    existing_recommendations = recommendation_inbox.list(
        limit=None,
        status=None,
        plan_id=None,
        include_archived=True,
        sort="none",
    )
    result = generate_profile_completeness_recommendations(
        profile_readiness_payload=profile_readiness.model_dump(mode="json") if profile_readiness else {},
        existing_recommendations=existing_recommendations,
        creator=recommendation_inbox if not request.dry_run else None,
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
) -> RecommendationFactoryResponse:
    try:
        plan_id = resolve_plan_id_or_active(request.plan_id)
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = snapshot_store.recent(limit=90)
    transactions = portfolio_store.list_transactions(limit=10_000)
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

    profile_payload = get_financial_profile_payload()
    profile_readiness = build_onboarding_status_response(
        profile_payload=profile_payload,
        latest_snapshot=None,
        active_plan_detail=detail,
        load_fallbacks=False,
    ).profile_readiness
    existing_recommendations = recommendation_inbox.list(
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
        creator=recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("stale_assumption_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/watchlist-research", response_model=RecommendationFactoryResponse)
def generate_watchlist_research_recommendation_candidates(
    request: WatchlistResearchRecommendationGenerateRequest,
) -> RecommendationFactoryResponse:
    try:
        watchlist_payload = build_portfolio_watchlist_payload(
            period=request.period,
            interval=request.interval,
            limit=request.limit,
            sort="ranked",
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
                PortfolioFitAssessmentRequest(symbol=symbol, period=request.period, interval=request.interval)
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

    existing_recommendations = recommendation_inbox.list(
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
        creator=recommendation_inbox if not request.dry_run else None,
        dry_run=request.dry_run,
        plan_id=request.plan_id,
        limit=request.limit,
    )
    if not request.dry_run and result.created:
        _queue_autogit_event("watchlist_research_recommendations_generated")
    return RecommendationFactoryResponse(**result.to_dict())


@app.post("/api/recommendations/generate/run-all", response_model=RecommendationFactoryRunAllResponse)
def run_all_recommendation_factories(
    request: RecommendationFactoryRunAllRequest,
) -> RecommendationFactoryRunAllResponse:
    factories: dict[str, RecommendationFactoryResponse] = {}
    errors: list[dict[str, Any]] = []

    try:
        factories["portfolio_risk"] = generate_portfolio_risk_recommendation_candidates(
            PortfolioRiskRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            )
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
            )
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
            )
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
            )
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
            )
        )
    except HTTPException as exc:
        errors.append({"factory": "stale_assumptions", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "stale_assumptions", "reason": str(exc)})

    try:
        factories["watchlist_research"] = generate_watchlist_research_recommendation_candidates(
            WatchlistResearchRecommendationGenerateRequest(
                dry_run=request.dry_run,
                plan_id=request.plan_id,
                limit=request.limit,
            )
        )
    except HTTPException as exc:
        errors.append({"factory": "watchlist_research", "reason": str(exc.detail)})
    except Exception as exc:
        errors.append({"factory": "watchlist_research", "reason": str(exc)})

    generated_count = sum(factory.generated_count for factory in factories.values())
    skipped_count = sum(factory.skipped_count for factory in factories.values())
    if not request.dry_run and generated_count:
        _queue_autogit_event("recommendation_factories_generated")

    return RecommendationFactoryRunAllResponse(
        generated_count=generated_count,
        skipped_count=skipped_count,
        factory_count=len(factories),
        factories=factories,
        errors=errors,
        dry_run=request.dry_run,
    )


@app.post("/api/recommendations", response_model=RecommendationItem)
def create_recommendation(request: RecommendationCreateRequest) -> RecommendationItem:
    try:
        prepared_payload = _prepare_recommendation_action_payload(
            source=request.source,
            action_payload=request.action_payload,
            plan_id=request.plan_id,
        )
        recommendation = recommendation_inbox.create(
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
def get_recommendation(recommendation_id: str) -> RecommendationItem:
    try:
        recommendation = recommendation_inbox.get(recommendation_id)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _recommendation_item_from_row(recommendation)


@app.put("/api/recommendations/{recommendation_id}", response_model=RecommendationItem)
def update_recommendation(
    recommendation_id: str,
    request: RecommendationUpdateRequest,
) -> RecommendationItem:
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one field to update")

    try:
        recommendation = recommendation_inbox.update(recommendation_id, updates=updates)
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
) -> RecommendationPreviewResponse:
    try:
        return await preview_recommendation(recommendation_id, request)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recommendations/{recommendation_id}/apply", response_model=RecommendationActionResponse)
async def apply_recommendation_route(
    recommendation_id: str,
    request: RecommendationApplyRequest,
) -> RecommendationActionResponse:
    try:
        response = await apply_recommendation_with_decision_packet(recommendation_id, request)
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
) -> RecommendationActionResponse:
    try:
        response = await reject_recommendation(
            recommendation_id,
            plan_id=request.plan_id,
            reason=request.reason,
            capture_scenario_diff=request.capture_scenario_diff,
            create_decision_packet=request.create_decision_packet,
            decision_packet_research_symbols=request.decision_packet_research_symbols,
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
) -> RecommendationActionResponse:
    try:
        response = update_recommendation_outcome(recommendation_id, request)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("recommendation_outcome_updated")
    return response


@app.post("/api/recommendations/{recommendation_id}/archive", response_model=RecommendationActionResponse)
def archive_recommendation_route(
    recommendation_id: str,
    request: RecommendationRejectRequest,
) -> RecommendationActionResponse:
    try:
        response = archive_recommendation(recommendation_id, note=request.reason)
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
def list_import_files() -> dict[str, list[str]]:
    files = sorted([path.name for path in settings.import_inbox_dir.glob("*.csv")])
    return {"files": files}


@app.get("/api/import/csv-templates")
def list_import_csv_templates() -> dict[str, list[CsvTemplateOption]]:
    templates = [CsvTemplateOption(**item) for item in list_csv_templates()]
    return {"templates": templates}


@app.get("/api/plans", response_model=list[PlanSummary])
def list_plans(limit: int = 100) -> list[PlanSummary]:
    summaries = plan_workspace.list_plans(limit=max(1, min(limit, 500)))
    return [PlanSummary(**summary) for summary in summaries]


@app.post("/api/plans", response_model=PlanDetailResponse)
def create_plan(request: PlanCreateRequest) -> PlanDetailResponse:
    try:
        detail = plan_workspace.create_plan(title=request.title, description=request.description)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_created")
    return _build_plan_detail_response(detail)


@app.get("/api/plans/{plan_id}", response_model=PlanDetailResponse)
def get_plan(plan_id: str) -> PlanDetailResponse:
    try:
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _build_plan_detail_response(detail)


@app.put("/api/plans/{plan_id}", response_model=PlanDetailResponse)
def update_plan(plan_id: str, request: PlanUpdateRequest) -> PlanDetailResponse:
    try:
        detail = plan_workspace.update_plan_files(
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
def update_plan_settings(plan_id: str, request: PlanSettingsUpdateRequest) -> PlanDetailResponse:
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one settings field to update")

    try:
        detail = plan_workspace.update_plan_settings(
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
def get_plan_timeline(plan_id: str) -> PlanTimelineResponse:
    try:
        timeline = plan_workspace.get_plan_timeline(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanTimelineResponse(**timeline)


@app.put("/api/plans/{plan_id}/timeline", response_model=PlanTimelineResponse)
def update_plan_timeline(plan_id: str, request: PlanTimelineUpdateRequest) -> PlanTimelineResponse:
    try:
        timeline = plan_workspace.update_plan_timeline(
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
def get_plan_contribution_rules(plan_id: str) -> PlanContributionRulesResponse:
    try:
        payload = plan_workspace.get_plan_contribution_rules(plan_id)
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
) -> PlanContributionRulesResponse:
    try:
        payload = plan_workspace.update_plan_contribution_rules(
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
def get_plan_assumption_sets(plan_id: str) -> PlanAssumptionSetsResponse:
    try:
        payload = plan_workspace.get_plan_assumption_sets(plan_id)
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
) -> PlanAssumptionSetsResponse:
    try:
        payload = plan_workspace.update_plan_assumption_sets(
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
def get_plan_branch_templates(plan_id: str) -> PlanScenarioBranchTemplatesResponse:
    try:
        payload = plan_workspace.get_plan_branch_templates(plan_id)
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
) -> PlanScenarioBranchTemplatesResponse:
    try:
        payload = plan_workspace.update_plan_branch_templates(
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


def pin_watchlist_research_bridge(
    plan_id: str,
    request: PlanResearchBridgeRequest,
) -> PlanResearchBridgeResponse:
    branch_templates_payload = plan_workspace.get_plan_branch_templates(plan_id)

    selected_items = select_research_bridge_watchlist_items(
        watchlist_items=portfolio_store.list_watchlist(),
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
        assumption_sets_payload = plan_workspace.get_plan_assumption_sets(plan_id)
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

    updated_templates_payload = plan_workspace.update_plan_branch_templates(
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
    plan_workspace.append_decision(
        plan_id=plan_id,
        summary=decision_summary,
        rationale=decision_rationale,
        status="accepted",
    )
    artifact_title = f"Research Bridge Pin - {template_name}"
    artifact_payload = plan_workspace.write_artifact(
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
) -> PlanResearchBridgeResponse:
    try:
        return pin_watchlist_research_bridge(plan_id=plan_id, request=request)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/plans/{plan_id}/scenario-diff", response_model=PlanScenarioDiffResponse)
async def run_plan_scenario_diff(plan_id: str, request: PlanScenarioDiffRequest) -> PlanScenarioDiffResponse:
    compare_updates = request.compare_settings.model_dump(exclude_unset=True)

    try:
        detail = plan_workspace.get_plan(plan_id)
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
        current_value = resolve_portfolio_value(request.current_portfolio_value_usd)
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
) -> PlanWithdrawalStrategyCompareResponse:
    arguments: dict[str, Any] = {
        "plan_id": plan_id,
        "current_portfolio_value_usd": request.current_portfolio_value_usd,
        "assumption_set_id": request.assumption_set_id,
        "strategies": request.strategies,
        "include_raw_results": request.include_raw_results,
    }
    try:
        payload = await tool_compare_withdrawal_strategies(arguments)
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
async def run_plan_scenario_branch(plan_id: str, request: PlanScenarioBranchRequest) -> PlanScenarioBranchResponse:
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
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PlanScenarioBranchResponse(**payload)


@app.get("/api/plans/{plan_id}/tracking", response_model=PlanTrackingResponse)
def get_plan_tracking(plan_id: str) -> PlanTrackingResponse:
    try:
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = snapshot_store.recent(limit=90)
    transactions = portfolio_store.list_transactions(limit=10_000)

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
def activate_plan(plan_id: str) -> PlanSummary:
    try:
        summary = plan_workspace.set_active_plan(plan_id)
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
) -> PlanRecommendationClosureSummaryResponse:
    try:
        response = create_plan_recommendation_closure_summary(
            plan_id=plan_id,
            request=request,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_recommendation_closure_summary_created")
    return response


@app.post("/api/plans/{plan_id}/decisions", response_model=PlanDetailResponse)
def append_plan_decision(plan_id: str, request: PlanDecisionCreateRequest) -> PlanDetailResponse:
    try:
        plan_workspace.append_decision(
            plan_id=plan_id,
            summary=request.summary,
            rationale=request.rationale,
            status=request.status,
        )
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _queue_autogit_event("plan_decision_added")
    return _build_plan_detail_response(detail)


@app.post("/api/plans/{plan_id}/refresh-context", response_model=PlanDetailResponse)
def refresh_plan_context(plan_id: str) -> PlanDetailResponse:
    try:
        plan_workspace.refresh_context(plan_id)
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _queue_autogit_event("plan_context_refreshed")
    return _build_plan_detail_response(detail)


@app.get("/api/plans/{plan_id}/artifacts/{artifact_id}", response_model=PlanArtifactResponse)
def read_plan_artifact(plan_id: str, artifact_id: str) -> PlanArtifactResponse:
    try:
        artifact = plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanArtifactResponse(**artifact)


@app.get("/api/workflows/templates", response_model=list[WorkflowTemplateResponse])
def list_workflow_templates() -> list[WorkflowTemplateResponse]:
    templates = workflow_runner.templates()
    return [WorkflowTemplateResponse(**item) for item in templates]


@app.post("/api/workflows/run", response_model=WorkflowRunResponse)
async def run_workflow(request: WorkflowRunRequest) -> WorkflowRunResponse:
    snapshot, previous_snapshot = await resolve_snapshots_for_workflow(
        use_live_snapshot=request.use_live_snapshot
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

    resolved_plan_id = request.plan_id or plan_workspace.get_active_plan_id()

    artifact_payload: dict[str, object] | None = None
    if request.save_to_plan:
        if resolved_plan_id:
            try:
                artifact_payload = plan_workspace.write_artifact(
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
) -> dict[str, Any]:
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
def list_copilot_conversations(limit: int = 30) -> list[CopilotConversationSummary]:
    summaries = conversation_store.list(limit=max(1, min(limit, 200)))
    return [CopilotConversationSummary(**summary) for summary in summaries]


@app.get("/api/copilot/conversations/{conversation_id}", response_model=CopilotConversationResponse)
def get_copilot_conversation(conversation_id: str) -> CopilotConversationResponse:
    try:
        conversation = conversation_store.get(conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return CopilotConversationResponse(**conversation)


@app.post("/api/copilot/chat", response_model=CopilotChatResponse)
async def copilot_chat(request: CopilotChatRequest) -> CopilotChatResponse:
    context_options = request.context_options
    context_symbols = normalize_research_symbols(
        context_options.research_symbols,
        max_symbols=context_options.research_symbol_limit,
    )
    contextual_brief = await build_contextual_brief(
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
    )
    try:
        result = await copilot.chat(
            question=request.question,
            conversation_id=request.conversation_id,
            contextual_brief=contextual_brief,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        detail = f"LLM provider error: {exc.response.text}"
        raise HTTPException(status_code=502, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Copilot failed: {exc}") from exc

    return CopilotChatResponse(**result)


@app.get("/api/snapshot/live", response_model=PortfolioSnapshot)
async def get_live_snapshot() -> PortfolioSnapshot:
    return await build_live_snapshot()


@app.post("/api/snapshot/sync")
async def sync_snapshot() -> dict[str, str | dict[str, str]]:
    try:
        return await execute_sync(trigger="manual")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc


@app.get("/api/snapshot/latest", response_model=PortfolioSnapshot)
def get_latest_snapshot() -> PortfolioSnapshot:
    try:
        return snapshot_store.latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/snapshot/history", response_model=SnapshotHistoryResponse)
def get_snapshot_history(limit: int = 30) -> SnapshotHistoryResponse:
    return build_snapshot_history_payload(limit=max(2, min(limit, 365)))


@app.post("/api/snapshot/backfill-history")
def backfill_snapshot_history_route(request: dict[str, Any] | None = None) -> dict[str, Any]:
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
        portfolio_store=portfolio_store,
        snapshot_store=snapshot_store,
        research=research_service,
        start_date=start_date,
        end_date=end_date,
        days=days,
        overwrite=overwrite,
    )


@app.post("/api/import/csv", response_model=CsvImportResponse)
async def import_csv_transactions(request: CsvImportRequest) -> CsvImportResponse:
    file_path = resolve_import_path(request.path)
    return await execute_csv_import(file_path=file_path, request=request)


@app.post("/api/import/upload-csv", response_model=CsvImportResponse)
async def import_uploaded_csv(
    file: UploadFile = File(...),
    dry_run: bool = Form(True),
    delimiter: str = Form(","),
    broker_template: str = Form("auto"),
    default_data_source: str | None = Form(None),
    default_currency: str | None = Form(None),
    archive_after_success: bool = Form(False),
) -> CsvImportResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file name provided")

    inbox_name = normalize_upload_filename(file.filename)
    destination = unique_inbox_path(inbox_name)

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

    return await execute_csv_import(file_path=destination, request=request)


@app.post("/api/planning/scenarios", response_model=PlanningResponse)
async def plan_scenarios(request: ScenarioRequest) -> PlanningResponse:
    current_value = request.current_portfolio_value_usd
    if current_value is None:
        try:
            latest_snapshot = snapshot_store.latest()
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
    service = ignidash_scenario_service
    timeline_projection: TimelineImpactProjectionResponse | None = None
    active_timeline_payload: dict[str, Any] | None = None
    active_withdrawal_strategy: str | None = None
    active_drawdown_order: str | None = None
    active_retirement_age: int | None = None
    active_plan_detail: dict[str, Any] | None = None
    active_plan_id = plan_workspace.get_active_plan_id()
    if active_plan_id:
        try:
            active_plan_detail = plan_workspace.get_plan(active_plan_id)
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
            service = build_ignidash_service_for_plan_settings(planning_settings_for_run)
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
            accounts_override=build_planning_accounts_from_portfolio(),
        )

    profile_payload = get_financial_profile_payload()
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

    scenario_guard_reason = await sidecar_contract_guard_reason("ignidash_scenario")
    result = await service.run(
        current_portfolio_value_usd=resolved_current_value,
        annual_contribution_usd=resolved_annual_contribution,
        years=request.years,
        hsa_extra_contribution_usd=request.hsa_extra_contribution_usd,
        accounts=build_planning_accounts_from_portfolio(),
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
        sidecar_guard_reason=scenario_guard_reason,
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
    if result.engine_status == "degraded":
        await engine_status_tracker.increment_degraded(
            "ignidash_scenario",
            reason=result.warnings[0] if result.warnings else None,
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
def planning_income_projection(request: IncomeProjectionRequest) -> IncomeProjectionResponse:
    if request.income_items is not None:
        income_items = [item.model_dump(mode="json") for item in request.income_items]
    else:
        profile_payload = get_financial_profile_payload()
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
def planning_expense_projection(request: ExpenseProjectionRequest) -> ExpenseProjectionResponse:
    if request.expense_items is not None:
        expense_items = [item.model_dump(mode="json") for item in request.expense_items]
    else:
        profile_payload = get_financial_profile_payload()
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
def planning_debt_projection(request: DebtProjectionRequest) -> DebtProjectionResponse:
    if request.debt_items is not None:
        debt_items = [item.model_dump(mode="json") for item in request.debt_items]
    else:
        profile_payload = get_financial_profile_payload()
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
) -> SocialSecurityProjectionResponse:
    earnings_history = (
        [item.model_dump(mode="json") for item in request.earnings_history]
        if request.earnings_history is not None
        else []
    )

    estimated_annual_earnings_usd = request.estimated_annual_earnings_usd
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
def planning_rmd_projection(request: RmdProjectionRequest) -> RmdProjectionResponse:
    if request.accounts is not None:
        accounts = [item.model_dump(mode="json") for item in request.accounts]
    else:
        accounts = build_planning_accounts_from_portfolio()

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
def planning_contribution_allocation(request: ContributionAllocationRequest) -> ContributionAllocationResponse:
    accounts = [item.model_dump(mode="json") for item in request.accounts] or build_planning_accounts_from_portfolio()
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

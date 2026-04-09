from __future__ import annotations

import asyncio
import json
import re
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx

from buildwealth_orchestrator.clients.ghostfolio import GhostfolioClient
from buildwealth_orchestrator.clients.ignidash import IgnidashClient
from buildwealth_orchestrator.schemas import (
    ChatRequest,
    ChatResponse,
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotConversationResponse,
    CopilotConversationSummary,
    CsvImportRequest,
    CsvImportResponse,
    FinancialProfileRequest,
    FinancialProfileResponse,
    OnboardingStatusResponse,
    OptionsChainRequest,
    PriceHistoryRequest,
    PlanArtifactResponse,
    PlanCreateRequest,
    PlanDecisionCreateRequest,
    PlanDetailResponse,
    PlanScenarioDiffRequest,
    PlanScenarioDiffResponse,
    PlanSettings,
    PlanSettingsUpdateRequest,
    ScenarioComparisonRow,
    PlanSummary,
    PlanUpdateRequest,
    PlanningResponse,
    PortfolioSnapshot,
    ResearchResponse,
    ScenarioRequest,
    SnapshotHistoryResponse,
    SyncStatusResponse,
    RecommendationActionResponse,
    RecommendationApplyRequest,
    RecommendationCreateRequest,
    RecommendationItem,
    RecommendationRejectRequest,
    RecommendationUpdateRequest,
    AffordabilityRequest,
    AffordabilityResponse,
    SimulateTradeRequest,
    SimulateTradeResponse,
    FinancialHealthResponse,
    GoalProgressResponse,
    PlanTrackingResponse,
    TodayDashboardResponse,
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
    archive_import_file,
    parse_transaction_csv,
)
from buildwealth_orchestrator.services.financial_profile import FinancialProfileStore
from buildwealth_orchestrator.services.ignidash_exporter import (
    IgnidashExportStore,
    build_ignidash_plan_payload,
)
from buildwealth_orchestrator.services.research import OpenBBResearchService
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine
from buildwealth_orchestrator.services.snapshot_store import (
    SnapshotStore,
    normalize_ghostfolio_snapshot,
)
from buildwealth_orchestrator.services.affordability import assess_affordability
from buildwealth_orchestrator.services.portfolio_simulator import simulate_trade
from buildwealth_orchestrator.services.goal_tracker import compute_goal_progress
from buildwealth_orchestrator.services.financial_health import compute_financial_health
from buildwealth_orchestrator.services.plan_tracker import compute_plan_tracking
from buildwealth_orchestrator.services.today_dashboard import build_today_dashboard_payload
from buildwealth_orchestrator.services.workflow_runner import WorkflowRunner
from buildwealth_orchestrator.services.plan_workspace import (
    PlanNotFoundError,
    PlanWorkspace,
)
from buildwealth_orchestrator.services.recommendation_inbox import (
    RecommendationInbox,
    RecommendationNotFoundError,
)
from buildwealth_orchestrator.services.user_settings import UserSettingsStore
from buildwealth_orchestrator.settings import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)

web_dir = Path(__file__).resolve().parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


user_settings_store = UserSettingsStore(settings.snapshot_dir.parent / "settings" / "user_settings.json")

# Apply user settings over env defaults
_user_cfg = user_settings_store.load_raw()
if _user_cfg.get("openai_api_key"):
    settings.openai_api_key = _user_cfg["openai_api_key"]
if _user_cfg.get("openai_model"):
    settings.openai_model = _user_cfg["openai_model"]
if _user_cfg.get("openai_base_url"):
    settings.openai_base_url = _user_cfg["openai_base_url"]
if _user_cfg.get("ghostfolio_api_base"):
    settings.ghostfolio_api_base = _user_cfg["ghostfolio_api_base"]
if _user_cfg.get("ghostfolio_security_token"):
    settings.ghostfolio_security_token = _user_cfg["ghostfolio_security_token"]

ghostfolio_client = GhostfolioClient(
    api_base=settings.ghostfolio_api_base,
    security_token=settings.ghostfolio_security_token,
    timeout_seconds=settings.ghostfolio_timeout_seconds,
)
ignidash_client = IgnidashClient(
    convex_actions_url=settings.ignidash_convex_url,
    convex_api_secret=settings.ignidash_convex_api_secret,
    timeout_seconds=settings.ghostfolio_timeout_seconds,
)
snapshot_store = SnapshotStore(settings.snapshot_dir)
ignidash_export_store = IgnidashExportStore(settings.ignidash_export_dir)
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
        "- For 'how am I doing?' or 'what is my financial situation?' → call get_financial_health first.\n"
        "- For 'can I afford X?' → call assess_affordability with the monthly cost or purchase price. "
        "It computes the full impact on cash flow, savings rate, and DTI automatically.\n"
        "- For 'am I on track?' → call get_plan_tracking for plan assumptions, or get_goal_progress for specific goals.\n"
        "- For 'when will I reach my goal?' or 'what do I need to save?' → call get_goal_progress.\n"
        "- For 'what if I change my contributions?' → call run_plan_scenario_diff.\n"
        "- For 'what should I do?' → call get_today_dashboard and list_recommendations.\n"
        "- For stock/investment research → call research_quote or research_price_history, "
        "then call simulate_trade to show how buying it would affect portfolio allocation.\n"
        "- For 'what if I buy/sell X?' → call simulate_trade to show allocation and concentration impact.\n"
        "- For daily reviews → call get_financial_health, get_plan_tracking, and get_today_dashboard.\n\n"
        "RESPONSE GUIDELINES:\n"
        "- When discussing portfolio holdings, reference specific symbols and allocation percentages.\n"
        "- When discussing cash flow, cite monthly income, expenses, and surplus figures.\n"
        "- When recommending actions, explain the quantitative impact (e.g., 'increasing contributions by "
        "$200/month would add ~$X to your projected retirement value').\n"
        "- Proactively flag risks you discover (high concentration, low emergency fund, negative cash flow)."
    ),
)

sync_lock = asyncio.Lock()
scheduler_task: asyncio.Task | None = None
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def build_live_snapshot() -> PortfolioSnapshot:
    try:
        holdings_payload = await ghostfolio_client.get_holdings(date_range="max")
        performance_payload = await ghostfolio_client.get_performance(date_range="max")
        accounts_payload = await ghostfolio_client.get_accounts()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ghostfolio fetch failed: {exc}") from exc

    return normalize_ghostfolio_snapshot(
        holdings_payload=holdings_payload,
        performance_payload=performance_payload,
        accounts_payload=accounts_payload,
        base_currency=settings.app_currency,
    )


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

            ignidash_payload = build_ignidash_plan_payload(snapshot)
            ignidash_path = ignidash_export_store.write(ignidash_payload)

            default_plan_response = {"status": "skipped"}
            if settings.ignidash_convex_api_secret:
                try:
                    response = await ignidash_client.create_default_plan(
                        user_id=settings.ignidash_default_user_id,
                        user_name=settings.ignidash_default_user_name,
                    )
                    default_plan_response = {
                        "status": response.get("status", "ok"),
                        "message": response.get("body", ""),
                    }
                except Exception as exc:
                    default_plan_response = {
                        "status": "error",
                        "message": str(exc),
                    }

            sync_state["last_snapshot_path"] = str(snapshot_path)
            sync_state["last_ignidash_payload_path"] = str(ignidash_path)
            sync_state["last_completed_at"] = utc_now()

            return {
                "snapshot": str(snapshot_path),
                "ignidash_import_payload": str(ignidash_path),
                "ignidash_default_plan": default_plan_response,
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

    accounts = await ghostfolio_client.get_accounts_list()
    account_ids_by_name: dict[str, str] = {}
    for account in accounts:
        name = str(account.get("name") or "").strip().lower()
        account_id = str(account.get("id") or "").strip()
        if name and account_id and name not in account_ids_by_name:
            account_ids_by_name[name] = account_id

    parsed = parse_transaction_csv(
        file_path=file_path,
        default_data_source=request.default_data_source or settings.ghostfolio_default_data_source,
        default_currency=request.default_currency or settings.ghostfolio_default_currency,
        delimiter=request.delimiter,
        account_ids_by_name=account_ids_by_name,
    )

    ghostfolio_response = None
    imported_activities = 0

    if parsed.activities:
        try:
            ghostfolio_response = await ghostfolio_client.import_activities(
                activities=parsed.activities,
                dry_run=request.dry_run,
            )
            if not request.dry_run:
                imported_activities = len(parsed.activities)
        except Exception as exc:
            parsed.errors.append(f"Ghostfolio import request failed: {exc}")
    else:
        parsed.warnings.append("No valid activities were parsed from this CSV file.")

    if request.archive_after_success and not request.dry_run and not parsed.errors:
        archived_path = archive_import_file(file_path, settings.import_archive_dir)
        parsed.warnings.append(f"Archived source CSV to {archived_path}")

    return CsvImportResponse(
        file_path=str(file_path),
        dry_run=request.dry_run,
        parsed_rows=parsed.parsed_rows,
        valid_activities=len(parsed.activities),
        imported_activities=imported_activities,
        warnings=parsed.warnings,
        errors=parsed.errors,
        ghostfolio_response=ghostfolio_response,
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


PLAN_SETTINGS_FIELDS = (
    "annual_contribution_usd",
    "years",
    "hsa_extra_contribution_usd",
    "marginal_tax_rate",
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
        inflation=settings.planner_inflation,
        monte_carlo_runs=settings.planner_monte_carlo_runs,
        hsa_delta_default=settings.planner_hsa_delta_default,
        marginal_tax_rate=(
            float(marginal_tax_rate)
            if marginal_tax_rate is not None
            else settings.planner_marginal_tax_rate
        ),
    )


def run_scenarios_for_plan_settings(
    current_portfolio_value_usd: float,
    plan_settings: dict[str, Any],
) -> PlanningResponse:
    validate_plan_return_relationships(plan_settings)
    engine = build_scenario_engine_for_plan_settings(plan_settings)
    annual_contribution = plan_settings.get("annual_contribution_usd")
    years = plan_settings.get("years")
    hsa_extra = plan_settings.get("hsa_extra_contribution_usd")

    return engine.run(
        current_portfolio_value_usd=float(current_portfolio_value_usd),
        annual_contribution_usd=(
            float(annual_contribution) if annual_contribution is not None else None
        ),
        years=int(years) if years is not None else None,
        hsa_extra_contribution_usd=(float(hsa_extra) if hsa_extra is not None else None),
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
) -> tuple[list[dict[str, Any]], dict[str, float | int | None]]:
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

    return scenario_deltas, monte_delta


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

    for key in ("income_items", "expense_items", "debt_items", "goal_items"):
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()
            row["label"] = label or "Untitled"

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
) -> list[dict[str, Any]]:
    cleaned_status = str(status or "").strip().lower() or None
    status_filter = None
    if cleaned_status in {"proposed", "applied", "rejected", "archived"}:
        status_filter = cleaned_status

    return recommendation_inbox.list(
        limit=max(1, min(int(limit), 500)),
        status=status_filter,  # type: ignore[arg-type]
        plan_id=(plan_id.strip() if isinstance(plan_id, str) and plan_id.strip() else None),
        include_archived=include_archived,
    )


def _build_recommendation_open_counts() -> tuple[int, int]:
    rows = recommendation_inbox.list(limit=500, status="proposed")
    high = [
        row
        for row in rows
        if str(row.get("priority", "")).strip().lower() == "high"
    ]
    return len(rows), len(high)


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
    return recommendation_inbox.create(
        title=f"{workflow_id.replace('_', ' ').title()} Recommendation",
        detail=text,
        priority="medium",
        recommendation_type="workflow_action",
        source=f"workflow:{workflow_id}",
        plan_id=plan_id,
        action_payload={
            "workflow_id": workflow_id,
            "suggested_action": text,
            "evidence": evidence,
        },
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
    return RecommendationActionResponse(
        recommendation=RecommendationItem(**recommendation),
        plan=plan_detail,
        message=message,
    )


def reject_recommendation(recommendation_id: str, reason: str = "") -> RecommendationActionResponse:
    recommendation = recommendation_inbox.get(recommendation_id)
    current_status = str(recommendation.get("status", "proposed")).strip().lower()
    if current_status in {"applied", "rejected"}:
        raise ValueError(f"Recommendation status is '{current_status}' and cannot be rejected.")

    updated = recommendation_inbox.set_status(
        recommendation_id,
        status="rejected",
        resolution_note=reason,
    )
    return RecommendationActionResponse(
        recommendation=RecommendationItem(**updated),
        plan=None,
        message="Recommendation rejected.",
    )


def archive_recommendation(recommendation_id: str, note: str = "") -> RecommendationActionResponse:
    recommendation = recommendation_inbox.set_status(
        recommendation_id,
        status="archived",
        resolution_note=note,
    )
    return RecommendationActionResponse(
        recommendation=RecommendationItem(**recommendation),
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
        inbox_open_count=inbox_open_count,
        inbox_high_priority_count=inbox_high_priority_count,
    )

    # Enrich with financial health summary
    try:
        from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem

        health = compute_financial_health(
            income_items=[IncomeItem(**i) for i in profile_payload.get("income_items", [])],
            expense_items=[ExpenseItem(**e) for e in profile_payload.get("expense_items", [])],
            debt_items=[DebtItem(**d) for d in profile_payload.get("debt_items", [])],
            goal_items=[GoalItem(**g) for g in profile_payload.get("goal_items", [])],
            snapshot=latest_snapshot,
        )
        dashboard.net_worth_usd = health.net_worth_usd
        dashboard.monthly_surplus_usd = health.monthly_surplus_usd
        dashboard.savings_rate_pct = health.savings_rate_pct
        dashboard.financial_health_status = health.status
    except Exception:
        pass

    return dashboard


async def build_contextual_brief(
    use_live_snapshot: bool = False,
    plan_id: str | None = None,
) -> str:
    snapshot_payload: dict[str, object]
    try:
        if use_live_snapshot:
            snapshot_payload = summarize_snapshot(await build_live_snapshot())
        else:
            snapshot_payload = summarize_snapshot(snapshot_store.latest())
    except FileNotFoundError:
        snapshot_payload = {"note": "No local snapshot yet. Run sync or ask tool to fetch live snapshot."}
    except Exception as exc:
        snapshot_payload = {"note": f"Snapshot context unavailable: {exc}"}

    try:
        snapshot_history_payload = build_snapshot_history_payload(limit=14).model_dump(mode="json")
    except Exception as exc:
        snapshot_history_payload = {"note": f"Snapshot history context unavailable: {exc}"}

    try:
        today_dashboard_payload = build_today_dashboard_response().model_dump(mode="json")
    except Exception as exc:
        today_dashboard_payload = {"note": f"Today dashboard context unavailable: {exc}"}

    try:
        profile_payload = FinancialProfileResponse(**get_financial_profile_payload()).model_dump(mode="json")
    except Exception as exc:
        profile_payload = {"note": f"Financial profile context unavailable: {exc}"}

    try:
        onboarding_payload = build_onboarding_status_response().model_dump(mode="json")
    except Exception as exc:
        onboarding_payload = {"note": f"Onboarding context unavailable: {exc}"}

    try:
        recommendation_rows = _recommendation_list(limit=20, status="proposed")
        recommendation_payload = {
            "open_count": len(recommendation_rows),
            "high_priority_count": len(
                [
                    row
                    for row in recommendation_rows
                    if str(row.get("priority", "")).strip().lower() == "high"
                ]
            ),
            "items": recommendation_rows[:8],
        }
    except Exception as exc:
        recommendation_payload = {"note": f"Recommendation context unavailable: {exc}"}

    try:
        plan_payload = plan_workspace.get_context_payload(plan_id=plan_id)
    except PlanNotFoundError as exc:
        plan_payload = {"note": str(exc)}
    except Exception as exc:
        plan_payload = {"note": f"Plan context unavailable: {exc}"}

    sync_payload = get_sync_status().model_dump(mode="json")

    context = {
        "location_state": settings.app_state,
        "currency": settings.app_currency,
        "sync_status": sync_payload,
        "today_dashboard": today_dashboard_payload,
        "financial_profile": profile_payload,
        "onboarding_status": onboarding_payload,
        "recommendations": recommendation_payload,
        "snapshot_summary": snapshot_payload,
        "snapshot_history": snapshot_history_payload,
        "plan_context": plan_payload,
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
    }
    return json.dumps(context, indent=2, default=str)


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


async def tool_update_financial_profile(arguments: dict[str, object]) -> dict[str, object]:
    profile_payload = get_financial_profile_payload()

    def _merge_list(key: str) -> None:
        value = arguments.get(key)
        if value is None:
            return
        if not isinstance(value, list):
            raise ValueError(f"{key} must be a list")
        profile_payload[key] = value

    _merge_list("income_items")
    _merge_list("expense_items")
    _merge_list("debt_items")
    _merge_list("goal_items")

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
    rows = _recommendation_list(
        limit=limit,
        status=status,
        plan_id=plan_id,
        include_archived=include_archived,
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

    action_payload = arguments.get("action_payload")
    payload = action_payload if isinstance(action_payload, dict) else {}

    recommendation = recommendation_inbox.create(
        title=title,
        detail=detail,
        priority=str(arguments.get("priority") or "medium").strip().lower() or "medium",
        recommendation_type=str(arguments.get("recommendation_type") or "general").strip().lower() or "general",
        source=str(arguments.get("source") or "copilot").strip().lower() or "copilot",
        plan_id=(str(arguments.get("plan_id") or "").strip() or None),
        action_payload=payload,
    )
    return {"recommendation": recommendation}


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
    )
    result = apply_recommendation(recommendation_id, payload)
    return result.model_dump(mode="json")


async def tool_reject_recommendation(arguments: dict[str, object]) -> dict[str, object]:
    recommendation_id = str(arguments.get("recommendation_id") or "").strip()
    if not recommendation_id:
        raise ValueError("recommendation_id is required")
    reason = str(arguments.get("reason") or "").strip()
    result = reject_recommendation(recommendation_id, reason=reason)
    return result.model_dump(mode="json")


async def tool_run_sync(_: dict[str, object]) -> dict[str, object]:
    return await execute_sync(trigger="copilot-tool")


async def tool_get_sync_status(_: dict[str, object]) -> dict[str, object]:
    return get_sync_status().model_dump(mode="json")


async def tool_run_planning(arguments: dict[str, object]) -> dict[str, object]:
    current_value = arguments.get("current_portfolio_value_usd")
    annual_contribution = arguments.get("annual_contribution_usd")
    years = arguments.get("years")
    hsa_extra = arguments.get("hsa_extra_contribution_usd")

    if current_value is None:
        current_value = snapshot_store.latest().total_value_usd

    result = scenario_engine.run(
        current_portfolio_value_usd=float(current_value),
        annual_contribution_usd=(float(annual_contribution) if annual_contribution is not None else None),
        years=(int(years) if years is not None else None),
        hsa_extra_contribution_usd=(float(hsa_extra) if hsa_extra is not None else None),
    )
    return result.model_dump(mode="json")


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


async def tool_list_accounts(_: dict[str, object]) -> dict[str, object]:
    accounts = await ghostfolio_client.get_accounts_list()
    simplified = []
    for account in accounts:
        simplified.append(
            {
                "id": account.get("id"),
                "name": account.get("name"),
                "balance": account.get("balance"),
                "currency": account.get("currency"),
                "isExcluded": account.get("isExcluded"),
            }
        )
    return {"count": len(simplified), "accounts": simplified}


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


async def tool_get_plan_tracking(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    detail = plan_workspace.get_plan(plan_id)
    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = snapshot_store.recent(limit=90)
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
    )
    return result.model_dump(mode="json")


async def tool_run_plan_scenario_diff(arguments: dict[str, object]) -> dict[str, object]:
    plan_id = resolve_plan_id_or_active(arguments.get("plan_id"))
    detail = plan_workspace.get_plan(plan_id)
    base_settings = detail.get("settings", {})
    compare_updates = extract_plan_settings_updates(arguments)
    candidate_settings = merge_plan_settings(base_settings, compare_updates)

    current_value_raw = arguments.get("current_portfolio_value_usd")
    current_value = resolve_portfolio_value(
        float(current_value_raw) if current_value_raw is not None else None
    )

    base_result = run_scenarios_for_plan_settings(
        current_portfolio_value_usd=current_value,
        plan_settings=base_settings,
    )
    candidate_result = run_scenarios_for_plan_settings(
        current_portfolio_value_usd=current_value,
        plan_settings=candidate_settings,
    )
    scenario_deltas, monte_carlo_delta = build_scenario_diff_payload(base_result, candidate_result)

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
        "base_result": base_result.model_dump(mode="json"),
        "candidate_result": candidate_result.model_dump(mode="json"),
        "scenario_deltas": scenario_deltas,
        "monte_carlo_delta": monte_carlo_delta,
        "applied_to_plan": applied,
    }


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
        name="get_onboarding_status",
        description="Read onboarding completion status for unified financial context.",
        parameters=empty_schema,
        handler=tool_get_onboarding_status,
    )
    copilot.register_tool(
        name="update_financial_profile",
        description=(
            "Update financial profile collections and tax settings. "
            "You may provide any subset of income_items, expense_items, debt_items, goal_items, "
            "tax_profile, flags, and notes."
        ),
        parameters={
            "type": "object",
            "properties": {
                "income_items": {"type": "array", "items": {"type": "object"}},
                "expense_items": {"type": "array", "items": {"type": "object"}},
                "debt_items": {"type": "array", "items": {"type": "object"}},
                "goal_items": {"type": "array", "items": {"type": "object"}},
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
            "List recommendation inbox items. Optional fields: status, plan_id, limit, include_archived."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "plan_id": {"type": "string"},
                "limit": {"type": "integer"},
                "include_archived": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=tool_list_recommendations,
    )
    copilot.register_tool(
        name="create_recommendation",
        description=(
            "Create a recommendation inbox item. "
            "Required: title, detail. Optional: priority, recommendation_type, source, plan_id, action_payload."
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
            "Apply a recommendation. For plan_settings_update recommendations, may include plan_settings_updates overrides."
        ),
        parameters={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "plan_settings_updates": {"type": "object"},
                "rationale": {"type": "string"},
                "decision_status": {"type": "string"},
            },
            "required": ["recommendation_id"],
            "additionalProperties": False,
        },
        handler=tool_apply_recommendation,
    )
    copilot.register_tool(
        name="reject_recommendation",
        description="Reject a recommendation inbox item with an optional reason.",
        parameters={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["recommendation_id"],
            "additionalProperties": False,
        },
        handler=tool_reject_recommendation,
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
            "Optional fields: current_portfolio_value_usd, annual_contribution_usd, years, hsa_extra_contribution_usd."
        ),
        parameters={
            "type": "object",
            "properties": {
                "current_portfolio_value_usd": {"type": "number"},
                "annual_contribution_usd": {"type": "number"},
                "years": {"type": "integer"},
                "hsa_extra_contribution_usd": {"type": "number"},
            },
            "additionalProperties": False,
        },
        handler=tool_run_planning,
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
        name="list_accounts",
        description="List known Ghostfolio accounts with balances and metadata.",
        parameters=empty_schema,
        handler=tool_list_accounts,
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


@app.get("/api/settings")
def get_user_settings() -> dict[str, Any]:
    return user_settings_store.load_masked()


@app.put("/api/settings")
def update_user_settings(request: dict[str, Any]) -> dict[str, Any]:
    global ghostfolio_client, openai_tool_client

    saved = user_settings_store.save(request)

    # Hot-reload affected services
    if saved.get("openai_api_key"):
        openai_tool_client = OpenAIChatToolClient(
            api_key=saved["openai_api_key"],
            model=saved.get("openai_model") or settings.openai_model,
            base_url=saved.get("openai_base_url") or settings.openai_base_url,
        )
        copilot.llm_client = openai_tool_client

    if saved.get("ghostfolio_security_token") or saved.get("ghostfolio_api_base"):
        ghostfolio_client = GhostfolioClient(
            api_base=saved.get("ghostfolio_api_base") or settings.ghostfolio_api_base,
            security_token=saved.get("ghostfolio_security_token") or settings.ghostfolio_security_token,
            timeout_seconds=settings.ghostfolio_timeout_seconds,
        )

    return user_settings_store.load_masked()


@app.on_event("startup")
async def on_startup() -> None:
    settings.import_inbox_dir.mkdir(parents=True, exist_ok=True)
    settings.import_archive_dir.mkdir(parents=True, exist_ok=True)
    settings.conversation_dir.mkdir(parents=True, exist_ok=True)
    settings.plans_dir.mkdir(parents=True, exist_ok=True)
    settings.financial_profile_path.parent.mkdir(parents=True, exist_ok=True)
    settings.recommendations_path.parent.mkdir(parents=True, exist_ok=True)

    global scheduler_task
    if settings.sync_interval_minutes > 0:
        scheduler_task = asyncio.create_task(scheduled_sync_loop())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global scheduler_task
    if scheduler_task is not None:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
        scheduler_task = None


@app.get("/", include_in_schema=False)
def ui_root() -> Response:
    index_file = web_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return HTMLResponse(
        "<h1>BuildWealth UI not found</h1><p>Expected index.html in orchestrator web directory.</p>",
        status_code=500,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/dashboard/today", response_model=TodayDashboardResponse)
def today_dashboard() -> TodayDashboardResponse:
    return build_today_dashboard_response()


@app.get("/api/financial-profile", response_model=FinancialProfileResponse)
def get_financial_profile() -> FinancialProfileResponse:
    return FinancialProfileResponse(**get_financial_profile_payload())


@app.put("/api/financial-profile", response_model=FinancialProfileResponse)
def update_financial_profile(request: FinancialProfileRequest) -> FinancialProfileResponse:
    saved = save_financial_profile_payload(request)
    return FinancialProfileResponse(**saved)


@app.get("/api/onboarding/status", response_model=OnboardingStatusResponse)
def onboarding_status() -> OnboardingStatusResponse:
    return build_onboarding_status_response()


@app.get("/api/financial-health", response_model=FinancialHealthResponse)
def get_financial_health() -> FinancialHealthResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem

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
        snapshot=snap,
    )


@app.post("/api/affordability", response_model=AffordabilityResponse)
def check_affordability(request: AffordabilityRequest) -> AffordabilityResponse:
    from buildwealth_orchestrator.schemas import DebtItem, ExpenseItem, GoalItem, IncomeItem

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
) -> list[RecommendationItem]:
    rows = _recommendation_list(
        limit=limit,
        status=status,
        plan_id=plan_id,
        include_archived=include_archived,
    )
    return [RecommendationItem(**row) for row in rows]


@app.post("/api/recommendations", response_model=RecommendationItem)
def create_recommendation(request: RecommendationCreateRequest) -> RecommendationItem:
    recommendation = recommendation_inbox.create(
        title=request.title,
        detail=request.detail,
        priority=request.priority,
        recommendation_type=request.recommendation_type,
        source=request.source,
        plan_id=request.plan_id,
        action_payload=request.action_payload,
    )
    return RecommendationItem(**recommendation)


@app.get("/api/recommendations/{recommendation_id}", response_model=RecommendationItem)
def get_recommendation(recommendation_id: str) -> RecommendationItem:
    try:
        recommendation = recommendation_inbox.get(recommendation_id)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RecommendationItem(**recommendation)


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

    return RecommendationItem(**recommendation)


@app.post("/api/recommendations/{recommendation_id}/apply", response_model=RecommendationActionResponse)
def apply_recommendation_route(
    recommendation_id: str,
    request: RecommendationApplyRequest,
) -> RecommendationActionResponse:
    try:
        return apply_recommendation(recommendation_id, request)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recommendations/{recommendation_id}/reject", response_model=RecommendationActionResponse)
def reject_recommendation_route(
    recommendation_id: str,
    request: RecommendationRejectRequest,
) -> RecommendationActionResponse:
    try:
        return reject_recommendation(recommendation_id, reason=request.reason)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recommendations/{recommendation_id}/archive", response_model=RecommendationActionResponse)
def archive_recommendation_route(
    recommendation_id: str,
    request: RecommendationRejectRequest,
) -> RecommendationActionResponse:
    try:
        return archive_recommendation(recommendation_id, note=request.reason)
    except RecommendationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sync/status", response_model=SyncStatusResponse)
def sync_status() -> SyncStatusResponse:
    return get_sync_status()


@app.get("/api/import/files")
def list_import_files() -> dict[str, list[str]]:
    files = sorted([path.name for path in settings.import_inbox_dir.glob("*.csv")])
    return {"files": files}


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
    return PlanDetailResponse(**detail)


@app.get("/api/plans/{plan_id}", response_model=PlanDetailResponse)
def get_plan(plan_id: str) -> PlanDetailResponse:
    try:
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanDetailResponse(**detail)


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
    return PlanDetailResponse(**detail)


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
    return PlanDetailResponse(**detail)


@app.post("/api/plans/{plan_id}/scenario-diff", response_model=PlanScenarioDiffResponse)
def run_plan_scenario_diff(plan_id: str, request: PlanScenarioDiffRequest) -> PlanScenarioDiffResponse:
    compare_updates = request.compare_settings.model_dump(exclude_unset=True)

    try:
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    base_settings = dict(detail.get("settings", {}))
    candidate_settings = merge_plan_settings(base_settings, compare_updates)

    try:
        current_value = resolve_portfolio_value(request.current_portfolio_value_usd)
        base_result = run_scenarios_for_plan_settings(
            current_portfolio_value_usd=current_value,
            plan_settings=base_settings,
        )
        candidate_result = run_scenarios_for_plan_settings(
            current_portfolio_value_usd=current_value,
            plan_settings=candidate_settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scenario_deltas, monte_carlo_delta = build_scenario_diff_payload(base_result, candidate_result)

    return PlanScenarioDiffResponse(
        plan_id=plan_id,
        current_portfolio_value_usd=current_value,
        base_settings=PlanSettings(**base_settings),
        candidate_settings=PlanSettings(**candidate_settings),
        base_result=base_result,
        candidate_result=candidate_result,
        scenario_deltas=[ScenarioComparisonRow(**item) for item in scenario_deltas],
        monte_carlo_delta=monte_carlo_delta,
    )


@app.get("/api/plans/{plan_id}/tracking", response_model=PlanTrackingResponse)
def get_plan_tracking(plan_id: str) -> PlanTrackingResponse:
    try:
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    plan_settings = PlanSettings(**detail.get("settings", {}))
    snapshots = snapshot_store.recent(limit=90)

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
    )


@app.post("/api/plans/{plan_id}/activate", response_model=PlanSummary)
def activate_plan(plan_id: str) -> PlanSummary:
    try:
        summary = plan_workspace.set_active_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanSummary(**summary)


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
    return PlanDetailResponse(**detail)


@app.post("/api/plans/{plan_id}/refresh-context", response_model=PlanDetailResponse)
def refresh_plan_context(plan_id: str) -> PlanDetailResponse:
    try:
        plan_workspace.refresh_context(plan_id)
        detail = plan_workspace.get_plan(plan_id)
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlanDetailResponse(**detail)


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
    contextual_brief = await build_contextual_brief(
        use_live_snapshot=request.use_live_snapshot,
        plan_id=request.plan_id,
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


@app.post("/api/import/csv", response_model=CsvImportResponse)
async def import_csv_transactions(request: CsvImportRequest) -> CsvImportResponse:
    file_path = resolve_import_path(request.path)
    return await execute_csv_import(file_path=file_path, request=request)


@app.post("/api/import/upload-csv", response_model=CsvImportResponse)
async def import_uploaded_csv(
    file: UploadFile = File(...),
    dry_run: bool = Form(True),
    delimiter: str = Form(","),
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
        default_data_source=default_data_source,
        default_currency=default_currency,
        archive_after_success=archive_after_success,
    )

    return await execute_csv_import(file_path=destination, request=request)


@app.post("/api/planning/scenarios", response_model=PlanningResponse)
def plan_scenarios(request: ScenarioRequest) -> PlanningResponse:
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

    return scenario_engine.run(
        current_portfolio_value_usd=current_value,
        annual_contribution_usd=request.annual_contribution_usd,
        years=request.years,
        hsa_extra_contribution_usd=request.hsa_extra_contribution_usd,
    )


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

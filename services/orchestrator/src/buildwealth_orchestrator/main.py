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
from buildwealth_orchestrator.services.workflow_runner import WorkflowRunner
from buildwealth_orchestrator.services.plan_workspace import (
    PlanNotFoundError,
    PlanWorkspace,
)
from buildwealth_orchestrator.settings import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)

web_dir = Path(__file__).resolve().parent / "web"
if web_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


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
        "You are BuildWealth Copilot, a single-user financial research and planning assistant. "
        "Use tools to ground answers in real portfolio data before making claims. "
        "Be explicit about assumptions and uncertainty. "
        "Do not provide legal/tax advice; provide analytical insights and scenarios."
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

    save_to_plan = bool(arguments.get("save_to_plan", True))
    if save_to_plan:
        requested_plan_id = arguments.get("plan_id")
        plan_id = str(requested_plan_id).strip() if isinstance(requested_plan_id, str) else ""
        if not plan_id:
            active_id = plan_workspace.get_active_plan_id()
            plan_id = active_id or ""
        if plan_id:
            artifact = plan_workspace.write_artifact(
                plan_id=plan_id,
                title=f"{workflow_id.replace('_', ' ').title()} Report",
                markdown=result.get("report_markdown", ""),
                kind=workflow_id,
            )
            result["artifact"] = artifact

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
            "Fields: workflow_id (required), optional plan_id, use_live_snapshot, save_to_plan, params object."
        ),
        parameters={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string"},
                "plan_id": {"type": "string"},
                "use_live_snapshot": {"type": "boolean"},
                "save_to_plan": {"type": "boolean"},
                "params": {"type": "object"},
            },
            "required": ["workflow_id"],
            "additionalProperties": False,
        },
        handler=tool_run_workflow,
    )


configure_copilot_tools()


@app.on_event("startup")
async def on_startup() -> None:
    settings.import_inbox_dir.mkdir(parents=True, exist_ok=True)
    settings.import_archive_dir.mkdir(parents=True, exist_ok=True)
    settings.conversation_dir.mkdir(parents=True, exist_ok=True)
    settings.plans_dir.mkdir(parents=True, exist_ok=True)

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

    artifact_payload: dict[str, object] | None = None
    if request.save_to_plan:
        resolved_plan_id = request.plan_id or plan_workspace.get_active_plan_id()
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

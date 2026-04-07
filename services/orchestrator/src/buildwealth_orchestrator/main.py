from __future__ import annotations

import asyncio
import re
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from buildwealth_orchestrator.clients.ghostfolio import GhostfolioClient
from buildwealth_orchestrator.clients.ignidash import IgnidashClient
from buildwealth_orchestrator.schemas import (
    ChatRequest,
    ChatResponse,
    CsvImportRequest,
    CsvImportResponse,
    OptionsChainRequest,
    PlanningResponse,
    PortfolioSnapshot,
    ResearchResponse,
    ScenarioRequest,
    SyncStatusResponse,
)
from buildwealth_orchestrator.services.coordinator import Coordinator
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


@app.on_event("startup")
async def on_startup() -> None:
    settings.import_inbox_dir.mkdir(parents=True, exist_ok=True)
    settings.import_archive_dir.mkdir(parents=True, exist_ok=True)

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

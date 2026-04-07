from __future__ import annotations

from fastapi import FastAPI, HTTPException

from buildwealth_orchestrator.clients.ghostfolio import GhostfolioClient
from buildwealth_orchestrator.clients.ignidash import IgnidashClient
from buildwealth_orchestrator.schemas import (
    ChatRequest,
    ChatResponse,
    OptionsChainRequest,
    PlanningResponse,
    PortfolioSnapshot,
    ResearchResponse,
    ScenarioRequest,
)
from buildwealth_orchestrator.services.coordinator import Coordinator
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/snapshot/live", response_model=PortfolioSnapshot)
async def get_live_snapshot() -> PortfolioSnapshot:
    return await build_live_snapshot()


@app.post("/api/snapshot/sync")
async def sync_snapshot() -> dict[str, str | dict[str, str]]:
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

    return {
        "snapshot": str(snapshot_path),
        "ignidash_import_payload": str(ignidash_path),
        "ignidash_default_plan": default_plan_response,
    }


@app.get("/api/snapshot/latest", response_model=PortfolioSnapshot)
def get_latest_snapshot() -> PortfolioSnapshot:
    try:
        return snapshot_store.latest()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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

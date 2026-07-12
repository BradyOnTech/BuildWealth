"""Snapshots routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "sync_status",
    "get_live_snapshot",
    "sync_snapshot",
    "get_latest_snapshot",
    "get_snapshot_history",
    "backfill_snapshot_history_route",
]


@router.get("/api/sync/status", response_model=m.SyncStatusResponse)
def sync_status() -> m.SyncStatusResponse:
    return m.get_sync_status()


@router.get("/api/snapshot/live", response_model=m.PortfolioSnapshot)
async def get_live_snapshot(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioSnapshot:
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(services, permission="portfolio.read")
        return await m.build_live_snapshot(resolved_services.portfolio_store)
    return await m.build_live_snapshot()


@router.post("/api/snapshot/sync")
async def sync_snapshot(
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, str | dict[str, str]]:
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(
            services,
            permission="portfolio.write",
            http_request=http_request,
            require_write_token=True,
        )
        try:
            return await m.execute_sync(
                trigger="manual",
                store=resolved_services.portfolio_store,
                snapshots=resolved_services.snapshot_store,
            )
        except Exception as exc:
            raise m.HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc
    try:
        return await m.execute_sync(trigger="manual")
    except Exception as exc:
        raise m.HTTPException(status_code=502, detail=f"Sync failed: {exc}") from exc


@router.get("/api/snapshot/latest", response_model=m.PortfolioSnapshot)
def get_latest_snapshot(
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.PortfolioSnapshot:
    resolved_store = m.snapshot_store
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(services, permission="portfolio.read")
        resolved_store = resolved_services.snapshot_store
    try:
        return resolved_store.latest()
    except FileNotFoundError as exc:
        raise m.HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/snapshot/history", response_model=m.SnapshotHistoryResponse)
def get_snapshot_history(
    limit: int = 30,
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> m.SnapshotHistoryResponse:
    resolved_store = None
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(services, permission="portfolio.read")
        resolved_store = resolved_services.snapshot_store
    return m.build_snapshot_history_payload(limit=max(2, min(limit, 365)), store=resolved_store)


@router.post("/api/snapshot/backfill-history")
def backfill_snapshot_history_route(
    request: dict[str, m.Any] | None = None,
    http_request: m.Request = m.Depends(m.get_current_request),
    services: m.WorkspaceServices = m.Depends(m.get_workspace_services),
) -> dict[str, m.Any]:
    resolved_portfolio_store = m.portfolio_store
    resolved_snapshot_store = m.snapshot_store
    if hasattr(services, "context"):
        resolved_services = m.route_workspace_services(
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
            raise m.HTTPException(status_code=400, detail="days must be a positive integer")

    overwrite = bool(payload.get("overwrite", True))

    start_date_value = payload.get("start_date")
    end_date_value = payload.get("end_date")

    def _parse_optional_date(raw: m.Any, field: str) -> m.date | None:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        try:
            return m.datetime.fromisoformat(text[:10]).date()
        except ValueError as exc:
            raise m.HTTPException(status_code=400, detail=f"{field} must be YYYY-MM-DD") from exc

    start_date = _parse_optional_date(start_date_value, "start_date")
    end_date = _parse_optional_date(end_date_value, "end_date")
    if start_date and end_date and start_date > end_date:
        raise m.HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    return m.backfill_snapshot_history(
        portfolio_store=resolved_portfolio_store,
        snapshot_store=resolved_snapshot_store,
        research=m.research_service,
        start_date=start_date,
        end_date=end_date,
        days=days,
        overwrite=overwrite,
    )

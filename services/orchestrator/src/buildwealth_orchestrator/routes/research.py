"""Research routes, extracted from main.py.

Handlers resolve main-module helpers through `m` at call time so test
monkeypatching of main attributes keeps working.
"""

from __future__ import annotations

from fastapi import APIRouter

import buildwealth_orchestrator.main as m

router = APIRouter()

__all__ = [
    "get_research_watchlist_rank",
    "options_chain",
    "quote",
    "price_history",
    "research_compare",
    "research_evidence_packet",
    "research_dossier",
    "research_dossier_lookup",
]


@router.get("/api/research/watchlist-rank", response_model=m.WatchlistRankResponse)
def get_research_watchlist_rank(
    period: str = "2y",
    interval: str = "1d",
    limit: int = 200,
) -> m.WatchlistRankResponse:
    payload = m.build_portfolio_watchlist_payload(
        period=period,
        interval=interval,
        sort="ranked",
        limit=limit,
    )
    return m.WatchlistRankResponse(**payload)


@router.post("/api/research/options-chain", response_model=m.ResearchResponse)
def options_chain(request: m.OptionsChainRequest) -> m.ResearchResponse:
    return m.research_service.options_chain(request.symbol)


@router.post("/api/research/quote", response_model=m.ResearchResponse)
def quote(request: m.OptionsChainRequest) -> m.ResearchResponse:
    return m.research_service.quote(request.symbol)


@router.post("/api/research/price-history", response_model=m.ResearchResponse)
def price_history(request: m.PriceHistoryRequest) -> m.ResearchResponse:
    return m.research_service.price_history(
        symbol=request.symbol,
        period=request.period,
        interval=request.interval,
    )


@router.post("/api/research/compare", response_model=m.ResearchCompareResponse)
def research_compare(request: m.ResearchCompareRequest) -> m.ResearchCompareResponse:
    if len(request.symbols) < 2:
        raise m.HTTPException(status_code=400, detail="Research compare requires at least 2 symbols.")

    return m.research_service.compare(
        symbols=request.symbols,
        period=request.period,
        interval=request.interval,
        baseline_symbol=request.baseline_symbol,
    )


@router.post("/api/research/evidence-packet", response_model=m.ResearchEvidencePacket)
def research_evidence_packet(request: m.ResearchEvidencePacketRequest) -> m.ResearchEvidencePacket:
    if not request.symbol:
        raise m.HTTPException(status_code=400, detail="Research evidence packet requires a symbol.")

    try:
        return m.research_service.evidence_packet(
            symbol=request.symbol,
            period=request.period,
            interval=request.interval,
        )
    except ValueError as exc:
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/research/dossier", response_model=m.ResearchDossierResponse)
def research_dossier(request: m.ResearchDossierRequest) -> m.ResearchDossierResponse:
    if len(request.symbols) < 2:
        raise m.HTTPException(status_code=400, detail="Research dossier requires at least 2 symbols.")

    try:
        return m.build_research_dossier_payload(
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
        raise m.HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/research/dossiers", response_model=m.ResearchDossierLookupResponse)
def research_dossier_lookup(
    plan_id: str | None = None,
    limit: int = 5,
    include_content: bool = False,
) -> m.ResearchDossierLookupResponse:
    payload = m.build_research_dossier_lookup_payload(
        plan_id=plan_id,
        limit=limit,
        include_content=include_content,
    )
    return m.ResearchDossierLookupResponse(**payload)

from __future__ import annotations

from typing import TypedDict, cast

from buildwealth_orchestrator.schemas import ChatResponse, PortfolioSnapshot
from buildwealth_orchestrator.services.portfolio_metrics import concentration_metrics


def _format_currency(value: float) -> str:
    return f"${value:,.0f}"


class ConcentrationPosition(TypedDict):
    symbol: str | None
    name: str | None
    weight: float
    value_usd: float


class ConcentrationMetrics(TypedDict):
    top_positions: list[ConcentrationPosition]
    herfindahl_index: float
    effective_number_of_positions: float


class PlanningScenario(TypedDict, total=False):
    label: str
    future_value_usd: float


class PlanningPayload(TypedDict, total=False):
    scenarios: list[PlanningScenario]


class ResearchPayload(TypedDict, total=False):
    available: bool
    message: str
    records: list[object]


class Coordinator:
    def answer(
        self,
        question: str,
        snapshot: PortfolioSnapshot,
        planning: PlanningPayload | None = None,
        research: ResearchPayload | None = None,
    ) -> ChatResponse:
        q = question.lower()
        holdings_dicts = [holding.model_dump(mode="python") for holding in snapshot.holdings]
        concentration = cast(ConcentrationMetrics, concentration_metrics(holdings_dicts))

        if any(token in q for token in ["allocation", "concentration", "portfolio", "holdings"]):
            top = concentration["top_positions"][:5]
            top_lines = ", ".join(
                [f"{str(item['symbol'] or '?')} ({item['weight'] * 100:.1f}%)" for item in top]
            )
            answer = (
                f"Current portfolio value is {_format_currency(snapshot.total_value_usd)} with "
                f"{len(snapshot.holdings)} holdings. Top weights: {top_lines}. "
                f"Herfindahl index: {concentration['herfindahl_index']} "
                f"(effective positions: {concentration['effective_number_of_positions']})."
            )
            return ChatResponse(answer=answer, route="portfolio", data={"concentration": dict(concentration)})

        if any(token in q for token in ["hsa", "retirement", "projection", "plan", "contribution"]):
            if not planning:
                return ChatResponse(
                    answer="Planning engine did not run. Provide planning data or rerun with refresh enabled.",
                    route="planning",
                    data={},
                )

            scenarios = planning.get("scenarios", [])
            scenario_rows = [item for item in scenarios if isinstance(item, dict)] if isinstance(scenarios, list) else []
            lookup = {str(item.get("label") or ""): item for item in scenario_rows}
            baseline = lookup.get("baseline")
            optimistic = lookup.get("optimistic")
            conservative = lookup.get("conservative")
            hsa = lookup.get("hsa_delta")
            if not all(isinstance(item, dict) for item in [baseline, optimistic, conservative, hsa]):
                return ChatResponse(
                    answer="Planning data is missing one or more scenario rows.",
                    route="planning",
                    data=dict(planning),
                )

            answer = (
                f"Baseline projection: {_format_currency(baseline['future_value_usd'])}; "
                f"optimistic: {_format_currency(optimistic['future_value_usd'])}; "
                f"conservative: {_format_currency(conservative['future_value_usd'])}. "
                f"With extra HSA strategy, projected value is {_format_currency(hsa['future_value_usd'])}."
            )
            return ChatResponse(answer=answer, route="planning", data=dict(planning))

        if any(token in q for token in ["option", "options", "chain", "sharpe", "research"]):
            if not research:
                return ChatResponse(
                    answer="Research agent did not run yet. Call /api/research/options-chain first.",
                    route="research",
                    data={},
                )
            available = bool(research.get("available", False))
            message = str(research.get("message", ""))
            records = research.get("records", [])
            count = len(records) if isinstance(records, list) else 0
            answer = f"Research status: {'available' if available else 'unavailable'}. {message}. Rows: {count}."
            return ChatResponse(answer=answer, route="research", data=dict(research))

        answer = (
            f"Portfolio value: {_format_currency(snapshot.total_value_usd)}. "
            f"Net performance: {_format_currency(snapshot.net_performance_usd)} "
            f"({snapshot.net_performance_percent:.2f}%). Ask about allocation, planning, or options research."
        )
        return ChatResponse(answer=answer, route="summary", data={"concentration": dict(concentration)})

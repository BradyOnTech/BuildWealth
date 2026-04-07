from __future__ import annotations

from typing import Any

from buildwealth_orchestrator.schemas import ChatResponse, PortfolioSnapshot
from buildwealth_orchestrator.services.research import concentration_metrics


def _format_currency(value: float) -> str:
    return f"${value:,.0f}"


class Coordinator:
    def answer(
        self,
        question: str,
        snapshot: PortfolioSnapshot,
        planning: dict[str, Any] | None = None,
        research: dict[str, Any] | None = None,
    ) -> ChatResponse:
        q = question.lower()
        holdings_dicts = [holding.model_dump() for holding in snapshot.holdings]
        concentration = concentration_metrics(holdings_dicts)

        if any(token in q for token in ["allocation", "concentration", "portfolio", "holdings"]):
            top = concentration["top_positions"][:5]
            top_lines = ", ".join([f"{item['symbol']} ({item['weight'] * 100:.1f}%)" for item in top])
            answer = (
                f"Current portfolio value is {_format_currency(snapshot.total_value_usd)} with "
                f"{len(snapshot.holdings)} holdings. Top weights: {top_lines}. "
                f"Herfindahl index: {concentration['herfindahl_index']} "
                f"(effective positions: {concentration['effective_number_of_positions']})."
            )
            return ChatResponse(answer=answer, route="portfolio", data={"concentration": concentration})

        if any(token in q for token in ["hsa", "retirement", "projection", "plan", "contribution"]):
            if not planning:
                return ChatResponse(
                    answer="Planning engine did not run. Provide planning data or rerun with refresh enabled.",
                    route="planning",
                    data={},
                )

            scenarios = planning.get("scenarios", [])
            lookup = {item["label"]: item for item in scenarios}
            baseline = lookup.get("baseline")
            optimistic = lookup.get("optimistic")
            conservative = lookup.get("conservative")
            hsa = lookup.get("hsa_delta")

            answer = (
                f"Baseline projection: {_format_currency(baseline['future_value_usd'])}; "
                f"optimistic: {_format_currency(optimistic['future_value_usd'])}; "
                f"conservative: {_format_currency(conservative['future_value_usd'])}. "
                f"With extra HSA strategy, projected value is {_format_currency(hsa['future_value_usd'])}."
            )
            return ChatResponse(answer=answer, route="planning", data=planning)

        if any(token in q for token in ["option", "options", "chain", "sharpe", "research"]):
            if not research:
                return ChatResponse(
                    answer="Research agent did not run yet. Call /api/research/options-chain first.",
                    route="research",
                    data={},
                )
            available = research.get("available", False)
            message = research.get("message", "")
            count = len(research.get("records", []))
            answer = f"Research status: {'available' if available else 'unavailable'}. {message}. Rows: {count}."
            return ChatResponse(answer=answer, route="research", data=research)

        answer = (
            f"Portfolio value: {_format_currency(snapshot.total_value_usd)}. "
            f"Net performance: {_format_currency(snapshot.net_performance_usd)} "
            f"({snapshot.net_performance_percent:.2f}%). Ask about allocation, planning, or options research."
        )
        return ChatResponse(answer=answer, route="summary", data={"concentration": concentration})

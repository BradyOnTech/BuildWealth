from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from buildwealth_orchestrator.schemas import PortfolioSnapshot
from buildwealth_orchestrator.services.research import concentration_metrics
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowRunner:
    def __init__(
        self,
        scenario_engine: ScenarioEngine,
        default_annual_contribution_usd: float,
        default_years: int,
        default_hsa_delta: float,
    ):
        self.scenario_engine = scenario_engine
        self.default_annual_contribution_usd = default_annual_contribution_usd
        self.default_years = default_years
        self.default_hsa_delta = default_hsa_delta

    def templates(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "risk_concentration_review",
                "title": "Risk Concentration Review",
                "description": (
                    "Evaluate portfolio concentration risk from latest holdings and flag potential over-exposure."
                ),
                "default_params": {
                    "max_single_holding_percent": 25.0,
                    "max_top3_percent": 60.0,
                },
            },
            {
                "id": "contribution_optimization",
                "title": "Contribution Optimization",
                "description": (
                    "Compare annual contribution levels and HSA optimization deltas against long-term outcomes."
                ),
                "default_params": {
                    "years": self.default_years,
                    "annual_contribution_usd": self.default_annual_contribution_usd,
                    "increment_options_usd": [0, 1000, 3000, 5000],
                    "hsa_extra_contribution_usd": self.default_hsa_delta,
                },
            },
        ]

    @staticmethod
    def _round(value: float) -> float:
        return round(float(value), 2)

    def run(
        self,
        workflow_id: str,
        snapshot: PortfolioSnapshot,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved = (params or {}).copy()
        if workflow_id == "risk_concentration_review":
            return self._run_risk_concentration(snapshot=snapshot, params=resolved)
        if workflow_id == "contribution_optimization":
            return self._run_contribution_optimization(snapshot=snapshot, params=resolved)
        raise ValueError(f"Unsupported workflow template: {workflow_id}")

    def _run_risk_concentration(
        self,
        snapshot: PortfolioSnapshot,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        max_single = float(params.get("max_single_holding_percent", 25.0))
        max_top3 = float(params.get("max_top3_percent", 60.0))

        holding_payloads = [holding.model_dump(mode="python") for holding in snapshot.holdings]
        metrics = concentration_metrics(holding_payloads)
        top_positions = metrics.get("top_positions", [])

        top1_pct = self._round(float(top_positions[0]["weight"]) * 100) if top_positions else 0.0
        top3_pct = self._round(sum(float(item["weight"]) for item in top_positions[:3]) * 100) if top_positions else 0.0

        breaches: list[str] = []
        if top1_pct > max_single:
            breaches.append(
                f"Top holding concentration is {top1_pct:.2f}% (threshold {max_single:.2f}%)."
            )
        if top3_pct > max_top3:
            breaches.append(
                f"Top 3 holdings concentration is {top3_pct:.2f}% (threshold {max_top3:.2f}%)."
            )

        risk_level = "high" if breaches else "moderate"
        if not breaches and top1_pct <= max_single * 0.75 and top3_pct <= max_top3 * 0.75:
            risk_level = "low"

        recommendations: list[str] = []
        if breaches:
            recommendations.append("Set a rebalancing target for the largest position over the next contribution cycle.")
            recommendations.append("Direct new contributions to underweight broad-market positions.")
            recommendations.append("Re-run this workflow after the next sync to track concentration trend.")
        else:
            recommendations.append("Current concentration appears within configured limits.")
            recommendations.append("Keep monitoring top holdings as new contributions are added.")

        report_lines = [
            "# Workflow Report: Risk Concentration Review",
            "",
            f"Generated: {utc_now_iso()}",
            "",
            "## Snapshot",
            "",
            f"- As of: {snapshot.as_of.isoformat()}",
            f"- Portfolio value: ${snapshot.total_value_usd:,.2f}",
            f"- Holdings count: {len(snapshot.holdings)}",
            "",
            "## Concentration Metrics",
            "",
            f"- Top holding: {top1_pct:.2f}%",
            f"- Top 3 holdings: {top3_pct:.2f}%",
            f"- Herfindahl index: {float(metrics.get('herfindahl_index', 0.0)):.4f}",
            f"- Effective positions: {float(metrics.get('effective_number_of_positions', 0.0)):.2f}",
            f"- Risk level: {risk_level}",
            "",
            "## Top Positions",
            "",
        ]

        if top_positions:
            for position in top_positions[:8]:
                weight_pct = float(position.get("weight", 0.0)) * 100
                report_lines.append(
                    f"- {position.get('symbol', 'UNKNOWN')}: {weight_pct:.2f}% (${float(position.get('value_usd', 0.0)):,.2f})"
                )
        else:
            report_lines.append("- No holdings available.")

        report_lines.extend(["", "## Breaches", ""])
        if breaches:
            report_lines.extend([f"- {item}" for item in breaches])
        else:
            report_lines.append("- No threshold breaches detected.")

        report_lines.extend(["", "## Recommendations", ""])
        report_lines.extend([f"- {item}" for item in recommendations])
        report_lines.append("")

        summary = (
            f"Risk level is {risk_level}. Top holding {top1_pct:.2f}%, top 3 holdings {top3_pct:.2f}%."
        )

        return {
            "workflow_id": "risk_concentration_review",
            "summary": summary,
            "generated_at": utc_now_iso(),
            "data": {
                "risk_level": risk_level,
                "top_holding_percent": top1_pct,
                "top3_percent": top3_pct,
                "breaches": breaches,
                "recommendations": recommendations,
                "metrics": metrics,
            },
            "report_markdown": "\n".join(report_lines),
        }

    def _run_contribution_optimization(
        self,
        snapshot: PortfolioSnapshot,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        years = int(params.get("years", self.default_years))
        base_contribution = float(params.get("annual_contribution_usd", self.default_annual_contribution_usd))
        hsa_extra = float(params.get("hsa_extra_contribution_usd", self.default_hsa_delta))

        increments_raw = params.get("increment_options_usd", [0, 1000, 3000, 5000])
        increments: list[float] = []
        if isinstance(increments_raw, list):
            for item in increments_raw:
                try:
                    increments.append(float(item))
                except Exception:
                    continue
        if not increments:
            increments = [0.0, 1000.0, 3000.0, 5000.0]

        runs: list[dict[str, Any]] = []
        for increment in sorted(set(increments)):
            annual = base_contribution + increment
            planning = self.scenario_engine.run(
                current_portfolio_value_usd=snapshot.total_value_usd,
                annual_contribution_usd=annual,
                years=years,
                hsa_extra_contribution_usd=0.0,
            )
            baseline = next((item for item in planning.scenarios if item.label == "baseline"), None)
            if baseline is None:
                continue
            runs.append(
                {
                    "increment_usd": self._round(increment),
                    "annual_contribution_usd": self._round(annual),
                    "future_value_usd": self._round(baseline.future_value_usd),
                    "real_value_usd": self._round(baseline.real_value_usd),
                    "monte_carlo_p50_usd": self._round(float(planning.monte_carlo.get("p50_future_value_usd", 0.0))),
                }
            )

        if not runs:
            raise ValueError("Contribution optimization failed to compute any scenario runs.")

        best_run = max(runs, key=lambda item: item["real_value_usd"])
        baseline_run = min(runs, key=lambda item: item["increment_usd"])
        best_delta_real = self._round(best_run["real_value_usd"] - baseline_run["real_value_usd"])

        hsa_plan = self.scenario_engine.run(
            current_portfolio_value_usd=snapshot.total_value_usd,
            annual_contribution_usd=base_contribution,
            years=years,
            hsa_extra_contribution_usd=hsa_extra,
        )
        hsa_scenario = next((item for item in hsa_plan.scenarios if item.label == "hsa_delta"), None)

        report_lines = [
            "# Workflow Report: Contribution Optimization",
            "",
            f"Generated: {utc_now_iso()}",
            "",
            "## Inputs",
            "",
            f"- Current portfolio value: ${snapshot.total_value_usd:,.2f}",
            f"- Base annual contribution: ${base_contribution:,.2f}",
            f"- Years modeled: {years}",
            f"- HSA extra contribution analyzed: ${hsa_extra:,.2f}",
            "",
            "## Contribution Comparisons",
            "",
            "| Extra Contribution | Annual Contribution | Future Value | Real Value | Monte Carlo P50 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for run in runs:
            report_lines.append(
                f"| ${run['increment_usd']:,.0f} | ${run['annual_contribution_usd']:,.0f} | ${run['future_value_usd']:,.0f} | ${run['real_value_usd']:,.0f} | ${run['monte_carlo_p50_usd']:,.0f} |"
            )

        report_lines.extend(
            [
                "",
                "## Recommendation",
                "",
                f"- Best modeled contribution increase: +${best_run['increment_usd']:,.0f} per year.",
                f"- Estimated real-value gain vs baseline: ${best_delta_real:,.0f}.",
            ]
        )

        if hsa_scenario is not None:
            report_lines.append(
                f"- HSA strategy real value estimate: ${float(hsa_scenario.real_value_usd):,.0f} at {years} years."
            )

        report_lines.extend(
            [
                "",
                "## Notes",
                "",
                "- Results are deterministic projection + Monte Carlo summary, not financial advice.",
                "- Re-run after major income/portfolio changes or assumption updates.",
                "",
            ]
        )

        summary = (
            f"Best modeled contribution increase is +${best_run['increment_usd']:,.0f}/yr "
            f"with about ${best_delta_real:,.0f} higher real value versus baseline."
        )

        return {
            "workflow_id": "contribution_optimization",
            "summary": summary,
            "generated_at": utc_now_iso(),
            "data": {
                "years": years,
                "base_annual_contribution_usd": self._round(base_contribution),
                "runs": runs,
                "best_run": best_run,
                "real_value_delta_vs_baseline": best_delta_real,
                "hsa_scenario": (hsa_scenario.model_dump(mode="json") if hsa_scenario is not None else None),
            },
            "report_markdown": "\n".join(report_lines),
        }

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import median

from buildwealth_orchestrator.schemas import PlanningResponse, ScenarioResult


@dataclass
class ScenarioAssumptions:
    years: int
    annual_contribution_usd: float
    expected_return: float
    inflation: float


class ScenarioEngine:
    def __init__(
        self,
        years_to_retirement: int,
        annual_contribution_usd: float,
        baseline_return: float,
        optimistic_return: float,
        conservative_return: float,
        return_volatility: float,
        inflation: float,
        monte_carlo_runs: int,
        hsa_delta_default: float,
        marginal_tax_rate: float,
    ):
        self.years_to_retirement = years_to_retirement
        self.annual_contribution_usd = annual_contribution_usd
        self.baseline_return = baseline_return
        self.optimistic_return = optimistic_return
        self.conservative_return = conservative_return
        self.return_volatility = return_volatility
        self.inflation = inflation
        self.monte_carlo_runs = monte_carlo_runs
        self.hsa_delta_default = hsa_delta_default
        self.marginal_tax_rate = marginal_tax_rate

    @staticmethod
    def _future_value(current_value: float, annual_contribution: float, years: int, expected_return: float) -> float:
        if years <= 0:
            return current_value

        growth = (1 + expected_return) ** years
        principal_growth = current_value * growth

        if expected_return == 0:
            contribution_growth = annual_contribution * years
        else:
            contribution_growth = annual_contribution * ((growth - 1) / expected_return)

        return principal_growth + contribution_growth

    def _real_value(self, nominal_future_value: float, years: int, inflation: float) -> float:
        return nominal_future_value / ((1 + inflation) ** years)

    def _scenario(self, label: str, current_value: float, assumptions: ScenarioAssumptions) -> ScenarioResult:
        future_value = self._future_value(
            current_value=current_value,
            annual_contribution=assumptions.annual_contribution_usd,
            years=assumptions.years,
            expected_return=assumptions.expected_return,
        )

        return ScenarioResult(
            label=label,
            future_value_usd=round(future_value, 2),
            real_value_usd=round(self._real_value(future_value, assumptions.years, assumptions.inflation), 2),
            assumptions={
                "years": assumptions.years,
                "annual_contribution_usd": assumptions.annual_contribution_usd,
                "expected_return": assumptions.expected_return,
                "inflation": assumptions.inflation,
            },
        )

    def _monte_carlo(self, current_value: float, annual_contribution: float, years: int) -> dict[str, float | int]:
        outcomes: list[float] = []

        for _ in range(self.monte_carlo_runs):
            value = current_value
            for _ in range(years):
                yearly_return = random.gauss(self.baseline_return, self.return_volatility)
                yearly_return = max(-0.95, yearly_return)
                value = (value * (1 + yearly_return)) + annual_contribution
            outcomes.append(value)

        outcomes.sort()
        p10 = outcomes[max(0, math.floor(len(outcomes) * 0.10) - 1)]
        p50 = median(outcomes)
        p90 = outcomes[min(len(outcomes) - 1, math.ceil(len(outcomes) * 0.90) - 1)]

        return {
            "runs": self.monte_carlo_runs,
            "p10_future_value_usd": round(float(p10), 2),
            "p50_future_value_usd": round(float(p50), 2),
            "p90_future_value_usd": round(float(p90), 2),
        }

    def run(
        self,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float | None = None,
        years: int | None = None,
        hsa_extra_contribution_usd: float | None = None,
    ) -> PlanningResponse:
        resolved_years = years or self.years_to_retirement
        resolved_contribution = annual_contribution_usd or self.annual_contribution_usd
        resolved_hsa_delta = hsa_extra_contribution_usd or self.hsa_delta_default

        baseline = self._scenario(
            label="baseline",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution,
                expected_return=self.baseline_return,
                inflation=self.inflation,
            ),
        )

        optimistic = self._scenario(
            label="optimistic",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution,
                expected_return=self.optimistic_return,
                inflation=self.inflation,
            ),
        )

        conservative = self._scenario(
            label="conservative",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution,
                expected_return=self.conservative_return,
                inflation=self.inflation,
            ),
        )

        hsa_tax_benefit = resolved_hsa_delta * self.marginal_tax_rate
        hsa_total_delta = resolved_hsa_delta + hsa_tax_benefit
        hsa_delta = self._scenario(
            label="hsa_delta",
            current_value=current_portfolio_value_usd,
            assumptions=ScenarioAssumptions(
                years=resolved_years,
                annual_contribution_usd=resolved_contribution + hsa_total_delta,
                expected_return=self.baseline_return,
                inflation=self.inflation,
            ),
        )

        monte_carlo = self._monte_carlo(
            current_value=current_portfolio_value_usd,
            annual_contribution=resolved_contribution,
            years=resolved_years,
        )

        return PlanningResponse(
            scenarios=[baseline, optimistic, conservative, hsa_delta],
            monte_carlo=monte_carlo,
        )

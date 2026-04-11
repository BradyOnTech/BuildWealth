from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from buildwealth_orchestrator.schemas import PlanningResponse, ScenarioResult
from buildwealth_orchestrator.services.contribution_rules import (
    normalize_account_type,
    tax_treatment_for_account_type,
)
from buildwealth_orchestrator.services.engine_adapter import SidecarAdapter, SidecarAdapterError
from buildwealth_orchestrator.services.scenario_engine import ScenarioEngine


class IgnidashScenarioAccountV1(BaseModel):
    account_id: str
    account_type: str
    tax_treatment: Literal["taxable", "tax_deferred", "tax_free"] = "taxable"
    balance: float
    annual_contribution: float = 0.0


class IgnidashScenarioOverrideV1(BaseModel):
    scenario_id: str
    label: str
    overrides: dict[str, float | str | bool | None] = Field(default_factory=dict)


class IgnidashScenarioRequestV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    start_year: int
    horizon_years: int
    household: dict[str, int]
    accounts: list[IgnidashScenarioAccountV1]
    baseline_assumptions: dict[str, float]
    scenario_overrides: list[IgnidashScenarioOverrideV1]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scenario_overrides")
    @classmethod
    def _validate_overrides(cls, values: list[IgnidashScenarioOverrideV1]) -> list[IgnidashScenarioOverrideV1]:
        if not values:
            raise ValueError("scenario_overrides must not be empty")
        return values


class IgnidashScenarioSummaryV1(BaseModel):
    ending_balance_nominal: float
    ending_balance_real: float
    total_contributions: float | None = None
    total_taxes: float | None = None
    success_probability: float | None = None


class IgnidashScenarioTimelinePointV1(BaseModel):
    year: int
    age: int
    starting_balance: float
    ending_balance: float
    contributions: float | None = None
    income: float | None = None
    expenses: float | None = None
    taxes: float | None = None
    growth: float | None = None
    withdrawals: float | None = None
    ending_balance_real: float | None = None


class IgnidashScenarioOutputV1(BaseModel):
    scenario_id: str
    label: str
    summary: IgnidashScenarioSummaryV1
    timeline: list[IgnidashScenarioTimelinePointV1] = Field(default_factory=list)


class IgnidashScenarioResponseV1(BaseModel):
    contract_version: Literal[1] = 1
    request_id: str
    engine: Literal["ignidash"] = "ignidash"
    engine_status: Literal["ok", "degraded"]
    fallback_method: str | None = None
    scenarios: list[IgnidashScenarioOutputV1]
    warnings: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None


class IgnidashScenarioService:
    def __init__(
        self,
        *,
        scenario_engine: ScenarioEngine,
        sidecar_adapter: SidecarAdapter | None,
        sidecar_enabled: bool,
        sidecar_path: str,
        currency: str = "USD",
        default_tax_rate: float = 0.25,
    ) -> None:
        self.scenario_engine = scenario_engine
        self.sidecar_adapter = sidecar_adapter
        self.sidecar_enabled = sidecar_enabled
        self.sidecar_path = sidecar_path
        self.currency = str(currency or "USD").upper()
        self.default_tax_rate = float(default_tax_rate)

    async def run(
        self,
        *,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float | None = None,
        years: int | None = None,
        hsa_extra_contribution_usd: float | None = None,
        accounts: list[dict[str, Any]] | None = None,
        income_projection: dict[str, Any] | None = None,
        contribution_allocation: dict[str, Any] | None = None,
    ) -> PlanningResponse:
        local_result = self.scenario_engine.run(
            current_portfolio_value_usd=current_portfolio_value_usd,
            annual_contribution_usd=annual_contribution_usd,
            years=years,
            hsa_extra_contribution_usd=hsa_extra_contribution_usd,
        )

        if not self.sidecar_enabled or self.sidecar_adapter is None:
            return local_result.model_copy(
                update={
                    "engine": "local",
                    "engine_status": "ok",
                    "fallback_method": None,
                    "warnings": [],
                    "income_projection": income_projection,
                    "contribution_allocation": contribution_allocation,
                }
            )

        request_payload = self._build_request_payload(
            current_portfolio_value_usd=current_portfolio_value_usd,
            annual_contribution_usd=annual_contribution_usd,
            years=years,
            hsa_extra_contribution_usd=hsa_extra_contribution_usd,
            accounts=accounts,
            income_projection=income_projection,
            contribution_allocation=contribution_allocation,
        )

        try:
            response_payload = await self.sidecar_adapter.post_json(
                path=self.sidecar_path,
                request_payload=request_payload.model_dump(mode="json"),
                request_model=IgnidashScenarioRequestV1,
                response_model=IgnidashScenarioResponseV1,
            )
            scenarios = self._merge_sidecar_scenarios(
                local_scenarios=local_result.scenarios,
                sidecar_scenarios=response_payload.scenarios,
            )
            return PlanningResponse(
                scenarios=scenarios,
                monte_carlo=local_result.monte_carlo,
                engine="ignidash",
                engine_status=response_payload.engine_status,
                fallback_method=response_payload.fallback_method,
                warnings=list(response_payload.warnings),
                income_projection=income_projection,
                contribution_allocation=contribution_allocation,
            )
        except SidecarAdapterError as exc:
            return local_result.model_copy(
                update={
                    "engine": "local",
                    "engine_status": "degraded",
                    "fallback_method": "local_scenario_engine_fallback",
                    "warnings": [f"Ignidash scenario sidecar unavailable: {exc}"],
                    "income_projection": income_projection,
                    "contribution_allocation": contribution_allocation,
                }
            )

    def _build_request_payload(
        self,
        *,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float | None,
        years: int | None,
        hsa_extra_contribution_usd: float | None,
        accounts: list[dict[str, Any]] | None,
        income_projection: dict[str, Any] | None,
        contribution_allocation: dict[str, Any] | None,
    ) -> IgnidashScenarioRequestV1:
        resolved_years = int(self.scenario_engine.years_to_retirement if years is None else years)
        resolved_contribution = float(
            self.scenario_engine.annual_contribution_usd
            if annual_contribution_usd is None
            else annual_contribution_usd
        )
        resolved_hsa = float(
            self.scenario_engine.hsa_delta_default
            if hsa_extra_contribution_usd is None
            else hsa_extra_contribution_usd
        )

        first_year_income = 0.0
        if income_projection:
            first_year_income = float(income_projection.get("first_year_gross_income_usd") or 0.0)

        baseline_assumptions = {
            "annual_return_rate": float(self.scenario_engine.baseline_return),
            "annual_inflation_rate": float(self.scenario_engine.inflation),
            "effective_tax_rate": self.default_tax_rate,
            "annual_income": first_year_income,
            "annual_expenses": 0.0,
        }

        scenario_overrides = [
            IgnidashScenarioOverrideV1(
                scenario_id="baseline",
                label="baseline",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.baseline_return),
                    "annual_contribution": resolved_contribution,
                    "horizon_years": resolved_years,
                },
            ),
            IgnidashScenarioOverrideV1(
                scenario_id="optimistic",
                label="optimistic",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.optimistic_return),
                    "annual_contribution": resolved_contribution,
                    "horizon_years": resolved_years,
                },
            ),
            IgnidashScenarioOverrideV1(
                scenario_id="conservative",
                label="conservative",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.conservative_return),
                    "annual_contribution": resolved_contribution,
                    "horizon_years": resolved_years,
                },
            ),
            IgnidashScenarioOverrideV1(
                scenario_id="hsa_delta",
                label="hsa_delta",
                overrides={
                    "annual_return_rate": float(self.scenario_engine.baseline_return),
                    "annual_contribution": resolved_contribution + resolved_hsa,
                    "horizon_years": resolved_years,
                },
            ),
        ]

        mapped_accounts = self._map_accounts(
            current_portfolio_value_usd=current_portfolio_value_usd,
            annual_contribution_usd=resolved_contribution,
            accounts=accounts,
        )

        metadata: dict[str, Any] = {
            "source": "buildwealth_orchestrator",
            "annual_contribution_usd": resolved_contribution,
        }
        if income_projection:
            metadata["income_projection"] = income_projection
        if contribution_allocation:
            metadata["contribution_allocation"] = contribution_allocation

        return IgnidashScenarioRequestV1(
            request_id=uuid4().hex,
            currency=self.currency,
            start_year=datetime.now(timezone.utc).year,
            horizon_years=resolved_years,
            household={"current_age": 35, "retirement_age": 35 + resolved_years},
            accounts=mapped_accounts,
            baseline_assumptions=baseline_assumptions,
            scenario_overrides=scenario_overrides,
            metadata=metadata,
        )

    def _map_accounts(
        self,
        *,
        current_portfolio_value_usd: float,
        annual_contribution_usd: float,
        accounts: list[dict[str, Any]] | None,
    ) -> list[IgnidashScenarioAccountV1]:
        if not accounts:
            return [
                IgnidashScenarioAccountV1(
                    account_id="primary",
                    account_type="portfolio",
                    tax_treatment="taxable",
                    balance=float(current_portfolio_value_usd),
                    annual_contribution=annual_contribution_usd,
                )
            ]

        mapped: list[IgnidashScenarioAccountV1] = []
        for index, account in enumerate(accounts, start=1):
            account_id = str(account.get("account_id") or account.get("id") or f"account-{index}").strip()
            if not account_id:
                account_id = f"account-{index}"

            account_type = normalize_account_type(account.get("account_type") or account.get("type"))
            tax_treatment_raw = account.get("tax_treatment")
            if isinstance(tax_treatment_raw, str):
                candidate_treatment = tax_treatment_raw.strip()
            else:
                candidate_treatment = ""
            if candidate_treatment in {"taxable", "tax_deferred", "tax_free"}:
                tax_treatment = cast(Literal["taxable", "tax_deferred", "tax_free"], candidate_treatment)
            else:
                tax_treatment = tax_treatment_for_account_type(account_type)

            balance = float(account.get("balance_usd") or account.get("balance") or 0.0)
            annual_contribution = float(
                account.get("annual_contribution_usd")
                or account.get("annual_contribution")
                or account.get("total_contribution_usd")
                or 0.0
            )

            mapped.append(
                IgnidashScenarioAccountV1(
                    account_id=account_id,
                    account_type=account_type,
                    tax_treatment=tax_treatment,
                    balance=balance,
                    annual_contribution=annual_contribution,
                )
            )

        if mapped:
            return mapped
        return [
            IgnidashScenarioAccountV1(
                account_id="primary",
                account_type="portfolio",
                tax_treatment="taxable",
                balance=float(current_portfolio_value_usd),
                annual_contribution=annual_contribution_usd,
            )
        ]

    @staticmethod
    def _merge_sidecar_scenarios(
        *,
        local_scenarios: list[ScenarioResult],
        sidecar_scenarios: list[IgnidashScenarioOutputV1],
    ) -> list[ScenarioResult]:
        by_label: dict[str, IgnidashScenarioOutputV1] = {}
        for row in sidecar_scenarios:
            key = str(row.scenario_id or row.label).strip().lower()
            if key in {"baseline", "optimistic", "conservative", "hsa_delta"}:
                by_label[key] = row

        merged: list[ScenarioResult] = []
        for local in local_scenarios:
            key = str(local.label).strip().lower()
            sidecar = by_label.get(key)
            if sidecar is None:
                merged.append(local)
                continue

            merged.append(
                ScenarioResult(
                    label=local.label,
                    future_value_usd=round(float(sidecar.summary.ending_balance_nominal), 2),
                    real_value_usd=round(float(sidecar.summary.ending_balance_real), 2),
                    assumptions=dict(local.assumptions),
                )
            )

        return merged

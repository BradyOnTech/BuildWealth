from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.scenario_engine import (
    DEFAULT_SIMULATION_SEED,
    HISTORICAL_YEARS,
    MONTE_CARLO_VARIANT_ALIASES,
    SIMULATION_MODE_ALIASES,
)
from buildwealth_orchestrator.services.timeline_defaults import (
    TIMELINE_DEFAULT_IMPACT_BY_EVENT,
    TIMELINE_EVENT_TYPES,
    TIMELINE_FREQUENCIES,
    TIMELINE_IMPACT_TYPES,
)

PLAN_WORKSPACE_SCHEMA_VERSION = 2


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class PlanNotFoundError(FileNotFoundError):
    pass


class PlanWorkspace:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.base_dir / "index.json"
        self._initialize_index()

    def _initialize_index(self) -> None:
        if self.index_path.exists():
            return

        self._save_index(self._empty_index_payload())

    @staticmethod
    def _empty_index_payload() -> dict[str, Any]:
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "active_plan_id": None,
            "plans": [],
        }

    def _load_index(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            payload = self._empty_index_payload()
            self._save_index(payload)

        if not isinstance(payload, dict):
            payload = self._empty_index_payload()

        payload.setdefault("active_plan_id", None)
        payload.setdefault("plans", [])
        payload["schema_version"] = PLAN_WORKSPACE_SCHEMA_VERSION
        self._save_index(payload)
        return payload

    def _save_index(self, index_payload: dict[str, Any]) -> None:
        tmp_path = self.index_path.with_name(f"{self.index_path.name}.{uuid.uuid4().hex}.tmp")
        tmp_path.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")
        tmp_path.replace(self.index_path)

    def _plan_dir(self, plan_id: str) -> Path:
        return self.base_dir / plan_id

    def _artifacts_dir(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "artifacts"

    def _settings_path(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "settings.json"

    def _timeline_path(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "timeline.json"

    def _contribution_rules_path(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "contribution_rules.json"

    def _assumption_sets_path(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "assumption_sets.json"

    def _branch_templates_path(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "branch_templates.json"

    def _saved_simulations_path(self, plan_id: str) -> Path:
        return self._plan_dir(plan_id) / "saved_simulations.json"

    @staticmethod
    def _slug(value: str, default: str = "artifact") -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
        return cleaned or default

    @staticmethod
    def _find_plan_metadata(index_payload: dict[str, Any], plan_id: str) -> dict[str, Any]:
        for plan in index_payload.get("plans", []):
            if plan.get("id") == plan_id:
                return plan
        raise PlanNotFoundError(f"Plan not found: {plan_id}")

    def _touch_plan(self, index_payload: dict[str, Any], plan_id: str) -> dict[str, Any]:
        plan = self._find_plan_metadata(index_payload, plan_id)
        plan["updated_at"] = utc_now_iso()
        return plan

    @staticmethod
    def _template_plan_markdown(title: str, description: str) -> str:
        lines = [f"# {title}", ""]
        if description:
            lines.extend([description.strip(), ""])
        lines.extend(
            [
                "## Goal",
                "",
                "- Define the primary financial outcome this plan is trying to achieve.",
                "",
                "## Constraints",
                "",
                "- Add constraints (tax, liquidity, risk, timeline).",
                "",
                "## Strategy",
                "",
                "- Document the high-level approach and tradeoffs.",
                "",
                "## Questions For Copilot",
                "",
                "- Add the next research questions to run through the agent workflow.",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _template_plan_yaml() -> str:
        return "\n".join(
            [
                "currency: USD",
                "state: MN",
                "targets:",
                "  retirement_age: null",
                "  annual_savings_usd: null",
                "risk_limits:",
                "  max_single_holding_pct: null",
                "  max_equity_allocation_pct: null",
                "assumptions:",
                "  expected_return_baseline: null",
                "  expected_return_optimistic: null",
                "  expected_return_conservative: null",
                "notes: []",
                "",
            ]
        )

    @staticmethod
    def _template_tasks() -> str:
        return "\n".join(
            [
                "# Tasks",
                "",
                "- [ ] Run latest portfolio sync",
                "- [ ] Ask Copilot for concentration-risk review",
                "- [ ] Compare at least two contribution scenarios",
                "",
            ]
        )

    @staticmethod
    def _default_settings() -> dict[str, Any]:
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "annual_contribution_usd": None,
            "years": None,
            "hsa_extra_contribution_usd": None,
            "marginal_tax_rate": None,
            "state_tax_rate": None,
            "simulation_mode": None,
            "simulation_monte_carlo_variant": None,
            "simulation_historical_start_year": None,
            "simulation_seed": None,
            "household_mode": None,
            "household_partner_income_usd": None,
            "household_partner_income_growth_rate": None,
            "household_partner_retirement_age": None,
            "household_partner_social_security_annual_usd": None,
            "household_partner_social_security_claiming_age": None,
            "household_shared_goal_target_usd": None,
            "household_shared_goal_target_year": None,
            "roth_conversion_annual_amount_usd": None,
            "roth_conversion_start_age": None,
            "roth_conversion_end_age": None,
            "inflation_rate": None,
            "expected_return_baseline": None,
            "expected_return_optimistic": None,
            "expected_return_conservative": None,
            "filing_status": None,
            "withdrawal_strategy": None,
            "drawdown_order": None,
            "updated_at": utc_now_iso(),
        }

    @staticmethod
    def _default_timeline() -> dict[str, Any]:
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "events": [],
            "retirement": {
                "target_retirement_age": None,
                "withdrawal_strategy": None,
                "drawdown_order": None,
                "social_security_birth_year": None,
                "social_security_claiming_age": None,
                "social_security_life_expectancy_age": None,
                "social_security_fra_monthly_benefit_usd": None,
                "social_security_estimated_annual_earnings_usd": None,
                "rmd_birth_year": None,
                "rmd_start_age": None,
            },
        }

    @staticmethod
    def _default_contribution_rules() -> dict[str, Any]:
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "base_rule": {"type": "save"},
            "rules": [],
            "profile_id": None,
            "employer_match_target_usd": 6000.0,
            "age": 35,
        }

    @staticmethod
    def _default_assumption_sets() -> dict[str, Any]:
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "active_assumption_set_id": "default",
            "sets": [
                {
                    "id": "default",
                    "name": "Default",
                    "expected_return_baseline": None,
                    "expected_return_optimistic": None,
                    "expected_return_conservative": None,
                    "inflation_rate": None,
                    "marginal_tax_rate": None,
                    "state_tax_rate": None,
                    "simulation_mode": None,
                    "simulation_monte_carlo_variant": None,
                    "simulation_historical_start_year": None,
                    "simulation_seed": None,
                    "roth_conversion_annual_amount_usd": None,
                    "roth_conversion_start_age": None,
                    "roth_conversion_end_age": None,
                },
                {
                    "id": "historical_average",
                    "name": "Historical Average",
                    "expected_return_baseline": 0.07,
                    "expected_return_optimistic": 0.09,
                    "expected_return_conservative": 0.05,
                    "inflation_rate": 0.03,
                    "marginal_tax_rate": None,
                    "state_tax_rate": None,
                    "simulation_mode": None,
                    "simulation_monte_carlo_variant": None,
                    "simulation_historical_start_year": None,
                    "simulation_seed": None,
                    "roth_conversion_annual_amount_usd": None,
                    "roth_conversion_start_age": None,
                    "roth_conversion_end_age": None,
                },
                {
                    "id": "conservative",
                    "name": "Conservative",
                    "expected_return_baseline": 0.05,
                    "expected_return_optimistic": 0.06,
                    "expected_return_conservative": 0.04,
                    "inflation_rate": 0.025,
                    "marginal_tax_rate": None,
                    "state_tax_rate": None,
                    "simulation_mode": None,
                    "simulation_monte_carlo_variant": None,
                    "simulation_historical_start_year": None,
                    "simulation_seed": None,
                    "roth_conversion_annual_amount_usd": None,
                    "roth_conversion_start_age": None,
                    "roth_conversion_end_age": None,
                },
                {
                    "id": "stagflation",
                    "name": "Stagflation",
                    "expected_return_baseline": 0.04,
                    "expected_return_optimistic": 0.05,
                    "expected_return_conservative": 0.02,
                    "inflation_rate": 0.05,
                    "marginal_tax_rate": None,
                    "state_tax_rate": None,
                    "simulation_mode": None,
                    "simulation_monte_carlo_variant": None,
                    "simulation_historical_start_year": None,
                    "simulation_seed": None,
                    "roth_conversion_annual_amount_usd": None,
                    "roth_conversion_start_age": None,
                    "roth_conversion_end_age": None,
                },
                {
                    "id": "japan_scenario",
                    "name": "Japan Scenario",
                    "expected_return_baseline": 0.02,
                    "expected_return_optimistic": 0.035,
                    "expected_return_conservative": 0.0,
                    "inflation_rate": 0.005,
                    "marginal_tax_rate": None,
                    "state_tax_rate": None,
                    "simulation_mode": None,
                    "simulation_monte_carlo_variant": None,
                    "simulation_historical_start_year": None,
                    "simulation_seed": None,
                    "roth_conversion_annual_amount_usd": None,
                    "roth_conversion_start_age": None,
                    "roth_conversion_end_age": None,
                }
            ],
        }

    @staticmethod
    def _default_branch_templates() -> dict[str, Any]:
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "default_template_id": "early_retirement",
            "templates": [
                {
                    "id": "early_retirement",
                    "name": "Early retirement",
                    "description": "Test retiring five years sooner with a shorter saving runway.",
                    "branch_name": "Early Retirement",
                    "assumption_set_id": None,
                    "compare_settings": {"years": 20},
                    "branch_events": [
                        {
                            "label": "Retire Early",
                            "event_type": "retirement",
                            "impact_type": "contribution",
                            "amount_usd": -25000.0,
                            "recurring_frequency": "yearly",
                            "start_year_offset": 20,
                            "duration_months": None,
                            "account_id": None,
                            "notes": "Models a shorter contribution runway before retirement.",
                        }
                    ],
                },
                {
                    "id": "home_purchase",
                    "name": "Home purchase",
                    "description": "Down payment and ongoing home cost increase.",
                    "branch_name": "Home Purchase",
                    "assumption_set_id": None,
                    "compare_settings": {},
                    "branch_events": [
                        {
                            "label": "Down Payment",
                            "event_type": "purchase",
                            "impact_type": "expense",
                            "amount_usd": 80000.0,
                            "recurring_frequency": "one_time",
                            "start_year_offset": 2,
                            "duration_months": None,
                            "account_id": None,
                            "notes": "One-time home purchase cash need.",
                        },
                        {
                            "label": "Higher Housing Costs",
                            "event_type": "purchase",
                            "impact_type": "expense",
                            "amount_usd": 900.0,
                            "recurring_frequency": "monthly",
                            "start_year_offset": 2,
                            "duration_months": 360,
                            "account_id": None,
                            "notes": "Estimated monthly increase after buying.",
                        },
                    ],
                },
                {
                    "id": "job_change",
                    "name": "Job change",
                    "description": "Income change with a short transition gap.",
                    "branch_name": "Job Change",
                    "assumption_set_id": None,
                    "compare_settings": {},
                    "branch_events": [
                        {
                            "label": "Transition Gap",
                            "event_type": "job_change",
                            "impact_type": "income",
                            "amount_usd": -6000.0,
                            "recurring_frequency": "monthly",
                            "start_year_offset": 0,
                            "duration_months": 3,
                            "account_id": None,
                            "notes": "Three-month income interruption.",
                        },
                        {
                            "label": "New Compensation",
                            "event_type": "job_change",
                            "impact_type": "income",
                            "amount_usd": 15000.0,
                            "recurring_frequency": "yearly",
                            "start_year_offset": 0,
                            "duration_months": None,
                            "account_id": None,
                            "notes": "Annualized salary lift.",
                        }
                    ],
                },
                {
                    "id": "one_income_household",
                    "name": "One-income household",
                    "description": "Model losing one income while reducing annual contributions.",
                    "branch_name": "One-Income Household",
                    "assumption_set_id": None,
                    "compare_settings": {"annual_contribution_usd": 12000.0},
                    "branch_events": [
                        {
                            "label": "Partner Income Pause",
                            "event_type": "job_change",
                            "impact_type": "income",
                            "amount_usd": -55000.0,
                            "recurring_frequency": "yearly",
                            "start_year_offset": 0,
                            "duration_months": 60,
                            "account_id": None,
                            "notes": "Five years with one household income.",
                        }
                    ],
                },
                {
                    "id": "roth_conversion_ladder",
                    "name": "Roth conversion ladder",
                    "description": "Test annual Roth conversions during the conversion window.",
                    "branch_name": "Roth Conversion Ladder",
                    "assumption_set_id": None,
                    "compare_settings": {
                        "roth_conversion_annual_amount_usd": 25000.0,
                        "roth_conversion_start_age": 60,
                        "roth_conversion_end_age": 72,
                    },
                    "branch_events": [],
                },
                {
                    "id": "market_stress",
                    "name": "Market stress",
                    "description": "Lower returns and higher inflation for a stress test.",
                    "branch_name": "Market Stress",
                    "assumption_set_id": "stagflation",
                    "compare_settings": {
                        "expected_return_baseline": 0.04,
                        "expected_return_optimistic": 0.05,
                        "expected_return_conservative": 0.02,
                        "inflation_rate": 0.05,
                    },
                    "branch_events": [],
                },
                {
                    "id": "high_tax_retirement",
                    "name": "High-tax retirement",
                    "description": "Higher marginal and state tax assumptions during retirement.",
                    "branch_name": "High-Tax Retirement",
                    "assumption_set_id": None,
                    "compare_settings": {
                        "marginal_tax_rate": 0.32,
                        "state_tax_rate": 0.08,
                    },
                    "branch_events": [
                        {
                            "label": "Retirement Tax Drag",
                            "event_type": "milestone",
                            "impact_type": "expense",
                            "amount_usd": 6000.0,
                            "recurring_frequency": "yearly",
                            "start_year_offset": 20,
                            "duration_months": None,
                            "account_id": None,
                            "notes": "Additional annual tax drag estimate.",
                        },
                    ],
                },
            ],
        }

    @staticmethod
    def _default_saved_simulations() -> dict[str, Any]:
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "items": [],
        }

    @staticmethod
    def _format_setting_value(key: str, value: Any) -> str:
        if value is None:
            return "default"

        if key in {"annual_contribution_usd", "hsa_extra_contribution_usd", "roth_conversion_annual_amount_usd"}:
            return f"${float(value):,.2f}"
        if key in {
            "years",
            "roth_conversion_start_age",
            "roth_conversion_end_age",
        }:
            return f"{int(value)} years"
        if key == "simulation_historical_start_year":
            return str(int(value))
        if key == "simulation_seed":
            return str(int(value))
        if key in {
            "marginal_tax_rate",
            "state_tax_rate",
            "inflation_rate",
            "expected_return_baseline",
            "expected_return_optimistic",
            "expected_return_conservative",
        }:
            return f"{float(value) * 100:.2f}%"
        return str(value)

    def _read_settings(self, plan_id: str) -> dict[str, Any]:
        path = self._settings_path(plan_id)
        if not path.exists():
            settings = self._default_settings()
            path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            return settings

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = self._default_settings()

        defaults = self._default_settings()
        defaults.update(payload if isinstance(payload, dict) else {})
        defaults["schema_version"] = PLAN_WORKSPACE_SCHEMA_VERSION
        path.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
        return defaults

    def _read_or_initialize_json(self, path: Path, default_payload: dict[str, Any]) -> dict[str, Any]:
        if not path.exists():
            path.write_text(json.dumps(default_payload, indent=2), encoding="utf-8")
            return dict(default_payload)

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

        merged = dict(default_payload)
        if isinstance(payload, dict):
            merged.update(payload)
        merged["schema_version"] = PLAN_WORKSPACE_SCHEMA_VERSION
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return merged

    def _write_settings(self, plan_id: str, settings_payload: dict[str, Any]) -> None:
        path = self._settings_path(plan_id)
        settings_payload = dict(settings_payload)
        settings_payload["updated_at"] = utc_now_iso()
        path.write_text(json.dumps(settings_payload, indent=2), encoding="utf-8")

    @staticmethod
    def _parse_optional_date(raw_value: Any) -> date | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, datetime):
            return raw_value.date()
        if isinstance(raw_value, date):
            return raw_value
        text = str(raw_value).strip()
        if not text:
            return None
        text = text.replace("Z", "+00:00")
        try:
            if "T" in text:
                return datetime.fromisoformat(text).date()
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _sanitize_timeline_payload(self, timeline_payload: dict[str, Any]) -> dict[str, Any]:
        raw_events = timeline_payload.get("events")
        if raw_events is None:
            raw_events = []
        if not isinstance(raw_events, list):
            raise ValueError("timeline.events must be a list")

        events: list[dict[str, Any]] = []
        for index, raw in enumerate(raw_events, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"timeline.events[{index}] must be an object")

            event_date = self._parse_optional_date(raw.get("date"))
            if event_date is None:
                raise ValueError(f"timeline.events[{index}].date must be YYYY-MM-DD")

            event_type = str(raw.get("event_type") or "milestone").strip().lower()
            if event_type not in TIMELINE_EVENT_TYPES:
                raise ValueError(f"timeline.events[{index}].event_type is invalid")

            impact_raw = raw.get("impact_type")
            impact_type = str(impact_raw).strip().lower() if impact_raw is not None else ""
            if not impact_type:
                impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")
            if impact_type not in TIMELINE_IMPACT_TYPES:
                raise ValueError(f"timeline.events[{index}].impact_type is invalid")

            recurring_frequency = str(raw.get("recurring_frequency") or "one_time").strip().lower()
            if recurring_frequency not in TIMELINE_FREQUENCIES:
                raise ValueError(f"timeline.events[{index}].recurring_frequency is invalid")

            try:
                amount_usd = float(raw.get("amount_usd") or 0.0)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"timeline.events[{index}].amount_usd must be numeric") from exc

            end_date = self._parse_optional_date(raw.get("end_date"))
            if end_date and end_date < event_date:
                raise ValueError(f"timeline.events[{index}].end_date must be on or after date")

            label = str(raw.get("label") or "").strip()
            if not label:
                raise ValueError(f"timeline.events[{index}].label is required")

            event_id = str(raw.get("id") or "").strip() or f"event-{uuid.uuid4().hex[:10]}"
            events.append(
                {
                    "id": event_id,
                    "date": event_date.isoformat(),
                    "label": label,
                    "event_type": event_type,
                    "impact_type": impact_type,
                    "amount_usd": amount_usd,
                    "recurring_frequency": recurring_frequency,
                    "end_date": end_date.isoformat() if end_date else None,
                    "account_id": (str(raw.get("account_id") or "").strip() or None),
                    "notes": str(raw.get("notes") or "").strip(),
                }
            )

        retirement_payload = timeline_payload.get("retirement")
        if not isinstance(retirement_payload, dict):
            retirement_payload = {}

        target_retirement_age = retirement_payload.get("target_retirement_age")
        if target_retirement_age is None:
            resolved_retirement_age = None
        else:
            try:
                resolved_retirement_age = int(target_retirement_age)
            except (TypeError, ValueError) as exc:
                raise ValueError("timeline.retirement.target_retirement_age must be an integer") from exc
            if resolved_retirement_age < 18 or resolved_retirement_age > 100:
                raise ValueError("timeline.retirement.target_retirement_age must be between 18 and 100")

        withdrawal_strategy = str(retirement_payload.get("withdrawal_strategy") or "").strip() or None
        drawdown_order = str(retirement_payload.get("drawdown_order") or "").strip() or None

        social_security_birth_year = retirement_payload.get("social_security_birth_year")
        if social_security_birth_year is None:
            resolved_social_security_birth_year = None
        else:
            try:
                resolved_social_security_birth_year = int(social_security_birth_year)
            except (TypeError, ValueError) as exc:
                raise ValueError("timeline.retirement.social_security_birth_year must be an integer") from exc
            if resolved_social_security_birth_year < 1900 or resolved_social_security_birth_year > 2500:
                raise ValueError("timeline.retirement.social_security_birth_year must be between 1900 and 2500")

        social_security_claiming_age = retirement_payload.get("social_security_claiming_age")
        if social_security_claiming_age is None:
            resolved_social_security_claiming_age = None
        else:
            try:
                resolved_social_security_claiming_age = int(social_security_claiming_age)
            except (TypeError, ValueError) as exc:
                raise ValueError("timeline.retirement.social_security_claiming_age must be an integer") from exc
            if resolved_social_security_claiming_age < 62 or resolved_social_security_claiming_age > 70:
                raise ValueError("timeline.retirement.social_security_claiming_age must be between 62 and 70")

        social_security_life_expectancy_age = retirement_payload.get("social_security_life_expectancy_age")
        if social_security_life_expectancy_age is None:
            resolved_social_security_life_expectancy_age = None
        else:
            try:
                resolved_social_security_life_expectancy_age = int(social_security_life_expectancy_age)
            except (TypeError, ValueError) as exc:
                raise ValueError("timeline.retirement.social_security_life_expectancy_age must be an integer") from exc
            if (
                resolved_social_security_life_expectancy_age < 67
                or resolved_social_security_life_expectancy_age > 120
            ):
                raise ValueError(
                    "timeline.retirement.social_security_life_expectancy_age must be between 67 and 120"
                )

        social_security_fra_monthly_benefit_usd = retirement_payload.get("social_security_fra_monthly_benefit_usd")
        if social_security_fra_monthly_benefit_usd is None:
            resolved_social_security_fra_monthly_benefit_usd = None
        else:
            try:
                resolved_social_security_fra_monthly_benefit_usd = float(social_security_fra_monthly_benefit_usd)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "timeline.retirement.social_security_fra_monthly_benefit_usd must be numeric"
                ) from exc
            if resolved_social_security_fra_monthly_benefit_usd < 0:
                raise ValueError("timeline.retirement.social_security_fra_monthly_benefit_usd must be >= 0")

        social_security_estimated_annual_earnings_usd = retirement_payload.get(
            "social_security_estimated_annual_earnings_usd"
        )
        if social_security_estimated_annual_earnings_usd is None:
            resolved_social_security_estimated_annual_earnings_usd = None
        else:
            try:
                resolved_social_security_estimated_annual_earnings_usd = float(
                    social_security_estimated_annual_earnings_usd
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "timeline.retirement.social_security_estimated_annual_earnings_usd must be numeric"
                ) from exc
            if resolved_social_security_estimated_annual_earnings_usd < 0:
                raise ValueError(
                    "timeline.retirement.social_security_estimated_annual_earnings_usd must be >= 0"
                )

        rmd_birth_year = retirement_payload.get("rmd_birth_year")
        if rmd_birth_year is None:
            resolved_rmd_birth_year = None
        else:
            try:
                resolved_rmd_birth_year = int(rmd_birth_year)
            except (TypeError, ValueError) as exc:
                raise ValueError("timeline.retirement.rmd_birth_year must be an integer") from exc
            if resolved_rmd_birth_year < 1900 or resolved_rmd_birth_year > 2500:
                raise ValueError("timeline.retirement.rmd_birth_year must be between 1900 and 2500")

        rmd_start_age = retirement_payload.get("rmd_start_age")
        if rmd_start_age is None:
            resolved_rmd_start_age = None
        else:
            try:
                resolved_rmd_start_age = int(rmd_start_age)
            except (TypeError, ValueError) as exc:
                raise ValueError("timeline.retirement.rmd_start_age must be an integer") from exc
            if resolved_rmd_start_age < 72 or resolved_rmd_start_age > 120:
                raise ValueError("timeline.retirement.rmd_start_age must be between 72 and 120")

        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "events": events,
            "retirement": {
                "target_retirement_age": resolved_retirement_age,
                "withdrawal_strategy": withdrawal_strategy,
                "drawdown_order": drawdown_order,
                "social_security_birth_year": resolved_social_security_birth_year,
                "social_security_claiming_age": resolved_social_security_claiming_age,
                "social_security_life_expectancy_age": resolved_social_security_life_expectancy_age,
                "social_security_fra_monthly_benefit_usd": resolved_social_security_fra_monthly_benefit_usd,
                "social_security_estimated_annual_earnings_usd": (
                    resolved_social_security_estimated_annual_earnings_usd
                ),
                "rmd_birth_year": resolved_rmd_birth_year,
                "rmd_start_age": resolved_rmd_start_age,
            },
        }

    def _sanitize_contribution_rules_payload(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        default_payload = self._default_contribution_rules()
        input_payload = raw_payload if isinstance(raw_payload, dict) else {}

        base_rule_raw = input_payload.get("base_rule")
        if not isinstance(base_rule_raw, dict):
            base_rule_raw = default_payload.get("base_rule", {"type": "save"})
        base_rule_type = str(base_rule_raw.get("type") or "save").strip().lower()
        if base_rule_type not in {"save", "spend"}:
            raise ValueError("contribution_rules.base_rule.type must be one of: save, spend")
        base_rule = {"type": base_rule_type}

        rules_raw = input_payload.get("rules")
        if rules_raw is None:
            rules_raw = default_payload.get("rules", [])
        if not isinstance(rules_raw, list):
            raise ValueError("contribution_rules.rules must be a list")
        rules: list[dict[str, Any]] = []
        for index, item in enumerate(rules_raw, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"contribution_rules.rules[{index}] must be an object")
            rules.append(item)

        profile_id = str(input_payload.get("profile_id") or "").strip() or None

        try:
            employer_match_target_usd = float(input_payload.get("employer_match_target_usd") or 6000.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("contribution_rules.employer_match_target_usd must be numeric") from exc
        if employer_match_target_usd < 0:
            raise ValueError("contribution_rules.employer_match_target_usd must be >= 0")

        age_raw = input_payload.get("age")
        if age_raw is None:
            age = 35
        else:
            try:
                age = int(age_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("contribution_rules.age must be an integer") from exc
            if age < 0 or age > 120:
                raise ValueError("contribution_rules.age must be between 0 and 120")

        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "base_rule": base_rule,
            "rules": rules,
            "profile_id": profile_id,
            "employer_match_target_usd": employer_match_target_usd,
            "age": age,
        }

    def _sanitize_assumption_sets_payload(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        default_payload = self._default_assumption_sets()
        input_payload = raw_payload if isinstance(raw_payload, dict) else {}

        raw_sets = input_payload.get("sets")
        if raw_sets is None:
            raw_sets = default_payload.get("sets", [])
        if not isinstance(raw_sets, list):
            raise ValueError("assumption_sets.sets must be a list")

        def _normalize_optional_rate(
            *,
            raw_value: Any,
            field: str,
            minimum: float,
            maximum: float,
        ) -> float | None:
            if raw_value is None:
                return None
            if isinstance(raw_value, str) and not raw_value.strip():
                return None
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"assumption_sets.{field} must be numeric") from exc
            if value < minimum or value > maximum:
                raise ValueError(
                    f"assumption_sets.{field} must be between {minimum} and {maximum}"
                )
            return value

        def _normalize_optional_int(
            *,
            raw_value: Any,
            field: str,
            minimum: int,
            maximum: int,
        ) -> int | None:
            if raw_value is None:
                return None
            if isinstance(raw_value, str) and not raw_value.strip():
                return None
            try:
                value = int(float(raw_value))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"assumption_sets.{field} must be an integer") from exc
            if value < minimum or value > maximum:
                raise ValueError(
                    f"assumption_sets.{field} must be between {minimum} and {maximum}"
                )
            return value

        def _normalize_optional_simulation_mode(
            *,
            raw_value: Any,
            field: str,
        ) -> str | None:
            if raw_value is None:
                return None
            text = str(raw_value).strip().lower()
            if not text:
                return None
            candidates = (
                text,
                text.replace("-", "_"),
                text.replace(" ", "_"),
                re.sub(r"[^a-z0-9_]+", "", text),
            )
            for candidate in candidates:
                resolved = SIMULATION_MODE_ALIASES.get(candidate)
                if resolved is not None:
                    return resolved
            raise ValueError(
                f"assumption_sets.{field} must be one of: fixed, stochastic, historical, monte_carlo"
            )

        def _normalize_optional_simulation_variant(
            *,
            raw_value: Any,
            field: str,
        ) -> str | None:
            if raw_value is None:
                return None
            text = str(raw_value).strip().lower()
            if not text:
                return None
            candidates = (
                text,
                text.replace("-", "_"),
                text.replace(" ", "_"),
                re.sub(r"[^a-z0-9_]+", "", text),
            )
            for candidate in candidates:
                resolved = MONTE_CARLO_VARIANT_ALIASES.get(candidate)
                if resolved is not None:
                    return resolved
            raise ValueError(
                f"assumption_sets.{field} must be one of: p10, p50, p90"
            )

        sets: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, raw in enumerate(raw_sets, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"assumption_sets.sets[{index}] must be an object")

            set_id = str(raw.get("id") or "").strip()
            if not set_id:
                set_id = f"set-{uuid.uuid4().hex[:10]}"
            set_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", set_id).strip("-").lower() or f"set-{index}"
            if set_id in seen_ids:
                raise ValueError(f"assumption_sets.sets[{index}].id must be unique")
            seen_ids.add(set_id)

            name = str(raw.get("name") or "").strip() or set_id.replace("_", " ").replace("-", " ").title()
            baseline = _normalize_optional_rate(
                raw_value=raw.get("expected_return_baseline"),
                field=f"sets[{index}].expected_return_baseline",
                minimum=-0.95,
                maximum=1.0,
            )
            optimistic = _normalize_optional_rate(
                raw_value=raw.get("expected_return_optimistic"),
                field=f"sets[{index}].expected_return_optimistic",
                minimum=-0.95,
                maximum=1.0,
            )
            conservative = _normalize_optional_rate(
                raw_value=raw.get("expected_return_conservative"),
                field=f"sets[{index}].expected_return_conservative",
                minimum=-0.95,
                maximum=1.0,
            )
            inflation = _normalize_optional_rate(
                raw_value=raw.get("inflation_rate"),
                field=f"sets[{index}].inflation_rate",
                minimum=-1.0,
                maximum=1.0,
            )
            marginal_tax_rate = _normalize_optional_rate(
                raw_value=raw.get("marginal_tax_rate"),
                field=f"sets[{index}].marginal_tax_rate",
                minimum=0.0,
                maximum=1.0,
            )
            state_tax_rate = _normalize_optional_rate(
                raw_value=raw.get("state_tax_rate"),
                field=f"sets[{index}].state_tax_rate",
                minimum=0.0,
                maximum=1.0,
            )
            simulation_mode = _normalize_optional_simulation_mode(
                raw_value=raw.get("simulation_mode"),
                field=f"sets[{index}].simulation_mode",
            )
            simulation_monte_carlo_variant = _normalize_optional_simulation_variant(
                raw_value=raw.get("simulation_monte_carlo_variant"),
                field=f"sets[{index}].simulation_monte_carlo_variant",
            )
            simulation_historical_start_year = _normalize_optional_int(
                raw_value=raw.get("simulation_historical_start_year"),
                field=f"sets[{index}].simulation_historical_start_year",
                minimum=min(HISTORICAL_YEARS),
                maximum=max(HISTORICAL_YEARS),
            )
            simulation_seed_value = raw.get("simulation_seed")
            if simulation_seed_value is None or (
                isinstance(simulation_seed_value, str) and not simulation_seed_value.strip()
            ):
                simulation_seed = None
            else:
                simulation_seed = _normalize_optional_int(
                    raw_value=simulation_seed_value,
                    field=f"sets[{index}].simulation_seed",
                    minimum=0,
                    maximum=2_147_483_647,
                )
                if simulation_seed is None:
                    simulation_seed = DEFAULT_SIMULATION_SEED
            roth_conversion_annual_amount_usd = _normalize_optional_rate(
                raw_value=raw.get("roth_conversion_annual_amount_usd"),
                field=f"sets[{index}].roth_conversion_annual_amount_usd",
                minimum=0.0,
                maximum=10_000_000.0,
            )
            roth_conversion_start_age = _normalize_optional_rate(
                raw_value=raw.get("roth_conversion_start_age"),
                field=f"sets[{index}].roth_conversion_start_age",
                minimum=0.0,
                maximum=120.0,
            )
            roth_conversion_end_age = _normalize_optional_rate(
                raw_value=raw.get("roth_conversion_end_age"),
                field=f"sets[{index}].roth_conversion_end_age",
                minimum=0.0,
                maximum=120.0,
            )
            if (
                roth_conversion_start_age is not None
                and roth_conversion_end_age is not None
                and roth_conversion_start_age > roth_conversion_end_age
            ):
                roth_conversion_start_age, roth_conversion_end_age = (
                    roth_conversion_end_age,
                    roth_conversion_start_age,
                )

            if baseline is not None and optimistic is not None and optimistic < baseline:
                raise ValueError(
                    f"assumption_sets.sets[{index}] optimistic return must be >= baseline return"
                )
            if baseline is not None and conservative is not None and conservative > baseline:
                raise ValueError(
                    f"assumption_sets.sets[{index}] conservative return must be <= baseline return"
                )
            if optimistic is not None and conservative is not None and conservative > optimistic:
                raise ValueError(
                    f"assumption_sets.sets[{index}] conservative return must be <= optimistic return"
                )

            sets.append(
                {
                    "id": set_id,
                    "name": name,
                    "expected_return_baseline": baseline,
                    "expected_return_optimistic": optimistic,
                    "expected_return_conservative": conservative,
                    "inflation_rate": inflation,
                    "marginal_tax_rate": marginal_tax_rate,
                    "state_tax_rate": state_tax_rate,
                    "simulation_mode": simulation_mode,
                    "simulation_monte_carlo_variant": simulation_monte_carlo_variant,
                    "simulation_historical_start_year": simulation_historical_start_year,
                    "simulation_seed": simulation_seed,
                    "roth_conversion_annual_amount_usd": roth_conversion_annual_amount_usd,
                    "roth_conversion_start_age": (
                        int(roth_conversion_start_age)
                        if roth_conversion_start_age is not None
                        else None
                    ),
                    "roth_conversion_end_age": (
                        int(roth_conversion_end_age)
                        if roth_conversion_end_age is not None
                        else None
                    ),
                }
            )

        if not sets:
            sets = list(default_payload.get("sets", []))

        valid_ids = {str(item.get("id") or "").strip() for item in sets if isinstance(item, dict)}
        active_assumption_set_id = str(
            input_payload.get("active_assumption_set_id")
            or default_payload.get("active_assumption_set_id")
            or ""
        ).strip().lower()
        if not active_assumption_set_id or active_assumption_set_id not in valid_ids:
            active_assumption_set_id = str(sets[0].get("id") or "default")

        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "active_assumption_set_id": active_assumption_set_id,
            "sets": sets,
        }

    def _sanitize_branch_template_event(
        self,
        *,
        raw: dict[str, Any],
        template_index: int,
        event_index: int,
    ) -> dict[str, Any]:
        label = str(raw.get("label") or "").strip()
        if not label:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].label is required"
            )

        event_type = str(raw.get("event_type") or "milestone").strip().lower()
        if event_type not in TIMELINE_EVENT_TYPES:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].event_type is invalid"
            )

        impact_raw = raw.get("impact_type")
        impact_type = str(impact_raw).strip().lower() if impact_raw is not None else ""
        if not impact_type:
            impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")
        if impact_type not in TIMELINE_IMPACT_TYPES:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].impact_type is invalid"
            )

        recurring_frequency = str(raw.get("recurring_frequency") or "one_time").strip().lower()
        if recurring_frequency not in TIMELINE_FREQUENCIES:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].recurring_frequency is invalid"
            )

        try:
            amount_usd = float(raw.get("amount_usd"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].amount_usd must be numeric"
            ) from exc

        try:
            start_year_offset = int(raw.get("start_year_offset") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].start_year_offset must be an integer"
            ) from exc
        if start_year_offset < 0 or start_year_offset > 80:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].start_year_offset must be between 0 and 80"
            )

        duration_raw = raw.get("duration_months")
        if duration_raw is None:
            duration_months = None
        else:
            try:
                duration_months = int(duration_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"branch_templates.templates[{template_index}].branch_events[{event_index}].duration_months must be an integer"
                ) from exc
            if duration_months < 1 or duration_months > 960:
                raise ValueError(
                    f"branch_templates.templates[{template_index}].branch_events[{event_index}].duration_months must be between 1 and 960"
                )

        return {
            "label": label,
            "event_type": event_type,
            "impact_type": impact_type,
            "amount_usd": amount_usd,
            "recurring_frequency": recurring_frequency,
            "start_year_offset": start_year_offset,
            "duration_months": duration_months,
            "account_id": (str(raw.get("account_id") or "").strip() or None),
            "notes": str(raw.get("notes") or "").strip(),
        }

    def _sanitize_branch_templates_payload(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        default_payload = self._default_branch_templates()
        input_payload = raw_payload if isinstance(raw_payload, dict) else {}

        raw_templates = input_payload.get("templates")
        if raw_templates is None:
            raw_templates = default_payload.get("templates", [])
        if not isinstance(raw_templates, list):
            raise ValueError("branch_templates.templates must be a list")

        templates: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, raw in enumerate(raw_templates, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"branch_templates.templates[{index}] must be an object")

            template_id = str(raw.get("id") or "").strip()
            if not template_id:
                template_id = f"branch-template-{uuid.uuid4().hex[:10]}"
            template_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", template_id).strip("-").lower() or f"branch-template-{index}"
            if template_id in seen_ids:
                raise ValueError(f"branch_templates.templates[{index}].id must be unique")
            seen_ids.add(template_id)

            branch_name = str(raw.get("branch_name") or "").strip()
            name = str(raw.get("name") or "").strip()
            if not name:
                name = branch_name or template_id.replace("_", " ").replace("-", " ").title()
            if not branch_name:
                branch_name = name

            description = str(raw.get("description") or "").strip()
            assumption_set_id = str(raw.get("assumption_set_id") or "").strip().lower() or None

            compare_raw = raw.get("compare_settings")
            if compare_raw is None:
                compare_raw = {}
            if not isinstance(compare_raw, dict):
                raise ValueError(f"branch_templates.templates[{index}].compare_settings must be an object")
            compare_settings = self._sanitize_settings_update(compare_raw)
            self._validate_return_relationships(compare_settings)

            events_raw = raw.get("branch_events")
            if events_raw is None:
                events_raw = []
            if not isinstance(events_raw, list):
                raise ValueError(f"branch_templates.templates[{index}].branch_events must be a list")
            branch_events: list[dict[str, Any]] = []
            for event_index, event_raw in enumerate(events_raw, start=1):
                if not isinstance(event_raw, dict):
                    raise ValueError(
                        f"branch_templates.templates[{index}].branch_events[{event_index}] must be an object"
                    )
                branch_events.append(
                    self._sanitize_branch_template_event(
                        raw=event_raw,
                        template_index=index,
                        event_index=event_index,
                    )
                )

            if not branch_events and not compare_settings:
                raise ValueError(
                    f"branch_templates.templates[{index}] must include branch_events and/or compare_settings"
                )

            templates.append(
                {
                    "id": template_id,
                    "name": name,
                    "description": description,
                    "branch_name": branch_name,
                    "assumption_set_id": assumption_set_id,
                    "compare_settings": compare_settings,
                    "branch_events": branch_events,
                }
            )

        if not templates:
            templates = list(default_payload.get("templates", []))
            seen_ids = {str(item.get("id") or "").strip() for item in templates if isinstance(item, dict)}

        default_template_id = str(
            input_payload.get("default_template_id")
            or default_payload.get("default_template_id")
            or ""
        ).strip().lower()
        if not default_template_id or default_template_id not in seen_ids:
            default_template_id = str(templates[0].get("id") or "")

        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "default_template_id": default_template_id or None,
            "templates": templates,
        }

    def _sanitize_settings_update(self, updates: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {
            "annual_contribution_usd",
            "years",
            "hsa_extra_contribution_usd",
            "marginal_tax_rate",
            "state_tax_rate",
            "simulation_mode",
            "simulation_monte_carlo_variant",
            "simulation_historical_start_year",
            "simulation_seed",
            "household_mode",
            "household_partner_income_usd",
            "household_partner_income_growth_rate",
            "household_partner_retirement_age",
            "household_partner_social_security_annual_usd",
            "household_partner_social_security_claiming_age",
            "household_shared_goal_target_usd",
            "household_shared_goal_target_year",
            "roth_conversion_annual_amount_usd",
            "roth_conversion_start_age",
            "roth_conversion_end_age",
            "inflation_rate",
            "expected_return_baseline",
            "expected_return_optimistic",
            "expected_return_conservative",
            "filing_status",
            "withdrawal_strategy",
            "drawdown_order",
        }
        sanitized: dict[str, Any] = {}

        for key, raw_value in updates.items():
            if key not in allowed_fields:
                continue

            if raw_value is None:
                sanitized[key] = None
                continue

            if key in {
                "filing_status",
                "withdrawal_strategy",
                "drawdown_order",
                "household_mode",
                "simulation_mode",
                "simulation_monte_carlo_variant",
            }:
                value = str(raw_value).strip()
                sanitized[key] = value or None
                continue

            if key == "years":
                try:
                    years = int(raw_value)
                except Exception as exc:
                    raise ValueError("years must be an integer between 1 and 80") from exc
                if years < 1 or years > 80:
                    raise ValueError("years must be between 1 and 80")
                sanitized[key] = years
                continue

            if key in {
                "roth_conversion_start_age",
                "roth_conversion_end_age",
                "household_partner_retirement_age",
                "household_partner_social_security_claiming_age",
            }:
                try:
                    age_value = int(raw_value)
                except Exception as exc:
                    raise ValueError(f"{key} must be an integer between 0 and 120") from exc
                if age_value < 0 or age_value > 120:
                    raise ValueError(f"{key} must be between 0 and 120")
                sanitized[key] = age_value
                continue

            if key == "household_shared_goal_target_year":
                try:
                    target_year = int(raw_value)
                except Exception as exc:
                    raise ValueError("household_shared_goal_target_year must be an integer between 1900 and 2500") from exc
                if target_year < 1900 or target_year > 2500:
                    raise ValueError("household_shared_goal_target_year must be between 1900 and 2500")
                sanitized[key] = target_year
                continue

            if key == "simulation_historical_start_year":
                try:
                    simulation_historical_start_year = int(raw_value)
                except Exception as exc:
                    raise ValueError("simulation_historical_start_year must be an integer between 1928 and 2024") from exc
                if simulation_historical_start_year < min(HISTORICAL_YEARS) or simulation_historical_start_year > max(HISTORICAL_YEARS):
                    raise ValueError("simulation_historical_start_year must be between 1928 and 2024")
                sanitized[key] = simulation_historical_start_year
                continue

            if key == "simulation_seed":
                try:
                    simulation_seed = int(raw_value)
                except Exception as exc:
                    raise ValueError("simulation_seed must be an integer between 0 and 2147483647") from exc
                if simulation_seed < 0 or simulation_seed > 2_147_483_647:
                    raise ValueError("simulation_seed must be between 0 and 2147483647")
                sanitized[key] = simulation_seed
                continue

            try:
                value = float(raw_value)
            except Exception as exc:
                raise ValueError(f"{key} must be numeric") from exc

            if key in {
                "annual_contribution_usd",
                "hsa_extra_contribution_usd",
                "roth_conversion_annual_amount_usd",
                "household_partner_income_usd",
                "household_partner_social_security_annual_usd",
                "household_shared_goal_target_usd",
            } and value < 0:
                raise ValueError(f"{key} must be >= 0")

            if key == "marginal_tax_rate" and not (0 <= value <= 1):
                raise ValueError("marginal_tax_rate must be between 0 and 1")

            if key == "state_tax_rate" and not (0 <= value <= 1):
                raise ValueError("state_tax_rate must be between 0 and 1")

            if key == "household_partner_income_growth_rate" and not (-1 <= value <= 1):
                raise ValueError("household_partner_income_growth_rate must be between -1 and 1")

            if key == "inflation_rate" and not (-1 <= value <= 1):
                raise ValueError("inflation_rate must be between -1 and 1")

            if key.startswith("expected_return_") and not (-0.95 <= value <= 1):
                raise ValueError(f"{key} must be between -0.95 and 1")

            sanitized[key] = value

        start_age = sanitized.get("roth_conversion_start_age")
        end_age = sanitized.get("roth_conversion_end_age")
        if (
            start_age is not None
            and end_age is not None
            and int(start_age) > int(end_age)
        ):
            raise ValueError("roth_conversion_start_age must be <= roth_conversion_end_age")

        household_mode = str(sanitized.get("household_mode") or "").strip().lower()
        if household_mode and household_mode not in {"individual", "couple"}:
            raise ValueError("household_mode must be one of: individual, couple")

        simulation_mode = str(sanitized.get("simulation_mode") or "").strip().lower()
        if simulation_mode:
            candidates = (
                simulation_mode,
                simulation_mode.replace("-", "_"),
                simulation_mode.replace(" ", "_"),
                re.sub(r"[^a-z0-9_]+", "", simulation_mode),
            )
            resolved_simulation_mode: str | None = None
            for candidate in candidates:
                resolved_simulation_mode = SIMULATION_MODE_ALIASES.get(candidate)
                if resolved_simulation_mode is not None:
                    break
            if resolved_simulation_mode is None:
                raise ValueError("simulation_mode must be one of: fixed, stochastic, historical, monte_carlo")
            sanitized["simulation_mode"] = resolved_simulation_mode
        elif "simulation_mode" in sanitized:
            sanitized["simulation_mode"] = None

        simulation_monte_carlo_variant = str(sanitized.get("simulation_monte_carlo_variant") or "").strip().lower()
        if simulation_monte_carlo_variant:
            candidates = (
                simulation_monte_carlo_variant,
                simulation_monte_carlo_variant.replace("-", "_"),
                simulation_monte_carlo_variant.replace(" ", "_"),
                re.sub(r"[^a-z0-9_]+", "", simulation_monte_carlo_variant),
            )
            resolved_simulation_monte_carlo_variant: str | None = None
            for candidate in candidates:
                resolved_simulation_monte_carlo_variant = MONTE_CARLO_VARIANT_ALIASES.get(candidate)
                if resolved_simulation_monte_carlo_variant is not None:
                    break
            if resolved_simulation_monte_carlo_variant is None:
                raise ValueError("simulation_monte_carlo_variant must be one of: p10, p50, p90")
            sanitized["simulation_monte_carlo_variant"] = resolved_simulation_monte_carlo_variant
        elif "simulation_monte_carlo_variant" in sanitized:
            sanitized["simulation_monte_carlo_variant"] = None

        resolved_mode_for_dependencies = sanitized.get("simulation_mode")
        if isinstance(resolved_mode_for_dependencies, str):
            if resolved_mode_for_dependencies == "fixed":
                sanitized["simulation_monte_carlo_variant"] = None
                sanitized["simulation_historical_start_year"] = None
                sanitized["simulation_seed"] = None
            elif resolved_mode_for_dependencies == "stochastic":
                sanitized["simulation_monte_carlo_variant"] = None
                sanitized["simulation_historical_start_year"] = None
            elif resolved_mode_for_dependencies == "historical":
                sanitized["simulation_monte_carlo_variant"] = None
            elif resolved_mode_for_dependencies == "monte_carlo":
                sanitized["simulation_historical_start_year"] = None

        filing_status = str(sanitized.get("filing_status") or "").strip().lower()
        if filing_status and filing_status not in {
            "single",
            "married_filing_jointly",
            "married_filing_separately",
            "head_of_household",
        }:
            raise ValueError(
                "filing_status must be one of: single, married_filing_jointly, "
                "married_filing_separately, head_of_household"
            )
        if "filing_status" in sanitized:
            sanitized["filing_status"] = filing_status or None

        return sanitized

    @staticmethod
    def _validate_return_relationships(settings_payload: dict[str, Any]) -> None:
        baseline = settings_payload.get("expected_return_baseline")
        optimistic = settings_payload.get("expected_return_optimistic")
        conservative = settings_payload.get("expected_return_conservative")

        if baseline is not None and optimistic is not None and float(optimistic) < float(baseline):
            raise ValueError("expected_return_optimistic must be >= expected_return_baseline")
        if baseline is not None and conservative is not None and float(conservative) > float(baseline):
            raise ValueError("expected_return_conservative must be <= expected_return_baseline")
        if optimistic is not None and conservative is not None and float(conservative) > float(optimistic):
            raise ValueError("expected_return_conservative must be <= expected_return_optimistic")

    @staticmethod
    def _validate_roth_conversion_window(settings_payload: dict[str, Any]) -> None:
        start_age = settings_payload.get("roth_conversion_start_age")
        end_age = settings_payload.get("roth_conversion_end_age")
        if start_age is None or end_age is None:
            return
        if int(start_age) > int(end_age):
            raise ValueError("roth_conversion_start_age must be <= roth_conversion_end_age")

    def create_plan(self, title: str, description: str = "") -> dict[str, Any]:
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("Plan title is required")

        plan_id = f"plan-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        plan_dir = self._plan_dir(plan_id)
        plan_dir.mkdir(parents=True, exist_ok=False)
        (plan_dir / "scenarios").mkdir(parents=True, exist_ok=True)
        (plan_dir / "artifacts").mkdir(parents=True, exist_ok=True)

        (plan_dir / "plan.md").write_text(
            self._template_plan_markdown(cleaned_title, description),
            encoding="utf-8",
        )
        (plan_dir / "plan.yaml").write_text(self._template_plan_yaml(), encoding="utf-8")
        (plan_dir / "tasks.md").write_text(self._template_tasks(), encoding="utf-8")
        (plan_dir / "context.md").write_text("", encoding="utf-8")
        (plan_dir / "decisions.jsonl").write_text("", encoding="utf-8")
        self._write_settings(plan_id, self._default_settings())
        self._timeline_path(plan_id).write_text(json.dumps(self._default_timeline(), indent=2), encoding="utf-8")
        self._contribution_rules_path(plan_id).write_text(
            json.dumps(self._default_contribution_rules(), indent=2),
            encoding="utf-8",
        )
        self._assumption_sets_path(plan_id).write_text(
            json.dumps(self._default_assumption_sets(), indent=2),
            encoding="utf-8",
        )
        self._branch_templates_path(plan_id).write_text(
            json.dumps(self._default_branch_templates(), indent=2),
            encoding="utf-8",
        )
        self._saved_simulations_path(plan_id).write_text(
            json.dumps(self._default_saved_simulations(), indent=2),
            encoding="utf-8",
        )

        now = utc_now_iso()
        metadata = {
            "id": plan_id,
            "title": cleaned_title,
            "description": description.strip() or "",
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "created_at": now,
            "updated_at": now,
        }

        index_payload = self._load_index()
        index_payload.setdefault("plans", []).append(metadata)
        if not index_payload.get("active_plan_id"):
            index_payload["active_plan_id"] = plan_id
        self._save_index(index_payload)

        self.refresh_context(plan_id)
        return self.get_plan(plan_id)

    def list_plans(self, limit: int = 100) -> list[dict[str, Any]]:
        index_payload = self._load_index()
        active_plan_id = index_payload.get("active_plan_id")
        plans = list(index_payload.get("plans", []))
        plans.sort(key=lambda item: item.get("updated_at", ""), reverse=True)

        summaries: list[dict[str, Any]] = []
        for plan in plans[: max(1, limit)]:
            summaries.append(
                {
                    "id": plan.get("id"),
                    "title": plan.get("title", "Untitled Plan"),
                    "description": plan.get("description", ""),
                    "created_at": plan.get("created_at"),
                    "updated_at": plan.get("updated_at"),
                    "is_active": plan.get("id") == active_plan_id,
                }
            )
        return summaries

    def _load_decisions(self, plan_id: str, limit: int = 200) -> list[dict[str, Any]]:
        decisions_path = self._plan_dir(plan_id) / "decisions.jsonl"
        if not decisions_path.exists():
            return []

        rows: list[dict[str, Any]] = []
        for raw in decisions_path.read_text(encoding="utf-8").splitlines():
            text = raw.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except json.JSONDecodeError:
                continue

        rows.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return rows[: max(1, limit)]

    def _list_artifacts(self, plan_id: str, limit: int = 40) -> list[dict[str, Any]]:
        artifacts_dir = self._artifacts_dir(plan_id)
        if not artifacts_dir.exists():
            return []

        files = sorted(artifacts_dir.glob("*.md"), reverse=True)
        artifacts: list[dict[str, Any]] = []

        for path in files[: max(1, limit)]:
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            title = ""
            if lines:
                first = lines[0].strip()
                if first.startswith("# "):
                    title = first[2:].strip()
            artifacts.append(
                {
                    "id": path.stem,
                    "file_name": path.name,
                    "title": title or path.stem,
                    "created_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
                }
            )

        return artifacts

    def read_artifact(self, plan_id: str, artifact_id: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        artifact_name = artifact_id if artifact_id.endswith(".md") else f"{artifact_id}.md"
        artifact_path = self._artifacts_dir(plan_id) / artifact_name
        if not artifact_path.exists():
            raise PlanNotFoundError(f"Artifact not found: {artifact_id}")

        text = artifact_path.read_text(encoding="utf-8")
        title = artifact_path.stem
        lines = text.splitlines()
        if lines and lines[0].startswith("# "):
            title = lines[0][2:].strip()

        return {
            "id": artifact_path.stem,
            "file_name": artifact_path.name,
            "title": title,
            "created_at": datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "content": text,
        }

    def update_artifact_content(self, plan_id: str, artifact_id: str, markdown: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        artifact_name = artifact_id if artifact_id.endswith(".md") else f"{artifact_id}.md"
        artifact_path = self._artifacts_dir(plan_id) / artifact_name
        if not artifact_path.exists():
            raise PlanNotFoundError(f"Artifact not found: {artifact_id}")

        artifact_path.write_text(markdown, encoding="utf-8")
        return self.read_artifact(plan_id=plan_id, artifact_id=artifact_path.stem)

    def write_artifact(
        self,
        plan_id: str,
        title: str,
        markdown: str,
        kind: str = "workflow",
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        artifacts_dir = self._artifacts_dir(plan_id)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
        file_stem = f"{timestamp}-{self._slug(kind, default='workflow')}-{self._slug(title)}"
        artifact_path = artifacts_dir / f"{file_stem}.md"
        artifact_path.write_text(markdown, encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)

        return {
            "id": artifact_path.stem,
            "file_name": artifact_path.name,
            "title": title,
            "created_at": datetime.fromtimestamp(artifact_path.stat().st_mtime, tz=timezone.utc).isoformat(),
        }

    def _read_saved_simulations_payload(self, plan_id: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        payload = self._read_or_initialize_json(
            self._saved_simulations_path(plan_id),
            self._default_saved_simulations(),
        )
        items_raw = payload.get("items")
        items = [item for item in items_raw if isinstance(item, dict)] if isinstance(items_raw, list) else []
        sanitized = {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "items": items,
        }
        self._saved_simulations_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        return sanitized

    def list_saved_simulations(self, plan_id: str, limit: int = 50) -> dict[str, Any]:
        payload = self._read_saved_simulations_payload(plan_id)
        items = list(payload.get("items", []))
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "plan_id": plan_id,
            "simulations": items[: max(1, limit)],
        }

    def get_saved_simulation(self, plan_id: str, saved_simulation_id: str) -> dict[str, Any]:
        payload = self._read_saved_simulations_payload(plan_id)
        requested_id = str(saved_simulation_id or "").strip()
        for item in payload.get("items", []):
            if str(item.get("id") or "").strip() == requested_id:
                return item
        raise PlanNotFoundError(f"Saved simulation not found: {saved_simulation_id}")

    def save_simulation(
        self,
        plan_id: str,
        simulation_payload: dict[str, Any],
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        payload = simulation_payload if isinstance(simulation_payload, dict) else {}
        title = str(payload.get("title") or "").strip() or "Saved Simulation"
        source = str(payload.get("source") or "simulation").strip().lower().replace("-", "_").replace(" ", "_")
        if source not in {"simulation", "scenario_diff", "scenario_branch", "withdrawal_strategy"}:
            raise ValueError("source must be one of: simulation, scenario_diff, scenario_branch, withdrawal_strategy")

        input_payload = payload.get("input_payload")
        result_payload = payload.get("result_payload")
        if not isinstance(input_payload, dict):
            input_payload = {}
        if not isinstance(result_payload, dict):
            raise ValueError("result_payload must be an object")

        summary = str(payload.get("summary") or "").strip()
        notes = str(payload.get("notes") or "").strip()
        created_at = utc_now_iso()
        saved = {
            "id": f"saved-simulation-{uuid.uuid4().hex[:10]}",
            "created_at": created_at,
            "title": title,
            "source": source,
            "summary": summary,
            "notes": notes,
            "immutable": True,
            "input_payload": input_payload,
            "result_payload": result_payload,
        }

        stored = self._read_saved_simulations_payload(plan_id)
        items = [item for item in stored.get("items", []) if isinstance(item, dict)]
        items.insert(0, saved)
        next_payload = {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "items": items,
        }
        self._saved_simulations_path(plan_id).write_text(json.dumps(next_payload, indent=2), encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)
        return saved

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        index_payload = self._load_index()
        metadata = self._find_plan_metadata(index_payload, plan_id)

        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan directory not found for {plan_id}")

        def read_optional(path: Path) -> str:
            if not path.exists():
                return ""
            return path.read_text(encoding="utf-8")

        return {
            "id": metadata.get("id"),
            "title": metadata.get("title", "Untitled Plan"),
            "description": metadata.get("description", ""),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "is_active": metadata.get("id") == index_payload.get("active_plan_id"),
            "schema_version": metadata.get("schema_version", PLAN_WORKSPACE_SCHEMA_VERSION),
            "files": {
                "plan_markdown": read_optional(plan_dir / "plan.md"),
                "plan_yaml": read_optional(plan_dir / "plan.yaml"),
                "tasks_markdown": read_optional(plan_dir / "tasks.md"),
                "context_markdown": read_optional(plan_dir / "context.md"),
                "timeline_json": json.dumps(
                    self._read_or_initialize_json(self._timeline_path(plan_id), self._default_timeline()),
                    indent=2,
                ),
                "contribution_rules_json": json.dumps(
                    self._read_or_initialize_json(
                        self._contribution_rules_path(plan_id),
                        self._default_contribution_rules(),
                    ),
                    indent=2,
                ),
                "assumption_sets_json": json.dumps(
                    self._read_or_initialize_json(
                        self._assumption_sets_path(plan_id),
                        self._default_assumption_sets(),
                    ),
                    indent=2,
                ),
                "branch_templates_json": json.dumps(
                    self._read_or_initialize_json(
                        self._branch_templates_path(plan_id),
                        self._default_branch_templates(),
                    ),
                    indent=2,
                ),
                "saved_simulations_json": json.dumps(
                    self._read_saved_simulations_payload(plan_id),
                    indent=2,
                ),
            },
            "settings": self._read_settings(plan_id),
            "decisions": self._load_decisions(plan_id),
            "artifacts": self._list_artifacts(plan_id),
            "saved_simulations": self.list_saved_simulations(plan_id, limit=10).get("simulations", []),
        }

    def set_active_plan(self, plan_id: str) -> dict[str, Any]:
        index_payload = self._load_index()
        metadata = self._find_plan_metadata(index_payload, plan_id)
        index_payload["active_plan_id"] = plan_id
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)
        return {
            "id": metadata.get("id"),
            "title": metadata.get("title", "Untitled Plan"),
            "description": metadata.get("description", ""),
            "created_at": metadata.get("created_at"),
            "updated_at": metadata.get("updated_at"),
            "is_active": True,
            "schema_version": metadata.get("schema_version", PLAN_WORKSPACE_SCHEMA_VERSION),
        }

    def update_plan_files(
        self,
        plan_id: str,
        plan_markdown: str | None = None,
        tasks_markdown: str | None = None,
    ) -> dict[str, Any]:
        if plan_markdown is None and tasks_markdown is None:
            raise ValueError("At least one file payload is required")

        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        if plan_markdown is not None:
            (plan_dir / "plan.md").write_text(plan_markdown, encoding="utf-8")
        if tasks_markdown is not None:
            (plan_dir / "tasks.md").write_text(tasks_markdown, encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)
        self.refresh_context(plan_id)
        return self.get_plan(plan_id)

    def append_decision(
        self,
        plan_id: str,
        summary: str,
        rationale: str | None = None,
        status: str = "proposed",
        action_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cleaned_summary = summary.strip()
        if not cleaned_summary:
            raise ValueError("Decision summary is required")

        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        decision = {
            "id": f"decision-{uuid.uuid4().hex[:10]}",
            "created_at": utc_now_iso(),
            "summary": cleaned_summary,
            "rationale": (rationale or "").strip(),
            "status": (status or "proposed").strip().lower(),
        }
        if isinstance(action_payload, dict) and action_payload:
            decision["action_payload"] = action_payload

        decisions_path = plan_dir / "decisions.jsonl"
        with decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision))
            handle.write("\n")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)
        self.refresh_context(plan_id)
        return decision

    def update_plan_settings(
        self,
        plan_id: str,
        updates: dict[str, Any],
        rationale: str | None = None,
        status: str = "accepted",
        log_decision: bool = True,
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        sanitized = self._sanitize_settings_update(updates)
        if not sanitized:
            raise ValueError("At least one supported settings field is required")

        current_settings = self._read_settings(plan_id)
        merged_settings = dict(current_settings)
        merged_settings.update(sanitized)
        self._validate_return_relationships(merged_settings)
        self._validate_roth_conversion_window(merged_settings)
        self._write_settings(plan_id, merged_settings)

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)

        if log_decision:
            changed_lines = []
            for key in sanitized:
                before = self._format_setting_value(key, current_settings.get(key))
                after = self._format_setting_value(key, merged_settings.get(key))
                if before == after:
                    continue
                changed_lines.append(f"{key}: {before} -> {after}")

            if changed_lines:
                summary = f"Updated plan settings: {'; '.join(changed_lines[:4])}"
                if len(changed_lines) > 4:
                    summary = f"{summary}; +{len(changed_lines) - 4} additional changes"
                self.append_decision(
                    plan_id=plan_id,
                    summary=summary,
                    rationale=(rationale or "Plan assumptions/inputs were updated."),
                    status=status,
                )
                return self.get_plan(plan_id)

        self.refresh_context(plan_id)
        return self.get_plan(plan_id)

    def get_plan_timeline(self, plan_id: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")
        return self._read_or_initialize_json(self._timeline_path(plan_id), self._default_timeline())

    def update_plan_timeline(
        self,
        plan_id: str,
        timeline_payload: dict[str, Any],
        rationale: str | None = None,
        status: str = "accepted",
        log_decision: bool = True,
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        sanitized = self._sanitize_timeline_payload(timeline_payload)
        self._timeline_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)

        if log_decision:
            event_count = len(sanitized.get("events", []))
            self.append_decision(
                plan_id=plan_id,
                summary=f"Updated plan timeline: {event_count} event(s).",
                rationale=(rationale or "Timeline events/retirement milestones were updated."),
                status=status,
            )
        else:
            self.refresh_context(plan_id)

        return sanitized

    def get_plan_contribution_rules(self, plan_id: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        payload = self._read_or_initialize_json(
            self._contribution_rules_path(plan_id),
            self._default_contribution_rules(),
        )
        sanitized = self._sanitize_contribution_rules_payload(payload)
        self._contribution_rules_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        return sanitized

    def update_plan_contribution_rules(
        self,
        plan_id: str,
        contribution_rules_payload: dict[str, Any],
        rationale: str | None = None,
        status: str = "accepted",
        log_decision: bool = True,
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        sanitized = self._sanitize_contribution_rules_payload(contribution_rules_payload)
        self._contribution_rules_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)

        if log_decision:
            self.append_decision(
                plan_id=plan_id,
                summary=(
                    "Updated contribution rules: "
                    f"{len(sanitized.get('rules', []))} rule(s), base={sanitized.get('base_rule', {}).get('type')}"
                ),
                rationale=(rationale or "Contribution-allocation rules were updated."),
                status=status,
            )
        else:
            self.refresh_context(plan_id)

        return sanitized

    def get_plan_assumption_sets(self, plan_id: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        payload = self._read_or_initialize_json(
            self._assumption_sets_path(plan_id),
            self._default_assumption_sets(),
        )
        sanitized = self._sanitize_assumption_sets_payload(payload)
        self._assumption_sets_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        return sanitized

    def update_plan_assumption_sets(
        self,
        plan_id: str,
        assumption_sets_payload: dict[str, Any],
        rationale: str | None = None,
        status: str = "accepted",
        log_decision: bool = True,
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        sanitized = self._sanitize_assumption_sets_payload(assumption_sets_payload)
        self._assumption_sets_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)

        if log_decision:
            self.append_decision(
                plan_id=plan_id,
                summary=(
                    "Updated assumption sets: "
                    f"{len(sanitized.get('sets', []))} set(s), active={sanitized.get('active_assumption_set_id')}"
                ),
                rationale=(rationale or "Planning assumption sets were updated."),
                status=status,
            )
        else:
            self.refresh_context(plan_id)

        return sanitized

    def get_plan_branch_templates(self, plan_id: str) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        payload = self._read_or_initialize_json(
            self._branch_templates_path(plan_id),
            self._default_branch_templates(),
        )
        sanitized = self._sanitize_branch_templates_payload(payload)
        self._branch_templates_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")
        return sanitized

    def update_plan_branch_templates(
        self,
        plan_id: str,
        branch_templates_payload: dict[str, Any],
        rationale: str | None = None,
        status: str = "accepted",
        log_decision: bool = True,
    ) -> dict[str, Any]:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        sanitized = self._sanitize_branch_templates_payload(branch_templates_payload)
        self._branch_templates_path(plan_id).write_text(json.dumps(sanitized, indent=2), encoding="utf-8")

        index_payload = self._load_index()
        self._touch_plan(index_payload, plan_id)
        self._save_index(index_payload)

        if log_decision:
            self.append_decision(
                plan_id=plan_id,
                summary=(
                    "Updated branch templates: "
                    f"{len(sanitized.get('templates', []))} template(s), "
                    f"default={sanitized.get('default_template_id')}"
                ),
                rationale=(rationale or "Scenario branch templates/presets were updated."),
                status=status,
            )
        else:
            self.refresh_context(plan_id)

        return sanitized

    def refresh_context(self, plan_id: str) -> str:
        plan_dir = self._plan_dir(plan_id)
        if not plan_dir.exists():
            raise PlanNotFoundError(f"Plan not found: {plan_id}")

        index_payload = self._load_index()
        metadata = self._find_plan_metadata(index_payload, plan_id)

        plan_text = (plan_dir / "plan.md").read_text(encoding="utf-8") if (plan_dir / "plan.md").exists() else ""
        tasks_text = (plan_dir / "tasks.md").read_text(encoding="utf-8") if (plan_dir / "tasks.md").exists() else ""
        settings_payload = self._read_settings(plan_id)
        timeline_payload = self._read_or_initialize_json(self._timeline_path(plan_id), self._default_timeline())
        contribution_rules_payload = self._read_or_initialize_json(
            self._contribution_rules_path(plan_id),
            self._default_contribution_rules(),
        )
        assumption_sets_payload = self._read_or_initialize_json(
            self._assumption_sets_path(plan_id),
            self._default_assumption_sets(),
        )
        branch_templates_payload = self._read_or_initialize_json(
            self._branch_templates_path(plan_id),
            self._default_branch_templates(),
        )
        decisions = self._load_decisions(plan_id, limit=8)

        decision_lines: list[str] = []
        for item in decisions:
            decision_lines.append(
                f"- [{item.get('status', 'proposed')}] {item.get('summary', '')} ({item.get('created_at', '')})"
            )

        setting_lines = [
            f"- Annual contribution: {self._format_setting_value('annual_contribution_usd', settings_payload.get('annual_contribution_usd'))}",
            f"- Horizon: {self._format_setting_value('years', settings_payload.get('years'))}",
            f"- HSA extra contribution: {self._format_setting_value('hsa_extra_contribution_usd', settings_payload.get('hsa_extra_contribution_usd'))}",
            f"- Marginal tax rate: {self._format_setting_value('marginal_tax_rate', settings_payload.get('marginal_tax_rate'))}",
            f"- State tax rate: {self._format_setting_value('state_tax_rate', settings_payload.get('state_tax_rate'))}",
            f"- Simulation mode: {self._format_setting_value('simulation_mode', settings_payload.get('simulation_mode'))}",
            f"- Monte Carlo variant: {self._format_setting_value('simulation_monte_carlo_variant', settings_payload.get('simulation_monte_carlo_variant'))}",
            f"- Historical start year: {self._format_setting_value('simulation_historical_start_year', settings_payload.get('simulation_historical_start_year'))}",
            f"- Simulation seed: {self._format_setting_value('simulation_seed', settings_payload.get('simulation_seed'))}",
            f"- Roth conversion annual target: {self._format_setting_value('roth_conversion_annual_amount_usd', settings_payload.get('roth_conversion_annual_amount_usd'))}",
            f"- Roth conversion start age: {self._format_setting_value('roth_conversion_start_age', settings_payload.get('roth_conversion_start_age'))}",
            f"- Roth conversion end age: {self._format_setting_value('roth_conversion_end_age', settings_payload.get('roth_conversion_end_age'))}",
            f"- Household mode: {settings_payload.get('household_mode') or 'individual'}",
            f"- Household partner income: {self._format_setting_value('household_partner_income_usd', settings_payload.get('household_partner_income_usd'))}",
            f"- Household partner growth: {self._format_setting_value('household_partner_income_growth_rate', settings_payload.get('household_partner_income_growth_rate'))}",
            f"- Household partner retirement age: {self._format_setting_value('household_partner_retirement_age', settings_payload.get('household_partner_retirement_age'))}",
            f"- Household partner Social Security annual: {self._format_setting_value('household_partner_social_security_annual_usd', settings_payload.get('household_partner_social_security_annual_usd'))}",
            f"- Household partner Social Security claiming age: {self._format_setting_value('household_partner_social_security_claiming_age', settings_payload.get('household_partner_social_security_claiming_age'))}",
            f"- Household shared-goal target: {self._format_setting_value('household_shared_goal_target_usd', settings_payload.get('household_shared_goal_target_usd'))}",
            f"- Household shared-goal target year: {self._format_setting_value('household_shared_goal_target_year', settings_payload.get('household_shared_goal_target_year'))}",
            f"- Inflation rate: {self._format_setting_value('inflation_rate', settings_payload.get('inflation_rate'))}",
            f"- Baseline return: {self._format_setting_value('expected_return_baseline', settings_payload.get('expected_return_baseline'))}",
            f"- Optimistic return: {self._format_setting_value('expected_return_optimistic', settings_payload.get('expected_return_optimistic'))}",
            f"- Conservative return: {self._format_setting_value('expected_return_conservative', settings_payload.get('expected_return_conservative'))}",
            f"- Filing status: {settings_payload.get('filing_status') or 'default'}",
            f"- Withdrawal strategy: {settings_payload.get('withdrawal_strategy') or 'not set'}",
            f"- Drawdown order: {settings_payload.get('drawdown_order') or 'age_aware'}",
        ]

        timeline_events = timeline_payload.get("events", [])
        if not isinstance(timeline_events, list):
            timeline_events = []
        preview_events = []
        for item in timeline_events[:5]:
            if not isinstance(item, dict):
                continue
            try:
                amount = float(item.get("amount_usd") or 0.0)
            except (TypeError, ValueError):
                amount = 0.0
            preview_events.append(
                f"- {item.get('date', '?')}: {item.get('label', 'Event')} "
                f"({item.get('event_type', 'milestone')}, {item.get('impact_type', 'portfolio')}, "
                f"{amount:,.2f} USD)"
            )
        timeline_preview = "\n".join(preview_events) if preview_events else "- No timeline events configured."

        context_lines = [
            f"# Plan Context: {metadata.get('title', 'Untitled Plan')}",
            "",
            "## Plan Summary",
            "",
            plan_text.strip()[:4000] or "No plan markdown yet.",
            "",
            "## Task Snapshot",
            "",
            tasks_text.strip()[:2000] or "No tasks documented yet.",
            "",
            "## Plan Settings",
            "",
            "\n".join(setting_lines),
            "",
            "## Standalone Modeling",
            "",
            f"- Timeline events: {len(timeline_payload.get('events', []))}",
            f"- Contribution rules: {len(contribution_rules_payload.get('rules', []))}",
            f"- Assumption sets: {len(assumption_sets_payload.get('sets', []))}",
            f"- Active assumption set: {assumption_sets_payload.get('active_assumption_set_id') or 'default'}",
            f"- Branch templates: {len(branch_templates_payload.get('templates', []))}",
            f"- Default branch template: {branch_templates_payload.get('default_template_id') or 'none'}",
            "",
            "## Timeline Preview",
            "",
            timeline_preview,
            "",
            "## Recent Decisions",
            "",
            "\n".join(decision_lines) if decision_lines else "- No decisions logged yet.",
            "",
        ]
        context_text = "\n".join(context_lines)
        (plan_dir / "context.md").write_text(context_text, encoding="utf-8")
        return context_text

    def get_context_payload(self, plan_id: str | None = None, max_chars: int = 6000) -> dict[str, Any]:
        index_payload = self._load_index()
        resolved_plan_id = plan_id or index_payload.get("active_plan_id")
        if not resolved_plan_id:
            return {"note": "No active plan is configured."}

        detail = self.get_plan(str(resolved_plan_id))
        context_markdown = detail["files"].get("context_markdown", "")
        if not context_markdown:
            context_markdown = self.refresh_context(str(resolved_plan_id))
            detail = self.get_plan(str(resolved_plan_id))

        trimmed = context_markdown[:max_chars]
        if len(context_markdown) > max_chars:
            trimmed = f"{trimmed}..."

        return {
            "id": detail.get("id"),
            "title": detail.get("title"),
            "description": detail.get("description", ""),
            "is_active": detail.get("is_active", False),
            "updated_at": detail.get("updated_at"),
            "settings": detail.get("settings", {}),
            "context_excerpt": trimmed,
        }

    def get_active_plan_id(self) -> str | None:
        index_payload = self._load_index()
        active_plan_id = index_payload.get("active_plan_id")
        if isinstance(active_plan_id, str) and active_plan_id.strip():
            return active_plan_id
        return None

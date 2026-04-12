from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PLAN_WORKSPACE_SCHEMA_VERSION = 2
TIMELINE_DEFAULT_IMPACT_BY_EVENT: dict[str, str] = {
    "purchase": "expense",
    "windfall": "income",
    "job_change": "income",
    "retirement": "contribution",
    "milestone": "portfolio",
}


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

        self._save_index(
            {
                "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
                "active_plan_id": None,
                "plans": [],
            }
        )

    def _load_index(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._initialize_index()
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))

        if not isinstance(payload, dict):
            payload = {}

        payload.setdefault("active_plan_id", None)
        payload.setdefault("plans", [])
        payload["schema_version"] = PLAN_WORKSPACE_SCHEMA_VERSION
        self._save_index(payload)
        return payload

    def _save_index(self, index_payload: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")

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
            "inflation_rate": None,
            "expected_return_baseline": None,
            "expected_return_optimistic": None,
            "expected_return_conservative": None,
            "filing_status": None,
            "withdrawal_strategy": None,
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
                },
                {
                    "id": "historical_average",
                    "name": "Historical Average",
                    "expected_return_baseline": 0.07,
                    "expected_return_optimistic": 0.09,
                    "expected_return_conservative": 0.05,
                    "inflation_rate": 0.03,
                    "marginal_tax_rate": None,
                },
                {
                    "id": "conservative",
                    "name": "Conservative",
                    "expected_return_baseline": 0.05,
                    "expected_return_optimistic": 0.06,
                    "expected_return_conservative": 0.04,
                    "inflation_rate": 0.025,
                    "marginal_tax_rate": None,
                },
                {
                    "id": "stagflation",
                    "name": "Stagflation",
                    "expected_return_baseline": 0.04,
                    "expected_return_optimistic": 0.05,
                    "expected_return_conservative": 0.02,
                    "inflation_rate": 0.05,
                    "marginal_tax_rate": None,
                },
                {
                    "id": "japan_scenario",
                    "name": "Japan Scenario",
                    "expected_return_baseline": 0.02,
                    "expected_return_optimistic": 0.035,
                    "expected_return_conservative": 0.0,
                    "inflation_rate": 0.005,
                    "marginal_tax_rate": None,
                }
            ],
        }

    @staticmethod
    def _default_branch_templates() -> dict[str, Any]:
        # Preset catalog shape aligns with Ignidash template-listing conventions
        # (named, reusable planning templates) while using BuildWealth branch-event schema.
        return {
            "schema_version": PLAN_WORKSPACE_SCHEMA_VERSION,
            "default_template_id": "job_loss_6_months",
            "templates": [
                {
                    "id": "job_loss_6_months",
                    "name": "Job Loss (6 Months)",
                    "description": "Temporary income interruption for six months.",
                    "branch_name": "Job Loss 6 Months",
                    "assumption_set_id": None,
                    "compare_settings": {},
                    "branch_events": [
                        {
                            "label": "Temporary Job Loss",
                            "event_type": "job_change",
                            "impact_type": "income",
                            "amount_usd": -7500.0,
                            "recurring_frequency": "monthly",
                            "start_year_offset": 0,
                            "duration_months": 6,
                            "account_id": None,
                            "notes": "Modeled as gross monthly income loss.",
                        }
                    ],
                },
                {
                    "id": "raise_20_percent",
                    "name": "Raise (20%)",
                    "description": "Ongoing promotion raise scenario.",
                    "branch_name": "Raise 20 Percent",
                    "assumption_set_id": None,
                    "compare_settings": {},
                    "branch_events": [
                        {
                            "label": "Promotion Raise",
                            "event_type": "job_change",
                            "impact_type": "income",
                            "amount_usd": 18000.0,
                            "recurring_frequency": "yearly",
                            "start_year_offset": 0,
                            "duration_months": None,
                            "account_id": None,
                            "notes": "Annualized salary lift.",
                        }
                    ],
                },
                {
                    "id": "new_child_costs",
                    "name": "New Child Costs",
                    "description": "One-time setup plus long-duration monthly childcare costs.",
                    "branch_name": "Have a Kid",
                    "assumption_set_id": None,
                    "compare_settings": {},
                    "branch_events": [
                        {
                            "label": "Childcare Setup Costs",
                            "event_type": "purchase",
                            "impact_type": "expense",
                            "amount_usd": 15000.0,
                            "recurring_frequency": "one_time",
                            "start_year_offset": 0,
                            "duration_months": None,
                            "account_id": None,
                            "notes": "",
                        },
                        {
                            "label": "Ongoing Childcare Costs",
                            "event_type": "milestone",
                            "impact_type": "expense",
                            "amount_usd": 1200.0,
                            "recurring_frequency": "monthly",
                            "start_year_offset": 0,
                            "duration_months": 216,
                            "account_id": None,
                            "notes": "",
                        },
                    ],
                },
            ],
        }

    @staticmethod
    def _format_setting_value(key: str, value: Any) -> str:
        if value is None:
            return "default"

        if key in {"annual_contribution_usd", "hsa_extra_contribution_usd"}:
            return f"${float(value):,.2f}"
        if key == "years":
            return f"{int(value)} years"
        if key in {
            "marginal_tax_rate",
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
            if event_type not in {"purchase", "windfall", "job_change", "retirement", "milestone"}:
                raise ValueError(f"timeline.events[{index}].event_type is invalid")

            impact_raw = raw.get("impact_type")
            impact_type = str(impact_raw).strip().lower() if impact_raw is not None else ""
            if not impact_type:
                impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")
            if impact_type not in {"income", "expense", "portfolio", "contribution", "debt_payment"}:
                raise ValueError(f"timeline.events[{index}].impact_type is invalid")

            recurring_frequency = str(raw.get("recurring_frequency") or "one_time").strip().lower()
            if recurring_frequency not in {"one_time", "monthly", "yearly"}:
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
        if event_type not in {"purchase", "windfall", "job_change", "retirement", "milestone"}:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].event_type is invalid"
            )

        impact_raw = raw.get("impact_type")
        impact_type = str(impact_raw).strip().lower() if impact_raw is not None else ""
        if not impact_type:
            impact_type = TIMELINE_DEFAULT_IMPACT_BY_EVENT.get(event_type, "portfolio")
        if impact_type not in {"income", "expense", "portfolio", "contribution", "debt_payment"}:
            raise ValueError(
                f"branch_templates.templates[{template_index}].branch_events[{event_index}].impact_type is invalid"
            )

        recurring_frequency = str(raw.get("recurring_frequency") or "one_time").strip().lower()
        if recurring_frequency not in {"one_time", "monthly", "yearly"}:
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
            "inflation_rate",
            "expected_return_baseline",
            "expected_return_optimistic",
            "expected_return_conservative",
            "filing_status",
            "withdrawal_strategy",
        }
        sanitized: dict[str, Any] = {}

        for key, raw_value in updates.items():
            if key not in allowed_fields:
                continue

            if raw_value is None:
                sanitized[key] = None
                continue

            if key in {"filing_status", "withdrawal_strategy"}:
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

            try:
                value = float(raw_value)
            except Exception as exc:
                raise ValueError(f"{key} must be numeric") from exc

            if key in {"annual_contribution_usd", "hsa_extra_contribution_usd"} and value < 0:
                raise ValueError(f"{key} must be >= 0")

            if key == "marginal_tax_rate" and not (0 <= value <= 1):
                raise ValueError("marginal_tax_rate must be between 0 and 1")

            if key == "inflation_rate" and not (-1 <= value <= 1):
                raise ValueError("inflation_rate must be between -1 and 1")

            if key.startswith("expected_return_") and not (-0.95 <= value <= 1):
                raise ValueError(f"{key} must be between -0.95 and 1")

            sanitized[key] = value

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
            },
            "settings": self._read_settings(plan_id),
            "decisions": self._load_decisions(plan_id),
            "artifacts": self._list_artifacts(plan_id),
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
            f"- Inflation rate: {self._format_setting_value('inflation_rate', settings_payload.get('inflation_rate'))}",
            f"- Baseline return: {self._format_setting_value('expected_return_baseline', settings_payload.get('expected_return_baseline'))}",
            f"- Optimistic return: {self._format_setting_value('expected_return_optimistic', settings_payload.get('expected_return_optimistic'))}",
            f"- Conservative return: {self._format_setting_value('expected_return_conservative', settings_payload.get('expected_return_conservative'))}",
            f"- Filing status: {settings_payload.get('filing_status') or 'default'}",
            f"- Withdrawal strategy: {settings_payload.get('withdrawal_strategy') or 'not set'}",
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

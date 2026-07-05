from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

PROFILE_SCHEMA_VERSION = 2
PROFILE_METADATA_REVIEW_STATUSES = {"copilot_drafted", "inferred", "stale"}
PROFILE_METADATA_MATERIAL_SECTIONS = ("tax_profile", "investment_policy")
PROFILE_METADATA_DEFAULT_STALE_AFTER_DAYS = {
    "tax_profile.filing_status": 365,
    "tax_profile.marginal_tax_rate": 180,
    "tax_profile.effective_tax_rate": 180,
    "tax_profile.state_tax_rate": 180,
    "tax_profile.state": 365,
    "investment_policy.max_single_symbol_exposure_pct": 365,
    "investment_policy.max_sector_exposure_pct": 365,
    "investment_policy.minimum_research_confidence": 365,
    "investment_policy.minimum_cash_runway_months": 365,
    "investment_policy.max_asset_class_exposure_pct": 365,
    "investment_policy.target_asset_class_allocation_pct": 365,
    "investment_policy.simplicity_preference": 365,
    "investment_policy.tax_sensitivity": 365,
    "investment_policy.risk_tolerance": 365,
    "investment_policy.preferred_account_locations": 365,
    "investment_policy.restricted_symbols": 365,
    "investment_policy.restricted_sectors": 365,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def _parse_optional_datetime(raw_value: Any) -> datetime | None:
    if isinstance(raw_value, datetime):
        return raw_value if raw_value.tzinfo else raw_value.replace(tzinfo=timezone.utc)
    text = str(raw_value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _has_profile_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def material_profile_field_paths_from_payload(payload: Mapping[str, Any]) -> list[str]:
    field_paths: list[str] = []
    for section_name in PROFILE_METADATA_MATERIAL_SECTIONS:
        section_payload = payload.get(section_name)
        if not isinstance(section_payload, Mapping):
            continue
        for field_name, value in sorted(section_payload.items()):
            if _has_profile_value(value):
                field_paths.append(f"{section_name}.{field_name}")
    return field_paths


def patch_material_profile_field_paths(patch_payload: Mapping[str, Any]) -> list[str]:
    field_paths: list[str] = []
    for section_name in PROFILE_METADATA_MATERIAL_SECTIONS:
        section_payload = patch_payload.get(section_name)
        if not isinstance(section_payload, Mapping):
            continue
        for field_name in sorted(section_payload):
            field_paths.append(f"{section_name}.{field_name}")
    return field_paths


def _profile_value_at_path(payload: Mapping[str, Any], field_path: str) -> Any:
    section_name, _, field_name = field_path.partition(".")
    section_payload = payload.get(section_name)
    if not isinstance(section_payload, Mapping):
        return None
    return section_payload.get(field_name)


def changed_material_profile_field_paths(
    before_payload: Mapping[str, Any],
    after_payload: Mapping[str, Any],
    *,
    candidate_paths: list[str] | None = None,
) -> list[str]:
    paths = candidate_paths or material_profile_field_paths_from_payload(after_payload)
    metadata = after_payload.get("profile_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    changed: list[str] = []
    for field_path in paths:
        before_value = _profile_value_at_path(before_payload, field_path)
        after_value = _profile_value_at_path(after_payload, field_path)
        if not _has_profile_value(after_value):
            continue
        if before_value != after_value or field_path not in metadata:
            changed.append(field_path)
    return changed


def merge_profile_metadata(
    payload: Mapping[str, Any],
    *,
    field_paths: list[str],
    source: str,
    status: str,
    confidence: str = "high",
    now: str | None = None,
) -> dict[str, Any]:
    resolved_now = now or utc_now_iso()
    merged = dict(payload)
    raw_metadata = merged.get("profile_metadata")
    metadata = dict(raw_metadata) if isinstance(raw_metadata, Mapping) else {}
    source_label = str(source or "profile_editor").strip() or "profile_editor"
    status_label = str(status or "user_confirmed").strip().lower() or "user_confirmed"

    for field_path in field_paths:
        if not _has_profile_value(_profile_value_at_path(merged, field_path)):
            continue
        existing = metadata.get(field_path)
        existing = dict(existing) if isinstance(existing, Mapping) else {}
        stale_after_days = existing.get("stale_after_days")
        if stale_after_days is None:
            stale_after_days = PROFILE_METADATA_DEFAULT_STALE_AFTER_DAYS.get(field_path, 365)
        entry = {
            **existing,
            "status": status_label,
            "source": source_label,
            "confidence": str(confidence or existing.get("confidence") or "high").strip().lower(),
            "updated_at": resolved_now,
            "stale_after_days": stale_after_days,
        }
        if status_label == "user_confirmed":
            entry["last_confirmed_at"] = resolved_now
            entry["confirmed_by_user"] = True
        else:
            entry.setdefault("captured_at", resolved_now)
            entry["confirmed_by_user"] = False
        metadata[field_path] = entry

    merged["profile_metadata"] = _normalize_profile_metadata(metadata)
    return merged


def profile_metadata_entry_is_stale(
    entry: Mapping[str, Any] | None,
    *,
    now: datetime | None = None,
) -> bool:
    if not isinstance(entry, Mapping):
        return False
    status = str(entry.get("status") or "").strip().lower()
    if status == "stale":
        return True
    last_confirmed_at = _parse_optional_datetime(entry.get("last_confirmed_at"))
    if last_confirmed_at is None:
        return False
    try:
        stale_after_days = float(entry.get("stale_after_days") or 0)
    except (TypeError, ValueError):
        stale_after_days = 0.0
    if stale_after_days <= 0:
        return False
    resolved_now = now or utc_now()
    return resolved_now - last_confirmed_at > timedelta(days=stale_after_days)


def profile_metadata_quality_for_field(
    profile_payload: Mapping[str, Any],
    field_path: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    metadata = profile_payload.get("profile_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    entry = metadata.get(field_path)
    entry = entry if isinstance(entry, Mapping) else {}
    status = str(entry.get("status") or "unknown").strip().lower() or "unknown"
    stale = profile_metadata_entry_is_stale(entry, now=now)
    freshness = "stale" if stale or status == "stale" else "current" if entry else "unknown"
    return {
        "status": status,
        "confidence": str(entry.get("confidence") or "unknown").strip().lower(),
        "freshness": freshness,
        "stale": stale,
        "source": str(entry.get("source") or "").strip() or None,
        "last_confirmed_at": entry.get("last_confirmed_at"),
        "stale_after_days": entry.get("stale_after_days"),
    }


def profile_metadata_review_field_paths(
    profile_payload: Mapping[str, Any],
    *,
    prefixes: tuple[str, ...] | None = None,
    now: datetime | None = None,
) -> list[str]:
    metadata = profile_payload.get("profile_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    paths = material_profile_field_paths_from_payload(profile_payload)
    if prefixes:
        paths = [field_path for field_path in paths if field_path.startswith(prefixes)]
    review_paths: list[str] = []
    for field_path in paths:
        entry = metadata.get(field_path)
        if not isinstance(entry, Mapping):
            continue
        status = str(entry.get("status") or "").strip().lower()
        if status in PROFILE_METADATA_REVIEW_STATUSES or profile_metadata_entry_is_stale(entry, now=now):
            review_paths.append(field_path)
    return review_paths


def profile_metadata_quality_warnings(
    profile_payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> list[str]:
    warnings: list[str] = []
    for field_path in profile_metadata_review_field_paths(profile_payload, now=now):
        quality = profile_metadata_quality_for_field(profile_payload, field_path, now=now)
        if quality.get("freshness") == "stale":
            warnings.append(f"financial_profile.{field_path}.stale")
        else:
            warnings.append(f"financial_profile.{field_path}.needs_review")
    return warnings


def _normalize_profile_metadata(raw_metadata: Any) -> dict[str, Any]:
    if not isinstance(raw_metadata, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    for raw_field_path, raw_entry in raw_metadata.items():
        field_path = str(raw_field_path or "").strip()
        if not field_path or "." not in field_path or not isinstance(raw_entry, Mapping):
            continue
        entry = dict(raw_entry)
        entry["status"] = str(entry.get("status") or "user_confirmed").strip().lower()
        entry["source"] = str(entry.get("source") or "unknown").strip() or "unknown"
        entry["confidence"] = str(entry.get("confidence") or "high").strip().lower()
        entry["confirmed_by_user"] = bool(entry.get("confirmed_by_user"))
        if entry.get("last_confirmed_at") is not None:
            entry["last_confirmed_at"] = str(entry.get("last_confirmed_at"))
        if entry.get("updated_at") is not None:
            entry["updated_at"] = str(entry.get("updated_at"))
        if entry.get("captured_at") is not None:
            entry["captured_at"] = str(entry.get("captured_at"))
        try:
            entry["stale_after_days"] = int(entry.get("stale_after_days"))
        except (TypeError, ValueError):
            entry["stale_after_days"] = PROFILE_METADATA_DEFAULT_STALE_AFTER_DAYS.get(field_path, 365)
        normalized[field_path] = entry
    return normalized


class FinancialProfileStore:
    def __init__(self, profile_path: Path):
        self.profile_path = profile_path
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "household_members": [],
            "income_items": [],
            "expense_items": [],
            "debt_items": [],
            "goal_items": [],
            "physical_assets": [],
            "tax_profile": {
                "filing_status": None,
                "marginal_tax_rate": None,
                "effective_tax_rate": None,
                "state_tax_rate": None,
                "state": None,
            },
            "investment_policy": {
                "max_single_symbol_exposure_pct": None,
                "max_sector_exposure_pct": None,
                "minimum_research_confidence": None,
                "minimum_cash_runway_months": None,
                "max_asset_class_exposure_pct": {},
                "target_asset_class_allocation_pct": {},
                "simplicity_preference": None,
                "tax_sensitivity": None,
                "risk_tolerance": None,
                "preferred_account_locations": {},
                "restricted_symbols": [],
                "restricted_sectors": [],
            },
            "flags": {
                "no_debt": False,
                "no_goals": False,
            },
            "profile_metadata": {},
            "notes": "",
            "updated_at": utc_now_iso(),
        }

    def _initialize(self) -> None:
        if self.profile_path.exists():
            return
        self.profile_path.write_text(
            json.dumps(self._default_payload(), indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _ensure_id(items: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for raw in items:
            item = dict(raw)
            item_id = str(item.get("id") or "").strip()
            if not item_id:
                item_id = f"{prefix}-{uuid.uuid4().hex[:10]}"
            item["id"] = item_id
            normalized.append(item)
        return normalized

    def _migrate_payload(self, raw: Any) -> dict[str, Any]:
        defaults = self._default_payload()
        default_policy = dict(defaults.get("investment_policy") or {})
        if isinstance(raw, dict):
            defaults.update(raw)

        # Profiles written before a policy field existed replace the whole
        # investment_policy dict on update; backfill new keys from defaults.
        raw_policy = defaults.get("investment_policy")
        defaults["investment_policy"] = {
            **default_policy,
            **(raw_policy if isinstance(raw_policy, dict) else {}),
        }

        defaults["schema_version"] = PROFILE_SCHEMA_VERSION

        defaults["household_members"] = self._ensure_id(
            [item for item in defaults.get("household_members", []) if isinstance(item, dict)],
            "member",
        )
        for item in defaults["household_members"]:
            relationship = str(item.get("relationship") or "other").strip().lower()
            if relationship not in {"self", "partner", "child", "dependent", "other"}:
                relationship = "other"
            item["relationship"] = relationship
            item["display_name"] = str(
                item.get("display_name") or item.get("label") or "Household member"
            ).strip() or "Household member"
            item["dependent"] = bool(item.get("dependent") or relationship in {"child", "dependent"})
            item.setdefault("birth_year", None)
            item.setdefault("retirement_age", None)
            item.setdefault("notes", "")

        defaults["income_items"] = self._ensure_id(
            [item for item in defaults.get("income_items", []) if isinstance(item, dict)],
            "income",
        )
        for item in defaults["income_items"]:
            item.setdefault("annual_growth_rate", None)
            item.setdefault("start_date", None)
            item.setdefault("end_date", None)

        defaults["expense_items"] = self._ensure_id(
            [item for item in defaults.get("expense_items", []) if isinstance(item, dict)],
            "expense",
        )
        for item in defaults["expense_items"]:
            item.setdefault("inflation_rate", None)
            item.setdefault("start_date", None)
            item.setdefault("end_date", None)

        defaults["debt_items"] = self._ensure_id(
            [item for item in defaults.get("debt_items", []) if isinstance(item, dict)],
            "debt",
        )
        for item in defaults["debt_items"]:
            item.setdefault("payoff_strategy", "minimum")
            item.setdefault("custom_monthly_payment_usd", None)

        defaults["goal_items"] = self._ensure_id(
            [item for item in defaults.get("goal_items", []) if isinstance(item, dict)],
            "goal",
        )

        defaults["physical_assets"] = self._ensure_id(
            [item for item in defaults.get("physical_assets", []) if isinstance(item, dict)],
            "asset",
        )
        for item in defaults["physical_assets"]:
            item.setdefault("asset_type", "other")
            item.setdefault("annual_growth_rate", None)
            item.setdefault("purchase_date", None)

        tax_profile = defaults.get("tax_profile")
        if not isinstance(tax_profile, dict):
            tax_profile = {}
        tax_defaults = self._default_payload()["tax_profile"]
        tax_defaults.update(tax_profile)
        defaults["tax_profile"] = tax_defaults

        investment_policy = defaults.get("investment_policy")
        if not isinstance(investment_policy, dict):
            investment_policy = {}
        policy_defaults = self._default_payload()["investment_policy"]
        policy_defaults.update(investment_policy)
        defaults["investment_policy"] = policy_defaults

        flags = defaults.get("flags")
        if not isinstance(flags, dict):
            flags = {}
        flag_defaults = self._default_payload()["flags"]
        flag_defaults.update(flags)
        defaults["flags"] = flag_defaults
        defaults["profile_metadata"] = _normalize_profile_metadata(defaults.get("profile_metadata"))

        return defaults

    def get(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except Exception:
            raw = self._default_payload()
        payload = self._migrate_payload(raw)
        self.profile_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    # Backward-compatible alias used by existing route handlers.
    def load(self) -> dict[str, Any]:
        return self.get()

    def save(
        self,
        payload: dict[str, Any],
        *,
        metadata_source: str = "profile_editor",
        metadata_status: str = "user_confirmed",
    ) -> dict[str, Any]:
        current = self.get()
        original = dict(current)
        candidate_paths = patch_material_profile_field_paths(payload)
        current.update(payload)
        current = self._migrate_payload(current)
        now = utc_now_iso()
        changed_paths = changed_material_profile_field_paths(
            original,
            current,
            candidate_paths=candidate_paths or None,
        )
        if changed_paths:
            current = merge_profile_metadata(
                current,
                field_paths=changed_paths,
                source=metadata_source,
                status=metadata_status,
                confidence="high" if metadata_status == "user_confirmed" else "medium",
                now=now,
            )
        current["updated_at"] = now
        self.profile_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_SCHEMA_VERSION = 2


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class FinancialProfileStore:
    def __init__(self, profile_path: Path):
        self.profile_path = profile_path
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "income_items": [],
            "expense_items": [],
            "debt_items": [],
            "goal_items": [],
            "physical_assets": [],
            "tax_profile": {
                "filing_status": None,
                "marginal_tax_rate": None,
                "effective_tax_rate": None,
                "state": None,
            },
            "flags": {
                "no_debt": False,
                "no_goals": False,
            },
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
        if isinstance(raw, dict):
            defaults.update(raw)

        defaults["schema_version"] = PROFILE_SCHEMA_VERSION

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

        flags = defaults.get("flags")
        if not isinstance(flags, dict):
            flags = {}
        flag_defaults = self._default_payload()["flags"]
        flag_defaults.update(flags)
        defaults["flags"] = flag_defaults

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

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get()
        current.update(payload)
        current = self._migrate_payload(current)
        current["updated_at"] = utc_now_iso()
        self.profile_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current

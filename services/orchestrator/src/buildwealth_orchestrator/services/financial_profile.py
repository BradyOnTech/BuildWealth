from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
            "income_items": [],
            "expense_items": [],
            "debt_items": [],
            "goal_items": [],
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

    def get(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.profile_path.read_text(encoding="utf-8"))
        except Exception:
            raw = self._default_payload()

        defaults = self._default_payload()
        if isinstance(raw, dict):
            defaults.update(raw)

        defaults["income_items"] = self._ensure_id(
            [item for item in defaults.get("income_items", []) if isinstance(item, dict)],
            "income",
        )
        defaults["expense_items"] = self._ensure_id(
            [item for item in defaults.get("expense_items", []) if isinstance(item, dict)],
            "expense",
        )
        defaults["debt_items"] = self._ensure_id(
            [item for item in defaults.get("debt_items", []) if isinstance(item, dict)],
            "debt",
        )
        defaults["goal_items"] = self._ensure_id(
            [item for item in defaults.get("goal_items", []) if isinstance(item, dict)],
            "goal",
        )

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

    def save(self, payload: dict[str, Any]) -> dict[str, Any]:
        current = self.get()
        current.update(payload)
        current["income_items"] = self._ensure_id(
            [item for item in current.get("income_items", []) if isinstance(item, dict)],
            "income",
        )
        current["expense_items"] = self._ensure_id(
            [item for item in current.get("expense_items", []) if isinstance(item, dict)],
            "expense",
        )
        current["debt_items"] = self._ensure_id(
            [item for item in current.get("debt_items", []) if isinstance(item, dict)],
            "debt",
        )
        current["goal_items"] = self._ensure_id(
            [item for item in current.get("goal_items", []) if isinstance(item, dict)],
            "goal",
        )
        current["updated_at"] = utc_now_iso()
        self.profile_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
        return current

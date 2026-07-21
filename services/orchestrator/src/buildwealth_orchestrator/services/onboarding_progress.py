from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.store_locks import synchronized_store


ONBOARDING_SCHEMA_VERSION = 1
ONBOARDING_EXPERIENCE_VERSION = "first-outcome-v1"
ONBOARDING_STEPS = (
    "welcome",
    "foundation",
    "portfolio",
    "future",
    "first_picture",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@synchronized_store("path")
class OnboardingProgressStore:
    """Durable, workspace-scoped progress through the first-outcome journey.

    Financial readiness remains derived from Canonical State. This store only
    records the user's journey through Setup so pausing or skipping a step is
    not confused with saying that the underlying financial context is ready.
    """

    def __init__(self, path: Path):
        self.path = path

    def get(self) -> dict[str, Any]:
        payload = self._read()
        return self._response(payload)

    def start(self) -> dict[str, Any]:
        existing = self._read()
        if existing is not None:
            return self._response(existing)
        now = _utc_now_iso()
        payload = {
            "schema_version": ONBOARDING_SCHEMA_VERSION,
            "experience_version": ONBOARDING_EXPERIENCE_VERSION,
            "status": "active",
            "current_step": ONBOARDING_STEPS[0],
            "completed_steps": [],
            "skipped_steps": [],
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
        }
        self._write(payload)
        return self._response(payload)

    def update(
        self,
        *,
        current_step: str | None = None,
        completed_step: str | None = None,
        skipped_step: str | None = None,
        complete: bool = False,
    ) -> dict[str, Any]:
        payload = self._read()
        if payload is None:
            payload = self.start()

        if current_step is not None:
            self._validate_step(current_step)
            payload["current_step"] = current_step
        if completed_step is not None:
            self._validate_step(completed_step)
            payload["completed_steps"] = self._append_unique(
                payload.get("completed_steps"),
                completed_step,
            )
            payload["skipped_steps"] = self._without(payload.get("skipped_steps"), completed_step)
        if skipped_step is not None:
            self._validate_step(skipped_step)
            payload["skipped_steps"] = self._append_unique(
                payload.get("skipped_steps"),
                skipped_step,
            )
            payload["completed_steps"] = self._without(payload.get("completed_steps"), skipped_step)
        if complete:
            payload["status"] = "complete"
            payload["current_step"] = ONBOARDING_STEPS[-1]
            payload["completed_at"] = _utc_now_iso()

        payload["updated_at"] = _utc_now_iso()
        self._write(payload)
        return self._response(payload)

    def _read(self) -> dict[str, Any] | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            return None
        if not isinstance(raw, dict):
            return None
        return self._normalize(raw)

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(self._normalize(payload), indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        status = str(raw.get("status") or "active").strip().lower()
        if status not in {"active", "complete"}:
            status = "active"
        current_step = str(raw.get("current_step") or ONBOARDING_STEPS[0]).strip()
        if current_step not in ONBOARDING_STEPS:
            current_step = ONBOARDING_STEPS[0]
        completed_steps = self._valid_steps(raw.get("completed_steps"))
        skipped_steps = [step for step in self._valid_steps(raw.get("skipped_steps")) if step not in completed_steps]
        return {
            "schema_version": ONBOARDING_SCHEMA_VERSION,
            "experience_version": str(
                raw.get("experience_version") or ONBOARDING_EXPERIENCE_VERSION
            ),
            "status": status,
            "current_step": current_step,
            "completed_steps": completed_steps,
            "skipped_steps": skipped_steps,
            "started_at": raw.get("started_at"),
            "updated_at": raw.get("updated_at"),
            "completed_at": raw.get("completed_at") if status == "complete" else None,
        }

    @staticmethod
    def _validate_step(step: str) -> None:
        if step not in ONBOARDING_STEPS:
            raise ValueError(f"Unknown onboarding step: {step}")

    @staticmethod
    def _append_unique(values: Any, value: str) -> list[str]:
        items = [str(item) for item in values] if isinstance(values, list) else []
        return items if value in items else [*items, value]

    @staticmethod
    def _without(values: Any, value: str) -> list[str]:
        return [str(item) for item in values if str(item) != value] if isinstance(values, list) else []

    @staticmethod
    def _valid_steps(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return list(dict.fromkeys(str(item) for item in values if str(item) in ONBOARDING_STEPS))

    @staticmethod
    def _response(payload: dict[str, Any] | None) -> dict[str, Any]:
        if payload is None:
            return {
                "schema_version": ONBOARDING_SCHEMA_VERSION,
                "experience_version": ONBOARDING_EXPERIENCE_VERSION,
                "started": False,
                "needs_setup": False,
                "status": "not_started",
                "current_step": ONBOARDING_STEPS[0],
                "completed_steps": [],
                "skipped_steps": [],
                "started_at": None,
                "updated_at": None,
                "completed_at": None,
            }
        return {
            **payload,
            "started": True,
            "needs_setup": payload.get("status") != "complete",
        }

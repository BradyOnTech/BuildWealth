from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.schemas import RecommendationStatus
from buildwealth_orchestrator.services.store_locks import synchronized_store
from buildwealth_orchestrator.services.json_store_migrations import migrate_payload


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class RecommendationNotFoundError(FileNotFoundError):
    pass


@synchronized_store('storage_path')
class RecommendationInbox:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {"recommendations": []}

    def _initialize(self) -> None:
        if self.storage_path.exists():
            return
        self.storage_path.write_text(
            json.dumps(self._default_payload(), indent=2),
            encoding="utf-8",
        )

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except Exception:
            payload = self._default_payload()

        if not isinstance(payload, dict):
            payload = self._default_payload()

        rows = payload.get("recommendations")
        if not isinstance(rows, list):
            rows = []
        payload["recommendations"] = [row for row in rows if isinstance(row, dict)]
        payload, migrated = migrate_payload("recommendations_inbox", payload)
        if migrated:
            self._save(payload)
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def list(
        self,
        limit: int | None = 100,
        status: RecommendationStatus | None = None,
        plan_id: str | None = None,
        include_archived: bool = False,
        sort: str = "created_at_desc",
    ) -> list[dict[str, Any]]:
        payload = self._load()
        rows = list(payload.get("recommendations", []))

        if status is not None:
            rows = [row for row in rows if str(row.get("status", "")).strip().lower() == status]
        elif not include_archived:
            rows = [row for row in rows if str(row.get("status", "")).strip().lower() != "archived"]

        if plan_id is not None:
            cleaned_plan_id = plan_id.strip()
            rows = [row for row in rows if str(row.get("plan_id") or "").strip() == cleaned_plan_id]

        normalized_sort = str(sort or "created_at_desc").strip().lower()
        if normalized_sort == "created_at_asc":
            rows.sort(key=lambda item: str(item.get("created_at", "")))
        elif normalized_sort == "none":
            pass
        else:
            rows.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)

        if limit is None:
            return rows

        bounded_limit = max(1, min(int(limit), 5000))
        return rows[:bounded_limit]

    def get(self, recommendation_id: str) -> dict[str, Any]:
        payload = self._load()
        for row in payload.get("recommendations", []):
            if str(row.get("id")) == recommendation_id:
                return dict(row)
        raise RecommendationNotFoundError(f"Recommendation not found: {recommendation_id}")

    def create(
        self,
        *,
        title: str,
        detail: str,
        priority: str = "medium",
        recommendation_type: str = "general",
        source: str = "manual",
        plan_id: str | None = None,
        action_payload: dict[str, Any] | None = None,
        status: RecommendationStatus = "proposed",
    ) -> dict[str, Any]:
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("title is required")

        cleaned_detail = detail.strip()
        if not cleaned_detail:
            raise ValueError("detail is required")

        now = utc_now_iso()
        recommendation = {
            "id": f"rec-{utc_now().strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}",
            "created_at": now,
            "updated_at": now,
            "title": cleaned_title,
            "detail": cleaned_detail,
            "priority": (priority or "medium").strip().lower(),
            "status": status,
            "recommendation_type": (recommendation_type or "general").strip().lower(),
            "source": (source or "manual").strip().lower(),
            "plan_id": (plan_id or "").strip() or None,
            "action_payload": action_payload if isinstance(action_payload, dict) else {},
            "resolution_note": "",
            "resolved_at": None,
        }

        payload = self._load()
        payload.setdefault("recommendations", []).append(recommendation)
        self._save(payload)
        return recommendation

    def update(self, recommendation_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        payload = self._load()
        rows = payload.get("recommendations", [])

        for index, row in enumerate(rows):
            if str(row.get("id")) != recommendation_id:
                continue

            merged = dict(row)
            if "title" in updates and updates.get("title") is not None:
                title = str(updates.get("title") or "").strip()
                if not title:
                    raise ValueError("title cannot be empty")
                merged["title"] = title

            if "detail" in updates and updates.get("detail") is not None:
                detail = str(updates.get("detail") or "").strip()
                if not detail:
                    raise ValueError("detail cannot be empty")
                merged["detail"] = detail

            if "priority" in updates and updates.get("priority") is not None:
                merged["priority"] = str(updates.get("priority") or "medium").strip().lower()

            if "recommendation_type" in updates and updates.get("recommendation_type") is not None:
                merged["recommendation_type"] = str(
                    updates.get("recommendation_type") or "general"
                ).strip().lower()

            if "source" in updates and updates.get("source") is not None:
                merged["source"] = str(updates.get("source") or "manual").strip().lower() or "manual"

            if "plan_id" in updates:
                merged["plan_id"] = str(updates.get("plan_id") or "").strip() or None

            if "action_payload" in updates and updates.get("action_payload") is not None:
                action_payload = updates.get("action_payload")
                if not isinstance(action_payload, dict):
                    raise ValueError("action_payload must be an object")
                merged["action_payload"] = action_payload

            merged["updated_at"] = utc_now_iso()
            rows[index] = merged
            payload["recommendations"] = rows
            self._save(payload)
            return merged

        raise RecommendationNotFoundError(f"Recommendation not found: {recommendation_id}")

    def restore(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(recommendation, dict):
            raise ValueError("recommendation restore payload must be an object")
        recommendation_id = str(recommendation.get("id") or "").strip()
        if not recommendation_id:
            raise ValueError("recommendation restore payload requires id")
        title = str(recommendation.get("title") or "").strip()
        if not title:
            raise ValueError("recommendation restore payload requires title")
        detail = str(recommendation.get("detail") or "").strip()
        if not detail:
            raise ValueError("recommendation restore payload requires detail")

        restored = dict(recommendation)
        restored["id"] = recommendation_id
        restored["title"] = title
        restored["detail"] = detail
        restored["priority"] = str(restored.get("priority") or "medium").strip().lower()
        restored["status"] = str(restored.get("status") or "proposed").strip().lower()
        restored["recommendation_type"] = str(
            restored.get("recommendation_type") or "general"
        ).strip().lower()
        restored["source"] = str(restored.get("source") or "git_restore").strip().lower() or "git_restore"
        restored["plan_id"] = str(restored.get("plan_id") or "").strip() or None
        if not isinstance(restored.get("action_payload"), dict):
            restored["action_payload"] = {}
        restored["updated_at"] = utc_now_iso()

        payload = self._load()
        rows = payload.get("recommendations", [])
        for index, row in enumerate(rows):
            if str(row.get("id")) == recommendation_id:
                rows[index] = restored
                payload["recommendations"] = rows
                self._save(payload)
                return restored

        rows.append(restored)
        payload["recommendations"] = rows
        self._save(payload)
        return restored

    def set_status(
        self,
        recommendation_id: str,
        status: RecommendationStatus,
        resolution_note: str = "",
    ) -> dict[str, Any]:
        payload = self._load()
        rows = payload.get("recommendations", [])

        for index, row in enumerate(rows):
            if str(row.get("id")) != recommendation_id:
                continue

            merged = dict(row)
            merged["status"] = status
            merged["updated_at"] = utc_now_iso()

            cleaned_note = resolution_note.strip()
            merged["resolution_note"] = cleaned_note
            if status in {"applied", "rejected"}:
                merged["resolved_at"] = utc_now_iso()
            elif status == "proposed":
                merged["resolved_at"] = None

            rows[index] = merged
            payload["recommendations"] = rows
            self._save(payload)
            return merged

        raise RecommendationNotFoundError(f"Recommendation not found: {recommendation_id}")

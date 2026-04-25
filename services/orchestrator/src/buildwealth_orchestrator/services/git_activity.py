"""Durable append-only activity feed for BuildWealth Git actions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROTECTED_EVENT_TYPES = {"checkpoint", "restore_preview", "restore_apply"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GitActivityStore:
    def __init__(self, activity_path: Path):
        self.activity_path = activity_path
        self.activity_path.parent.mkdir(parents=True, exist_ok=True)

    def record(
        self,
        *,
        event_type: str,
        title: str,
        message: str = "",
        status: str = "ok",
        ref: str | None = None,
        paths: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event = {
            "id": f"git-activity-{uuid.uuid4().hex[:12]}",
            "created_at": utc_now_iso(),
            "event_type": str(event_type or "git_event").strip().lower(),
            "title": str(title or "Git activity").strip(),
            "message": str(message or "").strip(),
            "status": str(status or "ok").strip().lower(),
            "ref": str(ref).strip() if ref else None,
            "paths": [
                str(path).strip()
                for path in (paths or [])
                if path is not None and str(path).strip()
            ],
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
        with self.activity_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=str, sort_keys=True))
            handle.write("\n")
        return event

    def list(
        self,
        *,
        limit: int = 50,
        event_type: str | None = None,
        status: str | None = None,
        ref: str | None = None,
        search: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.query(
            limit=limit,
            event_type=event_type,
            status=status,
            ref=ref,
            search=search,
        )["events"]

    def query(
        self,
        *,
        limit: int = 50,
        event_type: str | None = None,
        status: str | None = None,
        ref: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        if not self.activity_path.exists():
            return {
                "events": [],
                "summary": {"total_matched": 0, "event_type_counts": {}, "status_counts": {}},
            }
        bounded_limit = max(1, min(int(limit), 500))
        cleaned_event_type = str(event_type or "").strip().lower()
        cleaned_status = str(status or "").strip().lower()
        cleaned_ref = str(ref or "").strip()
        cleaned_search = str(search or "").strip().lower()
        rows: list[dict[str, Any]] = []
        event_type_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        total_matched = 0
        for line in reversed(self.activity_path.read_text(encoding="utf-8").splitlines()):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if cleaned_event_type and str(event.get("event_type") or "").lower() != cleaned_event_type:
                continue
            if cleaned_status and str(event.get("status") or "").lower() != cleaned_status:
                continue
            if cleaned_ref and str(event.get("ref") or "") != cleaned_ref:
                continue
            if cleaned_search and cleaned_search not in self._search_blob(event):
                continue
            total_matched += 1
            type_key = str(event.get("event_type") or "unknown")
            status_key = str(event.get("status") or "unknown")
            event_type_counts[type_key] = event_type_counts.get(type_key, 0) + 1
            status_counts[status_key] = status_counts.get(status_key, 0) + 1
            if len(rows) < bounded_limit:
                rows.append(event)
        return {
            "events": rows,
            "summary": {
                "total_matched": total_matched,
                "event_type_counts": event_type_counts,
                "status_counts": status_counts,
            },
        }

    def cleanup(
        self,
        *,
        dry_run: bool = True,
        max_events: int | None = None,
        max_age_days: int | None = None,
        include_protected: bool = False,
        export_confirmed: bool = False,
    ) -> dict[str, Any]:
        if not self.activity_path.exists():
            return self._cleanup_result(
                dry_run=dry_run,
                total_events=0,
                retained=[],
                removable=[],
                include_protected=include_protected,
                max_events=max_events,
                max_age_days=max_age_days,
            )
        if not dry_run and not export_confirmed:
            raise ValueError("Activity cleanup requires export_confirmed=true. Export the activity feed before cleanup.")

        rows = self._read_rows_oldest_first()
        removable_ids = self._removable_event_ids(
            rows=rows,
            max_events=max_events,
            max_age_days=max_age_days,
            include_protected=include_protected,
        )
        retained = [event for event in rows if str(event.get("id") or "") not in removable_ids]
        removable = [event for event in rows if str(event.get("id") or "") in removable_ids]
        result = self._cleanup_result(
            dry_run=dry_run,
            total_events=len(rows),
            retained=retained,
            removable=removable,
            include_protected=include_protected,
            max_events=max_events,
            max_age_days=max_age_days,
        )
        if not dry_run:
            self._write_rows(retained)
        return result

    def _read_rows_oldest_first(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in self.activity_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                rows.append(event)
        return rows

    def _write_rows(self, rows: list[dict[str, Any]]) -> None:
        with self.activity_path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, default=str, sort_keys=True))
                handle.write("\n")

    def _removable_event_ids(
        self,
        *,
        rows: list[dict[str, Any]],
        max_events: int | None,
        max_age_days: int | None,
        include_protected: bool,
    ) -> set[str]:
        removable: set[str] = set()
        cutoff = None
        if max_age_days is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(days=max(0, int(max_age_days)))
        for event in rows:
            event_id = str(event.get("id") or "")
            if not event_id or self._is_protected(event, include_protected=include_protected):
                continue
            if cutoff is not None:
                created_at = self._parse_created_at(event)
                if created_at is not None and created_at < cutoff:
                    removable.add(event_id)

        if max_events is not None:
            kept_count = 0
            target = max(0, int(max_events))
            for event in reversed(rows):
                event_id = str(event.get("id") or "")
                if not event_id:
                    continue
                if event_id in removable:
                    continue
                if self._is_protected(event, include_protected=include_protected):
                    kept_count += 1
                    continue
                if kept_count < target:
                    kept_count += 1
                else:
                    removable.add(event_id)
        return removable

    @staticmethod
    def _is_protected(event: dict[str, Any], *, include_protected: bool) -> bool:
        if include_protected:
            return False
        return str(event.get("event_type") or "").lower() in PROTECTED_EVENT_TYPES

    @staticmethod
    def _parse_created_at(event: dict[str, Any]) -> datetime | None:
        raw = event.get("created_at")
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _cleanup_result(
        *,
        dry_run: bool,
        total_events: int,
        retained: list[dict[str, Any]],
        removable: list[dict[str, Any]],
        include_protected: bool,
        max_events: int | None,
        max_age_days: int | None,
    ) -> dict[str, Any]:
        protected_skipped = [
            event
            for event in retained
            if str(event.get("event_type") or "").lower() in PROTECTED_EVENT_TYPES
        ]
        return {
            "dry_run": dry_run,
            "message": (
                f"{'Would remove' if dry_run else 'Removed'} {len(removable)} Git activity event(s); "
                f"{len(retained)} retained."
            ),
            "total_events": total_events,
            "events_removed": len(removable),
            "events_retained": len(retained),
            "protected_events_skipped": len(protected_skipped) if not include_protected else 0,
            "max_events": max_events,
            "max_age_days": max_age_days,
            "include_protected": include_protected,
            "removable_event_ids": [str(event.get("id") or "") for event in removable],
            "warnings": [
                "Export the filtered activity feed before cleanup.",
                "Checkpoint and restore audit events are protected unless include_protected=true.",
            ],
        }

    @staticmethod
    def _search_blob(event: dict[str, Any]) -> str:
        return json.dumps(
            {
                "event_type": event.get("event_type"),
                "title": event.get("title"),
                "message": event.get("message"),
                "status": event.get("status"),
                "ref": event.get("ref"),
                "paths": event.get("paths"),
                "metadata": event.get("metadata"),
            },
            sort_keys=True,
            default=str,
        ).lower()

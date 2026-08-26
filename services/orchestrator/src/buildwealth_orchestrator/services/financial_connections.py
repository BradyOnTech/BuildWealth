"""Workspace-owned persistence for read-only financial connections.

Provider access tokens do not belong here.  They live in WorkspaceSecretStore
under ``financial_connection:<provider>:<connection_id>:access_token``.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.store_locks import synchronized_store


FINANCIAL_CONNECTION_SCHEMA_VERSION = 1
OBSERVATION_SCHEMA_VERSION = 1
VALID_CONNECTION_STATUSES = {
    "pending_review",
    "active",
    "needs_attention",
    "disconnect_pending",
    "disconnected",
    "error",
}
VALID_MATCH_STATUSES = {"suggested", "confirmed", "created", "ignored"}
VALID_SYNC_OUTCOMES = {"running", "succeeded", "failed", "skipped"}


class FinancialConnectionNotFoundError(FileNotFoundError):
    pass


class FinancialConnectionStoreError(RuntimeError):
    pass


def financial_connection_access_token_key(*, provider: str, connection_id: str) -> str:
    """Return the only supported workspace-secret key for a provider token."""
    normalized_provider = _required_text(provider, "provider").lower()
    normalized_connection_id = _required_text(connection_id, "connection_id")
    for value, field in (
        (normalized_provider, "provider"),
        (normalized_connection_id, "connection_id"),
    ):
        if any(not (character.isalnum() or character in {"-", "_"}) for character in value):
            raise ValueError(f"{field} contains unsupported characters")
    return f"financial_connection:{normalized_provider}:{normalized_connection_id}:access_token"


def save_financial_connection_access_token(
    secret_store: Any,
    *,
    provider: str,
    connection_id: str,
    access_token: str,
) -> None:
    token = _required_text(access_token, "access_token")
    secret_store.set_secret(
        financial_connection_access_token_key(
            provider=provider,
            connection_id=connection_id,
        ),
        token,
    )


def load_financial_connection_access_token(
    secret_store: Any,
    *,
    provider: str,
    connection_id: str,
) -> str:
    return str(
        secret_store.get_secret(
            financial_connection_access_token_key(
                provider=provider,
                connection_id=connection_id,
            )
        )
        or ""
    )


def remove_financial_connection_access_token(
    secret_store: Any,
    *,
    provider: str,
    connection_id: str,
) -> None:
    secret_store.remove_secret(
        financial_connection_access_token_key(
            provider=provider,
            connection_id=connection_id,
        )
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number")
    return number


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return list(dict.fromkeys(text for item in value if (text := str(item or "").strip())))


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, allow_nan=False, indent=2, sort_keys=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except OSError as exc:
        raise FinancialConnectionStoreError(
            f"Unable to atomically write financial connection store: {path}"
        ) from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


@synchronized_store("storage_dir")
class FinancialConnectionStore:
    """Versioned metadata, sync-run, mapping, and observation persistence."""

    def __init__(self, storage_dir: Path, *, workspace_id: str):
        self.storage_dir = Path(storage_dir)
        self.workspace_id = _required_text(workspace_id, "workspace_id")
        self.metadata_path = self.storage_dir / "connections.json"
        self.observations_dir = self.storage_dir / "observations"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.observations_dir.mkdir(parents=True, exist_ok=True)
        if not self.metadata_path.exists():
            self._save_metadata(self._default_metadata())
        else:
            self._load_metadata()

    def _default_metadata(self) -> dict[str, Any]:
        return {
            "schema_version": FINANCIAL_CONNECTION_SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "connections": [],
            "account_mappings": [],
            "sync_runs": [],
            "connection_reports": [],
            "webhook_events": [],
            "updated_at": _utc_now_iso(),
        }

    def _load_metadata(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FinancialConnectionStoreError(
                f"Financial connection metadata is unreadable: {self.metadata_path}"
            ) from exc
        if not isinstance(raw, dict):
            raise FinancialConnectionStoreError("Financial connection metadata must be an object")
        try:
            schema_version = int(raw.get("schema_version") or 0)
        except (TypeError, ValueError) as exc:
            raise FinancialConnectionStoreError(
                "Financial connection metadata has an invalid schema version"
            ) from exc
        if schema_version > FINANCIAL_CONNECTION_SCHEMA_VERSION:
            raise FinancialConnectionStoreError(
                "Financial connection metadata was written by a newer BuildWealth version"
            )
        stored_workspace_id = str(raw.get("workspace_id") or "").strip()
        if stored_workspace_id and stored_workspace_id != self.workspace_id:
            raise FinancialConnectionStoreError("Financial connection store belongs to another workspace")

        normalized = self._default_metadata()
        normalized["connections"] = [
            self._normalize_connection(row)
            for row in raw.get("connections", [])
            if isinstance(row, dict)
        ]
        connection_ids = [row["connection_id"] for row in normalized["connections"]]
        if len(connection_ids) != len(set(connection_ids)):
            raise FinancialConnectionStoreError("Duplicate connection_id in connection store")

        normalized["account_mappings"] = [
            self._normalize_mapping(row)
            for row in raw.get("account_mappings", [])
            if isinstance(row, dict)
        ]
        mapping_keys = [
            (row["connection_id"], row["provider_account_id"])
            for row in normalized["account_mappings"]
        ]
        if len(mapping_keys) != len(set(mapping_keys)):
            raise FinancialConnectionStoreError("Duplicate provider account mapping in connection store")

        normalized["sync_runs"] = [
            self._normalize_sync_run(row)
            for row in raw.get("sync_runs", [])
            if isinstance(row, dict)
        ]
        run_ids = [row["sync_run_id"] for row in normalized["sync_runs"]]
        if len(run_ids) != len(set(run_ids)):
            raise FinancialConnectionStoreError("Duplicate sync_run_id in connection store")
        normalized["connection_reports"] = [
            self._normalize_connection_report(row)
            for row in raw.get("connection_reports", [])
            if isinstance(row, dict)
        ]
        report_ids = [row["report_id"] for row in normalized["connection_reports"]]
        if len(report_ids) != len(set(report_ids)):
            raise FinancialConnectionStoreError("Duplicate report_id in connection store")
        normalized["webhook_events"] = [
            self._normalize_webhook_event(row)
            for row in raw.get("webhook_events", [])
            if isinstance(row, dict)
        ]
        event_ids = [row["event_id"] for row in normalized["webhook_events"]]
        if len(event_ids) != len(set(event_ids)):
            raise FinancialConnectionStoreError("Duplicate event_id in connection store")
        normalized["webhook_events"] = normalized["webhook_events"][-500:]
        normalized["updated_at"] = str(raw.get("updated_at") or _utc_now_iso())
        if normalized != raw:
            self._save_metadata(normalized)
        return normalized

    def _save_metadata(self, payload: dict[str, Any]) -> None:
        payload["schema_version"] = FINANCIAL_CONNECTION_SCHEMA_VERSION
        payload["workspace_id"] = self.workspace_id
        _atomic_write_json(self.metadata_path, payload)

    def list_connections(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._load_metadata()["connections"]]

    def get_connection(self, connection_id: str) -> dict[str, Any]:
        target = _required_text(connection_id, "connection_id")
        for row in self._load_metadata()["connections"]:
            if row["connection_id"] == target:
                return dict(row)
        raise FinancialConnectionNotFoundError(f"Financial connection not found: {target}")

    def upsert_connection(self, connection: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(connection, dict):
            raise ValueError("connection must be an object")
        now = _utc_now_iso()
        candidate = dict(connection)
        candidate.setdefault("connection_id", f"conn_{uuid.uuid4().hex[:16]}")
        candidate.setdefault("workspace_id", self.workspace_id)
        candidate.setdefault("created_at", now)
        candidate["updated_at"] = now
        normalized = self._normalize_connection(candidate)

        payload = self._load_metadata()
        rows = payload["connections"]
        for index, existing in enumerate(rows):
            if existing["connection_id"] != normalized["connection_id"]:
                if (
                    existing["provider"] == normalized["provider"]
                    and existing["provider_item_id"] == normalized["provider_item_id"]
                ):
                    raise ValueError("Provider Item is already stored as another connection")
                continue
            if any(
                existing[field] != normalized[field]
                for field in ("workspace_id", "provider", "provider_item_id")
            ):
                raise ValueError("Cannot change a connection's provider identity")
            normalized["created_at"] = existing["created_at"]
            rows[index] = normalized
            break
        else:
            rows.append(normalized)
        payload["updated_at"] = now
        self._save_metadata(payload)
        return dict(normalized)

    def update_connection(self, connection_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get_connection(connection_id)
        immutable = {"connection_id", "workspace_id", "provider", "provider_item_id", "created_at"}
        attempted = immutable.intersection(updates)
        if attempted:
            raise ValueError(f"Cannot update immutable connection fields: {', '.join(sorted(attempted))}")
        return self.upsert_connection({**current, **updates})

    def delete_connection(self, connection_id: str, *, delete_observations: bool = True) -> bool:
        target = _required_text(connection_id, "connection_id")
        payload = self._load_metadata()
        original_count = len(payload["connections"])
        payload["connections"] = [
            row for row in payload["connections"] if row["connection_id"] != target
        ]
        if len(payload["connections"]) == original_count:
            return False
        payload["account_mappings"] = [
            row for row in payload["account_mappings"] if row["connection_id"] != target
        ]
        payload["updated_at"] = _utc_now_iso()
        self._save_metadata(payload)
        if delete_observations:
            self._observation_path(target).unlink(missing_ok=True)
        return True

    def list_account_mappings(self, connection_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._load_metadata()["account_mappings"]
        if connection_id is not None:
            target = _required_text(connection_id, "connection_id")
            rows = [row for row in rows if row["connection_id"] == target]
        return [dict(row) for row in rows]

    def upsert_account_mapping(self, mapping: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(mapping, dict):
            raise ValueError("mapping must be an object")
        normalized = self._normalize_mapping(mapping)
        self.get_connection(normalized["connection_id"])
        payload = self._load_metadata()
        rows = payload["account_mappings"]
        key = (normalized["connection_id"], normalized["provider_account_id"])
        for index, existing in enumerate(rows):
            if (existing["connection_id"], existing["provider_account_id"]) == key:
                rows[index] = normalized
                break
        else:
            rows.append(normalized)
        payload["updated_at"] = _utc_now_iso()
        self._save_metadata(payload)
        return dict(normalized)

    def remove_account_mapping(self, *, connection_id: str, provider_account_id: str) -> bool:
        target = (
            _required_text(connection_id, "connection_id"),
            _required_text(provider_account_id, "provider_account_id"),
        )
        payload = self._load_metadata()
        rows = payload["account_mappings"]
        payload["account_mappings"] = [
            row
            for row in rows
            if (row["connection_id"], row["provider_account_id"]) != target
        ]
        if len(payload["account_mappings"]) == len(rows):
            return False
        payload["updated_at"] = _utc_now_iso()
        self._save_metadata(payload)
        return True

    def replace_account_mappings(
        self,
        connection_id: str,
        mappings: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Atomically replace a connection's mappings after review approval."""
        target = _required_text(connection_id, "connection_id")
        self.get_connection(target)
        normalized = [
            self._normalize_mapping({**mapping, "connection_id": target})
            for mapping in mappings
            if isinstance(mapping, dict)
        ]
        provider_account_ids = [row["provider_account_id"] for row in normalized]
        if len(provider_account_ids) != len(set(provider_account_ids)):
            raise ValueError("Account mappings contain duplicate provider_account_id values")
        payload = self._load_metadata()
        payload["account_mappings"] = [
            row for row in payload["account_mappings"] if row["connection_id"] != target
        ] + normalized
        payload["updated_at"] = _utc_now_iso()
        self._save_metadata(payload)
        return [dict(row) for row in normalized]

    def start_sync_run(
        self,
        *,
        connection_id: str,
        trigger: str,
        sync_run_id: str | None = None,
    ) -> dict[str, Any]:
        target = _required_text(connection_id, "connection_id")
        self.get_connection(target)
        payload = self._load_metadata()
        now_value = datetime.now(timezone.utc)
        recovered = False
        for index, existing in enumerate(payload["sync_runs"]):
            if existing["connection_id"] != target or existing["outcome"] != "running":
                continue
            try:
                started = datetime.fromisoformat(str(existing.get("started_at") or ""))
            except ValueError:
                started = None
            if started is not None and started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if started is None or (now_value - started).total_seconds() >= 900:
                payload["sync_runs"][index] = self._normalize_sync_run(
                    {
                        **existing,
                        "outcome": "failed",
                        "completed_at": now_value.isoformat(),
                        "error_code": "STALE_SYNC_RECOVERED",
                    }
                )
                recovered = True
        if recovered:
            payload["updated_at"] = now_value.isoformat()
            self._save_metadata(payload)
        requested_run_id = sync_run_id or f"sync_{uuid.uuid4().hex[:16]}"
        for existing in payload["sync_runs"]:
            if existing["sync_run_id"] != requested_run_id:
                continue
            if existing["connection_id"] != target:
                raise ValueError("sync_run_id belongs to another connection")
            return dict(existing)
        if any(
            row["connection_id"] == target and row["outcome"] == "running"
            for row in payload["sync_runs"]
        ):
            raise FinancialConnectionStoreError("A sync is already running for this connection")
        now = _utc_now_iso()
        run = self._normalize_sync_run(
            {
                "sync_run_id": requested_run_id,
                "connection_id": target,
                "trigger": trigger,
                "outcome": "running",
                "started_at": now,
            }
        )
        payload["sync_runs"].append(run)
        payload["updated_at"] = now
        self._save_metadata(payload)
        return dict(run)

    def finish_sync_run(
        self,
        sync_run_id: str,
        *,
        outcome: str,
        provider_request_ids: list[str] | None = None,
        counts: dict[str, int] | None = None,
        warnings: list[str] | None = None,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        target = _required_text(sync_run_id, "sync_run_id")
        normalized_outcome = str(outcome or "").strip().lower()
        if normalized_outcome not in VALID_SYNC_OUTCOMES - {"running"}:
            raise ValueError("outcome must be succeeded, failed, or skipped")
        payload = self._load_metadata()
        for index, run in enumerate(payload["sync_runs"]):
            if run["sync_run_id"] != target:
                continue
            if run["outcome"] != "running":
                raise FinancialConnectionStoreError("Sync run is already complete")
            completed = self._normalize_sync_run(
                {
                    **run,
                    "outcome": normalized_outcome,
                    "completed_at": _utc_now_iso(),
                    "provider_request_ids": provider_request_ids or [],
                    "counts": counts or {},
                    "warnings": warnings or [],
                    "error_code": error_code,
                }
            )
            payload["sync_runs"][index] = completed
            payload["updated_at"] = completed["completed_at"]
            self._save_metadata(payload)
            return dict(completed)
        raise FinancialConnectionNotFoundError(f"Sync run not found: {target}")

    def list_sync_runs(self, connection_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._load_metadata()["sync_runs"]
        if connection_id is not None:
            target = _required_text(connection_id, "connection_id")
            rows = [row for row in rows if row["connection_id"] == target]
        return [dict(row) for row in rows]

    def create_connection_report(self, report: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_connection_report(report)
        self.get_connection(normalized["connection_id"])
        payload = self._load_metadata()
        for existing in payload["connection_reports"]:
            if existing["report_id"] == normalized["report_id"]:
                return dict(existing)
        payload["connection_reports"].append(normalized)
        payload["updated_at"] = _utc_now_iso()
        self._save_metadata(payload)
        return dict(normalized)

    def list_connection_reports(
        self,
        connection_id: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._load_metadata()["connection_reports"]
        if connection_id is not None:
            target = _required_text(connection_id, "connection_id")
            rows = [row for row in rows if row["connection_id"] == target]
        return [dict(row) for row in rows]

    def record_webhook_event(
        self,
        *,
        event_id: str,
        connection_id: str,
        event_type: str,
        event_code: str,
        received_at: str | None = None,
    ) -> bool:
        """Record minimal verified-event metadata; return False for a replay."""
        event = self._normalize_webhook_event(
            {
                "event_id": event_id,
                "connection_id": connection_id,
                "event_type": event_type,
                "event_code": event_code,
                "received_at": received_at or _utc_now_iso(),
            }
        )
        self.get_connection(event["connection_id"])
        payload = self._load_metadata()
        if any(row["event_id"] == event["event_id"] for row in payload["webhook_events"]):
            return False
        payload["webhook_events"].append(event)
        payload["webhook_events"] = payload["webhook_events"][-500:]
        payload["updated_at"] = _utc_now_iso()
        self._save_metadata(payload)
        return True

    def claim_webhook_event(self, event_id: str) -> bool:
        """Atomically claim pending webhook work, recovering stale claims."""
        target = _required_text(event_id, "event_id")
        payload = self._load_metadata()
        now = datetime.now(timezone.utc)
        for index, row in enumerate(payload["webhook_events"]):
            if row["event_id"] != target:
                continue
            if row.get("status") == "succeeded":
                return False
            if row.get("status") == "processing":
                try:
                    started = datetime.fromisoformat(str(row.get("processing_started_at") or ""))
                except ValueError:
                    started = None
                if started is not None and (now - started).total_seconds() < 900:
                    return False
            payload["webhook_events"][index] = self._normalize_webhook_event(
                {
                    **row,
                    "status": "processing",
                    "attempts": int(row.get("attempts") or 0) + 1,
                    "processing_started_at": now.isoformat(),
                    "last_error_code": None,
                }
            )
            payload["updated_at"] = now.isoformat()
            self._save_metadata(payload)
            return True
        return False

    def finish_webhook_event(
        self,
        event_id: str,
        *,
        succeeded: bool,
        error_code: str | None = None,
    ) -> bool:
        target = _required_text(event_id, "event_id")
        payload = self._load_metadata()
        now = _utc_now_iso()
        for index, row in enumerate(payload["webhook_events"]):
            if row["event_id"] != target:
                continue
            payload["webhook_events"][index] = self._normalize_webhook_event(
                {
                    **row,
                    "status": "succeeded" if succeeded else "pending",
                    "processed_at": now if succeeded else None,
                    "processing_started_at": None,
                    "last_error_code": None if succeeded else (error_code or "WEBHOOK_WORK_FAILED"),
                }
            )
            payload["updated_at"] = now
            self._save_metadata(payload)
            return True
        return False

    def list_webhook_events(self, connection_id: str | None = None) -> list[dict[str, Any]]:
        rows = self._load_metadata()["webhook_events"]
        if connection_id is not None:
            target = _required_text(connection_id, "connection_id")
            rows = [row for row in rows if row["connection_id"] == target]
        return [dict(row) for row in rows]

    def remove_webhook_event(self, event_id: str) -> bool:
        """Forget an event whose work failed so the provider may retry it."""
        target = _required_text(event_id, "event_id")
        payload = self._load_metadata()
        before = len(payload["webhook_events"])
        payload["webhook_events"] = [
            row for row in payload["webhook_events"] if row["event_id"] != target
        ]
        if len(payload["webhook_events"]) == before:
            return False
        payload["updated_at"] = _utc_now_iso()
        self._save_metadata(payload)
        return True

    def stage_observation(
        self,
        *,
        connection_id: str,
        accounts: list[dict[str, Any]],
        holdings: list[dict[str, Any]],
        observed_at: str,
        provider_payload_version: str,
        snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        target = _required_text(connection_id, "connection_id")
        self.get_connection(target)
        snapshot = self._normalize_snapshot(
            {
                "snapshot_id": snapshot_id or f"obs_{uuid.uuid4().hex[:16]}",
                "connection_id": target,
                "accounts": accounts,
                "holdings": holdings,
                "observed_at": observed_at,
                "provider_payload_version": provider_payload_version,
                "staged_at": _utc_now_iso(),
            }
        )
        state = self._load_observation_state(target)
        state["staged"] = snapshot
        state["updated_at"] = _utc_now_iso()
        self._save_observation_state(target, state)
        return dict(snapshot)

    def promote_staged_observation(
        self,
        connection_id: str,
        *,
        expected_snapshot_id: str | None = None,
    ) -> dict[str, Any]:
        target = _required_text(connection_id, "connection_id")
        state = self._load_observation_state(target)
        staged = state.get("staged")
        if not isinstance(staged, dict):
            raise FinancialConnectionStoreError("No staged observation is available")
        if expected_snapshot_id is not None and staged["snapshot_id"] != expected_snapshot_id:
            raise FinancialConnectionStoreError("Staged observation changed before promotion")
        state["previous"] = state.get("current")
        state["current"] = {**staged, "promoted_at": _utc_now_iso()}
        state["staged"] = None
        state["updated_at"] = state["current"]["promoted_at"]
        self._save_observation_state(target, state)
        return dict(state["current"])

    def discard_staged_observation(self, connection_id: str) -> bool:
        target = _required_text(connection_id, "connection_id")
        state = self._load_observation_state(target)
        if state.get("staged") is None:
            return False
        state["staged"] = None
        state["updated_at"] = _utc_now_iso()
        self._save_observation_state(target, state)
        return True

    def get_observation_state(self, connection_id: str) -> dict[str, Any]:
        target = _required_text(connection_id, "connection_id")
        self.get_connection(target)
        return self._load_observation_state(target)

    def current_observed_accounts(self, connection_id: str) -> list[dict[str, Any]]:
        current = self.get_observation_state(connection_id).get("current")
        if not isinstance(current, dict):
            return []
        return [dict(row) for row in current.get("accounts", []) if isinstance(row, dict)]

    def current_observed_holdings(self, connection_id: str) -> list[dict[str, Any]]:
        """Expose provider-owned current state without changing PortfolioStore yet."""
        current = self.get_observation_state(connection_id).get("current")
        if not isinstance(current, dict):
            return []
        return [dict(row) for row in current.get("holdings", []) if isinstance(row, dict)]

    def list_current_observed_holdings(
        self,
        *,
        buildwealth_account_id: str | None = None,
        include_disconnected: bool = True,
    ) -> list[dict[str, Any]]:
        """Return the workspace's promoted provider-owned holding state."""
        account_filter = _optional_text(buildwealth_account_id)
        rows: list[dict[str, Any]] = []
        for connection in self.list_connections():
            if not include_disconnected and connection["status"] == "disconnected":
                continue
            for holding in self.current_observed_holdings(connection["connection_id"]):
                if account_filter and holding.get("buildwealth_account_id") != account_filter:
                    continue
                rows.append(holding)
        return rows

    def delete_observations(self, connection_id: str) -> bool:
        path = self._observation_path(_required_text(connection_id, "connection_id"))
        existed = path.exists()
        path.unlink(missing_ok=True)
        return existed

    def _observation_path(self, connection_id: str) -> Path:
        safe_id = "".join(
            character if character.isalnum() or character in {"-", "_"} else "-"
            for character in connection_id
        ).strip("-_")
        if not safe_id or safe_id != connection_id:
            raise ValueError("connection_id contains unsupported characters")
        return self.observations_dir / f"{safe_id}.json"

    def _default_observation_state(self, connection_id: str) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "connection_id": connection_id,
            "staged": None,
            "current": None,
            "previous": None,
            "updated_at": _utc_now_iso(),
        }

    def _load_observation_state(self, connection_id: str) -> dict[str, Any]:
        path = self._observation_path(connection_id)
        if not path.exists():
            return self._default_observation_state(connection_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FinancialConnectionStoreError(f"Observation state is unreadable: {path}") from exc
        if not isinstance(raw, dict):
            raise FinancialConnectionStoreError("Observation state must be an object")
        try:
            schema_version = int(raw.get("schema_version") or 0)
        except (TypeError, ValueError) as exc:
            raise FinancialConnectionStoreError(
                "Observation state has an invalid schema version"
            ) from exc
        if schema_version > OBSERVATION_SCHEMA_VERSION:
            raise FinancialConnectionStoreError(
                "Observation state was written by a newer BuildWealth version"
            )
        if str(raw.get("workspace_id") or "") != self.workspace_id:
            raise FinancialConnectionStoreError("Observation state belongs to another workspace")
        if str(raw.get("connection_id") or "") != connection_id:
            raise FinancialConnectionStoreError("Observation state belongs to another connection")
        normalized = self._default_observation_state(connection_id)
        for slot in ("staged", "current", "previous"):
            value = raw.get(slot)
            normalized[slot] = self._normalize_snapshot(value) if isinstance(value, dict) else None
            if normalized[slot] is not None and normalized[slot]["connection_id"] != connection_id:
                raise FinancialConnectionStoreError(
                    f"{slot} observation belongs to another connection"
                )
        normalized["updated_at"] = str(raw.get("updated_at") or _utc_now_iso())
        if normalized != raw:
            self._save_observation_state(connection_id, normalized)
        return normalized

    def _save_observation_state(self, connection_id: str, payload: dict[str, Any]) -> None:
        payload["schema_version"] = OBSERVATION_SCHEMA_VERSION
        payload["workspace_id"] = self.workspace_id
        payload["connection_id"] = connection_id
        _atomic_write_json(self._observation_path(connection_id), payload)

    def _normalize_connection(self, row: dict[str, Any]) -> dict[str, Any]:
        workspace_id = _required_text(row.get("workspace_id") or self.workspace_id, "workspace_id")
        if workspace_id != self.workspace_id:
            raise ValueError("connection workspace_id does not match this store")
        status = str(row.get("status") or "pending_review").strip().lower()
        if status not in VALID_CONNECTION_STATUSES:
            raise ValueError(f"Unsupported financial connection status: {status}")
        environment = str(row.get("environment") or "sandbox").strip().lower()
        if environment not in {"sandbox", "development", "production"}:
            raise ValueError(f"Unsupported provider environment: {environment}")
        return {
            "connection_id": _required_text(row.get("connection_id"), "connection_id"),
            "provider": _required_text(row.get("provider"), "provider").lower(),
            "workspace_id": workspace_id,
            "connected_by_user_id": _required_text(
                row.get("connected_by_user_id"), "connected_by_user_id"
            ),
            "provider_item_id": _required_text(row.get("provider_item_id"), "provider_item_id"),
            "institution_id": _optional_text(row.get("institution_id")),
            "institution_name": _optional_text(row.get("institution_name")),
            "status": status,
            "environment": environment,
            "consented_products": _string_list(row.get("consented_products")),
            "consent_expiration_at": _optional_text(row.get("consent_expiration_at")),
            "last_successful_sync_at": _optional_text(row.get("last_successful_sync_at")),
            "last_attempted_sync_at": _optional_text(row.get("last_attempted_sync_at")),
            "last_webhook_at": _optional_text(row.get("last_webhook_at")),
            "last_error_code": _optional_text(row.get("last_error_code")),
            "last_error_message": _optional_text(row.get("last_error_message")),
            "created_at": _required_text(row.get("created_at") or _utc_now_iso(), "created_at"),
            "updated_at": _required_text(row.get("updated_at") or _utc_now_iso(), "updated_at"),
            "disconnected_at": _optional_text(row.get("disconnected_at")),
            "disconnect_retention": _optional_text(row.get("disconnect_retention")),
            "remote_removal_started_at": _optional_text(row.get("remote_removal_started_at")),
            "remote_removed_at": _optional_text(row.get("remote_removed_at")),
            "remote_removal_request_id": _optional_text(row.get("remote_removal_request_id")),
        }

    @staticmethod
    def _normalize_mapping(row: dict[str, Any]) -> dict[str, Any]:
        match_status = str(row.get("match_status") or "suggested").strip().lower()
        if match_status not in VALID_MATCH_STATUSES:
            raise ValueError(f"Unsupported account match status: {match_status}")
        buildwealth_account_id = _optional_text(row.get("buildwealth_account_id"))
        if match_status in {"confirmed", "created"} and not buildwealth_account_id:
            raise ValueError("Confirmed and created mappings require buildwealth_account_id")
        return {
            "connection_id": _required_text(row.get("connection_id"), "connection_id"),
            "provider_account_id": _required_text(
                row.get("provider_account_id"), "provider_account_id"
            ),
            "buildwealth_account_id": buildwealth_account_id,
            "match_status": match_status,
            "provider_name": _optional_text(row.get("provider_name")),
            "provider_official_name": _optional_text(row.get("provider_official_name")),
            "provider_type": _optional_text(row.get("provider_type")),
            "provider_subtype": _optional_text(row.get("provider_subtype")),
            "mask": _optional_text(row.get("mask")),
            "currency": (_optional_text(row.get("currency")) or "USD").upper(),
            "last_observed_at": _optional_text(row.get("last_observed_at")),
        }

    @staticmethod
    def _normalize_sync_run(row: dict[str, Any]) -> dict[str, Any]:
        outcome = str(row.get("outcome") or "running").strip().lower()
        if outcome not in VALID_SYNC_OUTCOMES:
            raise ValueError(f"Unsupported sync outcome: {outcome}")
        raw_counts = row.get("counts") if isinstance(row.get("counts"), dict) else {}
        counts: dict[str, int] = {}
        for key, value in raw_counts.items():
            counts[str(key)] = max(0, int(value))
        return {
            "sync_run_id": _required_text(row.get("sync_run_id"), "sync_run_id"),
            "connection_id": _required_text(row.get("connection_id"), "connection_id"),
            "trigger": _required_text(row.get("trigger") or "manual", "trigger"),
            "outcome": outcome,
            "started_at": _required_text(row.get("started_at") or _utc_now_iso(), "started_at"),
            "completed_at": _optional_text(row.get("completed_at")),
            "provider_request_ids": _string_list(row.get("provider_request_ids")),
            "counts": counts,
            "warnings": _string_list(row.get("warnings")),
            "error_code": _optional_text(row.get("error_code")),
        }

    @staticmethod
    def _normalize_connection_report(row: dict[str, Any]) -> dict[str, Any]:
        counts: dict[str, int] = {}
        raw_counts = row.get("counts") if isinstance(row.get("counts"), dict) else {}
        for key, value in raw_counts.items():
            counts[str(key)] = max(0, int(value))
        # Activation currently emits named top-level counts. Fold them into a
        # stable counts object while keeping the public report compact.
        for key in (
            "accounts_created",
            "accounts_confirmed",
            "accounts_ignored",
            "holdings_activated",
            "unmapped_securities",
        ):
            if row.get(key) is not None:
                counts[key] = max(0, int(row[key]))
        normalized = {
            "report_id": _required_text(row.get("report_id"), "report_id"),
            "connection_id": _required_text(row.get("connection_id"), "connection_id"),
            "action": _required_text(row.get("action"), "action"),
            "created_at": _required_text(row.get("created_at") or _utc_now_iso(), "created_at"),
            "counts": counts,
            "warnings": _string_list(row.get("warnings")),
        }
        for key in (
            "accounts_created",
            "accounts_confirmed",
            "accounts_ignored",
            "holdings_activated",
            "unmapped_securities",
        ):
            if key in counts:
                normalized[key] = counts[key]
        return normalized

    @staticmethod
    def _normalize_webhook_event(row: dict[str, Any]) -> dict[str, Any]:
        status = str(row.get("status") or "pending").strip().lower()
        if status not in {"pending", "processing", "succeeded"}:
            status = "pending"
        return {
            "event_id": _required_text(row.get("event_id"), "event_id"),
            "connection_id": _required_text(row.get("connection_id"), "connection_id"),
            "event_type": _required_text(row.get("event_type"), "event_type"),
            "event_code": _required_text(row.get("event_code"), "event_code"),
            "received_at": _required_text(row.get("received_at"), "received_at"),
            "status": status,
            "attempts": max(0, int(row.get("attempts") or 0)),
            "processing_started_at": _optional_text(row.get("processing_started_at")),
            "processed_at": _optional_text(row.get("processed_at")),
            "last_error_code": _optional_text(row.get("last_error_code")),
        }

    @classmethod
    def _normalize_snapshot(cls, row: dict[str, Any]) -> dict[str, Any]:
        connection_id = _required_text(row.get("connection_id"), "connection_id")
        observed_at = _required_text(row.get("observed_at"), "observed_at")
        payload_version = _required_text(
            row.get("provider_payload_version"), "provider_payload_version"
        )
        accounts = [
            cls._normalize_observed_account(
                {
                    "connection_id": connection_id,
                    "observed_at": observed_at,
                    **account,
                }
            )
            for account in row.get("accounts", [])
            if isinstance(account, dict)
        ]
        holdings = [
            cls._normalize_observed_holding(
                {
                    "connection_id": connection_id,
                    "observed_at": observed_at,
                    "provider_payload_version": payload_version,
                    **holding,
                }
            )
            for holding in row.get("holdings", [])
            if isinstance(holding, dict)
        ]
        normalized = {
            "snapshot_id": _required_text(row.get("snapshot_id"), "snapshot_id"),
            "connection_id": connection_id,
            "observed_at": observed_at,
            "provider_payload_version": payload_version,
            "accounts": accounts,
            "holdings": holdings,
            "staged_at": _required_text(row.get("staged_at") or _utc_now_iso(), "staged_at"),
        }
        if row.get("promoted_at"):
            normalized["promoted_at"] = str(row["promoted_at"])
        return normalized

    @staticmethod
    def _normalize_observed_account(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "connection_id": _required_text(row.get("connection_id"), "connection_id"),
            "provider_account_id": _required_text(
                row.get("provider_account_id"), "provider_account_id"
            ),
            "buildwealth_account_id": _optional_text(row.get("buildwealth_account_id")),
            "name": _optional_text(row.get("name")),
            "official_name": _optional_text(row.get("official_name")),
            "type": _optional_text(row.get("type")),
            "subtype": _optional_text(row.get("subtype")),
            "mask": _optional_text(row.get("mask")),
            "currency": (_optional_text(row.get("currency")) or "USD").upper(),
            "current_balance": _optional_number(row.get("current_balance"), "current_balance"),
            "available_balance": _optional_number(
                row.get("available_balance"), "available_balance"
            ),
            "cash_balance": _optional_number(row.get("cash_balance"), "cash_balance"),
            "observed_at": _required_text(row.get("observed_at"), "observed_at"),
        }

    @staticmethod
    def _normalize_observed_holding(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "connection_id": _required_text(row.get("connection_id"), "connection_id"),
            "provider_account_id": _required_text(
                row.get("provider_account_id"), "provider_account_id"
            ),
            "buildwealth_account_id": _optional_text(row.get("buildwealth_account_id")),
            "provider_security_id": _required_text(
                row.get("provider_security_id"), "provider_security_id"
            ),
            "symbol_or_identifier": _required_text(
                row.get("symbol_or_identifier"), "symbol_or_identifier"
            ),
            "name": _optional_text(row.get("name")),
            "quantity": _optional_number(row.get("quantity"), "quantity"),
            "institution_price": _optional_number(
                row.get("institution_price"), "institution_price"
            ),
            "institution_value": _optional_number(
                row.get("institution_value"), "institution_value"
            ),
            "cost_basis": _optional_number(row.get("cost_basis"), "cost_basis"),
            "currency": (_optional_text(row.get("currency")) or "USD").upper(),
            "observed_at": _required_text(row.get("observed_at"), "observed_at"),
            "provider_payload_version": _required_text(
                row.get("provider_payload_version"), "provider_payload_version"
            ),
        }

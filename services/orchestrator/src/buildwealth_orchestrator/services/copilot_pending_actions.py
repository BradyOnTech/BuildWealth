"""Durable, review-first financial actions proposed by BuildWealth Copilot.

This module deliberately does not execute an action.  It stores the exact JSON
payload proposed by a tool turn and enforces the state transition that makes a
user-reviewed action consumable once.  The caller remains responsible for:

* authenticating the user and authorizing the active workspace;
* showing the summary, evidence, and exact change before confirmation;
* applying the payload through a deterministic domain handler; and
* coordinating the domain write and ``mark_applied`` with an idempotency key.

Keeping handlers outside this store prevents the model-facing draft path from
gaining direct write authority over Canonical State.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import tempfile
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from buildwealth_orchestrator.services.store_locks import synchronized_store

PENDING_ACTION_SCHEMA_VERSION = 1
DEFAULT_ACTION_TTL = timedelta(minutes=30)
MAX_JSON_BYTES = 1_000_000
MAX_STORE_BYTES = 64_000_000
MAX_JSON_DEPTH = 64
MAX_SAFE_JSON_INTEGER = 9_007_199_254_740_991
MAX_ID_LENGTH = 256
MAX_SUMMARY_LENGTH = 1_000
MAX_REASON_LENGTH = 1_000
MAX_EVIDENCE_REFS = 100
MAX_EVIDENCE_REF_LENGTH = 1_024


class PendingActionStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    EXPIRED = "expired"
    STALE = "stale"


class FinancialActionImpact(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


TERMINAL_STATUSES = frozenset(
    {
        PendingActionStatus.APPLIED,
        PendingActionStatus.REJECTED,
        PendingActionStatus.EXPIRED,
        PendingActionStatus.STALE,
    }
)


class PendingActionError(RuntimeError):
    """Base error for pending financial action storage."""


class PendingActionValidationError(PendingActionError, ValueError):
    """Raised before unsafe or ambiguous data reaches the action store."""


class PendingActionStoreCorruptionError(PendingActionError):
    """Raised when persisted state cannot be trusted or safely interpreted."""


class PendingActionNotFoundError(PendingActionError, KeyError):
    def __init__(self, action_id: str):
        self.action_id = action_id
        super().__init__(f"Pending financial action not found: {action_id}")


class PendingActionStateError(PendingActionError):
    def __init__(self, action: "PendingFinancialAction", operation: str):
        self.action = action
        self.operation = operation
        super().__init__(
            f"Cannot {operation} pending financial action {action.action_id}; "
            f"its status is {action.status.value}."
        )


class PendingActionExpiredError(PendingActionStateError):
    pass


class PendingActionStaleError(PendingActionStateError):
    pass


def _utc_datetime(value: datetime, *, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise PendingActionValidationError(f"{field_name} must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise PendingActionValidationError(f"{field_name} must include a timezone.")
    return value.astimezone(timezone.utc)


def _datetime_text(value: datetime) -> str:
    return _utc_datetime(value, field_name="datetime").isoformat()


def _parse_datetime(value: Any, *, field_name: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise PendingActionStoreCorruptionError(f"Missing {field_name}.")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PendingActionStoreCorruptionError(f"Invalid {field_name}: {text}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PendingActionStoreCorruptionError(f"{field_name} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _validate_json_value(value: Any, *, path: str = "$", depth: int = 0) -> Any:
    """Return a JSON-native deep copy, rejecting lossy or surprising values."""

    if depth > MAX_JSON_DEPTH:
        raise PendingActionValidationError(
            f"JSON value exceeds the maximum nesting depth at {path}."
        )
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_JSON_INTEGER:
            raise PendingActionValidationError(
                f"Integer at {path} exceeds the cross-runtime safe JSON range."
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PendingActionValidationError(f"Non-finite number at {path} is not valid JSON.")
        return value
    if isinstance(value, list):
        return [
            _validate_json_value(item, path=f"{path}[{index}]", depth=depth + 1)
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PendingActionValidationError(f"JSON object key at {path} must be a string.")
            normalized[key] = _validate_json_value(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
            )
        return normalized
    raise PendingActionValidationError(f"Unsupported JSON value at {path}: {type(value).__name__}.")


def _canonical_json(value: Any, *, field_name: str) -> tuple[str, Any]:
    normalized = _validate_json_value(value)
    try:
        encoded = json.dumps(
            normalized,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise PendingActionValidationError(f"{field_name} is not safe JSON.") from exc
    if len(encoded.encode("utf-8")) > MAX_JSON_BYTES:
        raise PendingActionValidationError(f"{field_name} exceeds the {MAX_JSON_BYTES}-byte limit.")
    return encoded, normalized


def fingerprint_source_state(source_state: Any) -> str:
    """Create the deterministic fingerprint used for optimistic validation."""

    canonical, _ = _canonical_json(source_state, field_name="source_state")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def validate_source_fingerprint(
    expected_fingerprint: str,
    current_fingerprint: str,
) -> bool:
    """Constant-time comparison for an action's expected and current source state."""

    expected = _validated_text(
        expected_fingerprint,
        field_name="expected_fingerprint",
        max_length=256,
    )
    current = _validated_text(
        current_fingerprint,
        field_name="current_fingerprint",
        max_length=256,
    )
    return hmac.compare_digest(expected, current)


def _validated_text(
    value: Any,
    *,
    field_name: str,
    max_length: int,
    allow_newlines: bool = False,
) -> str:
    if not isinstance(value, str):
        raise PendingActionValidationError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        raise PendingActionValidationError(f"{field_name} must not be empty.")
    if len(text) > max_length:
        raise PendingActionValidationError(
            f"{field_name} exceeds the {max_length}-character limit."
        )
    for character in text:
        if ord(character) < 32 and not (allow_newlines and character in {"\n", "\r", "\t"}):
            raise PendingActionValidationError(f"{field_name} contains control characters.")
    return text


def _optional_reason(value: Any, *, field_name: str = "status_reason") -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PendingActionValidationError(f"{field_name} must be a string.")
    text = value.strip()
    if not text:
        return None
    return _validated_text(
        text,
        field_name=field_name,
        max_length=MAX_REASON_LENGTH,
        allow_newlines=True,
    )


def _normalize_evidence_refs(values: Sequence[str] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise PendingActionValidationError("evidence_refs must be an array of strings.")
    if len(values) > MAX_EVIDENCE_REFS:
        raise PendingActionValidationError(
            f"evidence_refs exceeds the {MAX_EVIDENCE_REFS}-item limit."
        )
    refs: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        ref = _validated_text(
            value,
            field_name=f"evidence_refs[{index}]",
            max_length=MAX_EVIDENCE_REF_LENGTH,
        )
        if ref in seen:
            continue
        seen.add(ref)
        refs.append(ref)
    return tuple(refs)


@dataclass(frozen=True)
class PendingFinancialAction:
    """Immutable view of one exact, user-reviewable financial action."""

    workspace_id: str
    action_id: str
    conversation_id: str
    turn_id: str
    tool_name: str
    tool_call_id: str
    summary: str
    impact_level: FinancialActionImpact
    source_state_fingerprint: str
    evidence_refs: tuple[str, ...]
    created_at: datetime
    expires_at: datetime
    status: PendingActionStatus
    payload_sha256: str
    _payload_json: str = field(repr=False)
    applied_at: datetime | None = None
    rejected_at: datetime | None = None
    expired_at: datetime | None = None
    stale_at: datetime | None = None
    status_reason: str | None = None

    @property
    def payload(self) -> dict[str, Any]:
        """Return a fresh copy so callers cannot mutate the stored proposal."""

        loaded = json.loads(self._payload_json)
        if not isinstance(loaded, dict):  # Defensive; construction requires an object.
            raise PendingActionStoreCorruptionError("Stored action payload is not an object.")
        return loaded

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "action_id": self.action_id,
            "conversation_id": self.conversation_id,
            "turn_id": self.turn_id,
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
            "summary": self.summary,
            "impact_level": self.impact_level.value,
            "source_state_fingerprint": self.source_state_fingerprint,
            "evidence_refs": list(self.evidence_refs),
            "created_at": _datetime_text(self.created_at),
            "expires_at": _datetime_text(self.expires_at),
            "status": self.status.value,
            "payload": self.payload,
            "payload_sha256": self.payload_sha256,
            "applied_at": _datetime_text(self.applied_at) if self.applied_at else None,
            "rejected_at": _datetime_text(self.rejected_at) if self.rejected_at else None,
            "expired_at": _datetime_text(self.expired_at) if self.expired_at else None,
            "stale_at": _datetime_text(self.stale_at) if self.stale_at else None,
            "status_reason": self.status_reason,
        }


def _payload_digest(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _record_from_dict(raw: Any, *, expected_workspace_id: str) -> PendingFinancialAction:
    if not isinstance(raw, Mapping):
        raise PendingActionStoreCorruptionError("Stored action must be a JSON object.")
    try:
        workspace_id = _validated_text(
            raw.get("workspace_id"),
            field_name="workspace_id",
            max_length=MAX_ID_LENGTH,
        )
        action_id = _validated_text(
            raw.get("action_id"),
            field_name="action_id",
            max_length=MAX_ID_LENGTH,
        )
        conversation_id = _validated_text(
            raw.get("conversation_id"),
            field_name="conversation_id",
            max_length=MAX_ID_LENGTH,
        )
        turn_id = _validated_text(
            raw.get("turn_id"),
            field_name="turn_id",
            max_length=MAX_ID_LENGTH,
        )
        tool_name = _validated_text(
            raw.get("tool_name"),
            field_name="tool_name",
            max_length=MAX_ID_LENGTH,
        )
        tool_call_id = _validated_text(
            raw.get("tool_call_id"),
            field_name="tool_call_id",
            max_length=MAX_ID_LENGTH,
        )
        summary = _validated_text(
            raw.get("summary"),
            field_name="summary",
            max_length=MAX_SUMMARY_LENGTH,
            allow_newlines=True,
        )
        impact = FinancialActionImpact(str(raw.get("impact_level") or ""))
        status = PendingActionStatus(str(raw.get("status") or ""))
        source_fingerprint = _validated_text(
            raw.get("source_state_fingerprint"),
            field_name="source_state_fingerprint",
            max_length=256,
        )
        evidence_refs = _normalize_evidence_refs(raw.get("evidence_refs"))
        payload_json, _ = _canonical_json(raw.get("payload"), field_name="payload")
        payload_sha256 = _validated_text(
            raw.get("payload_sha256"),
            field_name="payload_sha256",
            max_length=64,
        )
        status_reason = _optional_reason(raw.get("status_reason"))
    except (PendingActionValidationError, ValueError) as exc:
        raise PendingActionStoreCorruptionError(f"Invalid stored action: {exc}") from exc

    if workspace_id != expected_workspace_id:
        raise PendingActionStoreCorruptionError("Stored action belongs to a different workspace.")
    if not hmac.compare_digest(payload_sha256, _payload_digest(payload_json)):
        raise PendingActionStoreCorruptionError(
            f"Payload checksum mismatch for pending financial action {action_id}."
        )

    created_at = _parse_datetime(raw.get("created_at"), field_name="created_at")
    expires_at = _parse_datetime(raw.get("expires_at"), field_name="expires_at")
    if expires_at <= created_at:
        raise PendingActionStoreCorruptionError(
            f"Action {action_id} expires_at must be later than created_at."
        )

    def optional_timestamp(field_name: str) -> datetime | None:
        value = raw.get(field_name)
        return _parse_datetime(value, field_name=field_name) if value else None

    applied_at = optional_timestamp("applied_at")
    rejected_at = optional_timestamp("rejected_at")
    expired_at = optional_timestamp("expired_at")
    stale_at = optional_timestamp("stale_at")
    expected_timestamp = {
        PendingActionStatus.APPLIED: applied_at,
        PendingActionStatus.REJECTED: rejected_at,
        PendingActionStatus.EXPIRED: expired_at,
        PendingActionStatus.STALE: stale_at,
    }.get(status)
    terminal_timestamps = [applied_at, rejected_at, expired_at, stale_at]
    if status is PendingActionStatus.PENDING and any(terminal_timestamps):
        raise PendingActionStoreCorruptionError(
            f"Pending action {action_id} cannot have a terminal timestamp."
        )
    if status in TERMINAL_STATUSES and expected_timestamp is None:
        raise PendingActionStoreCorruptionError(
            f"{status.value} action {action_id} is missing its transition timestamp."
        )
    if status in TERMINAL_STATUSES and sum(value is not None for value in terminal_timestamps) != 1:
        raise PendingActionStoreCorruptionError(
            f"Action {action_id} has conflicting terminal timestamps."
        )

    return PendingFinancialAction(
        workspace_id=workspace_id,
        action_id=action_id,
        conversation_id=conversation_id,
        turn_id=turn_id,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        summary=summary,
        impact_level=impact,
        source_state_fingerprint=source_fingerprint,
        evidence_refs=evidence_refs,
        created_at=created_at,
        expires_at=expires_at,
        status=status,
        payload_sha256=payload_sha256,
        _payload_json=payload_json,
        applied_at=applied_at,
        rejected_at=rejected_at,
        expired_at=expired_at,
        stale_at=stale_at,
        status_reason=status_reason,
    )


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _default_id_factory() -> str:
    return f"pfa_{uuid.uuid4().hex}"


@synchronized_store("path")
class PendingFinancialActionStore:
    """Atomic JSON store scoped to one BuildWealth workspace."""

    def __init__(
        self,
        path: Path,
        *,
        workspace_id: str,
        clock: Callable[[], datetime] = _default_clock,
        id_factory: Callable[[], str] = _default_id_factory,
        default_ttl: timedelta = DEFAULT_ACTION_TTL,
    ):
        self.path = Path(path)
        self.workspace_id = _validated_text(
            workspace_id,
            field_name="workspace_id",
            max_length=MAX_ID_LENGTH,
        )
        if not callable(clock):
            raise PendingActionValidationError("clock must be callable.")
        if not callable(id_factory):
            raise PendingActionValidationError("id_factory must be callable.")
        if not isinstance(default_ttl, timedelta) or default_ttl <= timedelta(0):
            raise PendingActionValidationError("default_ttl must be a positive timedelta.")
        self._clock = clock
        self._id_factory = id_factory
        self.default_ttl = default_ttl

    def create(
        self,
        *,
        payload: Mapping[str, Any],
        conversation_id: str,
        turn_id: str,
        tool_name: str,
        tool_call_id: str,
        summary: str,
        impact_level: FinancialActionImpact | str,
        source_state_fingerprint: str,
        evidence_refs: Sequence[str] | None = None,
        expires_at: datetime | None = None,
        expires_in: timedelta | None = None,
    ) -> PendingFinancialAction:
        """Persist a proposal without granting it execution authority."""

        if not isinstance(payload, Mapping):
            raise PendingActionValidationError("payload must be a JSON object.")
        payload_json, _ = _canonical_json(payload, field_name="payload")
        try:
            impact = (
                impact_level
                if isinstance(impact_level, FinancialActionImpact)
                else FinancialActionImpact(str(impact_level))
            )
        except ValueError as exc:
            allowed = ", ".join(level.value for level in FinancialActionImpact)
            raise PendingActionValidationError(f"impact_level must be one of: {allowed}.") from exc

        created_at = self._now()
        if expires_at is not None and expires_in is not None:
            raise PendingActionValidationError("Provide expires_at or expires_in, not both.")
        if expires_in is not None:
            if not isinstance(expires_in, timedelta) or expires_in <= timedelta(0):
                raise PendingActionValidationError("expires_in must be a positive timedelta.")
            resolved_expires_at = created_at + expires_in
        elif expires_at is not None:
            resolved_expires_at = _utc_datetime(expires_at, field_name="expires_at")
        else:
            resolved_expires_at = created_at + self.default_ttl
        if resolved_expires_at <= created_at:
            raise PendingActionValidationError("expires_at must be later than created_at.")

        action_id = _validated_text(
            self._id_factory(),
            field_name="action_id",
            max_length=MAX_ID_LENGTH,
        )
        action = PendingFinancialAction(
            workspace_id=self.workspace_id,
            action_id=action_id,
            conversation_id=_validated_text(
                conversation_id,
                field_name="conversation_id",
                max_length=MAX_ID_LENGTH,
            ),
            turn_id=_validated_text(
                turn_id,
                field_name="turn_id",
                max_length=MAX_ID_LENGTH,
            ),
            tool_name=_validated_text(
                tool_name,
                field_name="tool_name",
                max_length=MAX_ID_LENGTH,
            ),
            tool_call_id=_validated_text(
                tool_call_id,
                field_name="tool_call_id",
                max_length=MAX_ID_LENGTH,
            ),
            summary=_validated_text(
                summary,
                field_name="summary",
                max_length=MAX_SUMMARY_LENGTH,
                allow_newlines=True,
            ),
            impact_level=impact,
            source_state_fingerprint=_validated_text(
                source_state_fingerprint,
                field_name="source_state_fingerprint",
                max_length=256,
            ),
            evidence_refs=_normalize_evidence_refs(evidence_refs),
            created_at=created_at,
            expires_at=resolved_expires_at,
            status=PendingActionStatus.PENDING,
            payload_sha256=_payload_digest(payload_json),
            _payload_json=payload_json,
        )
        actions = self._load()
        if any(existing.action_id == action.action_id for existing in actions):
            raise PendingActionValidationError(f"Generated duplicate action_id: {action.action_id}")
        actions.append(action)
        self._write(actions)
        return action

    def get(self, action_id: str) -> PendingFinancialAction:
        normalized_id = _validated_text(
            action_id,
            field_name="action_id",
            max_length=MAX_ID_LENGTH,
        )
        actions = self._load()
        actions, changed = self._expire_pending(actions, now=self._now())
        if changed:
            self._write(actions)
        return self._find(actions, normalized_id)

    def list(
        self,
        *,
        statuses: Iterable[PendingActionStatus | str] | None = None,
        conversation_id: str | None = None,
    ) -> list[PendingFinancialAction]:
        status_filter: set[PendingActionStatus] | None = None
        if statuses is not None:
            try:
                status_filter = {
                    item
                    if isinstance(item, PendingActionStatus)
                    else PendingActionStatus(str(item))
                    for item in statuses
                }
            except ValueError as exc:
                raise PendingActionValidationError("statuses contains an unknown status.") from exc
        conversation_filter = (
            _validated_text(
                conversation_id,
                field_name="conversation_id",
                max_length=MAX_ID_LENGTH,
            )
            if conversation_id is not None
            else None
        )
        actions = self._load()
        actions, changed = self._expire_pending(actions, now=self._now())
        if changed:
            self._write(actions)
        filtered = [
            action
            for action in actions
            if (status_filter is None or action.status in status_filter)
            and (conversation_filter is None or action.conversation_id == conversation_filter)
        ]
        return sorted(
            filtered,
            key=lambda action: (action.created_at, action.action_id),
            reverse=True,
        )

    def reject(
        self,
        action_id: str,
        *,
        reason: str = "Rejected by the user.",
    ) -> PendingFinancialAction:
        normalized_id = _validated_text(
            action_id,
            field_name="action_id",
            max_length=MAX_ID_LENGTH,
        )
        normalized_reason = _optional_reason(reason, field_name="reason")
        now = self._now()
        actions = self._load()
        actions, expired = self._expire_pending(actions, now=now)
        current = self._find(actions, normalized_id)
        if current.status is not PendingActionStatus.PENDING:
            if expired:
                self._write(actions)
            self._raise_unavailable(current, operation="reject")
        rejected = replace(
            current,
            status=PendingActionStatus.REJECTED,
            rejected_at=now,
            status_reason=normalized_reason,
        )
        self._replace_and_write(actions, rejected)
        return rejected

    def mark_applied(
        self,
        action_id: str,
        *,
        current_source_fingerprint: str,
    ) -> PendingFinancialAction:
        """Atomically consume a pending action after a successful domain write.

        This method never invokes the domain handler.  The caller should pass
        ``action_id`` to an idempotent handler, use the same source fingerprint
        for its compare-and-set, and call this transition only for that
        successful write.
        """

        normalized_id = _validated_text(
            action_id,
            field_name="action_id",
            max_length=MAX_ID_LENGTH,
        )
        current_fingerprint = _validated_text(
            current_source_fingerprint,
            field_name="current_source_fingerprint",
            max_length=256,
        )
        now = self._now()
        actions = self._load()
        actions, expired = self._expire_pending(actions, now=now)
        current = self._find(actions, normalized_id)
        if current.status is not PendingActionStatus.PENDING:
            if expired:
                self._write(actions)
            self._raise_unavailable(current, operation="mark as applied")

        if not validate_source_fingerprint(
            current.source_state_fingerprint,
            current_fingerprint,
        ):
            stale = replace(
                current,
                status=PendingActionStatus.STALE,
                stale_at=now,
                status_reason=(
                    "The underlying financial state changed after this action "
                    "was drafted. Review a fresh proposal before applying it."
                ),
            )
            self._replace_and_write(actions, stale)
            raise PendingActionStaleError(stale, operation="mark as applied")

        applied = replace(
            current,
            status=PendingActionStatus.APPLIED,
            applied_at=now,
            status_reason="Applied after explicit user confirmation.",
        )
        self._replace_and_write(actions, applied)
        return applied

    def _now(self) -> datetime:
        return _utc_datetime(self._clock(), field_name="clock result")

    def _load(self) -> list[PendingFinancialAction]:
        if not self.path.exists():
            return []
        try:
            if self.path.stat().st_size > MAX_STORE_BYTES:
                raise PendingActionStoreCorruptionError(
                    f"Pending action store exceeds {MAX_STORE_BYTES} bytes."
                )
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except PendingActionStoreCorruptionError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PendingActionStoreCorruptionError(
                f"Unable to read pending action store: {self.path}"
            ) from exc
        if not isinstance(raw, Mapping):
            raise PendingActionStoreCorruptionError(
                "Pending action store root must be a JSON object."
            )
        if raw.get("schema_version") != PENDING_ACTION_SCHEMA_VERSION:
            raise PendingActionStoreCorruptionError(
                "Unsupported pending action store schema version."
            )
        stored_workspace_id = raw.get("workspace_id")
        if stored_workspace_id != self.workspace_id:
            raise PendingActionStoreCorruptionError(
                "Pending action store belongs to a different workspace."
            )
        raw_actions = raw.get("actions")
        if not isinstance(raw_actions, list):
            raise PendingActionStoreCorruptionError(
                "Pending action store actions must be an array."
            )
        actions = [
            _record_from_dict(item, expected_workspace_id=self.workspace_id) for item in raw_actions
        ]
        ids = [action.action_id for action in actions]
        if len(ids) != len(set(ids)):
            raise PendingActionStoreCorruptionError(
                "Pending action store contains duplicate action ids."
            )
        return actions

    def _write(self, actions: Sequence[PendingFinancialAction]) -> None:
        document = {
            "schema_version": PENDING_ACTION_SCHEMA_VERSION,
            "workspace_id": self.workspace_id,
            "actions": [action.to_dict() for action in actions],
        }
        encoded = json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        if len(encoded.encode("utf-8")) > MAX_STORE_BYTES:
            raise PendingActionValidationError(
                f"Pending action store exceeds the {MAX_STORE_BYTES}-byte limit."
            )
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        try:
            parent.chmod(0o700)
        except OSError:
            pass

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(encoded)
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
            temporary_path = None
            self._fsync_directory(parent)
        except OSError as exc:
            raise PendingActionError(
                f"Unable to atomically write pending action store: {self.path}"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    @staticmethod
    def _find(
        actions: Sequence[PendingFinancialAction],
        action_id: str,
    ) -> PendingFinancialAction:
        for action in actions:
            if action.action_id == action_id:
                return action
        raise PendingActionNotFoundError(action_id)

    @staticmethod
    def _expire_pending(
        actions: Sequence[PendingFinancialAction],
        *,
        now: datetime,
    ) -> tuple[list[PendingFinancialAction], bool]:
        changed = False
        updated: list[PendingFinancialAction] = []
        for action in actions:
            if action.status is PendingActionStatus.PENDING and action.expires_at <= now:
                action = replace(
                    action,
                    status=PendingActionStatus.EXPIRED,
                    expired_at=now,
                    status_reason=(
                        "This proposal expired before confirmation. "
                        "Review a fresh proposal against current financial data."
                    ),
                )
                changed = True
            updated.append(action)
        return updated, changed

    def _replace_and_write(
        self,
        actions: Sequence[PendingFinancialAction],
        updated: PendingFinancialAction,
    ) -> None:
        replaced = [
            updated if action.action_id == updated.action_id else action for action in actions
        ]
        self._write(replaced)

    @staticmethod
    def _raise_unavailable(
        action: PendingFinancialAction,
        *,
        operation: str,
    ) -> None:
        if action.status is PendingActionStatus.EXPIRED:
            raise PendingActionExpiredError(action, operation=operation)
        if action.status is PendingActionStatus.STALE:
            raise PendingActionStaleError(action, operation=operation)
        raise PendingActionStateError(action, operation=operation)

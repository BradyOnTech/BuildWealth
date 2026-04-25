"""Short-lived restore-preview tokens for guarded restore apply."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class GitRestorePreviewTokenError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def restore_file_signature(file_payload: dict[str, Any]) -> str:
    payload = {
        "path": file_payload.get("path"),
        "status": file_payload.get("status"),
        "current_excerpt": file_payload.get("current_excerpt"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class GitRestorePreviewTokenStore:
    def __init__(self, token_path: Path):
        self.token_path = token_path
        self.token_path.parent.mkdir(parents=True, exist_ok=True)

    def create(self, *, preview: dict[str, Any], ttl_seconds: int = 900) -> dict[str, Any]:
        now = utc_now()
        token = {
            "token": f"git-preview-{secrets.token_urlsafe(24)}",
            "created_at": _iso(now),
            "expires_at": _iso(now + timedelta(seconds=max(60, min(int(ttl_seconds), 3600)))),
            "ref": preview.get("ref"),
            "path": preview.get("path"),
            "file_signatures": {
                str(file.get("path")): restore_file_signature(file)
                for file in preview.get("files", [])
                if isinstance(file, dict) and file.get("path")
            },
        }
        with self.token_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(token, sort_keys=True))
            handle.write("\n")
        return token

    def validate(
        self,
        *,
        token: str,
        ref: str,
        paths: list[str],
        current_preview: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        stored = self._find(token)
        if stored is None:
            raise GitRestorePreviewTokenError("Restore preview token is unknown or expired.")
        expires_at = _parse_iso(stored.get("expires_at"))
        if expires_at is None or expires_at <= (now or utc_now()):
            raise GitRestorePreviewTokenError("Restore preview token has expired. Generate a fresh preview.")
        if str(stored.get("ref") or "") != str(ref or ""):
            raise GitRestorePreviewTokenError("Restore preview token does not match the selected checkpoint.")

        stored_signatures = stored.get("file_signatures") if isinstance(stored.get("file_signatures"), dict) else {}
        current_signatures = {
            str(file.get("path")): restore_file_signature(file)
            for file in current_preview.get("files", [])
            if isinstance(file, dict) and file.get("path")
        }
        for path in paths:
            if path not in stored_signatures:
                raise GitRestorePreviewTokenError(f"Restore preview token does not include `{path}`.")
            if current_signatures.get(path) != stored_signatures[path]:
                raise GitRestorePreviewTokenError(
                    f"`{path}` changed since preview. Generate a fresh preview before applying restore."
                )
        return stored

    def get(self, token: str) -> dict[str, Any] | None:
        return self._find(token)

    def _find(self, token: str) -> dict[str, Any] | None:
        cleaned = str(token or "").strip()
        if not cleaned or not self.token_path.exists():
            return None
        for line in reversed(self.token_path.read_text(encoding="utf-8").splitlines()):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("token") == cleaned:
                return payload
        return None

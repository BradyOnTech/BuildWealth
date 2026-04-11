from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from buildwealth_orchestrator.schemas import EngineStatusItem, EngineStatusResponse


@dataclass(frozen=True)
class EngineProbeConfig:
    name: str
    base_url: str
    enabled: bool
    health_paths: tuple[str, ...]
    version_paths: tuple[str, ...]


class EngineStatusTracker:
    """Track sidecar probe status and degraded execution counts."""

    def __init__(
        self,
        *,
        configs: list[EngineProbeConfig],
        timeout_seconds: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.transport = transport
        self._configs = {config.name: config for config in configs}
        self._lock = asyncio.Lock()
        self._as_of: datetime = datetime.now(timezone.utc)
        self._state: dict[str, dict[str, Any]] = {}

        for config in configs:
            self._state[config.name] = {
                "name": config.name,
                "enabled": bool(config.enabled),
                "reachable": False,
                "contract_version": None,
                "degraded_count": 0,
                "last_error": None,
                "last_checked_at": None,
            }

    async def probe_all(self) -> None:
        results = await asyncio.gather(
            *(self._probe_one(config) for config in self._configs.values()),
            return_exceptions=False,
        )

        async with self._lock:
            self._as_of = datetime.now(timezone.utc)
            for name, payload in results:
                if name in self._state:
                    self._state[name].update(payload)

    async def _probe_one(self, config: EngineProbeConfig) -> tuple[str, dict[str, Any]]:
        checked_at = datetime.now(timezone.utc)

        if not config.enabled:
            return config.name, {
                "enabled": False,
                "reachable": False,
                "contract_version": None,
                "last_error": None,
                "last_checked_at": checked_at,
            }

        reachable = False
        last_error: str | None = None

        for path in config.health_paths:
            try:
                _ = await self._get_payload(config.base_url, path)
                reachable = True
                last_error = None
                break
            except Exception as exc:
                last_error = f"{path}: {exc}"

        contract_version: int | None = None
        if reachable:
            for path in config.version_paths:
                try:
                    payload = await self._get_payload(config.base_url, path)
                    contract_version = self._extract_contract_version(payload)
                    if contract_version is not None:
                        break
                except Exception:
                    continue

        return config.name, {
            "enabled": True,
            "reachable": reachable,
            "contract_version": contract_version,
            "last_error": last_error,
            "last_checked_at": checked_at,
        }

    async def _get_payload(self, base_url: str, path: str) -> dict[str, Any]:
        normalized_path = self._normalize_path(path)
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=self.timeout_seconds,
            transport=self.transport,
        ) as client:
            response = await client.get(normalized_path)

        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}

        if isinstance(payload, dict):
            return payload

        return {"value": payload}

    async def increment_degraded(self, engine_name: str, reason: str | None = None) -> None:
        async with self._lock:
            entry = self._state.get(engine_name)
            if entry is None:
                return
            entry["degraded_count"] = int(entry.get("degraded_count", 0)) + 1
            if reason:
                entry["last_error"] = reason
            self._as_of = datetime.now(timezone.utc)

    async def snapshot(self) -> EngineStatusResponse:
        async with self._lock:
            engines = [
                EngineStatusItem(**payload)
                for payload in sorted(self._state.values(), key=lambda item: str(item.get("name")))
            ]
            as_of = self._as_of

        return EngineStatusResponse(as_of=as_of, engines=engines)

    @staticmethod
    def _normalize_path(path: str) -> str:
        cleaned = str(path or "").strip()
        if not cleaned:
            raise ValueError("health/version path must not be empty")
        return cleaned if cleaned.startswith("/") else f"/{cleaned}"

    @staticmethod
    def _extract_contract_version(payload: dict[str, Any]) -> int | None:
        for key in ("contract_version", "contractVersion", "apiVersion", "version"):
            if key not in payload:
                continue
            value = payload.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return value if value >= 0 else None
            if isinstance(value, float):
                ivalue = int(value)
                return ivalue if ivalue >= 0 else None
            if isinstance(value, str):
                match = re.search(r"(\d+)", value)
                if match:
                    try:
                        return int(match.group(1))
                    except ValueError:
                        continue
        return None

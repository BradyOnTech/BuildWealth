from __future__ import annotations

import re
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError


ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)


class SidecarAdapterError(RuntimeError):
    """Base adapter error for sidecar communication failures."""


class SidecarRequestValidationError(SidecarAdapterError):
    """Raised when outbound payload fails contract validation."""


class SidecarResponseValidationError(SidecarAdapterError):
    """Raised when inbound payload fails contract validation."""


class SidecarTransportError(SidecarAdapterError):
    """Raised for sidecar transport and HTTP-level failures."""


class SidecarAdapter:
    """HTTP adapter with request/response validation and retry behavior."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 3.0,
        max_retries: int = 1,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(0.1, float(timeout_seconds))
        self.max_retries = max(0, int(max_retries))
        self.transport = transport

    async def post_json(
        self,
        *,
        path: str,
        request_payload: dict[str, Any],
        request_model: type[BaseModel],
        response_model: type[ResponseModelT],
    ) -> ResponseModelT:
        """Validate request, perform POST, and validate response contract."""

        try:
            request_obj = request_model.model_validate(request_payload)
        except ValidationError as exc:
            raise SidecarRequestValidationError(f"Invalid outbound contract payload: {exc}") from exc

        body = request_obj.model_dump(mode="json")
        attempts = self.max_retries + 1
        path_value = self._normalize_path(path)
        if not self._is_versioned_contract_path(path_value):
            raise SidecarTransportError(
                "Sidecar path must use a versioned contract prefix (for example /v1/...)"
            )

        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout_seconds,
                    transport=self.transport,
                ) as client:
                    response = await client.post(path_value, json=body)

                response.raise_for_status()

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise SidecarTransportError("Sidecar returned non-JSON response body") from exc

                try:
                    return response_model.model_validate(payload)
                except ValidationError as exc:
                    raise SidecarResponseValidationError(
                        f"Invalid inbound contract payload: {exc}"
                    ) from exc
            except SidecarResponseValidationError:
                raise
            except httpx.HTTPStatusError as exc:
                if attempt < attempts - 1 and self._is_retryable_status(exc.response.status_code):
                    continue
                status = exc.response.status_code
                raise SidecarTransportError(f"Sidecar request failed with HTTP {status}") from exc
            except httpx.RequestError as exc:
                if attempt < attempts - 1:
                    continue
                raise SidecarTransportError(f"Sidecar request failed: {exc}") from exc

        raise SidecarTransportError("Sidecar request failed after retries")

    @staticmethod
    def _normalize_path(path: str) -> str:
        cleaned = str(path).strip()
        if not cleaned:
            raise SidecarTransportError("Sidecar path must not be empty")
        return cleaned if cleaned.startswith("/") else f"/{cleaned}"

    @staticmethod
    def _is_versioned_contract_path(path: str) -> bool:
        return bool(re.match(r"^/v\d+(?:/|$)", path))

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code == 429 or status_code >= 500

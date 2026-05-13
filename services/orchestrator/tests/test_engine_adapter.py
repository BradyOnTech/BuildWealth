import asyncio
import json
from typing import Literal

import httpx
import pytest
from pydantic import BaseModel

from buildwealth_orchestrator.services.engine_adapter import (
    CalculationAdapter,
    CalculationAdapterRequestValidationError,
    CalculationAdapterResponseValidationError,
    CalculationAdapterTransportError,
)


class _RequestContract(BaseModel):
    contract_version: Literal[1]
    request_id: str


class _ResponseContract(BaseModel):
    contract_version: Literal[1]
    request_id: str
    engine_status: Literal["ok", "degraded"]


def test_calculation_adapter_retries_on_retryable_http_error() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(status_code=503, json={"detail": "temporary"})

        payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            status_code=200,
            json={
                "contract_version": 1,
                "request_id": payload["request_id"],
                "engine_status": "ok",
            },
        )

    adapter = CalculationAdapter(
        base_url="http://localhost:8411",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(
        adapter.post_json(
            path="/v1/example",
            request_payload={"contract_version": 1, "request_id": "req-1"},
            request_model=_RequestContract,
            response_model=_ResponseContract,
        )
    )

    assert result.request_id == "req-1"
    assert result.engine_status == "ok"
    assert attempts["count"] == 2


def test_calculation_adapter_rejects_invalid_outbound_payload() -> None:
    adapter = CalculationAdapter(base_url="http://localhost:8411", transport=httpx.MockTransport(lambda _: None))

    with pytest.raises(CalculationAdapterRequestValidationError):
        asyncio.run(
            adapter.post_json(
                path="/v1/example",
                request_payload={"contract_version": 2},
                request_model=_RequestContract,
                response_model=_ResponseContract,
            )
        )


def test_calculation_adapter_rejects_invalid_inbound_payload() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, json={"contract_version": 1, "engine_status": "ok"})

    adapter = CalculationAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(CalculationAdapterResponseValidationError):
        asyncio.run(
            adapter.post_json(
                path="/v1/example",
                request_payload={"contract_version": 1, "request_id": "req-2"},
                request_model=_RequestContract,
                response_model=_ResponseContract,
            )
        )


def test_calculation_adapter_rejects_non_contract_path() -> None:
    adapter = CalculationAdapter(
        base_url="http://localhost:8411",
        max_retries=0,
        transport=httpx.MockTransport(lambda _: httpx.Response(status_code=200, json={})),
    )

    with pytest.raises(CalculationAdapterTransportError):
        asyncio.run(
            adapter.post_json(
                path="/api/portfolio/benchmark",
                request_payload={"contract_version": 1, "request_id": "req-3"},
                request_model=_RequestContract,
                response_model=_ResponseContract,
            )
        )

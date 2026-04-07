from __future__ import annotations

from typing import Any

import httpx


class GhostfolioClient:
    def __init__(self, api_base: str, security_token: str, timeout_seconds: float = 20.0):
        self.api_base = api_base.rstrip("/")
        self.security_token = security_token
        self.timeout_seconds = timeout_seconds

    async def _get_bearer(self, client: httpx.AsyncClient) -> str:
        if not self.security_token:
            raise RuntimeError("GHOSTFOLIO_SECURITY_TOKEN is not set")

        response = await client.post(
            f"{self.api_base}/v1/auth/anonymous",
            json={"accessToken": self.security_token},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()

        token = payload.get("authToken") or payload.get("accessToken") or payload.get("token")
        if not token:
            raise RuntimeError("Ghostfolio anonymous auth response did not contain a bearer token")

        return token

    async def _authorized_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            token = await self._get_bearer(client)
            response = await client.get(
                f"{self.api_base}{path}",
                params=params or {},
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

    async def _authorized_post(
        self,
        path: str,
        payload: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            token = await self._get_bearer(client)
            response = await client.post(
                f"{self.api_base}{path}",
                params=params or {},
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return response.json()

    async def get_holdings(self, date_range: str = "max") -> dict[str, Any]:
        return await self._authorized_get("/v1/portfolio/holdings", params={"range": date_range})

    async def get_performance(self, date_range: str = "max") -> dict[str, Any]:
        try:
            return await self._authorized_get("/v2/portfolio/performance", params={"range": date_range})
        except httpx.HTTPStatusError:
            return await self._authorized_get("/v1/portfolio/performance", params={"range": date_range})

    async def get_accounts(self) -> dict[str, Any] | list[dict[str, Any]]:
        return await self._authorized_get("/v1/account")

    async def get_accounts_list(self) -> list[dict[str, Any]]:
        payload = await self.get_accounts()
        if isinstance(payload, list):
            return payload
        return payload.get("accounts", [])

    async def import_activities(
        self,
        activities: list[dict[str, Any]],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        return await self._authorized_post(
            "/v1/import",
            payload={"activities": activities},
            params={"dryRun": str(dry_run).lower()},
        )

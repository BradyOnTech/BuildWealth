from __future__ import annotations

from typing import Any

import httpx


class IgnidashClient:
    def __init__(self, convex_actions_url: str, convex_api_secret: str, timeout_seconds: float = 20.0):
        self.convex_actions_url = convex_actions_url.rstrip("/")
        self.convex_api_secret = convex_api_secret
        self.timeout_seconds = timeout_seconds

    async def create_default_plan(self, user_id: str, user_name: str) -> dict[str, Any]:
        if not self.convex_api_secret:
            raise RuntimeError("IGNIDASH_CONVEX_API_SECRET is not set")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.convex_actions_url}/createDefaultPlan",
                json={"userId": user_id, "userName": user_name},
                headers={"Authorization": f"Bearer {self.convex_api_secret}"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return {"status": "ok", "body": response.text}

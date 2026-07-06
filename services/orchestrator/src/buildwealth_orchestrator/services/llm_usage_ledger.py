"""Local LLM usage ledger — what the household's key actually spends.

BYOK users deserve to see what Copilot costs before any bill arrives, and no
hosted pricing can be designed without these numbers. The ledger keeps
monthly aggregates per (provider, model, task) in a small JSON file — counts
are exact (reported by the provider); dollar figures are estimates computed
at read time from a public price table, labeled as such.

Nothing here leaves the machine.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA_VERSION = 1
_KEEP_MONTHS = 12

# USD per 1M tokens (input, output). Public list prices, matched by longest
# model-name prefix; unknown and local models price at zero. Estimates only —
# providers change prices and bill nuances (caching, batch) aren't modeled.
_PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5.5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5": (1.25, 10.0),
    "claude-opus": (15.0, 75.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku": (1.0, 5.0),
    "gemini-3.1-flash-lite": (0.10, 0.40),
    "gemini": (0.30, 2.50),
    "grok": (3.0, 15.0),
}


def _month_key(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def normalize_usage(usage: Any) -> tuple[int, int]:
    """(prompt_tokens, completion_tokens) from OpenAI- or Anthropic-shaped usage."""
    if not isinstance(usage, dict):
        return (0, 0)

    def _count(*keys: str) -> int:
        for key in keys:
            try:
                value = int(usage.get(key) or 0)
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
        return 0

    return (
        _count("prompt_tokens", "input_tokens"),
        _count("completion_tokens", "output_tokens"),
    )


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    normalized_model = str(model or "").strip().lower()
    best: tuple[float, float] | None = None
    best_len = 0
    for prefix, prices in _PRICES_PER_MILLION.items():
        if normalized_model.startswith(prefix) and len(prefix) > best_len:
            best = prices
            best_len = len(prefix)
    if best is None:
        return 0.0
    input_price, output_price = best
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


class LLMUsageLedger:
    def __init__(self, ledger_path: Path):
        self.ledger_path = ledger_path

    def record(
        self,
        *,
        provider: str,
        model: str,
        task: str,
        usage: Any,
        now: datetime | None = None,
    ) -> None:
        prompt_tokens, completion_tokens = normalize_usage(usage)
        payload = self._load()
        months = payload.setdefault("months", {})
        month = months.setdefault(_month_key(now), {})
        key = f"{provider}|{model}|{task}"
        row = month.setdefault(
            key,
            {"provider": provider, "model": model, "task": task, "requests": 0, "prompt_tokens": 0, "completion_tokens": 0},
        )
        row["requests"] += 1
        row["prompt_tokens"] += prompt_tokens
        row["completion_tokens"] += completion_tokens
        self._prune(months)
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write(payload)

    def summary(self, *, now: datetime | None = None) -> dict[str, Any]:
        payload = self._load()
        months = payload.get("months", {})
        current_key = _month_key(now)
        return {
            "month": current_key,
            "current": self._month_summary(months.get(current_key, {})),
            "months_recorded": sorted(months.keys(), reverse=True),
            "note": "Token counts come from the provider; dollar figures are list-price estimates.",
        }

    @staticmethod
    def _month_summary(month: dict[str, Any]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        total_cost = 0.0
        total_requests = 0
        total_prompt = 0
        total_completion = 0
        for row in month.values():
            if not isinstance(row, dict):
                continue
            prompt_tokens = int(row.get("prompt_tokens") or 0)
            completion_tokens = int(row.get("completion_tokens") or 0)
            cost = estimate_cost_usd(str(row.get("model") or ""), prompt_tokens, completion_tokens)
            rows.append(
                {
                    "provider": row.get("provider"),
                    "model": row.get("model"),
                    "task": row.get("task"),
                    "requests": int(row.get("requests") or 0),
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "estimated_cost_usd": round(cost, 4),
                }
            )
            total_cost += cost
            total_requests += int(row.get("requests") or 0)
            total_prompt += prompt_tokens
            total_completion += completion_tokens
        rows.sort(key=lambda row: -row["estimated_cost_usd"])
        return {
            "rows": rows,
            "requests": total_requests,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "estimated_cost_usd": round(total_cost, 4),
        }

    @staticmethod
    def _prune(months: dict[str, Any]) -> None:
        for key in sorted(months.keys(), reverse=True)[_KEEP_MONTHS:]:
            months.pop(key, None)

    def _load(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.ledger_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {"schema_version": _SCHEMA_VERSION, "months": {}}
        if not isinstance(payload, dict) or not isinstance(payload.get("months"), dict):
            return {"schema_version": _SCHEMA_VERSION, "months": {}}
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

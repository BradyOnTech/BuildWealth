"""Canonical plain-language labels for materiality and review urgency."""

from __future__ import annotations

from typing import Any

MATERIALITY_LEVELS = ("low", "medium", "high", "critical")
ACTION_READINESS_BY_MATERIALITY = {
    "low": "Can review later",
    "medium": "Worth reviewing",
    "high": "Review before relying on this",
    "critical": "Needs attention before acting",
}


def normalize_materiality(value: Any, *, default: str = "low") -> str:
    level = str(value or "").strip().lower()
    return level if level in MATERIALITY_LEVELS else default


def action_readiness_for_materiality(value: Any, *, default: str = "low") -> str:
    return ACTION_READINESS_BY_MATERIALITY[normalize_materiality(value, default=default)]

"""Context Intelligence registry, indexing, and materiality helpers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping

from buildwealth_orchestrator.services.financial_profile import profile_metadata_quality_for_field


CONTEXT_REGISTRY_SCHEMA_VERSION = 1
MATERIALITY_POLICY_VERSION = "global_v1"
CONTEXT_ASSEMBLER_VERSION = "context_intelligence_assembler_v1"
CONTEXT_CONFLICT_REVIEW_SCHEMA_VERSION = 1
CONTEXT_CONFLICT_RECOMMENDATION_TYPE = "context_conflict_review"
CONTEXT_CONFLICT_RECOMMENDATION_SOURCE = "context_intelligence"
CONTEXT_CONFLICT_RESOLUTION_STATES = {
    "unresolved",
    "deferred",
    "resolved_by_source_update",
    "resolved_by_confirming_existing_source",
    "resolved_by_rejecting_candidate",
    "resolved_by_scoped_exception",
}
CONTEXT_CONFLICT_RELEVANCE_RESURFACE_REASONS = {
    "copilot_answer",
    "live_recommendation",
    "planning_projection",
    "investment_fit_review",
}

MATERIALITY_LEVELS = ("low", "medium", "high", "critical")
ACTION_READINESS_BY_MATERIALITY = {
    "low": "Can review later",
    "medium": "Worth reviewing",
    "high": "Review before relying on this",
    "critical": "Needs attention before acting",
}

AUTHORITY_SCORE = {
    "canonical": 1.0,
    "source_evidence": 0.9,
    "derived": 0.65,
    "conversation": 0.5,
}
MATERIALITY_SCORE = {
    "critical": 1.0,
    "high": 0.85,
    "medium": 0.6,
    "low": 0.35,
}
CONFIDENCE_SCORE = {
    "high": 1.0,
    "medium": 0.68,
    "low": 0.35,
    "unknown": 0.45,
}
FRESHNESS_SCORE = {
    "current": 1.0,
    "fresh": 1.0,
    "recent": 0.85,
    "unknown": 0.5,
    "stale": 0.2,
}

PROFILE_HIGH_MATERIALITY_PREFIXES = (
    "tax_profile.",
    "investment_policy.",
)
PLAN_HIGH_MATERIALITY_ENTITY_TYPES = {
    "plan_decision",
    "plan_setting_field",
    "plan_timeline_event",
}
PLAN_HIGH_MATERIALITY_FIELD_TOKENS = {
    "annual_contribution",
    "tax_rate",
    "marginal_tax",
    "state_tax",
    "filing_status",
    "withdrawal_strategy",
    "drawdown_order",
    "inflation_rate",
    "expected_return",
    "retirement",
    "roth_conversion",
}
QUESTION_SYMBOL_IGNORELIST = {
    "A",
    "AI",
    "AM",
    "AND",
    "ARE",
    "BUY",
    "CAN",
    "DO",
    "ETF",
    "FOR",
    "IRA",
    "I",
    "ME",
    "MY",
    "OR",
    "ROTH",
    "SELL",
    "SHOULD",
    "THE",
    "TO",
    "USD",
    "WHAT",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads_object(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _normalized_filter_values(values: Iterable[Any] | Any | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raw_values: Iterable[Any] = values.split(",")
    elif isinstance(values, (list, tuple, set)):
        raw_values = values
    else:
        raw_values = (values,)
    resolved = []
    for value in raw_values:
        token = str(value or "").strip()
        if token:
            resolved.append(token)
    return tuple(dict.fromkeys(resolved))


def _normalized_lower_values(values: Iterable[Any] | Any | None) -> tuple[str, ...]:
    return tuple(value.lower() for value in _normalized_filter_values(values))


def _normalized_symbol_values(values: Iterable[Any] | Any | None) -> tuple[str, ...]:
    return tuple(value.upper() for value in _normalized_filter_values(values))


def _extract_question_symbols(question: str) -> tuple[str, ...]:
    symbols: list[str] = []
    for token in re.findall(r"\b[A-Z][A-Z0-9.]{0,5}\b", str(question or "")):
        symbol = token.strip().upper()
        if symbol in QUESTION_SYMBOL_IGNORELIST or len(symbol) > 6:
            continue
        symbols.append(symbol)
    return tuple(dict.fromkeys(symbols))


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _compact_text(value: Any, *, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _clean_token(raw: Any, *, fallback: str = "item") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", str(raw or "").strip().lower()).strip("_")
    return cleaned or fallback


def _hash_payload(value: Any, *, length: int = 12) -> str:
    return hashlib.sha256(_json_dumps(value).encode("utf-8")).hexdigest()[:length]


def _stable_context_id(*parts: Any) -> str:
    tokens = [_clean_token(part) for part in parts if str(part or "").strip()]
    return f"ctx_{'_'.join(tokens) if tokens else 'item'}"


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _format_value(field_path: str, value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        field = field_path.lower()
        if field.endswith("_rate") or "_rate" in field:
            return f"{float(value) * 100:.2f}%" if abs(float(value)) <= 1 else f"{float(value):.2f}%"
        if field.endswith("_pct") or "_pct" in field:
            return f"{float(value):.2f}%"
        if field.endswith("_usd") or "_usd" in field:
            return f"${float(value):,.2f}"
        return f"{float(value):,.2f}"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _source_mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    except OSError:
        return None


def _normalize_materiality(value: Any, *, default: str = "low") -> str:
    level = str(value or "").strip().lower()
    if level in MATERIALITY_LEVELS:
        return level
    return default


@dataclass(frozen=True)
class MaterialityDecision:
    materiality: str
    action_readiness: str
    policy_version: str
    rule_ids: tuple[str, ...]
    rationale: str

    def as_quality_fields(self) -> dict[str, Any]:
        return {
            "materiality_policy_version": self.policy_version,
            "materiality_rule_ids": list(self.rule_ids),
        }


class MaterialityPolicy:
    """Global versioned defaults for explainable Context Materiality classification."""

    policy_version = MATERIALITY_POLICY_VERSION

    def classify(
        self,
        *,
        domain: str,
        entity_type: str,
        field_path: str = "",
        payload: Mapping[str, Any] | None = None,
        conflicts_material_context: bool = False,
        affects_live_advice: bool = False,
    ) -> MaterialityDecision:
        payload = payload if isinstance(payload, Mapping) else {}
        domain = str(domain or "").strip().lower()
        entity_type = str(entity_type or "").strip().lower()
        field_path = str(field_path or "").strip().lower()

        level = "low"
        rule_ids: list[str] = ["global_default_low"]

        if domain == "profile" and field_path.startswith(PROFILE_HIGH_MATERIALITY_PREFIXES):
            level = "high"
            rule_ids.append("profile_material_field_high")
        elif domain == "plan" and entity_type in PLAN_HIGH_MATERIALITY_ENTITY_TYPES:
            level = "high"
            rule_ids.append("plan_material_record_high")
        elif domain == "plan" and any(token in field_path for token in PLAN_HIGH_MATERIALITY_FIELD_TOKENS):
            level = "high"
            rule_ids.append("plan_material_field_high")
        elif domain == "recommendation":
            level = self._recommendation_materiality(payload)
            rule_ids.append(f"recommendation_{level}")
        elif domain == "research":
            level = "medium"
            rule_ids.append("research_narrative_medium")
        elif domain == "portfolio":
            level = "high"
            rule_ids.append("portfolio_financial_state_high")

        if conflicts_material_context:
            level = _max_materiality(level, "high")
            rule_ids.append("material_conflict_floor_high")
        if affects_live_advice:
            level = _max_materiality(level, "critical" if conflicts_material_context else "high")
            rule_ids.append("live_advice_escalation")

        return MaterialityDecision(
            materiality=level,
            action_readiness=ACTION_READINESS_BY_MATERIALITY[level],
            policy_version=self.policy_version,
            rule_ids=tuple(dict.fromkeys(rule_ids)),
            rationale=_materiality_rationale(level=level, rule_ids=rule_ids),
        )

    def _recommendation_materiality(self, payload: Mapping[str, Any]) -> str:
        priority = str(payload.get("priority") or "").strip().lower()
        action_payload = payload.get("action_payload")
        action_payload = action_payload if isinstance(action_payload, Mapping) else {}
        quality = action_payload.get("quality")
        quality = quality if isinstance(quality, Mapping) else {}
        impact = quality.get("impact")
        impact = impact if isinstance(impact, Mapping) else {}

        impact_level = _normalize_materiality(impact.get("level"), default="")
        if impact_level:
            return impact_level
        if priority in {"critical", "urgent"}:
            return "critical"
        if priority == "high":
            return "high"
        if quality.get("blocking_context"):
            return "high"
        return "medium"


def _max_materiality(left: str, right: str) -> str:
    order = {level: index for index, level in enumerate(MATERIALITY_LEVELS)}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def _materiality_rationale(*, level: str, rule_ids: list[str]) -> str:
    if level == "critical":
        return "Needs attention before acting because this context affects live advice or a material conflict."
    if level == "high":
        return "Review before relying on this because it can change planning, policy, tax, risk, or recommendation fit."
    if level == "medium":
        return "Worth reviewing because it can change ranking, research priority, or follow-up questions."
    return "Can review later because it mainly improves personalization or background explanation."


@dataclass(frozen=True)
class ContextItem:
    id: str
    domain: str
    entity_type: str
    entity_id: str
    source_ref: str
    authority: str
    text: str
    structured_payload: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    materiality: str = "low"
    materiality_rationale: str = ""
    action_readiness: str = "Can review later"
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    source_updated_at: str | None = None


class ContextRegistry:
    """SQLite-backed, rebuildable operational index for Context Intelligence."""

    def __init__(self, database_path: Path):
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS context_items (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    authority TEXT NOT NULL,
                    text TEXT NOT NULL,
                    structured_payload TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    quality TEXT NOT NULL,
                    materiality TEXT NOT NULL,
                    materiality_rationale TEXT NOT NULL,
                    action_readiness TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    source_updated_at TEXT,
                    indexed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rebuild_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    item_count INTEGER NOT NULL,
                    counts_by_domain TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS registry_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_context_items_domain ON context_items(domain)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_context_items_source_ref ON context_items(source_ref)"
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO registry_metadata(key, value)
                VALUES ('schema_version', ?)
                """,
                (str(CONTEXT_REGISTRY_SCHEMA_VERSION),),
            )

    def replace_all(self, items: Iterable[ContextItem]) -> dict[str, Any]:
        self._initialize()
        indexed_at = utc_now_iso()
        resolved_items = list(items)
        counts = _counts_by_domain(resolved_items)

        with self._connect() as connection:
            connection.execute("DELETE FROM context_items")
            connection.executemany(
                """
                INSERT INTO context_items (
                    id, domain, entity_type, entity_id, source_ref, authority, text,
                    structured_payload, provenance, quality, materiality,
                    materiality_rationale, action_readiness, created_at, updated_at,
                    source_updated_at, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_item_row(item, indexed_at=indexed_at) for item in resolved_items],
            )
            connection.execute(
                """
                INSERT INTO rebuild_runs(created_at, item_count, counts_by_domain)
                VALUES (?, ?, ?)
                """,
                (indexed_at, len(resolved_items), _json_dumps(counts)),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO registry_metadata(key, value)
                VALUES ('latest_rebuild_at', ?)
                """,
                (indexed_at,),
            )

        return {
            "database_path": str(self.database_path),
            "rebuilt_at": indexed_at,
            "item_count": len(resolved_items),
            "counts_by_domain": counts,
        }

    def status(self) -> dict[str, Any]:
        if not self.database_path.exists():
            return {
                "schema_version": CONTEXT_REGISTRY_SCHEMA_VERSION,
                "database_path": str(self.database_path),
                "database_exists": False,
                "item_count": 0,
                "counts_by_domain": {},
                "latest_rebuild_at": None,
            }

        self._initialize()
        with self._connect() as connection:
            item_count = int(connection.execute("SELECT COUNT(*) FROM context_items").fetchone()[0])
            rows = connection.execute(
                "SELECT domain, COUNT(*) AS count FROM context_items GROUP BY domain ORDER BY domain"
            ).fetchall()
            latest = connection.execute(
                "SELECT value FROM registry_metadata WHERE key = 'latest_rebuild_at'"
            ).fetchone()

        return {
            "schema_version": CONTEXT_REGISTRY_SCHEMA_VERSION,
            "database_path": str(self.database_path),
            "database_exists": True,
            "item_count": item_count,
            "counts_by_domain": {str(row["domain"]): int(row["count"]) for row in rows},
            "latest_rebuild_at": str(latest["value"]) if latest is not None else None,
        }

    def list_items(
        self,
        *,
        domain: str | None = None,
        limit: int = 100,
    ) -> list[ContextItem]:
        if not self.database_path.exists():
            return []
        self._initialize()
        bounded_limit = max(1, min(int(limit), 5000))
        params: list[Any] = []
        where = ""
        if domain:
            where = "WHERE domain = ?"
            params.append(str(domain).strip().lower())
        params.append(bounded_limit)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM context_items
                {where}
                ORDER BY domain, entity_type, entity_id
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_item_from_row(row) for row in rows]

    def search(
        self,
        *,
        query: str = "",
        domains: Iterable[Any] | Any | None = None,
        plan_id: str | None = None,
        symbols: Iterable[Any] | Any | None = None,
        entity_types: Iterable[Any] | Any | None = None,
        recommendation_status: str | None = None,
        field_path: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit), 100))
        resolved_domains = _normalized_lower_values(domains)
        resolved_symbols = _normalized_symbol_values(symbols)
        resolved_entity_types = _normalized_lower_values(entity_types)
        resolved_plan_id = str(plan_id or "").strip()
        resolved_recommendation_status = str(recommendation_status or "").strip().lower()
        resolved_field_path = str(field_path or "").strip()
        query_text = str(query or "").strip()
        query_terms = _search_terms(query_text)
        exact_filter_count = sum(
            1
            for value in (
                resolved_domains,
                resolved_plan_id,
                resolved_symbols,
                resolved_entity_types,
                resolved_recommendation_status,
                resolved_field_path,
            )
            if bool(value)
        )

        rows: list[dict[str, Any]] = []
        for item in self.list_items(limit=5000):
            if not _matches_search_filters(
                item,
                domains=resolved_domains,
                plan_id=resolved_plan_id,
                symbols=resolved_symbols,
                entity_types=resolved_entity_types,
                recommendation_status=resolved_recommendation_status,
                field_path=resolved_field_path,
            ):
                continue

            score = _score_context_item(
                item,
                query=query_text,
                query_terms=query_terms,
                exact_filter_count=exact_filter_count,
            )
            if query_terms and not score["matched_terms"] and exact_filter_count == 0:
                continue

            rows.append(_search_result_payload(item, score=score))

        rows.sort(
            key=lambda row: (
                float(row["score"]),
                MATERIALITY_SCORE.get(str(row["materiality"]), 0.0),
                str(row.get("updated_at") or ""),
            ),
            reverse=True,
        )
        return {
            "query": query_text,
            "filters": {
                "domains": list(resolved_domains),
                "plan_id": resolved_plan_id or None,
                "symbols": list(resolved_symbols),
                "entity_types": list(resolved_entity_types),
                "recommendation_status": resolved_recommendation_status or None,
                "field_path": resolved_field_path or None,
            },
            "total_candidates": len(rows),
            "count": min(len(rows), bounded_limit),
            "items": rows[:bounded_limit],
        }


class ContextIndexer:
    def __init__(self, *, materiality_policy: MaterialityPolicy | None = None):
        self.materiality_policy = materiality_policy or MaterialityPolicy()

    def build_profile_items(
        self,
        *,
        profile_payload: Mapping[str, Any],
        profile_path: Path,
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        updated_at = str(profile_payload.get("updated_at") or "") or _source_mtime_iso(profile_path)
        for section_name in ("tax_profile", "investment_policy"):
            section_payload = profile_payload.get(section_name)
            if not isinstance(section_payload, Mapping):
                continue
            for field_name, value in sorted(section_payload.items()):
                if not _present(value):
                    continue
                field_path = f"{section_name}.{field_name}"
                materiality = self.materiality_policy.classify(
                    domain="profile",
                    entity_type=f"{section_name}_field",
                    field_path=field_path,
                    payload={"value": value},
                )
                metadata_quality = profile_metadata_quality_for_field(profile_payload, field_path)
                items.append(
                    _build_context_item(
                        id=_stable_context_id("profile", field_path),
                        domain="profile",
                        entity_type=f"{section_name}_field",
                        entity_id=field_path,
                        source_ref=f"profile/financial_profile.json#{field_path}",
                        authority="canonical",
                        text=(
                            f"{section_name.replace('_', ' ').title()}: "
                            f"{field_name.replace('_', ' ')} is {_format_value(field_path, value)}."
                        ),
                        structured_payload={"field": field_path, "value": value},
                        provenance={
                            "source": metadata_quality.get("source") or "financial_profile",
                            "captured_by": "user",
                            "confirmed_by_user": metadata_quality.get("status") == "user_confirmed",
                        },
                        quality={
                            "confidence": metadata_quality.get("confidence") or "unknown",
                            "freshness": metadata_quality.get("freshness") or "unknown",
                            "status": metadata_quality.get("status") or "unknown",
                            "last_confirmed_at": metadata_quality.get("last_confirmed_at"),
                            "stale_after_days": metadata_quality.get("stale_after_days"),
                        },
                        materiality=materiality,
                        created_at=updated_at or utc_now_iso(),
                        updated_at=updated_at or utc_now_iso(),
                        source_updated_at=updated_at,
                    )
                )
        return items

    def build_plan_items(self, *, plan_workspace: Any) -> list[ContextItem]:
        items: list[ContextItem] = []
        for plan_summary in plan_workspace.list_plans(limit=500):
            if not isinstance(plan_summary, Mapping):
                continue
            plan_id = str(plan_summary.get("id") or "").strip()
            if not plan_id:
                continue
            try:
                detail = plan_workspace.get_plan(plan_id)
            except Exception:
                continue
            items.extend(self._build_single_plan_items(plan_summary=plan_summary, plan_detail=detail))
        return items

    def _build_single_plan_items(
        self,
        *,
        plan_summary: Mapping[str, Any],
        plan_detail: Mapping[str, Any],
    ) -> list[ContextItem]:
        plan_id = str(plan_summary.get("id") or plan_detail.get("id") or "").strip()
        if not plan_id:
            return []

        title = str(plan_summary.get("title") or plan_detail.get("title") or "Untitled Plan").strip()
        updated_at = str(plan_summary.get("updated_at") or plan_detail.get("updated_at") or "") or None
        is_active = bool(plan_summary.get("is_active") or plan_detail.get("is_active"))
        items: list[ContextItem] = [
            _build_context_item(
                id=_stable_context_id("plan", plan_id, "metadata"),
                domain="plan",
                entity_type="plan_metadata",
                entity_id=plan_id,
                source_ref=f"plans/{plan_id}/metadata",
                authority="canonical",
                text=f"Plan: {title}. Active: {'yes' if is_active else 'no'}.",
                structured_payload={
                    "plan_id": plan_id,
                    "title": title,
                    "description": plan_summary.get("description") or plan_detail.get("description") or "",
                    "is_active": is_active,
                },
                provenance={"source": "plan_workspace"},
                quality={"confidence": "high", "freshness": "current"},
                materiality=self.materiality_policy.classify(
                    domain="plan",
                    entity_type="plan_metadata",
                    field_path="metadata",
                ),
                created_at=str(plan_summary.get("created_at") or updated_at or utc_now_iso()),
                updated_at=updated_at or utc_now_iso(),
                source_updated_at=updated_at,
            )
        ]

        files = plan_detail.get("files")
        files = files if isinstance(files, Mapping) else {}
        context_markdown = str(files.get("context_markdown") or "").strip()
        if context_markdown:
            materiality = self.materiality_policy.classify(
                domain="plan",
                entity_type="plan_context_section",
                field_path="context_markdown",
            )
            items.append(
                _build_context_item(
                    id=_stable_context_id("plan", plan_id, "context"),
                    domain="plan",
                    entity_type="plan_context_section",
                    entity_id=f"{plan_id}:context",
                    source_ref=f"plans/{plan_id}/context.md",
                    authority="derived",
                    text=f"Plan context for {title}: {_compact_text(context_markdown)}",
                    structured_payload={"plan_id": plan_id},
                    provenance={"source": "plan_workspace.context_md"},
                    quality={"confidence": "medium", "freshness": "current"},
                    materiality=materiality,
                    created_at=updated_at or utc_now_iso(),
                    updated_at=updated_at or utc_now_iso(),
                    source_updated_at=updated_at,
                )
            )

        settings = plan_detail.get("settings")
        if isinstance(settings, Mapping):
            for field_name, value in sorted(settings.items()):
                if field_name == "schema_version" or not _present(value):
                    continue
                field_path = f"settings.{field_name}"
                materiality = self.materiality_policy.classify(
                    domain="plan",
                    entity_type="plan_setting_field",
                    field_path=field_path,
                    payload={"value": value},
                )
                items.append(
                    _build_context_item(
                        id=_stable_context_id("plan", plan_id, field_path),
                        domain="plan",
                        entity_type="plan_setting_field",
                        entity_id=f"{plan_id}:{field_path}",
                        source_ref=f"plans/{plan_id}/settings.json#{field_name}",
                        authority="canonical",
                        text=f"Plan setting for {title}: {field_name.replace('_', ' ')} is {_format_value(field_path, value)}.",
                        structured_payload={"plan_id": plan_id, "field": field_path, "value": value},
                        provenance={"source": "plan_workspace.settings"},
                        quality={"confidence": "high", "freshness": "current"},
                        materiality=materiality,
                        created_at=updated_at or utc_now_iso(),
                        updated_at=updated_at or utc_now_iso(),
                        source_updated_at=updated_at,
                    )
                )

        decisions = plan_detail.get("decisions")
        if isinstance(decisions, list):
            for decision in decisions:
                if not isinstance(decision, Mapping):
                    continue
                summary = str(decision.get("summary") or "").strip()
                if not summary:
                    continue
                decision_id = str(decision.get("id") or "").strip() or _hash_payload(decision)
                created_at = str(decision.get("created_at") or updated_at or utc_now_iso())
                materiality = self.materiality_policy.classify(
                    domain="plan",
                    entity_type="plan_decision",
                    field_path="decision",
                )
                items.append(
                    _build_context_item(
                        id=_stable_context_id("plan", plan_id, "decision", decision_id),
                        domain="plan",
                        entity_type="plan_decision",
                        entity_id=f"{plan_id}:{decision_id}",
                        source_ref=f"plans/{plan_id}/decisions.jsonl#{decision_id}",
                        authority="source_evidence",
                        text=f"Plan decision for {title}: {summary}",
                        structured_payload={"plan_id": plan_id, **dict(decision)},
                        provenance={"source": "plan_workspace.decisions"},
                        quality={"confidence": "high", "freshness": "current"},
                        materiality=materiality,
                        created_at=created_at,
                        updated_at=created_at,
                        source_updated_at=created_at,
                    )
                )

        artifacts = plan_detail.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, Mapping):
                    continue
                artifact_id = str(artifact.get("id") or "").strip()
                if not artifact_id:
                    continue
                title_text = str(artifact.get("title") or artifact_id).strip()
                file_name = str(artifact.get("file_name") or f"{artifact_id}.md").strip()
                lowered = f"{title_text} {file_name}".lower()
                is_research = "research" in lowered or "dossier" in lowered or "thesis" in lowered
                domain = "research" if is_research else "plan"
                entity_type = "research_dossier_artifact" if is_research else "plan_artifact"
                materiality = self.materiality_policy.classify(
                    domain=domain,
                    entity_type=entity_type,
                    field_path="artifact",
                )
                created_at = str(artifact.get("created_at") or updated_at or utc_now_iso())
                items.append(
                    _build_context_item(
                        id=_stable_context_id(domain, plan_id, "artifact", artifact_id),
                        domain=domain,
                        entity_type=entity_type,
                        entity_id=f"{plan_id}:{artifact_id}",
                        source_ref=f"plans/{plan_id}/artifacts/{file_name}",
                        authority="source_evidence",
                        text=f"{'Research' if is_research else 'Plan'} artifact for {title}: {title_text}.",
                        structured_payload={"plan_id": plan_id, **dict(artifact)},
                        provenance={"source": "plan_workspace.artifacts"},
                        quality={"confidence": "medium", "freshness": "current"},
                        materiality=materiality,
                        created_at=created_at,
                        updated_at=created_at,
                        source_updated_at=created_at,
                    )
                )

        return items

    def build_recommendation_items(self, *, recommendation_inbox: Any) -> list[ContextItem]:
        items: list[ContextItem] = []
        try:
            recommendations = recommendation_inbox.list(limit=None, include_archived=True)
        except Exception:
            return items

        for row in recommendations:
            if not isinstance(row, Mapping):
                continue
            recommendation_id = str(row.get("id") or "").strip()
            title = str(row.get("title") or "").strip()
            detail = str(row.get("detail") or "").strip()
            if not recommendation_id or not title:
                continue
            materiality = self.materiality_policy.classify(
                domain="recommendation",
                entity_type="recommendation",
                field_path=str(row.get("recommendation_type") or ""),
                payload=row,
            )
            created_at = str(row.get("created_at") or utc_now_iso())
            updated_at = str(row.get("updated_at") or created_at)
            items.append(
                _build_context_item(
                    id=_stable_context_id("recommendation", recommendation_id),
                    domain="recommendation",
                    entity_type="recommendation",
                    entity_id=recommendation_id,
                    source_ref=f"recommendations/inbox.json#recommendations.{recommendation_id}",
                    authority="canonical",
                    text=(
                        f"Recommendation: {title}. Status: {row.get('status') or 'unknown'}. "
                        f"Priority: {row.get('priority') or 'medium'}. {_compact_text(detail, limit=600)}"
                    ),
                    structured_payload=dict(row),
                    provenance={"source": "recommendation_inbox"},
                    quality=_recommendation_quality(row),
                    materiality=materiality,
                    created_at=created_at,
                    updated_at=updated_at,
                    source_updated_at=updated_at,
                )
            )
        return items

    def build_watchlist_items(self, *, portfolio_store: Any | None) -> list[ContextItem]:
        if portfolio_store is None:
            return []
        try:
            watchlist_items = portfolio_store.list_watchlist()
        except Exception:
            return []

        items: list[ContextItem] = []
        for row in watchlist_items:
            if not isinstance(row, Mapping):
                continue
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            thesis = str(row.get("thesis") or "").strip()
            note = str(row.get("note") or "").strip()
            tags = row.get("tags")
            tags = tags if isinstance(tags, list) else []
            if not thesis and not note and not tags:
                continue

            data_source = str(row.get("data_source") or "OPENBB").strip().upper() or "OPENBB"
            updated_at = str(row.get("updated_at") or row.get("thesis_reviewed_at") or "") or utc_now_iso()
            materiality = self.materiality_policy.classify(
                domain="research",
                entity_type="watchlist_thesis",
                field_path="thesis",
                payload=row,
            )
            text_parts = [f"Watchlist thesis for {symbol}."]
            if thesis:
                text_parts.append(f"Thesis: {_compact_text(thesis, limit=700)}")
            if note:
                text_parts.append(f"Note: {_compact_text(note, limit=400)}")
            if tags:
                text_parts.append(f"Tags: {', '.join(str(tag) for tag in tags)}.")
            if row.get("target_price_usd") is not None:
                text_parts.append(f"Target price: {_format_value('target_price_usd', row.get('target_price_usd'))}.")

            items.append(
                _build_context_item(
                    id=_stable_context_id("research", "watchlist", symbol, data_source),
                    domain="research",
                    entity_type="watchlist_thesis",
                    entity_id=symbol,
                    source_ref=f"portfolio/watchlist.json#items.{symbol}.{data_source}",
                    authority="source_evidence",
                    text=" ".join(text_parts),
                    structured_payload={"symbol": symbol, **dict(row)},
                    provenance={"source": "portfolio_store.watchlist", "data_source": data_source},
                    quality={
                        "confidence": "medium" if thesis else "low",
                        "freshness": "current" if row.get("thesis_reviewed_at") else "unknown",
                        "thesis_reviewed_at": row.get("thesis_reviewed_at") or None,
                        "thesis_expires_at": row.get("thesis_expires_at") or None,
                    },
                    materiality=materiality,
                    created_at=str(row.get("created_at") or updated_at),
                    updated_at=updated_at,
                    source_updated_at=updated_at,
                )
            )
        return items

    def build_all_items(
        self,
        *,
        profile_payload: Mapping[str, Any],
        profile_path: Path,
        plan_workspace: Any,
        recommendation_inbox: Any,
        portfolio_store: Any | None = None,
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        items.extend(self.build_profile_items(profile_payload=profile_payload, profile_path=profile_path))
        items.extend(self.build_plan_items(plan_workspace=plan_workspace))
        items.extend(self.build_recommendation_items(recommendation_inbox=recommendation_inbox))
        items.extend(self.build_watchlist_items(portfolio_store=portfolio_store))
        return items


class ContextIntelligenceService:
    def __init__(
        self,
        *,
        database_path: Path,
        financial_profile_store: Any,
        plan_workspace: Any,
        recommendation_inbox: Any,
        portfolio_store: Any | None = None,
        indexer: ContextIndexer | None = None,
    ):
        self.registry = ContextRegistry(database_path)
        self.financial_profile_store = financial_profile_store
        self.plan_workspace = plan_workspace
        self.recommendation_inbox = recommendation_inbox
        self.portfolio_store = portfolio_store
        self.indexer = indexer or ContextIndexer()

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        financial_profile_store: Any,
        plan_workspace: Any,
        recommendation_inbox: Any,
        portfolio_store: Any | None = None,
    ) -> "ContextIntelligenceService":
        return cls(
            database_path=settings.durable_storage_dir / "context_index.db",
            financial_profile_store=financial_profile_store,
            plan_workspace=plan_workspace,
            recommendation_inbox=recommendation_inbox,
            portfolio_store=portfolio_store,
        )

    def rebuild_registry(self) -> dict[str, Any]:
        profile_payload = self.financial_profile_store.get()
        items = self.indexer.build_all_items(
            profile_payload=profile_payload,
            profile_path=self.financial_profile_store.profile_path,
            plan_workspace=self.plan_workspace,
            recommendation_inbox=self.recommendation_inbox,
            portfolio_store=self.portfolio_store,
        )
        report = self.registry.replace_all(items)
        return {
            **report,
            "status": self.registry.status(),
        }

    def get_status(self) -> dict[str, Any]:
        return self.registry.status()

    def search_context(
        self,
        *,
        query: str = "",
        domains: Iterable[Any] | Any | None = None,
        plan_id: str | None = None,
        symbols: Iterable[Any] | Any | None = None,
        entity_types: Iterable[Any] | Any | None = None,
        recommendation_status: str | None = None,
        field_path: str | None = None,
        limit: int = 20,
        rebuild_if_empty: bool = False,
    ) -> dict[str, Any]:
        if rebuild_if_empty and self.registry.status().get("item_count") == 0:
            self.rebuild_registry()
        return self.registry.search(
            query=query,
            domains=domains,
            plan_id=plan_id,
            symbols=symbols,
            entity_types=entity_types,
            recommendation_status=recommendation_status,
            field_path=field_path,
            limit=limit,
        )

    def sync_conflict_review_items(
        self,
        conflicts: Iterable[Mapping[str, Any]],
        *,
        plan_id: str | None = None,
        symbols: Iterable[Any] | Any | None = None,
        relevance_reason: str = "copilot_answer",
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        synced: list[dict[str, Any]] = []
        timestamp = _now_iso(now)
        for conflict in conflicts:
            if not isinstance(conflict, Mapping) or not _is_persistent_material_conflict(conflict):
                continue
            dedupe_key = context_conflict_dedupe_key(
                conflict,
                plan_id=plan_id,
                symbols=symbols,
            )
            existing = self._find_conflict_review_item(dedupe_key)
            payload = _build_conflict_review_action_payload(
                conflict=conflict,
                dedupe_key=dedupe_key,
                plan_id=plan_id,
                symbols=symbols,
                existing=existing,
                relevance_reason=relevance_reason,
                now=timestamp,
            )
            title = _conflict_review_title(payload)
            detail = _conflict_review_detail(payload)
            priority = _conflict_priority(conflict)

            if existing is None:
                created = self.recommendation_inbox.create(
                    title=title,
                    detail=detail,
                    priority=priority,
                    recommendation_type=CONTEXT_CONFLICT_RECOMMENDATION_TYPE,
                    source=CONTEXT_CONFLICT_RECOMMENDATION_SOURCE,
                    plan_id=plan_id,
                    action_payload=payload,
                    status="proposed",
                )
                synced.append(_conflict_review_sync_result(created, created=True))
            else:
                updated = self.recommendation_inbox.update(
                    str(existing.get("id")),
                    {
                        "title": title,
                        "detail": detail,
                        "priority": priority,
                        "plan_id": plan_id,
                        "action_payload": payload,
                    },
                )
                synced.append(_conflict_review_sync_result(updated, created=False))
        return synced

    def defer_context_conflict_review_item(
        self,
        recommendation_id: str,
        *,
        deferred_until: str,
        reason: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        recommendation = self.recommendation_inbox.get(recommendation_id)
        action_payload = recommendation.get("action_payload")
        if not isinstance(action_payload, dict) or "context_conflict" not in action_payload:
            raise ValueError("recommendation is not a context conflict review item")

        payload = dict(action_payload)
        context_conflict = dict(payload.get("context_conflict") or {})
        context_conflict["resolution_state"] = "deferred"
        context_conflict["blocks_decision_grade_advice"] = True
        context_conflict["updated_at"] = _now_iso(now)
        context_conflict["deferral"] = {
            "deferred_until": str(deferred_until or "").strip(),
            "reason": str(reason or "").strip(),
            "deferred_at": _now_iso(now),
            "relevance_triggered_resurfaced": False,
            "resurfaced_at": None,
        }
        payload["context_conflict"] = context_conflict
        payload["quality"] = _conflict_review_quality(context_conflict)
        return self.recommendation_inbox.update(
            recommendation_id,
            {
                "detail": _conflict_review_detail(payload),
                "action_payload": payload,
            },
        )

    def _find_conflict_review_item(self, dedupe_key: str) -> dict[str, Any] | None:
        for row in self.recommendation_inbox.list(limit=None, include_archived=True, sort="none"):
            if str(row.get("recommendation_type") or "").strip().lower() != CONTEXT_CONFLICT_RECOMMENDATION_TYPE:
                continue
            action_payload = row.get("action_payload")
            if not isinstance(action_payload, Mapping):
                continue
            context_conflict = action_payload.get("context_conflict")
            if not isinstance(context_conflict, Mapping):
                continue
            if str(context_conflict.get("dedupe_key") or "") == dedupe_key:
                return dict(row)
        return None


def classify_context_intent(
    question: str,
    *,
    symbols: Iterable[Any] | Any | None = None,
) -> dict[str, Any]:
    """Classify retrieval intent with deterministic keyword rules."""

    question_text = str(question or "").strip()
    lowered = question_text.lower()
    resolved_symbols = tuple(
        dict.fromkeys([*_normalized_symbol_values(symbols), *_extract_question_symbols(question_text)])
    )

    signals: list[str] = []
    intent = "general"
    domains = ["profile", "plan", "recommendation", "research"]
    confidence = "low"

    investment_terms = (
        "buy",
        "sell",
        "stock",
        "ticker",
        "investment",
        "invest",
        "portfolio fit",
        "fit",
        "exposure",
        "concentration",
        "watchlist",
        "thesis",
        "dossier",
    )
    profile_terms = (
        "profile",
        "tax",
        "filing",
        "risk tolerance",
        "investment policy",
        "cash runway",
        "restricted",
    )
    planning_terms = (
        "plan",
        "retire",
        "retirement",
        "scenario",
        "projection",
        "contribution",
        "roth",
        "drawdown",
        "withdrawal",
    )
    recommendation_terms = (
        "recommendation",
        "should i",
        "what should",
        "next action",
        "apply",
        "reject",
    )

    if resolved_symbols or any(term in lowered for term in investment_terms):
        intent = "investment_fit"
        domains = ["research", "plan", "profile", "recommendation"]
        confidence = "high" if resolved_symbols else "medium"
        signals.append("investment_language")
    if any(term in lowered for term in profile_terms):
        if intent == "general":
            intent = "profile_question"
            domains = ["profile", "plan", "recommendation"]
            confidence = "medium"
        signals.append("profile_language")
    if any(term in lowered for term in planning_terms):
        if intent == "general":
            intent = "planning_question"
            domains = ["plan", "profile", "recommendation", "research"]
            confidence = "medium"
        signals.append("planning_language")
    if any(term in lowered for term in recommendation_terms):
        if intent == "general":
            intent = "recommendation_review"
            domains = ["recommendation", "plan", "profile", "research"]
            confidence = "medium"
        signals.append("recommendation_language")

    if resolved_symbols:
        signals.append("symbol_detected")
    if not signals:
        signals.append("general_context")

    return {
        "intent": intent,
        "confidence": confidence,
        "signals": list(dict.fromkeys(signals)),
        "domains": domains,
        "symbols": list(resolved_symbols),
        "search_query": question_text,
    }


class ContextAssembler:
    """Assemble structured context plus retrieved evidence for Copilot."""

    def __init__(
        self,
        *,
        context_service: ContextIntelligenceService,
        max_retrieved_items: int = 12,
        max_retrieved_text_chars: int = 6000,
    ):
        self.context_service = context_service
        self.max_retrieved_items = max(1, min(int(max_retrieved_items), 50))
        self.max_retrieved_text_chars = max(300, min(int(max_retrieved_text_chars), 24_000))

    async def assemble_context(
        self,
        *,
        question: str,
        plan_id: str | None,
        symbols: Iterable[Any] | Any | None,
        intent: Mapping[str, Any] | str | None,
        structured_context_builder: Callable[..., Awaitable[dict[str, Any]]],
        builder_options: Mapping[str, Any] | None = None,
        max_retrieved_items: int | None = None,
        max_retrieved_text_chars: int | None = None,
    ) -> dict[str, Any]:
        started_at = utc_now_iso()
        builder_kwargs = dict(builder_options or {})
        resolved_intent = _resolve_intent_payload(question=question, intent=intent, symbols=symbols)
        resolved_symbols = _merge_symbol_lists(symbols, resolved_intent.get("symbols"))
        if resolved_symbols and not builder_kwargs.get("research_symbols"):
            builder_kwargs["research_symbols"] = list(resolved_symbols)

        structured_context = await structured_context_builder(**builder_kwargs)
        scope = structured_context.get("scope")
        scope = scope if isinstance(scope, Mapping) else {}
        resolved_plan_id = str(plan_id or scope.get("plan_id") or "").strip() or None

        raw_items = self._retrieve_items(
            question=question,
            intent_payload=resolved_intent,
            plan_id=resolved_plan_id,
            symbols=resolved_symbols,
            max_items=max_retrieved_items or self.max_retrieved_items,
        )
        retrieved_context, citations, context_budget = _budget_retrieved_items(
            raw_items,
            max_items=max_retrieved_items or self.max_retrieved_items,
            max_text_chars=max_retrieved_text_chars or self.max_retrieved_text_chars,
        )
        conflicts = _build_assembly_conflicts(
            structured_context=structured_context,
            retrieved_context=retrieved_context,
        )
        conflict_review_items = self.context_service.sync_conflict_review_items(
            conflicts,
            plan_id=resolved_plan_id,
            symbols=resolved_symbols,
            relevance_reason="copilot_answer",
        )

        trace = {
            "assembler_version": CONTEXT_ASSEMBLER_VERSION,
            "started_at": started_at,
            "assembled_at": utc_now_iso(),
            "intent": resolved_intent,
            "plan_id": resolved_plan_id,
            "symbols": list(resolved_symbols),
            "retrieval": {
                "candidate_count": len(raw_items),
                "returned_count": len(retrieved_context.get("items", [])),
                "citation_count": len(citations),
                "truncated": bool(context_budget.get("truncated")),
            },
            "conflict_review_items": {
                "count": len(conflict_review_items),
                "ids": [
                    str(item.get("recommendation_id") or "")
                    for item in conflict_review_items
                    if item.get("recommendation_id")
                ],
            },
            "registry": self.context_service.get_status(),
            "structured_context_builder": "build_buildwealth_context_payload",
        }

        return {
            **structured_context,
            "retrieved_context": retrieved_context,
            "citations": citations,
            "context_budget": context_budget,
            "conflicts": conflicts,
            "conflict_review_items": conflict_review_items,
            "trace": trace,
        }

    def _retrieve_items(
        self,
        *,
        question: str,
        intent_payload: Mapping[str, Any],
        plan_id: str | None,
        symbols: tuple[str, ...],
        max_items: int,
    ) -> list[dict[str, Any]]:
        domains = intent_payload.get("domains")
        domains = domains if isinstance(domains, list) else None
        raw_results: list[dict[str, Any]] = []

        primary_result = self.context_service.search_context(
            query=question,
            domains=domains,
            symbols=symbols,
            limit=max_items * 2,
            rebuild_if_empty=True,
        )
        raw_results.extend(_result_items(primary_result))

        if plan_id:
            plan_result = self.context_service.search_context(
                query=question,
                domains=["plan", "research", "recommendation"],
                plan_id=plan_id,
                limit=max_items,
                rebuild_if_empty=True,
            )
            raw_results.extend(_result_items(plan_result))

        if not raw_results:
            fallback_result = self.context_service.search_context(
                query=question,
                domains=domains,
                limit=max_items,
                rebuild_if_empty=True,
            )
            raw_results.extend(_result_items(fallback_result))

        return _dedupe_result_items(raw_results)


def _build_context_item(
    *,
    id: str,
    domain: str,
    entity_type: str,
    entity_id: str,
    source_ref: str,
    authority: str,
    text: str,
    structured_payload: dict[str, Any],
    provenance: dict[str, Any],
    quality: dict[str, Any],
    materiality: MaterialityDecision,
    created_at: str,
    updated_at: str,
    source_updated_at: str | None,
) -> ContextItem:
    resolved_quality = dict(quality)
    resolved_quality.update(materiality.as_quality_fields())
    return ContextItem(
        id=id,
        domain=domain,
        entity_type=entity_type,
        entity_id=entity_id,
        source_ref=source_ref,
        authority=authority,
        text=_compact_text(text, limit=1800),
        structured_payload=structured_payload,
        provenance=provenance,
        quality=resolved_quality,
        materiality=materiality.materiality,
        materiality_rationale=materiality.rationale,
        action_readiness=materiality.action_readiness,
        created_at=created_at,
        updated_at=updated_at,
        source_updated_at=source_updated_at,
    )


def _recommendation_quality(row: Mapping[str, Any]) -> dict[str, Any]:
    action_payload = row.get("action_payload")
    action_payload = action_payload if isinstance(action_payload, Mapping) else {}
    quality = action_payload.get("quality")
    if isinstance(quality, Mapping):
        return dict(quality)
    return {"confidence": "medium", "freshness": "unknown"}


def _counts_by_domain(items: Iterable[ContextItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.domain] = counts.get(item.domain, 0) + 1
    return dict(sorted(counts.items()))


def _item_row(item: ContextItem, *, indexed_at: str) -> tuple[Any, ...]:
    return (
        item.id,
        item.domain,
        item.entity_type,
        item.entity_id,
        item.source_ref,
        item.authority,
        item.text,
        _json_dumps(item.structured_payload),
        _json_dumps(item.provenance),
        _json_dumps(item.quality),
        item.materiality,
        item.materiality_rationale,
        item.action_readiness,
        item.created_at,
        item.updated_at,
        item.source_updated_at,
        indexed_at,
    )


def _item_from_row(row: sqlite3.Row) -> ContextItem:
    return ContextItem(
        id=str(row["id"]),
        domain=str(row["domain"]),
        entity_type=str(row["entity_type"]),
        entity_id=str(row["entity_id"]),
        source_ref=str(row["source_ref"]),
        authority=str(row["authority"]),
        text=str(row["text"]),
        structured_payload=_json_loads_object(row["structured_payload"]),
        provenance=_json_loads_object(row["provenance"]),
        quality=_json_loads_object(row["quality"]),
        materiality=str(row["materiality"]),
        materiality_rationale=str(row["materiality_rationale"]),
        action_readiness=str(row["action_readiness"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        source_updated_at=str(row["source_updated_at"]) if row["source_updated_at"] is not None else None,
    )


def _matches_search_filters(
    item: ContextItem,
    *,
    domains: tuple[str, ...],
    plan_id: str,
    symbols: tuple[str, ...],
    entity_types: tuple[str, ...],
    recommendation_status: str,
    field_path: str,
) -> bool:
    if domains and item.domain.lower() not in domains:
        return False
    if entity_types and item.entity_type.lower() not in entity_types:
        return False
    if plan_id and not _item_matches_plan_id(item, plan_id):
        return False
    if symbols and not _item_matches_symbols(item, symbols):
        return False
    if recommendation_status and _structured_value_lower(item, "status") != recommendation_status:
        return False
    if field_path and not _item_matches_field_path(item, field_path):
        return False
    return True


def _item_matches_plan_id(item: ContextItem, plan_id: str) -> bool:
    target = plan_id.strip()
    if not target:
        return True
    if str(item.structured_payload.get("plan_id") or "").strip() == target:
        return True
    return f"/{target}/" in item.source_ref or item.source_ref.endswith(f"/{target}/metadata")


def _item_matches_symbols(item: ContextItem, symbols: tuple[str, ...]) -> bool:
    if not symbols:
        return True
    haystack = _context_search_haystack(item).upper()
    return any(
        re.search(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", haystack) is not None
        for symbol in symbols
    )


def _item_matches_field_path(item: ContextItem, field_path: str) -> bool:
    target = field_path.strip()
    if not target:
        return True
    target_lower = target.lower()
    payload_field = str(item.structured_payload.get("field") or "").strip().lower()
    return (
        payload_field == target_lower
        or item.entity_id.lower() == target_lower
        or item.source_ref.lower().endswith(f"#{target_lower}")
        or item.source_ref.lower().endswith(target_lower)
    )


def _structured_value_lower(item: ContextItem, key: str) -> str:
    return str(item.structured_payload.get(key) or "").strip().lower()


def _score_context_item(
    item: ContextItem,
    *,
    query: str,
    query_terms: tuple[str, ...],
    exact_filter_count: int,
) -> dict[str, Any]:
    lexical_score, matched_terms = _lexical_score(item, query=query, query_terms=query_terms)
    exact_score = min(1.0, exact_filter_count * 0.25)
    recency_score = _recency_score(item)
    quality_score = _quality_score(item)
    authority_score = AUTHORITY_SCORE.get(item.authority, 0.45)
    materiality_score = MATERIALITY_SCORE.get(item.materiality, 0.35)
    total_score = (
        lexical_score * 0.4
        + exact_score * 0.18
        + quality_score * 0.18
        + recency_score * 0.1
        + authority_score * 0.08
        + materiality_score * 0.06
    )
    return {
        "score": round(total_score, 4),
        "matched_terms": matched_terms,
        "score_breakdown": {
            "lexical": round(lexical_score, 4),
            "exact_filters": round(exact_score, 4),
            "quality": round(quality_score, 4),
            "recency": round(recency_score, 4),
            "authority": round(authority_score, 4),
            "materiality": round(materiality_score, 4),
        },
    }


def _lexical_score(
    item: ContextItem,
    *,
    query: str,
    query_terms: tuple[str, ...],
) -> tuple[float, list[str]]:
    if not query_terms:
        return 0.0, []
    haystack = _context_search_haystack(item).lower()
    matched = [term for term in query_terms if term in haystack]
    if not matched:
        return 0.0, []
    coverage = len(matched) / max(1, len(query_terms))
    phrase_bonus = 0.2 if query and query.lower() in haystack else 0.0
    entity_bonus = 0.12 if any(term in item.entity_id.lower() for term in matched) else 0.0
    return min(1.0, coverage + phrase_bonus + entity_bonus), matched


def _search_terms(query: str) -> tuple[str, ...]:
    terms = []
    for token in re.findall(r"[A-Za-z0-9_.%-]+", str(query or "").lower()):
        token = token.strip("._-%")
        if len(token) < 2 and not token.isdigit():
            continue
        terms.append(token)
    return tuple(dict.fromkeys(terms))


def _context_search_haystack(item: ContextItem) -> str:
    return " ".join(
        (
            item.id,
            item.domain,
            item.entity_type,
            item.entity_id,
            item.source_ref,
            item.text,
            _json_dumps(item.structured_payload),
            _json_dumps(item.provenance),
            _json_dumps(item.quality),
        )
    )


def _quality_score(item: ContextItem) -> float:
    confidence = str(
        item.quality.get("confidence") or item.quality.get("confidence_level") or "unknown"
    ).strip().lower()
    freshness = str(item.quality.get("freshness") or "unknown").strip().lower()
    status = str(item.quality.get("status") or "").strip().lower()
    confidence_score = CONFIDENCE_SCORE.get(confidence, CONFIDENCE_SCORE["unknown"])
    freshness_score = FRESHNESS_SCORE.get(freshness, FRESHNESS_SCORE["unknown"])
    status_bonus = 0.08 if status == "user_confirmed" else 0.0
    status_penalty = 0.12 if status in {"copilot_drafted", "inferred", "stale"} else 0.0
    return max(0.0, min(1.0, (confidence_score * 0.55) + (freshness_score * 0.45) + status_bonus - status_penalty))


def _recency_score(item: ContextItem) -> float:
    parsed = _parse_datetime(item.source_updated_at or item.updated_at or item.created_at)
    if parsed is None:
        return 0.5
    age_days = max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86_400)
    if age_days <= 30:
        return 1.0
    if age_days <= 180:
        return 0.75
    if age_days <= 365:
        return 0.55
    return 0.35


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _search_result_payload(item: ContextItem, *, score: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.id,
        "domain": item.domain,
        "entity_type": item.entity_type,
        "entity_id": item.entity_id,
        "source_ref": item.source_ref,
        "authority": item.authority,
        "text": item.text,
        "structured_payload": item.structured_payload,
        "provenance": item.provenance,
        "quality": item.quality,
        "materiality": item.materiality,
        "materiality_rationale": item.materiality_rationale,
        "action_readiness": item.action_readiness,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "source_updated_at": item.source_updated_at,
        "score": score["score"],
        "score_breakdown": score["score_breakdown"],
        "matched_terms": score["matched_terms"],
    }


def context_conflict_dedupe_key(
    conflict: Mapping[str, Any],
    *,
    plan_id: str | None = None,
    symbols: Iterable[Any] | Any | None = None,
) -> str:
    source_refs = _source_refs_from_conflict(conflict)
    payload = {
        "type": str(conflict.get("type") or "context_conflict").strip().lower(),
        "conflict_id": str(conflict.get("id") or "").strip(),
        "source_refs": source_refs,
        "plan_id": str(plan_id or "").strip(),
        "symbols": list(_normalized_symbol_values(symbols)),
    }
    return f"context_conflict:{_hash_payload(payload, length=18)}"


def _is_persistent_material_conflict(conflict: Mapping[str, Any]) -> bool:
    severity = str(conflict.get("severity") or "").strip().lower()
    return bool(conflict.get("blocks_decision_grade_advice")) or severity in {"high", "critical"}


def _build_conflict_review_action_payload(
    *,
    conflict: Mapping[str, Any],
    dedupe_key: str,
    plan_id: str | None,
    symbols: Iterable[Any] | Any | None,
    existing: Mapping[str, Any] | None,
    relevance_reason: str,
    now: str,
) -> dict[str, Any]:
    existing_payload = existing.get("action_payload") if isinstance(existing, Mapping) else {}
    existing_payload = existing_payload if isinstance(existing_payload, Mapping) else {}
    existing_conflict = existing_payload.get("context_conflict")
    existing_conflict = existing_conflict if isinstance(existing_conflict, Mapping) else {}

    source_refs = _source_refs_from_conflict(conflict)
    route = _context_conflict_route(conflict)
    state = _next_conflict_resolution_state(
        existing_conflict=existing_conflict,
        relevance_reason=relevance_reason,
        now=now,
    )
    first_seen_at = str(existing_conflict.get("first_seen_at") or now)
    seen_count = _safe_int(existing_conflict.get("seen_count"), 0) + 1
    deferral = _next_conflict_deferral(
        existing_conflict=existing_conflict,
        state=state,
        relevance_reason=relevance_reason,
        now=now,
    )
    blocks_decision_grade = not state.startswith("resolved_by_")

    context_conflict = {
        "schema_version": CONTEXT_CONFLICT_REVIEW_SCHEMA_VERSION,
        "dedupe_key": dedupe_key,
        "resolution_state": state,
        "conflict_type": str(conflict.get("type") or "context_conflict"),
        "severity": str(conflict.get("severity") or "high"),
        "plain_language": str(conflict.get("plain_language") or "This context needs review."),
        "source_refs": source_refs,
        "plan_id": str(plan_id or "").strip() or None,
        "symbols": list(_normalized_symbol_values(symbols)),
        "route": route,
        "review_actions": _context_conflict_review_actions(route),
        "deferral": deferral,
        "first_seen_at": first_seen_at,
        "last_seen_at": now,
        "seen_count": seen_count,
        "relevance_reason": str(relevance_reason or "").strip() or "unknown",
        "blocks_decision_grade_advice": blocks_decision_grade,
        "llm_assistance": {
            "explain_allowed": True,
            "recommend_allowed": True,
            "requires_user_confirmation_before_source_mutation": True,
        },
        "raw_conflict": dict(conflict),
    }
    return {
        "schema_version": CONTEXT_CONFLICT_REVIEW_SCHEMA_VERSION,
        "context_conflict": context_conflict,
        "quality": _conflict_review_quality(context_conflict),
        "suggested_action": {
            "type": "review_context_conflict",
            "route": route,
            "mutation_requires_confirmation": True,
            "summary": "Review or confirm the source context before relying on decision-grade advice.",
        },
    }


def _next_conflict_resolution_state(
    *,
    existing_conflict: Mapping[str, Any],
    relevance_reason: str,
    now: str,
) -> str:
    state = str(existing_conflict.get("resolution_state") or "unresolved").strip().lower()
    if state not in CONTEXT_CONFLICT_RESOLUTION_STATES:
        state = "unresolved"
    if state != "deferred":
        return state
    if _deferred_conflict_should_resurface(
        existing_conflict=existing_conflict,
        relevance_reason=relevance_reason,
        now=now,
    ):
        return "unresolved"
    return "deferred"


def _next_conflict_deferral(
    *,
    existing_conflict: Mapping[str, Any],
    state: str,
    relevance_reason: str,
    now: str,
) -> dict[str, Any]:
    existing_deferral = existing_conflict.get("deferral")
    deferral = dict(existing_deferral) if isinstance(existing_deferral, Mapping) else {}
    if state != "unresolved":
        return {
            "deferred_until": deferral.get("deferred_until"),
            "reason": deferral.get("reason") or "",
            "deferred_at": deferral.get("deferred_at"),
            "relevance_triggered_resurfaced": bool(deferral.get("relevance_triggered_resurfaced")),
            "resurfaced_at": deferral.get("resurfaced_at"),
        }

    if str(existing_conflict.get("resolution_state") or "").strip().lower() != "deferred":
        return {
            "deferred_until": deferral.get("deferred_until"),
            "reason": deferral.get("reason") or "",
            "deferred_at": deferral.get("deferred_at"),
            "relevance_triggered_resurfaced": bool(deferral.get("relevance_triggered_resurfaced")),
            "resurfaced_at": deferral.get("resurfaced_at"),
        }

    relevance_resurfaced = _relevance_reason_resurfaces(relevance_reason)
    return {
        "deferred_until": deferral.get("deferred_until"),
        "reason": deferral.get("reason") or "",
        "deferred_at": deferral.get("deferred_at"),
        "relevance_triggered_resurfaced": relevance_resurfaced or bool(
            deferral.get("relevance_triggered_resurfaced")
        ),
        "resurfaced_at": now,
    }


def _deferred_conflict_should_resurface(
    *,
    existing_conflict: Mapping[str, Any],
    relevance_reason: str,
    now: str,
) -> bool:
    if _relevance_reason_resurfaces(relevance_reason):
        return True
    deferral = existing_conflict.get("deferral")
    deferral = deferral if isinstance(deferral, Mapping) else {}
    deferred_until = _parse_datetime(deferral.get("deferred_until"))
    now_dt = _parse_datetime(now)
    if deferred_until is None or now_dt is None:
        return False
    return deferred_until <= now_dt


def _relevance_reason_resurfaces(relevance_reason: str) -> bool:
    reason = str(relevance_reason or "").strip().lower()
    return reason in CONTEXT_CONFLICT_RELEVANCE_RESURFACE_REASONS


def _context_conflict_route(conflict: Mapping[str, Any]) -> dict[str, Any]:
    refs = _source_refs_from_conflict(conflict)
    route = "copilot"
    label = "Copilot-guided review"
    target = "copilot"
    reason = "Use Copilot to explain the context conflict and pick the right source to review."

    if any(ref.startswith("profile/") for ref in refs):
        route = "profile"
        label = "Profile"
        target = "financial_profile"
        reason = "The context comes from the financial profile."
    elif any(ref.startswith("portfolio/watchlist") or "research" in ref.lower() for ref in refs):
        route = "research"
        label = "Research"
        target = "research_or_watchlist"
        reason = "The context comes from research evidence or a watchlist thesis."
    elif any(ref.startswith("plans/") for ref in refs):
        route = "plan"
        label = "Plan"
        target = "plan_workspace"
        reason = "The context comes from plan settings, decisions, or artifacts."
    elif any(ref.startswith("recommendations/") for ref in refs):
        route = "inbox"
        label = "Inbox"
        target = "recommendation_inbox"
        reason = "The context comes from an existing recommendation."

    return {
        "route": route,
        "label": label,
        "target": target,
        "reason": reason,
        "source_refs": refs,
    }


def _context_conflict_review_actions(route: Mapping[str, Any]) -> list[dict[str, Any]]:
    route_name = str(route.get("route") or "copilot").strip().lower()
    route_label = str(route.get("label") or "source").strip()
    return [
        {
            "action": "confirm_existing_source",
            "label": f"Confirm the current {route_label} context",
            "route": route_name,
            "requires_user_confirmation": True,
            "mutates_source": True,
            "resolution_state": "resolved_by_confirming_existing_source",
        },
        {
            "action": "update_source",
            "label": f"Update the {route_label} context",
            "route": route_name,
            "requires_user_confirmation": True,
            "mutates_source": True,
            "resolution_state": "resolved_by_source_update",
        },
        {
            "action": "reject_candidate",
            "label": "Reject the conflicting candidate",
            "route": route_name,
            "requires_user_confirmation": True,
            "mutates_source": False,
            "resolution_state": "resolved_by_rejecting_candidate",
        },
        {
            "action": "defer",
            "label": "Defer this review but keep the caution",
            "route": "inbox",
            "requires_user_confirmation": True,
            "mutates_source": False,
            "resolution_state": "deferred",
        },
        {
            "action": "explain",
            "label": "Explain why this matters",
            "route": "copilot",
            "requires_user_confirmation": False,
            "mutates_source": False,
        },
        {
            "action": "recommend",
            "label": "Recommend what to review first",
            "route": "copilot",
            "requires_user_confirmation": False,
            "mutates_source": False,
        },
        {
            "action": "record_scoped_exception",
            "label": "Record a narrow exception",
            "route": route_name,
            "requires_user_confirmation": True,
            "mutates_source": True,
            "resolution_state": "resolved_by_scoped_exception",
        },
    ]


def _source_refs_from_conflict(conflict: Mapping[str, Any]) -> list[str]:
    refs = conflict.get("source_refs")
    resolved = [str(ref).strip() for ref in refs if str(ref).strip()] if isinstance(refs, list) else []
    if resolved:
        return sorted(dict.fromkeys(resolved))

    raw_conflict = conflict.get("raw_conflict")
    if isinstance(raw_conflict, Mapping):
        nested = _source_refs_from_conflict(raw_conflict)
        if nested:
            return nested

    missing_sections = conflict.get("missing_sections")
    if isinstance(missing_sections, list):
        resolved.extend(_source_refs_from_missing_sections(missing_sections))
    return sorted(dict.fromkeys(resolved))


def _source_refs_from_missing_sections(missing_sections: Iterable[Any]) -> list[str]:
    refs: list[str] = []
    for item in missing_sections:
        text = str(item or "").strip()
        if text.startswith("financial_profile."):
            field_path = text.removeprefix("financial_profile.")
            field_path = re.sub(r"\.(stale|missing|needs_review)$", "", field_path)
            refs.append(f"profile/financial_profile.json#{field_path}")
        elif text.startswith("planning."):
            refs.append(f"plans/context#{text.removeprefix('planning.')}")
        elif text.startswith("research."):
            refs.append(f"research/context#{text.removeprefix('research.')}")
        elif text.startswith("recommendations."):
            refs.append(f"recommendations/inbox.json#{text.removeprefix('recommendations.')}")
    return refs


def _conflict_review_quality(context_conflict: Mapping[str, Any]) -> dict[str, Any]:
    blocks = bool(context_conflict.get("blocks_decision_grade_advice"))
    severity = str(context_conflict.get("severity") or "high").strip().lower()
    dedupe_key = str(context_conflict.get("dedupe_key") or "")
    return {
        "schema_version": 1,
        "source": "context_intelligence_conflict_review",
        "confidence_level": "high",
        "freshness_status": "fresh",
        "actionability": "review_only",
        "decision_grade": False,
        "blocking_context": [dedupe_key] if blocks and dedupe_key else [],
        "actionability_reasons": [
            "This is a review item. It explains the issue but does not change financial sources by itself."
        ],
        "impact": {
            "level": "high" if severity in {"critical", "high"} else "medium",
            "summary": "Context should be reviewed before using it for decision-grade advice.",
        },
    }


def _conflict_review_title(payload: Mapping[str, Any]) -> str:
    context_conflict = payload.get("context_conflict")
    context_conflict = context_conflict if isinstance(context_conflict, Mapping) else {}
    route = context_conflict.get("route")
    route = route if isinstance(route, Mapping) else {}
    route_label = str(route.get("label") or "context").strip()
    return f"Review {route_label} context before relying on advice"


def _conflict_review_detail(payload: Mapping[str, Any]) -> str:
    context_conflict = payload.get("context_conflict")
    context_conflict = context_conflict if isinstance(context_conflict, Mapping) else {}
    plain = str(context_conflict.get("plain_language") or "Some context needs review.").strip()
    route = context_conflict.get("route")
    route = route if isinstance(route, Mapping) else {}
    route_label = str(route.get("label") or "Copilot-guided review").strip()
    state = str(context_conflict.get("resolution_state") or "unresolved").strip()
    deferral = context_conflict.get("deferral")
    deferral = deferral if isinstance(deferral, Mapping) else {}
    deferred_until = str(deferral.get("deferred_until") or "").strip()
    deferred_note = (
        f"\n\nDeferred until: {deferred_until}. This only snoozes the review; it does not make the conflict resolved."
        if state == "deferred" and deferred_until
        else ""
    )
    return (
        f"{plain}\n\n"
        f"Review path: {route_label}. This item is review-only. Asking Copilot to explain or recommend a next step "
        "can help you understand the issue, but updating profile, plan, research, or recommendation context still "
        "requires your explicit confirmation.\n\n"
        "Until this is resolved, decision-grade advice should carry this caution."
        f"{deferred_note}"
    )


def _conflict_priority(conflict: Mapping[str, Any]) -> str:
    severity = str(conflict.get("severity") or "high").strip().lower()
    if severity in {"critical", "high"} or conflict.get("blocks_decision_grade_advice"):
        return "high"
    if severity == "low":
        return "low"
    return "medium"


def _conflict_review_sync_result(row: Mapping[str, Any], *, created: bool) -> dict[str, Any]:
    action_payload = row.get("action_payload")
    action_payload = action_payload if isinstance(action_payload, Mapping) else {}
    context_conflict = action_payload.get("context_conflict")
    context_conflict = context_conflict if isinstance(context_conflict, Mapping) else {}
    deferral = context_conflict.get("deferral")
    deferral = deferral if isinstance(deferral, Mapping) else {}
    route = context_conflict.get("route")
    route = route if isinstance(route, Mapping) else {}
    return {
        "recommendation_id": row.get("id"),
        "dedupe_key": context_conflict.get("dedupe_key"),
        "created": created,
        "resolution_state": context_conflict.get("resolution_state"),
        "route": route.get("route"),
        "source_refs": context_conflict.get("source_refs") or [],
        "blocks_decision_grade_advice": bool(context_conflict.get("blocks_decision_grade_advice")),
        "deferred_until": deferral.get("deferred_until"),
        "relevance_triggered_resurfaced": bool(deferral.get("relevance_triggered_resurfaced")),
    }


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _resolve_intent_payload(
    *,
    question: str,
    intent: Mapping[str, Any] | str | None,
    symbols: Iterable[Any] | Any | None,
) -> dict[str, Any]:
    classified = classify_context_intent(question, symbols=symbols)
    if intent is None:
        return classified
    if isinstance(intent, str):
        if not intent.strip():
            return classified
        resolved = dict(classified)
        resolved["intent"] = intent.strip()
        resolved["confidence"] = "manual"
        return resolved
    resolved = dict(classified)
    resolved.update({str(key): value for key, value in intent.items()})
    if "symbols" in resolved:
        resolved["symbols"] = list(_merge_symbol_lists(symbols, resolved.get("symbols")))
    return resolved


def _merge_symbol_lists(*symbol_groups: Any) -> tuple[str, ...]:
    merged: list[str] = []
    for group in symbol_groups:
        for symbol in _normalized_symbol_values(group):
            if symbol not in merged:
                merged.append(symbol)
    return tuple(merged)


def _result_items(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = result.get("items")
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, Mapping)]


def _dedupe_result_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(items, key=lambda row: float(row.get("score") or 0.0), reverse=True):
        item_id = str(item.get("id") or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        deduped.append(item)
    return deduped


def _budget_retrieved_items(
    items: list[dict[str, Any]],
    *,
    max_items: int,
    max_text_chars: int,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    bounded_item_limit = max(1, min(int(max_items), 50))
    text_budget = max(300, min(int(max_text_chars), 24_000))
    used_chars = 0
    returned_items: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    text_truncated = False

    for item in items[:bounded_item_limit]:
        resolved_item = dict(item)
        text = str(resolved_item.get("text") or "")
        remaining = max(0, text_budget - used_chars)
        if remaining <= 0:
            resolved_item["text"] = ""
            resolved_item["text_truncated"] = bool(text)
            text_truncated = text_truncated or bool(text)
        elif len(text) > remaining:
            resolved_item["text"] = (
                f"{text[: max(0, remaining - 3)].rstrip()}..."
                if remaining > 3
                else text[:remaining]
            )
            resolved_item["text_truncated"] = True
            used_chars += len(str(resolved_item["text"]))
            text_truncated = True
        else:
            resolved_item["text_truncated"] = False
            used_chars += len(text)

        returned_items.append(resolved_item)
        citations.append(_citation_from_context_item(resolved_item))

    item_truncated = len(items) > len(returned_items)
    context_budget = {
        "max_retrieved_items": bounded_item_limit,
        "candidate_items": len(items),
        "returned_items": len(returned_items),
        "max_retrieved_text_chars": text_budget,
        "returned_text_chars": used_chars,
        "truncated": item_truncated or text_truncated,
        "item_truncated": item_truncated,
        "text_truncated": text_truncated,
    }
    retrieved_context = {
        "count": len(returned_items),
        "items": returned_items,
        "truncated": bool(context_budget["truncated"]),
    }
    return retrieved_context, citations, context_budget


def _citation_from_context_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "context_item_id": item.get("id"),
        "source_ref": item.get("source_ref"),
        "domain": item.get("domain"),
        "entity_type": item.get("entity_type"),
        "authority": item.get("authority"),
        "materiality": item.get("materiality"),
        "text_preview": _compact_text(item.get("text"), limit=220),
    }


def _build_assembly_conflicts(
    *,
    structured_context: Mapping[str, Any],
    retrieved_context: Mapping[str, Any],
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    quality = structured_context.get("quality")
    quality = quality if isinstance(quality, Mapping) else {}
    coverage = quality.get("coverage")
    coverage = coverage if isinstance(coverage, Mapping) else {}
    missing_sections = coverage.get("missing_sections")
    missing = [str(item) for item in missing_sections if str(item).strip()] if isinstance(missing_sections, list) else []
    if missing:
        source_refs = _source_refs_from_missing_sections(missing)
        conflicts.append(
            {
                "id": f"context_quality:{_hash_payload(missing)}",
                "type": "missing_or_stale_context",
                "severity": "high",
                "plain_language": (
                    "Some financial context needs review before relying on decision-grade advice: "
                    f"{', '.join(missing[:5])}."
                ),
                "source_refs": source_refs,
                "missing_sections": missing,
                "review_actions": [
                    {"action": "review_context", "label": "Review the missing or stale context"},
                    {"action": "explain", "label": "Explain why this matters"},
                    {"action": "recommend", "label": "Recommend what to confirm first"},
                ],
                "blocks_decision_grade_advice": True,
            }
        )

    items = retrieved_context.get("items")
    if not isinstance(items, list):
        return conflicts

    for item in items[:8]:
        if not isinstance(item, Mapping):
            continue
        quality_payload = item.get("quality")
        quality_payload = quality_payload if isinstance(quality_payload, Mapping) else {}
        status = str(quality_payload.get("status") or "").strip().lower()
        freshness = str(quality_payload.get("freshness") or "").strip().lower()
        if status not in {"stale", "copilot_drafted", "inferred"} and freshness != "stale":
            continue
        label = str(item.get("entity_id") or item.get("source_ref") or "this context")
        conflicts.append(
            {
                "id": f"retrieved_context:{item.get('id')}",
                "type": "retrieved_context_needs_review",
                "severity": item.get("materiality") or "medium",
                "plain_language": (
                    f"{label} may need confirmation before using it for a recommendation."
                ),
                "source_refs": [item.get("source_ref")],
                "review_actions": [
                    {"action": "confirm_source", "label": "Confirm the current source"},
                    {"action": "update_source", "label": "Update the source"},
                    {"action": "defer", "label": "Defer and keep the caution"},
                    {"action": "explain", "label": "Explain this caution"},
                ],
                "blocks_decision_grade_advice": item.get("materiality") in {"high", "critical"},
            }
        )

    return conflicts

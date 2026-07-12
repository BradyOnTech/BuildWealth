"""Context Intelligence registry, indexing, and materiality helpers."""

from __future__ import annotations

import logging

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping

from buildwealth_orchestrator.services.embedding_clients import (
    DisabledEmbeddingClient,
    EmbeddingClient,
    build_embedding_client_from_settings,
)
from buildwealth_orchestrator.services.financial_profile import profile_metadata_quality_for_field
from buildwealth_orchestrator.services.session_focus import (
    EffectiveFocus,
    apply_focus_score_boost,
    collect_muted_safety_warnings,
    merge_focus_with_intent,
    plan_pass_domains,
    run_plan_id_pass,
)

logger = logging.getLogger(__name__)


CONTEXT_REGISTRY_SCHEMA_VERSION = 1
MATERIALITY_POLICY_VERSION = "global_v1"
CONTEXT_ASSEMBLER_VERSION = "context_intelligence_assembler_v2"
CONTEXT_CONFLICT_REVIEW_SCHEMA_VERSION = 1
CONTEXT_CONFLICT_RECOMMENDATION_TYPE = "context_conflict_review"
CONTEXT_CONFLICT_RECOMMENDATION_SOURCE = "context_intelligence"
CONTEXT_CANDIDATE_REVIEW_RECOMMENDATION_TYPE = "context_candidate_review"
CONTEXT_CANDIDATE_REVIEW_RECOMMENDATION_SOURCE = "context_intelligence"
CONTEXT_CANDIDATE_SCHEMA_VERSION = 1
CONTEXT_CANDIDATE_EVENT_SCHEMA_VERSION = 1
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
EMBEDDING_INDEX_SCHEMA_VERSION = 1
EMBEDDING_ELIGIBLE_ENTITY_TYPES = {
    "plan_context_section",
    "plan_decision",
    "plan_artifact",
    "research_dossier_artifact",
    "watchlist_thesis",
    "recommendation",
    "context_candidate",
}
CONTEXT_CANDIDATE_LIFECYCLE_STATES = {
    "pending_review",
    "deferred",
    "stale_unconfirmed",
    "applied",
    "rejected",
    "superseded",
    "archived",
}
CONTEXT_CANDIDATE_PROMPT_INFLUENCE_LEVELS = {
    "none",
    "mention_only",
    "supporting_context",
    "authoritative",
}
CONTEXT_CANDIDATE_REVIEW_ITEM_MATERIALITY = {"high", "critical"}
CONTEXT_CANDIDATE_INDEXABLE_STATES = {"applied"}

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
    "income_items",
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


def _json_loads_list(value: str | None) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _normalize_vector(values: Iterable[Any] | None) -> list[float] | None:
    if values is None:
        return None
    vector: list[float] = []
    for value in values:
        try:
            vector.append(float(value))
        except (TypeError, ValueError):
            return None
    if not vector or all(value == 0.0 for value in vector):
        return None
    return vector


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
                """
                CREATE TABLE IF NOT EXISTS context_embeddings (
                    context_item_id TEXT PRIMARY KEY,
                    embedding_provider TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    text_hash TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    embedded_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS context_candidates (
                    id TEXT PRIMARY KEY,
                    dedupe_key TEXT NOT NULL UNIQUE,
                    source_domain TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    extracted_claim TEXT NOT NULL,
                    target_domain TEXT NOT NULL,
                    target_area TEXT NOT NULL,
                    target_field TEXT,
                    target_value_json TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    materiality TEXT NOT NULL,
                    materiality_rationale TEXT NOT NULL,
                    action_readiness TEXT NOT NULL,
                    review_route TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL,
                    prompt_influence TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    applied_at TEXT,
                    archived_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS context_candidate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
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
                CREATE INDEX IF NOT EXISTS idx_context_embeddings_provider_model
                ON context_embeddings(embedding_provider, embedding_model)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_context_candidates_state
                ON context_candidates(lifecycle_state, prompt_influence)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_context_candidates_source_ref
                ON context_candidates(source_ref)
                """
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO registry_metadata(key, value)
                VALUES ('schema_version', ?)
                """,
                (str(CONTEXT_REGISTRY_SCHEMA_VERSION),),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO registry_metadata(key, value)
                VALUES ('embedding_schema_version', ?)
                """,
                (str(EMBEDDING_INDEX_SCHEMA_VERSION),),
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO registry_metadata(key, value)
                VALUES ('context_candidate_schema_version', ?)
                """,
                (str(CONTEXT_CANDIDATE_SCHEMA_VERSION),),
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
                "embeddings": {
                    "schema_version": EMBEDDING_INDEX_SCHEMA_VERSION,
                    "embedded_count": 0,
                    "eligible_count": 0,
                    "providers": [],
                    "latest_embedded_at": None,
                },
                "candidates": {
                    "schema_version": CONTEXT_CANDIDATE_SCHEMA_VERSION,
                    "candidate_count": 0,
                    "pending_review_count": 0,
                    "indexable_count": 0,
                    "counts_by_state": {},
                },
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
            embedding_count = int(connection.execute("SELECT COUNT(*) FROM context_embeddings").fetchone()[0])
            latest_embedding = connection.execute(
                "SELECT MAX(embedded_at) AS latest_embedded_at FROM context_embeddings"
            ).fetchone()
            provider_rows = connection.execute(
                """
                SELECT embedding_provider, embedding_model, dimensions, COUNT(*) AS count
                FROM context_embeddings
                GROUP BY embedding_provider, embedding_model, dimensions
                ORDER BY embedding_provider, embedding_model
                """
            ).fetchall()
            candidate_count = int(connection.execute("SELECT COUNT(*) FROM context_candidates").fetchone()[0])
            pending_review_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM context_candidates WHERE lifecycle_state = 'pending_review'"
                ).fetchone()[0]
            )
            indexable_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM context_candidates
                    WHERE lifecycle_state = 'applied'
                      AND prompt_influence IN ('supporting_context', 'authoritative')
                    """
                ).fetchone()[0]
            )
            state_rows = connection.execute(
                """
                SELECT lifecycle_state, COUNT(*) AS count
                FROM context_candidates
                GROUP BY lifecycle_state
                ORDER BY lifecycle_state
                """
            ).fetchall()

        items = self.list_items(limit=5000)
        eligible_count = sum(1 for item in items if _embedding_item_is_eligible(item))

        return {
            "schema_version": CONTEXT_REGISTRY_SCHEMA_VERSION,
            "database_path": str(self.database_path),
            "database_exists": True,
            "item_count": item_count,
            "counts_by_domain": {str(row["domain"]): int(row["count"]) for row in rows},
            "latest_rebuild_at": str(latest["value"]) if latest is not None else None,
            "embeddings": {
                "schema_version": EMBEDDING_INDEX_SCHEMA_VERSION,
                "embedded_count": embedding_count,
                "eligible_count": eligible_count,
                "providers": [
                    {
                        "provider": str(row["embedding_provider"]),
                        "model": str(row["embedding_model"]),
                        "dimensions": int(row["dimensions"]),
                        "count": int(row["count"]),
                    }
                    for row in provider_rows
                ],
                "latest_embedded_at": (
                    str(latest_embedding["latest_embedded_at"])
                    if latest_embedding is not None and latest_embedding["latest_embedded_at"] is not None
                    else None
                ),
            },
            "candidates": {
                "schema_version": CONTEXT_CANDIDATE_SCHEMA_VERSION,
                "candidate_count": candidate_count,
                "pending_review_count": pending_review_count,
                "indexable_count": indexable_count,
                "counts_by_state": {str(row["lifecycle_state"]): int(row["count"]) for row in state_rows},
            },
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

    def rebuild_embeddings(
        self,
        items: Iterable[ContextItem],
        *,
        embedding_client: EmbeddingClient,
    ) -> dict[str, Any]:
        self._initialize()
        resolved_items = list(items)
        eligible_items = [item for item in resolved_items if _embedding_item_is_eligible(item)]
        provider = str(getattr(embedding_client, "provider", "disabled") or "disabled")
        model = str(getattr(embedding_client, "model", "disabled") or "disabled")

        self._prune_embeddings_for_items(resolved_items)
        if not getattr(embedding_client, "enabled", False):
            return {
                "enabled": False,
                "provider": provider,
                "model": model,
                "eligible_count": len(eligible_items),
                "embedded_count": 0,
                "reused_count": 0,
                "skipped_count": len(eligible_items),
                "failed_count": 0,
            }

        embedded_count = 0
        reused_count = 0
        failed_count = 0
        embedded_at = utc_now_iso()
        with self._connect() as connection:
            for item in eligible_items:
                text = _embedding_text_for_item(item)
                text_hash = _hash_payload({"text": text}, length=32)
                existing = connection.execute(
                    """
                    SELECT text_hash
                    FROM context_embeddings
                    WHERE context_item_id = ?
                      AND embedding_provider = ?
                      AND embedding_model = ?
                    """,
                    (item.id, provider, model),
                ).fetchone()
                if existing is not None and str(existing["text_hash"]) == text_hash:
                    reused_count += 1
                    continue

                try:
                    vector = embedding_client.embed_text(text)
                    vector = _normalize_vector(vector)
                except Exception:
                    vector = None
                if vector is None:
                    failed_count += 1
                    continue

                connection.execute(
                    """
                    INSERT OR REPLACE INTO context_embeddings (
                        context_item_id, embedding_provider, embedding_model, dimensions,
                        text_hash, vector_json, embedded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        provider,
                        model,
                        len(vector),
                        text_hash,
                        _json_dumps(vector),
                        embedded_at,
                    ),
                )
                embedded_count += 1

        return {
            "enabled": True,
            "provider": provider,
            "model": model,
            "eligible_count": len(eligible_items),
            "embedded_count": embedded_count,
            "reused_count": reused_count,
            "skipped_count": max(0, len(eligible_items) - embedded_count - reused_count - failed_count),
            "failed_count": failed_count,
        }

    def _prune_embeddings_for_items(self, items: Iterable[ContextItem]) -> None:
        item_ids = [item.id for item in items]
        with self._connect() as connection:
            if not item_ids:
                connection.execute("DELETE FROM context_embeddings")
                return
            placeholders = ",".join("?" for _ in item_ids)
            connection.execute(
                f"DELETE FROM context_embeddings WHERE context_item_id NOT IN ({placeholders})",
                item_ids,
            )

    def embedding_vectors(
        self,
        *,
        provider: str,
        model: str,
        item_ids: Iterable[str] | None = None,
    ) -> dict[str, list[float]]:
        if not self.database_path.exists():
            return {}
        self._initialize()
        params: list[Any] = [provider, model]
        item_ids_list = [str(item_id) for item_id in item_ids or [] if str(item_id).strip()]
        item_filter = ""
        if item_ids_list:
            placeholders = ",".join("?" for _ in item_ids_list)
            item_filter = f"AND context_item_id IN ({placeholders})"
            params.extend(item_ids_list)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT context_item_id, vector_json
                FROM context_embeddings
                WHERE embedding_provider = ?
                  AND embedding_model = ?
                  {item_filter}
                """,
                params,
            ).fetchall()
        vectors: dict[str, list[float]] = {}
        for row in rows:
            vector = _normalize_vector(_json_loads_list(row["vector_json"]))
            if vector is not None:
                vectors[str(row["context_item_id"])] = vector
        return vectors

    def upsert_candidate(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        self._initialize()
        payload = _normalize_candidate_payload(candidate)
        existing: sqlite3.Row | None
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM context_candidates WHERE dedupe_key = ?",
                (payload["dedupe_key"],),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO context_candidates (
                        id, dedupe_key, source_domain, source_ref, extracted_claim,
                        target_domain, target_area, target_field, target_value_json,
                        confidence, materiality, materiality_rationale, action_readiness,
                        review_route, lifecycle_state, prompt_influence, metadata,
                        created_at, updated_at, applied_at, archived_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _candidate_row(payload),
                )
                self._record_candidate_event(
                    connection,
                    candidate_id=str(payload["id"]),
                    event_type="candidate_created",
                    payload=payload,
                )
                return payload

            merged = _candidate_from_row(existing)
            preserved_state = str(merged.get("lifecycle_state") or "pending_review")
            if preserved_state in {"applied", "rejected", "superseded", "archived"}:
                payload["lifecycle_state"] = preserved_state
                payload["prompt_influence"] = merged.get("prompt_influence")
                payload["applied_at"] = merged.get("applied_at")
                payload["archived_at"] = merged.get("archived_at")
            payload["id"] = merged["id"]
            payload["created_at"] = merged["created_at"]
            payload["updated_at"] = utc_now_iso()
            connection.execute(
                """
                UPDATE context_candidates
                SET source_domain = ?, source_ref = ?, extracted_claim = ?,
                    target_domain = ?, target_area = ?, target_field = ?, target_value_json = ?,
                    confidence = ?, materiality = ?, materiality_rationale = ?, action_readiness = ?,
                    review_route = ?, lifecycle_state = ?, prompt_influence = ?, metadata = ?,
                    updated_at = ?, applied_at = ?, archived_at = ?
                WHERE id = ?
                """,
                (
                    payload["source_domain"],
                    payload["source_ref"],
                    payload["extracted_claim"],
                    payload["target_domain"],
                    payload["target_area"],
                    payload.get("target_field"),
                    _json_dumps(payload.get("target_value")),
                    payload["confidence"],
                    payload["materiality"],
                    payload["materiality_rationale"],
                    payload["action_readiness"],
                    _json_dumps(payload["review_route"]),
                    payload["lifecycle_state"],
                    payload["prompt_influence"],
                    _json_dumps(payload["metadata"]),
                    payload["updated_at"],
                    payload.get("applied_at"),
                    payload.get("archived_at"),
                    payload["id"],
                ),
            )
            self._record_candidate_event(
                connection,
                candidate_id=str(payload["id"]),
                event_type="candidate_updated",
                payload=payload,
            )
        return payload

    def list_candidates(
        self,
        *,
        lifecycle_state: str | None = None,
        include_archived: bool = False,
        limit: int | None = 100,
    ) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        self._initialize()
        where: list[str] = []
        params: list[Any] = []
        if lifecycle_state:
            where.append("lifecycle_state = ?")
            params.append(str(lifecycle_state).strip().lower())
        elif not include_archived:
            where.append("lifecycle_state != 'archived'")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT ?"
            params.append(max(1, min(int(limit), 5000)))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM context_candidates
                {where_sql}
                ORDER BY updated_at DESC, created_at DESC
                {limit_sql}
                """,
                params,
            ).fetchall()
        return [_candidate_from_row(row) for row in rows]

    def update_candidate_lifecycle(
        self,
        candidate_id: str,
        *,
        lifecycle_state: str,
        prompt_influence: str | None = None,
        metadata_patch: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._initialize()
        state = _normalize_candidate_lifecycle_state(lifecycle_state)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM context_candidates WHERE id = ?",
                (str(candidate_id).strip(),),
            ).fetchone()
            if row is None:
                raise KeyError(f"Context candidate not found: {candidate_id}")

            payload = _candidate_from_row(row)
            now = utc_now_iso()
            payload["lifecycle_state"] = state
            payload["prompt_influence"] = _normalize_candidate_prompt_influence(
                prompt_influence if prompt_influence is not None else _default_prompt_influence_for_state(state)
            )
            metadata = dict(payload.get("metadata") or {})
            if isinstance(metadata_patch, Mapping):
                metadata.update(dict(metadata_patch))
            payload["metadata"] = metadata
            payload["updated_at"] = now
            if state == "applied":
                payload["applied_at"] = now
            if state == "archived":
                payload["archived_at"] = now

            connection.execute(
                """
                UPDATE context_candidates
                SET lifecycle_state = ?, prompt_influence = ?, metadata = ?,
                    updated_at = ?, applied_at = ?, archived_at = ?
                WHERE id = ?
                """,
                (
                    payload["lifecycle_state"],
                    payload["prompt_influence"],
                    _json_dumps(metadata),
                    payload["updated_at"],
                    payload.get("applied_at"),
                    payload.get("archived_at"),
                    payload["id"],
                ),
            )
            self._record_candidate_event(
                connection,
                candidate_id=str(payload["id"]),
                event_type=f"candidate_{state}",
                payload=payload,
            )
        return payload

    def candidate_events(self, candidate_id: str) -> list[dict[str, Any]]:
        if not self.database_path.exists():
            return []
        self._initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, candidate_id, event_type, created_at, payload
                FROM context_candidate_events
                WHERE candidate_id = ?
                ORDER BY id
                """,
                (str(candidate_id).strip(),),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "candidate_id": str(row["candidate_id"]),
                "event_type": str(row["event_type"]),
                "created_at": str(row["created_at"]),
                "payload": _json_loads_object(row["payload"]),
            }
            for row in rows
        ]

    def candidate_context_items(self) -> list[ContextItem]:
        items: list[ContextItem] = []
        for candidate in self.list_candidates(include_archived=True, limit=None):
            if not _candidate_is_indexable(candidate):
                continue
            items.append(_context_item_from_candidate(candidate))
        return items

    def _record_candidate_event(
        self,
        connection: sqlite3.Connection,
        *,
        candidate_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO context_candidate_events(candidate_id, event_type, created_at, payload)
            VALUES (?, ?, ?, ?)
            """,
            (
                candidate_id,
                event_type,
                utc_now_iso(),
                _json_dumps({"schema_version": CONTEXT_CANDIDATE_EVENT_SCHEMA_VERSION, **dict(payload)}),
            ),
        )

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
        query_embedding: list[float] | None = None,
        embedding_provider: str | None = None,
        embedding_model: str | None = None,
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

        candidate_items: list[ContextItem] = []
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
            candidate_items.append(item)

        semantic_scores = self._semantic_scores(
            query_embedding=query_embedding,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            item_ids=[item.id for item in candidate_items],
        )

        rows: list[dict[str, Any]] = []
        for item in candidate_items:
            score = _score_context_item(
                item,
                query=query_text,
                query_terms=query_terms,
                exact_filter_count=exact_filter_count,
                semantic_score=semantic_scores.get(item.id, 0.0),
                semantic_enabled=bool(semantic_scores),
            )
            if (
                query_terms
                and not score["matched_terms"]
                and exact_filter_count == 0
                and float(score["score_breakdown"].get("semantic") or 0.0) <= 0.0
            ):
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
            "semantic": {
                "enabled": bool(semantic_scores),
                "provider": embedding_provider,
                "model": embedding_model,
                "matched_count": len([score for score in semantic_scores.values() if score > 0]),
            },
            "total_candidates": len(rows),
            "count": min(len(rows), bounded_limit),
            "items": rows[:bounded_limit],
        }

    def _semantic_scores(
        self,
        *,
        query_embedding: list[float] | None,
        embedding_provider: str | None,
        embedding_model: str | None,
        item_ids: Iterable[str],
    ) -> dict[str, float]:
        query_vector = _normalize_vector(query_embedding)
        if query_vector is None or not embedding_provider or not embedding_model:
            return {}
        item_vectors = self.embedding_vectors(
            provider=embedding_provider,
            model=embedding_model,
            item_ids=item_ids,
        )
        scores: dict[str, float] = {}
        for item_id, vector in item_vectors.items():
            score = _cosine_similarity(query_vector, vector)
            scores[item_id] = max(0.0, min(1.0, score))
        return scores


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
            items.extend(
                self._build_single_plan_items(
                    plan_summary=plan_summary,
                    plan_detail=detail,
                    plan_workspace=plan_workspace,
                )
            )
        return items

    def _build_single_plan_items(
        self,
        *,
        plan_summary: Mapping[str, Any],
        plan_detail: Mapping[str, Any],
        plan_workspace: Any | None = None,
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
                artifact_content = ""
                if plan_workspace is not None:
                    try:
                        full_artifact = plan_workspace.read_artifact(plan_id=plan_id, artifact_id=artifact_id)
                    except Exception:
                        full_artifact = {}
                    if isinstance(full_artifact, Mapping):
                        artifact_content = str(full_artifact.get("content") or "").strip()
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
                        text=(
                            f"{'Research' if is_research else 'Plan'} artifact for {title}: "
                            f"{title_text}. {_compact_text(artifact_content, limit=1100)}"
                        ),
                        structured_payload={
                            "plan_id": plan_id,
                            **dict(artifact),
                            "content": _compact_text(artifact_content, limit=3000),
                        },
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
        embedding_client: EmbeddingClient | None = None,
        indexer: ContextIndexer | None = None,
    ):
        self.registry = ContextRegistry(database_path)
        self.financial_profile_store = financial_profile_store
        self.plan_workspace = plan_workspace
        self.recommendation_inbox = recommendation_inbox
        self.portfolio_store = portfolio_store
        self.embedding_client = embedding_client or DisabledEmbeddingClient()
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
        embedding_client: EmbeddingClient | None = None,
    ) -> "ContextIntelligenceService":
        # Default the embedding client from the same settings object rather
        # than DisabledEmbeddingClient — per-workspace services are rebuilt on
        # every request, so this is what makes saved embedding settings stick.
        if embedding_client is None:
            try:
                embedding_client = build_embedding_client_from_settings(settings)
            except Exception:
                embedding_client = None
        return cls(
            database_path=settings.durable_storage_dir / "context_index.db",
            financial_profile_store=financial_profile_store,
            plan_workspace=plan_workspace,
            recommendation_inbox=recommendation_inbox,
            portfolio_store=portfolio_store,
            embedding_client=embedding_client,
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
        items.extend(self.registry.candidate_context_items())
        report = self.registry.replace_all(items)
        embedding_report = self.registry.rebuild_embeddings(
            items,
            embedding_client=self.embedding_client,
        )
        return {
            **report,
            "embeddings": embedding_report,
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
        query_embedding: list[float] | None = None
        if getattr(self.embedding_client, "enabled", False) and str(query or "").strip():
            try:
                query_embedding = self.embedding_client.embed_text(str(query))
            except Exception as exc:
                # Fall back to structured search, but leave a trail — a wrong
                # base_url (e.g. host.docker.internal outside docker) otherwise
                # degrades semantic retrieval silently.
                logger.warning("query embedding failed; semantic search skipped: %s", exc)
                query_embedding = None
        return self.registry.search(
            query=query,
            domains=domains,
            plan_id=plan_id,
            symbols=symbols,
            entity_types=entity_types,
            recommendation_status=recommendation_status,
            field_path=field_path,
            limit=limit,
            query_embedding=query_embedding,
            embedding_provider=(
                str(self.embedding_client.provider)
                if getattr(self.embedding_client, "enabled", False) and query_embedding is not None
                else None
            ),
            embedding_model=(
                str(self.embedding_client.model)
                if getattr(self.embedding_client, "enabled", False) and query_embedding is not None
                else None
            ),
        )

    def rebuild_embeddings(self) -> dict[str, Any]:
        return self.registry.rebuild_embeddings(
            self.registry.list_items(limit=5000),
            embedding_client=self.embedding_client,
        )

    def draft_context_candidate(
        self,
        *,
        source_domain: str,
        source_ref: str,
        extracted_claim: str,
        target_domain: str,
        target_area: str,
        target_field: str | None = None,
        target_value: Any = None,
        confidence: str = "medium",
        metadata: Mapping[str, Any] | None = None,
        lifecycle_state: str = "pending_review",
        prompt_influence: str | None = None,
    ) -> dict[str, Any]:
        candidate = build_context_candidate_payload(
            source_domain=source_domain,
            source_ref=source_ref,
            extracted_claim=extracted_claim,
            target_domain=target_domain,
            target_area=target_area,
            target_field=target_field,
            target_value=target_value,
            confidence=confidence,
            metadata=metadata,
            lifecycle_state=lifecycle_state,
            prompt_influence=prompt_influence,
        )
        stored = self.registry.upsert_candidate(candidate)
        review_item = self._sync_context_candidate_review_item(stored)
        if review_item is not None:
            stored["review_item"] = review_item
        return stored

    def detect_chat_context_candidates(
        self,
        *,
        message: str,
        conversation_id: str | None = None,
        message_index: int | None = None,
    ) -> list[dict[str, Any]]:
        source_ref = _conversation_source_ref(conversation_id=conversation_id, message_index=message_index)
        drafts = detect_context_candidate_drafts_from_text(
            message,
            source_ref=source_ref,
        )
        return [self.draft_context_candidate(**draft) for draft in drafts]

    def summarize_conversation_candidate(
        self,
        *,
        conversation: Mapping[str, Any],
        min_messages: int = 8,
    ) -> dict[str, Any] | None:
        draft = build_conversation_summary_candidate(conversation, min_messages=min_messages)
        if draft is None:
            return None
        return self.draft_context_candidate(**draft)

    def list_context_candidates(
        self,
        *,
        lifecycle_state: str | None = None,
        include_archived: bool = False,
        limit: int | None = 100,
    ) -> list[dict[str, Any]]:
        return self.registry.list_candidates(
            lifecycle_state=lifecycle_state,
            include_archived=include_archived,
            limit=limit,
        )

    def list_context_candidate_events(self, candidate_id: str) -> list[dict[str, Any]]:
        return self.registry.candidate_events(candidate_id)

    def update_context_candidate_lifecycle(
        self,
        candidate_id: str,
        *,
        lifecycle_state: str,
        prompt_influence: str | None = None,
        metadata_patch: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        updated = self.registry.update_candidate_lifecycle(
            candidate_id,
            lifecycle_state=lifecycle_state,
            prompt_influence=prompt_influence,
            metadata_patch=metadata_patch,
        )
        self._sync_context_candidate_review_item(updated)
        return updated

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

    def _sync_context_candidate_review_item(self, candidate: Mapping[str, Any]) -> dict[str, Any] | None:
        existing = self._find_context_candidate_review_item(str(candidate.get("id") or ""))
        if not _candidate_requires_review_item(candidate):
            if existing is None:
                return None
            updated = self.recommendation_inbox.update(
                str(existing.get("id")),
                {
                    "title": _context_candidate_review_title(candidate),
                    "detail": _context_candidate_review_detail(candidate),
                    "priority": _candidate_review_priority(candidate),
                    "plan_id": _candidate_plan_id(candidate),
                    "action_payload": _context_candidate_review_action_payload(candidate),
                },
            )
            status = _context_candidate_review_status(candidate)
            closed = self.recommendation_inbox.set_status(
                str(updated.get("id")),
                status,
                resolution_note=f"Context candidate {candidate.get('lifecycle_state') or 'resolved'}.",
            )
            return _context_candidate_review_sync_result(closed, created=False)
        title = _context_candidate_review_title(candidate)
        detail = _context_candidate_review_detail(candidate)
        payload = _context_candidate_review_action_payload(candidate)
        if existing is None:
            created = self.recommendation_inbox.create(
                title=title,
                detail=detail,
                priority=_candidate_review_priority(candidate),
                recommendation_type=CONTEXT_CANDIDATE_REVIEW_RECOMMENDATION_TYPE,
                source=CONTEXT_CANDIDATE_REVIEW_RECOMMENDATION_SOURCE,
                plan_id=_candidate_plan_id(candidate),
                action_payload=payload,
                status="proposed",
            )
            return _context_candidate_review_sync_result(created, created=True)
        updated = self.recommendation_inbox.update(
            str(existing.get("id")),
            {
                "title": title,
                "detail": detail,
                "priority": _candidate_review_priority(candidate),
                "plan_id": _candidate_plan_id(candidate),
                "action_payload": payload,
            },
        )
        return _context_candidate_review_sync_result(updated, created=False)

    def _find_context_candidate_review_item(self, candidate_id: str) -> dict[str, Any] | None:
        for row in self.recommendation_inbox.list(limit=None, include_archived=True, sort="none"):
            if str(row.get("recommendation_type") or "").strip().lower() != CONTEXT_CANDIDATE_REVIEW_RECOMMENDATION_TYPE:
                continue
            action_payload = row.get("action_payload")
            if not isinstance(action_payload, Mapping):
                continue
            context_candidate = action_payload.get("context_candidate")
            if not isinstance(context_candidate, Mapping):
                continue
            if str(context_candidate.get("id") or "") == candidate_id:
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
        focus: Mapping[str, Any] | None = None,
        retrieval_focus_boost: bool = True,
    ) -> dict[str, Any]:
        started_at = utc_now_iso()
        builder_kwargs = dict(builder_options or {})
        resolved_intent = _resolve_intent_payload(question=question, intent=intent, symbols=symbols)
        resolved_symbols = _merge_symbol_lists(symbols, resolved_intent.get("symbols"))
        if resolved_symbols and not builder_kwargs.get("research_symbols"):
            builder_kwargs["research_symbols"] = list(resolved_symbols)

        effective_focus = merge_focus_with_intent(focus, resolved_intent)
        mode = effective_focus.mode
        mode_item_caps = {"narrow": 8, "balanced": 12, "wide": 12}
        mode_text_caps = {"narrow": 4000, "balanced": 6000, "wide": 6000}
        resolved_max_items = max_retrieved_items or min(
            self.max_retrieved_items,
            mode_item_caps.get(mode, 12),
        )
        resolved_max_text = max_retrieved_text_chars or min(
            self.max_retrieved_text_chars,
            mode_text_caps.get(mode, 6000),
        )

        structured_context = await structured_context_builder(**builder_kwargs)
        scope = structured_context.get("scope")
        scope = scope if isinstance(scope, Mapping) else {}
        resolved_plan_id = str(plan_id or scope.get("plan_id") or "").strip() or None

        raw_items = self._retrieve_items(
            question=question,
            intent_payload=resolved_intent,
            plan_id=resolved_plan_id,
            symbols=resolved_symbols,
            max_items=resolved_max_items,
            effective_focus=effective_focus,
        )
        raw_items = apply_focus_score_boost(
            raw_items,
            effective_focus,
            enabled=bool(retrieval_focus_boost),
        )
        retrieved_context, citations, context_budget = _budget_retrieved_items(
            raw_items,
            max_items=resolved_max_items,
            max_text_chars=resolved_max_text,
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
        quality = structured_context.get("quality")
        quality = quality if isinstance(quality, Mapping) else {}
        safety_warnings = collect_muted_safety_warnings(
            structured_context=structured_context,
            conflicts=conflicts,
            quality=quality,
            effective_focus=effective_focus,
            question=question,
            intent=resolved_intent,
        )

        trace = {
            "assembler_version": CONTEXT_ASSEMBLER_VERSION,
            "started_at": started_at,
            "assembled_at": utc_now_iso(),
            "intent": resolved_intent,
            "plan_id": resolved_plan_id,
            "symbols": list(resolved_symbols),
            "effective_focus": effective_focus.as_dict(),
            "retrieval": {
                "candidate_count": len(raw_items),
                "returned_count": len(retrieved_context.get("items", [])),
                "citation_count": len(citations),
                "truncated": bool(context_budget.get("truncated")),
                "domains": list(effective_focus.retrieval_registry_domains),
                "focus_boost": bool(retrieval_focus_boost),
                "plan_id_pass": run_plan_id_pass(plan_id=resolved_plan_id, effective=effective_focus),
            },
            "conflict_review_items": {
                "count": len(conflict_review_items),
                "ids": [
                    str(item.get("recommendation_id") or "")
                    for item in conflict_review_items
                    if item.get("recommendation_id")
                ],
            },
            "context_warnings": [
                {
                    "type": conflict.get("type"),
                    "severity": conflict.get("severity"),
                    "message": conflict.get("plain_language") or conflict.get("detail") or conflict.get("title"),
                    "source_refs": conflict.get("source_refs") or [],
                    "blocks_decision_grade_advice": bool(conflict.get("blocks_decision_grade_advice")),
                }
                for conflict in conflicts[:5]
                if isinstance(conflict, Mapping)
            ],
            "safety_warnings": safety_warnings,
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
            "safety_warnings": safety_warnings,
            "effective_focus": effective_focus.as_dict(),
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
        effective_focus: EffectiveFocus | None = None,
    ) -> list[dict[str, Any]]:
        if effective_focus is not None and effective_focus.retrieval_registry_domains:
            domains: list[str] | None = list(effective_focus.retrieval_registry_domains)
        else:
            raw_domains = intent_payload.get("domains")
            domains = raw_domains if isinstance(raw_domains, list) else None
        raw_results: list[dict[str, Any]] = []

        primary_result = self.context_service.search_context(
            query=question,
            domains=domains,
            symbols=symbols,
            limit=max_items * 2,
            rebuild_if_empty=True,
        )
        raw_results.extend(_result_items(primary_result))

        if effective_focus is not None and run_plan_id_pass(plan_id=plan_id, effective=effective_focus):
            plan_domains = plan_pass_domains(effective_focus)
            if plan_domains:
                plan_result = self.context_service.search_context(
                    query=question,
                    domains=plan_domains,
                    plan_id=plan_id,
                    limit=max_items,
                    rebuild_if_empty=True,
                )
                raw_results.extend(_result_items(plan_result))
        elif effective_focus is None and plan_id:
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
    semantic_score: float = 0.0,
    semantic_enabled: bool = False,
) -> dict[str, Any]:
    lexical_score, matched_terms = _lexical_score(item, query=query, query_terms=query_terms)
    exact_score = min(1.0, exact_filter_count * 0.25)
    resolved_semantic_score = max(0.0, min(float(semantic_score or 0.0), 1.0))
    recency_score = _recency_score(item)
    quality_score = _quality_score(item)
    authority_score = AUTHORITY_SCORE.get(item.authority, 0.45)
    materiality_score = MATERIALITY_SCORE.get(item.materiality, 0.35)
    if semantic_enabled:
        total_score = (
            lexical_score * 0.32
            + resolved_semantic_score * 0.24
            + exact_score * 0.16
            + quality_score * 0.12
            + recency_score * 0.07
            + authority_score * 0.05
            + materiality_score * 0.04
        )
    else:
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
            "semantic": round(resolved_semantic_score, 4),
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


def _embedding_item_is_eligible(item: ContextItem) -> bool:
    if item.entity_type not in EMBEDDING_ELIGIBLE_ENTITY_TYPES:
        return False
    text = _embedding_text_for_item(item)
    if not text:
        return False
    if item.authority == "canonical" and item.domain in {"profile", "portfolio"}:
        return False
    return True


def _embedding_text_for_item(item: ContextItem) -> str:
    payload = item.structured_payload if isinstance(item.structured_payload, dict) else {}
    parts = [
        item.domain,
        item.entity_type,
        item.entity_id,
        item.source_ref,
        item.text,
    ]
    for key in ("title", "summary", "rationale", "detail", "content", "thesis", "note", "description"):
        value = payload.get(key)
        if _present(value):
            parts.append(str(value))
    return _compact_text(" ".join(parts), limit=4000)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


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


def build_context_candidate_payload(
    *,
    source_domain: str,
    source_ref: str,
    extracted_claim: str,
    target_domain: str,
    target_area: str,
    target_field: str | None = None,
    target_value: Any = None,
    confidence: str = "medium",
    metadata: Mapping[str, Any] | None = None,
    lifecycle_state: str = "pending_review",
    prompt_influence: str | None = None,
) -> dict[str, Any]:
    source_domain_value = _clean_candidate_domain(source_domain, default="conversation")
    target_domain_value = _clean_candidate_domain(target_domain, default="conversation")
    target_area_value = str(target_area or "").strip() or "general"
    target_field_value = str(target_field or "").strip() or None
    claim = _compact_text(extracted_claim, limit=1200)
    metadata_payload = dict(metadata or {})
    materiality = _classify_context_candidate_materiality(
        target_domain=target_domain_value,
        target_area=target_area_value,
        target_field=target_field_value,
        target_value=target_value,
        metadata=metadata_payload,
    )
    state = _normalize_candidate_lifecycle_state(lifecycle_state)
    influence = _normalize_candidate_prompt_influence(
        prompt_influence
        if prompt_influence is not None
        else _default_prompt_influence_for_state(state, materiality=materiality.materiality)
    )
    dedupe_key = _context_candidate_dedupe_key(
        source_domain=source_domain_value,
        source_ref=source_ref,
        extracted_claim=claim,
        target_domain=target_domain_value,
        target_area=target_area_value,
        target_field=target_field_value,
    )
    now = utc_now_iso()
    return {
        "schema_version": CONTEXT_CANDIDATE_SCHEMA_VERSION,
        "id": _stable_context_id("candidate", dedupe_key),
        "dedupe_key": dedupe_key,
        "source_domain": source_domain_value,
        "source_ref": str(source_ref or "").strip() or f"{source_domain_value}/unknown",
        "extracted_claim": claim,
        "target_domain": target_domain_value,
        "target_area": target_area_value,
        "target_field": target_field_value,
        "target_value": target_value,
        "confidence": _normalize_candidate_confidence(confidence),
        "materiality": materiality.materiality,
        "materiality_rationale": materiality.rationale,
        "action_readiness": materiality.action_readiness,
        "review_route": _context_candidate_review_route(
            target_domain=target_domain_value,
            target_area=target_area_value,
            source_domain=source_domain_value,
        ),
        "lifecycle_state": state,
        "prompt_influence": influence,
        "metadata": {
            **metadata_payload,
            **materiality.as_quality_fields(),
            "llm_materiality_hint_used_as_input_only": bool(metadata_payload.get("llm_materiality_hint")),
        },
        "created_at": now,
        "updated_at": now,
        "applied_at": now if state == "applied" else None,
        "archived_at": now if state == "archived" else None,
    }


def detect_context_candidate_drafts_from_text(
    text: str,
    *,
    source_ref: str,
) -> list[dict[str, Any]]:
    message = str(text or "")
    drafts: list[dict[str, Any]] = []
    income_items: list[dict[str, Any]] = []
    income_claims: list[str] = []

    income_pattern = re.compile(
        r"\b(?P<subject>i|my\s+(?:wife|husband|spouse|partner))\s+"
        r"(?P<verb>make|makes|earn|earns|bring\s+in|brings\s+in)\s+"
        r"\$?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]+)?)\s*(?P<suffix>[kKmM])?\s*"
        r"(?P<cadence>per\s+year|a\s+year|annually|annual|/year|yr|per\s+month|a\s+month|monthly|/mo|/month)\b",
        re.I,
    )
    salary_pattern = re.compile(
        r"\b(?P<subject>my\s+salary|my\s+household\s+income|household\s+income)\s+"
        r"(?:is|=)\s+\$?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]+)?)\s*(?P<suffix>[kKmM])?\s*"
        r"(?P<cadence>per\s+year|a\s+year|annually|annual|/year|yr|per\s+month|a\s+month|monthly|/mo|/month)?\b",
        re.I,
    )

    for pattern in (income_pattern, salary_pattern):
        for match in pattern.finditer(message):
            if _looks_like_hypothetical_income_claim(message, match.start()):
                continue
            amount = _money_candidate_value(match.group("amount"), suffix=match.group("suffix"))
            cadence = str(match.group("cadence") or "annual").strip().lower()
            monthly_amount = amount if _income_cadence_is_monthly(cadence) else amount / 12.0
            subject = str(match.group("subject") or "").strip()
            income_claims.append(match.group(0))
            income_items.append(
                {
                    "label": _income_label_from_subject(subject),
                    "monthly_amount_usd": round(monthly_amount, 2),
                    "source_type": "salary",
                    "is_pre_tax": False,
                }
            )

    if income_items:
        summary = "; ".join(
            f"{item['label']}: ${item['monthly_amount_usd']:,.2f}/month"
            for item in income_items
        )
        drafts.append(
            _chat_candidate_draft(
                source_ref=source_ref,
                extracted_claim="; ".join(income_claims),
                target_domain="profile",
                target_area="income_items",
                target_field="income_items",
                target_value={
                    "summary": summary,
                    "income_items": income_items,
                    "requires_user_confirmation": True,
                },
                confidence="medium",
                metadata={
                    "extraction_kind": "income_claim",
                    "profile_patch_kind": "income_items",
                    "review_note": "Review or edit before adding to the financial profile.",
                },
            )
        )

    for match in re.finditer(r"\b(?:my\s+)?(?:marginal\s+)?tax\s+rate\s+(?:is|=)\s+([0-9]+(?:\.[0-9]+)?)\s*%?", message, re.I):
        value = _percent_candidate_value(match.group(1))
        drafts.append(
            _chat_candidate_draft(
                source_ref=source_ref,
                extracted_claim=match.group(0),
                target_domain="profile",
                target_area="tax_profile",
                target_field="tax_profile.marginal_tax_rate",
                target_value=value,
                confidence="medium",
            )
        )

    filing_match = re.search(
        r"\b(?:my\s+)?filing\s+status\s+(?:is|=)\s+([a-zA-Z_\s-]+?)(?:[.!?]|$)",
        message,
        re.I,
    )
    if filing_match:
        drafts.append(
            _chat_candidate_draft(
                source_ref=source_ref,
                extracted_claim=filing_match.group(0),
                target_domain="profile",
                target_area="tax_profile",
                target_field="tax_profile.filing_status",
                target_value=_clean_token(filing_match.group(1), fallback="unknown"),
                confidence="medium",
            )
        )

    risk_match = re.search(
        r"\b(?:my\s+)?risk\s+tolerance\s+(?:is|=)\s+(conservative|moderate|aggressive)\b",
        message,
        re.I,
    )
    if risk_match:
        drafts.append(
            _chat_candidate_draft(
                source_ref=source_ref,
                extracted_claim=risk_match.group(0),
                target_domain="profile",
                target_area="investment_policy",
                target_field="investment_policy.risk_tolerance",
                target_value=risk_match.group(1).lower(),
                confidence="medium",
            )
        )

    max_single_match = re.search(
        r"\bmax(?:imum)?\s+single[-\s]?(?:symbol|stock|holding)\s+(?:exposure|limit)\s+(?:is|=)\s+([0-9]+(?:\.[0-9]+)?)\s*%?",
        message,
        re.I,
    )
    if max_single_match:
        drafts.append(
            _chat_candidate_draft(
                source_ref=source_ref,
                extracted_claim=max_single_match.group(0),
                target_domain="profile",
                target_area="investment_policy",
                target_field="investment_policy.max_single_symbol_exposure_pct",
                target_value=float(max_single_match.group(1)),
                confidence="medium",
            )
        )

    contribution_match = re.search(
        r"\bannual\s+contribution\s+(?:is|=)\s+\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        message,
        re.I,
    )
    if contribution_match:
        drafts.append(
            _chat_candidate_draft(
                source_ref=source_ref,
                extracted_claim=contribution_match.group(0),
                target_domain="plan",
                target_area="settings",
                target_field="settings.annual_contribution_usd",
                target_value=_money_candidate_value(contribution_match.group(1)),
                confidence="medium",
            )
        )

    retirement_match = re.search(
        r"\b(?:retire|retirement)\s+(?:at|age)\s+([0-9]{2})\b",
        message,
        re.I,
    )
    if retirement_match:
        drafts.append(
            _chat_candidate_draft(
                source_ref=source_ref,
                extracted_claim=retirement_match.group(0),
                target_domain="plan",
                target_area="timeline",
                target_field="timeline.retirement.target_retirement_age",
                target_value=int(retirement_match.group(1)),
                confidence="medium",
            )
        )

    return _dedupe_candidate_drafts(drafts)


def build_conversation_summary_candidate(
    conversation: Mapping[str, Any],
    *,
    min_messages: int = 8,
) -> dict[str, Any] | None:
    messages = conversation.get("messages")
    if not isinstance(messages, list) or len(messages) < max(1, int(min_messages)):
        return None
    snippets: list[str] = []
    for message in messages[-12:]:
        if not isinstance(message, Mapping):
            continue
        role = str(message.get("role") or "").strip()
        content = _compact_text(message.get("content"), limit=220)
        if role and content:
            snippets.append(f"{role}: {content}")
    if not snippets:
        return None
    conversation_id = str(conversation.get("id") or "conversation").strip()
    summary = _compact_text(" | ".join(snippets), limit=1500)
    return {
        "source_domain": "conversation",
        "source_ref": f"conversation/{conversation_id}#summary",
        "extracted_claim": f"Conversation summary: {summary}",
        "target_domain": "conversation",
        "target_area": "conversation_summary",
        "target_field": None,
        "target_value": {"summary": summary, "message_count": len(messages)},
        "confidence": "medium",
        "metadata": {"conversation_id": conversation_id, "summary_kind": "deterministic_recent_messages"},
        "lifecycle_state": "pending_review",
        "prompt_influence": "mention_only",
    }


def _chat_candidate_draft(**kwargs: Any) -> dict[str, Any]:
    return {
        "source_domain": "conversation",
        "metadata": {"detector": "deterministic_chat_fact_v1"},
        "lifecycle_state": "pending_review",
        "prompt_influence": None,
        **kwargs,
    }


def _dedupe_candidate_drafts(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for draft in drafts:
        key = _context_candidate_dedupe_key(
            source_domain=str(draft.get("source_domain") or ""),
            source_ref=str(draft.get("source_ref") or ""),
            extracted_claim=str(draft.get("extracted_claim") or ""),
            target_domain=str(draft.get("target_domain") or ""),
            target_area=str(draft.get("target_area") or ""),
            target_field=str(draft.get("target_field") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(draft)
    return deduped


def _normalize_candidate_payload(candidate: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(candidate)
    if not payload.get("dedupe_key"):
        payload["dedupe_key"] = _context_candidate_dedupe_key(
            source_domain=str(payload.get("source_domain") or ""),
            source_ref=str(payload.get("source_ref") or ""),
            extracted_claim=str(payload.get("extracted_claim") or ""),
            target_domain=str(payload.get("target_domain") or ""),
            target_area=str(payload.get("target_area") or ""),
            target_field=str(payload.get("target_field") or ""),
        )
    payload["id"] = str(payload.get("id") or _stable_context_id("candidate", payload["dedupe_key"]))
    payload["source_domain"] = _clean_candidate_domain(payload.get("source_domain"), default="conversation")
    payload["source_ref"] = str(payload.get("source_ref") or f"{payload['source_domain']}/unknown").strip()
    payload["extracted_claim"] = _compact_text(payload.get("extracted_claim"), limit=1200)
    payload["target_domain"] = _clean_candidate_domain(payload.get("target_domain"), default="conversation")
    payload["target_area"] = str(payload.get("target_area") or "general").strip()
    payload["target_field"] = str(payload.get("target_field") or "").strip() or None
    payload["confidence"] = _normalize_candidate_confidence(payload.get("confidence"))
    payload["materiality"] = _normalize_materiality(payload.get("materiality"), default="low")
    payload["materiality_rationale"] = str(payload.get("materiality_rationale") or "").strip()
    payload["action_readiness"] = str(
        payload.get("action_readiness") or ACTION_READINESS_BY_MATERIALITY[payload["materiality"]]
    )
    review_route = payload.get("review_route")
    payload["review_route"] = dict(review_route) if isinstance(review_route, Mapping) else _context_candidate_review_route(
        target_domain=payload["target_domain"],
        target_area=payload["target_area"],
        source_domain=payload["source_domain"],
    )
    payload["lifecycle_state"] = _normalize_candidate_lifecycle_state(payload.get("lifecycle_state"))
    payload["prompt_influence"] = _normalize_candidate_prompt_influence(payload.get("prompt_influence"))
    metadata = payload.get("metadata")
    payload["metadata"] = dict(metadata) if isinstance(metadata, Mapping) else {}
    now = utc_now_iso()
    payload["created_at"] = str(payload.get("created_at") or now)
    payload["updated_at"] = str(payload.get("updated_at") or now)
    payload["applied_at"] = payload.get("applied_at")
    payload["archived_at"] = payload.get("archived_at")
    return payload


def _candidate_row(payload: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        payload["id"],
        payload["dedupe_key"],
        payload["source_domain"],
        payload["source_ref"],
        payload["extracted_claim"],
        payload["target_domain"],
        payload["target_area"],
        payload.get("target_field"),
        _json_dumps(payload.get("target_value")),
        payload["confidence"],
        payload["materiality"],
        payload["materiality_rationale"],
        payload["action_readiness"],
        _json_dumps(payload["review_route"]),
        payload["lifecycle_state"],
        payload["prompt_influence"],
        _json_dumps(payload["metadata"]),
        payload["created_at"],
        payload["updated_at"],
        payload.get("applied_at"),
        payload.get("archived_at"),
    )


def _candidate_from_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = {
        "schema_version": CONTEXT_CANDIDATE_SCHEMA_VERSION,
        "id": str(row["id"]),
        "dedupe_key": str(row["dedupe_key"]),
        "source_domain": str(row["source_domain"]),
        "source_ref": str(row["source_ref"]),
        "extracted_claim": str(row["extracted_claim"]),
        "target_domain": str(row["target_domain"]),
        "target_area": str(row["target_area"]),
        "target_field": str(row["target_field"]) if row["target_field"] else None,
        "target_value": _json_loads_any(row["target_value_json"]),
        "confidence": str(row["confidence"]),
        "materiality": str(row["materiality"]),
        "materiality_rationale": str(row["materiality_rationale"]),
        "action_readiness": str(row["action_readiness"]),
        "review_route": _json_loads_object(row["review_route"]),
        "lifecycle_state": str(row["lifecycle_state"]),
        "prompt_influence": str(row["prompt_influence"]),
        "metadata": _json_loads_object(row["metadata"]),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "applied_at": str(row["applied_at"]) if row["applied_at"] else None,
        "archived_at": str(row["archived_at"]) if row["archived_at"] else None,
    }
    return payload


def _json_loads_any(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _context_candidate_dedupe_key(
    *,
    source_domain: str,
    source_ref: str,
    extracted_claim: str,
    target_domain: str,
    target_area: str,
    target_field: str | None,
) -> str:
    payload = {
        "source_domain": _clean_candidate_domain(source_domain, default="conversation"),
        "source_ref": str(source_ref or "").strip(),
        "claim": _compact_text(extracted_claim, limit=500).lower(),
        "target_domain": _clean_candidate_domain(target_domain, default="conversation"),
        "target_area": str(target_area or "").strip().lower(),
        "target_field": str(target_field or "").strip().lower(),
    }
    return f"context_candidate:{_hash_payload(payload, length=18)}"


def _classify_context_candidate_materiality(
    *,
    target_domain: str,
    target_area: str,
    target_field: str | None,
    target_value: Any,
    metadata: Mapping[str, Any],
) -> MaterialityDecision:
    policy = MaterialityPolicy()
    domain = _clean_candidate_domain(target_domain, default="conversation")
    field_path = str(target_field or target_area or "").strip()
    entity_type = "context_candidate"
    if domain == "profile":
        if field_path.startswith("tax_profile."):
            entity_type = "tax_profile_field"
        elif field_path.startswith("investment_policy."):
            entity_type = "investment_policy_field"
    elif domain == "plan":
        entity_type = "plan_setting_field" if field_path.startswith("settings.") else "plan_decision"
    decision = policy.classify(
        domain=domain,
        entity_type=entity_type,
        field_path=field_path,
        payload={"value": target_value, **dict(metadata)},
    )
    hint = _normalize_materiality(metadata.get("llm_materiality_hint"), default="")
    if hint and hint in {"high", "critical"}:
        decision = policy.classify(
            domain=domain,
            entity_type=entity_type,
            field_path=field_path,
            payload={"value": target_value, **dict(metadata)},
            affects_live_advice=(hint == "critical"),
            conflicts_material_context=False,
        )
    return decision


def _context_candidate_review_route(
    *,
    target_domain: str,
    target_area: str,
    source_domain: str,
) -> dict[str, Any]:
    domain = _clean_candidate_domain(target_domain, default="conversation")
    if domain == "profile":
        return {
            "route": "profile",
            "label": "Profile",
            "target": target_area or "financial_profile",
            "reason": "Profile candidates must use the existing profile draft and apply flow.",
        }
    if domain == "plan":
        return {
            "route": "plan",
            "label": "Plan",
            "target": target_area or "plan_workspace",
            "reason": "Plan candidates must be reviewed through settings, timeline, decisions, or artifacts.",
        }
    if domain == "research":
        return {
            "route": "research",
            "label": "Research",
            "target": target_area or "research",
            "reason": "Research candidates belong in research or watchlist review.",
        }
    if domain == "recommendation":
        return {
            "route": "inbox",
            "label": "Inbox",
            "target": target_area or "recommendation_inbox",
            "reason": "Recommendation candidates belong in the Inbox review loop.",
        }
    if _clean_candidate_domain(source_domain, default="conversation") == "import":
        return {
            "route": "import",
            "label": "Import Review",
            "target": target_area or "import",
            "reason": "Imported candidates should be reviewed from the import surface.",
        }
    return {
        "route": "copilot",
        "label": "Copilot Review",
        "target": target_area or "context_capture",
        "reason": "Copilot can explain this capture before the user accepts or rejects it.",
    }


def _candidate_is_indexable(candidate: Mapping[str, Any]) -> bool:
    return (
        str(candidate.get("lifecycle_state") or "").strip().lower() in CONTEXT_CANDIDATE_INDEXABLE_STATES
        and str(candidate.get("prompt_influence") or "").strip().lower()
        in {"supporting_context", "authoritative"}
    )


def _context_item_from_candidate(candidate: Mapping[str, Any]) -> ContextItem:
    target_domain = _clean_candidate_domain(candidate.get("target_domain"), default="conversation")
    influence = str(candidate.get("prompt_influence") or "supporting_context").strip().lower()
    authority = "source_evidence" if influence != "authoritative" else "derived"
    updated_at = str(candidate.get("updated_at") or utc_now_iso())
    field_path = str(candidate.get("target_field") or candidate.get("target_area") or "context_candidate")
    materiality = MaterialityDecision(
        materiality=_normalize_materiality(candidate.get("materiality")),
        action_readiness=str(candidate.get("action_readiness") or "Can review later"),
        policy_version=str(
            (candidate.get("metadata") if isinstance(candidate.get("metadata"), Mapping) else {}).get(
                "materiality_policy_version",
                MATERIALITY_POLICY_VERSION,
            )
        ),
        rule_ids=tuple(
            (candidate.get("metadata") if isinstance(candidate.get("metadata"), Mapping) else {}).get(
                "materiality_rule_ids",
                [],
            )
        ),
        rationale=str(candidate.get("materiality_rationale") or ""),
    )
    return _build_context_item(
        id=_stable_context_id("candidate_context", candidate.get("id")),
        domain=target_domain,
        entity_type="context_candidate",
        entity_id=str(candidate.get("id") or ""),
        source_ref=str(candidate.get("source_ref") or ""),
        authority=authority,
        text=(
            f"Reviewed context capture for {field_path}: "
            f"{_compact_text(candidate.get('extracted_claim'), limit=900)}"
        ),
        structured_payload=dict(candidate),
        provenance={
            "source": "context_candidate",
            "source_domain": candidate.get("source_domain"),
            "prompt_influence": influence,
        },
        quality={
            "confidence": candidate.get("confidence"),
            "freshness": "current",
            "status": candidate.get("lifecycle_state"),
            "prompt_influence": influence,
        },
        materiality=materiality,
        created_at=str(candidate.get("created_at") or updated_at),
        updated_at=updated_at,
        source_updated_at=updated_at,
    )


def _clean_candidate_domain(value: Any, *, default: str) -> str:
    cleaned = _clean_token(value, fallback=default)
    return cleaned.replace("_", "-") if cleaned in {"follow-up"} else cleaned


def _normalize_candidate_confidence(value: Any) -> str:
    confidence = str(value or "").strip().lower()
    return confidence if confidence in {"low", "medium", "high"} else "medium"


def _normalize_candidate_lifecycle_state(value: Any) -> str:
    state = str(value or "").strip().lower()
    return state if state in CONTEXT_CANDIDATE_LIFECYCLE_STATES else "pending_review"


def _normalize_candidate_prompt_influence(value: Any) -> str:
    influence = str(value or "").strip().lower()
    return influence if influence in CONTEXT_CANDIDATE_PROMPT_INFLUENCE_LEVELS else "none"


def _default_prompt_influence_for_state(state: str, *, materiality: str = "low") -> str:
    if state == "applied":
        return "authoritative"
    if state in {"rejected", "superseded", "archived", "stale_unconfirmed"}:
        return "none"
    if state == "deferred":
        return "mention_only"
    return "none" if materiality == "low" else "mention_only"


def _candidate_requires_review_item(candidate: Mapping[str, Any]) -> bool:
    state = str(candidate.get("lifecycle_state") or "").strip().lower()
    if state in {"applied", "rejected", "superseded", "archived"}:
        return False
    materiality = str(candidate.get("materiality") or "").strip().lower()
    return materiality in CONTEXT_CANDIDATE_REVIEW_ITEM_MATERIALITY


def _context_candidate_review_title(candidate: Mapping[str, Any]) -> str:
    route = candidate.get("review_route")
    route = route if isinstance(route, Mapping) else {}
    label = str(route.get("label") or "Context").strip()
    return f"Review captured {label} context"


def _context_candidate_review_detail(candidate: Mapping[str, Any]) -> str:
    route = candidate.get("review_route")
    route = route if isinstance(route, Mapping) else {}
    route_label = str(route.get("label") or "the owning view").strip()
    claim = _compact_text(candidate.get("extracted_claim"), limit=500)
    target = str(candidate.get("target_field") or candidate.get("target_area") or "context").strip()
    return (
        f"Captured context needs review: {claim}\n\n"
        f"Where it would apply: {target}. Review path: {route_label}.\n\n"
        "This is not treated as financial truth yet. Accepting it should route through the owning source "
        "flow, such as Profile draft/apply, Plan settings or decisions, Research review, Import review, "
        "or Inbox review. Rejecting or deferring it keeps it out of authoritative Copilot context."
    )


def _context_candidate_review_action_payload(candidate: Mapping[str, Any]) -> dict[str, Any]:
    route = candidate.get("review_route")
    route = route if isinstance(route, Mapping) else {}
    return {
        "schema_version": CONTEXT_CANDIDATE_SCHEMA_VERSION,
        "context_candidate": dict(candidate),
        "quality": {
            "schema_version": 1,
            "source": "context_candidate_capture",
            "confidence_level": candidate.get("confidence") or "medium",
            "freshness_status": "fresh",
            "actionability": "review_only",
            "decision_grade": False,
            "blocking_context": [candidate.get("id")] if _candidate_requires_review_item(candidate) else [],
            "impact": {
                "level": candidate.get("materiality") or "medium",
                "summary": candidate.get("action_readiness") or "Review before relying on this.",
            },
        },
        "suggested_action": {
            "type": "review_context_candidate",
            "route": route.get("route") or "copilot",
            "target": route.get("target"),
            "requires_user_confirmation": True,
            "mutation_requires_confirmation": True,
            "summary": "Review the captured context before it can influence authoritative answers.",
        },
        "review_actions": [
            {
                "action": "accept_update_source",
                "label": "Accept and update the owning source",
                "route": route.get("route") or "copilot",
                "requires_user_confirmation": True,
                "mutates_source": True,
                "resulting_lifecycle_state": "applied",
            },
            {
                "action": "reject",
                "label": "Reject this captured context",
                "requires_user_confirmation": True,
                "mutates_source": False,
                "resulting_lifecycle_state": "rejected",
            },
            {
                "action": "defer",
                "label": "Defer this review",
                "requires_user_confirmation": True,
                "mutates_source": False,
                "resulting_lifecycle_state": "deferred",
            },
            {
                "action": "explain",
                "label": "Explain why this matters",
                "requires_user_confirmation": False,
                "mutates_source": False,
            },
        ],
    }


def _context_candidate_review_sync_result(row: Mapping[str, Any], *, created: bool) -> dict[str, Any]:
    action_payload = row.get("action_payload")
    action_payload = action_payload if isinstance(action_payload, Mapping) else {}
    candidate = action_payload.get("context_candidate")
    candidate = candidate if isinstance(candidate, Mapping) else {}
    route = candidate.get("review_route")
    route = route if isinstance(route, Mapping) else {}
    return {
        "recommendation_id": row.get("id"),
        "candidate_id": candidate.get("id"),
        "created": created,
        "route": route.get("route"),
        "materiality": candidate.get("materiality"),
        "lifecycle_state": candidate.get("lifecycle_state"),
    }


def _candidate_review_priority(candidate: Mapping[str, Any]) -> str:
    materiality = str(candidate.get("materiality") or "").strip().lower()
    return "high" if materiality in {"critical", "high"} else "medium"


def _context_candidate_review_status(candidate: Mapping[str, Any]) -> str:
    state = str(candidate.get("lifecycle_state") or "").strip().lower()
    if state == "applied":
        return "applied"
    if state == "rejected":
        return "rejected"
    return "archived"


def _candidate_plan_id(candidate: Mapping[str, Any]) -> str | None:
    metadata = candidate.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    plan_id = str(metadata.get("plan_id") or "").strip()
    return plan_id or None


def _conversation_source_ref(
    *,
    conversation_id: str | None,
    message_index: int | None,
) -> str:
    conversation = str(conversation_id or "conversation").strip() or "conversation"
    if message_index is None:
        return f"conversation/{conversation}"
    return f"conversation/{conversation}#message.{message_index}"


def _percent_candidate_value(value: Any) -> float:
    numeric = float(str(value).replace(",", ""))
    return numeric / 100.0 if numeric > 1 else numeric


def _money_candidate_value(value: Any, *, suffix: Any = None) -> float:
    numeric = float(str(value).replace(",", "").replace("$", ""))
    suffix_text = str(suffix or "").strip().lower()
    if suffix_text == "k":
        return numeric * 1_000
    if suffix_text == "m":
        return numeric * 1_000_000
    return numeric


def _income_cadence_is_monthly(cadence: str) -> bool:
    normalized = str(cadence or "").strip().lower()
    return normalized in {"per month", "a month", "monthly", "/mo", "/month"}


def _income_label_from_subject(subject: str) -> str:
    normalized = re.sub(r"\s+", " ", str(subject or "").strip().lower())
    if normalized in {"my wife", "my husband", "my spouse"}:
        return "Spouse income"
    if normalized == "my partner":
        return "Partner income"
    if normalized in {"my household income", "household income"}:
        return "Household income"
    return "My income"


def _looks_like_hypothetical_income_claim(message: str, start: int) -> bool:
    prefix = str(message or "")[max(0, start - 40) : start].lower()
    return bool(
        re.search(r"\b(?:what\s+if|if|assuming|suppose|hypothetically)\s+$", prefix)
        or re.search(r"\b(?:would|could|might|may)\s+$", prefix)
        or re.search(r"\b(?:want|hope|plan|expect)\s+to\s+$", prefix)
    )


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

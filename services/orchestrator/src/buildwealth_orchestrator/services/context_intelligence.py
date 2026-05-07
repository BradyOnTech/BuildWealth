"""Context Intelligence registry, indexing, and materiality helpers."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from buildwealth_orchestrator.services.financial_profile import profile_metadata_quality_for_field


CONTEXT_REGISTRY_SCHEMA_VERSION = 1
MATERIALITY_POLICY_VERSION = "global_v1"

MATERIALITY_LEVELS = ("low", "medium", "high", "critical")
ACTION_READINESS_BY_MATERIALITY = {
    "low": "Can review later",
    "medium": "Worth reviewing",
    "high": "Review before relying on this",
    "critical": "Needs attention before acting",
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

    def build_all_items(
        self,
        *,
        profile_payload: Mapping[str, Any],
        profile_path: Path,
        plan_workspace: Any,
        recommendation_inbox: Any,
    ) -> list[ContextItem]:
        items: list[ContextItem] = []
        items.extend(self.build_profile_items(profile_payload=profile_payload, profile_path=profile_path))
        items.extend(self.build_plan_items(plan_workspace=plan_workspace))
        items.extend(self.build_recommendation_items(recommendation_inbox=recommendation_inbox))
        return items


class ContextIntelligenceService:
    def __init__(
        self,
        *,
        database_path: Path,
        financial_profile_store: Any,
        plan_workspace: Any,
        recommendation_inbox: Any,
        indexer: ContextIndexer | None = None,
    ):
        self.registry = ContextRegistry(database_path)
        self.financial_profile_store = financial_profile_store
        self.plan_workspace = plan_workspace
        self.recommendation_inbox = recommendation_inbox
        self.indexer = indexer or ContextIndexer()

    @classmethod
    def from_settings(
        cls,
        settings: Any,
        *,
        financial_profile_store: Any,
        plan_workspace: Any,
        recommendation_inbox: Any,
    ) -> "ContextIntelligenceService":
        return cls(
            database_path=settings.durable_storage_dir / "context_index.db",
            financial_profile_store=financial_profile_store,
            plan_workspace=plan_workspace,
            recommendation_inbox=recommendation_inbox,
        )

    def rebuild_registry(self) -> dict[str, Any]:
        profile_payload = self.financial_profile_store.get()
        items = self.indexer.build_all_items(
            profile_payload=profile_payload,
            profile_path=self.financial_profile_store.profile_path,
            plan_workspace=self.plan_workspace,
            recommendation_inbox=self.recommendation_inbox,
        )
        report = self.registry.replace_all(items)
        return {
            **report,
            "status": self.registry.status(),
        }

    def get_status(self) -> dict[str, Any]:
        return self.registry.status()


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

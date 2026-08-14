"""BuildWealth domain adapters for explicit Copilot context references.

The generic resolver owns validation, workspace-scope verification, and prompt
framing. These adapters own the narrow Canonical State lookup for each
supported reference type. They intentionally return compact evidence snapshots
instead of whole Plan files, artifacts, or workspace stores.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from buildwealth_orchestrator.services.copilot_context_references import LookupMap


def build_workspace_context_reference_lookups(services: Any) -> LookupMap:
    """Bind reference lookups to one already-authorized workspace."""

    expected_workspace_id = str(services.record.id)

    def scoped(workspace_id: str) -> bool:
        return workspace_id == expected_workspace_id

    def envelope(
        *,
        reference_type: str,
        reference_id: str,
        label: str,
        as_of: Any,
        source_ref: str,
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": reference_type,
            "id": reference_id,
            "workspace_id": expected_workspace_id,
            "label": label,
            "as_of": str(as_of or "not_recorded"),
            "authority": "canonical_state",
            "source_ref": source_ref,
            "evidence": dict(evidence),
        }

    def plan_lookup(workspace_id: str, reference_id: str) -> Mapping[str, Any] | None:
        if not scoped(workspace_id):
            return None
        try:
            plan = services.plan_workspace.get_plan(reference_id)
        except FileNotFoundError:
            return None
        return envelope(
            reference_type="plan",
            reference_id=reference_id,
            label=str(plan.get("title") or reference_id),
            as_of=plan.get("updated_at"),
            source_ref=f"plan:{reference_id}",
            evidence={
                "description": plan.get("description") or "",
                "is_active": bool(plan.get("is_active")),
                "settings": plan.get("settings") or {},
                "artifact_count": len(plan.get("artifacts") or []),
                "saved_simulation_count": len(plan.get("saved_simulations") or []),
            },
        )

    def recommendation_lookup(
        workspace_id: str,
        reference_id: str,
    ) -> Mapping[str, Any] | None:
        if not scoped(workspace_id):
            return None
        try:
            item = services.recommendation_inbox.get(reference_id)
        except FileNotFoundError:
            return None
        return envelope(
            reference_type="recommendation",
            reference_id=reference_id,
            label=str(item.get("title") or reference_id),
            as_of=item.get("updated_at") or item.get("created_at"),
            source_ref=f"recommendation:{reference_id}",
            evidence={
                "status": item.get("status"),
                "priority": item.get("priority"),
                "recommendation_type": item.get("recommendation_type"),
                "detail": item.get("detail") or "",
                "plan_id": item.get("plan_id"),
                "score": item.get("score") or {},
                "action_payload": item.get("action_payload") or {},
            },
        )

    def saved_simulation_lookup(
        workspace_id: str,
        reference_id: str,
    ) -> Mapping[str, Any] | None:
        if not scoped(workspace_id):
            return None
        matches: list[tuple[str, dict[str, Any]]] = []
        for plan in services.plan_workspace.list_plans(limit=100):
            plan_id = str(plan.get("id") or "").strip()
            if not plan_id:
                continue
            try:
                simulation = services.plan_workspace.get_saved_simulation(
                    plan_id,
                    reference_id,
                )
            except FileNotFoundError:
                continue
            matches.append((plan_id, simulation))
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("Saved simulation ID is ambiguous in this workspace.")
        plan_id, simulation = matches[0]
        return envelope(
            reference_type="saved_simulation",
            reference_id=reference_id,
            label=str(simulation.get("title") or reference_id),
            as_of=simulation.get("created_at"),
            source_ref=f"plan:{plan_id}/saved_simulation:{reference_id}",
            evidence={
                "plan_id": plan_id,
                "source": simulation.get("source"),
                "summary": simulation.get("summary") or "",
                "notes": simulation.get("notes") or "",
                "input_payload": simulation.get("input_payload") or {},
                "result_payload": simulation.get("result_payload") or {},
                "immutable": bool(simulation.get("immutable")),
            },
        )

    def plan_artifact_lookup(
        workspace_id: str,
        reference_id: str,
    ) -> Mapping[str, Any] | None:
        if not scoped(workspace_id):
            return None
        matches: list[tuple[str, dict[str, Any]]] = []
        for plan in services.plan_workspace.list_plans(limit=100):
            plan_id = str(plan.get("id") or "").strip()
            if not plan_id:
                continue
            try:
                artifact = services.plan_workspace.read_artifact(
                    plan_id,
                    reference_id,
                )
            except FileNotFoundError:
                continue
            matches.append((plan_id, artifact))
        if not matches:
            return None
        if len(matches) != 1:
            raise ValueError("Plan artifact ID is ambiguous in this workspace.")
        plan_id, artifact = matches[0]
        return envelope(
            reference_type="plan_artifact",
            reference_id=reference_id,
            label=str(artifact.get("title") or reference_id),
            as_of=artifact.get("created_at"),
            source_ref=f"plan:{plan_id}/artifact:{reference_id}",
            evidence={
                "plan_id": plan_id,
                "file_name": artifact.get("file_name"),
                "content": artifact.get("content") or "",
            },
        )

    def holding_lookup(workspace_id: str, reference_id: str) -> Mapping[str, Any] | None:
        if not scoped(workspace_id):
            return None
        portfolio = services.portfolio_store.get_holdings()
        raw_holdings = portfolio.get("holdings")
        if not isinstance(raw_holdings, Mapping):
            return None
        direct = raw_holdings.get(reference_id)
        positions: list[dict[str, Any]]
        if isinstance(direct, Mapping):
            positions = [dict(direct)]
        else:
            positions = [
                dict(item)
                for item in raw_holdings.values()
                if isinstance(item, Mapping)
                and str(item.get("symbol") or "").strip() == reference_id
            ]
        if not positions:
            return None
        symbol = str(positions[0].get("symbol") or reference_id)
        value = sum(
            float(item.get("current_value") or item.get("value_usd") or 0)
            for item in positions
        )
        quantity = sum(float(item.get("quantity") or 0) for item in positions)
        cost_basis = sum(float(item.get("cost_basis") or 0) for item in positions)
        accounts = sorted(
            {
                str(item.get("account") or "").strip()
                for item in positions
                if str(item.get("account") or "").strip()
            }
        )
        return envelope(
            reference_type="holding",
            reference_id=reference_id,
            label=str(positions[0].get("name") or symbol),
            as_of=portfolio.get("updated_at"),
            source_ref=f"portfolio:holding:{reference_id}",
            evidence={
                "symbol": symbol,
                "position_count": len(positions),
                "accounts": accounts,
                "quantity": quantity,
                "current_value_usd": value,
                "cost_basis_usd": cost_basis,
                "base_currency": portfolio.get("base_currency") or "USD",
            },
        )

    return {
        "plan": plan_lookup,
        "recommendation": recommendation_lookup,
        "saved_simulation": saved_simulation_lookup,
        "plan_artifact": plan_artifact_lookup,
        "holding": holding_lookup,
    }

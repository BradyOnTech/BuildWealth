"""BuildWealth orchestration for read-only financial connections.

Plaid-specific payloads stop at the provider adapter. This service owns the
review boundary, encrypted token lifecycle, observed current state, and safe
disconnect ordering for one workspace.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from buildwealth_orchestrator.clients.financial_connections import (
    ErrorDisposition,
    FinancialConnectionProvider,
    InvestmentHoldingsSnapshot,
    ProviderAccount,
    ProviderSecurity,
)
from buildwealth_orchestrator.services.financial_connections import (
    financial_connection_access_token_key,
)
from buildwealth_orchestrator.services.connection_change_policy import (
    evaluate_connection_changes,
)


class FinancialConnectionServiceError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FinancialConnectionService:
    def __init__(self, *, provider: FinancialConnectionProvider, services: Any, control_plane: Any):
        self.provider = provider
        self.services = services
        self.control_plane = control_plane
        self.store = services.financial_connection_store

    def list_connections(self) -> dict[str, Any]:
        readiness = self.provider.configuration_readiness()
        secret_boundary_ready = self._production_secret_boundary_ready(readiness.environment)
        connections = self.store.list_connections()
        status_counts: dict[str, int] = {}
        enabled_products: dict[str, int] = {}
        for connection in connections:
            status = str(connection.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
            if status not in {"disconnected", "disconnect_pending"}:
                for product in connection.get("consented_products") or []:
                    name = str(product)
                    enabled_products[name] = enabled_products.get(name, 0) + 1
        return {
            "enabled": readiness.enabled,
            "configured": readiness.configured and secret_boundary_ready,
            "provider": readiness.provider,
            "readiness": {
                "environment": readiness.environment,
                "missing_settings": list(readiness.missing_settings)
                + ([] if secret_boundary_ready else ["BUILDWEALTH_SECRET_KEY_OR_FILE"]),
            },
            "inventory": {
                "total_items": len(connections),
                "active_items": status_counts.get("active", 0),
                "potentially_billable_items": sum(
                    count
                    for status, count in status_counts.items()
                    if status not in {"disconnected"}
                ),
                "attention_items": sum(
                    status_counts.get(status, 0)
                    for status in ("pending_review", "needs_attention", "error", "disconnect_pending")
                ),
                "status_counts": status_counts,
                "enabled_products": enabled_products,
                "pricing_note": "Plaid contract pricing is external; review this Item inventory against the monthly invoice.",
            },
            "items": [self._public_connection(row) for row in connections],
        }

    async def create_link_token(self, *, user_id: str) -> dict[str, Any]:
        self._require_ready()
        session = await self.provider.create_link_token(user_id=self._stable_user_id(user_id))
        return {
            "provider": self.provider.provider,
            "link_token": session.link_token,
            "expires_at": session.expires_at,
        }

    async def exchange_public_token(
        self,
        *,
        user_id: str,
        public_token: str,
        institution: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self._require_ready()
        institution = institution if isinstance(institution, dict) else {}
        institution_id = str(institution.get("institution_id") or "").strip()
        if institution_id:
            duplicate = next(
                (
                    row
                    for row in self.store.list_connections()
                    if str(row.get("institution_id") or "") == institution_id
                    and row.get("status") != "disconnected"
                ),
                None,
            )
            if duplicate is not None:
                raise FinancialConnectionServiceError(
                    "DUPLICATE_INSTITUTION_CONNECTION",
                    "This institution is already connected for the household. Repair or manage the existing connection instead.",
                    status_code=409,
                )
        exchange = await self.provider.exchange_public_token(public_token)
        existing = self.control_plane.lookup_financial_connection_index(
            provider=self.provider.provider,
            provider_item_id=exchange.provider_item_id,
        )
        if existing is not None:
            try:
                await self.provider.remove_item(exchange.access_token)
            except Exception:
                pass
            raise FinancialConnectionServiceError(
                "DUPLICATE_PROVIDER_ITEM",
                "This institution connection already exists. Repair or extend the existing connection instead.",
                status_code=409,
            )

        connection_id = f"conn_{uuid.uuid4().hex[:16]}"
        token_key = financial_connection_access_token_key(
            provider=self.provider.provider,
            connection_id=connection_id,
        )
        # Persist the credential before any other remote read. It is never put
        # into metadata, reports, exceptions, or response payloads.
        self.services.secret_store.set_secret(token_key, exchange.access_token)
        base_connection: dict[str, Any] | None = None
        try:
            base_connection = self.store.upsert_connection(
                {
                    "connection_id": connection_id,
                    "provider": self.provider.provider,
                    "workspace_id": self.services.context.workspace_id,
                    "connected_by_user_id": user_id,
                    "provider_item_id": exchange.provider_item_id,
                    "institution_id": institution.get("institution_id"),
                    "institution_name": institution.get("name"),
                    "status": "pending_review",
                    "environment": self.provider.configuration_readiness().environment,
                    "consented_products": ["investments"],
                }
            )
            self.control_plane.register_financial_connection_index(
                provider=self.provider.provider,
                provider_item_id=exchange.provider_item_id,
                workspace_id=self.services.context.workspace_id,
                connection_id=connection_id,
            )
        except Exception:
            try:
                await self.provider.remove_item(exchange.access_token)
            except Exception:
                pass
            self.services.secret_store.remove_secret(token_key)
            if base_connection is not None:
                try:
                    self.store.update_connection(
                        connection_id,
                        {
                            "status": "disconnected",
                            "disconnected_at": _utc_now_iso(),
                            "remote_removed_at": _utc_now_iso(),
                            "last_error_code": "CONNECTION_SETUP_FAILED",
                            "last_error_message": "The provider connection was revoked after local setup failed.",
                        },
                    )
                except Exception:
                    pass
            raise

        try:
            item = await self.provider.get_item(exchange.access_token)
            snapshot = await self.provider.get_investment_holdings(exchange.access_token)
            connection = self.store.update_connection(
                connection_id,
                {
                    "institution_id": item.institution_id or base_connection.get("institution_id"),
                    "institution_name": base_connection.get("institution_name"),
                    "consented_products": list(item.products or item.billed_products or ("investments",)),
                    "consent_expiration_at": item.consent_expiration_at,
                    "last_attempted_sync_at": _utc_now_iso(),
                    "last_error_code": item.error_code,
                    "last_error_message": (
                        "The institution needs attention." if item.error_code else None
                    ),
                },
            )
            accounts, holdings = self._normalize_snapshot(snapshot, connection_id=connection_id)
            observed_at = _utc_now_iso()
            self.store.stage_observation(
                connection_id=connection_id,
                accounts=accounts,
                holdings=holdings,
                observed_at=observed_at,
                provider_payload_version="plaid-investments-v1",
            )
            self._write_suggestions(connection_id, accounts)
        except Exception as exc:
            self._record_provider_failure(connection_id, exc)
            self._audit("connection.link_failed", connection_id, outcome="error", metadata={"code": str(getattr(exc, "code", "PROVIDER_ERROR"))})
            raise

        self._audit("connection.linked", connection_id, actor_user_id=user_id)

        return {
            "connection": self._public_connection(connection),
            "preview": self.get_preview(connection_id),
        }

    def get_preview(self, connection_id: str) -> dict[str, Any]:
        connection = self.store.get_connection(connection_id)
        state = self.store.get_observation_state(connection_id)
        staged = state.get("staged") if isinstance(state.get("staged"), dict) else None
        current = state.get("current") if isinstance(state.get("current"), dict) else None
        snapshot = staged or current or {}
        suggestions = {
            row["provider_account_id"]: row
            for row in self.store.list_account_mappings(connection_id)
        }
        accounts = []
        for account in snapshot.get("accounts", []):
            mapping = suggestions.get(str(account.get("provider_account_id"))) or {}
            accounts.append(
                {
                    **account,
                    "suggested_buildwealth_account_id": mapping.get("buildwealth_account_id"),
                    "suggested_match": (
                        {
                            "buildwealth_account_id": mapping.get("buildwealth_account_id"),
                            "reason": "the account name or masked identifier matches",
                        }
                        if mapping.get("buildwealth_account_id")
                        else None
                    ),
                    "match_status": mapping.get("match_status") or "suggested",
                }
            )
        return {
            "connection_id": connection_id,
            "status": connection["status"],
            "institution_name": connection.get("institution_name"),
            "accounts": accounts,
            "buildwealth_accounts": [
                {
                    "id": row.get("id"),
                    "name": row.get("name"),
                    "type": row.get("type"),
                    "currency": row.get("currency"),
                }
                for row in self.services.portfolio_store.get_accounts()
                if isinstance(row, dict) and row.get("id")
            ],
            "holdings_summary": {
                "count": len(snapshot.get("holdings", [])),
                "institution_value": round(
                    sum(float(row.get("institution_value") or 0.0) for row in snapshot.get("holdings", [])),
                    2,
                ),
            },
        }

    async def activate_connection(
        self,
        *,
        connection_id: str,
        accounts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        connection = self.store.get_connection(connection_id)
        if connection["status"] not in {"pending_review", "active"}:
            raise FinancialConnectionServiceError(
                "CONNECTION_NOT_REVIEWABLE", "This connection cannot be activated in its current state.", status_code=409
            )
        state = self.store.get_observation_state(connection_id)
        staged = state.get("staged")
        if not isinstance(staged, dict):
            if connection["status"] == "active":
                return {"connection": self._public_connection(connection), "report": {"idempotent": True}}
            raise FinancialConnectionServiceError("PREVIEW_NOT_READY", "Connection preview is not ready.", status_code=409)

        staged_accounts = {
            str(row.get("provider_account_id")): dict(row)
            for row in staged.get("accounts", [])
            if isinstance(row, dict)
        }
        selected_ids: set[str] = set()
        validated: list[tuple[dict[str, Any], dict[str, Any], bool, str]] = []
        portfolio_accounts = {
            str(row.get("id")): row
            for row in self.services.portfolio_store.get_accounts()
            if isinstance(row, dict) and row.get("id")
        }
        requested_targets: set[str] = set()
        for selection in accounts:
            provider_account_id = str(selection.get("provider_account_id") or "").strip()
            if not provider_account_id or provider_account_id not in staged_accounts:
                raise FinancialConnectionServiceError("INVALID_ACCOUNT_SELECTION", "An account selection is not part of this preview.")
            if provider_account_id in selected_ids:
                raise FinancialConnectionServiceError("DUPLICATE_ACCOUNT_SELECTION", "Each preview account may be selected once.")
            selected_ids.add(provider_account_id)
            include = bool(selection.get("include", True))
            requested_account_id = str(selection.get("buildwealth_account_id") or "").strip()
            observed_account = staged_accounts[provider_account_id]
            if include and not self._is_phase_one_investment_account(observed_account):
                raise FinancialConnectionServiceError(
                    "UNSUPPORTED_ACCOUNT_TYPE",
                    "Only investment accounts can be activated in this version.",
                    status_code=409,
                )
            if include and requested_account_id:
                target = portfolio_accounts.get(requested_account_id)
                if target is None:
                    raise FinancialConnectionServiceError("ACCOUNT_NOT_FOUND", "The selected BuildWealth account was not found.", status_code=404)
                if requested_account_id in requested_targets:
                    raise FinancialConnectionServiceError(
                        "DUPLICATE_ACCOUNT_TARGET",
                        "Two connected accounts cannot be merged into the same BuildWealth account.",
                        status_code=409,
                    )
                metadata = target.get("provider_metadata")
                if isinstance(metadata, dict) and (
                    str(metadata.get("connection_id") or "") != connection_id
                    or str(metadata.get("provider_account_id") or "") != provider_account_id
                ):
                    raise FinancialConnectionServiceError(
                        "ACCOUNT_ALREADY_CONNECTED",
                        "That BuildWealth account already belongs to another connection.",
                        status_code=409,
                    )
                requested_targets.add(requested_account_id)
            validated.append(
                (selection, staged_accounts[provider_account_id], include, requested_account_id)
            )
        if selected_ids != set(staged_accounts):
            raise FinancialConnectionServiceError(
                "INCOMPLETE_ACCOUNT_REVIEW",
                "Review every account in the preview before activation.",
            )

        account_ids: dict[str, str] = {}
        mapping_rows: list[dict[str, Any]] = []
        created_count = 0
        confirmed_count = 0
        ignored_count = 0
        observed_at = str(staged.get("observed_at") or _utc_now_iso())
        for selection, observed, include, requested_account_id in validated:
            provider_account_id = str(selection.get("provider_account_id") or "").strip()
            if not include:
                ignored_count += 1
                mapping_rows.append(
                    self._mapping_payload(connection_id, observed, None, "ignored")
                )
                continue
            if requested_account_id:
                buildwealth_account_id = requested_account_id
                match_status = "confirmed"
                confirmed_count += 1
            else:
                created = self.services.portfolio_store.add_account(
                    name=str(observed.get("name") or observed.get("official_name") or "Connected account"),
                    account_type=self._buildwealth_account_type(str(observed.get("subtype") or "")),
                    currency=str(observed.get("currency") or "USD"),
                    match_existing_name=False,
                )
                buildwealth_account_id = str(created["id"])
                match_status = "created"
                created_count += 1
            account_ids[provider_account_id] = buildwealth_account_id
            self.services.portfolio_store.attach_provider_account_mapping(
                buildwealth_account_id,
                provider=self.provider.provider,
                connection_id=connection_id,
                provider_account_id=provider_account_id,
                institution_id=connection.get("institution_id"),
                institution_name=connection.get("institution_name"),
                provider_name=observed.get("name"),
                provider_official_name=observed.get("official_name"),
                provider_type=observed.get("type"),
                provider_subtype=observed.get("subtype"),
                mask=observed.get("mask"),
                last_observed_at=observed_at,
            )
            mapping_rows.append(
                self._mapping_payload(
                    connection_id, observed, buildwealth_account_id, match_status
                )
            )

        self.store.replace_account_mappings(connection_id, mapping_rows)

        included_accounts = []
        for row in staged.get("accounts", []):
            provider_id = str(row.get("provider_account_id") or "")
            if provider_id in account_ids:
                included_accounts.append({**row, "buildwealth_account_id": account_ids[provider_id]})
        included_holdings = []
        for row in staged.get("holdings", []):
            provider_id = str(row.get("provider_account_id") or "")
            if provider_id in account_ids:
                included_holdings.append({**row, "buildwealth_account_id": account_ids[provider_id]})
        unmapped_security_count = self._review_unmapped_securities(
            connection,
            included_holdings,
        )
        promoted_stage = self.store.stage_observation(
            connection_id=connection_id,
            accounts=included_accounts,
            holdings=included_holdings,
            observed_at=observed_at,
            provider_payload_version=str(staged.get("provider_payload_version") or "plaid-investments-v1"),
        )
        self.store.promote_staged_observation(
            connection_id,
            expected_snapshot_id=promoted_stage["snapshot_id"],
        )
        now = _utc_now_iso()
        connection = self.store.update_connection(
            connection_id,
            {
                "status": "active",
                "last_attempted_sync_at": now,
                "last_successful_sync_at": now,
                "last_error_code": None,
                "last_error_message": None,
            },
        )
        report = {
            "report_id": f"connection_report_{uuid.uuid4().hex[:16]}",
            "connection_id": connection_id,
            "action": "activated",
            "created_at": now,
            "accounts_created": created_count,
            "accounts_confirmed": confirmed_count,
            "accounts_ignored": ignored_count,
            "holdings_activated": len(included_holdings),
            "unmapped_securities": unmapped_security_count,
        }
        if hasattr(self.store, "create_connection_report"):
            report = self.store.create_connection_report(report)
        self._audit(
            "connection.activated",
            connection_id,
            metadata={"accounts": created_count + confirmed_count, "holdings": len(included_holdings)},
        )
        return {"connection": self._public_connection(connection), "report": report}

    async def create_update_link_token(self, *, connection_id: str, user_id: str) -> dict[str, Any]:
        connection = self.store.get_connection(connection_id)
        token = self._access_token(connection)
        session = await self.provider.create_link_token(
            user_id=self._stable_user_id(user_id), access_token=token
        )
        self.store.create_connection_report(
            {
                "report_id": f"connection_report_{uuid.uuid4().hex[:16]}",
                "connection_id": connection_id,
                "action": "repair_started",
                "created_at": _utc_now_iso(),
                "warnings": [],
            }
        )
        self._audit("connection.repair_started", connection_id, actor_user_id=user_id)
        return {"provider": self.provider.provider, "link_token": session.link_token, "expires_at": session.expires_at}

    async def sync_connection(self, *, connection_id: str, trigger: str) -> dict[str, Any]:
        connection = self.store.get_connection(connection_id)
        if connection["status"] not in {"active", "needs_attention", "error"}:
            raise FinancialConnectionServiceError("CONNECTION_NOT_ACTIVE", "Only active connections can be updated.", status_code=409)
        run = self.store.start_sync_run(connection_id=connection_id, trigger=trigger)
        run_finished = False
        attempted_at = _utc_now_iso()
        self.store.update_connection(connection_id, {"last_attempted_sync_at": attempted_at})
        try:
            token = self._access_token(connection)
            item = await self.provider.get_item(token)
            snapshot = await self.provider.get_investment_holdings(token)
            accounts, holdings = self._normalize_snapshot(snapshot, connection_id=connection_id)
            mappings = {row["provider_account_id"]: row for row in self.store.list_account_mappings(connection_id)}
            accounts = [
                {**row, "buildwealth_account_id": (mappings.get(row["provider_account_id"]) or {}).get("buildwealth_account_id")}
                for row in accounts
                if (mappings.get(row["provider_account_id"]) or {}).get("match_status") in {"confirmed", "created"}
            ]
            holdings = [
                {**row, "buildwealth_account_id": (mappings.get(row["provider_account_id"]) or {}).get("buildwealth_account_id")}
                for row in holdings
                if (mappings.get(row["provider_account_id"]) or {}).get("match_status") in {"confirmed", "created"}
            ]
            before = self.store.get_observation_state(connection_id).get("current")
            observed_at = _utc_now_iso()
            staged = self.store.stage_observation(
                connection_id=connection_id,
                accounts=accounts,
                holdings=holdings,
                observed_at=observed_at,
                provider_payload_version="plaid-investments-v1",
            )
            self.store.promote_staged_observation(connection_id, expected_snapshot_id=staged["snapshot_id"])
            summary = evaluate_connection_changes(before, staged)
            warnings = self._create_review_items(connection, summary)
            self.store.finish_sync_run(
                run["sync_run_id"],
                outcome="succeeded",
                provider_request_ids=[value for value in (item.request_id, snapshot.request_id) if value],
                counts={"accounts": len(accounts), "holdings": len(holdings)},
                warnings=warnings,
            )
            run_finished = True
            connection = self.store.update_connection(
                connection_id,
                {
                    "status": "needs_attention" if item.error_code else "active",
                    "last_successful_sync_at": observed_at,
                    "last_error_code": item.error_code,
                    "last_error_message": "The institution needs attention." if item.error_code else None,
                },
            )
            report = self.store.create_connection_report(
                {
                    "report_id": f"connection_report_{uuid.uuid4().hex[:16]}",
                    "connection_id": connection_id,
                    "action": f"sync:{trigger}",
                    "created_at": observed_at,
                    "holdings_activated": len(holdings),
                    "warnings": warnings,
                }
            )
            self._audit(
                "connection.synced",
                connection_id,
                metadata={"trigger": trigger, "accounts": len(accounts), "holdings": len(holdings)},
            )
            return {
                "connection": self._public_connection(connection),
                "change_summary": summary,
                "report": report,
            }
        except Exception as exc:
            error_code = getattr(exc, "code", "SYNC_FAILED")
            if not run_finished:
                try:
                    self.store.finish_sync_run(
                        run["sync_run_id"], outcome="failed", error_code=error_code
                    )
                except Exception:
                    pass
            self._record_provider_failure(connection_id, exc)
            self._audit(
                "connection.sync_failed",
                connection_id,
                outcome="error",
                metadata={"trigger": trigger, "code": str(error_code)},
            )
            raise

    def disconnect_preview(self, connection_id: str) -> dict[str, Any]:
        connection = self.store.get_connection(connection_id)
        state = self.store.get_observation_state(connection_id)
        current = state.get("current") if isinstance(state.get("current"), dict) else {}
        account_count = len(current.get("accounts", []))
        holding_count = len(current.get("holdings", []))
        return {
            "connection_id": connection_id,
            "institution_name": connection.get("institution_name"),
            "choices": ["keep_frozen", "remove_connected_data"],
            "affected_counts": {
                "accounts": account_count,
                "holdings": holding_count,
            },
            "account_count": account_count,
            "holding_count": holding_count,
        }

    async def disconnect_connection(self, *, connection_id: str, retention: str) -> dict[str, Any]:
        if retention not in {"keep_frozen", "remove_connected_data"}:
            raise FinancialConnectionServiceError("INVALID_RETENTION", "Unsupported disconnect retention choice.")
        connection = self.store.get_connection(connection_id)
        if connection["status"] == "disconnected":
            return {"connection": self._public_connection(connection), "retention": retention, "remote_access_removed": True, "idempotent": True}
        connection = self.store.update_connection(
            connection_id,
            {
                "status": "disconnect_pending",
                "disconnect_retention": retention,
            },
        )
        if not connection.get("remote_removed_at"):
            started_at = connection.get("remote_removal_started_at") or _utc_now_iso()
            connection = self.store.update_connection(
                connection_id,
                {"remote_removal_started_at": started_at},
            )
            token = self._access_token(connection)
            try:
                removal = await self.provider.remove_item(token)
                if not removal.removed:
                    raise FinancialConnectionServiceError("REMOTE_REMOVAL_UNCONFIRMED", "The provider did not confirm removal.", status_code=502)
                connection = self.store.update_connection(
                    connection_id,
                    {
                        "remote_removed_at": _utc_now_iso(),
                        "remote_removal_request_id": removal.request_id or None,
                    },
                )
            except Exception as exc:
                # If the process died after Plaid removed the Item but before
                # the receipt was persisted, Plaid reports the old token as
                # invalid on retry. A recorded removal attempt makes that
                # terminal response safe to treat as already removed.
                if (
                    str(getattr(exc, "code", "")) == "INVALID_ACCESS_TOKEN"
                    and connection.get("remote_removal_started_at")
                ):
                    connection = self.store.update_connection(
                        connection_id,
                        {"remote_removed_at": _utc_now_iso()},
                    )
                else:
                    self._record_provider_failure(connection_id, exc, keep_status="disconnect_pending")
                    raise
        self.services.secret_store.remove_secret(
            financial_connection_access_token_key(provider=self.provider.provider, connection_id=connection_id)
        )
        self.control_plane.remove_financial_connection_index(
            provider=self.provider.provider,
            provider_item_id=connection["provider_item_id"],
            workspace_id=self.services.context.workspace_id,
            connection_id=connection_id,
        )
        mappings = self.store.list_account_mappings(connection_id)
        if retention == "remove_connected_data":
            for mapping in mappings:
                account_id = mapping.get("buildwealth_account_id")
                if account_id:
                    if mapping.get("match_status") == "created":
                        self.services.portfolio_store.remove_provider_created_account(
                            account_id,
                            connection_id=connection_id,
                            provider_account_id=mapping["provider_account_id"],
                        )
                    else:
                        self.services.portfolio_store.detach_provider_account_mapping(
                            account_id,
                            connection_id=connection_id,
                            provider_account_id=mapping["provider_account_id"],
                        )
                self.store.remove_account_mapping(
                    connection_id=connection_id,
                    provider_account_id=mapping["provider_account_id"],
                )
            self.store.delete_observations(connection_id)
        now = _utc_now_iso()
        connection = self.store.update_connection(
            connection_id,
            {
                "status": "disconnected",
                "disconnected_at": now,
                "disconnect_retention": retention,
                "last_error_code": None,
                "last_error_message": None,
            },
        )
        report = self.store.create_connection_report(
            {
                "report_id": f"connection_report_{uuid.uuid4().hex[:16]}",
                "connection_id": connection_id,
                "action": f"disconnected:{retention}",
                "created_at": now,
                "warnings": [],
            }
        )
        self._audit(
            "connection.disconnected",
            connection_id,
            metadata={"retention": retention},
        )
        return {
            "connection": self._public_connection(connection),
            "retention": retention,
            "remote_access_removed": True,
            "report": report,
        }

    def _require_ready(self) -> None:
        readiness = self.provider.configuration_readiness()
        if not readiness.enabled:
            raise FinancialConnectionServiceError("PROVIDER_DISABLED", "Financial connections are disabled.", status_code=503)
        if not readiness.configured:
            raise FinancialConnectionServiceError("PROVIDER_NOT_CONFIGURED", "Financial connections are not configured.", status_code=503)
        if not self._production_secret_boundary_ready(readiness.environment):
            raise FinancialConnectionServiceError(
                "PRODUCTION_SECRET_KEY_NOT_EXTERNAL",
                "Production financial connections require BUILDWEALTH_SECRET_KEY or BUILDWEALTH_SECRET_KEY_FILE outside the data directory.",
                status_code=503,
            )

    def _production_secret_boundary_ready(self, environment: str) -> bool:
        if environment != "production":
            return True
        return str(getattr(self.services, "secret_key_source", "data_dir")) in {
            "env",
            "file_override",
        }

    def _audit(
        self,
        action: str,
        connection_id: str,
        *,
        actor_user_id: str | None = None,
        outcome: str = "ok",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        try:
            context = self.services.context
            self.control_plane.record_audit_event(
                action=action,
                actor_user_id=actor_user_id or getattr(context, "user_id", None),
                organization_id=getattr(context, "organization_id", None),
                workspace_id=getattr(context, "workspace_id", None),
                target_type="financial_connection",
                target_id=connection_id,
                outcome=outcome,
                metadata_json=json.dumps(metadata or {}, sort_keys=True),
            )
        except Exception:
            pass

    def _stable_user_id(self, user_id: str) -> str:
        return f"{self.services.context.workspace_id}:{str(user_id).strip()}"

    def _access_token(self, connection: dict[str, Any]) -> str:
        token = self.services.secret_store.get_secret(
            financial_connection_access_token_key(provider=connection["provider"], connection_id=connection["connection_id"])
        )
        if not token:
            raise FinancialConnectionServiceError("ACCESS_TOKEN_MISSING", "The connection credential is unavailable. Reconnect the institution.", status_code=409)
        return token

    def _normalize_snapshot(self, snapshot: InvestmentHoldingsSnapshot, *, connection_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        observed_at = _utc_now_iso()
        account_ids = [row.provider_account_id for row in snapshot.accounts]
        security_ids = [row.provider_security_id for row in snapshot.securities]
        if not account_ids or len(account_ids) != len(set(account_ids)):
            raise FinancialConnectionServiceError(
                "INCOMPLETE_SNAPSHOT",
                "The institution returned an incomplete account snapshot. The prior valid snapshot was preserved.",
                status_code=502,
            )
        if len(security_ids) != len(set(security_ids)):
            raise FinancialConnectionServiceError(
                "INCOMPLETE_SNAPSHOT",
                "The institution returned duplicate security details. The prior valid snapshot was preserved.",
                status_code=502,
            )
        account_id_set = set(account_ids)
        holding_keys: set[tuple[str, str]] = set()
        for holding in snapshot.holdings:
            key = (holding.provider_account_id, holding.provider_security_id)
            if holding.provider_account_id not in account_id_set or key in holding_keys:
                raise FinancialConnectionServiceError(
                    "INCOMPLETE_SNAPSHOT",
                    "The institution returned inconsistent holding details. The prior valid snapshot was preserved.",
                    status_code=502,
                )
            holding_keys.add(key)
        securities = {row.provider_security_id: row for row in snapshot.securities}
        cash_by_account: dict[str, float] = {}
        holdings: list[dict[str, Any]] = []
        for row in snapshot.holdings:
            security = securities.get(row.provider_security_id)
            if security is None:
                raise FinancialConnectionServiceError("INCOMPLETE_HOLDINGS", "The institution returned a holding without its security details.", status_code=502)
            if security.is_cash_equivalent:
                cash_by_account[row.provider_account_id] = cash_by_account.get(row.provider_account_id, 0.0) + row.institution_value
            identifier = self._security_identifier(security)
            holdings.append(
                {
                    "connection_id": connection_id,
                    "provider_account_id": row.provider_account_id,
                    "buildwealth_account_id": None,
                    "provider_security_id": row.provider_security_id,
                    "symbol_or_identifier": identifier,
                    "name": security.name,
                    "quantity": row.quantity,
                    "institution_price": row.institution_price,
                    "institution_value": row.institution_value,
                    "cost_basis": row.cost_basis,
                    "currency": row.iso_currency_code or security.iso_currency_code or "USD",
                    "observed_at": observed_at,
                    "provider_payload_version": "plaid-investments-v1",
                }
            )
        accounts = [self._normalize_account(row, connection_id, observed_at, cash_by_account.get(row.provider_account_id)) for row in snapshot.accounts]
        return accounts, holdings

    @staticmethod
    def _normalize_account(account: ProviderAccount, connection_id: str, observed_at: str, cash_balance: float | None) -> dict[str, Any]:
        return {
            "connection_id": connection_id,
            "provider_account_id": account.provider_account_id,
            "buildwealth_account_id": None,
            "name": account.name,
            "official_name": account.official_name,
            "type": account.account_type,
            "subtype": account.account_subtype,
            "mask": account.mask,
            "currency": account.iso_currency_code or account.unofficial_currency_code or "USD",
            "current_balance": account.current_balance,
            "available_balance": account.available_balance,
            "cash_balance": cash_balance,
            "observed_at": observed_at,
        }

    @staticmethod
    def _security_identifier(security: ProviderSecurity) -> str:
        for value in (security.ticker_symbol, security.cusip, security.isin, security.sedol):
            text = str(value or "").strip().upper()
            if text:
                return text
        return f"PLAID:{security.provider_security_id}"

    def _write_suggestions(self, connection_id: str, accounts: list[dict[str, Any]]) -> None:
        portfolio_accounts = self.services.portfolio_store.get_accounts()
        for account in accounts:
            suggested = self._suggest_account(account, portfolio_accounts)
            self.store.upsert_account_mapping(
                self._mapping_payload(connection_id, account, suggested, "suggested")
            )

    @staticmethod
    def _suggest_account(observed: dict[str, Any], candidates: list[dict[str, Any]]) -> str | None:
        observed_name = str(observed.get("name") or "").strip().lower()
        observed_mask = str(observed.get("mask") or "").strip()
        matches = []
        for candidate in candidates:
            metadata = candidate.get("provider_metadata") if isinstance(candidate.get("provider_metadata"), dict) else {}
            name_match = observed_name and str(candidate.get("name") or "").strip().lower() == observed_name
            mask_match = observed_mask and str(metadata.get("mask") or "") == observed_mask
            if name_match or mask_match:
                matches.append(str(candidate.get("id") or ""))
        unique = [value for value in dict.fromkeys(matches) if value]
        return unique[0] if len(unique) == 1 else None

    @staticmethod
    def _mapping_payload(connection_id: str, observed: dict[str, Any], buildwealth_account_id: str | None, status: str) -> dict[str, Any]:
        return {
            "connection_id": connection_id,
            "provider_account_id": observed.get("provider_account_id"),
            "buildwealth_account_id": buildwealth_account_id,
            "match_status": status,
            "provider_name": observed.get("name"),
            "provider_official_name": observed.get("official_name"),
            "provider_type": observed.get("type"),
            "provider_subtype": observed.get("subtype"),
            "mask": observed.get("mask"),
            "currency": observed.get("currency"),
            "last_observed_at": observed.get("observed_at"),
        }

    @staticmethod
    def _buildwealth_account_type(subtype: str) -> str:
        normalized = subtype.strip().lower()
        if normalized in {"401k", "403b", "457b", "pension", "retirement"}:
            return "401k"
        if normalized in {"ira", "traditional ira"}:
            return "ira"
        if normalized in {"roth", "roth ira"}:
            return "roth_ira"
        if normalized in {"529", "education savings account"}:
            return "529"
        if normalized == "hsa":
            return "hsa"
        return "taxable"

    @staticmethod
    def _is_phase_one_investment_account(observed: dict[str, Any]) -> bool:
        return str(observed.get("type") or "").strip().lower() == "investment"

    def _record_provider_failure(self, connection_id: str, exc: Exception, *, keep_status: str | None = None) -> None:
        disposition = getattr(exc, "disposition", None)
        if keep_status:
            status = keep_status
        elif disposition == ErrorDisposition.REPAIRABLE:
            status = "needs_attention"
        elif disposition == ErrorDisposition.RETRYABLE:
            try:
                current_status = str(self.store.get_connection(connection_id).get("status") or "active")
            except Exception:
                current_status = "active"
            status = (
                current_status
                if current_status in {"active", "needs_attention", "pending_review"}
                else "active"
            )
        else:
            status = "error"
        code = str(getattr(exc, "code", "PROVIDER_ERROR"))
        message = str(getattr(exc, "message", "The financial connection could not be updated."))
        self.store.update_connection(connection_id, {"status": status, "last_attempted_sync_at": _utc_now_iso(), "last_error_code": code, "last_error_message": message[:240]})

    def _create_review_items(self, connection: dict[str, Any], summary: dict[str, Any]) -> list[str]:
        warnings = []
        if summary.get("review_required"):
            warnings.append("Connected holdings changed; review the latest observation.")
            try:
                self.services.recommendation_inbox.create(
                    title=f"Review changes from {connection.get('institution_name') or 'connected account'}",
                    detail="A connected holding appeared, disappeared, or changed quantity. The latest valid observation was applied and the prior snapshot was preserved.",
                    priority="medium",
                    recommendation_type="portfolio_review",
                    source="financial_connection",
                    action_payload={"connection_id": connection["connection_id"], "href": "#import"},
                )
            except Exception:
                pass
        return warnings

    def _review_unmapped_securities(
        self,
        connection: dict[str, Any],
        holdings: list[dict[str, Any]],
    ) -> int:
        registry = getattr(self.services, "asset_registry", None)
        unresolved: list[dict[str, Any]] = []
        for holding in holdings:
            identifier = str(holding.get("symbol_or_identifier") or "")
            resolved = None
            if registry is not None and not identifier.startswith("PLAID:"):
                try:
                    resolved = registry.detail(identifier)
                except Exception:
                    resolved = None
            if identifier.startswith("PLAID:") or (registry is not None and resolved is None):
                unresolved.append(holding)
        for holding in unresolved:
            try:
                self.services.recommendation_inbox.create(
                    title=f"Identify {holding.get('name') or 'a connected security'}",
                    detail=(
                        "This security arrived without an identifier BuildWealth can resolve. "
                        "Its provider value is preserved, but allocation and risk classification need review."
                    ),
                    priority="medium",
                    recommendation_type="asset_review",
                    source="financial_connection",
                    action_payload={
                        "connection_id": connection["connection_id"],
                        "provider_security_id": holding.get("provider_security_id"),
                        "href": "#portfolio",
                    },
                )
            except Exception:
                pass
        return len(unresolved)

    def _public_connection(self, connection: dict[str, Any]) -> dict[str, Any]:
        excluded = {"provider_item_id", "workspace_id"}
        public = {key: value for key, value in connection.items() if key not in excluded}
        try:
            public["account_count"] = len(
                [
                    row
                    for row in self.store.list_account_mappings(
                        connection["connection_id"]
                    )
                    if row.get("match_status") in {"confirmed", "created"}
                ]
            )
        except Exception:
            public["account_count"] = 0
        public["stale"] = connection.get("status") in {
            "needs_attention",
            "error",
            "disconnect_pending",
            "disconnected",
        }
        try:
            user = self.control_plane.get_user(connection["connected_by_user_id"])
            public["connected_by_name"] = (
                user.get("display_name") or user.get("name") or user.get("email")
            )
        except Exception:
            pass
        return public

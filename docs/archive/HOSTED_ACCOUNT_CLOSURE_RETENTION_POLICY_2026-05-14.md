# Hosted Account Closure and Retention Policy

**Date:** 2026-05-14

**Status:** First implementation policy. This is an engineering and product artifact, not legal advice.

## Purpose

BuildWealth needs a hosted-user account closure path before private beta users are invited. The important product boundary is:

- the hosted identity provider owns sign-in, password reset, MFA, passkeys, and provider-side identity lifecycle
- BuildWealth owns household workspace access, sessions, memberships, exports, encrypted provider secrets, backups, and audit records

This policy defines the first hosted closure implementation and what remains intentionally separate.

## User-Facing Language

Use **Close BuildWealth access** for the current hosted control.

Do not call the first implementation "delete my account" in the UI, because it does not yet erase workspace files, backups, audit events, or the hosted identity-provider user. It disables the BuildWealth account and revokes BuildWealth sessions.

Future destructive flows can use "Delete workspace data" or "Delete household data" after recovery windows, backup retention, and legal/privacy requirements are finalized.

Product/legal/privacy wording for the hosted UI and public policy pages is tracked in [Hosted Product, Legal, and Privacy Wording Draft](HOSTED_PRODUCT_LEGAL_PRIVACY_WORDING_DRAFT_2026-05-14.md).

## First Implementation

Hosted users can close their BuildWealth access from v2 Settings.

The flow:

1. User signs in through the hosted provider.
2. User opens Settings, Account & data.
3. User prepares an account export if they want a metadata copy first.
4. User types `close buildwealth access`.
5. BuildWealth verifies the active session, CSRF token, and `account.delete` permission.
6. BuildWealth marks the user `deleted`.
7. BuildWealth marks the user's memberships `inactive`.
8. BuildWealth revokes all active BuildWealth sessions for that user.
9. BuildWealth records an `account.hosted_access_closed` audit event.
10. BuildWealth leaves workspace files, backups, and audit records in place.

The hosted provider account is not deleted by this flow. If the provider offers self-service account deletion, that remains provider-managed until BuildWealth intentionally adds provider-specific lifecycle automation.

## Retained Data

The first implementation retains:

- workspace files
- backup archives and restore metadata
- audit events
- control-plane user row, with status `deleted`
- organization and workspace rows
- inactive membership rows
- operational records needed for security review or manual recovery

The account export removes password hashes and hosted provider subjects. It is safe to expose as user metadata, but it is not a complete workspace-data export.

## Not Yet Implemented

The current flow does not:

- delete financial workspace files
- delete encrypted provider secrets from retained workspace storage
- delete backups
- purge audit events
- anonymize the control-plane email address
- call Auth0 or another provider to delete the hosted identity
- define a legally reviewed retention duration
- provide a self-service undo/reactivation flow

These are launch items for the deeper deletion phase, not blockers for closing hosted access in private beta.

## Implementation Contract

Backend:

- `POST /api/account/hosted/close`
- requires cookie session
- requires CSRF header
- requires `account.delete`
- requires exact confirmation phrase `close buildwealth access`
- rejects local accounts; local accounts continue using `DELETE /api/account` with password confirmation
- calls `ControlPlaneStore.close_hosted_user_access`
- deletes the BuildWealth session cookie on success

Frontend:

- v2 Settings, Account & data
- visible only for provider-managed sign-in users
- placed after provider-managed security links and hosted readiness
- keeps export available before closure
- uses the plain action label `Close BuildWealth access`

Audit:

- action: `account.hosted_access_closed`
- target type: `user`
- metadata includes the hosted provider and the retention behavior

## Future Deletion Phase

Before shipping a true "delete my data" control, decide:

- recovery window length
- whether account email is anonymized immediately or after the recovery window
- whether one household owner can delete a shared household workspace
- how workspace backups are pruned
- how encrypted provider secrets are shredded
- what audit events must remain for abuse/security/legal review
- whether Copilot conversations are deleted with the workspace or retained as operational records
- whether imports and generated research packets are deleted with portfolio data
- how provider-side identity deletion is requested or delegated

Recommended product shape:

1. **Close BuildWealth access** disables account access now.
2. **Delete household data** becomes a separate destructive flow with export, recovery window, and final confirmation.
3. **Provider account deletion** remains provider-managed unless BuildWealth adds a reviewed provider-specific integration.

## Control-Plane Deletion Ledger

BuildWealth now has the database structure needed for a delayed destructive deletion flow.

Deletion requests are recorded in `account_data_deletion_requests` with:

- `status`: `pending`, `canceled`, `completed`, or `failed`
- `scope`: `workspace`, `household`, or `account`
- `requested_at`
- `purge_after`
- `canceled_at`
- `completed_at`
- `preview_json`
- `result_json`
- `failure_reason`

The control plane also tracks lifecycle timestamps on users, organizations, and workspaces:

- `deletion_requested_at`
- `purge_after`
- `deletion_completed_at`

When a deletion request is created, affected workspaces move to `pending_deletion`. Normal workspace resolution already requires `status = 'active'`, so pending workspaces are no longer available through ordinary app workflows. Canceling a pending request restores the affected workspace or household to `active`. Completing a request marks the affected records `deleted` after the purge worker has removed the filesystem data.

This ledger does not delete files by itself. It exists so preview, request, cancellation, and final purge can share one durable lifecycle record.

## Deletion Preview and Request API

BuildWealth now exposes the first dry-run deletion API layer:

- `GET /api/account/data-deletion/preview?scope=workspace`
- `GET /api/account/data-deletion/requests`
- `POST /api/account/data-deletion/request`
- `POST /api/account/data-deletion/{request_id}/cancel`

Preview responses include:

- affected workspace count
- per-workspace file counts and byte counts
- backup archive counts
- encrypted secret key names, never secret values
- deletion categories
- retention categories
- required confirmation phrase
- recovery window and `purge_after`

Requesting deletion records the preview snapshot into the deletion ledger and moves affected workspace records to `pending_deletion`. Canceling during the recovery window moves those records back to `active`.

## Settings UI

BuildWealth v2 Settings now exposes the deletion request workflow inside Account & data:

- choose deletion scope: current workspace, household data, or account data
- preview affected data before scheduling
- review workspace, file, byte, secret-key, and backup-archive counts
- see the recovery window and purge date
- type the confirmation phrase returned by the preview
- schedule deletion
- see pending deletion requests
- cancel pending deletion during the recovery window

The UI does not expose raw secret values. It can show secret key names so a user understands which provider keys are affected.

This is still not the final purge layer. Remaining work:

## Purge Worker

BuildWealth now has an irreversible purge worker service for due deletion requests.

The worker:

- reads pending deletion requests whose `purge_after` has passed
- resolves affected workspace records from the control plane
- refuses broad unsafe filesystem roots
- counts files, bytes, backup archives, and encrypted secret keys before deletion
- writes an empty shredded secrets file before removing the workspace tree
- removes the workspace root, including backup archives inside that workspace
- marks the deletion request `completed` with result JSON when all workspace purges succeed
- marks the deletion request `failed` with result JSON and `failure_reason` when any filesystem step fails
- records `account.data_deletion_completed` or `account.data_deletion_failed` audit events

The app exposes a callable helper, `purge_due_account_data_deletions`, and a maintenance CLI:

```bash
buildwealth-maintenance purge-due-account-data-deletions --pretty
```

For Docker Compose deployments, run the same job through the maintenance profile:

```bash
docker compose -f infra/docker-compose.yml --profile maintenance run --rm account-data-deletion-purge
```

Hosted deployments should schedule this command as a private maintenance job. It is not wired to a public user button.

Remaining work:

- hosted/legal/privacy review copy

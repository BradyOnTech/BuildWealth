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

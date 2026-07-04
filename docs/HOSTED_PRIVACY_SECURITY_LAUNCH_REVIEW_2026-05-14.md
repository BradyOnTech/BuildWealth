# Hosted Privacy and Security Launch Review

**Date:** 2026-05-14

**Status:** Draft launch checklist. This is an engineering and product review artifact, not legal advice.

## Purpose

BuildWealth is moving toward hosted identity, household workspaces, encrypted provider secrets, AI-assisted financial context, and user-owned financial records. Before real hosted users are invited, the product needs a plain-language privacy and security review that matches how the system actually works.

This document defines what must be reviewed, implemented, and verified before hosted launch.

## Data BuildWealth Handles

BuildWealth may store:

- account identity: email, display name, hosted provider subject, MFA/passkey status signals
- household profile: income, expenses, debts, goals, assumptions, tax-related planning inputs, retirement timeline
- portfolio data: holdings, accounts, transactions, prices, benchmarks, allocation rules, risk guardrails
- planning data: simulations, saved scenarios, contribution rules, withdrawal comparisons, assumptions, plan decisions
- research data: watchlist items, thesis notes, evidence packets, saved dossiers, review metadata
- Copilot data: conversation history, tool traces, context packets, drafted recommendations, profile updates, decision notes
- provider secrets: LLM/API keys stored in encrypted workspace secrets
- operational records: sessions, audit events, backups, restore previews, git activity, import reports

## Product Promises That Must Stay True

The hosted product should only make promises the implementation can support:

- Users sign into a private household workspace.
- Demo data stays separate from real household data.
- Provider keys are never returned in raw form after saving.
- Workspace financial data is scoped by authenticated user, active workspace, and membership role.
- Sensitive account actions require CSRF protection.
- Hosted password reset, MFA, and passkeys are managed by the configured identity provider.
- Account exports exclude password hashes and hosted provider subjects.
- Local account deactivation revokes sessions and disables memberships.
- Hosted account closure revokes BuildWealth sessions, disables memberships, and retains workspace files, backups, and audit records under the current retention policy.
- Secret-key rotation can be previewed and applied without exposing raw secrets.

## Required Launch Decisions

### Identity Provider

Recommended first private-beta provider: Auth0. See [Hosted Identity Provider Decision](./HOSTED_IDENTITY_PROVIDER_DECISION_2026-05-14.md).

Choose and document:

- provider name and tenant/environment
- redirect URI for hosted callback
- token auth method
- password reset URL
- MFA enrollment URL
- passkey enrollment URL
- account management URL
- hosted logout URL and post-logout redirect behavior
- email verification policy
- whether MFA is optional, encouraged, or required for hosted users
- how local development users migrate or link to hosted identities

### Data Retention

Define retention for:

- active user profile and workspace data
- deactivated accounts
- deleted workspaces
- backups
- audit events
- Copilot conversations
- import files and reports
- generated research packets

### User Controls

Before hosted launch, users should be able to:

- export account metadata
- export or download workspace data bundles
- remove provider keys
- deactivate local account access where applicable
- reach hosted account security controls
- reset demo data without affecting real data

Future hosted account deletion should define whether financial workspace files are immediately deleted, soft-deleted, or retained for a defined recovery window.

The current hosted closure policy is defined in [Hosted Account Closure and Retention Policy](./HOSTED_ACCOUNT_CLOSURE_RETENTION_POLICY_2026-05-14.md).

## Security Review Checklist

Before inviting real hosted users:

- [ ] Hosted identity provider configured in production tenant.
- [ ] Hosted provider readiness endpoint reports no blocked checks.
- [ ] Local password login disabled in hosted mode.
- [ ] Hosted callback tested with PKCE and one-time state.
- [ ] Hosted ID token validation tested for issuer, audience, expiry, nonce, allowed signing algorithm, and UserInfo subject matching.
- [ ] Hosted callback failures return users to the v2 sign-in screen with plain-language error copy.
- [ ] Hosted logout behavior is validated against the selected provider.
- [ ] Session cookie uses `HttpOnly`, `SameSite=Lax`, and `Secure` in hosted mode.
- [ ] Mutating cookie-auth routes require CSRF.
- [ ] Route tests prove workspace isolation for profile, portfolio, settings, Copilot, recommendations, backups, imports, and git actions.
- [ ] Provider keys are encrypted in workspace secrets and never stored in workspace settings JSON.
- [ ] Secret-key rotation preview/apply tested against hosted-like data.
- [ ] Backup restore is scoped to the active workspace.
- [ ] Account export excludes password hashes and hosted provider subjects.
- [ ] Audit events exist for hosted identity linking, hosted access closure, account deactivation, demo reset, and secret-key rotation.
- [ ] Production logs do not include raw provider keys, portfolio imports, Copilot prompts, or full financial profile payloads.

## AI and Financial Guidance Review

BuildWealth should keep user-facing language clear for non-experts:

- Call planning experiments "simulations" when the output is exploratory.
- Do not present a simulation as a real financial plan.
- Label AI outputs as drafts, reviews, or suggestions that the user can accept, reject, or edit.
- Show the facts and assumptions used for important recommendations.
- Use plain-language risk explanations instead of advisor jargon.
- Avoid language that implies a guaranteed outcome.

Before public hosted launch, review product copy with qualified counsel or compliance support.

## Privacy Policy Inputs

Draft public wording is now tracked in [Hosted Product, Legal, and Privacy Wording Draft](./HOSTED_PRODUCT_LEGAL_PRIVACY_WORDING_DRAFT_2026-05-14.md).
Hosted draft pages are exposed at `/privacy`, `/terms`, and `/ai-disclosure`.

A privacy policy should accurately describe:

- what data BuildWealth collects
- why the data is collected
- where data is stored
- how AI providers may be used
- how hosted identity is handled
- whether provider API keys are stored
- how users can export or delete data
- how long backups and audit logs are retained
- how users can contact the operator

## Open Items

- Create and validate the first Auth0 hosted tenant.
- Review and publish hosted product/legal/privacy wording.
- Choose legal operator name, privacy contact, terms contact, support path, jurisdiction, and minimum user age.
- Decide whether hosted MFA is optional or required.
- Replace the dependency-light local secret encryption primitive with KMS or a standard audited encryption library before production scale.
- Confirm whether no-sale/no-share, sensitive-data, vendor/subprocessor, AI-provider, and hosted identity-provider disclosures are sufficient for launch.

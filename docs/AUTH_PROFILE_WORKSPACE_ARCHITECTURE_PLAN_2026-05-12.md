# Auth, Profile, and Workspace Architecture Plan

**Date:** 2026-05-12

**Status:** Approved direction; implementation planning document.

## Purpose

BuildWealth is moving from a local single-user financial decision system into a private household workspace product. The next architecture step is to introduce authentication, user identity, household workspaces, profile ownership, encrypted provider secrets, and workspace-scoped data access before adding more user-facing depth.

This plan defines the target system and the implementation path. It should be used as the reference for future auth, profile, settings, data-isolation, and demo-data work.

## Decisions

1. BuildWealth will use a **household workspace** model.
2. The first auth implementation will be **BuildWealth-owned local auth** behind an auth-provider adapter.
3. Hosted auth providers may be added later, but route handlers and product logic must depend on BuildWealth's internal request context, not on a vendor-specific identity object.
4. LLM and provider API keys belong to the **workspace** by default.
5. Demo data will live in a dedicated **Demo Household** workspace with reset/delete controls.
6. Advisor/client sharing will be designed into the data model now, but hidden from the primary UI until needed.
7. Profile should be treated as the user's **Household Profile**, even if the current household has one member.
8. The v2 UI remains the only future product surface for this work.

## Product North Star

BuildWealth should feel like a private financial workspace, not a generic account dashboard. Authentication exists to protect and route a person's financial workspace. Profile exists to describe the household financial reality. Authorization exists to make sure every calculation, recommendation, import, Copilot answer, backup, export, and settings change uses the right workspace.

The user should experience this as:

- "This is my household's financial picture."
- "My data is separated from demo data and other users."
- "I can see which facts are confirmed, missing, stale, or need review."
- "Copilot and recommendations use the same reviewed data as the rest of the app."
- "I can reset demo data without touching real data."
- "Provider keys are saved securely and are never shown again after entry."

## Current State

BuildWealth currently runs as a local-first single-user app.

Important current code shapes:

- `services/orchestrator/src/buildwealth_orchestrator/main.py` creates process-global stores at import time.
- `services/orchestrator/src/buildwealth_orchestrator/settings.py` defines global data paths under `data/`.
- `UserSettingsStore` persists AI/provider settings to `data/settings/user_settings.json`.
- API keys are masked in API responses but stored locally in plaintext.
- `FinancialProfileStore` reads and writes `data/profile/financial_profile.json`.
- `PortfolioStore` reads and writes `data/portfolio/*.json`.
- `PlanWorkspace` reads and writes `data/plans`.
- `RecommendationInbox` reads and writes `data/recommendations/inbox.json`.
- `ConversationStore` reads and writes `data/conversations`.
- `ContextIntelligenceService` uses a local context index under `data/storage`.

This is acceptable for local single-user development, but it is not enough for real users, hosted access, shared households, demo workspaces, or advisor-ready permissions.

## Target Model

### Core Objects

**User**

Login identity for a real person.

Fields:

- `id`
- `email`
- `email_normalized`
- `display_name`
- `password_hash`
- `auth_provider`
- `auth_provider_subject`
- `mfa_enabled`
- `status`
- `created_at`
- `updated_at`
- `last_login_at`

Notes:

- First implementation uses local email/password auth.
- Hosted provider subjects are nullable until a hosted provider is added.
- A user can belong to multiple organizations later.

**Organization**

The owner container for people and workspaces.

Fields:

- `id`
- `name`
- `org_type`
- `status`
- `created_at`
- `updated_at`

Allowed `org_type` values:

- `household`
- `advisor_firm`

Initial UI exposes only household organizations. Advisor firm support is structural only at first.

**Membership**

Connects a user to an organization.

Fields:

- `id`
- `user_id`
- `organization_id`
- `role`
- `status`
- `invited_by_user_id`
- `created_at`
- `updated_at`

Initial roles:

- `owner`
- `member`
- `read_only`
- `advisor`
- `admin`

Initial UI exposes only `owner`. Other roles exist so future sharing does not require a data-model rewrite.

**Workspace**

The hard financial data boundary.

Fields:

- `id`
- `organization_id`
- `name`
- `workspace_type`
- `storage_mode`
- `storage_path`
- `database_path`
- `encryption_status`
- `backup_policy_id`
- `status`
- `created_at`
- `updated_at`

Allowed `workspace_type` values:

- `household`
- `demo`
- `client`

Initial workspace types:

- Real household workspace
- Demo household workspace

**Session**

Authenticated browser session.

Fields:

- `id`
- `user_id`
- `session_token_hash`
- `csrf_token_hash`
- `created_at`
- `last_seen_at`
- `expires_at`
- `revoked_at`
- `ip_hash`
- `user_agent_hash`

The raw session token should never be stored.

**Invitation**

Invite-only account and workspace sharing primitive.

Fields:

- `id`
- `organization_id`
- `workspace_id`
- `email`
- `role`
- `token_hash`
- `expires_at`
- `accepted_at`
- `created_by_user_id`
- `created_at`

Initial usage:

- Create first owner account.
- Later invite spouse/partner/read-only/advisor users.

**Audit Event**

Security and sensitive action trail.

Fields:

- `id`
- `actor_user_id`
- `organization_id`
- `workspace_id`
- `action`
- `target_type`
- `target_id`
- `outcome`
- `metadata_json`
- `created_at`

Examples:

- `auth.login_succeeded`
- `auth.login_failed`
- `workspace.created`
- `workspace.switched`
- `profile.updated`
- `settings.provider_key_saved`
- `settings.provider_key_removed`
- `demo_workspace.reset`
- `backup.created`
- `backup.restored`
- `export.created`

## Request Context

Every route that reads or writes financial data must resolve a `RequestContext` first.

Recommended shape:

```python
@dataclass(frozen=True)
class RequestContext:
    user_id: str
    organization_id: str
    workspace_id: str
    role: str
    permissions: frozenset[str]
    is_demo_workspace: bool
    auth_mode: str
```

The request context is responsible for:

- identifying the signed-in user
- resolving the selected workspace
- checking membership
- deriving permissions
- preventing cross-workspace reads
- giving route handlers the correct store factory

Routes should not reach into global financial stores.

## Auth Provider Strategy

### Initial Recommendation

Build local auth first, behind an adapter.

Recommended interface:

```python
class AuthProvider(Protocol):
    def create_user(self, email: str, password: str, display_name: str | None = None) -> AuthIdentity: ...
    def authenticate(self, email: str, password: str) -> AuthIdentity: ...
    def get_identity(self, provider_subject: str) -> AuthIdentity | None: ...
```

Initial implementation:

- `LocalAuthProvider`
- email/password
- Argon2 preferred, bcrypt acceptable
- secure password hashing
- invite-only registration
- session cookie auth

Future implementation:

- `OIDCAuthProvider`
- hosted provider subject mapping
- MFA/passkey support
- password reset through provider or email service

### Cookie and Session Policy

Use an HTTP-only secure session cookie.

Local development:

- `HttpOnly`
- `SameSite=Lax`
- `Secure=false` only on localhost

Hosted:

- `HttpOnly`
- `SameSite=Lax`
- `Secure=true`
- short-lived session with rolling renewal
- server-side session revocation

Mutating routes should require CSRF protection when cookie-based auth is active.

## Workspace Data Boundary

### Stage 1 Storage

Keep file-backed stores, but move them under workspace roots.

Target layout:

```text
data/
  control/
    control.db
  workspaces/
    ws_real_household/
      profile/
        financial_profile.json
      portfolio/
        accounts.json
        asset_metadata.json
        holdings.json
        transactions.json
        manual_prices.json
        risk_policy.json
      plans/
      recommendations/
        inbox.json
      imports/
        inbox/
        archive/
        workbench/
        reports/
      reports/
        portfolio_review_packets/
      conversations/
      storage/
        context_index.db
      settings/
        workspace_settings.json
      security/
        protection_policy.json
      today/
        review_checkpoint.json
    ws_demo_household/
      ...
```

The existing single-user `data/` directory should be migrated into a default household workspace.

### Stage 2 Storage

Move workspace Canonical State into per-workspace SQLite.

Target layout:

```text
data/
  control/
    control.db
  workspaces/
    {workspace_id}/
      buildwealth.db
      artifacts/
      backups/
```

Use SQLite first, not Postgres, because the near-term target is a small number of real users and isolated workspaces. This keeps the product private, inspectable, easy to back up, and easy to migrate later.

Recommended SQLite approach:

- `control.db` for identity, orgs, memberships, workspaces, sessions, invites, billing/entitlement stubs, and security audit.
- `buildwealth.db` per workspace for financial state.
- Large imports, exports, and generated artifacts can stay as workspace-scoped files.
- Context registry can remain rebuildable and separate from durable financial truth.

## Workspace Services

Introduce a workspace service factory that creates stores from the request context.

Recommended module:

```text
services/orchestrator/src/buildwealth_orchestrator/services/workspace_services.py
```

Recommended shape:

```python
@dataclass
class WorkspacePaths:
    root: Path
    profile_path: Path
    portfolio_dir: Path
    plans_dir: Path
    recommendations_path: Path
    conversation_dir: Path
    durable_storage_dir: Path
    backup_archive_dir: Path
    import_inbox_dir: Path
    import_archive_dir: Path
    import_workbench_dir: Path
    import_reports_dir: Path
    portfolio_review_packet_dir: Path
    today_review_checkpoint_path: Path
    protection_policy_path: Path


@dataclass
class WorkspaceServices:
    paths: WorkspacePaths
    financial_profile_store: FinancialProfileStore
    portfolio_store: PortfolioStore
    plan_workspace: PlanWorkspace
    recommendation_inbox: RecommendationInbox
    conversation_store: ConversationStore
    context_intelligence_service: ContextIntelligenceService
    import_workbench_store: ImportWorkbenchStore
    snapshot_store: SnapshotStore
```

Route dependency:

```python
def get_workspace_services(
    context: RequestContext = Depends(get_request_context),
) -> WorkspaceServices:
    return workspace_service_factory.for_context(context)
```

Implementation note:

- A request-scoped cache is fine.
- A process-global cache by workspace id is acceptable only if stores are stateless wrappers around paths and do not hold mutable request state.
- Any cache key must include `workspace_id`.

## Settings and Secrets

### Current Problem

`UserSettingsStore` stores API keys in plaintext. API responses mask sensitive values, but the raw key remains in the local settings JSON.

This should be replaced before real hosted users enter API keys.

### Target Model

Split settings into three categories.

**App Config**

Environment-level configuration.

Examples:

- app environment
- default currency
- control DB path
- workspace root path
- auth mode
- session duration
- encryption key source

Lives in:

- environment variables
- local `.env`
- deployment configuration

**Workspace Settings**

Non-secret workspace behavior.

Examples:

- preferred LLM provider
- preferred model
- provider base URL
- timeout
- max tokens
- context embedding provider
- context embedding enabled flag
- backup preferences
- data-retention preferences

Lives in:

- Stage 1: `data/workspaces/{workspace_id}/settings/workspace_settings.json`
- Stage 2: `workspace_settings` table in `buildwealth.db`

**Workspace Secrets**

Sensitive provider credentials.

Examples:

- LLM API key
- market data provider key
- bank/brokerage aggregation token
- webhook secrets

Lives in:

- Stage 1: encrypted workspace secret store
- Stage 2: encrypted `workspace_secrets` table or external secret manager

API responses should return:

```json
{
  "llm_provider": "openai",
  "llm_model": "gpt-5.5",
  "llm_api_key_configured": true,
  "llm_api_key_last4": "1234",
  "llm_api_key": null
}
```

Never return a stored raw key after save.

### Encryption Recommendation

For local implementation:

- Use an app-level secret key from environment or generated local key file.
- Use authenticated encryption.
- Store only encrypted secret payloads.
- Store `last4`, `created_at`, `updated_at`, and provider metadata separately.

For hosted implementation:

- Use deployment-managed secret material.
- Consider per-workspace envelope keys.
- Add key rotation before public launch.

## Household Profile

Profile becomes the user-facing model of the household's financial reality.

Navigation label:

- `Profile`

Page heading:

- `Your Financial Picture`

Internal model:

- Household Profile

Core profile sections:

- Household members
- Income
- Spending
- Debt
- Goals
- Taxes
- Investing guardrails
- Physical assets
- Preferences
- Constraints
- Data quality

### Household Members

Add a `household_members` section to the financial profile.

Suggested shape:

```json
{
  "household_members": [
    {
      "id": "member-primary",
      "display_name": "Primary",
      "relationship": "self",
      "birth_year": 1990,
      "retirement_age": 65,
      "dependent": false,
      "metadata": {
        "source": "profile_editor",
        "status": "user_confirmed",
        "updated_at": "..."
      }
    }
  ]
}
```

Plain-language UI labels:

- `You`
- `Partner`
- `Child`
- `Dependent`
- `Other household member`

Do not require users to understand tax or advisory terminology to complete the household section.

### Field-Level Metadata

BuildWealth already has profile metadata concepts. Continue and expand them.

Each material field should track:

- source
- status
- confidence
- last confirmed date
- stale after days
- whether the user confirmed it

User-facing statuses:

- `Confirmed`
- `Needs review`
- `Out of date`
- `Missing`
- `Imported`
- `Drafted by Copilot`

Internal statuses may remain more specific, but the UI should keep the language simple.

### Profile Mutation Policy

Material profile changes must use reviewed mutation paths.

Allowed direct edits:

- user manually edits a profile field in the Profile page
- user confirms a guided setup answer

Review-required edits:

- Copilot-drafted profile changes
- imported profile facts
- inferred facts
- stale material facts
- conflicts between Profile, Plan, Portfolio, and Recommendations

Copilot may draft profile changes, but it should not silently apply material financial facts.

## Authorization Model

Permissions should be explicit even if the first UI only exposes owners.

Initial permissions:

- `workspace.read`
- `workspace.manage`
- `profile.read`
- `profile.write`
- `portfolio.read`
- `portfolio.write`
- `plan.read`
- `plan.write`
- `recommendations.read`
- `recommendations.write`
- `copilot.use`
- `settings.read`
- `settings.write`
- `secrets.write`
- `imports.read`
- `imports.write`
- `backup.read`
- `backup.write`
- `export.create`
- `demo.reset`

Role mapping:

```text
owner:
  all workspace permissions

member:
  read/write financial workflows, no workspace deletion or member management

read_only:
  read financial workflows, no mutation

advisor:
  read and draft/recommend, mutation requires household approval

admin:
  organization administration, not automatically financial-data access
```

Initial enforcement can be simple, but it must be centralized.

## Demo Workspace

Demo data should not be mixed into the user's real household workspace.

Create:

- one real household workspace
- one demo household workspace

Demo workspace behavior:

- clearly labeled as demo
- safe to reset
- excluded from real financial readiness
- does not share conversations, recommendations, portfolio data, or profile with real workspace
- may use the same app-level provider settings only if explicitly allowed

Recommended controls:

- Settings -> Data & Privacy -> Demo Data
- `Create demo workspace`
- `Reset demo workspace`
- `Delete demo workspace`
- `Switch to demo`
- `Switch to my household`

Reset should:

- archive or delete the existing demo workspace data
- reseed using `scripts/seed-demo-data.py`
- preserve the real household workspace untouched

Acceptance test:

- resetting demo data does not change the real household profile, portfolio, recommendations, conversations, or settings.

## First-Run UX

First-run flow:

1. Create owner account.
2. Create household workspace.
3. Choose one:
   - `Start with my household`
   - `Try demo data`
4. Land on Today.
5. Today shows profile readiness, top missing data, and next action.
6. Settings lets the user add AI/provider keys later.

Login flow:

1. User enters email and password.
2. BuildWealth creates a server-side session.
3. User lands in last selected workspace if still authorized.
4. If no workspace exists, route to household setup.
5. If session expires, return to login and preserve unsaved local draft where practical.

Workspace switching:

- Add a workspace switcher in the v2 shell.
- Keep it visually quiet.
- Clearly label demo workspace.
- Do not show advisor/client features until enabled.

Recommended shell areas:

- Sidebar remains workflow navigation.
- Top/right account menu handles user, workspace, and logout.
- Settings handles account, household, AI connections, data/privacy, and backups.

## API Surface

Initial auth routes:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/session`
- `POST /api/auth/invitations`
- `POST /api/auth/invitations/accept`

Initial workspace routes:

- `GET /api/workspaces`
- `POST /api/workspaces`
- `POST /api/workspaces/{workspace_id}/select`
- `GET /api/workspaces/current`
- `POST /api/workspaces/{workspace_id}/demo/reset`

Initial account routes:

- `GET /api/account`
- `PATCH /api/account`

Existing routes should not add `workspace_id` as a normal user-controlled query parameter. The active workspace should resolve from the session and selected workspace, with explicit server-side authorization.

For administrative or test-only routes that accept a workspace id, validate membership every time.

## Route Migration Strategy

The route migration should happen in vertical slices.

### Slice 1: Auth Spine

Add:

- control database
- local auth provider
- session service
- request context dependency
- workspace registry
- first owner bootstrap

Exit criteria:

- app can create/login/logout a user
- app can resolve `RequestContext`
- unauthenticated API requests return 401 unless explicitly public
- tests can create two users and two workspaces

### Slice 2: Workspace Store Factory

Add:

- `WorkspacePaths`
- `WorkspaceServices`
- workspace root creation
- default household migration path
- demo workspace creation path

Exit criteria:

- workspace A and workspace B get different data roots
- existing store classes can be instantiated from workspace paths
- no financial route needs a process-global profile/portfolio/plan store for the converted domain

### Slice 3: Profile and Settings

Convert:

- `GET /api/financial-profile`
- `PUT /api/financial-profile`
- `GET /api/onboarding/status`
- `GET /api/settings`
- `PUT /api/settings`
- `POST /api/settings/test-llm`

Add:

- household members in profile schema
- workspace settings
- encrypted workspace secrets
- masked secret API responses

Exit criteria:

- user A cannot read or update user B's profile
- saving an API key does not store plaintext in the settings JSON
- key presence is visible but raw key is never returned
- demo workspace has its own profile/settings

### Slice 4: Portfolio and Imports

Convert:

- portfolio state
- asset registry
- import workbench
- import reports
- portfolio audit
- portfolio review packets

Exit criteria:

- workspace A imports do not appear in workspace B
- portfolio analytics use the active workspace only
- asset metadata and manual prices are workspace-scoped

### Slice 5: Plan and Recommendations

Convert:

- plan workspace
- saved simulations
- plan decisions
- strategy comparisons
- recommendation inbox
- recommendation factory

Exit criteria:

- recommendations are generated from the active workspace only
- plan simulations cannot read another workspace's profile/portfolio
- plan decisions are workspace-scoped

### Slice 6: Copilot, Conversations, and Context

Convert:

- conversation store
- Copilot runtime
- context assembler
- context registry
- context cache keys
- context traces

Exit criteria:

- user A cannot retrieve user B's conversations
- Copilot cannot answer from another workspace's Profile, Portfolio, Plan, Inbox, Research, or Context Registry
- cache keys include workspace identity

### Slice 7: Backups, Export, and Recovery

Convert:

- backup service
- restore service
- storage protection
- export bundles
- versioned workspace support

Exit criteria:

- backup list is workspace-scoped
- restore requires authorization
- user A cannot infer whether user B has backups
- export package contains only selected workspace data

### Slice 8: SQLite Source of Truth

Migrate from workspace-scoped JSON to per-workspace SQLite.

Exit criteria:

- new workspaces use SQLite as durable source of truth
- existing JSON workspace import remains available
- migration tests round-trip current fixtures
- backups and restore are tested with SQLite workspaces

## Frontend Plan

### API Helper

Update the v2 API helper to handle:

- 401 unauthenticated responses
- 403 unauthorized responses
- CSRF token inclusion for mutating requests
- active workspace state
- workspace switch events
- logout

### Shell

Add:

- account menu
- active workspace label
- demo workspace badge
- logout action
- workspace switcher

Do not crowd the primary workflow navigation.

### Settings

Recommended Settings sections:

- `My Account`
- `Household`
- `Connections & AI`
- `Data & Privacy`
- `Backup & Export`

`Connections & AI` should show:

- provider
- model
- endpoint
- key configured state
- last tested date
- test connection action
- remove key action

It should not show the stored raw key.

### Profile

Profile should remain the user's place to understand and correct BuildWealth's model of their household.

Add or refine:

- household members section
- readiness summary
- missing facts
- stale facts
- source/status badges
- guided edit flows
- links from Today, Inbox, Plan, Portfolio, and Copilot

Use plain-language labels.

Avoid exposing internal severity, tenancy, or database language in the UI.

## Migration Plan

### Existing Local Data

Create a migration command:

```text
python scripts/migrate-single-user-data-to-workspace.py
```

Responsibilities:

- create `control.db` if missing
- create initial owner user
- create household organization
- create default household workspace
- move or copy current `data/profile`, `data/portfolio`, `data/plans`, `data/recommendations`, `data/imports`, `data/reports`, `data/conversations`, `data/storage`, and related files into the workspace root
- preserve a backup of the original local layout
- write a migration report

The migration should default to copy-first for safety. Destructive cleanup can be a later explicit action.

### Demo Data

Update `scripts/seed-demo-data.py` to support:

```text
python scripts/seed-demo-data.py --workspace ws_demo_household
python scripts/seed-demo-data.py --reset --workspace ws_demo_household
```

The script should never seed demo data into the real household workspace unless explicitly forced in a test environment.

## Testing Strategy

### Unit Tests

Add tests for:

- password hashing and verification
- session token hashing
- CSRF token verification
- request context resolution
- role-to-permission mapping
- workspace path resolution
- encrypted secret save/load/remove
- masked secret API shape

### Route Tests

For every converted domain, add two-user isolation tests:

- user A creates data
- user B creates different data
- user A cannot read user B data
- user B cannot read user A data
- unauthorized workspace id is rejected
- unauthenticated request returns 401

Priority route groups:

- Profile
- Settings/secrets
- Portfolio
- Imports
- Plan
- Recommendations
- Copilot conversations
- Context
- Backups/export

### Browser Tests

Add v2 browser tests for:

- first-run owner setup
- login/logout
- session expiration behavior
- workspace switching
- demo workspace reset
- Profile readiness in real workspace
- Profile readiness in demo workspace
- AI key configured/test/remove flow

### Security Regression Tests

Add a dedicated isolation test module that fails if a route can read financial data without `RequestContext`.

Test names should be blunt:

- `test_user_cannot_read_other_workspace_profile`
- `test_user_cannot_restore_other_workspace_backup`
- `test_copilot_context_does_not_cross_workspaces`
- `test_demo_reset_does_not_touch_real_workspace`
- `test_raw_api_key_is_not_returned_after_save`
- `test_raw_api_key_is_not_stored_in_workspace_settings`

## Security Baseline

Before inviting any real hosted user:

- no plaintext API keys in workspace settings
- session cookies are HTTP-only
- hosted cookies use `Secure=true`
- mutating cookie-auth routes require CSRF protection
- auth failures are rate-limited
- passwords are hashed with Argon2 or bcrypt
- backup/restore is workspace-scoped
- exports are workspace-scoped
- security audit events exist for sensitive actions
- tests prove workspace isolation

Before public launch:

- password reset flow
- optional MFA or passkey support
- privacy policy and data handling review
- financial guidance/advice language review
- hosted backup restore drills
- key rotation plan
- account deletion/export controls

## Implementation Notes by File Area

### `settings.py`

Change:

- keep app-level config only
- add `CONTROL_DB_PATH`
- add `WORKSPACE_ROOT_DIR`
- add `AUTH_MODE`
- add session lifetime settings
- add encryption key source setting

Avoid:

- global financial data paths as the only source of truth for route handlers

### `main.py`

Change:

- stop relying on module-global financial stores for converted routes
- add auth/session middleware or dependencies
- add `get_request_context`
- add `get_workspace_services`
- convert routes by domain

Temporary bridge:

- unconverted routes may use legacy global stores during migration
- each route should be tracked until converted
- new financial routes should use workspace services only

### `services/user_settings.py`

Change:

- keep provider defaults and masking helpers if useful
- stop storing raw keys in plaintext settings
- split into non-secret workspace settings and encrypted workspace secrets

Potential new modules:

- `services/workspace_settings.py`
- `services/workspace_secrets.py`

### `services/financial_profile.py`

Change:

- keep current migration/readiness behavior
- add `household_members`
- keep field-level metadata
- ensure all profile store instances are workspace-scoped

### `services/context_intelligence.py`

Change:

- context index path must be workspace-scoped
- traces and cache keys must include workspace id
- structured Canonical State remains authoritative

### `web-v2`

Change:

- add login/session handling
- add workspace switcher
- add account menu
- add demo workspace badge
- add settings sections
- update Profile to include household member concepts

## Acceptance Criteria

This architecture slice is complete when:

- a user can register or be bootstrapped locally
- a user can log in and log out
- every converted financial route requires a request context
- a real household workspace and demo household workspace can coexist
- demo data can be reset without touching real data
- Profile reads/writes are workspace-scoped
- Settings reads/writes are workspace-scoped
- API keys are encrypted and never returned raw
- two-user route tests prove isolation for Profile and Settings
- the implementation path for Portfolio, Plan, Recommendations, Copilot, Context, and Backups is documented and ready to execute

## Open Follow-Up Decisions

These do not block the first slice, but should be decided before hosted beta:

1. Which hosted auth provider, if any, should be used later?
2. Should users eventually bring their own provider keys, use BuildWealth-managed provider credits, or both?
3. Should workspace SQLite use file-level encryption from the start, or only field-level encryption for secrets during the first beta?
4. What is the exact invite-only beta operating environment?
5. What account deletion and data-retention policy should be exposed to users?

## Recommended First Implementation Pull

Start with the smallest vertical slice that proves the boundary:

1. Add `control.db` schema and repository.
2. Add `LocalAuthProvider`.
3. Add session cookie login/logout.
4. Add `RequestContext`.
5. Add workspace registry and default household workspace.
6. Add demo household workspace.
7. Add `WorkspaceServices`.
8. Convert Profile routes.
9. Convert Settings routes with encrypted secrets.
10. Add two-user isolation tests for Profile and Settings.

Do not start by rewriting all storage into SQLite. First make workspace identity unavoidable. Once the app cannot accidentally act without a workspace, the storage migration becomes much safer.

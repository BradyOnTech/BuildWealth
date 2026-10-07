# BuildWealth v1 to v2 UI Migration Plan

## Date
2026-05-08

## Status
Completed migration record for replacing classic v1 workflows with the v2 Product Surface.

This document follows [ADR 0004](../adr/0004-v2-is-the-only-future-product-surface.md): v2 is the BuildWealth product surface. The public classic/v1 fallback route has been removed after replacement coverage and product-owner approval.

## Why This Exists

The v2 UI is the product direction. This record documents the deliberate migration away from the earlier UI without dropping user jobs before v2 had a clear replacement path.

The migration rule should be Workflow Replacement:

> No classic surface is removed until every user job it supports has a v2 home, a deliberate v2 replacement, or explicit product-owner approval to remove the old workflow.

The screenshot of the v1 Settings page highlights the mismatch. v1 Settings is not just AI provider setup. It also includes backup and restore, data protection, local version history, AutoGit, remote sync, restore preview, Git activity, retention, and cleanup. Treating v2 Settings as "API keys only" would strand real functionality.

## Code Review Summary

### v1 App Shell

File: `services/orchestrator/src/buildwealth_orchestrator/web/app.js`

v1 imports and exposes these internal pages:

- Today: `dashboard`
- Profile: `profile`
- Copilot: `copilot`
- Research: `research`
- Plans: `plans`
- Tracking: `tracking`
- Inbox: `recommendations`
- Workflows: `workflows`
- Import: `import-statement`
- Portfolio: `portfolio`
- Sync & Import: `sync`
- Settings: `settings`

It also currently links externally to historical upstream/reference apps.

Those external links are not part of the future product surface and should be removed as native BuildWealth workflows replace the jobs they represented.

### v2 App Shell

File: `services/orchestrator/src/buildwealth_orchestrator/web-v2/app.js`

v2 currently imports:

- Today
- Portfolio
- Plan
- Copilot
- Research
- Atelier
- Inbox

The visible nav is based on `meta.group`.

Current issue:

- `web-v2/views/inbox.js` has `group: 'hidden'`
- Today links to `#inbox`
- The page exists, but the user cannot discover it from the sidebar

This is a navigation discrepancy and should be fixed early.

### v1 Settings Scope

File: `services/orchestrator/src/buildwealth_orchestrator/web/views/settings.js`

v1 Settings contains these jobs:

- AI provider setup
- provider API key
- model and base URL
- test provider
- backup list
- create backup
- restore selected backup
- protection policy
- apply protection
- local Git/version history
- initialize versioned workspace
- create checkpoint
- preview diffs
- AutoGit policy and run-due action
- remote connect, push, pull
- restore preview
- guarded restore apply
- Git activity feed
- export Git activity
- retention cleanup

This is a broad "system operations" surface, not only a settings page.

### v2 Atelier Scope

File: `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/atelier.js`

v2 Atelier already covers part of the operations surface:

- durable storage status
- release readiness
- backups summary
- protection summary
- Git checkpoint summary
- audit activity summary
- create backup
- apply protection
- create checkpoint
- read-only restore preview

But it does not fully replace v1 Settings because it does not expose:

- AI provider settings
- backup restore apply
- protection policy editing
- Git policy editing
- Git init
- full diff inspection
- AutoGit policy
- remote connect/push/pull
- guarded restore apply
- Git activity filters/export/cleanup

### v1 Profile Scope

File: `services/orchestrator/src/buildwealth_orchestrator/web/views/profile.js`

v1 Profile supports:

- onboarding status
- tax basics
- profile notes
- income items
- expense items
- debt items
- goal items
- physical assets
- basic add/remove table workflows
- save through `PUT /api/financial-profile`

v2 has no equivalent page yet.

### v1 Import and Sync Scope

Files:

- `web/views/import-statement.js`
- `web/views/sync.js`

v1 supports:

- CSV statement import
- statement import apply
- CSV upload/import
- import file list
- CSV template list
- snapshot sync
- sync status

v2 does not expose these as first-class flows.

### v1 Portfolio Scope

File: `web/views/portfolio.js`

v1 Portfolio is large and operational. It supports:

- holdings
- transactions
- accounts
- snapshot history
- benchmark
- attribution
- watchlist
- refresh prices
- account creation
- custom assets
- cost-basis methods
- risk policy
- manual prices
- FX rates
- snapshot backfill
- transaction deletion
- corporate actions and lot audit display

v2 Portfolio is stronger for executive review and fit assessment, but does not yet replace these operational portfolio-maintenance jobs.

### v1 Workflows and Tracking Scope

Files:

- `web/views/workflows.js`
- `web/views/tracking.js`

v1 Workflows supports:

- workflow template selection
- plan target selection
- live snapshot toggle
- save to plan
- create recommendations
- template JSON params
- run workflow
- report output

v1 Tracking supports:

- plan-vs-actual view
- plan selector
- load tracking
- return and value drift

v2 Plan has a stronger trajectory section and likely replaces Tracking, but Workflows still needs an explicit v2 home.

## Capability Ledger

| v1 Surface | User Job | Current v2 Status | Migration Decision |
| --- | --- | --- | --- |
| Today | daily summary, recommended action, system state | mostly replaced by v2 Today | v2 canonical |
| Profile | edit financial profile and onboarding data | missing | build v2 Profile |
| Copilot | conversations and context preview | replaced by v2 Copilot, but v1 has explicit context preview controls | v2 canonical, consider advanced context diagnostics elsewhere |
| Research | compare symbols and generate dossiers | mostly replaced by v2 Research, but dossier creation differs | v2 canonical after dossier creation parity |
| Plans | plan CRUD and settings | largely replaced by v2 Plan | v2 canonical after create/edit parity is confirmed |
| Tracking | plan-vs-actual | folded into v2 Plan trajectory | deprecate only after route/deep-link parity |
| Inbox | recommendations | v2 exists but hidden | make visible immediately |
| Workflows | run workflow templates | missing | add v2 Workflows or fold into Plan/Atelier |
| Import | statement import | missing | add v2 Import |
| Portfolio | maintain accounts, transactions, prices, watchlist, risk settings | partially replaced by v2 Portfolio | keep classic fallback until advanced maintenance exists |
| Sync & Import | CSV import, upload, sync status | missing | add v2 Data Ingestion |
| Settings | AI, backup, protection, Git, restore, activity | partially split between v2 Atelier and missing Settings | split into v2 Settings and v2 Data & Recovery |
| External upstream app links | historical reference apps | footer links exist | remove; do not preserve as v2 destinations |

## Recommended v2 Information Architecture

Do not reproduce v1's long sidebar one-for-one. That would preserve capability but keep the old UX shape. Instead, use a grouped v2 navigation that makes the main jobs clear.

Recommended sidebar:

```text
Daily
  I     Today
  II    Portfolio
  III   Plan
  IV    Copilot

Foundation
  V     Profile
  VI    Inbox
  VII   Research

Operations
  VIII  Import & Sync
  IX    Workflows
  X     Data & Recovery
  XI    Settings
```

Notes:

- **Inbox must become visible.** It is currently a hidden route despite being linked from Today.
- **Atelier should be renamed or repositioned.** "Atelier" is attractive but ambiguous for a financial product. Its current contents are really **Data & Recovery** or **Operations**.
- **Settings should not absorb every operational tool.** AI provider setup belongs in Settings. Backup restore, Git, checkpoints, and audit activity should move toward Data & Recovery.
- **Profile belongs in Foundation**, because it is the source of personal context used by Copilot, Plan, Portfolio, and recommendations.
- **Import & Sync should be a visible Operations item**, not buried in Settings or classic fallback.
- **Workflows need a v2 decision.** Either keep a Workflows page, or fold workflow templates into Plan as "Run planning workflow". Do not leave them classic-only.

## Route Plan

Canonical v2 routes:

- `#today`
- `#portfolio`
- `#plan`
- `#copilot`
- `#profile`
- `#inbox`
- `#research`
- `#import`
- `#workflows`
- `#data-recovery`
- `#settings`

Compatibility redirects or aliases:

- `#tracking` -> `#plan?section=trajectory`
- `#plans` -> `#plan`
- `#sync` -> `#import?section=sync`
- `#import-statement` -> `#import?section=statement`
- `#recommendations` -> `#inbox`
- `#atelier` -> `#data-recovery` after rename

Classic fallback links may remain available until the migration is complete, but each fallback needs a v2 replacement path:

- `/#profile`
- `/#sync`
- `/#workflows`
- `/#settings`
- `/#portfolio`

## Navigation Mockups

### Phase 1: Transitional v2 Sidebar

This phase surfaces missing routes without pretending every v2 page has full parity.

```text
BuildWealth
The Wealth Almanac

Daily
  I     Today
  II    Portfolio
  III   Plan
  IV    Copilot

Foundation
  V     Profile        [new]
  VI    Inbox
  VII   Research

Operations
  VIII  Import & Sync  [classic fallback inside page]
  IX    Workflows      [classic fallback inside page]
  X     Data & Recovery
  XI    Settings

Footer
  Classic UI [temporary migration scaffolding]
```

### Phase 2: Native v2 Sidebar

This phase removes "classic fallback inside page" labels after parity is implemented.

```text
Daily
  Today
  Portfolio
  Plan
  Copilot

Foundation
  Profile
  Inbox
  Research

Operations
  Import & Sync
  Workflows
  Data & Recovery
  Settings
```

## Page Ownership

### Profile

Owns:

- financial profile overview
- editable profile tables
- onboarding completeness
- investment policy guardrails
- profile context candidates
- profile conflicts and stale fields

Does not own:

- portfolio transactions
- plan settings
- raw context registry diagnostics

### Settings

Owns:

- AI provider
- API key
- model
- base URL
- provider test
- context intelligence posture
- optional embedding settings
- app preferences

Does not own:

- restore apply
- Git diff inspection
- backup retention
- transaction import

### Data & Recovery

Owns:

- durable storage readiness
- backup create/list/restore
- protection policy
- Git/version history
- checkpoints
- AutoGit
- remote sync
- restore preview and guarded apply
- Git activity feed/export/cleanup

This page should absorb the operational parts of v1 Settings over time.

### Import & Sync

Owns:

- snapshot sync status
- manual sync
- CSV import
- statement import
- upload flow
- import history
- file/template selection

### Workflows

Owns:

- workflow template catalog
- run workflow
- plan target selection
- save as artifact
- create recommendations from workflow output

Open product decision:

- keep Workflows as an Operations page, or
- move workflow execution into Plan as "Run planning workflow"

Recommendation: keep a v2 Workflows page initially for parity, then promote the most useful workflows into Plan over time.

### Portfolio

Owns:

- holdings overview
- allocation
- risk watch
- fit review
- watchlist review
- portfolio maintenance actions

Needed v2 expansion:

- accounts
- transactions
- manual prices
- FX rates
- custom assets
- cost-basis methods
- risk policy editing
- snapshot backfill
- corporate action and lot audit visibility

The v2 Portfolio page should not become a single giant form. Use tabs or sub-sections:

- Standing
- Allocation
- Risk
- Watchlist
- Transactions
- Accounts & Pricing
- Audit

## Migration Gates

These gates were used to decide when classic UI links could be removed.

### Gate 1: Discoverability

- every v1 page has a visible v2 route or visible fallback route
- Inbox is visible in v2 nav
- Settings and Profile are visible in v2 nav
- Today links do not point to hidden-only routes

### Gate 2: Critical Setup Parity

- user can configure AI provider from v2
- user can edit core financial profile from v2
- user can import/sync data from v2 or has a clear in-page fallback
- user can create a backup from v2
- user can see whether data is safe to rely on

### Gate 3: Operational Parity

- backup restore flow has a v2 home
- data protection policy has a v2 home
- Git checkpoint and restore preview have a v2 home
- portfolio transaction/account maintenance has a v2 home
- workflow templates have a v2 home

### Gate 4: Classic Removal Readiness

- telemetry or audit logs show classic routes are no longer needed for routine tasks
- v2 browser tests cover each migrated user job
- docs point users to v2 routes
- no public classic UI fallback is required for routine tasks
- product owner explicitly confirms v2 covers the needed workflow outcomes

### Gate 5: Classic Removal

Completed after Gate 4 and explicit product-owner approval:

- remove classic from primary footer
- remove the public classic route
- keep historical assets only as inert source history unless a later cleanup deletes them

## Implementation Slices

### Slice 0: Parity Ledger and Navigation Fix

Purpose: stop accidental functionality loss.

Tasks:

- Add this migration plan to docs.
- Make v2 Inbox visible in navigation.
- Add v2 navigation groups: Daily, Foundation, Operations.
- Add placeholder/stub routes for Profile, Settings, Import & Sync, Workflows, and Data & Recovery if native pages are not built yet.
- Each placeholder must include clear links to the classic route and list what still lives there.
- Rename or alias Atelier as Data & Recovery, while keeping `#atelier` as a compatibility route.

Acceptance:

- user can discover every major job from the v2 sidebar
- no user has to know the classic hash route by memory
- hidden routes are only used for internal detail pages, not primary jobs

### Slice 1: v2 Settings for AI Provider Setup

Purpose: make Copilot setup v2-native.

Tasks:

- Add `web-v2/views/settings.js`.
- Add v2 API helpers for `GET /api/settings`, `PUT /api/settings`, and `POST /api/settings/test-llm`.
- Implement provider selection, API key, model, base URL, timeout, max output tokens, and parallel tool calls.
- Preserve masked-key behavior.
- Add provider default reset.
- Add friendly provider status states.

Acceptance:

- user can configure OpenAI or another provider from v2
- Copilot can use the saved provider without container restart
- saving a masked key does not erase the stored key
- provider test success/failure is plain language

### Slice 2: v2 Profile Overview and Editing

Purpose: make user context visible and editable.

Tasks:

- Add `web-v2/views/profile.js`.
- Load `GET /api/financial-profile` and `GET /api/onboarding/status`.
- Render profile completeness.
- Render profile overview cards.
- Add editable tables for tax, income, expenses, debt, goals, physical assets.
- Add Investment Policy guardrails with plain-language labels.
- Save through `PUT /api/financial-profile`.

Acceptance:

- user can update profile from v2
- profile changes persist after reload
- onboarding status refreshes
- profile is clearly tied to Copilot, Plan, Portfolio, and recommendations

### Slice 3: v2 Data & Recovery

Purpose: migrate operational parts of v1 Settings into a clearer page.

Tasks:

- Rename v2 Atelier navigation label to Data & Recovery.
- Preserve `#atelier` alias.
- Add backup restore list and restore preview.
- Add guarded restore apply.
- Add protection policy editing.
- Add Git policy/init/checkpoint/diff sections.
- Add AutoGit settings and run-due action.
- Add remote connect/push/pull.
- Add Git activity filters, export, and cleanup.

Acceptance:

- every backup/protection/Git job from v1 Settings has a v2 equivalent or explicit fallback
- destructive or externally visible operations require clear confirmation
- restore apply remains guarded through service APIs, never raw Git checkout

### Slice 4: v2 Import & Sync

Purpose: make data ingestion discoverable and less technical.

Tasks:

- Add `web-v2/views/import-sync.js`.
- Show sync status and manual sync.
- Add CSV upload/import.
- Add import templates.
- Add statement import and apply.
- Show recent import files and outcomes.

Acceptance:

- user can sync snapshot data from v2
- user can import CSV data from v2
- user can understand whether import changed profile, portfolio, or transactions

### Slice 5: v2 Workflows

Purpose: preserve guided workflow functionality.

Tasks:

- Add `web-v2/views/workflows.js`.
- Load workflow templates.
- Select target plan.
- Run workflow with optional live snapshot.
- Save result as plan artifact.
- Create recommendations from workflow output.
- Link workflow output to Plan and Inbox.

Acceptance:

- every v1 workflow job can be completed from v2
- workflow output has clear next action
- generated recommendations appear in v2 Inbox

### Slice 6: v2 Portfolio Maintenance

Purpose: finish Portfolio parity without weakening v2's better review UX.

Tasks:

- Add Portfolio sub-navigation.
- Add Transactions section.
- Add Accounts section.
- Add Manual Prices and FX section.
- Add Risk Policy editor.
- Add Custom Assets section.
- Add audit surfaces for corporate actions and lot events.

Acceptance:

- user can maintain portfolio data from v2
- v1 Portfolio is no longer required for normal portfolio operations
- fit review remains prominent and not buried under maintenance forms

### Slice 7: Classic Usage Exit Plan

Purpose: safely retire v1 as a primary surface.

Tasks:

- [x] Add route-level notices in classic UI that link to v2 replacements.
- [x] Add docs that map old routes to new routes.
- [x] Add browser tests for every v2 replacement route.
- [x] Make `/` route to v2.
- [x] Remove the public classic fallback route after parity gates passed.

Acceptance:

- users can move from v1 to v2 without losing functionality
- support docs and route redirects are clear
- classic can be retired with evidence, not assumption

## Immediate Recommendations

Do these next:

1. Fix v2 navigation so Inbox is visible.
2. Add v2 Settings for AI provider setup.
3. Add v2 Profile.
4. Rename or alias Atelier to Data & Recovery and move the operations plan there.
5. Add temporary v2 placeholder pages for Import & Sync and Workflows that deep-link to classic until native pages are built.

This gives users a coherent v2 entrypoint now, while keeping every v1 capability reachable.

## Relationship to Existing Plans

This plan complements:

- `docs/archive/V2_PROFILE_SETTINGS_UX_PLAN_2026-05-08.md`
- `docs/archive/CONTEXT_INTELLIGENCE_IMPLEMENTATION_PLAN_2026-05-07.md`

The Profile/Settings UX plan describes the target pages. This migration plan describes how to get there without losing the broader v1 functionality that currently lives in the classic UI.

# BuildWealth v2 Information Architecture and UX Strategy

## Date
2026-05-08

## Status
Product UX strategy for v2 navigation, page grouping, and user workflows.

## Core Position

BuildWealth should not migrate the v1 sidebar one-for-one into v2.

The v1 sidebar is an implementation map. It exposes many useful tools, but it does not express the user's real workflow. v2 should be organized around the financial decision loop:

1. What is happening?
2. What needs my decision?
3. How does this affect my plan?
4. How does this affect my portfolio?
5. What does BuildWealth know about me?
6. What do I need to configure, import, or recover?

That means not every capability belongs in the main sidebar. Some things should be:

- primary destinations
- contextual sections inside a destination
- utility actions
- setup flows
- advanced system tools
- classic fallbacks during migration

## Product Mental Model

The app should feel like a financial operating system with five major user spaces:

### 1. Command

The user asks:

- Am I okay?
- What changed?
- What should I look at next?

Primary surface:

- Today

### 2. Decisions

The user asks:

- What is waiting for me?
- What should I accept, reject, defer, or investigate?
- What has BuildWealth drafted?

Primary surface:

- Inbox

### 3. Future

The user asks:

- What is my plan?
- What assumptions drive it?
- What scenarios should I compare?
- What decisions have I already made?

Primary surface:

- Plan

### 4. Capital

The user asks:

- What do I own?
- What risks do I have?
- Does this investment fit me?
- What transactions, accounts, prices, and assets support the picture?

Primary surface:

- Portfolio

### 5. Personal Context

The user asks:

- What does BuildWealth know about me?
- What is missing, stale, inferred, or conflicting?
- What should Copilot and recommendations rely on?

Primary surface:

- Profile

Copilot is not a domain. It is an operator over all domains. It still deserves primary access because it is a major interaction mode, but it should not become the place where hidden product functionality lives.

## Recommended Primary Navigation

The main sidebar should stay small. It should include the surfaces users return to repeatedly.

Recommended primary sidebar:

```text
BuildWealth

Today
Inbox
Plan
Portfolio
Profile
Copilot
```

Why these six:

- **Today** is the command center.
- **Inbox** is the decision queue and should not be hidden.
- **Plan** is the future-state workspace.
- **Portfolio** is current capital and risk.
- **Profile** is the user's financial reality and context source.
- **Copilot** is the natural-language operator.

This is the strongest long-term sidebar because it maps to the user's actual recurring questions, not internal modules.

## Secondary Utility Navigation

Do not put every tool in the main sidebar. Put lower-frequency utilities behind a clearly labeled secondary menu.

Recommended utility entrypoint:

```text
Top-right: Data & Tools
```

Inside Data & Tools:

```text
Data & Tools

Data
  Import & Sync
  Accounts & Transactions
  Prices & FX

Automation
  Workflows
  Recommendation Sweep

Research
  Research Library
  Watchlist Research

System
  Connections & AI
  Data & Recovery
  Activity Log
  Advanced Settings
```

This keeps the sidebar focused while preserving full access.

## Why Not Put Everything In The Sidebar

Several v1 pages are tools, not destinations.

Examples:

- Import is something users do when data is stale or missing.
- Sync is an action and status, not a daily destination.
- Workflows are launchable procedures, often attached to Plan or Inbox.
- Backup and Git restore are safety tools, not part of everyday financial thinking.
- Manual prices and FX rates are portfolio maintenance tools, not a top-level mental model.
- Research is often entered from a symbol, fit review, watchlist item, or plan artifact.

If all of these stay in the main sidebar, the app feels like an admin console. BuildWealth should feel like a guided financial system.

## Main Page Responsibilities

### Today

Role:

- start here
- summarize state
- route the user to the right next surface

Should show:

- net worth / standing
- top change
- top decision
- profile readiness warning
- stale data warning
- active plan confidence
- portfolio risk highlight
- recent Copilot/context captures

Should link to:

- Inbox for decisions
- Profile for missing personal context
- Import & Sync for stale/missing data
- Data & Recovery for trust/safety issues
- Plan or Portfolio for domain-specific investigation

Today should not contain large editors.

### Inbox

Role:

- decision review queue
- recommendation lifecycle
- context candidate review

Should include:

- recommendations
- context captures
- material conflicts
- Copilot drafts
- deferred decisions
- review history

This should be a primary sidebar item. A decision system hidden from navigation undermines the app.

### Plan

Role:

- future-state workspace
- assumptions
- scenarios
- decision log
- artifacts

Should include:

- plan story
- assumptions
- health
- trajectory / plan-vs-actual
- scenarios
- branches
- withdrawals
- timeline
- contribution rules
- decisions
- plan artifacts

Should absorb:

- v1 Tracking
- plan-specific workflow outputs

Should not absorb:

- global settings
- raw imports
- generic backup/Git tooling

### Portfolio

Role:

- current capital, exposure, and investment fit

Should include high-level sections:

- Standing
- Allocation
- Risk
- Watchlist
- Fit Review
- Maintenance

The Maintenance area should contain lower-frequency tools:

- accounts
- transactions
- custom assets
- manual prices
- FX rates
- cost basis
- risk policy
- lot audit
- corporate actions

Portfolio maintenance should be discoverable from Portfolio, but not necessarily top-level sidebar.

### Profile

Role:

- personal financial reality
- context quality
- user-specific constraints

Should include:

- overview
- income and spending
- debt
- goals
- taxes
- assets
- investment policy
- context quality
- field source/status

Profile should be primary navigation because it is not merely "settings." It changes the quality and safety of nearly every answer.

### Copilot

Role:

- conversational operator

Should include:

- conversation thread
- plan scope
- context trace
- "what data was used"
- suggested next routes

Should not be the only way to access:

- profile editing
- plan editing
- import
- settings
- recovery

Copilot should route users into product surfaces, not hide those surfaces.

## Where Research Belongs

Research is important, but it is not always a primary sidebar destination.

Recommended model:

- keep Research accessible through Data & Tools
- expose research contextually from Portfolio, Watchlist, Plan artifacts, and Inbox
- optionally show Research as a sidebar item only if active investing/research becomes a daily workflow

Recommended route:

- `#research` remains valid
- nav location: Data & Tools -> Research Library

Rationale:

Most users do not start with "Research." They start with:

- Does this investment fit?
- Why is this holding risky?
- Should I act on this recommendation?
- What evidence supports this plan decision?

Those should deep-link into Research.

## Where Import & Sync Belongs

Import & Sync should not be a main sidebar item long-term.

It should appear:

- in Data & Tools
- as a Today warning action when data is stale
- from Portfolio when holdings or prices are missing
- from Profile when income/expense imports are available

Recommended page:

- `#import-sync`

Sections:

- Sync status
- Upload/import CSV
- Statement import
- Import history
- Templates

## Where Workflows Belong

Workflows should not be a permanent main sidebar item unless they become a major repeated user behavior.

Recommended model:

- Data & Tools -> Workflows
- Plan -> "Run planning workflow"
- Inbox -> "Generate review items"
- Copilot -> can launch or draft workflow parameters

Workflow outputs should route back to:

- Plan artifacts
- Inbox recommendations
- Copilot explanation

## Where Settings Belongs

Settings should not be the home of all advanced operations.

Recommended page:

- `#settings`

Name:

- Connections & AI

Owns:

- AI provider
- API key
- model
- base URL
- provider test
- context intelligence posture
- optional embedding provider
- preferences

Does not own:

- backup restore
- Git history
- activity retention
- import
- portfolio maintenance

## Where Data & Recovery Belongs

Recommended page:

- `#data-recovery`

Name:

- Data & Recovery

Owns:

- backup status
- create backup
- restore preview
- guarded restore apply
- protection policy
- durable storage
- Git checkpoints
- AutoGit
- remote sync
- activity log
- cleanup/export

This is a utility/system page. It belongs in Data & Tools, not the main sidebar.

Atelier can remain as an internal/legacy alias, but the user-facing label should become **Data & Recovery**. "Atelier" is elegant but does not explain the job.

## Proposed Shell Layout

### Sidebar

```text
BuildWealth

Today
Inbox
Plan
Portfolio
Profile
Copilot

[Data & Tools]
```

### Top Bar

```text
Current page / active plan              Data freshness   Provider status   Data & Tools
```

Top-bar status chips:

- data fresh / stale
- Copilot configured / fallback mode
- profile ready / review needed
- backup okay / needs backup

Each chip should deep-link to the owning page or utility.

### Data & Tools Drawer

```text
Data & Tools

Data
  Import & Sync
  Accounts & Transactions
  Prices & FX

Automation
  Workflows
  Recommendation Sweep

Research
  Research Library
  Watchlist Research

System
  Connections & AI
  Data & Recovery
  Activity Log
  Classic UI
```

This drawer can be a right-side panel, command menu, or full page. The important part is that it is discoverable but not part of the daily sidebar.

## Route Map

Primary routes:

- `#today`
- `#inbox`
- `#plan`
- `#portfolio`
- `#profile`
- `#copilot`

Utility routes:

- `#research`
- `#import-sync`
- `#workflows`
- `#settings`
- `#data-recovery`
- `#activity`

Domain subroutes:

- `#portfolio?section=transactions`
- `#portfolio?section=accounts`
- `#portfolio?section=pricing`
- `#portfolio?section=risk-policy`
- `#plan?section=trajectory`
- `#plan?section=workflows`
- `#profile?section=taxes`
- `#profile?section=investing`
- `#settings?section=ai`
- `#data-recovery?section=restore`

Compatibility aliases:

- `#atelier` -> `#data-recovery`
- `#tracking` -> `#plan?section=trajectory`
- `#plans` -> `#plan`
- `#sync` -> `#import-sync`
- `#import-statement` -> `#import-sync?section=statement`
- `#recommendations` -> `#inbox`

## User Workflow Maps

### Daily Review

```text
Today
  -> sees top change
  -> opens Inbox decision
  -> reviews evidence
  -> opens Plan or Portfolio if needed
  -> accepts/rejects/defers
  -> outcome later returns to Inbox quality
```

### Missing Personal Context

```text
Today or Copilot warning
  -> Profile
  -> edits missing field or asks Copilot to help
  -> change creates source/status metadata
  -> Inbox closes related context capture
  -> Copilot answers improve
```

### Investment Decision

```text
Portfolio
  -> Fit Review
  -> Research evidence
  -> Inbox recommendation or Copilot discussion
  -> Plan impact if relevant
  -> decision recorded
```

### Data Import

```text
Today stale data warning or Data & Tools
  -> Import & Sync
  -> upload/import/sync
  -> preview changes
  -> apply
  -> Portfolio/Profile updates
  -> Today refreshes
```

### Recovery / Trust

```text
Top-bar trust warning or Data & Tools
  -> Data & Recovery
  -> create backup / inspect restore preview / checkpoint
  -> apply guarded recovery action only after confirmation
```

## What Should Be Removed From Main Navigation

Long-term, these should not be permanent main sidebar items:

- Research
- Import
- Sync & Import
- Workflows
- Settings
- Data & Recovery
- Activity Log
- Portfolio Analysis
- Simulations

They remain reachable through Data & Tools and contextual links.

## What Must Stay Highly Visible

These should be visible in primary navigation:

- Today
- Inbox
- Plan
- Portfolio
- Profile
- Copilot

This is the smallest set that still covers the app's core promise.

## Migration Recommendation

### Phase 1: Make v2 Coherent

- Sidebar: Today, Inbox, Plan, Portfolio, Profile, Copilot
- Add Data & Tools drawer/page.
- Move Atelier label to Data & Recovery.
- Add placeholder utility pages that deep-link to classic fallbacks.
- Keep classic accessible from Data & Tools.

### Phase 2: Migrate Utilities

- Build native v2 Settings.
- Build native v2 Import & Sync.
- Expand Data & Recovery to cover v1 Settings operations.
- Add v2 Workflows.

### Phase 3: Migrate Maintenance

- Expand Portfolio maintenance sections.
- Move tracking alias into Plan trajectory.
- Move workflow outputs into Plan/Inbox.
- Keep Research as contextual utility.

### Phase 4: Deprecate Classic

- Set `/v2` as the default product UI.
- Keep v2 as the only public product route.
- Do not reintroduce primary classic links after parity gates have passed.

## Final Recommendation

Use a six-item primary sidebar:

```text
Today
Inbox
Plan
Portfolio
Profile
Copilot
```

Put everything else in a discoverable **Data & Tools** utility layer and through contextual links.

This respects the full functionality of v1 without making v2 feel like a control panel. It also gives users a better mental model: start with what changed, review what needs a decision, inspect the plan and portfolio, maintain personal context, and use Copilot to operate across all of it.

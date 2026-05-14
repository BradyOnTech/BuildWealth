# BuildWealth Git Integration Design

## Date
2026-04-23

## Status
Proposed design for first-class Git audit and provenance support in BuildWealth.

## Recommendation
BuildWealth should adopt Git as an optional, first-class audit layer for curated user artifacts. It should not become a Git-first application and it should not turn the entire runtime data root into a repository.

The right model for this codebase is:

- BuildWealth remains local-first and orchestrator-owned.
- Canonical persistence remains in the orchestrator's file-backed stores and durable storage services.
- Git versions a curated, reviewable projection of high-value artifacts.
- Remote sync stays opt-in and defaults to off.

This preserves the architecture in which the orchestrator owns persistence, service logic, and audit history.

## Why Git Helps BuildWealth
BuildWealth is not a note-taking app. Its value comes from trusted financial context, recommendations, planning artifacts, and decision trails. Git is useful here because it adds:

- Provenance for AI-assisted changes to plans, recommendations, and reports.
- Human-reviewable diffs for important financial decisions.
- A durable history of why a plan changed over time.
- An explicit audit trail for recommendation apply/reject flows.
- Optional local-only checkpoints without depending on a cloud service.

Git is not useful here as a replacement for:

- backup and restore
- durable storage migration
- secrets storage
- high-frequency runtime state
- every transient chat or sync event

## Product Goals

1. Give users a trustworthy history of material planning and recommendation changes.
2. Let users create manual checkpoints without leaving the app.
3. Support optional automatic checkpoints for meaningful domain events.
4. Keep local-only operation as the default.
5. Make remote push available, but only by explicit user opt-in.
6. Avoid noisy histories caused by imports, sync loops, backups, or chat traffic.

## Non-Goals

- Do not replace `BackupRestoreService`.
- Do not replace `DurableStorageMigrationService`.
- Do not auto-commit every field edit, keypress, or sync poll.
- Do not track `env` files, API keys, backup archives, SQLite durable snapshots, or logs.
- Do not depend on a remote to use the feature.
- Do not make versioned workspace files directly editable as the primary write path in v1.

## Chosen Architecture

### Summary
BuildWealth adds a separate Git-managed versioned workspace that is materialized from canonical orchestrator stores.

Canonical stores remain the source of truth:

- `data/plans/`
- `data/recommendations/inbox.json`
- `data/profile/financial_profile.json`
- `data/reports/portfolio_review_packets/`
- `data/snapshots/`
- `data/conversations/`
- `data/storage/`
- `data/backups/`
- `data/settings/user_settings.json`

New versioned workspace:

- Development default: `data/versioned/`
- Packaged app default: platform application support directory, for example `~/Library/Application Support/BuildWealth/versioned/`
- Configurable via new setting `VERSIONED_WORKSPACE_DIR`

This workspace is its own Git repository and is intentionally separate from the application source repository.

### Why a Separate Workspace
This is the correct choice over making the whole `data/` tree a repo because:

- the current source repo already tracks application code
- runtime `data/` includes noisy and sensitive files
- backups and durable snapshots should never appear in Git history
- conversations and raw imports are too high-churn for useful commit history
- a curated projection produces cleaner diffs and safer remote behavior

## What Gets Versioned

### Default Included

- plan workspace metadata and files
- plan decisions
- plan artifacts
- recommendation records
- portfolio review packets
- explicit snapshot checkpoints created by the user or a recommendation flow
- selected protection policy and audit metadata

### Default Excluded

- `data/settings/user_settings.json`
- `infra/env/*.env`
- `data/backups/`
- `data/storage/`
- `data/conversations/`
- `data/imports/inbox/`
- `data/imports/archive/`
- `data/simulation/`
- every raw auto-generated portfolio snapshot in `data/snapshots/`
- logs and caches

### Optional Later Inclusion

- `data/profile/financial_profile.json`, but only as an explicit policy choice
- watchlist and similar low-churn user configuration

The financial profile is intentionally excluded from the default policy because it is highly sensitive and has lower audit value than plan and recommendation artifacts.

## Versioned Workspace Layout

The versioned workspace is a normalized mirror, not a blind copy.

```text
data/versioned/
  README.md
  .gitignore
  manifests/
    export_manifest.json
    workspace_policy.json
  plans/
    index.json
    <plan_id>/
      plan.md
      plan.yaml
      tasks.md
      context.md
      decisions.jsonl
      settings.json
      timeline.json
      contribution_rules.json
      assumption_sets.json
      branch_templates.json
      artifacts/
        *.md
  recommendations/
    index.json
    <recommendation_id>.json
  reports/
    portfolio_review_packets/
      <packet_id>.json
      <packet_id>.md
  snapshots/
    checkpoints/
      checkpoint-<timestamp>.json
  policy/
    protection_policy.json
```

### Materialization Rules

- Plans are copied with their existing per-plan directory structure.
- Recommendations are split from `inbox.json` into one file per recommendation plus an `index.json` for better diffs.
- Review packets keep both markdown and JSON.
- Snapshot checkpoints are curated summaries, not full raw sync snapshots.
- The export manifest records source paths, export time, and workspace policy version.

## Snapshot Checkpoint Model
BuildWealth should not commit every sync-created snapshot file. That would create noisy history and large repositories.

Instead, BuildWealth adds a separate checkpoint concept:

- A checkpoint is created manually or after a meaningful workflow outcome.
- A checkpoint captures a stable summary of the latest portfolio state.
- The checkpoint includes totals, key concentrations, selected top holdings, and source references.

Example checkpoint content:

```json
{
  "checkpoint_id": "checkpoint-20260423T153000Z",
  "created_at": "2026-04-23T15:30:00Z",
  "source_snapshot_path": "data/snapshots/snapshot-20260423T152955Z.json",
  "summary": {
    "base_currency": "USD",
    "total_value_usd": 247000.12,
    "net_performance_usd": 15420.88,
    "net_performance_percent": 6.66,
    "top_holdings": [
      {"symbol": "AAPL", "allocation_percent": 18.2},
      {"symbol": "MSFT", "allocation_percent": 11.4}
    ]
  }
}
```

This keeps version history meaningful without turning Git into a time-series store.

## Settings and Policy
Add a new orchestrator-owned settings file:

- `data/settings/git_integration.json`

Proposed schema:

```json
{
  "enabled": false,
  "workspace_dir": "data/versioned",
  "autogit_enabled": false,
  "auto_push_enabled": false,
  "auto_checkpoint_idle_seconds": 180,
  "remote_name": "origin",
  "include_financial_profile": false,
  "include_snapshot_checkpoints": true,
  "include_review_packets": true,
  "include_recommendations": true,
  "include_plans": true
}
```

Policy defaults:

- Git feature disabled by default
- Local repository only
- Auto checkpoint disabled by default
- Auto push disabled by default
- Financial profile export disabled by default

## Backend Services

### 1. `GitRepositoryService`
Thin wrapper around system `git` commands. Responsibilities:

- initialize repo
- status
- diff
- history
- commit
- pull
- push
- remote status
- connect remote

This service should classify errors into structured application states:

- `no_repo`
- `no_remote`
- `ok`
- `rejected`
- `auth_error`
- `network_error`
- `conflict`
- `error`

### 2. `VersionedWorkspaceService`
Materializes the curated Git workspace from canonical stores. Responsibilities:

- export plan workspace files
- normalize and split recommendation records
- export review packets
- write snapshot checkpoints
- write export manifest
- ensure deterministic JSON formatting and stable file ordering

This service should write atomically so a checkpoint never captures a half-written export.

### 3. `GitIntegrationSettingsStore`
Stores user-facing Git integration configuration under `data/settings/git_integration.json`.

### 4. `GitCheckpointService`
Owns checkpoint orchestration. Responsibilities:

- receive domain events from app workflows
- debounce automatic checkpoints
- ask `VersionedWorkspaceService` to materialize current state
- generate commit messages
- call `GitRepositoryService` to commit and optionally push

### 5. `GitCommitMessageService`
Generates deterministic, domain-aware commit messages.

Examples:

- `Update plan "Retirement 2038"`
- `Record recommendation decision for "Reduce AAPL concentration"`
- `Generate portfolio review packet`
- `Create portfolio checkpoint after recommendation apply`
- `Update BuildWealth versioned workspace`

Commit bodies should include structured detail when available:

- event type
- plan id
- recommendation id
- packet id
- actor source such as `user`, `workflow`, or `copilot`

## Domain Events That Trigger Checkpoints

### Should Trigger

- plan created
- plan files updated
- plan settings updated
- plan decision appended
- plan artifact written
- recommendation created
- recommendation accepted
- recommendation rejected
- recommendation outcome recorded
- review packet generated
- snapshot checkpoint created
- protection policy updated

### Should Not Trigger

- every conversation message
- every sync run
- every imported CSV row
- backup creation
- durable storage migration
- engine health probe changes
- transient cache refreshes

This is the main point where BuildWealth should intentionally diverge from Tolaria. Meaningful financial events matter more than editor-focus heuristics.

## AutoGit Policy
AutoGit should exist, but it should be domain-aware and conservative.

### Default Behavior

- off by default
- local commits only
- no automatic push
- debounce on server-side domain events

### Trigger Strategy

- queue checkpoint-eligible events
- wait `auto_checkpoint_idle_seconds` after the most recent eligible event
- if another eligible event arrives, reset the timer
- when timer expires, materialize workspace and commit if there are changes

### Explicitly Deferred

- browser focus/blur heuristics
- background pull loops
- auto-push on app inactivity

Those heuristics work better for note-editing products than they do for a finance application with imports, generated artifacts, and recommendation workflows.

## Remote Policy
Remote support should be available, but it must stay explicit and safe.

### Defaults

- no remote configured
- local commits succeed with no remote
- push is never attempted unless a remote is configured

### Remote Connect Flow

1. User pastes remote URL.
2. App runs `git remote add origin <url>`.
3. App fetches remote refs.
4. If remote is empty, app pushes local history and sets upstream.
5. If remote branch exists and shares history with local and remote is not ahead, app sets upstream and pushes if needed.
6. If histories are unrelated or remote is ahead, app refuses connection and keeps local repo unchanged.

This should mirror Tolaria's safest idea: never rewrite local financial history just to satisfy a remote connection flow.

### Pull and Push Policy

- manual push allowed once remote exists
- manual pull allowed once remote exists
- no automatic background pull in v1
- no automatic merge conflict handling in v1

BuildWealth is primarily a single-user local app. Background pull is more likely to surprise users than help them.

## API Surface
Proposed endpoints:

- `GET /api/git/status`
- `GET /api/git/history?limit=20`
- `GET /api/git/activity?limit=50&event_type=<type>&status=<status>&ref=<hash>&search=<text>`
- `POST /api/git/activity/cleanup`
- `GET /api/git/diff?path=<workspace_path>&ref=<commit_or_head>`
- `POST /api/git/init`
- `POST /api/git/checkpoint`
- `POST /api/git/push`
- `POST /api/git/pull`
- `POST /api/git/remote/connect`
- `GET /api/git/policy`
- `PUT /api/git/policy`
- `POST /api/git/snapshot-checkpoints`

Response payloads should be small and structured, with classified statuses rather than raw stderr strings whenever possible.

## UI Design

### Settings Page
Add a `Version History` section in the existing settings view.

Controls:

- enable version history
- initialize local repository
- create checkpoint now
- enable AutoGit
- enable auto push
- connect remote
- view branch and ahead/behind state
- open recent history

### Minimal History Surface
Initial UI should not try to recreate a full desktop Git client.

V1 surfaces:

- repository initialized or not
- local-only vs remote-connected status
- last checkpoint time and short hash
- recent commit list
- diff viewer for a selected commit or current workspace changes

### Placement
The Settings view is the correct initial home because BuildWealth currently does not have a Tolaria-style bottom bar Git affordance and does not need one to validate the feature.

## Restore and Rollback Model
Git restore should be staged carefully: preview first, then guarded selected-file apply, and never raw checkout into canonical stores.

### V1

- read-only history and diff
- manual checkpoint
- manual push and pull
- read-only restore preview
- guarded restore apply for explicit supported files
- conflict-aware restore selection UX
- durable Git activity feed with event/status/hash/search filters, metrics, JSON/CSV export, and retention controls
- preview-token binding for guarded restore apply

### V2

- broader selective restore for additional plan artifacts and sensitive policy/profile records
- activity-retention policies for different audit categories if one-size-fits-all cleanup is not enough

This matters because the versioned workspace is a projection, not the primary write model.

Guarded restore apply requires:

- an explicit commit ref
- one or more explicit supported file paths
- the `APPLY_GIT_RESTORE` confirmation phrase
- an optional short-lived preview token that binds apply to a recent preview
- a stale-preview check before apply; token validation rejects paths that changed after preview
- a pre-apply checkpoint of the current canonical state
- service-layer validation/import writes
- a post-apply checkpoint of restored canonical state

## Development Notes

- Add `data/versioned/` to the root `.gitignore` so the application source repo stays clean in development.
- Keep the versioned workspace as a separate nested repository when running inside the app source checkout.
- In packaged builds, move the workspace outside the app bundle and outside the source tree entirely.

## Alternatives Considered

### Alternative A: Make `data/` the Git repo
Rejected.

Reasons:

- tracks too much sensitive and noisy state
- mixes backups and durable storage concerns into Git
- creates poor diffs for high-churn files
- risks confusion with the application source repository

### Alternative B: Make canonical stores directly editable in the Git repo
Rejected for v1.

Reasons:

- requires a much tighter import/export contract
- makes conflict handling much harder
- increases the chance of user edits bypassing validation logic

### Alternative C: No Git support at all
Rejected.

Reasons:

- loses useful provenance for plan and recommendation workflows
- weakens trust in AI-assisted changes
- leaves a gap between local-first storage and auditable history

## Phased Rollout

### Phase 1: Manual Local Checkpoints

Deliver:

- `GitIntegrationSettingsStore`
- `VersionedWorkspaceService`
- `GitRepositoryService`
- `POST /api/git/init`
- `GET /api/git/status`
- `GET /api/git/history`
- `GET /api/git/diff`
- `POST /api/git/checkpoint`
- Settings UI for init, status, history, and manual checkpoint

Exit criteria:

- user can initialize a local repo
- user can create a checkpoint after meaningful app actions
- user can inspect commit history and diffs

### Phase 2: Safe Remote Connect and Manual Push/Pull

Deliver:

- remote connect flow
- remote status
- manual push
- manual pull
- refusal of unrelated histories

Exit criteria:

- local-only use remains fully supported
- remote connection does not rewrite local history
- push/pull failures are surfaced as structured states

### Phase 3: Domain-Aware AutoGit

Deliver:

- checkpoint event queue
- domain event hooks
- debounce-based automatic local commits
- semantic commit message generation

Exit criteria:

- automatic commits happen only for meaningful financial workflow changes
- history remains readable and low-noise

### Phase 4: Selective Restore

Deliver:

- read-only restore preview
- checkpoint-scoped preview of plan artifacts, recommendation records, review packets, and selected policy artifacts
- guarded selective restore apply for supported plan files, recommendation records, and review packet files
- structured restore table with restorable/preview-only markers
- durable activity feed for checkpoint, AutoGit, remote, restore preview, and restore apply events with filters, counts, search, export, and dry-run cleanup
- short-lived restore preview tokens that are validated before apply when provided
- service-layer re-apply flows that reject unsupported exported paths

Exit criteria:

- users can preview restore impact without modifying canonical BuildWealth data
- users can select supported preview rows without hand-typing paths
- users are warned when current content changes after preview
- restore does not bypass validation
- users can recover high-value artifacts from history safely

## Testing Strategy

- unit tests for recommendation export normalization
- unit tests for snapshot checkpoint generation
- unit tests for commit message generation
- integration tests using temporary Git repos for init, status, commit, remote connect, push rejection, and no-remote local commit
- API tests for checkpoint endpoints, policy settings, AutoGit, remote operations, diff/history, restore preview, and guarded restore apply
- frontend smoke tests for the Settings Git guide, local history, AutoGit, remote sync, restore preview, and guarded restore apply sections

## Final Design Decision
BuildWealth should implement first-class Git support, but only as a curated audit and provenance layer around high-value user artifacts.

The correct first implementation is:

- separate versioned workspace
- manual local checkpoints first
- remote push opt-in
- no background pull loop
- no Tolaria-style focus-driven Git behavior in v1
- AutoGit only from domain events and idle/debounce heuristics
- restore preview before guarded restore apply

That design benefits BuildWealth. A Tolaria-style "Git for everything" model does not.

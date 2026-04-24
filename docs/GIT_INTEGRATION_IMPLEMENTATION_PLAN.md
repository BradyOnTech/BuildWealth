# BuildWealth Git Integration Implementation Plan

## Date
2026-04-23

## Status
Active implementation plan derived from `docs/GIT_INTEGRATION_DESIGN.md`.

## Purpose
This document turns the Git integration design into an execution sequence for the current BuildWealth codebase.

It is intentionally implementation-oriented:

- which slices to build first
- which files and modules to add or change
- which endpoints and UI surfaces to ship
- which tests to add
- what each slice must prove before moving on

## Execution Summary
BuildWealth should implement Git integration in four phases:

1. Foundation and local manual checkpoints
2. Read-only history and diff UX
3. Safe remote connect and manual push/pull
4. Domain-aware AutoGit and selective follow-up polish

The recommended first shippable milestone is Phase 1 only:

- initialize a local versioned workspace repo
- materialize curated artifacts into it
- create a manual checkpoint
- inspect Git status and recent commits

That gives immediate product value while keeping the risk bounded.

## Guiding Constraints

- The orchestrator remains the source of truth.
- The versioned Git workspace is a projection, not the primary write path.
- Backup and durable storage flows remain independent.
- No feature in this plan should require a remote.
- Automatic Git behavior must be domain-event driven, not browser-focus driven.

## Current Repository Anchors

### Canonical data sources already present

- `services/orchestrator/src/buildwealth_orchestrator/services/plan_workspace.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/recommendation_inbox.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_review_packets.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/snapshot_store.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/financial_profile.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/user_settings.py`
- `services/orchestrator/src/buildwealth_orchestrator/settings.py`
- `services/orchestrator/src/buildwealth_orchestrator/main.py`

### Existing UI surface to extend first

- `services/orchestrator/src/buildwealth_orchestrator/web/views/settings.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/lib/api.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/lib/components.js`

### Existing safety boundaries to preserve

- `services/orchestrator/src/buildwealth_orchestrator/services/backup_restore.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/durable_storage.py`

## New Modules To Add

### Backend services

- `services/orchestrator/src/buildwealth_orchestrator/services/git_repository.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/versioned_workspace.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/git_integration_settings.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/git_checkpoint.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/git_commit_messages.py`

### Backend tests

- `services/orchestrator/tests/test_git_repository.py`
- `services/orchestrator/tests/test_versioned_workspace.py`
- `services/orchestrator/tests/test_git_checkpoint.py`
- `services/orchestrator/tests/test_git_integration_api.py`
- `services/orchestrator/tests/test_git_integration_settings.py`

### Optional shared fixtures

- `services/orchestrator/tests/fixtures/git_remote_repo/` only if a reusable temp-repo fixture becomes worthwhile

## Settings Changes

### `settings.py`
Add new fields:

- `versioned_workspace_dir`
- `git_integration_settings_path`

Recommended defaults:

- `VERSIONED_WORKSPACE_DIR=data/versioned`
- `GIT_INTEGRATION_SETTINGS_PATH=data/settings/git_integration.json`

### `git_integration_settings.py`
Add a dedicated settings store similar in spirit to `user_settings.py`, but for non-secret Git policy.

Required fields:

- `enabled`
- `workspace_dir`
- `autogit_enabled`
- `auto_push_enabled`
- `auto_checkpoint_idle_seconds`
- `remote_name`
- `include_plans`
- `include_recommendations`
- `include_review_packets`
- `include_snapshot_checkpoints`
- `include_financial_profile`

## Phase 1: Foundation and Manual Local Checkpoints

### Goal
Ship a safe, local-only checkpoint flow for curated BuildWealth artifacts.

### Scope

- create versioned workspace directory
- initialize Git repo inside versioned workspace
- export selected canonical stores into normalized workspace files
- create manual checkpoint commits
- expose repo status and last commits via API

### Backend Work

#### Slice 1.1: Settings and service wiring
Files:

- `services/orchestrator/src/buildwealth_orchestrator/settings.py`
- `services/orchestrator/src/buildwealth_orchestrator/main.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/git_integration_settings.py`

Tasks:

- add settings fields for versioned workspace paths
- add `GitIntegrationSettingsStore`
- instantiate the store in `main.py`
- ensure workspace/settings directories are created lazily

Acceptance criteria:

- app boots with Git integration disabled
- default settings file is created on first load
- no Git calls happen unless feature is enabled or explicitly initialized

#### Slice 1.2: Versioned workspace materialization
Files:

- `services/orchestrator/src/buildwealth_orchestrator/services/versioned_workspace.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/plan_workspace.py` only if small helper exposure is needed
- `services/orchestrator/src/buildwealth_orchestrator/services/recommendation_inbox.py` only if small export helper exposure is needed

Tasks:

- write workspace bootstrap files:
  - `README.md`
  - `.gitignore`
  - `manifests/export_manifest.json`
  - `manifests/workspace_policy.json`
- export `data/plans/` into `versioned/plans/`
- export recommendation inbox into per-record JSON files plus `index.json`
- export review packets into `versioned/reports/portfolio_review_packets/`
- export protection policy if present
- support deterministic JSON formatting and stable file ordering
- clean removed exported files without deleting `.git/`

Acceptance criteria:

- two consecutive exports with no source changes produce no file diff
- exported recommendations are split deterministically
- excluded stores do not appear in the versioned workspace

#### Slice 1.3: Git repository wrapper
Files:

- `services/orchestrator/src/buildwealth_orchestrator/services/git_repository.py`

Tasks:

- implement thin system-git wrappers:
  - `is_repo`
  - `init_repo`
  - `status`
  - `history`
  - `diff`
  - `commit`
  - `has_remote`
  - `remote_status`
- classify errors into structured result payloads
- return paths relative to the versioned workspace

Acceptance criteria:

- local repo init works in a temp directory
- status reports clean/dirty state and changed files
- commit succeeds with configured local identity
- “nothing to commit” returns a structured non-crash result

#### Slice 1.4: Manual checkpoint orchestrator
Files:

- `services/orchestrator/src/buildwealth_orchestrator/services/git_checkpoint.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/git_commit_messages.py`

Tasks:

- materialize workspace before checkpoint
- generate default commit message for manual checkpoint
- commit only when exported files changed
- include a short structured body with source event type and export timestamp

Initial commit messages:

- `Create BuildWealth checkpoint`
- `Update BuildWealth versioned workspace`

Acceptance criteria:

- manual checkpoint exports then commits in one call
- clean workspace returns a `nothing_to_commit` style response
- commit messages are deterministic

#### Slice 1.5: API endpoints
Files:

- `services/orchestrator/src/buildwealth_orchestrator/main.py`
- `services/orchestrator/src/buildwealth_orchestrator/schemas.py`

Endpoints:

- `GET /api/git/policy`
- `PUT /api/git/policy`
- `POST /api/git/init`
- `GET /api/git/status`
- `GET /api/git/history`
- `POST /api/git/checkpoint`

Tasks:

- add Pydantic request and response models
- wire endpoints to settings, export, and git services
- ensure endpoints return structured statuses and operator-readable messages

Acceptance criteria:

- endpoints work with Git disabled before init
- policy update persists across restarts
- status and history work after initialization
- checkpoint endpoint returns commit metadata when a commit happens

### UI Work

#### Slice 1.6: Settings panel v1
Files:

- `services/orchestrator/src/buildwealth_orchestrator/web/views/settings.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/lib/api.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/lib/components.js`

Tasks:

- add `Version History` section
- show current enablement and initialization state
- add buttons:
  - `Initialize Repository`
  - `Create Checkpoint`
  - `Refresh Status`
- show:
  - branch
  - local-only state
  - dirty/clean state
  - changed file count
  - last commit short hash and timestamp

Acceptance criteria:

- user can initialize and checkpoint from the settings view
- UI handles clean/dirty/no-repo states without reload
- error states are readable and non-destructive

### Tests

- unit test export manifest generation
- unit test recommendation splitting
- unit test policy store defaults and persistence
- integration tests for repo init, status, checkpoint
- API tests for policy init/status/checkpoint sequence

### Phase 1 Exit Criteria

- user can initialize a local repo
- user can create a checkpoint from the UI
- user can see status and recent commits
- no remote is required
- no backup or durable-storage behavior is affected

## Phase 2: Read-Only History and Diff UX

### Goal
Make checkpoints inspectable enough to be useful in daily workflows.

### Scope

- recent commit list
- current diff view
- per-commit diff view

### Backend Work

#### Slice 2.1: Diff and history enrichment
Files:

- `services/orchestrator/src/buildwealth_orchestrator/services/git_repository.py`
- `services/orchestrator/src/buildwealth_orchestrator/main.py`
- `services/orchestrator/src/buildwealth_orchestrator/schemas.py`

Endpoints:

- `GET /api/git/diff`
- `GET /api/git/history?limit=<n>`

Tasks:

- expose current workspace diff
- expose commit-scoped diff by hash
- return recent commits with message, hash, date, changed file count

Acceptance criteria:

- current diff loads for dirty workspace
- commit diff loads for selected history entry
- no binary or oversized payload crashes the endpoint

### UI Work

#### Slice 2.2: History panel
Files:

- `services/orchestrator/src/buildwealth_orchestrator/web/views/settings.js`
- optional helper extraction into `web/lib/components.js`

Tasks:

- render recent commit list under `Version History`
- render a simple diff panel for selected commit or current changes
- support refresh after checkpoint

Acceptance criteria:

- user can inspect what changed in the latest checkpoint
- list refreshes correctly after a new checkpoint

### Tests

- service tests for diff and history parsing
- API tests for diff/history payload shape
- lightweight frontend smoke test if settings UI test harness exists for this view

### Phase 2 Exit Criteria

- checkpoint history is understandable without using terminal Git
- current changes and historical diffs are visible in the app

## Phase 3: Safe Remote Connect and Manual Push/Pull

### Goal
Add optional remote support without breaking local-first behavior.

### Scope

- connect remote
- detect ahead/behind state
- manual push
- manual pull
- reject incompatible histories

### Backend Work

#### Slice 3.1: Remote connect flow
Files:

- `services/orchestrator/src/buildwealth_orchestrator/services/git_repository.py`
- `services/orchestrator/src/buildwealth_orchestrator/main.py`
- `services/orchestrator/src/buildwealth_orchestrator/schemas.py`

Endpoints:

- `POST /api/git/remote/connect`
- `POST /api/git/push`
- `POST /api/git/pull`

Tasks:

- add remote connection with fetch-first validation
- detect empty remote vs compatible existing branch vs incompatible history
- surface structured states:
  - `connected`
  - `already_configured`
  - `incompatible_history`
  - `auth_error`
  - `network_error`
  - `error`
- implement manual push and pull endpoints
- implement remote status reporting in `GET /api/git/status`

Acceptance criteria:

- local-only repo still checkpoints successfully with no remote
- incompatible remote histories are rejected without mutating local export content
- push rejection is classified clearly

### UI Work

#### Slice 3.2: Remote controls
Files:

- `services/orchestrator/src/buildwealth_orchestrator/web/views/settings.js`

Tasks:

- add remote URL input and connect action
- add manual `Push` and `Pull` buttons
- show ahead/behind and remote-configured state
- show local-only explanatory text when no remote exists

Acceptance criteria:

- user can connect an empty private remote
- user can push manually
- user sees readable errors for auth/network/rejection states

### Tests

- integration tests with temp bare remote repo
- connect-flow tests for empty and incompatible remotes
- push rejection test
- API tests for connect/push/pull

### Phase 3 Exit Criteria

- remote support is optional and safe
- local-only remains a first-class path
- push/pull behavior is structured and predictable

## Phase 4: Domain-Aware AutoGit

### Goal
Add automatic local checkpointing based on meaningful financial workflow events.

### Scope

- event queue
- debounce timer
- automatic commit messages
- optional auto-push only if remote exists and user enabled it

### Backend Work

#### Slice 4.1: Event model
Files:

- `services/orchestrator/src/buildwealth_orchestrator/services/git_checkpoint.py`
- selected source modules and workflows:
  - `services/orchestrator/src/buildwealth_orchestrator/services/plan_workspace.py`
  - `services/orchestrator/src/buildwealth_orchestrator/services/recommendation_inbox.py`
  - `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_review_packets.py`
  - `services/orchestrator/src/buildwealth_orchestrator/main.py`

Tasks:

- define checkpoint event types:
  - `plan_updated`
  - `plan_settings_updated`
  - `decision_appended`
  - `artifact_written`
  - `recommendation_created`
  - `recommendation_decision_recorded`
  - `review_packet_generated`
  - `snapshot_checkpoint_created`
- emit events after successful canonical writes
- debounce queued events using `auto_checkpoint_idle_seconds`

Acceptance criteria:

- multiple quick plan changes collapse into one automatic checkpoint
- failed canonical writes do not emit checkpoint events

#### Slice 4.2: AutoGit execution rules
Files:

- `services/orchestrator/src/buildwealth_orchestrator/services/git_checkpoint.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/git_commit_messages.py`

Tasks:

- add background-safe timer/debounce logic suitable for current runtime model
- commit only if exported workspace changed
- push only if:
  - remote exists
  - auto push enabled
  - push is not currently blocked by rejection/conflict state

Commit message examples:

- `Update plan "Retirement 2038"`
- `Record recommendation decision for "Reduce concentration"`
- `Generate portfolio review packet`

Acceptance criteria:

- AutoGit produces low-noise semantic history
- no browser focus/blur logic is required
- auto push never runs when no remote exists

### UI Work

#### Slice 4.3: AutoGit settings
Files:

- `services/orchestrator/src/buildwealth_orchestrator/web/views/settings.js`

Tasks:

- add toggle for AutoGit
- add toggle for auto push
- add idle-threshold input
- show last automatic checkpoint result

Acceptance criteria:

- user can enable AutoGit independently from remote push
- settings persist and are reflected in backend behavior

### Tests

- debounce and event-collapse unit tests
- commit message tests by event type
- end-to-end tests for plan update leading to one automatic checkpoint

### Phase 4 Exit Criteria

- automatic commits are event-based and readable
- history does not fill with sync noise
- auto push remains opt-in

## Deferred Follow-Up Work

### Selective Restore
Not part of the first implementation plan.

Later work:

- preview restore diff
- restore plan files or recommendation records back through service-layer import/apply flows
- never raw-checkout files directly into canonical stores without validation

### Financial Profile Inclusion
Defer until after the default policy proves useful.

Reason:

- highly sensitive
- lower audit value than plans and recommendation artifacts
- may need separate masking/redaction rules

### Conversation Versioning
Defer indefinitely unless a strong user need appears.

Reason:

- high churn
- low diff quality
- high privacy sensitivity

## Delivery Order Recommendation
If this work is implemented in small PRs, use this order:

1. settings + git integration policy store
2. versioned workspace export service
3. git repository wrapper
4. checkpoint orchestrator
5. API routes and schemas for init/status/checkpoint
6. settings UI v1
7. history and diff
8. remote connect and push/pull
9. AutoGit event model and debounce

## Risk Register

### Risk 1: Noisy commit history
Mitigation:

- export only curated artifacts
- do not version raw sync snapshots
- do not auto-commit on every write

### Risk 2: Sensitive data pushed remotely
Mitigation:

- local-only default
- exclude secrets and user settings by default
- require explicit remote connection
- keep financial profile opt-in

### Risk 3: Versioned workspace drift from canonical stores
Mitigation:

- always materialize from canonical stores before checkpoint
- deterministic export format
- tests for idempotent export

### Risk 4: Git errors degrade the app
Mitigation:

- feature is optional
- classify errors into structured states
- keep failures isolated from plan/recommendation core flows

### Risk 5: Restore semantics become unsafe
Mitigation:

- defer restore
- route any future restore through validated service-layer apply flows

## Definition of Done for First Release
The first release of BuildWealth Git integration is complete when:

- a user can enable the feature and initialize a local repository
- the app exports a curated versioned workspace deterministically
- the user can create a manual checkpoint from the settings UI
- the user can see current status and recent history
- remote support remains optional and local-only works fully
- backup and durable-storage systems remain unchanged

## Immediate Next Build Slice
The next implementation slice should be:

1. add `versioned_workspace_dir` and `git_integration_settings_path` to `settings.py`
2. implement `GitIntegrationSettingsStore`
3. implement `VersionedWorkspaceService` with plans, recommendations, and review packets export
4. add tests for deterministic export and settings persistence

That slice establishes the correct architecture before any Git command orchestration is added.

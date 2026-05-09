# Migration and Compatibility

## Scope
BuildWealth uses file-backed local stores with schema-versioned payloads. Migrations are handled inside orchestrator services during read/write flows.

## Current Schema and Contract Versions (2026-04-15)

### Data Stores
- Portfolio holdings payload: `schema_version = 8`
- Accounts payload: `schema_version = 2`
- Asset metadata payload: `schema_version = 1`
- Cost basis methods payload: `schema_version = 1`
- Manual prices payload: `schema_version = 1`
- FX rates payload: `schema_version = 1`
- FX history payload: `schema_version = 1`
- Watchlist payload: `schema_version = 1`
- Risk policy payload: `schema_version = 1`
- Lot audit payload: `schema_version = 1`
- Corporate actions payload: `schema_version = 1`
- Financial profile payload: `schema_version = 2`
- Plan workspace payloads (index/settings/timeline/contribution rules/assumption sets/branch templates): `schema_version = 2`

### Retired Engine Contracts
Earlier builds included versioned sidecar contracts for benchmark, attribution, and scenario calculations. Those contracts are migration scaffolding under the BuildWealth-native capability direction and should not be expanded for new work.

## Migration Behavior

### 1) Portfolio Store
On initialization/read, portfolio payloads are normalized and upgraded in place.

Key upgrade behaviors:
- Legacy transactions normalized (ids, action normalization, symbol/account defaults, lot method defaults).
- Legacy holdings upgraded to account-scoped records with canonical lot structures.
- Legacy holdings without lots receive synthesized legacy lots to preserve position continuity.
- Existing marked/manual prices are preserved through rebuild/migration paths.
- Account cash, totals, and allocation breakdowns are recalculated into current schema shape.
- Watchlist payloads are normalized to symbol+source identity shape.

### 2) Financial Profile Store
On read/write, payload is migrated to schema v2 with defaults and item-id normalization.

Key upgrade behaviors:
- Ensures `income_items`, `expense_items`, `debt_items`, `goal_items`, `physical_assets` arrays exist.
- Ensures stable generated ids for items that previously had none.
- Adds/normalizes newer fields (`annual_growth_rate`, `inflation_rate`, debt payoff strategy fields, physical asset fields).

### 3) Plan Workspace Store
Plan workspace index/files are normalized to schema v2.

Key upgrade behaviors:
- Ensures canonical plan index shape and timestamps.
- Ensures timeline payload includes retirement block defaults.
- Ensures contribution rules / assumption sets / branch templates files use current payload envelopes and defaults.

### 4) Native Capability Migration
BuildWealth is moving away from sidecar runtime compatibility and toward native orchestrator-owned capabilities.

Migration behavior:
- existing sidecar-related settings, probes, and contract files may remain until the native replacement workflow is complete
- new implementation should target native services such as Import Workbench, Asset Registry, Portfolio Analytics Engine, Plan Simulation Engine, and Plan Strategy Lab
- removal should happen after tests prove no active v2 workflow depends on the old adapter path

### 5) Durable Storage Upgrade Path (Phase 6.0 Slice 1)
BuildWealth now includes a migration service to stage file-backed stores into a SQLite durable snapshot:
- `GET /api/storage/durable/status`
- `POST /api/storage/durable/migrate` (default includes rollback simulation checks)
- `POST /api/storage/durable/rollback`

Migration behavior:
- source files remain the active runtime store during this slice.
- upgrade creates a timestamped migration report and backup snapshot under `DURABLE_STORAGE_DIR/migrations/...`.
- the SQLite snapshot is checksum-verified against source files before activation.
- rollback restores source files from migration backup and restores/removes the durable database based on pre-migration state.

### 6) Backup and Restore Path (Phase 6.0 Slice 2)
BuildWealth now includes archive-based backup/restore operations:
- `GET /api/storage/backups`
- `POST /api/storage/backups`
- `POST /api/storage/backups/restore`

Behavior:
- backups are written under `BACKUP_ARCHIVE_DIR` (default `data/backups`) as timestamped tar archives.
- each archive includes `manifest.json` with per-file checksums and an aggregate checksum.
- restore validates manifest checksums before replacing active data.
- restore can create a pre-restore safety backup (`create_pre_restore_backup=true` by default).

### 7) Local Data Protection Options (Phase 6.0 Slice 3)
BuildWealth now includes policy-driven local permission hardening for sensitive stores:
- `GET /api/storage/protection/status`
- `PUT /api/storage/protection/policy`
- `POST /api/storage/protection/apply`

Behavior:
- policy is stored at `PROTECTION_POLICY_PATH` (default `data/security/protection_policy.json`).
- levels:
  - `standard`: owner/group read + owner write.
  - `hardened`: owner-only permissions.
- policy can include backup archives and can auto-apply on startup.
- status reports non-compliant file/directory counts against active policy.

### 8) Runtime Telemetry Dashboard (Phase 6.0 Slice 4)
BuildWealth now includes a runtime telemetry surface for operational visibility:
- `GET /api/telemetry/runtime`

Behavior:
- reports API latency distribution and error-rate metrics (avg/p50/p95/p99/max plus top routes).
- reports context freshness status (latest context generation time, snapshot age/stale state, coverage/warning signals).
- reports cache quality for unified-context stores (hit rates, utilization, evictions/expired-pruned counters, and quality status).

## Compatibility Window Policy

1. Forward upgrades
- Current orchestrator is expected to auto-upgrade known legacy payload shapes when files are read.
- Upgrades are persisted back to disk after normalization.

2. Backward compatibility
- Downgrade compatibility is not guaranteed after migration writes current schema versions.

3. Retired engine compatibility
- Sidecar contract compatibility is historical migration scaffolding.
- New calculation behavior should use native BuildWealth service contracts and typed API schemas.

## Operational Guidance

Before upgrading BuildWealth:
1. Back up `data/` (especially `data/portfolio`, `data/plans`, `data/profile`).
2. Upgrade and start orchestrator.
3. Optionally stage a durable snapshot with rollback checks:
   - `POST /api/storage/durable/migrate` (default `run_rollback_check=true`)
4. Optionally set and apply local protection policy:
   - `PUT /api/storage/protection/policy`
   - `POST /api/storage/protection/apply`
5. Trigger a read path (for example `/api/snapshot/latest`, `/api/financial-profile`, plan APIs) so schema migrations run.
6. Validate runtime telemetry via `/api/telemetry/runtime` and ensure latency/freshness/cache signals are present.

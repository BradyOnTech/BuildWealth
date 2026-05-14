# Standalone Operations

## Scope
This runbook describes how to run BuildWealth in standalone local-first mode and how to verify core runtime health.

Earlier versions of this runbook described retired calculation-module modes. That path is superseded by BuildWealth-native capability ownership. BuildWealth now runs portfolio analysis and plan simulation through orchestrator-owned services.

## Runtime Modes

### Mode A: Orchestrator Only (Default)
Use this for normal local development and daily usage. This is the canonical runtime mode.

```bash
./scripts/init-env.sh
docker compose -f infra/docker-compose.yml up -d orchestrator
```

Checks:
```bash
curl -s http://localhost:8090/health | jq
```

Expected behavior:
- Core APIs and UI are available.
- The v2 product surface is available.
- Portfolio, Plan, Profile, Inbox, Copilot, Import & Sync, Data & Recovery, and Settings workflows should route through BuildWealth-owned APIs.

### Retired Migration Scaffolding
Legacy calculation settings, service status probes, retired adapter interfaces, and upstream container profiles are retired from normal operation. Do not add new workflows that depend on them.

If a stale reference appears during development, remove it or convert it into BuildWealth-owned service logic with direct tests.

## Triage Checklist

1. Snapshot freshness warnings in unified context:
- Unified context now marks snapshot freshness and stale status under `quality.freshness`.
- Configure stale threshold with `COPILOT_CONTEXT_SNAPSHOT_STALE_AFTER_SECONDS` (default: `86400`).
- If stale warnings appear frequently, schedule syncs or use `use_live_snapshot=true` for Copilot context requests.

2. Context cache visibility:
- Use `GET /api/copilot/context/cache` to inspect current research/projection cache entry counts and rolling hit/miss/write trend counters.
- Use payload-level cache metadata from `GET /api/copilot/context` to confirm hit/miss and force-refresh bypass behavior per request.
- Use `POST /api/copilot/context/cache/reset` to clear cache entries (and optionally metrics) during local troubleshooting.
- For context payload size control, pass `detail_level=light` on `GET /api/copilot/context` (or `context_options.detail_level` in chat requests); use `full` only when deep payload detail is required.

3. Runtime telemetry dashboard checks:
- Use `GET /api/telemetry/runtime` for API latency distribution, context freshness summary, and cache quality rollups.
- In UI, open the Today Dashboard `Runtime Telemetry` panel to inspect p95 latency, server error rate, context freshness state, and per-route/per-cache-store details.

## Durable Storage Upgrade Path (Phase 6.0 Slice 1)

Status:
```bash
curl -s http://localhost:8090/api/storage/durable/status | jq
```

Run migration + rollback simulation checks:
```bash
curl -s -X POST http://localhost:8090/api/storage/durable/migrate \
  -H 'Content-Type: application/json' \
  -d '{"run_rollback_check": true}' | jq
```

Rollback latest migration backup:
```bash
curl -s -X POST http://localhost:8090/api/storage/durable/rollback \
  -H 'Content-Type: application/json' \
  -d '{}' | jq
```

## Backup and Restore (Phase 6.0 Slice 2)

List backup archives:
```bash
curl -s http://localhost:8090/api/storage/backups | jq
```

Create a backup archive:
```bash
curl -s -X POST http://localhost:8090/api/storage/backups \
  -H 'Content-Type: application/json' \
  -d '{"reason":"manual_ops_backup"}' | jq
```

Restore a backup archive:
```bash
curl -s -X POST http://localhost:8090/api/storage/backups/restore \
  -H 'Content-Type: application/json' \
  -d '{"backup_id":"<backup-id>","create_pre_restore_backup":true}' | jq
```

## Local Data Protection (Phase 6.0 Slice 3)

Inspect policy and compliance status:
```bash
curl -s http://localhost:8090/api/storage/protection/status | jq
```

Update policy (hardened mode, include backups, auto-apply on startup):
```bash
curl -s -X PUT http://localhost:8090/api/storage/protection/policy \
  -H 'Content-Type: application/json' \
  -d '{"protection_level":"hardened","include_backups":true,"auto_apply_on_startup":true}' | jq
```

Apply permission hardening now:
```bash
curl -s -X POST http://localhost:8090/api/storage/protection/apply \
  -H 'Content-Type: application/json' \
  -d '{"protection_level":"hardened","include_backups":true}' | jq
```

## Runtime Telemetry Dashboard (Phase 6.0 Slice 4)

Inspect runtime telemetry API:
```bash
curl -s http://localhost:8090/api/telemetry/runtime | jq
```

This telemetry surface includes:
- API latency summary (`avg`, `p50`, `p95`, `p99`, max, server-error rate) and top routes by p95 latency.
- Context freshness summary (latest context generation time, snapshot age/stale state, coverage/missing sections, warning count).
- Cache quality summary for research and baseline-projection stores (hit rate, utilization, evictions, expired-pruned counters, quality status).

## Scripted Reliability Smoke Checks (Cross-Cutting Follow-up)

Run the storage reliability smoke suite (backup/restore + protection policy):
```bash
make reliability-smoke-storage
```

This scripted check validates:
- backup archive creation and listing behavior.
- restore correctness (including pre-restore safety backup behavior).
- protection-policy update and apply behavior in hardened mode, including backup-archive inclusion.

## Useful Commands

```bash
make up
make ps
make logs
make sync
make telemetry-runtime
make reliability-smoke-storage
make backup
make backup-list
make backup-restore BACKUP_ID=...
make protection-status
make protection-apply LEVEL=hardened INCLUDE_BACKUPS=true
make down
```

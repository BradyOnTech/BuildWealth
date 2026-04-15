# Standalone Operations

## Scope
This runbook describes how to run BuildWealth in standalone mode, how to enable optional sidecars, and how to verify contract compatibility at runtime.

## Runtime Modes

### Mode A: Orchestrator Only (Default)
Use this for normal local development and daily usage.

```bash
./scripts/init-env.sh
docker compose -f infra/docker-compose.yml up -d orchestrator
```

Checks:
```bash
curl -s http://localhost:8090/health | jq
curl -s http://localhost:8090/api/engines/status | jq
```

Expected behavior:
- Core APIs and UI are available.
- Sidecar-backed routes still work, but may return degraded metadata when sidecars are disabled.

### Mode B: Orchestrator + Sidecars (Optional)
Use this when contract-compatible sidecar engines are available.

1. Start sidecars externally (or your own local services) at configured base URLs.
2. Ensure sidecars expose:
- health endpoint(s) configured via `*_SIDECAR_HEALTH_PATHS`
- version endpoint(s) configured via `ENGINE_SIDECAR_VERSION_PATHS`
- versioned contract paths (`/v1/...`)

3. Update `infra/env/orchestrator.env`:
- `ENABLE_GHOSTFOLIO_BENCHMARK_SIDECAR=true`
- `ENABLE_GHOSTFOLIO_ATTRIBUTION_SIDECAR=true`
- `ENABLE_IGNIDASH_SCENARIO_SIDECAR=true`
- Confirm `*_SIDECAR_BASE_URL`, `*_SIDECAR_PATH`, and expected contract version vars.

4. Restart orchestrator:
```bash
docker compose -f infra/docker-compose.yml restart orchestrator
```

5. Verify compatibility:
```bash
curl -s http://localhost:8090/api/engines/status | jq
```

For each enabled engine, confirm:
- `reachable: true`
- `contract_compatible: true`
- `contract_version` equals `expected_contract_version`

### Mode C: Legacy Upstream App Stack (Optional Profile)
This profile runs full Ghostfolio/Ignidash application containers for upstream reference/debug workflows.

```bash
docker compose -f infra/docker-compose.yml --profile legacy-upstream up -d
```

This profile is not required for standalone BuildWealth operation.

## Contract Compatibility Guarantees

1. Adapter path enforcement
- Sidecar calls must target versioned paths (`/v{n}/...`).
- Non-versioned sidecar paths are rejected by adapter validation.

2. Probe + guard behavior
- Engine probes collect health, version, and compatibility metadata.
- If a sidecar contract version is unknown/mismatched, orchestrator guards sidecar invocation and returns local fallback metadata when available.

3. Degraded mode transparency
- Degraded responses include engine metadata (for example `engine_status`, `fallback_method`, and warnings).
- Engine degraded counters are surfaced in `/api/engines/status`.

## Triage Checklist

1. Sidecar route unexpectedly degraded:
- Check `GET /api/engines/status` for `reachable` and `contract_compatible`.
- Confirm sidecar `/version` payload exposes a parseable `contract_version`.
- Confirm orchestrator env expected version matches sidecar contract major.

2. Sidecar route unreachable:
- Confirm sidecar process is running and bound to configured localhost port.
- Verify base URL and health paths in `infra/env/orchestrator.env`.

3. Contract mismatch:
- Upgrade sidecar to expected contract major, or
- Intentionally pin orchestrator expected contract version to sidecar major only if contracts are verified compatible.

4. Snapshot freshness warnings in unified context:
- Unified context now marks snapshot freshness and stale status under `quality.freshness`.
- Configure stale threshold with `COPILOT_CONTEXT_SNAPSHOT_STALE_AFTER_SECONDS` (default: `86400`).
- If stale warnings appear frequently, schedule syncs or use `use_live_snapshot=true` for Copilot context requests.

5. Context cache visibility:
- Use `GET /api/copilot/context/cache` to inspect current research/projection cache entry counts and rolling hit/miss/write trend counters.
- Use payload-level cache metadata from `GET /api/copilot/context` to confirm hit/miss and force-refresh bypass behavior per request.
- Use `POST /api/copilot/context/cache/reset` to clear cache entries (and optionally metrics) during local troubleshooting.
- For context payload size control, pass `detail_level=light` on `GET /api/copilot/context` (or `context_options.detail_level` in chat requests); use `full` only when deep payload detail is required.

6. Runtime telemetry dashboard checks:
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

## Useful Commands

```bash
make up
make up-legacy
make ps
make logs
make sync
make telemetry-runtime
make backup
make backup-list
make backup-restore BACKUP_ID=...
make protection-status
make protection-apply LEVEL=hardened INCLUDE_BACKUPS=true
make down
```

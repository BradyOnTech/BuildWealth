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

## Useful Commands

```bash
make up
make up-legacy
make ps
make logs
make sync
make down
```

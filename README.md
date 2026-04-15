# BuildWealth

BuildWealth is a local-first financial command center that combines:
- Portfolio tracking and analytics
- Long-horizon planning and scenario modeling
- Investment research context
- Copilot workflows grounded in your own data

The Python orchestrator (`services/orchestrator`) is the system of record.
Ghostfolio/Ignidash logic is reused through optional, contract-bound sidecars for high-complexity compute domains.

## Standalone Runtime Modes

1. **Orchestrator only (default)**
- Runs BuildWealth as a single local app entrypoint.
- Uses local calculations and local JSON stores.
- Does not require Ghostfolio/Ignidash app containers.

2. **Orchestrator + sidecars (optional)**
- Enables benchmark/attribution/planning sidecar calls through versioned `/v{n}/...` contracts.
- Sidecars are stateless compute engines; orchestrator still owns all persistence.

3. **Legacy upstream app stack (optional profile)**
- For upstream reference/debug workflows only.
- Not required for normal BuildWealth standalone operation.

## Quick Start (Standalone Default)

1. Initialize environment files:
```bash
./scripts/init-env.sh
```

2. Review `infra/env/orchestrator.env`.
- Sidecars are disabled by default.
- Configure OpenAI/OpenBB as needed.

3. Start BuildWealth:
```bash
docker compose -f infra/docker-compose.yml up -d orchestrator
```

4. Open app + health:
- UI: `http://localhost:8090`
- Health: `http://localhost:8090/health`

5. Optional first snapshot sync:
```bash
curl -s -X POST http://localhost:8090/api/snapshot/sync | jq
```

## Optional Sidecar Mode

1. Start your Ghostfolio/Ignidash sidecar services so they expose:
- health endpoint(s): `/health` (or configured alternates)
- version endpoint: `/version` returning `contract_version`
- versioned API paths: `/v1/...`

2. Set `infra/env/orchestrator.env`:
- `ENABLE_GHOSTFOLIO_BENCHMARK_SIDECAR=true`
- `ENABLE_GHOSTFOLIO_ATTRIBUTION_SIDECAR=true`
- `ENABLE_IGNIDASH_SCENARIO_SIDECAR=true`
- Ensure base URLs and sidecar paths are correct.

3. Restart orchestrator and verify engine state:
```bash
curl -s http://localhost:8090/api/engines/status | jq
```

Look for `reachable=true` and `contract_compatible=true` for enabled engines.

## Optional Legacy Upstream App Profile

Start the full Ghostfolio/Ignidash app containers only when needed:
```bash
docker compose -f infra/docker-compose.yml --profile legacy-upstream up -d
```

## Key API Endpoints

- `GET /health`
- `GET /api/engines/status`
- `GET /api/storage/durable/status`
- `POST /api/storage/durable/migrate`
- `POST /api/storage/durable/rollback`
- `GET /api/storage/backups`
- `POST /api/storage/backups`
- `POST /api/storage/backups/restore`
- `POST /api/snapshot/sync`
- `GET /api/snapshot/latest`
- `GET /api/portfolio/benchmark`
- `GET /api/portfolio/attribution`
- `POST /api/planning/scenarios`
- `GET /api/copilot/context`
- `GET /api/copilot/context/cache`
- `POST /api/copilot/context/cache/reset`
- `POST /api/copilot/chat`

## Local Testing

```bash
cd services/orchestrator
python3 -m pip install -e .[dev]
pytest -q
```

## Make Targets

```bash
make init-env
make up
make up-legacy
make ps
make logs
make sync
make backup
make backup-list
make backup-restore BACKUP_ID=...
make down
```

## Docs

- [Architecture](./docs/ARCHITECTURE.md)
- [Sidecar Adapter Architecture](./docs/SIDECAR_ADAPTER_ARCHITECTURE.md)
- [Standalone Operations](./docs/OPERATIONS_STANDALONE.md)
- [Migration and Compatibility](./docs/MIGRATION_AND_COMPATIBILITY.md)
- [Standalone Build Plan](./docs/STANDALONE_BUILD_PLAN.md)
- [Product Roadmap (Source of Truth, 2026-04-15)](./docs/ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md)

# BuildWealth

BuildWealth is a local-first financial command center that combines:
- Portfolio tracking and analytics
- Long-horizon planning and scenario modeling
- Investment research context
- Copilot workflows grounded in your own data

The Python orchestrator (`services/orchestrator`) is the system of record.
Portfolio analytics, import review, asset maintenance, and plan simulation run through BuildWealth-owned services and the v2 product surface.

## Runtime Mode

1. **BuildWealth app**
- Runs BuildWealth as a single local app entrypoint.
- Uses local calculations and local JSON stores.
- Does not require external financial app containers.

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

## Demo Household Data

For end-to-end product testing, seed a realistic average-household dataset:

```bash
./scripts/seed-demo-data.py
```

This creates a mid-career household profile, investment accounts, portfolio transactions,
watchlist items, recommendations, a sample import CSV, and a retirement simulation workspace.
The script is idempotent for rows marked as demo data, so it can be rerun while testing.

Copilot needs a real provider key for live answers. To seed the demo and persist your local
provider settings in one step:

```bash
LLM_API_KEY=... ./scripts/seed-demo-data.py
```

The key is stored only in the local `data/settings/user_settings.json` file.

## Engine Status

BuildWealth runs standalone by default. Engine status is available for native runtime checks:
```bash
curl -s http://localhost:8090/api/engines/status | jq
```

## Key API Endpoints

- `GET /health`
- `GET /api/engines/status`
- `GET /api/telemetry/runtime`
- `GET /api/storage/durable/status`
- `POST /api/storage/durable/migrate`
- `POST /api/storage/durable/rollback`
- `GET /api/storage/backups`
- `POST /api/storage/backups`
- `POST /api/storage/backups/restore`
- `GET /api/storage/protection/status`
- `PUT /api/storage/protection/policy`
- `POST /api/storage/protection/apply`
- `GET /api/git/policy`
- `PUT /api/git/policy`
- `POST /api/git/init`
- `GET /api/git/status`
- `GET /api/git/history`
- `GET /api/git/activity`
- `POST /api/git/activity/cleanup`
- `GET /api/git/diff`
- `POST /api/git/checkpoint`
- `POST /api/git/remote`
- `POST /api/git/push`
- `POST /api/git/pull`
- `GET /api/git/autogit`
- `POST /api/git/autogit/run-due`
- `GET /api/git/restore-preview`
- `POST /api/git/restore-apply`
- `POST /api/snapshot/sync`
- `GET /api/snapshot/latest`
- `GET /api/portfolio/benchmark`
- `GET /api/portfolio/attribution`
- `GET /api/recommendations`
- `POST /api/recommendations/generate/portfolio-risk`
- `POST /api/recommendations/generate/plan-tracking`
- `POST /api/recommendations/generate/cash-liquidity`
- `POST /api/recommendations/generate/run-all`
- `GET /api/recommendations/closure-analytics`
- `POST /api/recommendations/{recommendation_id}/outcome`
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

## Docs

- [Architecture](./docs/ARCHITECTURE.md)
- [Future State Product Plan (active, 2026-04-26)](./docs/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md)
- [Git Integration Design](./docs/GIT_INTEGRATION_DESIGN.md)
- [Git Integration Implementation Plan](./docs/GIT_INTEGRATION_IMPLEMENTATION_PLAN.md)
- [Sidecar Adapter Architecture](./docs/SIDECAR_ADAPTER_ARCHITECTURE.md)
- [Standalone Operations](./docs/OPERATIONS_STANDALONE.md)
- [Migration and Compatibility](./docs/MIGRATION_AND_COMPATIBILITY.md)
- [Standalone Build Plan (historical)](./docs/STANDALONE_BUILD_PLAN.md)
- [Product Roadmap (historical source of truth, 2026-04-15)](./docs/ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md)

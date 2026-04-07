# BuildWealth

Self-hosted financial platform for planning and research across:
- `Ghostfolio` for investment tracking and portfolio state
- `Ignidash` for long-range planning simulations
- `OpenBB` for market and derivatives research
- `BuildWealth Orchestrator` (this repo) for agent-style coordination and unified APIs

## Recommended Defaults (from your requirements)
- Single-user deployment
- Local-first on your MacBook Pro M1 Pro
- USD base currency
- Account coverage: taxable + retirement + HSA, no crypto
- Ghostfolio as source of truth for holdings/transactions
- Minnesota planning context
- Chat + dashboards

## Repository Layout
- `infra/docker-compose.yml`: full local stack
- `infra/env/*.env.example`: service environment templates
- `scripts/init-env.sh`: generates local env files with secrets
- `services/orchestrator`: FastAPI coordinator and sync/research/planning endpoints
- `docs/`: architecture and decision records

## Quick Start
1. Initialize env files:
```bash
./scripts/init-env.sh
```

2. Set your Ghostfolio security token:
- Open `infra/env/orchestrator.env`
- Replace `GHOSTFOLIO_SECURITY_TOKEN=__SET_MANUALLY__`

3. Start all services:
```bash
docker compose -f infra/docker-compose.yml up -d
```

4. Verify services:
- Ghostfolio: `http://localhost:3333`
- Ignidash: `http://localhost:3000`
- Convex Dashboard: `http://localhost:6791`
- Orchestrator health: `http://localhost:8090/health`

5. Run first sync:
```bash
curl -s -X POST http://localhost:8090/api/snapshot/sync | jq
```

## Orchestrator API
- `GET /health`
- `GET /api/snapshot/live`: pull current Ghostfolio snapshot
- `POST /api/snapshot/sync`: pull + persist snapshot, generate Ignidash import payload
- `GET /api/snapshot/latest`: latest persisted snapshot
- `POST /api/planning/scenarios`: baseline/optimistic/conservative/HSA scenario run
- `POST /api/research/options-chain`: OpenBB options chain request
- `POST /api/chat`: rule-based coordinator response over current financial context

## Notes on Ignidash Integration
Ignidash write APIs are user-auth scoped. This scaffold does two reliable things immediately:
- Calls `createDefaultPlan` through Ignidash Convex HTTP action (service-auth)
- Generates a valid `createPlanWithData` payload JSON in `data/ignidash/`

Direct full mutation sync into user-owned plan data is planned as the next integration layer.

## Local Test (orchestrator)
```bash
cd services/orchestrator
python3 -m pip install -e .[dev]
pytest -q
```

## Operations
Common tasks:
```bash
make init-env
make up
make ps
make logs
make sync
make down
```

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
- BuildWealth UI: `http://localhost:8090`
- Orchestrator health: `http://localhost:8090/health`

5. Run first sync:
```bash
curl -s -X POST http://localhost:8090/api/snapshot/sync | jq
```

6. Optional: import broker CSV in UI:
- Open `http://localhost:8090`
- Use `Upload CSV` or `Inbox Import`

7. Optional: import broker CSV via API (place files in `data/imports/inbox/`):
```bash
curl -s -X POST http://localhost:8090/api/import/csv \
  -H 'content-type: application/json' \
  -d '{"path":"example.csv","dry_run":true}' | jq
```

## Orchestrator API
- `GET /health`
- `GET /api/snapshot/live`: pull current Ghostfolio snapshot
- `POST /api/snapshot/sync`: pull + persist snapshot, generate Ignidash import payload
- `GET /api/sync/status`: scheduler/sync run state
- `GET /api/snapshot/latest`: latest persisted snapshot
- `POST /api/import/csv`: parse broker-style CSV and import activities into Ghostfolio
- `POST /api/import/upload-csv`: multipart upload + import in one request
- `GET /api/import/files`: list inbox CSV files
- `POST /api/planning/scenarios`: baseline/optimistic/conservative/HSA scenario run
- `POST /api/research/options-chain`: OpenBB options chain request
- `POST /api/chat`: rule-based coordinator response over current financial context

## CSV Import Format
Accepted columns (aliases supported): `date, action, symbol, quantity, unit_price, fee, amount, currency, data_source, account_name, comment`.

Action mapping:
- `buy/bought/purchase/reinvest` -> `BUY`
- `sell/sold` -> `SELL`
- `div/dividend` -> `DIVIDEND`
- `interest` -> `INTEREST`
- `fee/commission` -> `FEE`

The importer tries to infer missing `quantity` or `unit_price` from `amount`.

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

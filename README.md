# BuildWealth

BuildWealth is a single-entrypoint, local-first financial application that combines:
- portfolio state and analytics
- long-horizon planning and scenario modeling
- investment research data
- Copilot workflows grounded in your own data

The orchestrator (`services/orchestrator`) is the control plane and system of record.
High-complexity calculations can run through local contract-bound sidecars adapted from Ghostfolio and Ignidash.

## Architecture (Current)
- Python orchestrator owns persistence, APIs, migrations, and Copilot orchestration.
- Sidecars are optional local engines behind versioned contracts (`/v{n}/...`).
- Sidecar health and contract compatibility are probed and exposed via `/api/engines/status`.
- On sidecar failure or contract mismatch, orchestrator returns explicit degraded-mode metadata and uses local fallback paths where available.

## Repository Layout
- `infra/docker-compose.yml`: local stack
- `infra/env/*.env.example`: environment templates
- `scripts/init-env.sh`: generate local env files
- `services/orchestrator`: FastAPI app + web UI
- `contracts/engine/v1`: sidecar contract schemas
- `docs/`: architecture/roadmap/decision docs

## Quick Start
1. Initialize env files:
```bash
./scripts/init-env.sh
```

2. Review orchestrator runtime config in `infra/env/orchestrator.env`:
- sidecar base URLs and paths
- sidecar enable flags
- OpenAI/OpenBB settings

3. Start services:
```bash
docker compose -f infra/docker-compose.yml up -d
```

4. Open BuildWealth:
- UI: `http://localhost:8090`
- Health: `http://localhost:8090/health`

5. Optional sync/import:
```bash
curl -s -X POST http://localhost:8090/api/snapshot/sync | jq
```

## Key API Endpoints
- `GET /health`
- `GET /api/engines/status`
- `GET /api/snapshot/latest`
- `POST /api/snapshot/sync`
- `GET /api/portfolio/benchmark`
- `GET /api/portfolio/attribution`
- `POST /api/planning/scenarios`
- `GET /api/copilot/context`
- `POST /api/copilot/chat`

## Local Tests (Orchestrator)
```bash
cd services/orchestrator
python3 -m pip install -e .[dev]
pytest -q
```

## Operations
```bash
make init-env
make up
make ps
make logs
make sync
make down
```

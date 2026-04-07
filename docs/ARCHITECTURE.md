# Architecture

## High-Level Components
1. Ghostfolio (`localhost:3333`)
- Canonical portfolio and transaction store
- Provides holdings/performance/account APIs

2. Ignidash (`localhost:3000`) + Convex (`localhost:3210/3211`)
- Long-term financial simulation UI and engine
- Receives generated plan payloads from orchestrator bridge

3. BuildWealth Orchestrator (`localhost:8090`)
- Pulls holdings context from Ghostfolio
- Normalizes to a stable JSON snapshot schema
- Runs scenario planning and Monte Carlo projections
- Runs OpenBB-backed research calls when enabled
- Exposes chat endpoint for agent-like interactions

## Data Flow
1. `POST /api/snapshot/sync`
- Orchestrator authenticates to Ghostfolio with anonymous bearer token flow
- Pulls:
  - `/api/v1/portfolio/holdings?range=max`
  - `/api/v2/portfolio/performance?range=max` (fallback v1)
  - `/api/v1/account`
- Writes normalized snapshot to `data/snapshots/`
- Generates Ignidash `createPlanWithData` payload into `data/ignidash/`

2. Planning requests
- Reads latest snapshot or provided values
- Runs baseline/optimistic/conservative/HSA delta projections
- Runs Monte Carlo percentile analysis (P10/P50/P90)

3. Research requests
- Calls OpenBB options-chain endpoint when package/provider is configured
- Returns structured records for agent reasoning

## Security Model (Current)
- Local-only Docker network by default
- Per-service secrets in env files
- No public ingress by default
- No audit log requirement in this phase

## Future Layer
- Add authenticated service-to-user Ignidash mutation bridge
- Add broker-specific import adapters and scheduling
- Add persistent conversation memory and tool-call ledger

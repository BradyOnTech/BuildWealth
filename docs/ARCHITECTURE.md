# Architecture

## Current Direction (2026-04-14)
BuildWealth runs as a standalone local application with Python as the control plane and data owner.
Selected high-complexity calculations are delegated to optional, contract-bound sidecars adapted from Ghostfolio and Ignidash.

## Core Principles
1. Single source of truth: orchestrator owns persistence, schema upgrades, and API contracts.
2. Contract-first engine reuse: sidecars communicate only via versioned `/v{n}/...` payload contracts.
3. Safe degraded mode: sidecar failures or contract mismatches never take down core orchestrator flows.
4. Single user entrypoint: BuildWealth UI/API is the product surface, not external upstream UIs.

## Runtime Components

### 1) BuildWealth Orchestrator (`localhost:8090`)
- FastAPI app + web UI
- Local JSON stores for portfolio, plans, profile, recommendations, and conversations
- Migration/normalization on read and write
- Copilot orchestration, tool routing, and context packaging

### 2) Ghostfolio Compute Sidecar (`localhost:8411`, optional)
- Benchmark comparison calculations
- Attribution calculations
- Stateless HTTP compute only; no direct persistence access

### 3) Ignidash Compute Sidecar (`localhost:8412`, optional)
- Scenario simulation and planning compute paths
- Stateless HTTP compute only; no direct persistence access

### 4) OpenBB/LLM Providers (optional external APIs)
- Market/research enrichment and model inference
- Accessed through orchestrator-owned adapter/services

## Data and Control Flow
1. User/API writes update local orchestrator stores only.
2. Orchestrator computes local outputs and can call sidecars for selected domains.
3. Sidecar request/response payloads are contract-validated.
4. Engine status probes track `reachable`, `contract_version`, and `contract_compatible`.
5. If sidecar is unavailable or mismatched, orchestrator emits explicit degraded metadata and uses local fallback where available.

## Contract Governance
- Engine contracts live under `contracts/engine/v1`.
- Major contract changes require a new version folder and adapter wiring.
- Adapter paths must be versioned (`/v1/...` etc.).
- Contract compatibility checks gate sidecar usage at runtime.

## Local Operations Modes
1. **Default:** orchestrator-only standalone mode.
2. **Optional:** orchestrator + sidecar engines.
3. **Optional legacy profile:** full Ghostfolio/Ignidash app containers for reference workflows.

See:
- [`docs/OPERATIONS_STANDALONE.md`](./OPERATIONS_STANDALONE.md)
- [`docs/MIGRATION_AND_COMPATIBILITY.md`](./MIGRATION_AND_COMPATIBILITY.md)
- [`docs/SIDECAR_ADAPTER_ARCHITECTURE.md`](./SIDECAR_ADAPTER_ARCHITECTURE.md)

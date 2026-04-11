# Architecture

## Current Direction (2026-04-10)
BuildWealth uses a hybrid architecture:
- Python orchestrator is the control plane and persistent data owner.
- Targeted TypeScript sidecars provide high-complexity compute domains adapted from Ghostfolio and Ignidash.
- BuildWealth keeps a single-entrypoint UX and does not expose external app UIs to the user.

Detailed contracts and rollout sequence are documented in:
- [`docs/SIDECAR_ADAPTER_ARCHITECTURE.md`](./SIDECAR_ADAPTER_ARCHITECTURE.md)
- [`contracts/engine/v1/README.md`](../contracts/engine/v1/README.md)

## High-Level Components
1. BuildWealth Orchestrator (`localhost:8090`)
- Source of truth for ledger, accounts, snapshots, plans, and profile data
- Owns schema migration and API contracts
- Hosts UI and copilot workflow endpoints
- Applies fallback logic when sidecar engines are unavailable

2. Ghostfolio Engine Sidecar (`localhost:8411`)
- Stateless benchmark and attribution compute engine
- Consumes only versioned contract payloads

3. Ignidash Engine Sidecar (`localhost:8412`)
- Stateless planning/tax/scenario compute engine
- Consumes only versioned contract payloads

## Data and Control Flow
1. Portfolio and planning writes
- All writes go to orchestrator-owned local stores.
- Sidecars never read local files directly.

2. Engine-backed calculations
- Orchestrator adapter validates payload against contract schema.
- Adapter calls sidecar endpoint over localhost HTTP.
- Response is schema-validated before API serialization.

3. Degraded mode
- On sidecar timeout/failure, orchestrator emits explicit degraded result metadata and uses local fallback logic where available.

## Security and Isolation
- Sidecars bind to localhost only.
- No user auth tokens are forwarded to sidecars.
- Sidecars are stateless and receive only minimum required fields for each calculation.

## Near-Term Evolution
- Add benchmark comparison endpoint behind Ghostfolio adapter.
- Add scenario simulation endpoint behind Ignidash adapter.
- Expand to attribution and tax/withdrawal strategy endpoints after contract stability and parity testing.

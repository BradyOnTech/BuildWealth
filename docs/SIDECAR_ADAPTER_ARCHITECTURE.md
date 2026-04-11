# Sidecar Adapter Architecture

## Objective
Define how BuildWealth reuses Ghostfolio and Ignidash logic without embedding or forking full applications into the runtime path.

This document formalizes a hybrid approach:
- Python orchestrator remains the control plane and data owner.
- Targeted TypeScript sidecars run selected upstream-derived calculation engines.
- Python adapters translate canonical BuildWealth models to versioned sidecar contracts.

## Terms

### Adapter (Python)
A thin integration layer inside orchestrator that:
- maps canonical request models to sidecar contract payloads
- invokes sidecar endpoint/process
- validates sidecar responses
- maps results back into BuildWealth API schemas
- enforces timeout/retry/fallback policy

### Sidecar (TypeScript)
A stateless compute service/process that:
- receives contract payloads
- executes calculation logic adapted from Ghostfolio or Ignidash
- returns contract response
- does not own persistence or user/session state

## Design Principles
1. Single source of truth: Python owns persistent state and migrations.
2. Contract first: sidecars can only communicate through versioned schemas.
3. No hidden coupling: sidecars must not read BuildWealth local files directly.
4. Deterministic compute: same request payload yields same response payload.
5. Safe degradation: if sidecar fails, Python returns explicit degraded result and can fall back to local logic where available.

## System Boundaries

### Python Control Plane Responsibilities
- Portfolio ledger and transaction persistence
- Profile and planning data persistence
- Snapshot and history storage
- API authorization and orchestration
- Workflow and copilot orchestration
- Fallback calculations

### Sidecar Responsibilities
- Domain-specific calculations with high parity value:
  - Ghostfolio engine:
    - benchmark comparison timeline
    - advanced performance attribution
  - Ignidash engine:
    - tax simulation
    - contribution ordering
    - withdrawal strategy simulation

## Runtime Topology (Local First)
1. `services/orchestrator` starts as primary API.
2. Sidecars run on localhost ports or as subprocesses.
3. Adapters call sidecars over local HTTP JSON.
4. Sidecar health is checked on startup and before calls.

Suggested local defaults:
- Ghostfolio engine sidecar: `localhost:8411`
- Ignidash engine sidecar: `localhost:8412`

## Contract Versioning
- Every sidecar endpoint includes `contract_version` in request and response.
- Version format: integer major (`1`, `2`, ...).
- Breaking change requires new major contract.
- Python adapter rejects unknown versions unless explicitly configured.

## Error and Fallback Policy
1. Adapter call timeout: 2-5 seconds for synchronous endpoints.
2. Retry once for transient network/process failures.
3. If still failing:
- return structured degraded response
- include `engine_status: "degraded"` and `fallback_method`
- emit log with sidecar error category and correlation id

## Security and Isolation
- Bind sidecars to localhost only.
- No direct user-auth tokens passed to sidecars.
- Pass only minimum required payload fields.
- Validate all sidecar responses against schemas before use.

## Testing Strategy
1. Contract tests:
- validate sample payloads against JSON schemas
2. Adapter tests:
- mock sidecar responses and failures
3. Golden parity tests:
- compare sidecar output against upstream fixture expectations
4. End-to-end tests:
- orchestrator + sidecars running together on local ports

## Rollout Plan

### Phase A: Foundation (Now)
1. Add `contracts/engine/v1` schemas.
2. Implement adapter base utilities in Python:
- request/response validation
- timeout/retry
- degraded-response wrapper
3. Scaffold sidecar process wrappers (health endpoint + version endpoint).

### Phase B: Ghostfolio Sidecar v1
1. Endpoint: benchmark comparison timeline.
2. Input: canonical portfolio value history + benchmark symbols + date range.
3. Output: portfolio return series, benchmark return series, alpha/excess metrics.
4. Replace/augment local benchmark API with adapter-backed implementation.

### Phase C: Ignidash Sidecar v1
1. Endpoint: scenario simulation.
2. Input: canonical plan/profile assumptions and account balances.
3. Output: timeline projections and summary metrics.
4. Integrate into planning endpoints behind feature flag.

### Phase D: Expansion
1. Add attribution endpoint to Ghostfolio sidecar.
2. Add tax and withdrawal strategy endpoints to Ignidash sidecar.
3. Increase parity coverage and retire duplicate local implementations when stable.

## Acceptance Criteria
1. Sidecar endpoints are schema-validated end-to-end.
2. Python APIs remain functional when sidecars are down (degraded mode).
3. At least one Ghostfolio-backed and one Ignidash-backed endpoint are live behind adapters.
4. BuildWealth remains single-entrypoint UX with no user navigation into external apps.

## Implementation Notes
- Upstream references should be documented at file level and in `ATTRIBUTIONS.md`.
- New engine contracts should live under `contracts/engine/v{n}`.
- Avoid direct copying; adapt to BuildWealth canonical model and Python orchestration requirements.

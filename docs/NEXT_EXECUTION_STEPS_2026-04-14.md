# BuildWealth Next Execution Steps (2026-04-14)

## Purpose
Concrete follow-on work after Phase 1.18 completion, ordered by leverage and dependency.

## Current Snapshot
- Core Phase 1 + Phase 2 foundations are implemented and passing tests.
- Phase 1.18 broker CSV templates are implemented with template selection, auto-detection, and broker-specific parsing coverage.
- Phase 3.1 asset metadata database expansion is complete (seeded catalog + deterministic fallback + schema/UI plumbing + tests).
- Primary remaining work is Phase 3 sidecar hardening, UX consolidation, and documentation/ops cleanup.

## Priority Order

### 1) Phase 3.1 Asset Metadata Database
Status: Completed

Scope:
1. Add seeded local metadata catalog for broad coverage (target: ~500+ symbols).
2. Include practical fields for portfolio/planning context: `name`, `asset_class`, `sector`, `region`, `asset_type`, `data_source`.
3. Add deterministic fallback classification for uncategorized symbols.
4. Ensure seeding does not overwrite richer user/imported metadata.
5. Add tests for seed load + fallback behavior.

Why now:
- Improves allocation quality, planning assumptions, and Copilot context in one slice.

### 2) Phase 3.3 Sidecar Boundary Hardening (Active)
Status: In Progress

Scope:
1. Audit sidecar adapters/routes for strict contract-version checks.
2. Verify health/version probe behavior and degraded counters for all sidecars.
3. Add regression tests for sidecar failure modes and fallback telemetry.
4. Remove/document any remaining legacy full-app bridge assumptions.

Progress:
- Implemented: contract-version compatibility tracking in engine status, route-level sidecar guards, guarded local fallback metadata, and contract-guard regression tests.
- Remaining: finish bridge-assumption cleanup docs and complete UX/ops follow-through in 3.4/3.6.

Why next:
- Stabilizes the targeted-adapter architecture before further feature depth.

### 3) Phase 3.4 UX Consolidation / Product UX Pass
Status: Pending

Scope:
1. Replace JSON-heavy planner controls with guided forms where possible.
2. Improve dashboard/portfolio/plans flow cohesion and action loops.
3. Surface evidence/freshness/assumption context consistently in high-impact views.

Why:
- Moves from “power-user tooling” to polished, durable product workflows.

### 4) Phase 3.6 Documentation + Ops Cleanup
Status: Pending

Scope:
1. Reconcile roadmap docs to current truth (capability audit is stale).
2. Update README and local run/sidecar instructions to current architecture.
3. Document migration and compatibility expectations.

Why:
- Keeps execution aligned and prevents drift in future slices.

## Guardrails
1. Keep using Ghostfolio and Ignidash upstream logic/code patterns when beneficial.
2. Avoid over-indexing on one deep feature without finishing adjacent integration value.
3. Prefer shipping vertical slices with tests over isolated internals.

## Definition of Done for This Workstream
1. 3.1 merged with tests and visible metadata-quality improvements.
2. 3.3 merged with fallback/contract regression coverage.
3. Docs reflect shipped reality and current priorities.
4. Full orchestrator test suite remains green.

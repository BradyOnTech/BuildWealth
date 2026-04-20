# Codebase Quality Follow-Up

## Date
2026-04-15

## Purpose
This document records the areas where the recent code-quality refactor improved maintainability but also introduced more indirection, plus the areas where the sidecar/degraded-mode layer remains intentionally complex because it reflects the chosen architecture.

The goal is not to undo the refactor. The goal is to make the new structure easier to understand and to reduce complexity where the indirection is now doing too many jobs at once.

## Summary
The refactor was a net improvement:
- duplication is lower
- dead code and weak comments were removed
- shared field definitions and contract shapes are more centralized
- typing is stronger in several service modules
- error handling is less misleading

The tradeoff is that some shared helpers now sit one layer farther away from the feature code that uses them, and the sidecar orchestration layer still carries real complexity because it has to support:
- local-first execution
- optional sidecars
- contract-version guards
- degraded responses
- operator-facing engine health

## Execution Status (2026-04-20)
- Completed: Slice A (Shared Helper Cohesion)
- Completed: Slice B (Frontend Field Schema Isolation)
- Completed: Slice C (Engine Policy and Envelope Unification)
- Completed: Slice D (Planning Sidecar Decomposition)
- Completed: Slice E (Sidecar Matrix Test Hardening)

## Areas With New Indirection

### 1. Service Helper Consolidation
Status:
- Completed (2026-04-15, Slice A)

Files:
- `services/orchestrator/src/buildwealth_orchestrator/services/value_coercion.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/recurring_projection.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/buildwealth_context.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/income_projection.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/expense_projection.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_review_packets.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_risk_alerts.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/debt_projection.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/rmd_projection.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/scenario_engine.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/tax_engine.py`

What happened:
- shared coercion/parsing/time helpers moved into `value_coercion.py`
- shared recurring schedule projection logic moved into `recurring_projection.py`
- mixed helper ownership in `service_utils.py` was removed

Why this is better:
- lower duplication
- fewer subtly different helper implementations
- easier to test once and reuse everywhere
- helper ownership is explicit for coercion/parsing vs projection concerns

Why this is more indirect:
- feature files still import shared helpers rather than keeping small local utilities inline

Guardrails after split:
1. Keep names explicit and domain-neutral.
2. Keep only truly shared logic in these modules.
3. If a helper is only used by one service later, move it back to that service.

### 2. Neutral Extraction From Feature Modules
Files:
- `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_metrics.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/research.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/coordinator.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/workflow_runner.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/today_dashboard.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/timeline_defaults.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/plan_workspace.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/timeline_projection.py`

What happened:
- concentration logic moved out of `research.py` into `portfolio_metrics.py`
- timeline defaults moved into `timeline_defaults.py`

Why this is better:
- removes sideways dependencies between feature modules
- lowers future circular-dependency risk

Why this is more indirect:
- the new modules are neutral but still small, so a reader has to jump files to understand simple logic
- `timeline_defaults.py` is canonical for the runtime services, but related value sets can still drift in other files if they are duplicated later

How to fix it:
1. Group these modules under a clearly named shared domain area if more helpers accumulate.
   - recommended direction: `services/shared/portfolio_metrics.py` and `services/shared/timeline_defaults.py`
2. Replace untyped `dict[str, Any]` returns in `portfolio_metrics.py` with a typed response object or `TypedDict`.
3. Audit `schemas.py` and any frontend enum/value mirrors so timeline defaults stay single-source.
4. Do not create a generic dumping ground. If the shared area grows beyond a handful of focused helpers, split by domain.

### 3. Frontend Plan-Setting Registry Centralization
Status:
- Completed (2026-04-15, Slice B)

Files:
- `services/orchestrator/src/buildwealth_orchestrator/web/lib/plan_setting_fields.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/lib/components.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/views/plan-editor.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/views/plans.js`
- `services/orchestrator/src/buildwealth_orchestrator/web/views/profile.js`

What happened:
- plan-setting field metadata moved from `state.js` into `plan_setting_fields.js`
- plan-setting form usage now goes through explicit helper wrappers in `components.js`
- added a focused round-trip smoke test for field-registry render/parse behavior

Why this is better:
- lower UI drift
- fewer duplicated option lists
- shared parsing/rendering behavior
- runtime state and form-schema ownership are now separated

Why this is more indirect:
- there is still one extra jump between plan views and metadata module
- wrappers in `components.js` add a small layer, but make the metadata contract explicit

Guardrails after split:
1. Keep `plan_setting_fields.js` limited to declarative field/option metadata.
2. Keep `state.js` runtime-mutable only.
3. Keep plan-setting wrappers explicit if generic component helpers evolve.

### 4. Shared Schema Base Classes
Files:
- `services/orchestrator/src/buildwealth_orchestrator/schemas.py`
- `contracts/engine/v1/ghostfolio.*.json`

What happened:
- repeated request/response shapes were collapsed into shared Pydantic bases and repeated JSON schema fragments were centralized with local `$defs`

Why this is better:
- less repeated contract shape drift
- clearer envelope consistency

Why this is more indirect:
- inheritance makes it harder to understand a final request/response shape by reading one class in isolation
- `schemas.py` is continuing to accumulate multiple domains in one file

How to fix it:
1. Keep the shared bases, but move them into clearly marked sections or a dedicated `schemas_shared.py` only if the main file keeps growing.
2. Add short comments above internal base models stating which public models inherit from them.
3. Avoid further inheritance depth. One shared base layer is enough.

## Intentional Complexity That Should Not Be Deleted

### Sidecar / Degraded-Mode Execution
Files:
- `services/orchestrator/src/buildwealth_orchestrator/services/planning_sidecar.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/engine_adapter.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/engine_status.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_benchmark.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_attribution.py`
- `services/orchestrator/src/buildwealth_orchestrator/services/copilot_runtime.py`

What makes it complex:
- one codepath may produce:
  - local result
  - sidecar request
  - contract guard skip
  - adapter error fallback
  - degraded response with explicit metadata
- engine health and contract compatibility are tracked separately from request execution
- benchmark, attribution, and planning all follow similar patterns but are not identical

Why this complexity is intentional:
- BuildWealth chose targeted sidecar reuse, not a full rewrite and not a full fork
- local mode must remain functional when sidecars are disabled or unavailable
- contract guards are necessary to avoid silent incorrect compute

What should not happen:
- do not remove degraded mode
- do not collapse sidecar and local execution into hidden implicit fallbacks
- do not let feature services invent their own ad hoc engine metadata fields

## How To Simplify The Intentional Complexity

### 1. Extract Engine Call Policy
Problem:
- services decide sidecar eligibility inline

Fix:
1. Introduce a small engine policy helper that answers:
   - sidecar enabled?
   - adapter available?
   - contract compatible?
   - guard reason?
2. Return a typed result such as `EngineCallDisposition`.
3. Make planning, benchmark, and attribution use the same policy entrypoint.

### 2. Extract Shared Degraded Response Assembly
Problem:
- each service still assembles degraded metadata in slightly different ways

Fix:
1. Add one helper module for engine result envelopes.
2. Centralize:
   - `engine`
   - `engine_status`
   - `fallback_method`
   - warnings merge behavior
3. Leave domain payload assembly in the feature services.

### 3. Separate Planning Sidecar Responsibilities
Status:
- Completed (2026-04-20, Slice D)

Problem:
- `planning_sidecar.py` still handles too many jobs in one class:
  - local execution
  - request building
  - adapter call
  - degraded fallback
  - response merge

Result:
1. Split into focused internal helpers:
   - local result builder
   - local-only/degraded envelope builders
   - sidecar request execution helper
   - sidecar merge response helper
2. Kept the external service API unchanged.
3. Added local-path projection payload regression coverage.

### 4. Normalize Engine Metadata Vocabulary
Problem:
- fallback and engine-status concepts are consistent in spirit, but still scattered

Fix:
1. Define canonical enums/constants for:
   - engine status values
   - fallback method values
   - contract guard reasons
2. Reuse them in Pydantic models, service logic, and tests.
3. Keep docs aligned with those exact values.

### 5. Add Sidecar Matrix Tests
Problem:
- the architecture is intentional, but its complexity is easiest to break in edge cases

Fix:
1. Add explicit matrix coverage for:
   - disabled
   - adapter missing
   - contract mismatch
   - request error
   - invalid response
   - successful sidecar response
2. Assert both business payload correctness and engine metadata correctness.

## Recommended Execution Order

### Slice A: Shared Helper Cohesion (Completed 2026-04-15)
Goal:
- split shared helper responsibilities into cohesive modules and keep helper ownership obvious

Definition of done:
- no mixed coercion/projection helper module remains
- all touched services still pass targeted tests

### Slice B: Frontend Field Schema Isolation (Completed 2026-04-15)
Goal:
- move plan-setting field metadata out of `state.js`

Definition of done:
- runtime state and UI field schema are separated
- plan settings render/parse from one dedicated metadata module

### Slice C: Engine Policy and Envelope Unification (Completed 2026-04-15)
Goal:
- isolate intentional sidecar complexity behind smaller internal abstractions

Definition of done:
- planning, benchmark, and attribution all use the same engine call policy helper
- degraded metadata assembly is shared and typed

### Slice D: Planning Sidecar Decomposition (Completed 2026-04-20)
Goal:
- reduce the internal cognitive load of `planning_sidecar.py`

Definition of done:
- request build, local execution, fallback, and merge paths are separate functions
- behavior and API contracts stay unchanged

### Slice E: Sidecar Matrix Test Hardening (Completed 2026-04-15)
Goal:
- make intentional complexity safer to maintain

Definition of done:
- each engine path has explicit degraded-mode and success-path matrix coverage

## Guardrail
The right fix is to isolate complexity, not pretend it does not exist.

For extracted helpers:
- keep only the helpers that are truly shared
- keep helper modules small and cohesive

For sidecar orchestration:
- keep degraded mode explicit
- make engine decisions and result envelopes canonical
- test the state matrix directly

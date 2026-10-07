# Release Readiness Product Contract Implementation Plan

**Goal:** Make "ready to rely on BuildWealth today?" a stable backend/product signal that can be used by v2 Atelier, Today, future product testing, and eventually release gates.

**Product posture:** This is trust infrastructure, not a new feature area. The contract should tell the user whether the current local app state is dependable enough for day-to-day financial decision support. It should prefer clear warnings over false confidence.

## Current State

Already present:

- v2 Atelier shows durable store, latest backup, protection compliance, git checkpoint status, audit-event status, safe trust actions, read-only restore preview, and Profile/Copilot audit rows.
- Today has a Trust & Durability command card and Trust confidence heat-map domain.
- Storage/protection/git/audit endpoints exist.
- Browser coverage exists for the v2 Atelier safe trust workflow.

Previous gap:

- Readiness is derived inside the frontend checklist. Backup age, checkpoint policy, restore-preview confidence, workflow verification status, and provider/degraded blockers are not yet represented as a stable backend contract.

Current implementation:

- `GET /api/release-readiness` returns the shared backend contract.
- Today's Trust & Durability command card and Trust confidence domain use the backend readiness status.
- v2 Atelier renders the backend checklist and recommended safe actions while keeping full restore apply out of v2.
- Backend, frontend unit, and browser workflow tests cover the contract and v2 trust flow.
- Workflow verification is persisted through `POST /api/release-readiness/workflow-verification`; readiness now warns when product workflow evidence is missing/stale, blocks when the latest run failed, and marks the workflow check ready when the latest product pass is fresh.

## Contract Shape

Add a release-readiness response with:

- `status`: `ready`, `warning`, or `blocked`
- `ready_count` and `total_count`
- `generated_at`
- `summary`
- `checks`: ordered readiness checks
- `blocking_gaps`: issues that should prevent relying on the app today
- `warnings`: issues that are acceptable only with caveats
- `recommended_actions`: safe next actions such as create backup, apply protection, create checkpoint, run restore preview, review provider degradation, or run product smoke tests

Each check should include:

- `id`
- `title`
- `status`: `ready`, `warning`, or `blocked`
- `detail`
- `domain`: storage, protection, checkpoint, audit, provider, workflow, or data
- `action_kind`
- `href`
- optional `last_verified_at`
- optional `metadata`

## First Readiness Checks

- Durable store exists and is reachable.
- Backup exists and is not older than the configured threshold.
- Protection is supported and compliant.
- Git repository/checkpoint state is available and not dirty beyond the configured tolerance.
- Audit feed has recent protected or user-impacting events.
- Restore-preview evidence exists recently, or the app recommends running a read-only preview.
- Provider/engine degradation is not currently blocking major decision surfaces.
- Critical browser workflow verification status is known when available.

## Implementation Tasks

### Task 1: Define schemas and backend builder

- Add Pydantic schemas for readiness check, recommended action, and response.
- Add a builder in the orchestrator that composes existing durable storage, backup, protection, git status, git activity, engine/provider/degraded signals, and workflow verification metadata.
- Keep thresholds conservative and centralized.

### Task 2: Add API route

- Add `GET /api/release-readiness`.
- Return a full response even when one dependency fails; dependency failures should become warning or blocked checks, not endpoint crashes unless the whole orchestrator is unhealthy.

### Task 3: Update v2 consumers

- Update v2 API wrappers.
- Make v2 Atelier render the readiness checklist from the backend response.
- Make Today Trust command card and Trust confidence heat-map domain prefer the readiness contract when available.

### Task 4: Add tests

- Backend tests for `ready`, `warning`, and `blocked` states.
- Frontend unit tests that v2 Atelier renders backend readiness checks and recommended actions.
- Browser workflow test that mocks `/api/release-readiness` and verifies the checklist survives safe trust actions.

### Task 5: Product-testing integration

- Add release-readiness status to the product testing checklist.
- Use this contract as the first gate before the manual feature-by-feature product test pass.

## Non-Goals

- No full restore apply inside v2.
- No automatic file cleanup.
- No claim that investment advice is decision-grade solely because storage is ready.
- No hidden provider fallback that masks degraded data.

## Done When

- v2 Atelier and Today both use the same readiness contract.
- The app can distinguish `ready`, `warning`, and `blocked` trust states.
- The contract recommends safe corrective actions.
- Tests cover dependency failures and stale/missing trust evidence.
- The manual product-testing checklist starts with release-readiness verification.

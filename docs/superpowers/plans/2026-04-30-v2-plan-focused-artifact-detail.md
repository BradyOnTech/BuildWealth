# v2 Plan Focused Artifact Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `#plan?...&section=artifacts&artifact=...` open a focused v2 artifact detail view instead of only landing on the artifact list.

**Architecture:** Reuse the existing `GET /api/plans/{plan_id}/artifacts/{artifact_id}` endpoint. Keep the artifact list visible, add a focused detail panel above it, escape artifact content, surface packet citations, and provide contextual links back to Plan sections, Research, Inbox, and Copilot where appropriate.

**Tech Stack:** Existing FastAPI/Pydantic artifact endpoint; v2 vanilla JS Plan state; Node unit tests; Playwright-backed v2 Plan workflow.

---

## Tasks

### Task 1: Add Focused Artifact Contracts

- [x] Add Plan unit tests proving `renderArtifacts(plan, state)` renders a focused artifact panel when `state.focusedArtifact` is present.
- [x] Add Plan source tests proving `plan.js` reads `params.artifact`, calls `api.planArtifact`, and passes artifact state into `renderArtifacts`.
- [x] Run `node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs` and confirm the new tests fail.

### Task 2: Implement Focused Artifact Loading And Rendering

- [x] Add `ui.artifacts` state to `plan.js` with `focusedArtifactId`, `focusedArtifact`, `busy`, and `error`.
- [x] Load focused artifact detail during Plan init and plan switching when an `artifact` route param is present.
- [x] Render a focused detail panel in `artifacts.js` with type label, created date, escaped content, packet citations, and contextual actions.
- [x] Keep research dossier and thesis routes pointed to v2 Research while generic artifact detail stays inside v2 Plan.

### Task 3: Browser Workflow, Docs, Verification

- [x] Extend the v2 Plan browser workflow to open a generic artifact link and verify focused content renders.
- [x] Update roadmap docs to mark focused generic artifact detail complete.
- [x] Run `node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/*.test.mjs`.
- [x] Run `python -m pytest services/orchestrator/tests/test_web_v2_plan_browser.py -q`.
- [x] Run `git diff --check`.

## Acceptance Criteria

- Artifact links with `artifact=` open a focused v2 Plan detail panel.
- The detail panel renders full artifact content safely escaped.
- Packet citations remain visible and linked where possible.
- The artifact list remains available below the focused detail.
- Browser coverage protects the focused artifact route.

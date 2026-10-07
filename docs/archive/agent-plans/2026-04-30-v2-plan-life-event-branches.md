# v2 Plan Life-Event Branches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move common life-event what-if branch templates into v2 Plan so users can preview real-life changes without falling back to classic Plan.

**Architecture:** Reuse the existing Plan Workspace branch-template and scenario-branch backend contracts. Add one focused v2 Plan module that reads templates, lets the user choose a template and small overrides, posts a branch preview, and hands the result to Copilot or the decision ledger without applying settings.

**Tech Stack:** FastAPI/Pydantic backend contracts already exist; v2 vanilla JS modules; Node unit tests; existing Plan browser workflow can be extended later.

---

## File Map

- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/lib/api.js` to add `planBranchTemplates`, `updatePlanBranchTemplates`, and `planScenarioBranch` wrappers.
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/branches.js` for branch template rendering, draft state helpers, payload construction, and result rendering.
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js` to load branch templates, render the new section, handle branch form events, run branch previews, and save branch decision notes.
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs` with failing tests first.
- Update `docs/archive/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md` and `docs/archive/agent-plans/2026-04-29-plan-workspace-migration.md` after implementation.

## Tasks

### Task 1: Add API And Render Contracts

- [x] Add Plan unit tests proving `api.js` exposes branch-template and scenario-branch wrappers.
- [x] Add tests proving branch templates render as a v2 Plan section and `buildScenarioBranchPayload` includes `branch_template_id`, `branch_name`, `assumption_set_id`, `current_portfolio_value_usd`, `compare_settings`, and `branch_events`.
- [x] Run `node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs` and confirm the new tests fail.

### Task 2: Build The Branch Workspace

- [x] Add `branches.js` with a template picker, compact event summary, override fields, run button, and branch result.
- [x] Add API wrappers in `api.js`.
- [x] Wire `plan.js` state, data loading, event delegation, render slot, branch preview call, and save decision note.
- [x] Change the footer branch link from classic Plan to `#plan?id=...&section=branches`.

### Task 3: Update Docs And Verify

- [x] Mark life-event branches as migrated for the common v2 workflow while leaving withdrawal comparison as the remaining advanced fallback.
- [x] Run `node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/*.test.mjs`.
- [x] Run `python -m pytest services/orchestrator/tests/test_plan_workspace.py services/orchestrator/tests/test_web_v2_plan_browser.py -q`.
- [x] Run `git diff --check`.

## Acceptance Criteria

- v2 Plan shows a Life Event Branches section.
- Users can pick a saved branch template, optionally stage bounded overrides, and run a scenario branch preview.
- Branch results show scenario deltas, Monte Carlo/simulation metadata when present, Copilot handoff, and save-decision action.
- Common branch work no longer uses the classic Plan link.
- Advanced withdrawal comparison remains the only Plan footer classic fallback.

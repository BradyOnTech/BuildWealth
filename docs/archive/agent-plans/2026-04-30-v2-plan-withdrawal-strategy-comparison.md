# v2 Plan Withdrawal Strategy Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move withdrawal-strategy comparison into v2 Plan so retirement drawdown tradeoffs can be reviewed without the classic Plan fallback.

**Architecture:** Reuse the existing `POST /api/plans/{plan_id}/withdrawal-strategy-compare` backend contract. Add a focused v2 Plan module that lets the user choose strategies, optionally select an assumption set/current portfolio value, renders tax/withdrawal/terminal-balance comparison rows, and supports Copilot/decision handoff without applying settings.

**Tech Stack:** Existing FastAPI/Pydantic contract; v2 vanilla JS modules; Node unit tests; Playwright-backed v2 Plan browser workflow.

---

## File Map

- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/lib/api.js` to add `planWithdrawalStrategyCompare`.
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/withdrawals.js` for strategy selection, payload construction, result rendering, and handoff controls.
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js` to render the withdrawal comparison section, handle field/action events, call the API, save decision notes, and retire the last classic Plan footer fallback.
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs` with failing tests first.
- Extend `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan_workspace.spec.mjs` to cover the v2 withdrawal comparison loop.
- Update `docs/archive/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md` and `docs/archive/agent-plans/2026-04-29-plan-workspace-migration.md`.

## Tasks

### Task 1: Add API And Render Contracts

- [x] Add Plan unit tests proving the v2 API exposes `planWithdrawalStrategyCompare(id, body)`.
- [x] Add tests proving `buildWithdrawalComparePayload` parses selected strategies, assumption set, current portfolio value, and `include_raw_results`.
- [x] Add tests proving `renderWithdrawals` shows strategy rows, tax/withdrawal metrics, best-strategy hints, warnings, Copilot handoff, and save-decision action.
- [x] Run `node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs` and confirm the new tests fail.

### Task 2: Build The v2 Withdrawal Comparison Surface

- [x] Add `withdrawals.js` with strategy checkboxes, optional context inputs, run button, result table, warnings, and handoffs.
- [x] Add the API wrapper in `api.js`.
- [x] Wire `plan.js` state, render slot, event delegation, compare call, and save-decision action.
- [x] Change the footer withdrawal link from classic Plan to `#plan?id=...&section=withdrawals`.

### Task 3: Browser Workflow And Docs

- [x] Extend the v2 Plan browser workflow to run withdrawal comparison and save a decision note.
- [x] Mark withdrawal comparison as migrated in the future-state and Plan migration docs.
- [x] Run `node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/*.test.mjs`.
- [x] Run `python -m pytest services/orchestrator/tests/test_withdrawal_strategy_compare.py services/orchestrator/tests/test_web_v2_plan_browser.py -q`.
- [x] Run `git diff --check`.

## Acceptance Criteria

- v2 Plan shows a Withdrawal Strategy Comparison section.
- Users can compare common strategies without leaving v2 Plan.
- Results show withdrawals, taxes, terminal balance, Monte Carlo percentiles, warnings, and best-strategy metadata.
- Users can discuss the comparison in Copilot or save a proposed decision note.
- The Plan footer no longer needs a classic Plan link for high-frequency Plan workflows.

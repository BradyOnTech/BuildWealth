# Account-Type Contribution Fit Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make portfolio-fit and generated investment/research rows explain account-type and contribution-routing concerns without creating direct trade advice.

**Architecture:** Reuse the existing portfolio-fit service, investment policy profile payload, account-location helpers, and watchlist/research recommendation generator. Add a compact `contribution_guidance` object under `portfolio_impact` and generate review-only rows when account/contribution policy conflicts are the primary fit concern.

**Tech Stack:** FastAPI/Pydantic backend, local-first JSON stores, Python service tests, v2 vanilla JS surfaces, Node/browser tests where UI routing changes.

---

## Scope

This slice should answer:

- Does the proposed or implied account fit the user's account-location policy?
- Does tax sensitivity make the selected account worth reviewing?
- Would a contribution route worsen concentration, asset-class, cash-floor, or simplicity policy concerns?
- What should the user review next?

This slice must not:

- optimize tax lots
- recommend buying or selling
- automatically change contribution rules
- present tax advice as a definitive answer

## Task 1: Portfolio-Fit Contribution Guidance

**Files:**

- Modify `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_fit.py`
- Test `services/orchestrator/tests/test_portfolio_fit.py`

- [x] **Step 1: Write failing tests**

Add tests that assert portfolio-fit returns `portfolio_impact["contribution_guidance"]` when a proposed account or account-location policy creates review context.

Expected fields:

- `status`: `review`
- `account_id`
- `account_type`
- `tax_treatment`
- `review_reasons`
- `policy_conflicts`
- `recommended_review`

- [x] **Step 2: Verify red**

Run:

```bash
python -m pytest services/orchestrator/tests/test_portfolio_fit.py -q
```

Expected: new tests fail because `contribution_guidance` is not present.

- [x] **Step 3: Implement minimal guidance derivation**

Use existing account helpers and existing policy gaps. Keep the object compact and derived inside `assess_portfolio_fit(...)`.

- [x] **Step 4: Verify green**

Run:

```bash
python -m pytest services/orchestrator/tests/test_portfolio_fit.py -q
```

Expected: portfolio-fit tests pass.

## Task 2: Recommendation Factory Rows

**Files:**

- Modify `services/orchestrator/src/buildwealth_orchestrator/services/recommendation_factory.py`
- Test `services/orchestrator/tests/test_recommendation_factory.py`

- [x] **Step 1: Write failing tests**

Add a watchlist/research generator test where fit payload contains `tax:contribution_account_policy` and `portfolio_impact.contribution_guidance`.

Expected row:

- title: `Review VTI contribution account fit`
- actionability: `review_only`
- suggested action kind: `review_portfolio_fit`
- no buy/sell wording
- evidence includes `contribution_guidance`

- [x] **Step 2: Verify red**

Run:

```bash
python -m pytest services/orchestrator/tests/test_recommendation_factory.py -q
```

Expected: new test fails because no contribution-account signal exists.

- [x] **Step 3: Implement minimal generator branch**

Add a branch before generic account-location policy handling so contribution-routing rows get a distinct signal key and title.

- [x] **Step 4: Verify green**

Run:

```bash
python -m pytest services/orchestrator/tests/test_recommendation_factory.py -q
```

Expected: recommendation factory tests pass.

## Task 3: Surface Review

**Files:**

- Inspect `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/portfolio.js`
- Inspect `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/copilot/thread.js`
- Modify only if the new guidance is invisible in existing fit cards.

- [x] **Step 1: Inspect existing fit card rendering**

Confirm whether `portfolio_impact.contribution_guidance` is displayed or summarized.

- [x] **Step 2: Add compact rendering if needed**

Render only:

- account treatment
- review reasons
- recommended review

- [x] **Step 3: Verify UI unit tests**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/portfolio.test.mjs services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/copilot_thread.test.mjs
```

Expected: relevant v2 rendering tests pass.

## Task 4: Browser Workflow

**Files:**

- Extend an existing investment recommendation browser spec if routing changes.
- Prefer `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/investment_recommendation_loop.spec.mjs`.

- [ ] **Step 1: Add mocked contribution/account fit row**

Use a `generator:watchlist_research` row with `suggested_action.kind = "review_portfolio_fit"` and `policy_gap = "tax:contribution_account_policy"`.

- [ ] **Step 2: Verify route loop**

The row should route to Portfolio fit review and keep Copilot as the explanatory next step.

- [ ] **Step 3: Run browser test**

Run the focused browser workflow. In the Codex sandbox, Chromium may need elevated permissions.

## Completion Criteria

- Portfolio-fit emits compact account-type contribution guidance.
- Watchlist/research recommendations create review-only contribution-account rows.
- No generated wording says buy, sell, trade, or automatically change allocation.
- Existing Portfolio/Copilot cards make the new context inspectable.
- Docs reflect Plan migration as complete enough and account-policy guidance as the next compounding slice.

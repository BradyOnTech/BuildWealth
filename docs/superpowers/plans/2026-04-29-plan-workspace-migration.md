# v2 Plan Workspace Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make v2 Plan the durable, inspectable financial thesis for BuildWealth: assumptions, timeline, contribution rules, decisions, evidence, scenario diffs, and outcome learning.

**Architecture:** Keep existing backend Plan Workspace contracts and migrate the high-frequency product surfaces into focused v2 modules. Plan should not become a second Inbox, Portfolio, or Research page; it should connect those surfaces by explaining the assumptions and decisions they depend on.

**Tech Stack:** FastAPI/Pydantic backend, local-first `PlanWorkspace`, v2 vanilla JS views, Node unit tests, pytest backend tests, Playwright browser workflows.

---

## Product North Star

BuildWealth is a local-first financial decision operating system. Plan is the living thesis inside that system.

Today says what matters now. Inbox holds reviewable recommendations. Portfolio and Research answer whether an investment fits. Copilot helps discuss and draft. Plan should answer:

- What are we trying to accomplish?
- What assumptions are guiding the advice?
- What changed, who changed it, and why?
- Which evidence supported a decision?
- What did we expect to happen?
- Did the outcome later prove useful?

The Plan migration is successful when a user can understand and adjust their plan without leaving v2 for normal workflows.

## Current State

Already present:

- v2 Plan masthead, story, trajectory, decisions, and look-closer footer.
- Existing API contracts for plan detail, settings, timeline, contribution rules, assumption sets, scenario diff, scenario branch, tracking, decisions, artifacts, and saved dossier thesis revision.
- Recommendation application and outcome capture already write decision packets, closure artifacts, and scenario preview context.
- v2 Research can show packet, compare, dossier, and thesis review surfaces.
- v2 Plan now links saved research dossier artifacts into v2 Research.

Current gaps:

- Plan assumptions are displayed as a static ledger, not a true workspace.
- Plan settings, assumption sets, timeline, and contribution rules still largely rely on classic routes or Copilot tools.
- Artifacts are not typed into a dedicated v2 artifact/evidence center.
- Decisions are visible, but not yet connected enough to recommendation closure, expected outcome, research citations, Copilot threads, or scenario previews.
- Scenario diff exists as an API, but not as a normal v2 review surface.
- Plan health is implicit across Today/Inbox instead of visible in Plan.

## Design Principles

- **Plan is not a dashboard clone.** It should preserve durable context, not duplicate every Today card.
- **Plan is not a research terminal.** It should link evidence into Research and show why that evidence matters to the plan.
- **Plan is not a recommendation queue.** It should show decision history and open plan-specific reviews, while Inbox remains the action queue.
- **Migrate by workflow frequency.** Settings, assumptions, artifacts, decisions, and scenario diffs come before rare advanced tools.
- **Keep classic as a fallback only.** The footer can keep advanced links while each high-frequency slice graduates into v2.
- **TDD every slice.** Each migration slice starts with a focused unit/backend/browser test.

## File Map

Primary frontend files:

- `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js`  
  Owns Plan page state, data loading, tab/section composition, event delegation, and route params.
- `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/story.js`  
  Current plan title, lede, key assumptions, and top actions. This should become the read-only assumption summary.
- `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/trajectory.js`  
  Tracking and plan-vs-actual visualization.
- `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/decisions.js`  
  Decision ledger and append form.
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/assumptions.js`  
  Editable Plan assumptions, assumption freshness, active assumption set, and save controls.
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/artifacts.js`  
  Typed artifact/evidence center with routes to v2 Research, Inbox, and closure artifacts.
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/scenarios.js`  
  Scenario diff form/results and decision-packet save hooks when available.
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/health.js`  
  Compact Plan health model: stale assumptions, weak tax/cash context, open plan reviews, old decisions, stale linked research.

Primary frontend API file:

- `services/orchestrator/src/buildwealth_orchestrator/web-v2/lib/api.js`  
  Add wrappers for plan settings, timeline, contribution rules, assumption sets, scenario diff, branch templates, and refresh context.

Primary backend files:

- `services/orchestrator/src/buildwealth_orchestrator/main.py`  
  Existing endpoints are mostly enough for the first migration slices. Add small aggregate helpers only when the UI would otherwise need to make many calls for a single page.
- `services/orchestrator/src/buildwealth_orchestrator/services/plan_workspace.py`  
  Durable local plan files, decisions, artifacts, settings, timeline, assumption sets, and branch templates. Avoid schema churn unless a v2 surface needs a typed field that cannot be derived.
- `services/orchestrator/src/buildwealth_orchestrator/schemas.py`  
  Add response fields only when they are stable product concepts, not temporary UI convenience.
- `services/orchestrator/src/buildwealth_orchestrator/services/recommendation_factory.py`  
  Only touched when Plan health or assumptions create/update recommendation rows.

Primary test files:

- `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan_workspace.spec.mjs`
- `services/orchestrator/tests/test_plan_workspace.py`
- `services/orchestrator/tests/test_recommendation_ranking_integration.py`
- `services/orchestrator/tests/test_recommendation_actions.py`
- `services/orchestrator/tests/test_web_v2_*_browser.py`

## Existing Backend Contracts To Reuse

- `GET /api/plans`
- `GET /api/plans/{plan_id}`
- `PATCH /api/plans/{plan_id}/settings`
- `GET /api/plans/{plan_id}/timeline`
- `PUT /api/plans/{plan_id}/timeline`
- `GET /api/plans/{plan_id}/contribution-rules`
- `PUT /api/plans/{plan_id}/contribution-rules`
- `GET /api/plans/{plan_id}/assumption-sets`
- `PUT /api/plans/{plan_id}/assumption-sets`
- `POST /api/plans/{plan_id}/scenario-diff`
- `POST /api/plans/{plan_id}/scenario-branch`
- `GET /api/plans/{plan_id}/tracking`
- `POST /api/plans/{plan_id}/decisions`
- `POST /api/plans/{plan_id}/refresh-context`
- `GET /api/plans/{plan_id}/artifacts/{artifact_id}`
- `PUT /api/plans/{plan_id}/artifacts/{artifact_id}/thesis`

## Phase Order

Recommended build order:

1. Plan assumptions read/edit workspace.
2. Plan health model and Today/Inbox links back to assumptions.
3. Typed artifact/evidence center.
4. Decision ledger enrichment.
5. Scenario diff workspace.
6. Timeline and contribution rules migration.
7. Copilot Plan review surfaces.
8. Browser workflow coverage and classic fallback retirement.

This order gives the app the highest decision-quality improvement first, then deepens the Plan as a durable memory.

---

## Task 1: Add v2 Plan API Wrappers

**Goal:** Let v2 Plan call existing Plan Workspace endpoints without ad hoc fetch code.

**Files:**

- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/lib/api.js`
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`

- [x] **Step 1: Write the failing API wiring test**

Add assertions that `api.js` exposes these methods and endpoint strings:

- `planSettings(id, patch)`
- `planTimeline(id)`
- `updatePlanTimeline(id, body)`
- `planContributionRules(id)`
- `updatePlanContributionRules(id, body)`
- `planAssumptionSets(id)`
- `updatePlanAssumptionSets(id, body)`
- `planScenarioDiff(id, body)`
- `refreshPlanContext(id)`

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
```

Expected: fails because the wrappers do not exist.

- [x] **Step 2: Implement the wrappers**

Use the existing `fetchJson`, `postJson`, `putJson`, and add a local `patchJson` helper:

```js
function patchJson(url, body = {}) {
  return fetchJson(url, {
    method: 'PATCH',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}
```

Add the wrappers to `api`.

- [x] **Step 3: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
```

Expected: all Plan unit tests pass.

---

## Task 2: Build The Plan Assumptions Workspace

**Goal:** Turn the static assumptions ledger into a useful read/edit surface for the assumptions that drive recommendations, scenario quality, and investment fit.

**Files:**

- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/assumptions.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/story.js`
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`

**First fields:**

- annual contribution
- years horizon
- expected return baseline
- inflation rate
- marginal tax rate
- filing status
- withdrawal strategy
- drawdown order
- simulation mode
- active assumption set

- [x] **Step 1: Write a failing render test**

Test that the Plan page can render:

- "Plan assumptions"
- active assumption set name
- current expected return
- current marginal tax rate
- warnings for missing tax rate and missing contribution
- a Save button only when an edit is staged

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
```

Expected: fails because `renderAssumptions` does not exist.

- [x] **Step 2: Implement read-only assumption summary**

Create `renderAssumptions(plan, assumptionState)` with:

- compact field rows
- freshness/weakness labels
- active assumption set summary
- no mutation yet

- [x] **Step 3: Add edit controls**

Use simple form controls:

- number inputs for contribution, years, returns, inflation, tax rate
- select controls for filing status, withdrawal strategy, drawdown order, simulation mode
- select control for active assumption set

Keep staged form state inside `plan.js` under `ui.assumptions`.

- [x] **Step 4: Save settings and assumption-set changes**

On save:

- send changed scalar settings to `PATCH /api/plans/{plan_id}/settings`
- send active assumption set changes to `PUT /api/plans/{plan_id}/assumption-sets`
- reload `api.plan(id)` after save
- preserve existing decision logging from backend

- [x] **Step 5: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
python -m pytest services/orchestrator/tests/test_plan_workspace.py -q
```

Expected: frontend render tests pass and backend plan workspace tests remain green.

---

## Task 3: Add Plan Health

**Goal:** Make Plan explain whether its own advice is decision-grade.

**Files:**

- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/health.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/main.py` only if an aggregate payload is needed
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`
- Test `services/orchestrator/tests/test_recommendation_ranking_integration.py`

**Health signals:**

- missing or stale tax rate
- missing or inconsistent contribution assumptions
- expected return not reviewed recently
- insufficient tracking history
- open stale-assumption recommendation rows
- linked research thesis due or policy-material-change review open
- old accepted decisions with no closure/outcome capture

- [x] **Step 1: Write failing render tests**

Test Plan health renders:

- `Ready`, `Needs review`, or `Weak`
- "Tax assumptions need review" when marginal tax rate is missing
- "Open stale-assumption reviews" when proposed `generator:stale_assumptions` rows exist for the plan
- direct links to `#inbox?focus=...` when rows exist

- [x] **Step 2: Implement client-side health derivation**

Start with data already available from:

- `plan.settings`
- `plan.decisions`
- `plan.artifacts`
- `plan.top_next_actions`
- `api.recommendations({ planId, status: 'proposed' })`
- `api.planTracking(id)`

Avoid a backend aggregate until repeated fetch cost or shape complexity requires it.

- [x] **Step 3: Link Today and Inbox back into Plan assumptions**

Where Today stale-assumption cards point to broad Inbox, keep Inbox as the review queue but ensure Plan-specific actions can link to:

```text
#plan?id=<plan_id>&section=assumptions
```

If route parsing cannot support `section` cleanly yet, add `params.section` handling in `plan.js`.

- [x] **Step 4: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
python -m pytest services/orchestrator/tests/test_recommendation_ranking_integration.py -q
```

Expected: health rendering and Today/Inbox link tests pass.

---

## Task 4: Build The Typed Artifact And Evidence Center

**Goal:** Make plan artifacts inspectable by purpose instead of treating them as an undifferentiated file list.

**Files:**

- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/artifacts.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js`
- Optionally modify `services/orchestrator/src/buildwealth_orchestrator/services/plan_workspace.py` if artifact summaries need stable `kind`
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`
- Test `services/orchestrator/tests/test_plan_workspace.py`

**Artifact buckets:**

- Research dossiers
- Research bridge pins
- Decision packets
- Recommendation closure summaries
- Thesis revisions
- Scenario reports
- General notes

- [x] **Step 1: Write failing artifact classification tests**

Given plan artifacts with `kind`, `file_name`, and `title`, assert:

- research dossiers route to `#research?dossier=...&plan=...`
- thesis review routes to `#research?thesisReview=...&plan=...`
- decision packets show "Decision packet"
- closure summaries show "Outcome/closure"
- unknown artifacts show "General artifact"

- [x] **Step 2: Implement artifact classifier**

Use a small pure function:

```js
export function classifyPlanArtifact(artifact = {}) {
  const kind = String(artifact.kind || '').toLowerCase();
  const title = String(artifact.title || '').toLowerCase();
  const fileName = String(artifact.file_name || '').toLowerCase();
  if (kind === 'research_dossier' || fileName.includes('-research-dossier-') || title.startsWith('research dossier')) {
    return 'research_dossier';
  }
  if (kind === 'research_bridge') return 'research_bridge';
  if (title.includes('decision packet')) return 'decision_packet';
  if (title.includes('closure') || title.includes('outcome')) return 'closure_summary';
  if (title.includes('scenario')) return 'scenario_report';
  return 'general';
}
```

- [x] **Step 3: Render artifact cards**

Each card should include:

- type label
- title
- created date
- primary route
- secondary route when useful
- packet citations if already available in artifact preview/content

- [x] **Step 4: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
```

Expected: artifact classification and route rendering pass.

---

## Task 5: Enrich The Decision Ledger

**Goal:** Connect decisions to recommendations, expected outcomes, scenario previews, evidence, and closure history.

**Files:**

- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/decisions.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/artifacts.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/main.py` only if decision payloads need stable recommendation references
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`
- Test `services/orchestrator/tests/test_recommendation_actions.py`

**Decision row should show when available:**

- status
- rationale
- source recommendation id
- linked artifact id
- expected outcome summary
- scenario preview summary
- outcome captured/not captured
- "Open in Inbox" link when recommendation id exists
- "Open artifact" link when artifact id exists

- [x] **Step 1: Write failing decision render tests**

Assert that a decision containing recommendation metadata renders:

- recommendation link
- decision packet link
- closure summary link
- expected outcome text

- [x] **Step 2: Implement enriched decision display**

Keep the existing editorial list, but add compact metadata rows below the rationale.

- [x] **Step 3: Add missing-backlink detection**

If a decision has an accepted/applied status but no outcome/closure artifact, show:

```text
Outcome not captured yet
```

and link to Inbox when a recommendation id is present.

- [x] **Step 4: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
python -m pytest services/orchestrator/tests/test_recommendation_actions.py -q
```

Expected: decision ledger tests pass and recommendation action persistence remains green.

---

## Task 6: Build v2 Scenario Diff Workspace

**Goal:** Let the user compare plan changes before accepting them, using the existing scenario diff contract.

**Files:**

- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/scenarios.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/lib/api.js`
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`
- Test existing backend scenario tests around plan diff

**First scenario fields:**

- annual contribution
- expected return
- inflation
- marginal tax rate
- years horizon
- current portfolio value override
- base assumption set
- candidate assumption set

- [ ] **Step 1: Write failing scenario render test**

Assert that a scenario form can render, stage a candidate contribution, and call:

```text
POST /api/plans/{plan_id}/scenario-diff
```

with:

```json
{
  "compare_settings": {
    "annual_contribution_usd": 30000
  }
}
```

- [ ] **Step 2: Implement scenario form state**

Store scenario diff form state under `ui.scenarios`.

- [ ] **Step 3: Render result summary**

Show:

- candidate vs base settings
- scenario deltas
- Monte Carlo delta when present
- simulation delta when present
- warnings/errors

Use compact rows instead of charts in the first slice.

- [ ] **Step 4: Add decision handoff**

When a scenario diff is useful, offer:

- "Discuss in Copilot"
- "Save decision note"
- "Open related Inbox recommendation" when focused from a recommendation

Do not apply settings automatically from the scenario diff surface.

- [ ] **Step 5: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
python -m pytest services/orchestrator/tests -q
```

Expected: scenario unit tests pass and backend suite remains green.

---

## Task 7: Migrate Timeline And Contribution Rules

**Goal:** Move high-frequency planning structure edits into v2.

**Files:**

- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/timeline.js`
- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan/contributions.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/lib/api.js`
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs`
- Test `services/orchestrator/tests/test_plan_workspace.py`

**Timeline first slice:**

- retirement age
- retirement year when available
- major events list
- withdrawal strategy
- drawdown order

**Contribution rules first slice:**

- account allocation rows
- contribution priority
- annual limits/targets where already represented

- [ ] **Step 1: Write failing timeline render/save tests**

Assert v2 Plan can load timeline, render retirement age, stage a change, and call `PUT /api/plans/{plan_id}/timeline`.

- [ ] **Step 2: Write failing contribution render/save tests**

Assert v2 Plan can load contribution rules, render account allocation rows, stage a change, and call `PUT /api/plans/{plan_id}/contribution-rules`.

- [ ] **Step 3: Implement timeline module**

Keep timeline edits small. Use an "Edit timeline" disclosure rather than permanently open forms.

- [ ] **Step 4: Implement contributions module**

Render dense, operational rows. Do not make this a marketing-style card layout.

- [ ] **Step 5: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan.test.mjs
python -m pytest services/orchestrator/tests/test_plan_workspace.py -q
```

Expected: timeline/contribution tests pass and existing Plan Workspace persistence stays green.

---

## Task 8: Connect Copilot To Plan Review

**Goal:** Let Copilot discuss the plan with structured context without ballooning history.

**Files:**

- Modify `services/orchestrator/src/buildwealth_orchestrator/main.py`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/copilot.js`
- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/copilot/thread.js`
- Test `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/copilot_thread.test.mjs`
- Test `services/orchestrator/tests/test_copilot_tool_updates.py`

**Copilot prompts:**

- "Review plan assumptions"
- "Explain this scenario diff"
- "Draft a decision note"
- "Review stale assumptions"
- "Explain why this thesis affects the plan"

**Context management rule:**

Copilot should receive bounded plan context:

- plan id/title
- active assumption set summary
- top 5 weak/stale plan health signals
- selected artifact ids/citations
- selected scenario diff result summary

Do not send full artifact contents or long decision history unless the user opens a specific artifact/revision.

- [ ] **Step 1: Write failing Copilot prompt test**

Assert the Copilot Plan prompt includes plan id, active assumption set, and selected health signals, but does not include all artifacts.

- [ ] **Step 2: Add route prompts**

Add Plan buttons that navigate to:

```text
#copilot?intent=review_plan_assumptions&plan=<plan_id>
#copilot?intent=explain_scenario_diff&plan=<plan_id>
```

- [ ] **Step 3: Render Plan trace cards**

When Copilot uses Plan tools, render a compact trace card with:

- assumptions reviewed
- gaps found
- suggested next step
- linked Plan section

- [ ] **Step 4: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/copilot_thread.test.mjs
python -m pytest services/orchestrator/tests/test_copilot_tool_updates.py -q
```

Expected: Copilot Plan prompt and trace tests pass.

---

## Task 9: Add Browser-Level Plan Workflow Coverage

**Goal:** Protect the migrated Plan workflows from regression.

**Files:**

- Create `services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan_workspace.spec.mjs`
- Create or extend `services/orchestrator/tests/test_web_v2_plan_browser.py`

**Browser workflows:**

- open v2 Plan
- edit a core assumption
- save and verify decision log updated
- open artifact center and route to research dossier
- run a scenario diff
- append a decision
- open Copilot plan-review prompt

- [ ] **Step 1: Write Playwright test with mocked API routes**

Use the existing v2 browser-test pattern. Keep the mocked API payloads small and specific.

- [ ] **Step 2: Add pytest wrapper**

Use the existing `test_web_v2_*_browser.py` pattern so the browser test runs in the full backend test suite.

- [ ] **Step 3: Verify browser flow**

Run:

```bash
./node_modules/.bin/playwright test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/plan_workspace.spec.mjs --browser=chromium --reporter=line
python -m pytest services/orchestrator/tests/test_web_v2_plan_browser.py -q
```

Expected: browser workflow passes. In the Codex sandbox, Chromium may need an elevated run because of macOS Mach port permissions.

---

## Task 10: Retire High-Frequency Classic Links

**Goal:** Make classic Plan links rare fallback paths, not the normal workflow.

**Files:**

- Modify `services/orchestrator/src/buildwealth_orchestrator/web-v2/views/plan.js`
- Modify docs:
  - `docs/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md`
  - `docs/INVESTMENT_FIT_RESEARCH_PLAN_2026-04-26.md`

- [ ] **Step 1: Inventory remaining classic links**

Search:

```bash
rg -n 'href="/#plans|classic plan|Browse artifacts|Look closer' services/orchestrator/src/buildwealth_orchestrator/web-v2 docs
```

- [ ] **Step 2: Replace migrated links**

Remove or demote classic links for:

- settings
- timeline
- contribution rules
- scenario diff
- decisions
- artifacts

Keep advanced branch/withdrawal tools in fallback until they have v2 surfaces.

- [ ] **Step 3: Update docs**

Mark migrated Plan Workspace slices complete in:

- `docs/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md`
- `docs/INVESTMENT_FIT_RESEARCH_PLAN_2026-04-26.md`

- [ ] **Step 4: Verify**

Run:

```bash
node --test services/orchestrator/src/buildwealth_orchestrator/web-v2/tests/*.test.mjs
python -m pytest services/orchestrator/tests -q
git diff --check
```

Expected: all tests pass and docs reflect the current Plan migration state.

---

## Acceptance Criteria

Plan Workspace migration is complete enough for this phase when:

- v2 Plan displays and edits core assumptions.
- v2 Plan shows plan health and why confidence is weak or strong.
- v2 Plan exposes typed artifacts and routes research artifacts into v2 Research.
- v2 Plan decisions connect to recommendations, evidence, scenario previews, and outcomes.
- v2 Plan can run a scenario diff for common assumption changes.
- Timeline and contribution rules have first-class v2 surfaces.
- Copilot can discuss a bounded Plan context without full-history bloat.
- Browser tests cover the normal Plan review workflow.
- Classic Plan links remain only for advanced or low-frequency tools.

## Near-Term Recommendation

Start with Tasks 1 and 2.

That gives the app the most leverage fastest: stale assumptions, investment-fit confidence, Today readiness, scenario quality, and Copilot answers all depend on the plan assumptions being visible and editable in the v2 vocabulary.

After Tasks 1 and 2 pass, do Task 3 immediately. Plan health is what turns assumptions from static settings into decision quality.

## Execution Checkpoints

Checkpoint after Task 2:

- User can view and edit core assumptions in v2.
- Saves write through existing backend contracts.
- Decision log records assumption changes.

Checkpoint after Task 4:

- Plan can explain linked research evidence and decision artifacts.
- Today/Inbox/Research/Plan are connected for thesis and dossier workflows.

Checkpoint after Task 6:

- User can review a proposed plan change through scenario diff before applying.

Checkpoint after Task 9:

- Browser workflow proves the migrated Plan loop works end to end.

## Non-Goals For This Migration

- No automatic trading.
- No hidden AI "buy/sell" decisions.
- No full tax optimizer inside Plan.
- No wholesale backend rewrite.
- No giant one-shot Plan page redesign.
- No duplicating Research packet detail inside Plan when a link to v2 Research is enough.
- No sending full plan history into Copilot by default.

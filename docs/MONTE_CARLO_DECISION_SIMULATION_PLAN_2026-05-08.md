# BuildWealth Monte Carlo Decision Simulation Plan

## Date
2026-05-08

## Status
Active feature planning and implementation guide for making BuildWealth's simulations decision-grade while preserving BuildWealth's decision-system positioning.

This document expands the Plan, Inbox, Copilot, and recommendation-quality pillars in:
- [BuildWealth Future State Product Plan](./FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md)
- [Native Portfolio and Plan Modules Implementation Guide](./NATIVE_PORTFOLIO_PLAN_MODULES_IMPLEMENTATION_GUIDE_2026-05-08.md)

## Product Position

BuildWealth should not merely copy a retirement calculator.

The target product position is:

> BuildWealth uses Monte Carlo simulation to show where a financial plan is resilient, where it can fail, and which reviewable action is most likely to improve the user's future.

Dedicated retirement planners make Monte Carlo simulations, historical backtests, tax estimation, and explanations feel approachable. BuildWealth can match or exceed that outcome because the local scenario engine already has fixed, stochastic, historical, and Monte Carlo modes, plus tax/account timelines, withdrawal strategy hooks, RMDs, Social Security, Roth conversion fields, and plan decision evidence.

The BuildWealth opportunity is to make Monte Carlo more valuable than a single probability number. The simulation should feed a decision loop:

1. Run the plan through many possible futures.
2. Identify the failure modes and fragile years.
3. Explain the drivers in plain language.
4. Suggest specific reviewable what-if changes.
5. Let the user compare those changes before changing the active plan.
6. Save the result as evidence behind a plan decision or recommendation.

Example target experience:

> Your Plan Strength is Workable, but the weak point is 2034-2039 because taxable assets deplete before Social Security starts. The highest-value reviews are delaying retirement by one year, reducing spending by $8k/year, or changing withdrawal order. Simulate those now?

## Quality Bar

Monte Carlo quality is not a single algorithm. It is the combined quality of model coverage, return assumptions, tax/cash-flow mechanics, validation, explanation, and UX.

BuildWealth should treat a simulation as decision-grade only when it can answer:

- What assumptions were used?
- What return model was used?
- How many trials were run?
- What percentiles matter?
- What counts as plan failure?
- Which years and accounts are most fragile?
- Which inputs are missing, stale, or weak?
- Which action would likely improve the outcome?
- What evidence should be saved if the user acts?

## Current Foundation

BuildWealth already has enough scaffolding to start from a strong position.

Existing foundation:

- `ScenarioEngine` supports fixed, stochastic, historical, and Monte Carlo modes.
- Monte Carlo runs are seeded for reproducibility.
- Current outputs include p10, p50, and p90 terminal values.
- Historical return data exists through the local scenario engine.
- Scenario runs already support accounts, income, expenses, debt, timeline events, contributions, Social Security, RMDs, filing status, state tax rate, IRMAA toggle, Roth conversions, drawdown order, and withdrawal strategy.
- Plan workspace supports assumption sets, scenario diffs, branch templates, decisions, evidence records, and simulation settings.
- v2 Plan should organize these into Overview, Simulations, What-ifs, Strategies, Assumptions, Timeline, and Decisions.

Current gaps:

- The current Monte Carlo helper is terminal-value oriented.
- Monte Carlo does not yet run the full annual account/tax/cash-flow engine per trial.
- Outputs do not yet include full percentile timelines, Plan Strength, funded-trial rate, failure-year distribution, or failure-mode summaries.
- Return models are not exposed as a clear simulation-provider interface.
- Historical backtests and Monte Carlo are not yet visually unified in Plan.
- Recommendation and Inbox flows do not yet routinely use simulation failure modes as evidence.
- The UI does not yet make the simulation feel as clear and consumer-ready as a dedicated planning product.

## Product Boundary

BuildWealth should use simulation for education, planning, review, and decision support.

BuildWealth should not:

- present Monte Carlo as certainty
- hide weak assumptions behind a polished probability
- automatically mutate the active plan
- produce unreviewed financial, investment, tax, or legal advice
- make a funded-trial percentage look more precise than the data supports

Allowed product language:

- "This plan appears workable under..."
- "The most common failure mode is..."
- "This assumption has high impact..."
- "Review these what-if changes before acting..."
- "This result needs review because..."

Avoid:

- "You are safe."
- "This guarantees retirement success."
- "You should definitely..."
- "AI recommends..."

## Target User Workflows

### Workflow 1: Run The Active Plan

The user opens Plan -> Simulations and runs the active plan through Monte Carlo.

The result should show:

- Plan Strength
- funded-trial rate
- median ending value
- p10, p25, p50, p75, and p90 ending values
- fan chart over time
- first failure-year distribution
- worst five-year stretch
- fragile years
- account depletion order
- tax/withdrawal pressure points
- missing or stale inputs

The result should answer:

> Am I generally on track, and where could this plan break?

### Workflow 2: Compare A Decision Lever

The user chooses a lever such as:

- retire one year later
- save $500/month more
- spend $8k/year less in retirement
- change withdrawal order
- start Social Security at a different age
- add or reduce Roth conversions
- change asset allocation return assumptions
- model a job loss or home purchase branch

BuildWealth runs a side-by-side comparison against the active plan and explains:

- change in Plan Strength
- change in funded-trial rate
- change in median ending value
- change in p10 outcome
- change in failure years
- tradeoffs and new risks
- whether the result is strong enough to save as a Saved Simulation

### Workflow 3: Generate A Simulation-Backed Recommendation

The recommendation engine detects a fragile plan area and creates an Inbox item.

Example:

> Review retirement spending flexibility. Monte Carlo shows the active plan falls below the cash reserve target in 28% of trials, usually between ages 62 and 67. Reducing retirement spending by $8k/year improves the p10 ending value by $210k and lowers early-depletion risk.

The recommendation should include:

- trigger
- simulation inputs
- result summary
- expected impact
- reversibility
- downside
- review route
- Saved Simulation link
- outcome capture prompt

### Workflow 4: Ask Copilot What Changed

The user asks:

> Why did my Plan Strength fall?

Copilot should retrieve the latest Saved Simulation, current plan assumptions, profile freshness, portfolio changes, and recommendation history.

Copilot should explain:

- which input changed
- whether the change came from market movement, spending, income, tax assumptions, plan timeline, or model settings
- whether the answer is decision-grade
- which review flow should happen next

Copilot should not invent a hidden simulation. If a fresh run is needed, it should offer to run one through the same API used by Plan.

## Simulation Engine Architecture

### Module: Simulations

Add a focused engine module:

`services/orchestrator/src/buildwealth_orchestrator/services/plan_simulation_engine.py`

Purpose:

- run full-path Monte Carlo trials
- produce percentile timelines
- calculate success/failure metrics
- preserve deterministic reproducibility through seeds
- keep return-provider logic separate from plan cash-flow mechanics

The existing `scenario_engine.py` should remain the deterministic and scenario-comparison foundation while the new module extracts richer simulation behavior. Over time, `ScenarioEngine` can delegate Monte Carlo paths to `PlanSimulationEngine`.

### Module: Return Providers

Add return-provider helpers behind a small interface:

`services/orchestrator/src/buildwealth_orchestrator/services/return_providers.py`

Initial providers:

- `fixed`: constant annual return for deterministic projections
- `normal`: annual Gaussian draws using expected return and volatility
- `lognormal`: bounded positive-skew model for portfolio returns
- `historical_sequence`: contiguous historical backtest from a selected year
- `historical_bootstrap`: random historical years or blocks with replacement
- `stress`: explicit bad-sequence provider for sequence-of-returns review

Each provider should return:

- annual nominal return
- annual inflation assumption where available
- provider metadata
- warnings when assumptions are weak

### Module: Simulation Analyzer

Add an analyzer module:

`services/orchestrator/src/buildwealth_orchestrator/services/plan_simulation_analyzer.py`

Purpose:

- extract Plan Strength and funded-trial rate
- calculate failure-year distribution
- identify fragile years
- summarize account depletion sequences
- compare candidate vs baseline
- produce plain-language explanation payloads
- create chart-ready series for v2 Plan

The analyzer should not mutate plan state. It should turn raw simulation outputs into decision-ready evidence.

### Module: Saved Simulations

Use the existing Plan evidence pattern, then add a dedicated store only if Saved Simulation volume or lookup needs outgrow `PlanWorkspace`.

Saved Simulations should include:

- plan id
- assumption set id
- simulation config
- seed
- return provider
- run count
- input freshness summary
- output metrics
- percentile timelines
- driver summary
- warnings
- linked recommendation or decision ids

## Data Contract

Add typed schemas in `schemas.py` for user-facing simulation contracts.

Suggested request model:

`PlanSimulationRunRequest`

Core fields:

- `plan_id`
- `scenario_id`
- `assumption_set_id`
- `mode`
- `return_provider`
- `run_count`
- `seed`
- `start_year`
- `start_age`
- `retirement_age`
- `success_floor_usd`
- `cash_reserve_floor_months`
- `failure_definition`
- `candidate_plan_updates`
- `save_simulation`

Suggested response model:

`PlanSimulationRunResponse`

Core fields:

- `run_id`
- `plan_id`
- `status`
- `decision_grade`
- `input_quality`
- `config`
- `summary`
- `percentile_timelines`
- `failure_analysis`
- `driver_analysis`
- `account_analysis`
- `tax_analysis`
- `warnings`
- `recommended_plan_levers`
- `saved_simulation_id`

Suggested summary fields:

- `plan_strength_label`
- `funded_trial_rate_pct`
- `median_ending_balance_usd`
- `p10_ending_balance_usd`
- `p90_ending_balance_usd`
- `median_real_ending_balance_usd`
- `first_failure_year_median`
- `trials_failed_count`
- `trials_run_count`

## API Routes

Add routes near existing Plan and planning routes.

Suggested routes:

- `POST /api/plans/{plan_id}/simulation/run`
- `POST /api/plans/{plan_id}/simulation/compare`
- `GET /api/plans/{plan_id}/simulations/saved`
- `GET /api/plans/{plan_id}/simulations/saved/{saved_simulation_id}`
- `POST /api/plans/{plan_id}/simulations/saved/{saved_simulation_id}/decision`

Keep existing routes stable:

- `/api/planning/scenarios`
- `/api/plans/{plan_id}/scenario-diff`
- `/api/plans/{plan_id}/scenario-branch`
- withdrawal comparison routes

Existing routes can call the richer simulation engine later, but the first slice should avoid breaking current consumers.

## v2 UI Plan

### Plan -> Simulations

Add the primary simulation view here.

It should show:

- Plan Strength headline
- funded-trial rate
- fan chart
- ending-balance percentile cards
- fragile years
- input-quality warnings
- "Run fresh simulation" action
- "Save simulation" action

### Plan -> Simulations

Add comparison flows here.

It should show:

- baseline vs candidate Plan Strength
- p10/p50/p90 deltas
- failure-year delta
- driver explanation
- decision handoff

### Plan -> What-ifs

Add template-to-simulation flow here.

The user should be able to choose templates such as:

- early retirement
- job loss
- home purchase
- one-income household
- high-tax retirement
- Roth conversion ladder
- market stress

The branch result should be previewed before it touches the active plan.

### Plan -> Decisions

Saved Simulations should become decision evidence.

A decision record should show:

- what was compared
- simulation result
- expected benefit
- main risk
- review date
- disconfirming signal
- linked recommendation if any

### Inbox

Simulation-backed recommendations should route directly to the relevant Plan section with the Saved Simulation in focus.

### Today

Today should summarize simulation readiness, not the full simulation.

Possible card:

> Plan Strength needs review. Last simulation is 53 days old and profile expenses changed materially. Run a fresh simulation before relying on retirement confidence.

## Copilot Behavior

Copilot should use simulation as a tool, not as a parallel calculator.

Copilot can:

- explain Saved Simulations
- run a fresh simulation through the official API
- compare proposed changes
- draft a recommendation from a simulation result
- draft a plan decision with pre-mortem fields
- identify missing context that blocks decision-grade simulation

Copilot should not:

- invent Plan Strength or funded-trial numbers
- silently change plan assumptions
- treat stale simulations as current
- override weak or missing input warnings

Every Copilot simulation answer should be able to expose:

- plan id
- Saved Simulation id or Simulation Run id
- seed
- run count
- return provider
- input quality warnings
- timestamp

## Recommendation Factory Integration

Add simulation-backed recommendation generators after the first full simulation response is stable.

Initial generators:

- `generator:plan_strength_review`
- `generator:fragile_year_review`
- `generator:withdrawal_order_review`
- `generator:spending_flexibility_review`
- `generator:simulation_stale_after_material_change`

Recommended action language should stay review-oriented.

Examples:

- "Review retirement spending flexibility"
- "Compare withdrawal orders before relying on this plan"
- "Run a fresh simulation after expense changes"
- "Review Social Security claiming age sensitivity"
- "Save a decision if this branch becomes the active plan"

## Validation Plan

Simulation credibility needs tests beyond ordinary unit coverage.

### Determinism Tests

- same seed and config produce the same result
- different seed changes stochastic paths
- fixed mode produces no stochastic drift

### Distribution Tests

- p10 <= p50 <= p90
- higher expected return usually increases median output
- higher volatility increases dispersion
- more trials stabilizes percentile estimates within tolerance

### Historical Tests

- selected historical start year produces expected return sequence
- bootstrap provider samples from allowed years only
- stress provider includes severe early negative-return years

### Cash-Flow Tests

- income/expense changes alter failure rates
- contribution changes alter accumulation outcomes
- retirement spending changes alter depletion outcomes
- debt and timeline events affect fragile years

### Tax And Account Tests

- taxable, tax-deferred, and Roth accounts follow expected withdrawal behavior
- RMDs affect tax-deferred account timelines
- Roth conversions affect tax-deferred and Roth balances
- state tax and IRMAA settings change tax outputs

### UX Contract Tests

- Plan renders Plan Strength, fan chart data, warnings, and recommended what-if changes
- scenario compare renders baseline/candidate deltas
- Saved Simulations route to Decisions and Inbox
- Copilot links to Simulation Run or Saved Simulation instead of uncited numbers

### Outcome Tests

Create fixture scenarios that prove the same or better user outcomes through BuildWealth contracts:

- accumulation-only FIRE plan
- retirement drawdown plan
- Roth conversion window
- delayed retirement by one year
- reduced retirement spending
- early bad market sequence

These tests should compare qualitative behavior and broad numeric ranges, not copied implementation details.

## Phased Implementation

### Phase 1: Full-Path Monte Carlo Service

Goal:

Move from terminal-value Monte Carlo to full annual path simulation.

Build:

- `return_providers.py`
- `plan_simulation_engine.py`
- p10/p25/p50/p75/p90 percentile timelines
- Plan Strength
- funded-trial rate
- failure-year distribution
- deterministic seed behavior
- backend tests for core engine behavior

Acceptance:

- the engine can run 1,000 trials for a realistic plan and return stable chart-ready output
- the response includes warnings when inputs are missing or weak
- existing `ScenarioEngine` behavior stays compatible

### Phase 2: Simulation Analyzer And API

Goal:

Turn raw simulation paths into user-facing evidence.

Build:

- `plan_simulation_analyzer.py`
- `PlanSimulationRunRequest`
- `PlanSimulationRunResponse`
- `/api/plans/{plan_id}/simulation/run`
- `/api/plans/{plan_id}/simulation/compare`
- Saved Simulation save/read behavior
- service and route tests

Acceptance:

- a run explains Plan Strength, fragile years, and recommended what-if changes
- compare response explains what improved or worsened
- Saved Simulations can be retrieved by Plan and Copilot

### Phase 3: v2 Plan Experience

Goal:

Make simulation understandable without Copilot.

Build:

- Plan -> Simulations panel
- fan chart data rendering
- percentile cards
- fragile-year list
- recommended what-if changes
- save simulation action
- Plan -> Simulations comparison panel
- browser tests for run, compare, save, and focus routes

Acceptance:

- a user can run and understand the active plan simulation from v2 Plan
- a user can compare at least one lever without editing JSON
- a user can save the result as evidence

### Phase 4: Decision And Recommendation Loop

Goal:

Connect simulation quality to BuildWealth's differentiating decision loop.

Build:

- simulation-backed recommendation generators
- Inbox review cards
- Plan decision handoff
- pre-mortem prompts for high-impact simulation decisions
- outcome capture fields linked to the saved simulation
- Today stale-simulation and fragile-plan cards

Acceptance:

- a simulation result can become a reviewable recommendation
- an accepted decision preserves the simulation evidence
- Today warns when the simulation is stale after material changes

### Phase 5: Copilot Tooling

Goal:

Let Copilot operate the same reviewed simulation workflows.

Build:

- Copilot simulation run tool
- Copilot simulation compare tool
- Saved Simulation explanation prompts
- missing-context handling
- tool trace display
- tests proving Copilot cites Simulation Run or Saved Simulation ids

Acceptance:

- Copilot can answer "why did my Plan Strength change?" from Saved Simulations and current context
- Copilot can run a fresh simulation only through official APIs
- Copilot can draft, but not silently apply, plan changes

## Consumer Value Opportunities

BuildWealth can exceed ordinary retirement calculators if it owns these moments:

**From probability to action**

Do not stop at a funded-trial percentage. Show what could improve the plan and how much.

**From generic model to personal reality**

Use actual profile, cash, debt, portfolio, account, tax, and recommendation context.

**From one-time calculator to living system**

Warn when the last simulation is stale because income, expenses, portfolio, tax settings, or plan assumptions changed.

**From AI explanation to evidence trail**

Every important explanation should point to a Simulation Run, Saved Simulation, recommendation, or decision.

**From hidden complexity to confidence**

Show the user what is decision-grade, what is weak, and what needs review before relying on the projection.

## Acceptance Criteria

This feature is ready when:

- BuildWealth can run full annual Monte Carlo paths over account, tax, income, expense, contribution, withdrawal, RMD, Social Security, and Roth conversion mechanics.
- The Plan UI shows Plan Strength, funded-trial rate, percentile timelines, failure modes, and recommended what-if changes.
- Historical backtests and Monte Carlo outputs are explainable in the same Plan workspace.
- Saved Simulations can be linked to decisions and recommendations.
- Copilot can explain and operate simulation runs without becoming a separate source of truth.
- Tests cover deterministic behavior, percentile ordering, historical sequences, cash-flow sensitivity, tax/account behavior, API contracts, and primary v2 UI flows.
- User-facing language avoids certainty and frames outputs as decision support.

## First Build Slice

The recommended first slice is:

- [ ] Add `return_providers.py` with fixed, normal, historical sequence, and historical bootstrap providers.
- [ ] Add `plan_simulation_engine.py` that runs full annual paths using existing account/tax/cash-flow helpers where possible.
- [ ] Return p10/p25/p50/p75/p90 timelines and terminal values.
- [ ] Return Plan Strength, funded-trial rate, and first-failure-year distribution.
- [ ] Add backend tests for determinism, percentile ordering, historical sequence selection, and contribution/spending sensitivity.
- [ ] Keep existing `ScenarioEngine.run(...)` and `/api/planning/scenarios` compatible.

This slice creates the real engine foundation without forcing a UI migration in the same step.

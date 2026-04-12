# BuildWealth Standalone Build Plan

## Date: 2026-04-10

## Strategic Direction

**BuildWealth is becoming a standalone single-user financial command center with targeted engine reuse.** Python remains the control plane and system of record, while selected high-complexity calculations are delegated to local TypeScript sidecars adapted from Ghostfolio (portfolio analytics) and Ignidash (planning/tax simulation).

Both Ghostfolio and Ignidash are MIT licensed, which permits us to:
- Read and reference their source code on GitHub
- Port algorithms to Python when needed
- Reuse logic in sidecar services with adapter contracts
- Borrow their data schemas and test cases
- Use their broker CSV templates and asset class taxonomies

We must:
- Add an `ATTRIBUTIONS.md` to the repo acknowledging both projects and their copyright holders
- Keep the MIT license attribution for any substantial code we adapt

## Why This Approach (vs. Full Rewrite)

We considered four options:

### Option A: Full TypeScript-to-Python Rewrite
Rebuild all mature Ghostfolio/Ignidash logic in Python.
- **Pros:** One language in runtime path
- **Cons:** High parity risk, long validation cycle, large maintenance burden

### Option B: BuildWealth as Thin Orchestration Layer
Keep full Ghostfolio and Ignidash apps as runtime dependencies.
- **Pros:** Maximum upstream behavior fidelity
- **Cons:** Multi-app operations burden and tighter coupling to external app boundaries

### Option C: Dual Path (Both Rewrite + Integrations)
Maintain complete local rewrite while also preserving integration stack.
- **Pros:** Flexibility
- **Cons:** Highest complexity and long-term maintenance cost

### Option D: Targeted Sidecar Reuse (CHOSEN)
Keep Python as source of truth; use local sidecars for high-complexity domains behind strict versioned adapter contracts.
- **Pros:** Single BuildWealth UX, faster parity in hard domains, bounded operational complexity
- **Cons:** Requires robust contract governance and degraded-mode handling

**Decision:** Option D. This keeps the product single-entrypoint while avoiding unnecessary reimplementation of mature financial engines.

## Execution Constraints

These decisions refine the build plan based on the current repository and upstream source reality:

- **Breaking schema/API changes are allowed early.** We will move schema, migration, and UI contract changes into Sprint 1 instead of deferring them.
- **Ghostfolio and Ignidash sidecars are intentional architecture, not temporary shims.** We will keep sidecars only for high-complexity domains where reuse beats rewrite, with explicit contracts and fallback behavior.
- **Upstream reuse should be selective, not literal.** Ghostfolio is most useful for import/account/asset metadata patterns and test fixtures; Ignidash is most useful for tax, account, contribution, and simulation logic.
- **Migration is a foundation task, not polish.** New ledger and planner models should replace the current simplified contracts early, with explicit migrations for stored portfolio, plan, and profile data.
- **Contract-first integration is mandatory.** Adapter/sidecar payloads must be schema-versioned under `contracts/engine/v{n}` and validated on request/response boundaries.

---

## Progress Log

### 2026-04-10 (Completed - Architecture Draft)
- Added architecture decision update in `docs/DECISIONS.md` selecting targeted sidecar reuse
- Added `docs/SIDECAR_ADAPTER_ARCHITECTURE.md` blueprint for adapter boundaries, contracts, fallback, and rollout
- Added initial engine contract schemas under `contracts/engine/v1` for Ghostfolio benchmark and Ignidash scenario endpoints

### 2026-04-10 (Completed - Sidecar Foundation v1)
- Added adapter base utility (`engine_adapter.py`) with contract validation, timeout handling, and retry policy for sidecar calls
- Added Ghostfolio benchmark service (`portfolio_benchmark.py`) that builds contract payloads from local snapshot history and supports sidecar + local degraded fallback
- Added portfolio benchmark API endpoint (`GET /api/portfolio/benchmark`) and associated sidecar feature flags/settings
- Added unit coverage for adapter transport/validation behavior and benchmark service sidecar/fallback execution paths

### 2026-04-10 (Completed - Planning Sidecar v1)
- Added Ignidash scenario sidecar service (`planning_sidecar.py`) with contract payload construction, response mapping, and local fallback behavior
- `/api/planning/scenarios` now routes through sidecar integration when enabled and falls back to local scenario engine when unavailable
- Planning response now includes engine metadata (`engine`, `engine_status`, `fallback_method`, `warnings`) for degraded-path transparency
- Added unit coverage for sidecar disabled/success/failure paths in `test_planning_sidecar.py`

### 2026-04-10 (Completed - Benchmark Overlay UI)
- Portfolio history panel now fetches benchmark comparison data from `GET /api/portfolio/benchmark` alongside snapshot history
- Added benchmark symbol controls and chart overlay rendering (portfolio value line + benchmark-scaled line)
- Added benchmark summary line showing benchmark return, alpha, and engine status/fallback metadata

### 2026-04-11 (Completed - Engine Health Hardening)
- Added `EngineStatusTracker` with startup and periodic sidecar probes plus degraded-path counters for benchmark/planning engines
- Added `GET /api/engines/status` for runtime engine visibility (`enabled`, `reachable`, `contract_version`, `degraded_count`, `last_error`)
- Probes now use upstream-informed health conventions:
  - Ghostfolio supports `GET /api/v1/health`
  - Ignidash self-hosting health checks use `GET /api/health` for app and `/version` for Convex backend
- Benchmark and planning routes now increment degraded counters whenever sidecar execution falls back to local logic

### 2026-04-11 (Completed - Engine Status UI)
- Today dashboard now fetches `GET /api/engines/status` and renders engine telemetry cards (enabled, reachable, degraded events, probe age)
- Added engine detail panel with per-engine health badge, contract version, degraded count, and last error visibility
- Added explicit “Refresh Engine Status” action that triggers live probe refresh via `?refresh=true`

### 2026-04-11 (Completed - Attribution Sidecar Foundation)
- Added Ghostfolio attribution adapter service (`portfolio_attribution.py`) with request/response contracts and local degraded fallback
- Added `GET /api/portfolio/attribution` endpoint plus engine degraded counter wiring under `ghostfolio_attribution`
- Added v1 engine contracts for attribution (`ghostfolio.attribution.request/response.schema.json`)
- Portfolio UI now fetches attribution payloads and renders top contributors/detractors with contribution and allocation context
- Added unit coverage for sidecar disabled/success/failure paths in `test_portfolio_attribution.py`

### 2026-04-11 (Completed - Tax Engine Foundation)
- Added federal tax engine foundation (`tax_engine.py`) adapted from Ignidash tax calculators and tax-data tables
- Implemented 2026 ordinary-income brackets, standard deduction, LTCG bracket stacking, NIIT, Social Security taxable-income handling, and FICA withholding estimates
- Added planning endpoint `POST /api/planning/tax-estimate` for callable tax breakdowns
- Added focused tax engine unit coverage in `test_tax_engine.py` (ordinary income, capital gains/NIIT, Social Security taxability, year-fallback behavior)

### 2026-04-11 (Completed - Contribution Rule Prioritization Foundation)
- Added contribution allocation engine (`contribution_rules.py`) adapted from Ignidash ranked-rule and shared-limit logic (`contribution-rules.ts`, `contribution-form-schema.ts`)
- Added planning endpoint `POST /api/planning/contribution-allocation` with support for rule-based allocation and default `tax_optimized_high_earner` profile generation
- Planner scenario-diff flows now consume plan contribution rules and pass per-account annual contributions into the Ignidash sidecar request payload when rules are present
- Planning responses now include `contribution_allocation` metadata so scenario output can show effective employee + employer funded contribution totals
- Added focused coverage in `test_contribution_rules.py` and extended sidecar request coverage in `test_planning_sidecar.py`

### 2026-04-11 (Completed - Physical Assets Foundation)
- Financial health model now includes `physical_assets` from financial profile in net-worth computation (`net_worth = portfolio + physical_assets - debt`)
- Added explicit health-response breakdown fields for `physical_assets_value_usd` and `total_assets_usd`
- Today dashboard financial-health enrichment now passes profile physical assets through to health computation
- Added compatibility alias on financial profile store (`load()`) for existing API handlers
- Added/updated focused tests in `test_financial_health.py` for physical-asset net-worth inclusion and response counts

### 2026-04-11 (Completed - Income Modeling Foundation)
- Added income projection service (`income_projection.py`) with growth-rate and active-date window handling for profile income items
- Added planning endpoint `POST /api/planning/income-projection` to generate year-by-year income curves from either provided inputs or saved profile data
- Planning scenario route now includes projected first-year income in Ignidash baseline assumptions and attaches projection payload in sidecar metadata
- Plan scenario-diff flows now generate and pass base/candidate income projections so planning responses include model context for income assumptions
- Added `income_projection` field on planning responses and focused coverage in `test_income_projection.py` and `test_planning_sidecar.py`

### 2026-04-11 (Completed - Income Modeling UI Wiring)
- Profile UI income builder now captures `annual_growth_rate`, `start_date`, and `end_date` for each income row
- Profile income table now renders growth and active-window dates so modeled assumptions are visible after save/reload
- Plan scenario-diff output now surfaces base/candidate income projection summaries (first-year, final-year, annualized growth) alongside scenario deltas

### 2026-04-11 (Completed - Expense Modeling Foundation)
- Added expense projection service (`expense_projection.py`) with inflation-rate and active-date window handling for profile expense items
- Added planning endpoint `POST /api/planning/expense-projection` to generate year-by-year expense curves from either provided inputs or saved profile data
- Planning scenario route and plan scenario-diff flows now generate and pass base/candidate expense projections so sidecar baseline assumptions include first-year annual expenses
- Planning responses now include `expense_projection` metadata, and scenario-diff output surfaces base/candidate expense projection summaries
- Profile UI expense builder now captures `inflation_rate`, `start_date`, and `end_date` and renders those assumptions after save/reload
- Added focused coverage in `test_expense_projection.py` and extended sidecar request coverage in `test_planning_sidecar.py`

### 2026-04-11 (Completed - Debt Payoff Modeling Foundation)
- Added debt payoff projection service (`debt_projection.py`) with minimum/snowball/avalanche/custom strategy handling and month-by-month amortization output
- Added planning endpoint `POST /api/planning/debt-projection` plus Copilot tool `project_debt_payoff` for strategy and payoff comparisons from profile or explicit inputs
- Planning scenario route and plan scenario-diff flows now generate and pass base/candidate debt projections; sidecar baseline assumptions now include first-year annual debt payments and debt projection metadata
- Planning responses now include `debt_projection` metadata, and scenario-diff output surfaces base/candidate debt strategy/payoff summaries
- Profile UI debt builder now captures payoff strategy and optional custom monthly payment per debt item
- Added focused coverage in `test_debt_projection.py`, extended sidecar payload coverage in `test_planning_sidecar.py`, and profile migration coverage for new debt fields

### 2026-04-12 (Completed - Plan Timeline Events Foundation)
- Added timeline impact projection service (`timeline_projection.py`) with support for dated `purchase`, `windfall`, `job_change`, `retirement`, and `milestone` events, including one-time/monthly/yearly recurrence and year-by-year impact aggregation
- Plan Workspace now persists validated plan timelines in `timeline.json`, supports read/update operations, and includes timeline previews in generated plan context output
- Added plan timeline API endpoints (`GET/PUT /api/plans/{plan_id}/timeline`) plus Copilot tools (`get_plan_timeline`, `update_plan_timeline`) for timeline modeling workflows
- Planning and scenario-diff flows now compute and pass timeline projections into Ignidash sidecar metadata and baseline assumptions; first-year portfolio/contribution impacts are applied to scenario setup and income/expense/debt impacts are applied to sidecar assumptions
- Plan Workspace UI now includes timeline JSON editing/saving and scenario-diff output now surfaces base/candidate timeline impact summaries
- Added focused coverage in `test_timeline_projection.py`, `test_plan_workspace.py`, and `test_planning_sidecar.py`

### 2026-04-12 (Completed - Tax-Aware Scenario Engine Foundation)
- Replaced the local planning fallback projection engine with a year-by-year tax-aware model (`scenario_engine.py`) that consumes income, expense, debt, timeline, and contribution-allocation inputs
- Added per-scenario yearly cashflow/tax timeline outputs and per-account balance timeline outputs (contribution, withdrawal, growth, ending balance)
- Implemented tax-aware withdrawal handling (taxable-first, then tax-deferred, then tax-free) plus tax-deferred withdrawal tax reconciliation
- Planning sidecar local fallback now receives full projection inputs (accounts, income/expense/debt/timeline/contribution context, filing status) so degraded mode behavior remains meaningful
- Plan and planning endpoints now pass account/filling-status context through to scenario execution and apply timeline first-year portfolio/contribution effects consistently
- Added focused coverage for tax-aware timeline/account behavior in `test_scenario_engine.py` and extended integration coverage in `test_planning_sidecar.py`

### 2026-04-12 (Completed - Withdrawal Strategies Foundation)
- Added strategy-aware retirement withdrawals in local planning simulation (`scenario_engine.py`) with `cashflow_only`, `four_percent_rule`, `dynamic_guardrails`, `bond_tent`, and `bucket_strategy`
- Reused Ignidash planning patterns from `src/lib/calc/{portfolio,simulation-engine,account,phase}.ts` for age-aware withdrawal ordering and phase-aware retirement behavior
- Planning sidecar/local fallback wiring now carries `withdrawal_strategy` and `retirement_age` (`planning_sidecar.py`) so degraded mode and sidecar mode share the same strategy assumptions
- Plan scenario APIs now resolve strategy from plan settings with timeline retirement fallback and pass it through scenario execution (`main.py`)
- Added focused coverage in `test_scenario_engine.py` and `test_planning_sidecar.py` for strategy normalization, guardrail behavior, bucket ordering, and strategy metadata propagation

### 2026-04-12 (Completed - Social Security Modeling Foundation)
- Added Social Security projection service (`social_security_projection.py`) with FRA-benefit estimation from earnings, claim-age comparisons (`62/67/70`), and year-by-year benefit projection output
- Added planning endpoint `POST /api/planning/social-security-projection` plus Copilot tool `project_social_security` for explicit SS benefit estimation workflows
- Extended plan timeline retirement schema/sanitization to carry SS planning assumptions (birth year, claiming age, life expectancy, FRA monthly benefit override, estimated earnings)
- Planning and scenario-diff flows now generate and pass Social Security projections into scenario execution; sidecar metadata and local fallback now both carry `social_security_projection`
- Local tax-aware scenario engine now applies Social Security income in annual cashflow and federal tax calculations (`social_security_income_usd`) instead of hardcoded zero
- Plan scenario-diff UI output now includes Social Security context summaries for base/candidate comparisons
- Added focused coverage in `test_social_security_projection.py`, `test_scenario_engine.py`, `test_planning_sidecar.py`, and `test_plan_workspace.py`

### 2026-04-12 (Completed - RMD Modeling Foundation)
- Added RMD projection service (`rmd_projection.py`) adapted from Ignidash RMD table/simulation patterns (`src/lib/calc/historical-data/rmd-table.ts`, `src/lib/calc/simulation-engine.ts`, `src/lib/calc/portfolio.ts`)
- Added planning endpoint `POST /api/planning/rmd-projection` plus Copilot tool `project_rmd_schedule` for explicit required-minimum-distribution projections
- Extended plan timeline retirement schema/sanitization to carry RMD assumptions (`rmd_birth_year`, `rmd_start_age`) with SECURE 2.0 start-age handling
- Planning and scenario-diff flows now generate/pass `rmd_projection` metadata into sidecar/local execution and return it in planning responses
- Local tax-aware scenario engine now enforces per-account RMD withdrawals for eligible tax-deferred accounts (401k/403b/IRA), tracks yearly `rmds_usd`, and reconciles tax impact from forced distributions
- Plan scenario-diff UI output now includes RMD context summaries for base/candidate comparisons
- Added focused coverage in `test_rmd_projection.py`, `test_scenario_engine.py`, `test_planning_sidecar.py`, and `test_plan_workspace.py`

### 2026-04-12 (Completed - Multiple Assumption Sets Foundation)
- Added plan assumption-set schema and APIs (`GET/PUT /api/plans/{plan_id}/assumption-sets`) with validation and decision-log integration in Plan Workspace
- Added default named assumption presets aligned to Ignidash market-assumption patterns (`default`, `historical_average`, `conservative`, `stagflation`, `japan_scenario`)
- Plan scenario execution now applies the active assumption set by default; scenario-diff now supports separate base/candidate assumption-set selection
- Planning and sidecar execution now propagate assumption-set identity (`assumption_set_id`, `assumption_set_name`) into scenario assumptions and sidecar metadata for traceability
- Plan Workspace UI now includes assumption-set JSON editing/saving and scenario-diff base/candidate assumption-set selectors
- Added focused coverage in `test_plan_workspace.py`, `test_plan_assumption_sets.py`, `test_scenario_engine.py`, and `test_planning_sidecar.py`

### 2026-04-12 (Completed - Scenario Branching Foundation)
- Added life-event scenario branch API (`POST /api/plans/{plan_id}/scenario-branch`) and Copilot tool (`run_plan_scenario_branch`) for branch-vs-base comparisons
- Added branch-event modeling contract with offset-based scheduling and temporary duration support (`start_year_offset`, `duration_months`, recurring frequency)
- Branch execution now reuses timeline projection wiring so temporary income/expense/contribution/debt/portfolio impacts are applied using the same recurrence logic as plan timeline events
- Branch runs support optional assumption-set selection and optional settings overrides, then return full scenario deltas + Monte Carlo deltas against the base plan
- Plan Workspace UI now includes a dedicated “Scenario Branch (Life Events)” panel with branch-name, assumption-set selection, branch-events JSON editing, and branch output rendering
- Added focused coverage in `test_plan_scenario_branching.py` for branch-event normalization and timeline merge behavior

### 2026-04-12 (Completed - Projection Visualization Foundation)
- Added a new Plan Workspace “Projection Visuals” section that consumes existing scenario outputs and renders long-horizon visuals without introducing new simulation pathways
- Implemented net-worth-over-time charting from scenario timeline points with explicit debt trajectory overlays and physical-asset appreciation overlays (using profile `physical_assets` growth assumptions)
- Implemented account-type stacked projection charting with a metric toggle (`ending_balance_usd`, `contribution_usd`, `growth_usd`) for contribution-vs-growth inspection
- Added per-account projection summary table (final balance, cumulative contributions, cumulative growth, cumulative withdrawals) to support account-level interpretation
- Visualization wiring now updates directly from scenario-diff and scenario-branch runs, enabling side-by-side source switching across base/candidate/branch outputs

### 2026-04-12 (Completed - Scenario Branch Templates Follow-up)
- Added persisted plan-level branch template catalog (`branch_templates.json`) with defaults for common life-event what-ifs (job loss, raise, new child costs)
- Added branch-template APIs (`GET/PUT /api/plans/{plan_id}/branch-templates`) plus Copilot tools (`get_plan_branch_templates`, `update_plan_branch_templates`)
- Extended scenario-branch execution to optionally run from `branch_template_id`, layering template compare-settings/events with request overrides and deduplicating duplicate events
- Added Plan Workspace UI support for template selection/loading, branch-template JSON editing/saving, and template-aware branch execution
- Added focused coverage in `test_plan_workspace.py` and `test_plan_scenario_branching.py` for template round-trip, validation, and parsing/selection behavior

### 2026-04-09 (Completed)
- Phase 1.1: BuildWealth-native TWR calculator integrated into local portfolio store
- Phase 1.2: XIRR money-weighted return added and surfaced in portfolio snapshot/UI
- Tracking now prefers transaction-aware Modified Dietz and falls back to snapshot-delta when needed

### 2026-04-09 (Completed - Next Slice Foundation)
- Phase 1.3 foundation: portfolio holdings are now account-scoped (`account_id:symbol`) with explicit account registry and migration to schema v3
- Phase 1.4 foundation: lot-aware holdings model added (FIFO lot consumption for sells, per-position lots persisted, realized gains/fees tracked)
- Phase 1.6 foundation: local asset metadata cache introduced (`asset_metadata.json`) and threaded into holdings/snapshots
- Import pipeline now resolves account names to local account IDs, auto-creates missing accounts, and ingests asset metadata columns
- Portfolio UI now supports account creation/selection and displays account + asset-class on holdings/transactions
- Plan tracking assumptions now infer expected return from latest snapshot asset-class mix when no explicit plan return assumption is set

### 2026-04-09 (Completed - Next Slice Expansion)
- Phase 1.4 expansion: configurable cost basis methods added (FIFO, LIFO, AVERAGE) with persistent method rules (global, account, symbol, position) and rebuild-time application
- Phase 1.7 foundation: allocation breakdowns now computed in-store for asset class, sector, and region
- Portfolio UI now includes per-position cost basis method controls plus allocation breakdown tables

### 2026-04-09 (Completed - Activity + Cash Foundation)
- Phase 1.10 foundation: transaction activity model now supports `FEE`, `INTEREST`, `TRANSFER_IN`, `TRANSFER_OUT`, `CASH_DEPOSIT`, `CASH_WITHDRAW`, `STOCK_SPLIT`, and `MERGER` in local rebuild logic
- Phase 1.11 foundation: account-level cash ledger added (`account_cash`) with derived `total_cash` and `total_portfolio_value`
- Account totals now include `cash_balance` and per-account `total_value`; portfolio UI surfaces these balances and expanded activity entry options
- CSV importer now recognizes transfer/cash/split/merger activity aliases and supports symbol-optional cash rows

### 2026-04-09 (Completed - Total Return Foundation)
- Phase 1.5 foundation: portfolio performance now decomposes return into `price_return` and `income_return`, with explicit `total_return` and contribution-based return percentages
- Performance model now tracks `gross_contributions`, `realized_gains`, `unrealized_gains`, and `income_received` in the local snapshot contract
- Closed-position realized gains/income are preserved in rebuild-time performance aggregation so total return does not reset after a full exit
- Portfolio UI now surfaces price-return and income-return KPI cards

### 2026-04-09 (Completed - Manual Price Foundation)
- Phase 1.12 foundation: manual price override store added (`manual_prices.json`) with migration-safe payload and per-symbol overrides
- Holdings pricing now follows Ghostfolio-style `MANUAL` source precedence over fetched market prices
- Portfolio API now supports manual price override CRUD endpoints and the UI can set/clear per-symbol overrides inline

### 2026-04-09 (Completed - Custom Asset Foundation)
- Phase 1.13 foundation: custom asset creation flow added (manual symbol generation, manual metadata tagging, and initial ledger position)
- Custom assets now carry metadata (`data_source=MANUAL`, `is_custom_asset=true`, valuation method) and appear in dedicated portfolio UI section
- Portfolio API now supports listing and creating custom assets using the same manual valuation path as manual price overrides

### 2026-04-09 (Completed - Multi-Currency Foundation)
- Phase 1.8 foundation: holdings are now currency-aware with persisted native and base-currency fields (`currency`, `base_currency`, `fx_rate_to_base`, native/base cost/value/returns)
- Added standalone FX rate store (`fx_rates.json`) with migration-safe payload, portfolio API CRUD endpoints, and portfolio UI controls for set/clear rates
- Rebuild/finalize performance paths now convert transaction cash flows to base currency before TWR/XIRR-style calculations; totals and account views remain base-normalized
- Implementation pattern follows Ghostfolio exchange-rate service design (static/manual rates first, upstream provider fetching can layer on next)

### 2026-04-09 (Completed - Multi-Currency Expansion)
- Phase 1.8 expansion: added FX history store (`fx_rates_history.json`) with date-indexed pair factors and migration-safe payload handling
- Performance conversion now prefers historical FX factor by transaction date (with prior-rate fallback), then falls back to current FX rates
- Portfolio refresh now auto-fetches latest and historical FX pairs for non-base currencies using OpenBB quote/history endpoints with Ghostfolio-style direct/inverse pair fallback

### 2026-04-09 (Completed - Historical Backfill Foundation)
- Phase 1.9 foundation: added transaction-replay snapshot backfill service to generate daily historical snapshots from ledger + historical prices
- New snapshot backfill API endpoint (`POST /api/snapshot/backfill-history`) supports date range or day-window generation and overwrite control
- Backfill valuation applies per-day FX conversion and historical FX factors for non-base currency positions

### 2026-04-09 (Completed - Portfolio History UI Foundation)
- Phase 1.14 foundation: portfolio view now includes a snapshot-history trend chart and recent-history table sourced from `/api/snapshot/history`
- Portfolio UI now includes one-click historical backfill controls (days/date range + overwrite) that call `POST /api/snapshot/backfill-history`
- Standalone workflow now supports: rebuild historical data from ledger, then immediately visualize value trend inside the main portfolio screen

---

## Current Capability Audit

### What We Already Built (relative to Ghostfolio)
| Capability | Status | Coverage |
|------------|--------|----------|
| Position tracking | Built | ~20% of Ghostfolio |
| Transaction ledger (BUY/SELL/DIVIDEND) | Built | Basic |
| Average cost basis | Built | Method-selectable (avg/fifo/lifo) |
| Current price fetch (via OpenBB) | Built | Single provider |
| CSV import (basic) | Built | One generic format |
| Multi-account ledger | Built (foundation) | ~40% |
| Time-weighted return (TWR) | Built | ~55% |
| Money-weighted return (IRR/XIRR) | Built | ~50% |
| FIFO/LIFO cost basis | Built (configurable) | ~55% |
| Tax lot tracking | Built (lot-aware) | ~55% |
| Asset class breakdown | Built | ~45% |
| Sector breakdown | Built (foundation) | ~35% |
| Geographic breakdown | Built (foundation) | ~35% |
| Multi-currency | Built (foundation + expansion) | ~55% |
| Historical price backfill | Built (foundation) | ~35% |
| Total return (incl. dividends) | Built (foundation) | ~45% |
| Performance attribution | Built (foundation) | ~35% |
| Benchmark comparison | Built (sidecar-backed + UI) | ~55% |
| Activity types beyond buy/sell/div | Built (foundation) | ~40% |
| Watchlists | NOT BUILT | 0% |
| Custom asset types | Built (foundation) | ~40% |
| Cash management | Built (foundation) | ~35% |
| Manual price overrides | Built (foundation) | ~45% |
| Time-series charts | Built (foundation) | ~30% |
| Broker-specific CSV templates | NOT BUILT | 0% |

### What We Already Built (relative to Ignidash)
| Capability | Status | Coverage |
|------------|--------|----------|
| Long-range projection scenarios | Built | Baseline/optimistic/conservative + Monte Carlo |
| Plan settings (contribution, return, years) | Built | Basic |
| Plan-vs-actual tracking | Built | Functional |
| Goal progress tracking | Built | Functional |
| Plan workspace (file-based) | Built | Functional |
| Scenario diff | Built | Basic |
| Account contribution prioritization | Built (foundation) | ~35% |
| Tax-aware account modeling | Built (foundation) | ~35% |
| Income modeling with growth rates | Built (foundation) | ~40% |
| Expense modeling with inflation | Built (foundation) | ~35% |
| Debt payoff modeling | Built (foundation) | ~35% |
| Physical assets | Built (foundation) | ~35% |
| Timeline events on plans | Built (foundation) | ~35% |
| Federal tax brackets | Built (foundation) | ~35% |
| State tax | NOT BUILT | 0% |
| FICA / Social Security tax | Built (foundation) | ~30% |
| Capital gains (LTCG/STCG/NIIT) | Built (foundation) | ~35% |
| Social Security claiming optimization | Built (foundation) | ~30% |
| RMD calculations (age 73+) | Built (foundation) | ~30% |
| Withdrawal strategies (4% rule, dynamic, bond tent) | Built (foundation) | ~35% |
| Multiple assumption sets | Built (foundation) | ~35% |
| Scenario branching (life events) | Built (foundation + saved templates) | ~45% |
| Net worth charts over time | Built (foundation + UI) | ~35% |
| Per-account balance projections | Built (foundation + visualization expansion) | ~45% |

**Honest assessment:** We're at ~20% feature parity with Ghostfolio and ~34% with Ignidash. There is substantial work ahead.

---

## Build Phases

### Phase 1: Portfolio Analytics Overhaul (Ghostfolio-inspired)

**Goal:** Make BuildWealth a real portfolio tracker. Replace the naive "cost basis vs current value" math with proper performance calculation.

**Reference source:** Ghostfolio repo, specifically:
- `apps/api/src/app/portfolio/calculator/` — portfolio calculator structure, activity models, test fixtures
- `apps/api/src/app/import/` — broker CSV templates
- `apps/api/src/services/data-provider/` — asset metadata and market data wiring
- `libs/common/src/lib/` — shared types and helpers

**Items in priority order:**

#### 1.1 Time-Weighted Return (TWR) Calculator [HIGHEST PRIORITY]
- Implement a BuildWealth-native TWR calculator in Python (`services/portfolio_performance.py`)
- Use Ghostfolio's activity model, portfolio tests, and calculator structure where helpful, but do not depend on a direct code port
- Handles cash flows correctly (deposits, withdrawals don't artificially inflate/deflate returns)
- Annualized return calculation
- Period returns (YTD, 1y, 3y, 5y, all-time)
- Test against Ghostfolio's test cases for correctness
- **Why first:** Most visibly broken thing. Currently shows -100% when prices aren't refreshed.

#### 1.2 Money-Weighted Return (IRR / XIRR)
- Implement XIRR in Python (Newton's method on cash flow series)
- Reuse Ghostfolio transaction semantics and fixtures where they help validate cash-flow timing behavior
- Shows actual personal return considering deposit timing
- Add to portfolio view alongside TWR
- **Why:** Personal performance metric that includes timing of contributions

#### 1.3 Multi-Account Ledger
- Refactor `portfolio_store.py` to store holdings as `(symbol, account_id)` pairs
- Add account types: `taxable`, `traditional_ira`, `roth_ira`, `traditional_401k`, `roth_401k`, `hsa`, `529`, `savings`, `checking`
- Rebuild holdings logic to handle per-account positions
- Migration path for existing single-account data
- **Why:** Foundation for tax-aware planning, real account segregation

#### 1.4 Cost Basis Methods (FIFO/LIFO/Average/Specific Lots)
- Add tax lot tracking — each BUY creates a lot with date and cost
- SELL transactions consume lots based on chosen method
- Configurable per-account or per-symbol
- Track realized gains/losses separately
- **Why:** Accurate cost basis for tax purposes

#### 1.5 Total Return Calculation
- Include dividends in performance (not just price appreciation)
- Distinguish price return, dividend yield, total return
- Cumulative dividend tracking per position
- **Why:** Real performance includes income, not just capital gains

#### 1.6 Asset Class Metadata
- Build symbol → asset class lookup (Yahoo Finance category, OpenBB classification)
- Cache locally in `data/asset_metadata.json`
- Categories: US Stocks, International Stocks, Emerging Markets, US Bonds, International Bonds, Cash, Commodities, REITs, Crypto
- Add sector and region (use yfinance/OpenBB metadata)
- **Why:** Enables allocation breakdowns and proper risk analysis

#### 1.7 Allocation Breakdowns
- Asset class allocation (stock/bond/cash/etc.)
- Sector allocation (Tech/Healthcare/Financials/etc.)
- Geographic allocation (US/International/EM)
- Use the asset metadata from 1.6
- Display as charts in portfolio view
- **Why:** Risk visibility, rebalancing decisions

#### 1.8 Multi-Currency Support
- Per-position currency
- Conversion to base currency for totals
- FX rate fetching (OpenBB or static rates)
- Historical FX for performance calculation
- **Why:** International holdings are common; current USD-only is limiting

#### 1.9 Historical Price Backfill
- For new positions, fetch historical prices back to purchase date
- Build daily/weekly snapshot history from transaction history + price history
- Enable charts of holdings/value over time
- **Why:** Charts and accurate historical performance

#### 1.10 Activity Types Beyond Buy/Sell/Dividend
- Add: `FEE`, `INTEREST`, `TRANSFER_IN`, `TRANSFER_OUT`, `CASH_DEPOSIT`, `CASH_WITHDRAW`, `STOCK_SPLIT`, `MERGER`
- Properly handle each in the holdings rebuild logic
- **Why:** Accurate ledger requires all activity types

#### 1.11 Cash Management
- Track cash balances per account separately from positions
- Cash deposits/withdrawals affect cash balance
- BUYs reduce cash, SELLs increase cash (optional auto-link)
- **Why:** Real portfolio view needs cash visibility

#### 1.12 Manual Price Overrides
- Allow user to set a manual price for illiquid positions (private equity, real estate, etc.)
- Distinguishes "live price" from "manual price" in display
- **Why:** Custom asset support

#### 1.13 Custom Asset Types
- Beyond stocks/ETFs: real estate, private equity, art, crypto, manual valuations
- Each can have manual price + manual class metadata
- **Why:** Net worth completeness

#### 1.14 Time-Series Charts
- Holdings value over time
- Allocation over time (stacked area)
- Performance over time (TWR, IRR)
- Compare against benchmark
- **Why:** Visual analysis is fundamental for portfolio review

#### 1.15 Benchmark Comparison
- Configurable benchmarks (default SPY, VTI, BND)
- Show portfolio TWR vs benchmark TWR over selected period
- Alpha calculation (excess return)
- **Why:** Performance context — am I beating the market?

#### 1.16 Performance Attribution
- Per-position contribution to total return
- Top contributors and detractors over period
- **Why:** Understand what drove returns

#### 1.17 Watchlists
- Track symbols you're considering but don't own
- Display alongside portfolio for easy comparison
- **Why:** Research workflow

#### 1.18 Broker-Specific CSV Templates
- Port Ghostfolio's broker templates: Schwab, Fidelity, Vanguard, Robinhood, E*TRADE, Interactive Brokers, Ally, M1, Wealthfront
- Each template knows the column mapping for that broker's export format
- One-click selection in import view
- **Why:** Friction-free imports from real brokerage accounts

---

### Phase 2: Planning Engine Overhaul (Ignidash-inspired)

**Goal:** Transform "rough projections" into a real tax-aware retirement planning engine.

**Reference source:** Ignidash repo, specifically:
- Convex schema for plan model
- Tax calculation modules
- Simulation engine

**Items in priority order:**

#### 2.1 Tax Calculation Engine [HIGHEST PRIORITY in Phase 2]
- Port Ignidash's tax calculation to Python (`services/tax_engine.py`)
- Federal income tax brackets (2026 brackets, configurable for future years)
- FICA (Social Security + Medicare withholding)
- Capital gains (LTCG brackets, STCG as ordinary income)
- Net Investment Income Tax (NIIT, 3.8% above $200k single / $250k MFJ)
- Standard deduction lookup
- Effective tax rate calculation
- State tax should be treated as a BuildWealth extension after the federal engine is stable; it is not currently modeled in Ignidash core logic
- **Why first:** Foundation for everything else in planning

#### 2.2 Account Contribution Rule Prioritization
- Define ranked rules for funding: max 401k match → HSA → Roth IRA → remaining 401k → taxable
- Each rule has: target account, amount type (fixed, percentage, max), priority rank
- Scenario engine consumes rules to allocate annual savings across accounts
- Default rule sets per common scenario (e.g., "tax-optimized for high earners")
- **Why:** Realistic modeling of how people actually save

#### 2.3 Income Modeling with Growth
- Income items get optional `annual_growth_rate` field (default: inflation rate)
- Income items get optional `start_date` and `end_date` (for job changes, side gigs)
- Scenario engine projects income over time, not just current snapshot
- **Why:** Real income changes; static current income is wrong for planning

#### 2.4 Expense Modeling with Inflation
- Expense items get optional `inflation_rate` field (default: CPI 3%)
- Some expenses inflate at different rates (healthcare 5%, education 4%, etc.)
- Optional start/end dates (mortgage payoff, kids in college period)
- **Why:** Static expenses don't match reality

#### 2.5 Debt Payoff Modeling
- Each debt has: balance, interest_rate, minimum_payment, payoff_strategy
- Compute amortization schedule
- Project payoff date at minimum vs accelerated payments
- Strategies: minimum, snowball, avalanche, custom monthly
- **Why:** Debt is a major part of financial planning, currently underserved

#### 2.6 Physical Assets
- Add `physical_assets` to financial profile: house, car, jewelry, equipment
- Each has: label, current_value, appreciation_rate (or depreciation), purchase_date
- Net worth includes physical assets
- Display in financial health summary
- **Why:** Net worth currently only counts portfolio value — major gap

#### 2.7 Plan Timeline Events
- Plans get a `timeline` field with dated events
- Event types: `purchase` (one-time expense), `windfall` (one-time income), `job_change`, `retirement`, `milestone`
- Each event has: date, label, financial impact (amount, account, recurring or one-time)
- Scenario engine applies events at correct dates in projections
- Examples: "Buy house 2028 (-$80k from taxable, +$2k/mo expense)", "Retire 2055 (stop contributions, start withdrawals)"
- **Why:** Real plans have specific dated events, not just a steady-state projection

#### 2.8 Tax-Aware Scenario Engine
- Rewrite `scenario_engine.py` to be tax-aware
- Consume contribution rules (2.2) to allocate savings
- Consume income/expense growth (2.3, 2.4) for cash flow projections
- Consume tax engine (2.1) to compute after-tax growth and withdrawals
- Project per-account balances over time
- Withdrawal phase modeling
- **Why:** Current scenario engine is too simplistic for serious planning

#### 2.9 Withdrawal Strategies
- 4% rule (Bengen)
- Dynamic withdrawal (Guyton-Klinger guardrails)
- Bond tent (decreasing equity exposure as you age)
- Bucket strategy (cash/bond/stock buckets)
- Each strategy is a function: given current assets and year, return withdrawal amount
- **Why:** Retirement income planning

#### 2.10 Social Security Modeling
- Estimate benefit at full retirement age (FRA) from earnings history
- Claiming age optimization (62 vs 67 vs 70)
- Project SS income in retirement
- Spousal benefits should be treated as a later BuildWealth extension, not assumed to exist upstream
- **Why:** Major income source in retirement, affects everything

#### 2.11 RMD Calculations
- Required minimum distributions using SECURE Act 2.0 age rules (age 73 for older cohorts, age 75 for birth year 1960+)
- IRS uniform lifetime table
- Per-account RMD calculation (traditional 401k, traditional IRA)
- Force withdrawals in scenario engine to model tax impact
- **Why:** Forced taxable income that affects retirement planning

#### 2.12 Multiple Assumption Sets
- Save named assumption sets: "historical average", "conservative", "stagflation", "japan scenario"
- Run scenarios with different assumption sets to see range of outcomes
- **Why:** Sensitivity analysis is critical for plans

#### 2.13 Scenario Branching (Life Events)
- "What if I lose my job for 6 months?"
- "What if I get a 20% raise?"
- "What if I have a kid?"
- Branch from current plan, apply temporary changes, project forward
- Compare branched scenario vs base
- **Why:** Real planning is about modeling uncertainty

#### 2.14 Net Worth Charts Over Time
- Project net worth across decades using all the above
- Stacked by account type (visible asset allocation over time)
- Show debt reduction over time
- Show physical asset appreciation
- **Why:** Visual planning is more actionable than tables

#### 2.15 Per-Account Balance Projections
- For each account, project balance year by year
- Color-coded by account type
- Toggle to show contributions vs growth
- **Why:** Understanding which accounts grow how is critical for tax planning

---

### Phase 3: Polish and Productization

#### 3.1 Asset Metadata Database
- Build a small JSON database of common ETF/stock metadata
- Covers ~500 popular tickers (S&P 500 + popular ETFs)
- Asset class, sector, region, expense ratio (for funds)
- Fallback to OpenBB lookup for unknown symbols
- **Why:** Faster than API calls, works offline

#### 3.2 ATTRIBUTIONS.md
- Credit Ghostfolio (https://github.com/ghostfolio/ghostfolio) — MIT
- Credit Ignidash (https://github.com/schelskedevco/ignidash) — MIT
- Credit OpenBB Platform — MIT
- Credit any other ported code with file references
- **Why:** License compliance and good citizenship

#### 3.3 Sidecar Boundary Hardening
- Remove legacy full-app bridge assumptions from runtime and docs
- Keep only contract-bound sidecar endpoints with health/version checks
- Add degraded-mode observability and fallback regression coverage
- **Why:** Keep sidecar usage intentional, bounded, and operationally safe

#### 3.4 UI Updates
- Portfolio view: Add account selector, allocation charts, TWR/IRR display
- Plans view: Add timeline event editor, contribution rule editor
- Profile view: Add physical assets section
- Tracking view: Use TWR/IRR instead of naive return math
- **Why:** Surface the new capabilities

#### 3.5 Copilot Tool Updates
- New tools: `get_account_balances`, `compute_tax`, `add_timeline_event`, `compare_withdrawal_strategies`, `get_asset_allocation`, `set_contribution_rules`
- Update system prompt with new tool guide entries
- **Why:** AI access to all new capabilities

#### 3.6 Documentation and Ops Cleanup
- Rewrite README and local run instructions for standalone mode
- Document sidecar startup and contract compatibility guarantees
- Document migration steps and compatibility windows
- **Why:** The repo should describe the architecture we actually ship

---

## Implementation Order (Recommended)

### Sprint 1 (Schema Cutover Foundation)
1. `ATTRIBUTIONS.md`
2. New standalone portfolio + planning schemas
3. Migration for existing transactions, plans, and profile data
4. Sidecar adapter foundation:
   establish `contracts/engine/v1` schemas and adapter validation utilities
5. Phase 1.1 — Time-Weighted Return calculator
6. Phase 1.2 — Money-Weighted Return (IRR/XIRR)
7. Update portfolio view and tracking view to consume the new schema and show TWR/IRR

### Sprint 2 (Multi-Account)
1. Phase 1.3 — Multi-Account Ledger
2. Phase 1.4 — Cost Basis Methods (FIFO/LIFO/Average)
3. Phase 1.5 — Total Return Calculation

### Sprint 3 (Asset Intelligence)
1. Phase 1.6 — Asset Class Metadata
2. Phase 1.7 — Allocation Breakdowns
3. Phase 1.10 — Activity Types beyond buy/sell/div
4. Phase 1.11 — Cash Management

### Sprint 4 (Tax Engine Foundation)
1. Phase 2.1 — Tax Calculation Engine
2. Phase 2.2 — Account Contribution Rule Prioritization
3. Phase 2.6 — Physical Assets

### Sprint 5 (Real Planning)
1. Phase 2.3 — Income Modeling with Growth
2. Phase 2.4 — Expense Modeling with Inflation
3. Phase 2.5 — Debt Payoff Modeling
4. Phase 2.7 — Plan Timeline Events
5. Phase 2.8 — Tax-Aware Scenario Engine

### Sprint 6 (Retirement Modeling)
1. Phase 2.9 — Withdrawal Strategies
2. Phase 2.10 — Social Security
3. Phase 2.11 — RMD Calculations

### Sprint 7 (Visualization)
1. Phase 1.9 — Historical Price Backfill
2. Phase 1.14 — Time-Series Charts
3. Phase 2.14 — Net Worth Charts Over Time
4. Phase 2.15 — Per-Account Balance Projections

### Sprint 8 (Advanced Analytics)
1. Phase 1.15 — Benchmark Comparison
2. Phase 1.16 — Performance Attribution
3. Phase 2.12 — Multiple Assumption Sets
4. Phase 2.13 — Scenario Branching

### Sprint 9 (Polish)
1. Phase 1.8 — Multi-Currency Support
2. Phase 1.12 — Manual Price Overrides
3. Phase 1.13 — Custom Asset Types
4. Phase 1.17 — Watchlists
5. Phase 1.18 — Broker-Specific CSV Templates
6. Phase 3.3 — Sidecar Boundary Hardening
7. Phase 3.6 — Documentation and Ops Cleanup

---

## Reference Source URLs

When porting code, fetch from these locations:

**Ghostfolio (https://github.com/ghostfolio/ghostfolio):**
- Portfolio calculators and fixtures: `apps/api/src/app/portfolio/calculator/`
- Import templates: `apps/api/src/app/import/`
- Asset metadata: `apps/api/src/services/data-provider/`
- Types and interfaces: `libs/common/src/lib/`

**Ignidash (https://github.com/schelskedevco/ignidash):**
- Plan schema: `convex/schema.ts`
- Simulation engine: `src/lib/calc/simulation-engine.ts`
- Tax calculation: `src/lib/calc/taxes.ts`
- Contribution rules: `src/lib/calc/contribution-rules.ts`
- Accounts / portfolio mechanics: `src/lib/calc/account.ts`, `src/lib/calc/portfolio.ts`

**Tools to use:**
- `WebFetch` to read GitHub source files when needed
- Prefer sidecar reuse for high-complexity benchmark/attribution and planning/tax logic
- Translate TypeScript algorithms to Python only when sidecar integration is not the best fit
- Use upstream test cases as reference for correctness whenever they map cleanly to our standalone model

---

## License Compliance

For each significant piece of code we port:
1. Add a comment at the top of the Python file noting the source: `# Adapted from Ghostfolio (MIT) — apps/api/src/app/portfolio/calculator/twr-portfolio-calculator.ts`
2. Add an entry to `ATTRIBUTIONS.md`
3. Preserve any inline copyright headers from the original code
4. Make non-trivial modifications (this is a port, not a copy — we will be translating to Python idioms)

---

## Success Metrics

We will know this plan is succeeding when:

- **Phase 1 complete:** A user can track a real multi-account portfolio with proper TWR/IRR, asset allocation breakdowns, and accurate cost basis. Feature parity with Ghostfolio core functionality.
- **Phase 2 complete:** A user can build a real retirement plan with tax-aware projections, contribution prioritization, timeline events, and withdrawal strategies. Feature parity with Ignidash core functionality.
- **Phase 3 complete:** Sidecar boundaries are hardened, docs match shipped architecture, polished UI, copilot has access to all new tools.
- **Overall:** A single-user can run BuildWealth as one local application entrypoint with Python-owned data and optional local engine sidecars, delivering stronger portfolio and planning intelligence than any single upstream tool alone.

---

## Out of Scope (For Now)

These are not part of this plan but may come later:

- Multi-user support
- Cloud sync / mobile apps
- Bank account direct integration (Plaid)
- Crypto exchange integration
- Real-time price streaming
- Options/derivatives modeling beyond current OpenBB chains
- Automated rebalancing execution (we model, user executes)
- Tax filing integration
- Estate planning
- Insurance modeling

# BuildWealth Standalone Build Plan

## Date: 2026-04-09

## Strategic Direction

**BuildWealth is becoming a fully standalone single-user financial command center.** Rather than depending on Ghostfolio (portfolio tracker) and Ignidash (planning simulator) as external services, we are porting their core logic into BuildWealth itself.

Both Ghostfolio and Ignidash are MIT licensed, which permits us to:
- Read and reference their source code on GitHub
- Port their algorithms to Python
- Borrow their data schemas and test cases
- Use their broker CSV templates and asset class taxonomies

We must:
- Add an `ATTRIBUTIONS.md` to the repo acknowledging both projects and their copyright holders
- Keep the MIT license attribution for any substantial code we adapt

## Why This Approach (vs. Integration)

We considered three options:

### Option A: Standalone BuildWealth (CHOSEN)
Build everything ourselves, leveraging MIT-licensed code from Ghostfolio and Ignidash where it makes sense.
- **Pros:** Single app, single deployment, full control, no external dependencies
- **Cons:** Significant effort to reach feature parity with mature tools

### Option B: BuildWealth as Orchestration Layer
Run Ghostfolio + Ignidash as services, with BuildWealth as the AI/synthesis layer on top.
- **Pros:** Each tool excels at its domain
- **Cons:** Three services to run, integration complexity (especially Ignidash's auth-scoped Convex API), shared infrastructure burden

### Option C: Hybrid
Standalone basics, optional integration for power users.
- **Pros:** Flexible
- **Cons:** Two paths to maintain, neither gets full attention

**Decision:** Option A. The user wants a single application. We accept the build effort in exchange for deployment simplicity and control.

## Execution Constraints

These decisions refine the build plan based on the current repository and upstream source reality:

- **Breaking schema/API changes are allowed early.** We will move schema, migration, and UI contract changes into Sprint 1 instead of deferring them.
- **Ghostfolio and Ignidash are temporary compatibility adapters during the transition.** We may keep import/export compatibility paths while standalone replacements are being built, but we should not preserve them as long-term architectural dependencies.
- **Upstream reuse should be selective, not literal.** Ghostfolio is most useful for import/account/asset metadata patterns and test fixtures; Ignidash is most useful for tax, account, contribution, and simulation logic.
- **Migration is a foundation task, not polish.** New ledger and planner models should replace the current simplified contracts early, with explicit migrations for stored portfolio, plan, and profile data.

---

## Progress Log

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
| Multi-currency | NOT BUILT | 0% |
| Historical price backfill | NOT BUILT | 0% |
| Total return (incl. dividends) | NOT BUILT | 0% |
| Performance attribution | NOT BUILT | 0% |
| Benchmark comparison | NOT BUILT | 0% |
| Activity types beyond buy/sell/div | NOT BUILT | 0% |
| Watchlists | NOT BUILT | 0% |
| Custom asset types | NOT BUILT | 0% |
| Cash management | NOT BUILT | 0% |
| Manual price overrides | NOT BUILT | 0% |
| Time-series charts | NOT BUILT | 0% |
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
| Account contribution prioritization | NOT BUILT | 0% |
| Tax-aware account modeling | NOT BUILT | 0% |
| Income modeling with growth rates | NOT BUILT | 0% |
| Expense modeling with inflation | NOT BUILT | 0% |
| Debt payoff modeling | NOT BUILT | 0% |
| Physical assets | NOT BUILT | 0% |
| Timeline events on plans | NOT BUILT | 0% |
| Federal tax brackets | NOT BUILT | 0% |
| State tax | NOT BUILT | 0% |
| FICA / Social Security tax | NOT BUILT | 0% |
| Capital gains (LTCG/STCG/NIIT) | NOT BUILT | 0% |
| Social Security claiming optimization | NOT BUILT | 0% |
| RMD calculations (age 73+) | NOT BUILT | 0% |
| Withdrawal strategies (4% rule, dynamic, bond tent) | NOT BUILT | 0% |
| Multiple assumption sets | NOT BUILT | 0% |
| Scenario branching (life events) | NOT BUILT | 0% |
| Net worth charts over time | NOT BUILT | 0% |
| Per-account balance projections | NOT BUILT | 0% |

**Honest assessment:** We're at ~20% feature parity with Ghostfolio and ~15% with Ignidash. There is substantial work ahead.

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

#### 3.3 Remove Transitional Compatibility Paths
- Retire Ghostfolio client calls once standalone import/ledger/performance flows fully replace them
- Retire Ignidash export/client flows once standalone planning becomes the source of truth
- Update env vars, docs, and health checks to reflect standalone operation
- **Why:** Avoid preserving dead integration surfaces after the cutover

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
- Remove Ghostfolio/Ignidash setup steps once no longer needed
- Document migration steps and compatibility windows
- **Why:** The repo should describe the architecture we actually ship

---

## Implementation Order (Recommended)

### Sprint 1 (Schema Cutover Foundation)
1. `ATTRIBUTIONS.md`
2. New standalone portfolio + planning schemas
3. Migration for existing transactions, plans, and profile data
4. Compatibility adapter boundary:
   Ghostfolio/Ignidash clients stay available only behind import/export bridges during transition
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
6. Phase 3.3 — Remove Transitional Compatibility Paths
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
- Translate TypeScript algorithms to Python
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
- **Phase 3 complete:** Transitional adapters are removed, docs match the shipped standalone architecture, polished UI, copilot has access to all new tools.
- **Overall:** A single-user can run BuildWealth standalone (no Docker, no Ghostfolio, no Ignidash) and have a more powerful financial command center than any single existing tool, with the AI orchestration layer as the differentiator.

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

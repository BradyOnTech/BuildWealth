# BuildWealth Feature Gap Analysis

## Date: 2026-04-08

## Status
Archived snapshot from early pre-standalone planning. Many items below have since been implemented.
For current execution priority and status, use:
- [ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md](./ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md)
- [STANDALONE_BUILD_PLAN.md](./STANDALONE_BUILD_PLAN.md)
- [CODEBASE_QUALITY_FOLLOW_UP_2026-04-15.md](./CODEBASE_QUALITY_FOLLOW_UP_2026-04-15.md)

## Context

This analysis walks through the product as a real user trying to accomplish five core goals:
1. Figure out their current financial situation
2. Figure out their financial future
3. Chat with AI agents to see how decisions affect their future
4. Chat with AI agents about financial ability to make certain decisions
5. Research investments based on current financials

---

## Mock User Walkthrough

### Day 1: "I want to understand my financial situation"

User opens BuildWealth and lands on the Dashboard. They see portfolio value ($247k), concentration risk (medium), and a checklist.

**What's missing:**
- **No net worth calculation.** Dashboard shows portfolio value but doesn't combine it with cash, debt, or other assets from the financial profile.
- **No monthly cash flow summary.** Income and expenses are entered in the profile, but nowhere does the app say "you make $8,200/month, spend $5,100/month, surplus of $3,100/month."
- **No financial health assessment.** No score, no ratios, no synthesis. The data exists (income, expenses, debt, portfolio) but nothing combines it into a health check.

**Verdict:** The app shows investments but doesn't show the complete financial picture.

### Day 2: "I want to plan my financial future"

User goes to Plans, runs scenarios. Baseline/optimistic/conservative projections work. Plan-vs-actual tracking works.

**What's missing:**
- **No goal-seeking.** Scenario engine projects out to a fixed horizon but can't answer "when will I hit $1M?" or "what contribution rate gets me to $X by year Y?"
- **No goal progress tracking.** Goals are entered (e.g., "Down payment: $80k by 2028") but no tool connects them to portfolio trajectory. Goals are just labels — they don't participate in calculations.
- **No life event modeling.** Can't model temporary income loss, windfalls, variable expenses, or other non-steady-state scenarios.

**Verdict:** Good for steady-state projections, can't answer goal-specific or life-event questions.

### Day 3: "Can I afford to buy a house?"

User asks Copilot: "Can I afford a $450k house?"

**What's missing:**
- **No affordability calculator tool.** Copilot has income/expenses/debt data but no structured tool to compute mortgage affordability, debt-to-income ratios, or cash flow impact.
- **No cash flow tool.** Can read individual income/expense items but can't get a "monthly surplus" number.
- **No expense impact simulation.** Can't model "what happens to my plan if I take on a $2,000/month mortgage?" in one step.

**Verdict:** Copilot has the data for affordability but lacks tools to calculate reliably.

### Day 4: "Should I buy AAPL or MSFT?"

User asks Copilot to compare stocks.

**What's missing:**
- **No multi-symbol comparison tool.** Makes separate API calls per ticker and tries to compare from memory.
- **No portfolio impact simulation.** Can't answer "if I put $10k into AAPL, how does my allocation change? Does concentration get worse?"
- **No fundamental data** beyond basic quote (no earnings growth, revenue trends, analyst ratings).
- **No portfolio-aware research.** Nothing connects current holdings to potential additions.

**Verdict:** Research is one-stock-at-a-time with basic data. Can't do meaningful comparison or portfolio-aware analysis.

### Day 5: "What should I actually DO?"

User reviews Recommendation Inbox.

**What's missing:**
- **Recommendations are generic.** "Run concentration-risk workflow" rather than "sell 5% of AAPL to reduce concentration below 20%."
- **No actionable rebalancing suggestions.** Detects concentration but doesn't calculate what to buy/sell.
- **No priority-ranked strategic action plan.** Checklist is operational ("run sync", "set up plan"), not strategic ("your biggest financial lever is increasing 401k contribution").

---

## Proposed Features (Priority Order)

### 1. Financial Health Summary

**User goal:** "Understand my current financial situation"

A copilot tool + dashboard integration that computes:
- Net worth (portfolio value + cash - total debt)
- Monthly cash flow (total income - total expenses = surplus)
- Savings rate (surplus / gross income)
- Debt-to-income ratio (total debt payments / gross income)
- Emergency fund coverage (liquid portfolio / monthly expenses in months)
- Financial health status (healthy / needs attention / critical)

This is a computation and display gap because the data already exists in the financial profile and portfolio snapshot. It is the highest-leverage improvement.

### 2. Affordability Calculator

**User goal:** "Financial ability to make certain decisions"

A copilot tool that takes a proposed expense and answers:
- Can you afford it given current cash flow?
- How does it affect your savings rate?
- How does it impact your plan trajectory? (runs scenario with reduced contributions)
- What's your new debt-to-income ratio?
- For mortgages: front-end and back-end ratios, estimated monthly payment

### 3. Goal Progress Tracking

**User goal:** "Figure out my financial future"

Connect the profile's goals to the scenario engine:
- Goal progress: "Down payment: $80k by 2028 — you have $32k, need $48k more, at current savings rate you'll get there in 16 months."
- Goal-seeking: "What monthly savings gets me to $80k by 2028?"
- Multiple goal tracking on dashboard/plan view

### 4. Portfolio Impact Simulation

**User goal:** "Research investments based on current financials"

A tool that simulates a trade before you make it:
- "What if I buy $10k of AAPL?" → Shows new allocation, new concentration, new top holdings
- "What if I sell half my BRK.B?" → Shows rebalanced portfolio
- Risk impact: "Does this trade increase or decrease concentration?"

### 5. Enhanced Copilot System Prompt

**User goal:** "Chat with AI agents effectively"

Current prompt is 2 generic sentences. Should guide the copilot to:
- Check cash flow before answering affordability questions
- Pull financial profile before making assumptions about user situation
- Use scenario diffs for "what if" questions
- Reference specific holdings when discussing concentration
- Proactively flag risks it discovers
- Use get_plan_tracking when asked "am I on track?"
- Run financial health summary as part of daily reviews

---

## Current Copilot Capability Scorecard

| Capability | Rating | Notes |
|-----------|--------|-------|
| Portfolio questions | 5/5 | Live/cached snapshots, full historical trending |
| Financial profile review | 5/5 | Complete income, expense, debt, goal data |
| Long-term planning scenarios | 4/5 | 3-scenario + HSA, Monte Carlo, but fixed assumptions |
| What-if analysis | 3/5 | Can modify contributions/years, limited to simple changes |
| Market research | 3/5 | Quote, price history, options via OpenBB |
| Investment comparison | 1/5 | No built-in comparison; one ticker at a time |
| Affordability assessment | 1/5 | No calculator; manual ratio calculation only |
| Tax optimization | 0/5 | Explicitly excluded from scope |
| Recommendation quality | 3/5 | Full inbox workflow but generic suggestions |
| Risk analysis | 2/5 | Concentration only; no beta, Sharpe, correlation |

## Copilot Tools Registered (25 total)

### Portfolio & Snapshot
- `get_latest_snapshot` — Latest local snapshot
- `get_live_snapshot` — Live from Ghostfolio
- `get_snapshot_history` — Historical trends (14-day)
- `list_accounts` — Ghostfolio accounts

### Financial Profile
- `get_financial_profile` — Full profile (income, expenses, debt, goals, tax)
- `update_financial_profile` — Full update
- `get_onboarding_status` — Completion tracking

### Dashboard & Context
- `get_today_dashboard` — Complete daily summary
- `get_sync_status` — Sync engine status
- `run_sync` — Trigger full sync pipeline

### Recommendations
- `list_recommendations` — Filter by status, priority, plan
- `create_recommendation` — Manual creation
- `apply_recommendation` — With plan settings override
- `reject_recommendation` — With reason tracking

### Planning
- `run_planning_scenarios` — Baseline/optimistic/conservative/HSA
- `run_plan_scenario_diff` — Compare scenarios with optional apply
- `get_plan_context` — Plan summary
- `get_plan_settings` — Settings detail
- `update_plan_settings` — Settings + decision logging
- `append_plan_decision` — Decision history
- `get_plan_tracking` — Plan vs actual comparison

### Workflows
- `list_workflow_templates` — Available templates
- `run_workflow_template` — With report/recommendation/artifact save

### Research
- `research_options_chain` — OpenBB options data
- `research_quote` — Live quote data
- `research_price_history` — Historical prices

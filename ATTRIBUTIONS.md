# Attributions

BuildWealth incorporates ideas, schemas, test patterns, and implementation approaches
adapted from the following open source projects:

## Ghostfolio

- Project: https://github.com/ghostfolio/ghostfolio
- License: AGPL-3.0 (current upstream default branch as of 2026-04-14; verify by adapted revision)
- Copyright: Ghostfolio contributors
- Intended reuse in BuildWealth:
  portfolio activity models, import workflows, broker CSV handling patterns,
  asset metadata patterns, and portfolio test fixtures
- File-level adaptations:
  `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_store.py`
  (multi-currency rate storage and normalization patterns adapted from
  `apps/api/src/services/exchange-rate-data/exchange-rate-data.service.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/price_updater.py`
  (FX pair resolution and historical-rate lookup fallback patterns adapted from
  `apps/api/src/services/exchange-rate-data/exchange-rate-data.service.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/snapshot_backfill.py`
  (historical timeline/transaction-point backfill patterns adapted from
  `apps/api/src/app/portfolio/calculator/portfolio-calculator.ts` and
  `apps/api/src/helper/portfolio.helper.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/portfolio_attribution.py`
  (position-level net-performance attribution structure adapted from
  `apps/api/src/app/portfolio/calculator/roai/portfolio-calculator.ts` and
  `apps/api/src/app/portfolio/portfolio.service.ts`)

## Ignidash

- Project: https://github.com/schelskedevco/ignidash
- License: AGPL-3.0 (current upstream default branch as of 2026-04-14; verify by adapted revision)
- Copyright: Ignidash contributors
- Intended reuse in BuildWealth:
  planning schemas, tax engine structure, contribution rule logic,
  account simulation mechanics, and retirement-planning test patterns
- File-level adaptations:
  `services/orchestrator/src/buildwealth_orchestrator/services/tax_engine.py`
  (federal tax calculation flow and tax-data table structure adapted from
  `src/lib/calc/taxes.ts` and
  `src/lib/calc/tax-data/{federal-income-tax-brackets,capital-gains-tax-brackets,standard-deduction,niit-thresholds,social-security-tax-brackets}.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/contribution_rules.py`
  (ranked contribution waterfall, shared-limit enforcement, and account-type annual
  limit helper structure adapted from `src/lib/calc/contribution-rules.ts` and
  `src/lib/schemas/inputs/contribution-form-schema.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/income_projection.py`
  (income growth and active-timeframe projection structure adapted from
  `src/lib/calc/incomes.ts` plus related income/timeframe schema helpers in
  `src/lib/schemas/inputs/{income-form-schema,income-expenses-shared-schemas}.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/expense_projection.py`
  (expense inflation and active-timeframe projection structure adapted from
  `src/lib/calc/expenses.ts` plus related expense/timeframe schema helpers in
  `src/lib/schemas/inputs/{expense-form-schema,income-expenses-shared-schemas}.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/debt_projection.py`
  (debt payoff strategy projection and amortization flow adapted from
  `src/lib/calc/debts.ts` plus debt input schema/testing patterns from
  `src/lib/schemas/inputs/debt-form-schema.ts` and `src/lib/calc/debts.test.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/timeline_projection.py`
  (timeline event normalization, date-window recurrence, and impact-shaping structure
  adapted from `src/lib/schemas/inputs/timeline-form-schema.ts`,
  `convex/timeline.ts`, and `convex/validators/timeline_validator.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/plan_workspace.py`
  (plan timeline persistence/validation structure aligned to Ignidash timeline schema
  conventions from `src/lib/schemas/inputs/timeline-form-schema.ts` and
  `convex/validators/timeline_validator.ts`; assumption-set persistence/validation
  patterns aligned to `convex/market_assumptions.ts`,
  `convex/validators/market_assumptions_validator.ts`, and
  `src/lib/schemas/inputs/market-assumptions-form-schema.ts`; saved branch-template
  catalog persistence patterns aligned to Ignidash named-template conventions in
  `convex/templates/{basic,early_retirement}.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/main.py`
  (assumption-set selection and scenario wiring patterns aligned to Ignidash
  market-assumptions input and template conventions from
  `convex/market_assumptions.ts`, `convex/templates/basic.ts`, and
  `convex/templates/early_retirement.ts`; life-event branch shaping and timeline
  impact wiring aligned to `src/lib/schemas/inputs/timeline-form-schema.ts`,
  `convex/timeline.ts`, and `convex/validators/timeline_validator.ts`; saved
  branch-template catalog wiring and default-template fallback patterns aligned
  to Ignidash named-template usage in `convex/templates/{basic,early_retirement}.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/web/views/plan-editor.js`
  (single-simulation net-worth chart data shaping, debt/asset overlay framing,
  and metric-driven projection view selection patterns aligned to
  `src/lib/calc/data-extractors/chart-data-extractor.ts` and
  `src/app/dashboard/simulator/[planId]/components/outputs/charts/single-simulation/single-simulation-net-worth-area-chart.tsx`);
  `services/orchestrator/src/buildwealth_orchestrator/services/social_security_projection.py`
  (timeline age/retirement framing and claim-age comparison structure aligned to
  `src/lib/schemas/inputs/timeline-form-schema.ts` and `src/lib/calc/phase.ts`;
  benefit formula implementation is a BuildWealth extension);
  `services/orchestrator/src/buildwealth_orchestrator/services/rmd_projection.py`
  (RMD start-age policy, IRS Uniform Lifetime table usage, and per-account
  distribution projection structure adapted from
  `src/lib/calc/historical-data/rmd-table.ts`,
  `src/lib/calc/simulation-engine.ts`, and `src/lib/calc/portfolio.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/scenario_engine.py`
  (tax-aware year-by-year scenario projection, account withdrawal ordering, and
  phase-aware simulation structure adapted from `src/lib/calc/simulation-engine.ts`,
  `src/lib/calc/portfolio.ts`, `src/lib/calc/account.ts`, and `src/lib/calc/phase.ts`);
  `services/orchestrator/src/buildwealth_orchestrator/services/research.py`
  (research dossier packaging and comparison-summary framing aligned to
  `src/lib/calc/data-analyzers/*` output conventions);
  `services/orchestrator/src/buildwealth_orchestrator/services/recommendation_scoring.py`
  (weighted analyzer-style output packaging aligned to
  `src/lib/calc/data-analyzers/*` summary-shaping conventions)

## OpenBB Platform

- Project: https://github.com/OpenBB-finance/OpenBB
- License: MIT
- Copyright: OpenBB contributors
- Intended reuse in BuildWealth:
  market data access patterns and research integrations already used by the app

## Notes

- Individual source-adapted files in BuildWealth should include a short file header
  pointing back to the upstream source path when the adaptation is substantial.
- This document is intentionally high-level. More specific file-level attributions
  should be added as standalone implementations are introduced.

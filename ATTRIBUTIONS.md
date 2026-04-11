# Attributions

BuildWealth incorporates ideas, schemas, test patterns, and implementation approaches
adapted from the following open source projects:

## Ghostfolio

- Project: https://github.com/ghostfolio/ghostfolio
- License: MIT
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
- License: MIT
- Copyright: Ignidash contributors
- Intended reuse in BuildWealth:
  planning schemas, tax engine structure, contribution rule logic,
  account simulation mechanics, and retirement-planning test patterns
- File-level adaptations:
  `services/orchestrator/src/buildwealth_orchestrator/services/tax_engine.py`
  (federal tax calculation flow and tax-data table structure adapted from
  `src/lib/calc/taxes.ts` and
  `src/lib/calc/tax-data/{federal-income-tax-brackets,capital-gains-tax-brackets,standard-deduction,niit-thresholds,social-security-tax-brackets}.ts`)

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

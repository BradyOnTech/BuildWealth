# Attributions

BuildWealth is my own Python and JavaScript codebase, but I didn't design it in a
vacuum. Early on I studied two excellent open-source finance apps to learn how
experienced teams model portfolios and retirement plans. The BuildWealth modules
listed below were written independently in Python; no source was copied. Their
module docstrings still point at the upstream files I used as design references,
so anyone can compare them.

## Ghostfolio

- Project: https://github.com/ghostfolio/ghostfolio (AGPL-3.0)
- What I learned from it: multi-currency exchange-rate normalization and fallback,
  transaction-replay portfolio history, position-level performance attribution,
  activity export shapes, and benchmark trend rules.
- BuildWealth modules that reference it: `portfolio_store.py`, `price_updater.py`,
  `snapshot_backfill.py`, `portfolio_attribution.py`, `portfolio_review_packets.py`,
  and the benchmark trend helpers in `main.py`.

## Ignidash

- Project: https://github.com/schelskedevco/ignidash (AGPL-3.0)
- What I learned from it: the shape of a phase-aware, tax-aware retirement
  simulation; federal tax-table structure; ranked contribution waterfalls with
  shared limits; income, expense, debt and timeline projection structure; and RMD
  start-age policy.
- BuildWealth modules that reference it: `scenario_engine.py`, `tax_engine.py`,
  `contribution_rules.py`, `income_projection.py`, `expense_projection.py`,
  `debt_projection.py`, `timeline_projection.py`, `rmd_projection.py`,
  `social_security_projection.py`, `plan_workspace.py`, and the output shaping in
  `recommendation_scoring.py`.

## Data and libraries

- **Historical annual returns** (1928 onward) in `scenario_engine.py`: NYU Stern
  historical market returns, using the copy Ignidash ships in
  `src/lib/calc/historical-data/nyu-returns.ts`. This is factual data, not code, but
  I'm naming the source.
- **Peer benchmarks** in `peer_benchmark.py`: summary statistics from the Federal
  Reserve's 2022 Survey of Consumer Finances.
- **[marked](https://github.com/markedjs/marked)** v12.0.2 (MIT): vendored at
  `web-v2/lib/marked.esm.js` with its license header intact.
- **[OpenBB Platform](https://github.com/OpenBB-finance/OpenBB)**: an optional
  market-data extra. It isn't bundled and is installed separately under its own
  license.
- **Fonts**: Fraunces and IBM Plex Mono (SIL OFL, via Google Fonts) and Switzer
  (Fontshare free license). They are loaded at runtime, not bundled.

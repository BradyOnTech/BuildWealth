# Attributions

BuildWealth is a proof-of-concept application that implements portfolio, planning, import, simulation, recommendation, and Copilot workflows inside the BuildWealth codebase.

Current provenance notes should be kept implementation-focused:

- OpenBB Platform is used for market-data access where configured.
- BuildWealth portfolio services own portfolio state, pricing, import review, audit, and analytics behavior.
- BuildWealth planning services own tax calculations, contribution rules, timeline projections, simulations, saved simulations, and withdrawal comparisons.

When future work materially imports a third-party algorithm or dataset, add a concise note naming the BuildWealth file, the external source, and the reason the source matters. Do not add product-surface references or UI terminology for external applications.

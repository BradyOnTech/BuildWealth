# BuildWealth-native capability ownership

BuildWealth owns the full portfolio and planning experience inside the orchestrator, v2 UI, Copilot tools, persistence layer, and audit trail.

Older adapter and external-app concepts are migration scaffolding only. They must not appear in runtime navigation, product labels, UX copy, module names, recommendation text, Copilot answers, or default operations.

New implementation should use BuildWealth workflow names:

- Portfolio, Portfolio Analysis, Portfolio Audit, and Asset Registry for investment workflows.
- Import Workbench for statement, CSV, reconciliation, and import-report workflows.
- Plan, Simulations, Saved Simulations, and Plan Strategy Lab for what-if, retirement, contribution, tax, and withdrawal workflows.

If optional calculation services remain during migration, they are implementation details behind BuildWealth-owned interfaces. The user-facing contract is always BuildWealth data in, BuildWealth explanation out, and BuildWealth review/apply controls around changes.

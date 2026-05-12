# Native Completion and Deletion Plan

**Date**

2026-05-12

**Status**

Active punchlist for finishing BuildWealth-native functional depth and then removing legacy upstream runtime scaffolding.

**Purpose**

BuildWealth is absorbing the useful portfolio and planning capabilities into native workflows. The target state is one BuildWealth product surface, one BuildWealth-owned data model, and no required external-app runtime. Historical provenance can remain where intentionally required, but users should never need old app names to understand or operate the product.

**Completion Standard**

A capability is complete when:

- the backend service owns the behavior locally
- the API contract is typed and covered by route tests
- v2 exposes the workflow from the right user home
- Copilot reaches the same reviewed API boundary
- browser or render tests cover the main user path
- user-facing copy uses BuildWealth language
- deletion of old runtime scaffolding would not remove active product behavior

**Ordered Completion Slices**

1. **Saved Simulation Lifecycle**
   - [x] Add Saved Simulation detail and focus state.
   - [x] Compare a Saved Simulation against the current active plan.
   - [x] Rerun a Saved Simulation from its saved inputs using current plan data.
   - [x] Let users create a new Saved Simulation from a rerun.
   - [x] Link Saved Simulations from Decisions, Inbox, and Copilot.

2. **Simulation Depth**
   - [x] Add chart-ready metric extraction for yearly cash flow, taxes, contributions, withdrawals, balances, and RMDs.
   - [x] Add phase summaries for accumulation, transition, and retirement.
   - [x] Add percentile bands when stochastic or Monte Carlo results are available.
   - [x] Link warnings to the exact Profile or Assumptions fields that need review.

3. **Strategy Comparison Depth**
   - [x] Expand contribution ordering explanations beyond the existing rule list.
   - [x] Deepen withdrawal diagnostics for taxes, ending value, depletion risk, cash-flow stability, and account exhaustion order.
   - [x] Save chosen strategies as Plan decisions with rationale.
   - [x] Use Review level before applying material strategy changes.

4. **Import & Review Completion**
   - [x] Route unresolved assets into Investments & Assets before apply.
   - [x] Keep durable import reports linked from Portfolio History.
   - [x] Improve broker mapping templates and confidence display.
   - [x] Add browser workflow coverage for preview -> resolve -> apply -> report.

5. **Investments & Assets Completion**
   - [x] Add asset detail pages.
   - [x] Show seeded, imported, manual, and provider provenance.
   - [x] Make metadata and price overrides explicit and reversible.
   - [x] Surface custom assets, manual prices, and FX maintenance from native v2 paths.

6. **Portfolio Analysis Completion**
   - [x] Add period switching: Today, WTD, MTD, YTD, 1Y, 5Y, Max.
   - [x] Deepen benchmark and attribution views.
   - [x] Separate price return, income return, cash-flow effects, and fees where data allows.
   - [x] Explain concentration, sector, region, account, and allocation risks.

7. **Portfolio History and Export Completion**
   - [x] Add audit event detail.
   - [x] Export transactions, holdings, lots, metadata, import reports, and audit reports as a bundle.
   - [x] Document recovery or reversal posture for destructive and manual changes.

8. **Copilot Native Boundary**
   - [x] Remove old-app and sidecar language from user-facing Copilot prompts and tool summaries.
   - [x] Keep Copilot as a draft/review helper, not an unreviewed mutation path.
   - [x] Make Copilot cite Simulation Run, Saved Simulation, Portfolio History, and Import Report IDs.

9. **Deletion Readiness**
   - [x] Remove or quarantine legacy Docker profiles.
   - [x] Remove default env vars for retired runtime paths.
   - [x] Remove unused adapters and exporters after native route tests prove coverage.
   - [x] Rename tests/classes that now describe native behavior.
   - [x] Keep only intentional provenance/legal references.
   - [ ] Remove compatibility contract files after final v1/classic removal approval.

**Deletion Gates**

Do not remove a legacy runtime component until:

- the matching v2 workflow exists
- service and route tests cover the native behavior
- no v2 user path links to the old surface
- Copilot has a native tool/API path for the same job
- a scan confirms no user-facing old-app copy remains

Final classic/v1 removal remains a product-owner decision.

# Native Capability Source-of-Truth Cleanup

**Date**

2026-05-09

**Status**

Active cleanup checklist before and during BuildWealth-native feature implementation.

**Purpose**

BuildWealth now targets native capability ownership and the v2 Product Surface. Older docs, settings, code names, comments, tests, and UI links still contain retired calculation module and external-app language from earlier architecture decisions.

This checklist exists so cleanup happens deliberately while implementation proceeds.

Functional completion and deletion gates are tracked in [Native Completion and Deletion Plan](./NATIVE_COMPLETION_AND_DELETION_PLAN_2026-05-12.md).

**Canonical Decisions**

- BuildWealth-native capabilities replace native capability ownership: [ADR 0003](./adr/0003-buildwealth-native-capability-ownership.md)
- v2 is the only future product surface: [ADR 0004](./adr/0004-v2-is-the-only-future-product-surface.md)
- Outcome Parity is the standard, not feature or screen cloning.
- Workflow Replacement is the v2 migration standard.
- Classic/v1 removal requires the Classic Removal Gate and explicit product-owner approval.

**Canonical BuildWealth Terms**

Use these terms in new implementation:

- Import Workbench
- Import Report
- Asset Registry
- Asset Review Item
- Portfolio Analysis
- Portfolio Audit
- Simulations
- Scenario
- Branch
- Simulation Run
- Saved Simulation
- Plan Strength
- Plan Lever
- Plan Lever Impact Level
- Plan Lever Impact Policy
- Plan Decision
- Plan Strategy Lab

Avoid these as product/module/runtime terms:

- Portfolio Analysis feature
- Simulations feature
- retired calculation module feature
- external app parity
- classic fallback as a permanent home
- feature parity as the migration standard

**Documentation Cleanup**

- [x] Add glossary terms to `CONTEXT.md`.
- [x] Add ADR for native capability ownership.
- [x] Add ADR for v2 as the only future product surface.
- [x] Update `docs/ARCHITECTURE.md` to native-first architecture.
- [x] Mark `docs/NATIVE_CAPABILITY_ARCHITECTURE.md` as superseded.
- [x] Update standalone operations away from optional retired calculation module mode.
- [x] Update migration/compatibility away from active retired calculation module contract expansion.
- [x] Update v1-to-v2 migration plan to Workflow Replacement and owner-approved removal.
- [ ] Update implementation plans as each BuildWealth-retired calculation module starts.
- [ ] Fix stale license/provenance wording that says MIT where the source projects are AGPL-3.0.

**Runtime Reference Cleanup**

Remove or rename references after native workflows cover the related user job:

- [x] Remove external app links from v2 Data & Tools.
- [ ] Remove external app links from classic/v1 where possible before full v1 deletion.
- [ ] Remove default env variables for retired retired calculation module paths.
- [ ] Remove or quarantine legacy upstream Docker profiles.
- [ ] Remove unused clients/exporters once route tests prove they are not active.
- [ ] Rename user-facing engine labels to BuildWealth-native terms.
- [ ] Remove retired calculation module names from Copilot tool text and recommendation copy.
- [ ] Remove retired calculation module names from test names when the tests describe native behavior.
- [ ] Keep provenance in attribution/legal history only where required.

**Implementation Cleanup Rule**

When building a new retired calculation module, do not first clone the old reference-app boundary. Start from the BuildWealth user workflow and keep the implementation local to the owning module.

For example:

- Import & Review starts with Import Workbench and Import Report, not an external importer clone.
- Portfolio Analysis starts with Portfolio Analysis, not a benchmark retired calculation module.
- Simulations start with Simulations, Simulation Run, and Saved Simulation, not an external planning app route.

**First Implementation Slice**

The first native implementation slice is Import & Review:

1. Build v2 Import Workbench around file, mapping, reconciliation, apply, and Import Report.
2. Route unresolved assets into Asset Registry and Asset Review Items.
3. Feed applied state into Portfolio and Portfolio Audit.
4. Keep Copilot as a helper that can draft or explain, not silently apply.
5. Add service, route, v2 render, and browser workflow tests.

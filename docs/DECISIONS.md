# Decision Log

## 2026-05-09 Native Capability Ownership

1. Native capability ownership
- Decision: BuildWealth owns portfolio analytics, imports, asset registry, simulations, and plan strategy work as native product capabilities.
- Rationale: the product goal is to provide the same or better functionality entirely inside BuildWealth, without separate application references in runtime paths, product labels, UX copy, module names, recommendation text, or Copilot answers.
- ADR: [0003-buildwealth-native-capability-ownership.md](./adr/0003-buildwealth-native-capability-ownership.md)

2. Legacy implementation language
- Decision: treat prior adapter and bridge references as migration scaffolding unless a document explicitly marks them as active migration notes.
- Rationale: future implementation should optimize for BuildWealth-owned workflows, not preservation of an optional advanced runtime mode.

## 2026-05-09 v2 Product Surface

1. Canonical UI
- Decision: v2 is the only future BuildWealth product surface.
- Rationale: new native capabilities should converge into one coherent user experience instead of splitting workflows across v2, classic/v1, or external app links.
- ADR: [0004-v2-is-the-only-future-product-surface.md](./adr/0004-v2-is-the-only-future-product-surface.md)

2. Classic/v1 exit
- Decision: treat classic/v1 UI as temporary migration scaffolding.
- Rationale: classic fallbacks are acceptable during migration only when they have explicit replacement paths in v2.

## 2026-04-14 Standalone Documentation/Ops Reconciliation

1. Canonical source of truth update
- Decision: supersede early assumptions that a separate portfolio ledger is the canonical source for runtime operations.
- Rationale: BuildWealth orchestrator now owns persistent state (portfolio/profile/plans) as the single source of truth.

2. Default runtime mode
- Decision: default local run mode is orchestrator-only standalone operation.
- Rationale: matches shipped architecture and avoids coupling day-to-day operation to separate application stacks.

3. Legacy runtime handling
- Decision: remove non-BuildWealth runtime containers from the default product stack.
- Rationale: preserves standalone BuildWealth operation as the normal path.

## 2026-04-07 Baseline Decisions

1. Deployment model
- Decision: local-first on a single MacBook host.
- Rationale: fastest implementation path and easiest debugging.

2. Network exposure
- Decision: private/local only first.
- Rationale: avoids premature hardening and DNS/TLS setup while data model and workflows stabilize.

3. Reverse proxy
- Decision: defer initial reverse proxy.
- Rationale: all core services are reachable on localhost in development.
- Upgrade path: add Traefik when exposing beyond LAN.

4. Auth strategy
- Decision: separate service credentials by component via env secrets.
- Rationale: clean trust boundaries and easier rotation.

5. Data source priority
- Decision: Portfolio Analysis as source of truth; start with CSV/API ingestion into Portfolio Analysis, then fan out. (Superseded by 2026-04-14 standalone data-ownership decision.)
- Rationale: single canonical ledger minimizes drift.

6. Historical import depth
- Decision: import at least 2 years initially, then extend to full history.
- Rationale: enough data for trend/risk baselines without blocking launch.

7. Sync cadence
- Decision: nightly sync as default, with manual trigger endpoint available.
- Rationale: balances freshness with operational simplicity.

8. Agent orchestration
- Decision: coordinator API first with explicit tools and schemas; integrate LangGraph next.
- Rationale: hardens data contracts before adding expensive LLM orchestration complexity.

9. LLM recommendation
- Decision: OpenAI as primary for coordinator synthesis; keep model/provider abstraction in config.
- Rationale: best tool ecosystem and straightforward production path.

10. Memory strategy
- Decision: persist normalized snapshots and generated plan payloads from day 1.
- Rationale: provides durable context immediately and supports replay/debug.

11. Ingestion strategy
- Decision: standardize on a canonical CSV transaction schema with alias mapping, then translate to Portfolio Analysis import payloads. (Superseded by orchestrator-owned standalone import model.)
- Rationale: gets reliable ingestion live quickly while broker-specific adapters are added incrementally.

## 2026-04-10 Architecture Update

1. Standalone strategy refinement
- Decision: keep BuildWealth Python orchestrator as the control plane while implementing high-complexity portfolio and planning domains behind BuildWealth-owned interfaces.
- Rationale: preserves single-app UX and local-first operation while reducing parity risk and rewrite cost on mature financial calculation logic.

2. Canonical data ownership
- Decision: Python remains the system of record for ledger, profile, plans, and snapshots. Optional calculation services are stateless implementation details.
- Rationale: avoids split-brain data models and keeps migration logic centralized.

3. Engine integration model
- Decision: use versioned calculation interfaces with strict response validation and fallback behavior while migration scaffolding remains.
- Rationale: contract versioning reduces integration drift and keeps optional calculators isolated from product workflows.

4. Scope of optional calculation services
- Decision: prioritize local BuildWealth services for benchmark, attribution, tax, and scenario calculation, while retaining explicit degraded fallback behavior where optional calculators still exist.
- Rationale: maximizes correctness without introducing unnecessary service complexity.

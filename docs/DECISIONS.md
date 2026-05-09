# Decision Log

## 2026-05-09 Upstream Runtime Exit

1. Native capability ownership
- Decision: supersede the earlier long-term sidecar strategy with BuildWealth-native capabilities for portfolio analytics, imports, asset registry, plan simulation, and plan strategy work.
- Rationale: the product goal is now to provide the same or better functionality entirely inside BuildWealth, without Ghostfolio or Ignidash references in runtime paths, product labels, UX copy, module names, recommendation text, or Copilot answers.
- ADR: [0003-buildwealth-native-capabilities-replace-upstream-sidecars.md](./adr/0003-buildwealth-native-capabilities-replace-upstream-sidecars.md)

2. Legacy sidecar language
- Decision: treat prior Ghostfolio/Ignidash sidecar references as historical scaffolding unless a document explicitly marks them as active migration notes.
- Rationale: future implementation should optimize for deletion of external app concepts, not preservation of an optional advanced runtime mode.

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
- Decision: supersede early assumptions that Ghostfolio is the canonical ledger source for runtime operations.
- Rationale: BuildWealth orchestrator now owns persistent state (portfolio/profile/plans) as the single source of truth.

2. Default runtime mode
- Decision: default local run mode is orchestrator-only standalone operation.
- Rationale: matches shipped architecture and avoids coupling day-to-day operation to full upstream app stacks.

3. Legacy upstream app stack handling
- Decision: keep full Ghostfolio/Ignidash app containers as optional `legacy-upstream` profile only. (Superseded by 2026-05-09 upstream runtime exit.)
- Rationale: preserves reference/debug workflows without making them required for standalone BuildWealth operation.

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
- Decision: Ghostfolio as source of truth; start with CSV/API ingestion into Ghostfolio, then fan out. (Superseded by 2026-04-14 standalone data-ownership decision.)
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
- Decision: standardize on a canonical CSV transaction schema with alias mapping, then translate to Ghostfolio import payloads. (Superseded by orchestrator-owned standalone import model.)
- Rationale: gets reliable ingestion live quickly while broker-specific adapters are added incrementally.

## 2026-04-10 Architecture Update

1. Standalone strategy refinement
- Decision: keep BuildWealth Python orchestrator as the control plane, but shift from broad TypeScript-to-Python logic translation to targeted Ghostfolio/Ignidash sidecar reuse for high-complexity domains. (Superseded by 2026-05-09 upstream runtime exit.)
- Rationale: preserves single-app UX and local-first operation while reducing parity risk and rewrite cost on mature financial calculation logic.

2. Canonical data ownership
- Decision: Python remains the system of record for ledger, profile, plans, and snapshots. Sidecars are stateless compute engines.
- Rationale: avoids split-brain data models and keeps migration logic centralized.

3. Engine integration model
- Decision: use versioned contract interfaces between Python adapters and sidecars, with strict response validation and fallback behavior. (Superseded by 2026-05-09 upstream runtime exit.)
- Rationale: contract versioning reduces integration drift and allows independent evolution of sidecars.

4. Scope of sidecar adoption
- Decision: prioritize sidecars for benchmark/timeline attribution (Ghostfolio) and tax/scenario calculation (Ignidash), while retaining low-complexity logic in Python. (Superseded by 2026-05-09 upstream runtime exit.)
- Rationale: maximizes reuse ROI without introducing unnecessary service complexity.

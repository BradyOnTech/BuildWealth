# Decision Log

## 2026-04-14 Standalone Documentation/Ops Reconciliation

1. Canonical source of truth update
- Decision: supersede early assumptions that Ghostfolio is the canonical ledger source for runtime operations.
- Rationale: BuildWealth orchestrator now owns persistent state (portfolio/profile/plans) as the single source of truth.

2. Default runtime mode
- Decision: default local run mode is orchestrator-only standalone operation.
- Rationale: matches shipped architecture and avoids coupling day-to-day operation to full upstream app stacks.

3. Legacy upstream app stack handling
- Decision: keep full Ghostfolio/Ignidash app containers as optional `legacy-upstream` profile only.
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
- Decision: keep BuildWealth Python orchestrator as the control plane, but shift from broad TypeScript-to-Python logic translation to targeted Ghostfolio/Ignidash sidecar reuse for high-complexity domains.
- Rationale: preserves single-app UX and local-first operation while reducing parity risk and rewrite cost on mature financial calculation logic.

2. Canonical data ownership
- Decision: Python remains the system of record for ledger, profile, plans, and snapshots. Sidecars are stateless compute engines.
- Rationale: avoids split-brain data models and keeps migration logic centralized.

3. Engine integration model
- Decision: use versioned contract interfaces between Python adapters and sidecars, with strict response validation and fallback behavior.
- Rationale: contract versioning reduces integration drift and allows independent evolution of sidecars.

4. Scope of sidecar adoption
- Decision: prioritize sidecars for benchmark/timeline attribution (Ghostfolio) and tax/scenario calculation (Ignidash), while retaining low-complexity logic in Python.
- Rationale: maximizes reuse ROI without introducing unnecessary service complexity.

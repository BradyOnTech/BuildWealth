# Decision Log

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
- Decision: Ghostfolio as source of truth; start with CSV/API ingestion into Ghostfolio, then fan out.
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
- Decision: standardize on a canonical CSV transaction schema with alias mapping, then translate to Ghostfolio import payloads.
- Rationale: gets reliable ingestion live quickly while broker-specific adapters are added incrementally.

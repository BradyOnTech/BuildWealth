# Engine Contracts v1

This directory defines versioned JSON contracts between BuildWealth Python adapters and local TypeScript optional calculation services.

## Rules
- Requests and responses MUST include `contract_version`.
- `contract_version` is a major integer. This folder is `v1` (`contract_version = 1`).
- Breaking changes require a new folder (`v2`) and new schema IDs.
- Adapters validate outbound and inbound payloads against these schemas.
- Optional calculation services are stateless: all required calculation inputs are passed in request payloads.

## Included v1 Contracts
- `portfolio.benchmark.request.schema.json`
- `portfolio.benchmark.response.schema.json`
- `portfolio.attribution.request.schema.json`
- `portfolio.attribution.response.schema.json`
- `plan.scenario.request.schema.json`
- `plan.scenario.response.schema.json`

## Runtime Expectations
- Engine host binding: localhost only.
- Response includes `engine_status` (`ok` or `degraded`).
- If degraded, response should include `fallback_method` and warnings.

## Direction
These contracts remain only for optional calculator compatibility while native BuildWealth services mature. New product work should start from BuildWealth-owned interfaces and v2 workflows.

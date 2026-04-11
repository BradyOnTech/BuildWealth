# Engine Contracts v1

This directory defines versioned JSON contracts between BuildWealth Python adapters and local TypeScript sidecars.

## Rules
- Requests and responses MUST include `contract_version`.
- `contract_version` is a major integer. This folder is `v1` (`contract_version = 1`).
- Breaking changes require a new folder (`v2`) and new schema IDs.
- Adapters validate outbound and inbound payloads against these schemas.
- Sidecars are stateless: all required calculation inputs are passed in request payloads.

## Included v1 Contracts
- `ghostfolio.benchmark.request.schema.json`
- `ghostfolio.benchmark.response.schema.json`
- `ignidash.scenario.request.schema.json`
- `ignidash.scenario.response.schema.json`

## Runtime Expectations
- Engine host binding: localhost only.
- Response includes `engine_status` (`ok` or `degraded`).
- If degraded, response should include `fallback_method` and warnings.

## Attribution
Contract semantics are designed to support logic adapted from:
- Ghostfolio ([MIT](https://github.com/ghostfolio/ghostfolio/blob/main/LICENSE))
- Ignidash ([MIT](https://github.com/schelskedevco/ignidash/blob/main/LICENSE))

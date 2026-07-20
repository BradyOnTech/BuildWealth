# BuildWealth

BuildWealth is a local-first financial command center that combines:
- Portfolio tracking and analytics
- Long-horizon planning and scenario modeling
- Investment research context
- Copilot workflows grounded in your own data

The Python orchestrator (`services/orchestrator`) is the system of record.
Portfolio analytics, import review, asset maintenance, and plan simulation run through BuildWealth-owned services and the v2 product surface.

## Runtime Mode

1. **BuildWealth app**
- Runs BuildWealth as a single local app entrypoint.
- Uses local calculations and local JSON stores.
- Does not require external financial app containers.

## Auth Modes

BuildWealth supports local development auth and a hosted OIDC sign-in foundation.

- `AUTH_MODE=dev` keeps the default local developer workspace.
- `AUTH_MODE=local` enables local email/password registration and login.
- `AUTH_MODE=hosted` or `AUTH_MODE=oidc` disables local password login and uses a configured OIDC provider.

Recommended first private-beta hosted provider: **Auth0**, because it fits
BuildWealth's server-side OIDC adapter without adding a vendor SDK to the product
boundary. See
[`docs/HOSTED_IDENTITY_PROVIDER_DECISION_2026-05-14.md`](./docs/HOSTED_IDENTITY_PROVIDER_DECISION_2026-05-14.md).

Hosted OIDC configuration:

```bash
AUTH_MODE=hosted
AUTH_OIDC_PROVIDER_NAME="Auth0"
AUTH_OIDC_ISSUER_URL="https://tenant.region.auth0.com"
AUTH_OIDC_CLIENT_ID="..."
AUTH_OIDC_CLIENT_SECRET="..."
AUTH_OIDC_REDIRECT_URI="https://your-buildwealth-host/api/auth/hosted/callback"
# Optional: client_secret_basic (default) or client_secret_post
AUTH_OIDC_TOKEN_AUTH_METHOD="client_secret_basic"
# Optional hardening controls
AUTH_OIDC_REQUIRE_ID_TOKEN="true"
AUTH_OIDC_ALLOWED_ID_TOKEN_ALGS="RS256 ES256"
AUTH_OIDC_REQUIRE_MFA="false"
AUTH_OIDC_LOGOUT_URL="https://tenant.region.auth0.com/oidc/logout"
AUTH_POST_LOGOUT_REDIRECT_URI="https://your-buildwealth-host/v2"
AUTH_ACCOUNT_MANAGEMENT_URL=""
AUTH_PASSWORD_RESET_URL=""
AUTH_MFA_ENROLLMENT_URL=""
AUTH_PASSKEY_ENROLLMENT_URL=""
```

If discovery is not available, set `AUTH_OIDC_AUTHORIZATION_ENDPOINT`,
`AUTH_OIDC_TOKEN_ENDPOINT`, `AUTH_OIDC_USERINFO_ENDPOINT`, and
`AUTH_OIDC_JWKS_URI` explicitly. Hosted mode validates ID tokens by default,
including issuer, audience, expiry, nonce, signing algorithm, and UserInfo
subject matching.

Hosted secret-key rotation drill:

```bash
curl -s http://localhost:8090/api/auth/hosted/readiness | jq
curl -s http://localhost:8090/api/security/secrets/rotation/preview | jq
curl -s -X POST http://localhost:8090/api/security/secrets/rotation/apply \
  -H "content-type: application/json" \
  -H "x-buildwealth-csrf-token: ..." \
  -d '{"confirm":"rotate"}' | jq
```

## Quick Start (Standalone Default)

1. Initialize environment files:
```bash
./scripts/init-env.sh
```

2. Review `infra/env/orchestrator.env`.
- Optional external calculators are disabled by default.
- Configure OpenAI/OpenBB as needed.

3. Start BuildWealth:
```bash
docker compose -f infra/docker-compose.yml up -d orchestrator
```

4. Open app + health:
- UI: `http://localhost:8090`
- Health: `http://localhost:8090/health`

5. Optional first snapshot sync:
```bash
curl -s -X POST http://localhost:8090/api/snapshot/sync | jq
```

## Demo Household Data

For end-to-end product testing, seed a realistic average-household dataset:

```bash
./scripts/seed-demo-data.py
```

This creates a mid-career household profile, investment accounts, portfolio transactions,
watchlist items, recommendations, a sample import CSV, and a retirement simulation workspace.
The script is idempotent for rows marked as demo data, so it can be rerun while testing.

Copilot needs a real provider key for live answers. To seed the demo and persist your local
provider settings in one step:

```bash
LLM_API_KEY=... ./scripts/seed-demo-data.py
```

The key is stored in the active workspace's encrypted local secret store and is only returned
to the UI as a masked value.

### Use a ChatGPT/Codex subscription instead of an API key

BuildWealth can also run Copilot through the Codex app-server included in the
orchestrator image:

1. Open **Connections & AI**.
2. Choose **ChatGPT subscription** as the provider.
3. Select **Connect ChatGPT**, then enter the one-time code on OpenAI's device
   authorization page.

This connection is deliberately separate from BuildWealth account sign-in.
ChatGPT is the AI entitlement; BuildWealth local/OIDC auth still protects the
household workspace. The Codex credential is encrypted in the workspace secret
store and materialized only inside a temporary `CODEX_HOME` for each turn.

Subscription-backed usage follows the connected ChatGPT workspace's Codex plan,
credits, rate limits, retention, and admin policy. It avoids a BuildWealth-owned
OpenAI API key and per-token API bill; it does not make inference unlimited or
remove the cost of hosting BuildWealth and Codex app-server. The app-server
dynamic-tool bridge is experimental, so keep the pinned Codex CLI version in
the Docker image and upgrade it deliberately after running the Copilot tests.

Relevant endpoints:

- `GET /api/settings/codex-subscription`
- `POST /api/settings/codex-subscription/connect`
- `POST /api/settings/codex-subscription/disconnect`

For a hosted container (Render, Fly, or a VPS), keep one persistent `/app/data`
volume and one stable `BUILDWEALTH_SECRET_KEY`. Set `CODEX_BIN` only if the CLI
is installed somewhere other than `codex` on `PATH`.

## Maintenance Jobs

Due account-data deletion requests are purged by a private maintenance command, not a public API button:

```bash
docker compose -f infra/docker-compose.yml --profile maintenance run --rm account-data-deletion-purge
```

The job deletes due workspace data after the recovery window and records completion or failure in the control-plane deletion ledger.

## Service Status

BuildWealth runs standalone by default. Service status is available for native runtime checks:
```bash
curl -s http://localhost:8090/api/services/status | jq
```

## Key API Endpoints

- `GET /health`
- `GET /api/services/status`
- `GET /api/telemetry/runtime`
- `GET /api/storage/durable/status`
- `POST /api/storage/durable/migrate`
- `POST /api/storage/durable/rollback`
- `GET /api/storage/backups`
- `POST /api/storage/backups`
- `POST /api/storage/backups/restore`
- `GET /api/storage/protection/status`
- `PUT /api/storage/protection/policy`
- `POST /api/storage/protection/apply`
- `GET /api/git/policy`
- `PUT /api/git/policy`
- `POST /api/git/init`
- `GET /api/git/status`
- `GET /api/git/history`
- `GET /api/git/activity`
- `POST /api/git/activity/cleanup`
- `GET /api/git/diff`
- `POST /api/git/checkpoint`
- `POST /api/git/remote`
- `POST /api/git/push`
- `POST /api/git/pull`
- `GET /api/git/autogit`
- `POST /api/git/autogit/run-due`
- `GET /api/git/restore-preview`
- `POST /api/git/restore-apply`
- `POST /api/snapshot/sync`
- `GET /api/snapshot/latest`
- `GET /api/portfolio/benchmark`
- `GET /api/portfolio/attribution`
- `GET /api/recommendations`
- `POST /api/recommendations/generate/portfolio-risk`
- `POST /api/recommendations/generate/plan-tracking`
- `POST /api/recommendations/generate/cash-liquidity`
- `POST /api/recommendations/generate/run-all`
- `GET /api/recommendations/closure-analytics`
- `POST /api/recommendations/{recommendation_id}/outcome`
- `POST /api/planning/scenarios`
- `GET /api/copilot/context`
- `GET /api/copilot/context/cache`
- `POST /api/copilot/context/cache/reset`
- `POST /api/copilot/chat`

## Local Testing

```bash
cd services/orchestrator
python3 -m pip install -e .[dev]
pytest -q
```

## Make Targets

```bash
make init-env
make up
make ps
make logs
make sync
make telemetry-runtime
make reliability-smoke-storage
make backup
make backup-list
make backup-restore BACKUP_ID=...
make protection-status
make protection-apply LEVEL=hardened INCLUDE_BACKUPS=true
make down
```

## Docs

- [Architecture](./docs/ARCHITECTURE.md)
- [Future State Product Plan (active, 2026-04-26)](./docs/FUTURE_STATE_PRODUCT_PLAN_2026-04-26.md)
- [Git Integration Design](./docs/GIT_INTEGRATION_DESIGN.md)
- [Git Integration Implementation Plan](./docs/GIT_INTEGRATION_IMPLEMENTATION_PLAN.md)
- [Native Capability Architecture](./docs/NATIVE_CAPABILITY_ARCHITECTURE.md)
- [Standalone Operations](./docs/OPERATIONS_STANDALONE.md)
- [Migration and Compatibility](./docs/MIGRATION_AND_COMPATIBILITY.md)
- [Standalone Build Plan (historical)](./docs/STANDALONE_BUILD_PLAN.md)
- [Product Roadmap (historical source of truth, 2026-04-15)](./docs/ROADMAP_SOURCE_OF_TRUTH_2026-04-15.md)

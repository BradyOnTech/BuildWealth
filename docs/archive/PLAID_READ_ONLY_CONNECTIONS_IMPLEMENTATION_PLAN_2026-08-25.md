# Plaid Read-Only Financial Connections — Implementation Plan (2026-08-25)

| Field | Value |
| --- | --- |
| **Status** | Implemented behind a disabled-by-default feature flag; external rollout validation pending |
| **Branch** | `feature/plaid-connection-plan` |
| **Initial audience** | One BuildWealth household |
| **Initial provider** | Plaid |
| **Initial data** | Investment accounts, balances, cash, and current holdings |
| **Safety boundary** | Read-only and advisory; no trades or money movement |
| **Primary surfaces** | Import & Review, Portfolio · Accounts |

---

## Outcome

BuildWealth will let a household connect investment and retirement accounts
through Plaid and keep their current balances and holdings up to date without
removing or weakening manual entry and CSV imports.

The first release will:

- connect an institution through Plaid Link;
- retrieve investment accounts, balances, cash, and current holdings;
- suggest matches to existing manually created BuildWealth accounts;
- require one explicit review before activating a new connection;
- update approved connections automatically each day;
- show connection health, freshness, and important changes;
- keep provider-owned quantities and balances read-only;
- preserve BuildWealth-owned classifications, tax treatment, goals, tags, and
  notes;
- let the user disconnect while choosing whether to keep a frozen local copy
  or remove provider-imported data;
- remain strictly read-only and advisory.

The governing product rule is:

> Connected data makes manual work optional, never impossible. Manual entry and
> CSV import remain permanent, first-class alternatives.

---

## Decisions Locked By Product Review

1. **Manual entry stays.** Connected, manual, and CSV-sourced accounts can
   coexist.
2. **Investments come first.** The first release focuses on brokerage,
   retirement, education, and health-investment accounts rather than bank
   spending and liabilities.
3. **The first audience is one household.** The design must not prevent future
   multi-workspace hosting, but public scale is not a launch requirement.
4. **Read-only is a firm boundary.** BuildWealth will not place trades, move
   money, or request credentials or account/routing numbers for execution.
5. **Initial connection requires review.** Account matches and the first data
   import are previewed before they affect Portfolio.
6. **Later updates are automatic.** Once approved, institution-supplied data is
   applied automatically, with previous snapshots and meaningful changes
   visible for review.
7. **Current state comes before historical activity.** Phase 1 imports accounts,
   balances, cash, and holdings. Connected investment transactions are a later
   phase.
8. **Provider values are not manually overwritten.** Connected quantities and
   balances remain provider-owned; BuildWealth metadata remains editable.
9. **Suspicious changes do not freeze the portfolio.** Apply the latest observed
   data, preserve the prior snapshot, and create a visible review item.
10. **Disconnect offers a retention choice.** Revoke Plaid access immediately,
    then either retain a frozen local copy or remove provider-imported data.
11. **Connections belong to the household workspace.** Record which member
    created the connection, but make the resulting data visible to authorized
    household members.
12. **Daily freshness is enough.** Use normal provider updates and a
    non-billable “Check for updates” read. Do not use paid Investments Refresh
    in Phase 1.
13. **Plaid is the first provider.** Hills Bank is present in Plaid's official
    US coverage data with Investments, Balance, and Transactions support, while
    it is not listed in SnapTrade's public institution table. The internal seam
    remains provider-neutral so another provider can be added later.
14. **Connection fees eventually belong in a paid tier.** There are no current
    customers, so final packaging is deferred. Cost tracking is not deferred.

---

## Scope

### Phase 1 includes

- Plaid Sandbox and qualifying Production Trial support
- Plaid Link for web
- one or more Plaid Items in one household workspace
- investment account discovery
- current balances and cash
- current security holdings
- account-match preview and explicit activation
- automatic daily synchronization
- webhook-triggered synchronization
- connection repair through Link update mode
- connection status and freshness UI
- remote Plaid Item removal
- local keep-or-delete choice on disconnect
- workspace deletion integration
- audit, telemetry, backup/restore, and privacy updates

### Phase 1 does not include

- bank spending transaction synchronization
- investment transaction synchronization
- connected tax-lot history or performance history
- liabilities synchronization
- real-time or paid on-demand refresh
- trading, transfers, Auth, account/routing numbers, or Identity
- mobile-native Plaid SDKs
- multiple connection providers in production
- public multi-tenant scale
- replacing OpenBB or BuildWealth's market-data and analytics services

### Later phases

1. Investment transactions with explicit activity mapping and incomplete-history
   handling.
2. Bank and credit-card Transactions for cash-flow analysis.
3. Liabilities for mortgages, student loans, and credit-card debt.
4. A second provider only when measured coverage or data-quality gaps justify
   the operational cost.

---

## Provider Decision And Coverage Test

Plaid should be implemented first because it serves BuildWealth's likely
whole-household direction and publicly lists Hills Bank. SnapTrade remains the
strongest brokerage-focused alternative if Plaid investment quality is
insufficient.

Before Production approval, run a documented coverage test against exact login
portals—not only institution brand names—for:

- Fidelity
- Vanguard
- Charles Schwab retail and Retirement Plan Center
- E*TRADE / Morgan Stanley
- Merrill and Merrill Benefits
- JPMorgan / Chase
- Wells Fargo
- Edward Jones
- Robinhood
- Interactive Brokers
- Empower
- TIAA
- Principal
- Voya
- Transamerica
- Hills Bank

For each available institution, record:

- Link completion and OAuth behavior;
- account and subtype discovery;
- retirement-plan coverage;
- cash and balance accuracy;
- holding identifiers, quantities, prices, and values;
- cost-basis availability, without making it a Phase 1 requirement;
- stale-data behavior and update timing;
- reconnect/update-mode behavior;
- duplicate-link prevention;
- disconnect behavior.

Passing Phase 1 does not require every institution above to work. It requires
Hills Bank plus an agreed representative set of major investment providers, and
clear fallback messaging for unsupported institutions.

---

## Architecture

### Provider-neutral boundary

Create a narrow `FinancialConnectionProvider` interface owned by BuildWealth.
Plaid-specific request and response types must stop at this boundary.

The interface should cover:

- create an initial or update-mode Link session;
- exchange a temporary connection token;
- inspect an Item and its institution;
- fetch accounts and current investment holdings;
- remove an Item;
- validate and normalize webhook events;
- classify retryable, repairable, and terminal errors.

Implement `PlaidConnectionProvider` with the existing `httpx` dependency. Keep
credentials, hosts, timeouts, retry policy, and response normalization inside
the adapter rather than spreading Plaid calls through routes and portfolio
services.

### Storage ownership

Use three deliberately separate storage concepts:

1. **Connection index in the control database**
   - maps `provider + provider_item_id` to `workspace_id + connection_id`;
   - allows an unauthenticated, verified webhook to find the correct workspace;
   - contains no access tokens or raw financial payloads.
2. **Workspace connection store**
   - contains connection metadata, consented products, status, institution,
     sync state, account mappings, and audit references;
   - remains part of the workspace backup and deletion lifecycle.
3. **Workspace secret store**
   - stores one encrypted Plaid access token per connection;
   - never returns tokens through an API, export, log, error, or audit record.

Recommended secret key:

```text
financial_connection:plaid:<connection_id>:access_token
```

Plaid client ID and environment-specific secret are deployment credentials and
belong in environment or secret-manager configuration, not the workspace
store.

### Connection record

```text
connection_id
provider                         # plaid
workspace_id
connected_by_user_id
provider_item_id                 # case-sensitive
institution_id
institution_name
status                           # pending_review, active, needs_attention,
                                 # disconnect_pending, disconnected, error
environment                      # sandbox, production
consented_products
consent_expiration_at
last_successful_sync_at
last_attempted_sync_at
last_webhook_at
last_error_code                  # normalized; never raw token-bearing payload
last_error_message
created_at
updated_at
disconnected_at
```

### Account mapping

Do not use a Plaid account or Item identifier as the BuildWealth account ID.
Provider identifiers are case-sensitive and should remain opaque.

Each mapping records:

```text
connection_id
provider_account_id
buildwealth_account_id
match_status                     # suggested, confirmed, created, ignored
provider_name
provider_official_name
provider_type
provider_subtype
mask
currency
last_observed_at
```

Extend account normalization so provider metadata is deliberately preserved.
The current account migration reconstructs a small fixed dictionary and would
otherwise discard these fields.

### Observed holdings

Create a separate, versioned observed-holdings store. Do not synthesize BUY
transactions to make connected holdings appear in the transaction-derived
ledger.

An observed holding includes:

```text
connection_id
provider_account_id
buildwealth_account_id
provider_security_id
symbol_or_identifier
name
quantity
institution_price
institution_value
cost_basis                       # nullable
currency
observed_at
provider_payload_version
```

The Portfolio read model resolves current state as follows:

- connected and active account: observed holdings are authoritative for
  current quantity, cash, and institution balance;
- manual or CSV-only account: the existing transaction-derived holdings remain
  authoritative;
- connected account with retained manual history: manual transactions support
  history and provenance, while observed holdings own current state;
- disconnected-and-retained account: the last observation remains visible but
  is clearly stale and no longer refreshes.

OpenBB remains responsible for market prices, research, benchmarks, and
analytics. Institution prices are preserved as source evidence and used for
reconciliation, not silently promoted to the only market-price source.

---

## Connection And Review Flow

1. The user selects **Connect investment account** in Import & Review or
   Portfolio · Accounts.
2. BuildWealth explains what will be collected, that the connection is
   read-only, and that manual import remains available.
3. The server creates a short-lived Plaid Link token for a stable, non-PII
   BuildWealth user identifier and the `investments` product only.
4. Plaid Link handles institution selection, OAuth or credentials, MFA, and
   account consent.
5. The browser sends the temporary public token to BuildWealth.
6. The server exchanges it for an Item ID and access token. The access token is
   encrypted immediately.
7. BuildWealth fetches accounts and holdings and creates a connection preview.
8. Matching rules suggest existing BuildWealth accounts using confirmed user
   choices, account names, types, institution, and mask. They never silently
   merge accounts.
9. The user confirms matches, chooses which accounts to include, and activates
   the connection.
10. BuildWealth writes the first observed snapshot, updates the Portfolio read
    model, creates an Import Report-like connection report, and schedules
    automatic synchronization.

If the user abandons review after token exchange, retain the connection in
`pending_review` for a short documented window. Provide resume and cancel
actions. Cancel must call Plaid `/item/remove` and then shred the local access
token.

### Proposed API

```text
GET    /api/connections
POST   /api/connections/plaid/link-token
POST   /api/connections/plaid/exchange
GET    /api/connections/{connection_id}/preview
POST   /api/connections/{connection_id}/activate
POST   /api/connections/{connection_id}/sync
POST   /api/connections/{connection_id}/update-link-token
POST   /api/connections/{connection_id}/disconnect-preview
DELETE /api/connections/{connection_id}
POST   /api/webhooks/plaid
```

All user-initiated mutations require session authentication, workspace
permission, and CSRF protection. The webhook is the only unauthenticated route;
it requires Plaid signature verification.

Add explicit `connections.read` and `connections.write` permissions rather
than treating a financial connection as an AI-provider setting.

---

## Synchronization Contract

### Cadence

- run once immediately after activation;
- run daily for every active connection;
- run after a verified holdings update webhook;
- let **Check for updates** fetch already-available data without calling paid
  Investments Refresh;
- do not add real-time polling or paid refresh in Phase 1.

### Per-connection safety

- one sync for a connection may run at a time;
- webhook events and sync runs are idempotent;
- a run writes a complete staged snapshot before replacing the active
  observation;
- a partial or invalid provider response never erases the last good snapshot;
- every run records start time, completion time, provider request IDs, counts,
  normalized warnings, and outcome;
- raw secrets and full raw provider responses are not logged.

The current in-process scheduler and file locks are single-process. That is
acceptable for the initial one-household deployment. Before multiple workers or
multiple app machines are enabled, move connection jobs and locks to a durable
database-backed queue or enforce a single scheduler leader.

### Change review

Apply a valid new observation automatically, preserve the previous observation,
and create a Portfolio review item when a versioned change policy detects:

- an account disappearing or becoming inaccessible;
- a holding appearing or disappearing;
- a large unexplained quantity change;
- a large account-value change outside expected market movement;
- an unmapped security;
- a provider balance that materially disagrees with resolved holdings;
- connection consent nearing expiration;
- an Item that needs Link update mode.

Thresholds must live in a tested policy module, not be scattered through UI
code. Initial thresholds can be tuned from Sandbox and household observations
without changing the connection schema.

---

## Connection Repair And Disconnect

### Repair

For `ITEM_LOGIN_REQUIRED`, expiring consent, changed permissions, or newly
available accounts:

1. mark the connection `needs_attention`;
2. keep the last good snapshot visible with a stale warning;
3. create an update-mode Link token using the existing access token;
4. let the user repair the Item;
5. resync and clear the warning after a successful observation.

Prevent duplicate Items by checking the household's existing institution
connections before exchanging another public token. Direct the user to repair
or extend the existing Item when appropriate.

### Disconnect

The disconnect preview offers:

- **Disconnect and keep a frozen copy**
- **Disconnect and remove connected data**

Both paths:

1. mark the connection `disconnect_pending` and prevent new reads;
2. call Plaid `/item/remove` while the access token still exists;
3. retry safely if Plaid is unavailable;
4. remove the access token only after confirmed removal or a reviewed terminal
   “already removed” result;
5. end provider billing;
6. write a security and portfolio audit event.

The remove-data path then deletes provider observations and mappings without
deleting unrelated manual accounts or transactions. The keep-data path marks
the retained snapshot disconnected and stale.

### Workspace deletion

Requesting workspace or household deletion must immediately begin remote Plaid
Item removal rather than waiting through the local recovery window while access
and billing continue. The deletion UI must explain that canceling local deletion
does not restore revoked financial connections; the user would reconnect them.

The purge worker must not shred a Plaid access token until remote removal is
confirmed or recorded for operator retry. A permanently failed remote removal
must remain a visible maintenance failure rather than being hidden by local
filesystem deletion.

---

## User Experience

### Import & Review

Add a primary **Connect investment account** card above the CSV workbench:

- explains read-only access and collected data;
- launches Plaid Link;
- shows the account-match and first-import preview;
- links to manual entry and CSV as permanent alternatives;
- shows pending connection reviews that can be resumed or canceled.

### Portfolio · Accounts

For each account, show:

- manual, CSV, or connected source;
- institution and masked identifier;
- connection health;
- last successful update;
- connected by household member;
- personal/shared planning designation;
- repair, check, and disconnect actions.

Connected balance and quantity fields are visibly read-only. BuildWealth-owned
account metadata remains editable.

### Portfolio and Today

- label stale connected data in Portfolio;
- show significant connection changes as review items, not silent toast-only
  messages;
- route unhealthy connections to the repair flow;
- never describe provider data as real-time;
- keep manual accounts fully usable when Plaid is unavailable.

### Privacy copy

Before Link, state plainly:

- Plaid will connect to the institution and provide permissioned financial
  data to BuildWealth;
- BuildWealth does not receive the user's bank password;
- the connection is read-only;
- which account and holding data will be stored;
- automatic updates continue until disconnect;
- the user can disconnect and choose whether to retain a frozen copy.

Update the public privacy notice, terms, deletion language, and provider list.
Configure Plaid Data Transparency Messaging and a production use case before
requesting Production access.

---

## Security And Reliability Requirements

1. Store the Plaid client secret outside the workspace and access tokens in the
   encrypted workspace secret store.
2. Never expose access tokens or the Plaid secret in browser code, URLs, logs,
   telemetry, audit metadata, errors, exports, or connection previews.
3. Verify every webhook's `Plaid-Verification` JWT, algorithm, key, issued-at
   time, and raw-body SHA-256 before accepting it.
4. Cache webhook verification keys with a bounded lifetime and safe rotation.
5. Record webhook idempotency and reject stale replay attempts.
6. Use explicit outbound timeouts and bounded retries with jitter for safe
   read operations.
7. Do not automatically retry public-token exchange or remote Item removal
   unless idempotency is proven for the specific operation.
8. Add a Content Security Policy compatible with Plaid Link's documented script,
   frame, and connection origins; retain same-origin application controls.
9. Apply atomic file writes to new connection and observation stores.
10. Treat restore from backup as untrusted connection state: verify each
    restored Item with Plaid before resuming automatic sync, so an old backup
    cannot resurrect a disconnected connection.
11. Add provider availability and failure counts to runtime telemetry without
    account identifiers or financial values.

---

## Cost Controls

- Initialize only `investments` in Phase 1.
- Do not call `/investments/transactions/get`; it activates a second Investments
  subscription.
- Do not initialize Transactions, Liabilities, Auth, Identity, or Balance.
- Use ordinary account and holdings reads; do not call Investments Refresh.
- Track active Items, enabled products, pending-review Items, broken Items, and
  disconnect-pending Items.
- Warn locally when a pending-review connection approaches its cleanup deadline.
- Remove abandoned and disconnected Items remotely.
- Add an operator-readable monthly connection inventory before leaving Trial.
- Confirm exact Pay-as-you-go pricing in the Plaid Dashboard before inviting
  anyone outside the household.

Plaid Sandbox is free. Qualifying new US/Canada teams can use a Production Trial
with up to 10 lifetime-created Items. Exact paid rates are shown during the
Production application rather than in public documentation.

---

## Implementation Sequence

### Task 1: Record the domain and provider decision

**Files:**

- Add an ADR under `docs/adr/`
- Update `CONTEXT.md`
- Update `docs/ARCHITECTURE.md`
- Update `docs/archive/STANDALONE_BUILD_PLAN.md`

- [x] Define Financial Connection, Provider Item, Account Mapping, Observation,
  Connection Report, Connection Health, and Staleness.
- [x] Record Plaid-first, provider-neutral, manual-permanent, and read-only
  decisions.
- [x] Remove Plaid from blanket “out of scope” language.

### Task 2: Add configuration and the provider client

**Files:**

- Modify `services/orchestrator/src/buildwealth_orchestrator/settings.py`
- Add `services/orchestrator/src/buildwealth_orchestrator/clients/plaid.py`
- Add focused client tests
- Update example environment files

- [x] Add environment, client ID, secret, webhook URL, redirect URI, country,
  timeout, and feature-flag settings.
- [x] Implement the narrow provider interface and normalized error model.
- [x] Use recorded fixtures with all secrets scrubbed.
- [x] Add readiness output that reports configuration without revealing values.

### Task 3: Add connection persistence and migrations

**Files:**

- Modify control database migrations and store
- Modify `workspace_services.py`
- Add a versioned workspace connection store
- Extend portfolio account normalization
- Add persistence and migration tests

- [x] Add the webhook lookup index.
- [x] Add workspace connection, mapping, sync-run, and observation schemas.
- [x] Store access tokens only through `WorkspaceSecretStore`.
- [x] Use atomic writes and preserve provider metadata during migration.
- [x] Include new files in backup, deletion preview, protection policy, and
  account export rules as appropriate.

### Task 4: Build Link and first-import review

**Files:**

- Add `routes/connections.py`
- Register the router in `main.py`
- Extend `web-v2/lib/api.js`
- Extend `web-v2/views/import_sync.js`
- Add API and UI tests

- [x] Create initial Link tokens server-side.
- [x] Exchange public tokens and encrypt access tokens immediately.
- [x] Fetch accounts and holdings into a staged preview.
- [x] Suggest but never silently apply account matches.
- [x] Support account inclusion, activation, resume, and cancel.
- [x] Produce durable Connection Reports and audit events.

### Task 5: Integrate observed holdings into Portfolio

**Files:**

- Add an observed-holdings service/store
- Modify the Portfolio read-model boundary
- Extend Portfolio schemas and analytics fixtures
- Extend Portfolio · Accounts UI
- Add deterministic reconciliation tests

- [x] Prefer observations for current state on active connected accounts.
- [x] Preserve manual history without double-counting current holdings.
- [x] Resolve provider securities through the Asset Registry.
- [x] Quarantine unmapped securities for review.
- [x] Show institution-value versus BuildWealth market-value evidence.
- [x] Make provider-owned fields read-only and BuildWealth metadata editable.

### Task 6: Add automatic sync and webhooks

**Files:**

- Add a connection sync coordinator
- Add the Plaid webhook route and verifier
- Extend scheduler startup/shutdown logic
- Extend runtime telemetry
- Add webhook, concurrency, and idempotency tests

- [x] Run per connection rather than through the module-level default store.
- [x] Stage and validate complete observations before replacement.
- [x] Verify webhook signatures against the exact raw request body.
- [x] Deduplicate webhook events and serialize sync by connection.
- [x] Implement daily sync and non-refresh **Check for updates**.
- [x] Create review items from the versioned change policy.

### Task 7: Add repair, disconnect, and deletion lifecycle

**Files:**

- Extend connection routes and UI
- Modify account-data deletion orchestration
- Extend maintenance worker behavior
- Add lifecycle and failure-recovery tests

- [x] Implement Link update mode.
- [x] Prevent and remediate duplicate Items.
- [x] Implement keep-frozen and remove-data disconnect choices.
- [x] Remove the Plaid Item before shredding its token.
- [x] Persist retryable remote cleanup work.
- [x] Integrate immediate remote revocation with delayed local deletion.

### Task 8: Complete privacy, security, and rollout gates

**Files:**

- Modify `web-v2/privacy.html` and related legal drafts
- Modify `infra/Caddyfile`
- Update deployment and operations documentation
- Add a provider coverage test record

- [ ] Configure Plaid Dashboard branding, redirect URIs, webhook URL, and Data
  Transparency Messaging use case.
- [x] Add the Plaid-compatible Content Security Policy; production browser
  verification remains a rollout gate.
- [ ] Exercise secret-key rotation with active Plaid tokens in Sandbox.
- [ ] Exercise backup restore without reviving a removed Item.
- [ ] Run the exact-institution coverage matrix.
- [ ] Confirm paid pricing and add cost alerts before leaving Trial.

---

## Test Strategy

### Unit tests

- Plaid payload normalization
- account-type and subtype mapping
- security identifier mapping and unknown-security quarantine
- account match scoring and explicit confirmation
- observed-versus-manual precedence
- change-detection policy
- connection state transitions
- safe error normalization
- no-secret serialization

### API tests

- authentication, workspace isolation, permissions, and CSRF
- Link token creation and exchange
- activation idempotency
- sync serialization
- update-mode tokens
- disconnect retention choices
- remote-removal retry behavior
- webhook JWT, freshness, body hash, and replay rejection
- account deletion with active and failed-removal connections

### UI tests

- pre-Link explanation
- first-import review and matching
- manual/CSV alternatives remain visible
- connected fields are read-only
- freshness and stale states
- repair flow
- disconnect preview and both retention choices
- keyboard and small-screen behavior around Plaid Link launch/return

### Sandbox workflows

- successful initial Link
- OAuth redirect and return
- duplicate institution attempt
- abandoned pending review
- holdings update webhook
- Item login required and repair
- consent expiration warning
- provider timeout during sync
- provider timeout during disconnect
- account removed or permission revoked
- backup restore after remote Item removal

---

## Release Gates

The household beta may start only when:

- a connected account cannot place a trade or move money through any API path;
- manual accounts and CSV import still work with Plaid disabled;
- initial account matching requires explicit confirmation;
- repeated syncs do not duplicate accounts or holdings;
- an invalid or partial response cannot erase the last good snapshot;
- provider-owned balances and quantities cannot be edited through UI or API;
- webhook verification and replay protection pass;
- disconnect calls `/item/remove` before token destruction;
- workspace deletion cannot silently leave a billable Plaid Item active;
- logs, reports, exports, backups, and errors have been checked for secret
  leakage;
- Hills Bank and the agreed representative brokerage set have recorded test
  results;
- privacy and consent copy is visible before Link;
- active connection counts and enabled products are observable;
- exact post-Trial pricing has been reviewed.

---

## Success Measures

For the first household release:

- connect at least one major brokerage or retirement provider and Hills Bank;
- complete connection and account matching without editing a file;
- represent current holdings and cash without double-counting manual history;
- finish seven consecutive daily syncs without duplicate or lost observations;
- repair a forced Sandbox Item error through update mode;
- disconnect successfully through both local retention choices;
- preserve full manual and CSV workflows with the Plaid feature flag off;
- explain the source and freshness of every connected balance and holding.

---

## Official References

- Plaid Link: <https://plaid.com/docs/link/>
- Plaid Investments: <https://plaid.com/docs/investments/>
- Plaid billing: <https://plaid.com/docs/account/billing/>
- Plaid Items and removal: <https://plaid.com/docs/api/items/>
- Plaid webhook verification:
  <https://plaid.com/docs/api/webhooks/webhook-verification/>
- Plaid institution coverage:
  <https://plaid.com/documents/us_institution_coverage.csv>
- Plaid Data Transparency Messaging:
  <https://plaid.com/docs/link/data-transparency-messaging-migration-guide/>
- SnapTrade supported brokerages:
  <https://support.snaptrade.com/brokerages>
- SnapTrade pricing: <https://snaptrade.com/pricing>

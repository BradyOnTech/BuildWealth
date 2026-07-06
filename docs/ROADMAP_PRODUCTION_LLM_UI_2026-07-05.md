# Roadmap: Production, LLM Strategy, and UI Density — 2026-07-05

Three roadmap areas raised on 2026-07-05, grounded in what the codebase
already has. Each section states current state honestly, then sequences the
work smallest-first.

---

## 1. Production, production database, authentication

### Where we actually are

More is in place than "local prototype" suggests:

- **Auth**: `AUTH_MODE` already supports `dev`, `local`, `oidc`, `hosted`
  (plus `secure`/`test`/`disabled` paths). OIDC identity-provider decision is
  documented (HOSTED_IDENTITY_PROVIDER_DECISION_2026-05-14). Sessions, CSRF
  tokens, and per-request permission checks exist.
- **Multi-tenancy**: the control plane (SQLite) models users, organizations,
  memberships, and workspaces; `WorkspaceServiceFactory` isolates each
  workspace's storage tree. Account closure/retention policy is drafted and
  partially implemented.
- **Data layer**: control plane is SQLite; workspace data is JSON files +
  SQLite (context index) under per-workspace roots. Encrypted secret store
  with key rotation exists.

### The honest gaps

1. **SQLite + JSON files under concurrency.** Fine for single-household
   local-first (the product's soul — keep it). Not fine for a hosted fleet:
   no connection pooling, no row-level locking, backup story is file copy.
2. **Single process, single container.** Scheduled sync, embeddings, and
   request serving share one event loop.
3. **No migration discipline.** Schema versions exist per-payload, but there
   is no ordered migration runner for the control DB.

### Sequence (smallest useful step first)

1. **Storage abstraction seam, not a rewrite.** ✅ *Done 2026-07-06.*
   `ControlDatabase` connection seam (control_database.py): the store owns
   SQL and business rules; the adapter owns connections, transactions, and
   dialect quirks. SQLite stays the local-first default forever; adding
   Postgres is a bounded task documented as a recipe in that module
   (implement one adapter, review the marked `# dialect:` sites, run the
   auth/workspace suite as the acceptance gate). Workspace JSON payloads
   stay files — per-tenant and small; move them only when metrics say
   otherwise.
2. **Migration runner** ✅ *Done 2026-07-06.* Hand-rolled, not alembic —
   eight tables of readable SQL don't justify an ORM dependency
   (control_db_migrations.py): append-only numbered migrations, one explicit
   transaction each (DDL-safe rollback), recorded in schema_migrations; the
   pre-runner schema is baseline 0001 and existing databases adopt it
   idempotently on boot.
3. **Harden the hosted auth path**: finish OIDC end-to-end against the chosen
   IdP, add rate limiting on auth endpoints, session revocation list,
   and audit-log the permission denials that already exist.
4. **Deploy shape**: one app container + managed Postgres + object storage
   for workspace trees/backups. Add a worker process (same image, different
   entrypoint) for sync/embeddings when the event loop shows contention —
   not before.

**Principle: local-first is the product; hosted is a deployment mode of the
same code.** Anything that would fork the two (a hosted-only data model, a
hosted-only feature) needs a strong reason.

---

## 2. LLM flexibility and subscriptions

### Where we actually are

`llm_clients.py` already abstracts OpenAI, Gemini, Anthropic, xAI, and any
OpenAI-compatible endpoint (which covers local Ollama/LM Studio). Keys are
BYOK, stored encrypted per workspace, hot-reloaded on settings save.
Embeddings run locally via Ollama. So "use various LLMs" is largely built —
what's missing is *policy* and *packaging*.

### Roadmap

1. **Per-task model routing.** One global model is wrong: Copilot chat wants
   the best reasoning model; recommendation drafting and outcome summaries
   can run on a cheap/local model; embeddings already run locally. Add a
   small routing table (`task class → provider/model`) with the current
   single-model behavior as default. This is the highest-leverage piece and
   is pure configuration plumbing on top of the existing client factory.
2. **Cost visibility before cost billing.** Meter tokens per provider/task in
   a local ledger and show it in Settings ("Copilot used ~$1.40 of your
   OpenAI key this month"). BYOK users deserve this anyway, and no
   subscription can be priced without these numbers.
3. **Subscription shape (hosted tier only).** BYOK stays free forever in the
   local app — that's the trust position. The hosted product can offer:
   - *Hosted Free*: bring your own key.
   - *Hosted Plus*: managed keys with a monthly included budget (metered by
     the ledger from step 2), overage disabled by default.
   Payment integration (Stripe) only enters at this step, after production
   auth (section 1) is real.
4. **Graceful degradation is a feature.** Every LLM surface already has a
   no-key fallback; keep treating "no LLM configured" as a first-class mode.
   The measured/data-driven features (simulations, fees, drift, housing)
   must never sit behind a subscription.

---

## 3. UI density — "condense, don't scroll"

### The observation

Each page is honest but *busy*: Today has hero + command center + cards +
room; Portfolio is six Movements deep; a user scrolls to find things they
didn't know they were looking for. Good apps compress: one screen answers
"how am I doing?", and everything else is one obvious click away.

### Design principles to adopt

1. **One page, one question.** Today = "how am I doing and what's next?"
   Portfolio = "what do I own and is it healthy?" Plan = "will I make it?"
   Anything on a page not serving its question moves behind a click.
2. **Summary card → detail on demand.** Each analytical panel (fees,
   diversification, housing, risk) collapses to a one-line verdict chip with
   its number ("Fees $27/yr — index-cheap ✓", "Spread 34/100 — concentrated")
   that expands in place. The full prose lives one click deep, not in the
   scroll path.
3. **Verdict first, evidence second.** Panels currently lead with metrics
   grids. Lead with the sentence a person needs ("Nothing to fix here"),
   then the numbers for those who want them.
4. **Movements become a table of contents.** Portfolio's section heads turn
   into an in-page nav (sticky, small) so "find what you want without
   knowing what you want" is a scan of six labels, not six screens.
5. **Kill duplicate tellings.** Concentration currently appears in risk
   alerts, diversification, and Today. One canonical card per fact; other
   surfaces link to it rather than restating it.

### Sequence

1. **Portfolio first** (worst offender): collapse Movements III–IV panels to
   verdict chips + expanders, add the in-page section nav. No data changes —
   pure presentation, all render functions already return self-contained
   panels.
2. **Today second**: cap the visible command cards at 3 with "show all",
   fold health highlights into the hero marginalia, move the Room below a
   fold-line summary.
3. **Measure by clicks-to-answer**: for five common questions ("am I
   diversified?", "what do fees cost me?", "how's the house factored?",
   "what changed this month?", "what should I do next?") the answer should
   be visible or one click from the landing page.

---

*Enrichment status note (same date): the built-in fund catalog now seeds
expense ratios for its 46 fund entries; the fee panel reaches full coverage
on common portfolios without user typing. Provider-fed enrichment (live
lookups, fund look-through for overlap detection) is the next data layer and
pairs with the diversification score's stated look-through caveat.*

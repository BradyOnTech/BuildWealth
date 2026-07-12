# App Review Tracker — 2026-07-12

Source: full-codebase review (backend orchestrator, web-v2 frontend, data/docs/infra/testing).
Status legend: unchecked = not started. Check items off as they are completed.

## Overall verdict

BuildWealth's feature surface is broad and genuinely finished (no stub pages, no unwired
buttons, zero TODO markers), testing is unusually strong (126 pytest files, 41 frontend
test files, Playwright e2e), and the domain thinking in `CONTEXT.md` and the ADRs is a
real asset. The weaknesses are not missing features — they are structural debt
concentrated in a few specific places.

---

## Improvements (priority order)

### 1. Split `main.py`

`services/orchestrator/src/buildwealth_orchestrator/main.py` is 23,566 lines defining all
230 routes in one file, on top of 94 well-factored service modules. It is the
merge-conflict magnet, the untestable layer, and the reason handler logic is hard to audit.

- [x] Introduce FastAPI `APIRouter` modules, one per domain: `portfolio`, `plans`,
      `recommendations`, `copilot`, `auth`, `storage`, `research`, `imports`, `git`
- [x] Move routes incrementally, domain by domain, keeping tests green after each move
- [x] Investigate stray malformed markers deep in the file (e.g. an `@APP.GET(` around
      line 20635) — possible incomplete/auto-generated edits
- [ ] Target: no file over ~1,000 lines when done (repo preference is ~300 for new code)
      — progress: main.py 23,566 → 17,278 (route layer fully extracted to 19
      `routes/*.py` modules; remaining bulk is helpers/copilot tools/context
      assembly, a follow-up extraction). Note: the `@APP.GET(` marker was a
      review-scan artifact; none exist in the file.

### 2. Add CI

There is no CI at all (no `.github/`, nothing gating commits) despite the large test suite.

- [x] GitHub Actions workflow running `make test` (pytest, 126 files)
- [x] Wire the 29 orphaned `node:test` `*.test.mjs` frontend unit tests into a runner
      (`node --test`; add to Makefile and/or npm scripts) — currently they only run manually
- [x] Add the Playwright browser suite (`npm run test:web-v2:browser`) to CI
- [ ] Gate merges/pushes on the suite passing (requires pushing the workflow and enabling branch protection on GitHub — manual step)

### 3. Copilot streaming and cancel

Chat is a blocking POST with a "thinking" flag and no `AbortController`
(`web-v2/views/copilot.js:358-413`). Most user-visible improvement available.

- [x] SSE (or chunked) streaming of copilot responses
- [x] Cancel button wired to `AbortController`
- [x] Stop persisting transport errors into the conversation as fake assistant turns
      (`copilot.js:402`) — show a transient banner instead

### 4. Fix the secrets story

Workspace secrets use a home-rolled HMAC-SHA256 stream cipher
(`services/workspace_settings.py:81-150`), and the symmetric key is stored in plaintext at
`data/control/local_secret.key` next to the ciphertext — at-rest encryption protects
against essentially nothing.

- [ ] Replace home-rolled cipher with the `cryptography` library (e.g. Fernet)
- [ ] Move the key out of the data dir: macOS Keychain, or passphrase-derived key
- [ ] Migration path for existing encrypted secrets

### 5. JSON-store integrity

The SQLite control DB has a disciplined migration runner; the much larger JSON/YAML
surface has `schema_version` fields but no migration runner and no locking. Atomic
per-file `os.replace` does not prevent read-modify-write races between concurrent
requests. Breaks first on the hosted-SaaS path.

- [ ] Per-store locking (asyncio lock or file lock) around read-modify-write cycles
- [ ] Ordered migration runner for JSON stores (mirror `control_db_migrations.py` discipline)
- [ ] Tests exercising concurrent writers against the same store

### 6. Delete dead weight

- [x] Remove legacy v1 frontend `web/` (~10.5k lines, still bundled and mounted at
      `/static` via `main.py:470` but never served as a page)
- [x] Remove empty, unenforced `contracts/engine/v1/` placeholder
- [x] Remove empty `data/ignidash/` directory (no code references)
- [x] Fix or delete untracked `services/orchestrator/tests/plan.test.mjs` — broken as
      written: missing all imports, wrong directory (relative paths resolve to
      `services/orchestrator/views/`, which doesn't exist; the real test lives in
      `web-v2/tests/plan.test.mjs`)

### 7. Smaller items

- [ ] Schedule automated backups — `data/backups/` is empty even though the backup
      machinery and Make targets exist
- [ ] Fix hardcoded `python3.12` site-packages path in `infra/docker-compose.yml`
      (silently breaks web-v2 hot-mount on a base-image Python bump; local venv is 3.14)
- [ ] Frontend dedup: ~6 views reimplement skeleton loaders and money/percent formatters
      (`fmtMoneyOrDash`, `fmtUsdOrEmpty`, `fmtUsdSafe`, `fmtPctOrDash`) despite
      `lib/format.js` — consolidate into shared helpers
- [ ] Accessibility: keyboard navigation + focus management for custom dropdowns
      (workspace/account/status/tools drawer, `app.js:634`); add `aria-live` regions for
      async state changes (currently 1 in the whole app)
- [ ] Remove unreachable `renderPlaceholder()` "Coming soon" branch in
      `web-v2/views/profile.js:254`
- [ ] Review the 155 broad `except Exception` sites — at minimum add logging where
      external-call failures are currently swallowed (`research.py` etc.)
- [ ] Refresh hardcoded default model ids in `llm_clients.py` (will silently rot)

---

## Features to add (ranked by leverage against what's already built)

### 1. Tax strategy tools

Composition of existing services (tax engine, RMD projections, Social Security modeling,
lot-level cost basis, scenario engine).

- [ ] Tax-loss harvesting candidates (lots below basis, wash-sale awareness)
- [ ] Roth conversion ladder planner as a scenario type

### 2. Scheduled morning brief

Digest combining the recommendations sweep, risk alerts, plan-resilience drift, and
pending Conflict Review Items. Snapshots, recommendation factory, and inbox already exist.

- [ ] Scheduler for the sweep/digest
- [ ] Delivery surface: "since you last looked" panel on Today (and/or email)

### 3. LLM cost visibility UI

Usage ledger already meters tokens by month (`data/storage/llm_usage_ledger.json`); it
has no Settings surface. Already on the roadmap; nearly free.

- [ ] Settings panel showing usage/cost by month, provider, model

### 4. Per-task LLM model routing

Roadmap item; the multi-vendor client work is the prerequisite, this is the payoff.

- [ ] Task-class → provider/model mapping (cheap models for classification/extraction,
      expensive model for copilot reasoning)

### 5. Fund look-through for overlap/diversification

Fund-overlap and diversification analytics currently treat funds as opaque; roadmap
sketches this as "asset enrichment."

- [ ] Provider-fed fund holdings data
- [ ] Look-through overlap and diversification for VTI/VXUS/BND-style portfolios

### 6. Turn on semantic retrieval

The embeddings path in `context_intelligence.py` (4,093 lines) is fully built but ships
as `DisabledEmbeddingClient` — an entire subsystem unexercised.

- [ ] Wire embeddings to local Ollama by default (setup already anticipates
      `host.docker.internal:11434`)
- [ ] Exercise/verify the semantic retrieval path once enabled

---

## Suggested sequencing

1. **First:** split `main.py` (§1) and add CI (§2) — they make every subsequent change
   cheaper and safer.
2. **Then:** copilot streaming (§3) as the first user-facing win.
3. Remaining improvements and features in listed order, adjusting for appetite.

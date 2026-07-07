# Production Hosting Plan

**Written:** 2026-07-07 · Reference for hosting decisions as BuildWealth
moves from "runs on my Mac" to a hosted product. Companion to
[DEPLOYMENT.md](DEPLOYMENT.md) (the how-to) and
[ROADMAP_PRODUCTION_LLM_UI_2026-07-05.md](ROADMAP_PRODUCTION_LLM_UI_2026-07-05.md).

## The constraint that drives every choice

BuildWealth's state is **SQLite (control plane) + a tree of JSON files per
workspace**, all under `./data`. That means the app needs a real disk
wherever it runs. Any hosting decision that pretends the app is stateless —
serverless containers, scale-to-zero, multi-instance load balancing — breaks
on this until two things happen:

1. Control DB on Postgres (the seam exists: `control_database.py`, a
   bounded adapter task).
2. Workspace files on a database or object storage (a real project, not yet
   designed).

Neither is needed for a private instance. Both are needed before serious
multi-instance/public hosting. Plan around that honestly.

A second, subtler constraint: **background work runs in-process** (the
scheduled sync heartbeat, sweeps). Anything that stops the process when idle
— scale-to-zero, aggressive auto-stop — silently kills the heartbeat.

## Phase 1 — Private instance (now)

Two good options; both are prepared in this repo. Pick by taste:

### Option A: Small VPS + Caddy (built and verified)

`infra/docker-compose.prod.yml` + `infra/Caddyfile`. Hetzner CX22 (~€5/mo)
or DO 2GB droplet. You own the box; backups are a tar of `./data` plus an
off-box copy; TLS is automatic via Caddy/Let's Encrypt.

- **For:** cheapest, fully understood stack, disk is just a disk, no
  platform opinions to fight. Verified end-to-end already.
- **Against:** you are the ops team (OS updates, firewall, docker upgrades).

### Option B: Fly.io (config written: `services/orchestrator/fly.toml`)

Fly runs the same Docker image on their edge; TLS and the proxy are theirs
(no Caddy container), a Fly Volume mounts at `/app/data`.

```bash
cd services/orchestrator
fly launch --no-deploy        # once: creates the app, prompts region
fly volumes create buildwealth_data --size 3
fly deploy
fly certs add app.example.com # custom domain; or use yourapp.fly.dev
```

- **For:** least ops burden — no server to patch, TLS/domains handled,
  `fly deploy` is the whole update story, volume snapshots built in
  (5-day retention; still copy backups off-platform).
- **Against / must-know:**
  - **Volumes are pinned to one host in one region.** Fine for one
    instance; it is the same "the disk is the app" reality as a VPS,
    dressed nicer.
  - **`auto_stop_machines` must stay off** or the sync heartbeat dies
    when the machine sleeps. The fly.toml pins `min_machines_running = 1`.
  - Pricing is usage-based and less predictable than a fixed VPS
    (roughly $5–10/mo for one small always-on machine + volume).
  - First deploy needs a `fly.toml` sanity pass — it's written to Fly's
    documented format but nothing substitutes for the first real deploy.

**Recommendation: either is right; Fly.io if you value zero server
maintenance, VPS if you value fixed cost and full control.** Auth posture,
backups discipline, and the app itself are identical in both.

## The Neon question (and managed Postgres generally)

Neon (serverless Postgres with branching/PITR) is a good product — **for the
part of the problem BuildWealth doesn't have yet.** Today Postgres would
replace only the control DB (users, sessions, workspaces — kilobytes), while
the actual financial data stays in workspace files on a volume. You'd take
on: implementing the Postgres adapter, a network dependency in the auth hot
path, cold-start latency on the free tier — and still need the disk.

**Adopt Neon when the public-product milestone arrives**, specifically when
any of these become true:

- more than one app instance (sessions must be shared state),
- registration opens to strangers (managed backups/PITR for the control
  plane stop being optional),
- workspace data itself moves to Postgres/object storage (the real
  statelessness project — design work, not an adapter).

The migration path is already bounded: implement `ControlDatabase` for
psycopg per the recipe in `control_database.py`, review the marked
`# dialect:` sites, point `CONTROL_DB_URL` at Neon, run the auth/workspace
suite as the acceptance gate.

## Phase 2 — Hosted identity (when you create the Auth0 tenant)

Independent of hosting choice: fill `AUTH_OIDC_*`, flip `AUTH_MODE=hosted`.
Password login turns off; Auth0 owns MFA/resets/passkeys
(decision record: HOSTED_IDENTITY_PROVIDER_DECISION_2026-05-14.md).

## Phase 3 — Public product (the checklist that gates it)

In order, from ROADMAP + DEPLOYMENT docs:

1. Auth0 live (Phase 2) — no public launch on shared-password auth.
2. Neon/Postgres for the control plane (above).
3. Workspace storage design: files → object storage or DB; this is the
   biggest single engineering item on the path.
4. Second process for background work (sync/embeddings) once the event
   loop shows contention — same image, different entrypoint.
5. Operations: error reporting (e.g. Sentry), log retention, restore
   drills on a schedule.
6. Legal surface live and accurate (privacy/terms/AI disclosure pages
   exist in the repo; they must be reviewed and served).
7. Load reality check — only then revisit multi-region/edge anything.

## What is already true regardless of platform

- The image is the artifact; dev and prod run the same build.
- Schema migrates itself at boot (`schema_migrations` ledger).
- `AUTH_MODE=secure`: registration locks after the owner; rate limits,
  session revocation, and the security audit trail are active.
- `/health` verifies database/storage/disk and returns 503 when degraded —
  point UptimeRobot at it whichever platform you choose.
- Backups are a copy of `./data`, restore is untar + restart. **Test the
  restore once before trusting it.**

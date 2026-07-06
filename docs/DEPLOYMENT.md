# Deploying BuildWealth as a private hosted instance

This is the path from "runs on my machine" to "my BuildWealth at
`https://app.example.com`, for me and my household." It deliberately ships
the smallest safe thing: one server, the same Docker image you run locally,
HTTPS via Caddy, and password login that closes registration after the owner
account exists. Public multi-user launch is a later, bigger step — the last
section says exactly what it adds.

## What you get

- The full app over HTTPS at your domain, certificates managed automatically.
- `AUTH_MODE=secure`: email/password login, Secure+HttpOnly cookies, CSRF
  enforcement, **no dev auto-login**, and registration that locks after the
  first (owner) account is created.
- All data on the server in `./data` — same layout as local, SQLite + JSON.
  No external database service. (The storage seam exists for Postgres later;
  a private instance genuinely does not need it.)

## Prerequisites

- A small VPS (1–2 GB RAM is plenty): Hetzner, DigitalOcean, etc., with
  Docker and the compose plugin installed.
- A domain (or subdomain) with an **A record pointing at the server's IP**
  before first start — Caddy needs it resolving to obtain certificates.
- Ports 80 and 443 open in the provider's firewall.

## Deploy

```bash
# on the server
git clone <your-repo-url> buildwealth && cd buildwealth

# production environment
cp infra/env/orchestrator.prod.env.example infra/env/orchestrator.prod.env
# review it — AUTH_MODE=secure is already set; nothing is mandatory to edit

# your domain (Caddy reads this)
export BUILDWEALTH_DOMAIN=app.example.com

docker compose -f infra/docker-compose.prod.yml up -d --build
```

First visit to `https://app.example.com` shows the sign-in screen; use
**Create account** — that first registration becomes the owner and closes
registration (strangers who find the URL get 403). Set
`AUTH_ALLOW_OPEN_REGISTRATION=true` in the env file only if other household
members should be able to self-register.

The orchestrator is not published on any host port — it is reachable only
through Caddy. The dev compose file (`docker-compose.yml`) remains the local
workflow; nothing about local use changes.

## Verify the stack locally first (optional but recommended)

The same production compose runs on a workstation with a locally-trusted
certificate — `BUILDWEALTH_DOMAIN` defaults to `localhost`:

```bash
docker compose -f infra/docker-compose.prod.yml up -d --build
curl -sk https://localhost/api/auth/config   # auth_mode: "secure"
```

Register, log in, confirm strangers get 403 — then tear down with
`docker compose -f infra/docker-compose.prod.yml down`. Note this uses your
real `./data` directory unless you override the volume.

## Backups

Everything lives in `./data`. A nightly cron on the server:

```bash
# /etc/cron.d/buildwealth-backup  (02:10 nightly, keep 14 days)
10 2 * * * root cd /root/buildwealth && tar czf /var/backups/buildwealth-$(date +\%F).tar.gz data && find /var/backups -name 'buildwealth-*.tar.gz' -mtime +14 -delete
```

Copy the archives off the box (rclone to object storage, or even scp to your
Mac on a schedule). **A backup that only exists on the server is not a
backup.** Restore = stop the stack, untar over `./data`, start the stack.

The app's own backup tooling (Data & Recovery in the UI) writes archives
into `data/backups/` — those ride along in the nightly tar.

## Updating

```bash
cd buildwealth && git pull
docker compose -f infra/docker-compose.prod.yml up -d --build
```

Schema changes apply themselves at boot via the migration runner
(`schema_migrations` in the control DB records what ran). Take a backup
before updating; restore it if an update misbehaves.

## Maintenance jobs

The deletion-purge worker runs as a compose profile, suitable for cron:

```bash
docker compose -f infra/docker-compose.prod.yml --profile maintenance run --rm account-data-deletion-purge
```

## What a public launch adds (not needed for a private instance)

In rough order, per docs/ROADMAP_PRODUCTION_LLM_UI_2026-07-05.md:

1. **Hosted identity provider** — `AUTH_MODE=hosted` with Auth0 (decision:
   docs/HOSTED_IDENTITY_PROVIDER_DECISION_2026-05-14.md). Disables password
   login; the IdP owns MFA, resets, passkeys. Requires creating the Auth0
   tenant and filling the `AUTH_OIDC_*` values.
2. **Abuse hardening** — rate limiting on auth endpoints, session revocation
   list, audit-logging permission denials.
3. **Operations** — uptime monitoring, error reporting, tested restores.
4. **Legal surface** — the drafted privacy/terms/AI-disclosure pages served
   and accurate; account closure and data-deletion flows exercised for real.
5. **Storage** — Postgres via the control-DB seam if and when concurrent
   load demands it; a worker process for sync/embeddings if the event loop
   shows contention.

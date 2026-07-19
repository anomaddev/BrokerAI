# BrokerAI + self-hosted Supabase

Vendored from the official [Supabase Docker](https://github.com/supabase/supabase/tree/master/docker) layout.

## Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 4 GB | 8 GB+ |
| CPU | 2 cores | 4 cores+ |
| Disk | 40 GB SSD | 80 GB+ |
| Runtime | Docker Engine + Compose | |

BrokerAI keeps **FastAPI** as the product API. Postgres is the system of record; Auth/Storage/Studio come from this stack. Trading tables are **not** exposed via PostgREST to the browser.

## Quick start (dev)

From the repo root:

```bash
./scripts/setup-supabase.sh --start
# or via the full dev bootstrap:
./scripts/dev.sh
```

`scripts/setup-supabase.sh` copies `.env.example` → `.env`, generates JWT/API keys, sets localhost URLs, and appends `BROKERAI_*` Postgres/Supabase vars to the repo `.env` when missing.

## Endpoints (localhost)

| Service | URL |
|---------|-----|
| Kong API | http://127.0.0.1:8000 |
| Studio | http://127.0.0.1:3000 |
| Postgres | `127.0.0.1:5432` (user `postgres`, password from `.env`) |

[`docker-compose.brokerai.yml`](docker-compose.brokerai.yml) publishes these ports on **loopback only** (`127.0.0.1:…`), so they are not reachable from other hosts.

Print secrets: `cd deploy/supabase && sh run.sh secrets`

## Compose override

[`docker-compose.brokerai.yml`](docker-compose.brokerai.yml) binds Kong/Studio/Postgres/pooler to `127.0.0.1` and puts Analytics / Vector / Edge Functions behind the `full` profile so typical LXC installs stay lighter.

## Production (Proxmox LXC)

Proxmox installs (`ct/brokerai.sh` → `install/brokerai-install.sh`) and standalone (`scripts/install-lxc.sh`) already:

1. Install Docker Engine (nesting + keyctl enabled on unprivileged LXC).
2. Start this stack via `scripts/lib/install-supabase.sh`.
3. Write `BROKERAI_DATABASE_URL` / Supabase keys into `/etc/brokerai/config.env`.
4. Run `ensure_indexes()` so the `brokerai` schema exists.
5. Enable daily Postgres dumps (`brokerai-postgres-backup.timer`).
6. Optionally install **host Caddy** for BrokerAI HTTPS when `BROKERAI_DOMAIN` is set.
7. Optionally expose Kong + Studio on a **second hostname** via the same host Caddy when `BROKERAI_SUPABASE_DOMAIN` is set (Studio behind basic auth from `DASHBOARD_*`). Do **not** enable [`docker-compose.caddy.yml`](docker-compose.caddy.yml) alongside host Caddy — both bind `:80`/`:443`.

### Public Supabase (optional)

Kong/Studio remain published on **loopback** in [`docker-compose.brokerai.yml`](docker-compose.brokerai.yml). Host Caddy is the public edge.

| Variable | Example | Effect |
|----------|---------|--------|
| `BROKERAI_DOMAIN` | `broker.example.com` | Caddy → uvicorn `:1989` |
| `BROKERAI_SUPABASE_DOMAIN` | `supabase.example.com` | Caddy → Kong `:8000` + Studio `:3000` (basic auth) |
| `BROKERAI_SUPABASE_URL` | `https://supabase.example.com` | Set automatically when Supabase domain is configured |

DNS: point **both** hostnames at the LXC (or NAT 80/443). Postgres `:5432` stays private.

Install-time:

```bash
BROKERAI_DOMAIN=broker.example.com \
BROKERAI_SUPABASE_DOMAIN=supabase.example.com \
  bash ct/brokerai.sh
```

**After install (UI):** Settings → System → **Public domains (HTTPS)** — enter hostnames and click **Apply HTTPS domains**. That runs `scripts/apply-domain-tls.sh` (sudoers) to write config, install/reload Caddy, update Supabase public URLs, and restart `brokerai-web`.

**After install (CLI):** set both vars in `/etc/brokerai/config.env`, then:

```bash
source /opt/brokerai/scripts/lib/install-common.sh
export BROKERAI_DOMAIN BROKERAI_SUPABASE_DOMAIN
_brokerai_maybe_install_caddy_tls /opt/brokerai /etc/brokerai/config.env
systemctl restart brokerai-web
```

That rewrites `deploy/supabase/.env` (`SUPABASE_PUBLIC_URL`, `API_EXTERNAL_URL`, `SITE_URL`, …) and recreates the Auth container.

**Security:** exposing Kong makes publishable keys more sensitive; never put `service_role` in the browser. Prefer a strong `DASHBOARD_PASSWORD`. Do not publish Postgres.

**Smoke (after DNS + TLS):**

1. `https://<BROKERAI_DOMAIN>` — login
2. `https://<BROKERAI_SUPABASE_DOMAIN>/auth/v1/health` — Kong
3. `https://<BROKERAI_SUPABASE_DOMAIN>` — Studio (basic auth)
4. From a remote browser: research unread Realtime / signed report URLs

Local Caddyfile generation check (no root): `bash scripts/lib/verify-domain-caddy.sh`

### Postgres backups

| Item | Path / unit |
|------|-------------|
| Dump script | `/opt/brokerai/scripts/backup-postgres.sh` |
| Timer | `brokerai-postgres-backup.timer` (daily ~03:15) |
| Output | `/var/lib/brokerai/backups/postgres/brokerai-postgres-*.sql.gz` |
| Retention | `BROKERAI_BACKUP_RETENTION_DAYS` (default `7`) |

Manual backup:

```bash
/opt/brokerai/scripts/backup-postgres.sh
```

Restore example (stops app writers first; destructive):

```bash
gunzip -c /var/lib/brokerai/backups/postgres/brokerai-postgres-YYYYMMDDTHHMMSSZ.sql.gz \
  | docker exec -i supabase-db psql -U postgres -d postgres
```

### TLS note

Public HTTPS is terminated by **host Caddy** (BrokerAI and optional Supabase hostnames), not by the Supabase compose Caddy overlay. Compose still binds Kong/Studio to `127.0.0.1`; only Caddy should be reachable on 80/443.

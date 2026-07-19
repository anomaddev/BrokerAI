# BrokerAI

> ## ⚠️ Disclaimer — Not for live trading
>
> **BrokerAI is experimental software and is still in active development.** It is incomplete, untested for production use, and may contain bugs that cause incorrect orders, missed exits, data loss, or other failures.
>
> **Do not connect BrokerAI to live brokerage accounts or trade with real money.** Use practice/demo accounts only, and assume you may lose any funds you expose to this software.
>
> By using BrokerAI, you accept all risk. The authors and contributors provide no warranty and are not liable for trading losses, account damage, or any other financial harm.

Multi-bot trading platform for Proxmox LXC. BrokerAI runs a **Secretary-coordinated trading loop** for forex: strategy-driven candle analysis, OANDA order execution, a Postgres trade ledger (self-hosted Supabase), daily research reports, and a full React dashboard — all managed via the `brokerai` CLI.

**Alpha 0.0.8** — Strategy analysis workspace, recency badges, multi-select filters, rich OHLC charts with market closure markers and legends, forex market calendar, `at_time` indicator, EMA crossover refinements, and Secretary pipeline updates. See [`docs/releases/v0.0.8.md`](docs/releases/v0.0.8.md). Prior major release: [`v0.0.7.md`](docs/releases/v0.0.7.md).

## Overview

| Component | Description |
|-----------|-------------|
| **Orchestrator** | Process lifecycle, heartbeat, and control IPC |
| **Secretary** | Candle timeline, pipeline dispatch, timed research, activity log |
| **Broker** | Execution gates, exit monitors, associate dispatch, OANDA sync |
| **Web UI** | React dashboard + REST API on port **1989** (auth required) |
| **CLI** | `brokerai` — status, bot control, research, candle cache, updates |
| **Supabase** | Self-hosted Postgres + Auth + Studio (market data, strategies, ledger) |
| **Auto-update** | Systemd timer checks GitHub every 6 hours |

### Bot taxonomy

**Persistent bots** (Secretary mode — default):

| Bot | Role |
|-----|------|
| `secretary` | Schedules candle pipelines, dispatches workers, timed research |
| `broker` | Execution gates, exit monitors, associate dispatch, broker sync |
| `researcher` | Daily/weekly reports on demand via Secretary worker |

**Ephemeral workers** (spin up per job):

| Worker | Role |
|--------|------|
| Data Manager | Fetch/cache candles per `(pair, timeframe)` |
| Data Analyst | Run strategy analysis per candle close |
| Associate | Place orders per asset class (forex/OANDA implemented) |
| Researcher | Generate daily/weekly reports |

See [`docs/architecture/the-loop.md`](docs/architecture/the-loop.md) for full design notes.

## Architecture

```
Proxmox Host
  └── ct/brokerai.sh  →  LXC Container (Debian 13, nesting+keyctl, 40GB+)
                            ├── brokerai-orchestrator.service  (After docker.service)
                            ├── brokerai-web.service  (:1989; 127.0.0.1 when Caddy TLS)
                            ├── Caddy (optional HTTPS: BROKERAI_DOMAIN + optional BROKERAI_SUPABASE_DOMAIN)
                            ├── Docker: Supabase on 127.0.0.1 (Postgres :5432, Kong :8000, Studio :3000)
                            ├── brokerai-postgres-backup.timer
                            ├── brokerai-update.timer
                            └── /usr/local/bin/brokerai
```

**Data flow (Secretary mode):**

```
Secretary ──► Data Manager worker ──► Postgres market_candles
         ──► Data Analyst worker ──► strategy_analysis_runs
         ──► Broker ──► Associate workers ──► broker_lots
Researcher worker (on demand) ──► research_cache
```

At each due candle close (e.g. M15):

1. Secretary creates a `CandleJob` and dispatches parallel pipelines (capped by `BROKERAI_PIPELINE_CONCURRENCY`)
2. Data Manager worker upserts closed bars into `market_candles`
3. Data Analyst worker evaluates enabled strategies
4. Broker applies execution gates, resolves priority conflicts, dispatches Associates
5. Broker exit monitors evaluate open lots for crossover / trail stops

Broker also syncs OANDA state on startup and on a slow tick (~30s). The web API runs a separate background sync loop (default 5 min).

**Runtime paths (container):**

| Path | Purpose |
|------|---------|
| `/opt/brokerai` | Application code + Python venv |
| `/etc/brokerai/config.env` | Configuration |
| `/var/lib/brokerai/data/` | Heartbeat, control IPC, auth, research reports |
| `/var/log/brokerai/` | Update and application logs |
| `deploy/supabase/` | Self-hosted Supabase Docker stack + Postgres volumes |

## Web UI

Open **http://\<container-ip\>:1989**, or **https://\<BROKERAI_DOMAIN\>** when TLS was configured at install (dev: `http://localhost:5173`). When `BROKERAI_SUPABASE_DOMAIN` is set, Kong/Studio are at **https://\<BROKERAI_SUPABASE_DOMAIN\>** (Studio uses basic auth).

| Page | Path | Description |
|------|------|-------------|
| **Dashboard** | `/` | OANDA account summary, exchange connection status |
| **Reports** | `/research/reports` | Daily/weekly research reports, signals panel, run/rerun |
| **Strategies** | `/research/strategies` | List, enable/disable, create from preset, edit |
| **Analysis** | `/research/analysis` | Analyzer run history with recency, filters, direction, confidence, gate results, and candle context |
| **Backtesting** | `/research/backtest` | Placeholder — coming next |
| **Explore** | `/trading/explore` | Candle chart, pair search, timeframe/history, live revision stream |
| **Forex** | `/trading/forex` | Trade ledger with filters, sync, reconciliation badges, detail chart |
| **Activity** | `/activity` | Bot event timeline with job-ID correlation |
| **Cost Ledger** | `/cost-ledger` | Cost / fee ledger |
| **Settings** | `/settings/*` | Account, models, connections, research, broker, system, backup |

Older paths such as `/daily-reports`, `/trading/strategies`, and `/trading/trades` redirect to the canonical routes above.

**App chrome:** market sessions bar (forex + optional asset-class indicators), bot status pills, background task progress for sync/research jobs, collapsible sidebar.

### Settings

| Section | What you configure |
|---------|-------------------|
| **General** | Profile photo, display preferences |
| **Account** | Username/password (builtin), display name |
| **Display** | Timezone, time format |
| **Models** | LLM providers (Open WebUI functional; OpenAI/Claude/Grok UI stubs) |
| **Connections** | OANDA exchange, NewsAPI, Massive (Polygon) market status |
| **Research** | Contributor/synthesis models, daily/weekly scheduling, data sources |
| **Broker** | Per-asset-class enable, forex pairs, session windows |
| **System** | Bot status, Postgres stats, updates, reboot/shutdown |
| **Backup** | Config / data backup helpers |

## Trading

### Strategy presets

| Preset | Description |
|--------|-------------|
| **EMA Crossover** | Fast/slow EMA cross with ADX + ATR filters, ATR-based stops, RR take-profit |
| **Custom** | Blank template for manual parameter configuration |

Params use **schema v1** with sections: `timeframe`, `indicators`, `signal`, `filters`, `exits`, `risk`, `execution`. See [`docs/strategies/params-schema.md`](docs/strategies/params-schema.md).

Default EMA Crossover: M15 timeframe, ADX ≥ 25, London + NY sessions, 1% risk per trade, max 3 trades/day per strategy/pair.

**Indicators:** EMA, SMA, RSI, ADX, ATR.

### Execution

Before placing an order, Broker checks signal direction, confidence threshold, asset-class and strategy session windows, daily trade limits, and priority when multiple strategies signal the same pair.

**Exit monitors** on each relevant candle close: reverse crossover, trail stop (EMA slow), trail stop (ATR). Manual and broker-side closes are also recorded.

**Forex associate (OANDA):** validates gates, sizes units from risk % and stop distance, places market orders with optional stop-loss/take-profit, records lots in the ledger. Without OANDA credentials, intents are logged only (paper mode).

> Live order execution is **forex-only via OANDA**. Stocks, crypto, futures, options, and metals remain scaffolded.

### Trade ledger

Open and closed trades are stored in Postgres (`broker_lots`) with strategy linkage, direction, pair, units, entry/exit prices, reason codes, and P&L.

**OANDA sync** reconciles the ledger against live broker state: import missing trades, update open lots, close drifted positions, backfill exit details. Runs automatically on the Broker slow tick and via **Trading → Forex → Sync OANDA** (background task).

**Reconciliation** compares ledger open lots vs OANDA snapshot (`matched`, `ledger_only`, `broker_only` badges in the UI).

## Research

- **Daily reports** — multi-model contributor analysis + synthesis via NewsAPI and configured LLM (Open WebUI)
- **Weekly brief / debrief** — scheduled via Secretary with separate model selection
- **Signals panel** — broker-enabled asset classes from the latest daily report
- **Background tasks** — run, rerun, and delete reports from the UI with progress in the footer

Configure in **Settings → Research** and **Settings → Models**. Requires NewsAPI in **Settings → Connections** and at least one enabled forex pair.

## Self-hosted Supabase (Postgres)

BrokerAI uses the Docker stack under [`deploy/supabase/`](deploy/supabase/) (see [`deploy/supabase/BROKERAI.md`](deploy/supabase/BROKERAI.md)). FastAPI talks to Postgres directly; trading tables are not exposed via PostgREST.

```bash
./scripts/setup-supabase.sh --start
# Schema is created on API/orchestrator startup (SQLAlchemy create_all)
# Studio: http://127.0.0.1:3000  —  Postgres: 127.0.0.1:5432
```

| Table (schema `brokerai`) | Purpose |
|---------------------------|---------|
| `market_candles` | Cached OHLCV bars (`UNIQUE` symbol/timeframe/source/ts) |
| `candle_sync_state` | Per-pair/timeframe fetch scheduling state |
| `candle_watch` | Candle close watch registry (e.g. Explore page) |
| `strategies` | Saved strategy definitions (params v1, instruments, enabled) |
| `strategy_analysis_runs` | Per-candle analyzer output and gate results |
| `broker_lots` | Open/closed trade ledger |
| `broker_events` | Normalized broker transaction events |
| `instrument_exposure` | Materialized per-instrument long/short rollups |
| `broker_sync_state` | Per-exchange/account sync cursor |
| `oanda_account_summaries` | OANDA account summary snapshots from sync |
| `bot_activity` | Pipeline and bot event log |
| `research_cache` | Daily research summaries |
| `ai_models` | Connected LLM configs |
| `data_connections` | NewsAPI, Massive, per-model capabilities |
| `exchange_connections` | OANDA credentials |
| `research_settings` | Research scheduling and model selection |
| `asset_settings` | Per-asset-class broker config (forex pairs, sessions) |
| `user_profiles` / `onboarding` | Auth profile prefs + wizard progress |

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKERAI_DATABASE_URL` | `postgresql+asyncpg://…@127.0.0.1:5432/postgres` | Async Postgres URL |
| `BROKERAI_SUPABASE_URL` | `http://127.0.0.1:8000` | Kong / Auth API |
| `BROKERAI_SUPABASE_ANON_KEY` | _(generated)_ | Publishable key |
| `BROKERAI_SUPABASE_SERVICE_ROLE_KEY` | _(generated)_ | Server-only Admin API key |
| `BROKERAI_SUPABASE_JWT_SECRET` | _(generated)_ | JWT verification secret |

## Authentication

| Mode | Env | Notes |
|------|-----|-------|
| `builtin` (default) | `BROKERAI_AUTH_MODE=builtin` | Username/password; signed `brokerai_session` cookie |
| `oidc` | `BROKERAI_AUTH_MODE=oidc` + issuer/client | External IdP (Authentik, Keycloak, …); same session cookie after PKCE |

Profiles live in Postgres `brokerai.user_profiles` (file fallback under `data/auth/`). When Supabase keys are set, builtin setup/login can also create a GoTrue user and enable **TOTP MFA**. See [`docs/auth/self-hosted-oidc.md`](docs/auth/self-hosted-oidc.md).

## First-run setup

On first visit the Web UI runs a guided onboarding wizard:

1. **Welcome / Admin** — create the admin account (also used for SSH on LXC)
2. **Profile photo** — optional avatar
3. **MFA** — optional TOTP when Supabase Auth is configured
4. **Exchange** — connect an available broker module (OANDA / forex today; others Coming soon)
5. **Instruments** — enable pairs/symbols for that exchange
6. **Data sources** — optional market data / news APIs
7. **Models** — optional AI providers for research
8. **Finish** — open the dashboard

**Local design / QA:** reset first-run state and walk the wizard with:

```bash
./scripts/dev-onboarding.sh
./scripts/dev-onboarding.sh --step exchange
```

See [`docs/dev/onboarding-preview.md`](docs/dev/onboarding-preview.md).

**Proxmox install:** When running [`ct/brokerai.sh`](ct/brokerai.sh), after you pick **Default Install** (or Advanced / App Defaults), an optional host dialog can pre-create the admin account. Prefer skipping it so the web wizard handles the full first-run path.

Pre-set admin credentials without prompts (still complete remaining wizard steps in the UI):

```bash
BROKERAI_ADMIN_USER=admin BROKERAI_ADMIN_PASSWORD='YourStr0ng!Pass' \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

**Standalone install:** Same env vars work with [`scripts/install-lxc.sh`](scripts/install-lxc.sh).

1. Open **http://\<container-ip\>:1989** (or **https://\<domain\>** if `BROKERAI_DOMAIN` was set)
2. Complete the onboarding wizard (or sign in if admin was pre-configured, then finish remaining steps).
3. SSH with the same username and password: `ssh youruser@<container-ip>`

## Installation

### Option 1: Proxmox (creates LXC + installs)

Run on the **Proxmox host**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

Creates an unprivileged Debian LXC with Docker nesting, installs self-hosted Supabase (Postgres), optional Caddy TLS when you set a hostname, and enables daily Postgres backups.

Optional env before running:

```bash
BROKERAI_ADMIN_USER=admin BROKERAI_ADMIN_PASSWORD='YourStr0ng!Pass' \
BROKERAI_DOMAIN=broker.example.com \
BROKERAI_SUPABASE_DOMAIN=supabase.example.com \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

Point DNS A/AAAA for both hostnames at the LXC and open TCP 80/443 for Let’s Encrypt. See [`deploy/supabase/BROKERAI.md`](deploy/supabase/BROKERAI.md).

### Option 2: Standalone (existing container or VM)

Run **inside** Debian/Ubuntu as root:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/scripts/install-lxc.sh)"
```

Installs Docker + self-hosted Supabase, Node.js (frontend build), Python venv, systemd units, backup timer, and optional Caddy when `BROKERAI_DOMAIN` is set (`BROKERAI_SUPABASE_DOMAIN` for public Kong/Studio).

## CLI

```bash
brokerai help
brokerai status [--json]
brokerai bots list [--json]
brokerai bots start|stop <name> [--json]
brokerai run orchestrator
brokerai research status [--json]
brokerai research run-daily [--force]
brokerai research run-weekly-brief
brokerai research run-weekly-debrief
brokerai research list [--limit N]
brokerai research show <date-or-file>
brokerai research test-news
brokerai research test-model
brokerai candles sync|backfill|verify|repair|status
brokerai update check [--json]
brokerai update apply
brokerai services status|restart         # root
brokerai version [--json]
```

Add `--json` to supported commands for machine-readable output.

## Configuration

Edit `/etc/brokerai/config.env` (or `.env` in repo root for dev). Template: [`config/config.env.example`](config/config.env.example)

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKERAI_SECRET_KEY` | _(generated on install)_ | Session signing secret |
| `BROKERAI_WEB_PORT` | `1989` | Web UI port |
| `BROKERAI_WEB_BIND` | `0.0.0.0` | Uvicorn bind (`127.0.0.1` when Caddy TLS is enabled) |
| `BROKERAI_DOMAIN` | _(empty)_ | Public hostname — Caddy TLS at install or Settings → System |
| `BROKERAI_SUPABASE_DOMAIN` | _(empty)_ | Optional second hostname — host Caddy → Kong + Studio (basic auth) |
| `BROKERAI_BACKUP_DIR` | `/var/lib/brokerai/backups/postgres` | `pg_dump` output directory |
| `BROKERAI_BACKUP_RETENTION_DAYS` | `7` | Days to keep logical dumps |
| `BROKERAI_ENABLED_BOTS` | `secretary,broker,researcher` | Active persistent bots |
| `BROKERAI_PIPELINE_CONCURRENCY` | `10` | Max parallel symbol pipelines |
| `BROKERAI_SECRETARY_TICK_INTERVAL_SECONDS` | `5` | Secretary tick interval |
| `BROKERAI_BROKER_SYNC_INTERVAL_SECONDS` | `30` | Broker OANDA sync interval |
| `BROKERAI_TRADE_SYNC_INTERVAL_SECONDS` | `300` | Web API background sync interval |
| `BROKERAI_DATABASE_URL` | `postgresql+asyncpg://…` | Postgres (Supabase; always loopback) |
| `BROKERAI_SUPABASE_URL` | `http://127.0.0.1:8000` | Kong URL (`https://…` when `BROKERAI_SUPABASE_DOMAIN` is set) |
| `BROKERAI_DATA_DIR` | `/var/lib/brokerai/data` | Runtime state |
| `BROKERAI_LOG_DIR` | `/var/log/brokerai` | Logs |
| `BROKERAI_AUTO_UPDATE` | `true` | Enable automatic updates |
| `BROKERAI_UPDATE_TRACK` | `branch` | `branch` \| `release` \| `latest-release` \| `next-major` |

## Web API

| Endpoint group | Auth | Description |
|----------------|------|-------------|
| `/api/auth/*` | Mixed | Setup, login, logout, profile, account settings |
| `/api/health` | No | Health, version, Postgres status |
| `/api/bots`, `/api/bots/{name}/start\|stop` | Yes | Sub-bot statuses and IPC control |
| `/api/pipeline/status` | Yes | Secretary pipeline state |
| `/api/trades` | Yes | Ledger list, detail, candles, sync, reconciliation, close |
| `/api/strategies` | Yes | Presets, CRUD, enable/disable |
| `/api/strategy-analysis-runs` | Yes | Analyzer run history and detail |
| `/api/market-data/candles`, `/delta`, `/stream` | Yes | Candle data and SSE revision stream |
| `/api/market-status` | Yes | Forex session and asset-class status |
| `/api/research/*` | Yes | Reports, signals, run daily/weekly |
| `/api/tasks/*` | Yes | Background task progress and cancel |
| `/api/bot/activity` | Yes | Bot event timeline |
| `/api/settings/*` | Yes | Models, connections, exchanges, research, assets, updates |
| `/api/system/db`, `/power`, `/reboot`, `/shutdown` | Yes | DB stats, host power control |
| `/api/update/*` | Yes | Check and apply updates |

## Development

Quick start (recommended):

```bash
git clone https://github.com/anomaddev/BrokerAI.git
cd BrokerAI
./scripts/dev.sh              # Bootstrap venv, .env, Supabase, npm; start all services
```

`dev.sh` options: `--setup` (bootstrap only), `--backend-only` (no Vite), `--no-supabase`, `--no-open`.

Opens **http://localhost:5173** (Vite proxies `/api` → `:1989`). Setup wizard on first run; password 8–32 chars with upper+lower+digit+special.

Manual equivalent:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp config/config.env.example .env   # append BROKERAI_DATA_DIR, LOG_DIR, SECRET_KEY per scripts/dev.sh
mkdir -p data logs

./scripts/setup-supabase.sh --start   # Postgres :5432, Kong :8000, Studio :3000

brokerai run orchestrator                                        # terminal 1
uvicorn brokerai.web.app:app --reload --port 1989               # terminal 2
cd frontend && npm install && npm run dev -- --host 127.0.0.1   # terminal 3
```

**Tests:**

```bash
./venv/bin/python -m pytest    # run as module (not plain `pytest`)
```

**Build frontend for production:**

```bash
./scripts/build-frontend.sh    # → src/brokerai/web/static/
```

### Architecture docs

Index: [`docs/README.md`](docs/README.md).

| Doc | Topic |
|-----|-------|
| [`docs/architecture/the-loop.md`](docs/architecture/the-loop.md) | Secretary pipeline design |
| [`docs/architecture/orchestrator-and-bot-loops.md`](docs/architecture/orchestrator-and-bot-loops.md) | Orchestrator and tick loops |
| [`docs/architecture/data-manager.md`](docs/architecture/data-manager.md) | Candle fetch worker + service |
| [`docs/architecture/data-analyzer.md`](docs/architecture/data-analyzer.md) | Strategy analysis worker |
| [`docs/architecture/caching.md`](docs/architecture/caching.md) | Cache behavior |
| [`docs/architecture/oanda-entity-linkages.md`](docs/architecture/oanda-entity-linkages.md) | OANDA sync, broker ledger, entity mapping |
| [`docs/strategies/params-schema.md`](docs/strategies/params-schema.md) | Strategy params v1 |
| [`docs/auth/self-hosted-oidc.md`](docs/auth/self-hosted-oidc.md) | Builtin vs OIDC auth |
| [`docs/dev/onboarding-preview.md`](docs/dev/onboarding-preview.md) | Clean-DB onboarding preview |

## Project structure

```
BrokerAI/
├── frontend/                       React + Vite dashboard
├── src/brokerai/
│   ├── auth/                       Setup, login, sessions, MFA helpers
│   ├── bots/                       Persistent bots + ephemeral workers
│   │   ├── secretary/              Pipeline dispatch, timeline
│   │   ├── broker/                 Gates, exit monitors, sync
│   │   ├── researcher/             Research host bot
│   │   ├── data_manager/           Candle fetch worker + service
│   │   ├── data_analyzer/          Strategy analysis worker
│   │   └── associate/              Per-asset-class order placement
│   ├── strategies/                 Presets, params v1, evaluators
│   ├── trading/                    Indicators, broker models, sync
│   ├── db/                         Postgres client + repositories (SQLAlchemy)
│   ├── cli/                        brokerai command
│   ├── core/                       Orchestrator + control IPC
│   └── web/                        FastAPI + static SPA
├── deploy/supabase/                Self-hosted Supabase Docker stack
├── docs/                           Architecture, auth, strategies (see docs/README.md)
├── scripts/
│   ├── dev.sh                      Local dev bootstrap
│   ├── setup-supabase.sh
│   ├── install-lxc.sh
│   ├── build-frontend.sh
│   └── lib/install-supabase.sh
├── config/
└── systemd/
```

## Future Optimizations

Planned improvements that are not implemented yet:

- **Analysis run retention (`strategy_analysis_runs`)** — Runs are deduped per `(strategy, pair, candle_time)` and updated in place on re-analysis, so growth is roughly `strategies × pairs × bars_per_day` (not one row per bot poll). For watchlists and future ML (crosses, approaching signals, filter/gate context), keep a long history rather than aggressive pruning. A sensible default when volume matters: retain all signal-bearing runs (cross, approaching, actionable direction) indefinitely; trim old `none` runs after 90–180 days; optionally archive signal runs to Parquet/JSON before prune. Revisit when the table exceeds ~5–10M rows or ~20–50 GB.

## Known limitations (Alpha)

- **Forex execution only** — other asset classes have stub associates and data paths
- **Practice account strongly recommended** — live OANDA execution uses real money
- **Backtesting not implemented** — placeholder page only
- **Research trade-analysis mode** — not implemented
- **Fixed account balance for sizing** — forex associate uses 10,000 default when OANDA balance is unavailable

## License

MIT

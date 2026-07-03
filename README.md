# BrokerAI

> ## ⚠️ Disclaimer — Not for live trading
>
> **BrokerAI is experimental software and is still in active development.** It is incomplete, untested for production use, and may contain bugs that cause incorrect orders, missed exits, data loss, or other failures.
>
> **Do not connect BrokerAI to live brokerage accounts or trade with real money.** Use practice/demo accounts only, and assume you may lose any funds you expose to this software.
>
> By using BrokerAI, you accept all risk. The authors and contributors provide no warranty and are not liable for trading losses, account damage, or any other financial harm.

Multi-bot trading platform for Proxmox LXC. BrokerAI runs a **Secretary-coordinated trading loop** for forex: strategy-driven candle analysis, OANDA order execution, a MongoDB trade ledger, daily research reports, and a full React dashboard — all managed via the `brokerai` CLI.

**Alpha 0.0.6** — Secretary pipeline, live forex execution (OANDA), trade ledger, strategy builder, Explore charts, and research reports. See [`docs/releases/v0.0.5.md`](docs/releases/v0.0.5.md) for the prior major release notes.

## Overview

| Component | Description |
|-----------|-------------|
| **Orchestrator** | Process lifecycle, heartbeat, and control IPC |
| **Secretary** | Candle timeline, pipeline dispatch, timed research, activity log |
| **Broker** | Execution gates, exit monitors, associate dispatch, OANDA sync |
| **Web UI** | React dashboard + REST API on port **1989** (auth required) |
| **CLI** | `brokerai` — status, bot control, research, candle cache, updates |
| **MongoDB** | Market data, strategies, trade ledger, research, bot activity |
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

**Legacy bots** (when `BROKERAI_USE_SECRETARY_PIPELINE=false`): `data_manager`, `data_analyzer`, `executor`, `brokers` — independent 5s tick loops.

See [`docs/architecture/the-loop.md`](docs/architecture/the-loop.md) for full design notes.

## Architecture

```
Proxmox Host
  └── ct/brokerai.sh  →  LXC Container (Debian 13)
                            ├── brokerai-orchestrator.service
                            ├── brokerai-web.service  (:1989)
                            ├── mongod  (:27017, localhost)
                            ├── brokerai-update.timer
                            └── /usr/local/bin/brokerai
```

**Data flow (Secretary mode):**

```
Secretary ──► Data Manager worker ──► MongoDB (market_data)
         ──► Data Analyst worker ──► strategy_analysis_runs
         ──► Broker ──► Associate workers ──► broker_lots
Researcher worker (on demand) ──► research_cache
```

At each due candle close (e.g. M15):

1. Secretary creates a `CandleJob` and dispatches parallel pipelines (capped by `BROKERAI_PIPELINE_CONCURRENCY`)
2. Data Manager worker upserts closed bars into `market_data`
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
| `/var/lib/mongodb` | MongoDB data files |

## Web UI

Open **http://\<container-ip\>:1989** (or `http://localhost:5173` in dev).

| Page | Path | Description |
|------|------|-------------|
| **Dashboard** | `/` | OANDA account summary, exchange connection status |
| **Reports** | `/daily-reports` | Daily/weekly research reports, signals panel, run/rerun |
| **Explore** | `/trading/explore` | Candle chart, pair search, timeframe/history, live revision stream |
| **Strategies** | `/trading/strategies` | List, enable/disable, create from preset, edit |
| **Trades** | `/trading/trades` | Trade ledger with filters, sync, reconciliation badges, detail chart |
| **Live Analysis** | `/trading/analysis` | Analyzer run history with direction, confidence, gate results |
| **Activity** | `/activity` | Bot event timeline with job-ID correlation |
| **Settings** | `/settings/*` | Models, connections, research, broker asset classes, system |
| **Backtesting** | `/research/backtesting` | Placeholder — coming next |

**App chrome:** market sessions bar (forex + optional asset-class indicators), bot status pills, background task progress for sync/research jobs, collapsible sidebar.

### Settings

| Section | What you configure |
|---------|-------------------|
| **General** | Profile photo, username/password, display name, timezone, time format |
| **Models** | LLM providers (Open WebUI functional; OpenAI/Claude/Grok UI stubs) |
| **Connections** | OANDA exchange, NewsAPI, Massive (Polygon) market status |
| **Research** | Contributor/synthesis models, daily/weekly scheduling, data sources |
| **Broker** | Per-asset-class enable, forex pairs, session windows |
| **System** | Bot status, MongoDB stats, updates, reboot/shutdown |

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

Open and closed trades are stored in MongoDB (`broker_lots` collection) with strategy linkage, direction, pair, units, entry/exit prices, reason codes, and P&L.

**OANDA sync** reconciles the ledger against live broker state: import missing trades, update open lots, close drifted positions, backfill exit details. Runs automatically on the Broker slow tick and via **Trading → Trades → Sync OANDA** (background task).

**Reconciliation** compares ledger open lots vs OANDA snapshot (`matched`, `ledger_only`, `broker_only` badges in the UI).

## Research

- **Daily reports** — multi-model contributor analysis + synthesis via NewsAPI and configured LLM (Open WebUI)
- **Weekly brief / debrief** — scheduled via Secretary with separate model selection
- **Signals panel** — broker-enabled asset classes from the latest daily report
- **Background tasks** — run, rerun, and delete reports from the UI with progress in the footer

Configure in **Settings → Research** and **Settings → Models**. Requires NewsAPI in **Settings → Connections** and at least one enabled forex pair.

## MongoDB

Local MongoDB binds to **127.0.0.1:27017** only. Browse data with [MongoDB Compass](https://www.mongodb.com/products/compass):

```bash
ssh -L 27017:127.0.0.1:27017 youruser@<container-ip>
```

Connect Compass to `mongodb://127.0.0.1:27017/brokerai`.

| Collection | Purpose |
|------------|---------|
| `market_data` | Cached OHLCV bars (timeseries; symbol, timeframe, source, time) |
| `candle_sync_state` | Per-pair/timeframe fetch scheduling state |
| `candle_watch` | Candle close watch registry (e.g. Explore page) |
| `strategies` | Saved strategy definitions (params v1, instruments, enabled) |
| `strategy_analysis_runs` | Per-candle analyzer output and gate results |
| `broker_lots` | Open/closed trade ledger |
| `broker_events` | Normalized broker transaction events |
| `broker_sync_state` | Per-exchange/account sync cursor |
| `bot_activity` | Pipeline and bot event log |
| `research_cache` | Daily research summaries |
| `ai_models` | Connected LLM configs |
| `data_connections` | NewsAPI, Massive, per-model capabilities |
| `exchange_connections` | OANDA credentials |
| `research_settings` | Research scheduling and model selection |
| `asset_settings` | Per-asset-class broker config (forex pairs, sessions) |

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKERAI_MONGODB_URI` | `mongodb://127.0.0.1:27017` | MongoDB connection |
| `BROKERAI_MONGODB_DB` | `brokerai` | Database name |

## First-run setup

**Proxmox install:** When running [`ct/brokerai.sh`](ct/brokerai.sh), after you pick **Default Install** (or Advanced / App Defaults), a **BrokerAI Setup** screen asks for an optional admin account before the container is created. If you configure it there, the Web UI opens straight to login.

Pre-set credentials without prompts:

```bash
BROKERAI_ADMIN_USER=admin BROKERAI_ADMIN_PASSWORD='YourStr0ng!Pass' \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

**Standalone install:** Same env vars work with [`scripts/install-lxc.sh`](scripts/install-lxc.sh).

1. Open **http://\<container-ip\>:1989**
2. If no admin was pre-configured, complete the setup wizard (username + strong password).
3. Otherwise, sign in with the credentials you set at install time.
4. Configure OANDA in **Settings → Connections** (practice account recommended).
5. Enable forex pairs in **Settings → Broker → Forex**.
6. Create and enable at least one strategy in **Trading → Strategies**.
7. SSH with the same username and password: `ssh youruser@<container-ip>`

## Installation

### Option 1: Proxmox (creates LXC + installs)

Run on the **Proxmox host**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

### Option 2: Standalone (existing container or VM)

Run **inside** Debian/Ubuntu as root:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/scripts/install-lxc.sh)"
```

Installs MongoDB, Node.js (frontend build), Python venv, and systemd units.

## CLI

```bash
brokerai help
brokerai status [--json]
brokerai bots list [--json]
brokerai bots start|stop <name> [--json]
brokerai run orchestrator
brokerai run data-manager [--once]     # dev: legacy data-manager tick
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
| `BROKERAI_ENABLED_BOTS` | `secretary,broker,researcher` | Active persistent bots |
| `BROKERAI_USE_SECRETARY_PIPELINE` | `true` | Secretary-coordinated pipeline |
| `BROKERAI_PIPELINE_CONCURRENCY` | `10` | Max parallel symbol pipelines |
| `BROKERAI_SECRETARY_TICK_INTERVAL_SECONDS` | `5` | Secretary tick interval |
| `BROKERAI_BROKER_SYNC_INTERVAL_SECONDS` | `30` | Broker OANDA sync interval |
| `BROKERAI_TRADE_SYNC_INTERVAL_SECONDS` | `300` | Web API background sync interval |
| `BROKERAI_MONGODB_URI` | `mongodb://127.0.0.1:27017` | MongoDB URI |
| `BROKERAI_MONGODB_DB` | `brokerai` | MongoDB database |
| `BROKERAI_DATA_DIR` | `/var/lib/brokerai/data` | Runtime state |
| `BROKERAI_LOG_DIR` | `/var/log/brokerai` | Logs |
| `BROKERAI_AUTO_UPDATE` | `true` | Enable automatic updates |
| `BROKERAI_UPDATE_TRACK` | `branch` | `branch` \| `release` \| `latest-release` \| `next-major` |

### Legacy rollback

```bash
BROKERAI_USE_SECRETARY_PIPELINE=false
BROKERAI_ENABLED_BOTS=data_manager,data_analyzer,executor,brokers,researcher
```

## Web API

| Endpoint group | Auth | Description |
|----------------|------|-------------|
| `/api/auth/*` | Mixed | Setup, login, logout, profile, account settings |
| `/api/health` | No | Health, version, MongoDB status |
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
./scripts/dev.sh              # Bootstrap venv, .env, MongoDB, npm; start all services
```

`dev.sh` options: `--setup` (bootstrap only), `--backend-only` (no Vite), `--no-mongo`, `--no-open`.

Opens **http://localhost:5173** (Vite proxies `/api` → `:1989`). Setup wizard on first run; password ≥12 chars with upper+lower+digit+special.

Manual equivalent:

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install -e .
cp config/config.env.example .env   # append BROKERAI_DATA_DIR, LOG_DIR, SECRET_KEY per scripts/dev.sh
mkdir -p data logs

docker run -d --name brokerai-mongo -p 27017:27017 mongo:7   # or local mongod

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

| Doc | Topic |
|-----|-------|
| [`docs/architecture/the-loop.md`](docs/architecture/the-loop.md) | Secretary pipeline design |
| [`docs/architecture/orchestrator-and-bot-loops.md`](docs/architecture/orchestrator-and-bot-loops.md) | Orchestrator and tick loops |
| [`docs/architecture/data-manager.md`](docs/architecture/data-manager.md) | Candle fetch and cache |
| [`docs/architecture/data-analyzer.md`](docs/architecture/data-analyzer.md) | Strategy analysis |
| [`docs/architecture/caching.md`](docs/architecture/caching.md) | Cache behavior |
| [`docs/strategies/params-schema.md`](docs/strategies/params-schema.md) | Strategy params v1 |

## Project structure

```
BrokerAI/
├── frontend/                       React + Vite dashboard
├── src/brokerai/
│   ├── auth/                       Setup, login, sessions
│   ├── bots/                       Secretary, Broker, Researcher + legacy bots
│   │   ├── secretary/              Pipeline dispatch, workers
│   │   ├── broker/                 Gates, exit monitors, sync
│   │   └── associate/              Per-asset-class order placement
│   ├── strategies/                 Presets, params v1, evaluators
│   ├── trading/                    Indicators, broker models, sync
│   ├── db/                         MongoDB client + repositories
│   ├── cli/                        brokerai command
│   ├── core/                       Orchestrator + control IPC
│   └── web/                        FastAPI + static SPA
├── docs/                           Architecture and release notes
├── scripts/
│   ├── dev.sh                      Local dev bootstrap
│   ├── install-lxc.sh
│   ├── build-frontend.sh
│   └── lib/install-mongodb.sh
├── config/
└── systemd/
```

## Known limitations (Alpha)

- **Forex execution only** — other asset classes have stub associates and data paths
- **Practice account strongly recommended** — live OANDA execution uses real money
- **Backtesting not implemented** — placeholder page only
- **Research trade-analysis mode** — not implemented
- **Fixed account balance for sizing** — forex associate uses 10,000 default when OANDA balance is unavailable
- **Account snapshots in-memory** — not yet persisted to MongoDB
- **Legacy mode** — pre-Secretary tick bots still work but Secretary mode is the supported path

## License

MIT

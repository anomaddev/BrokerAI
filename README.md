# BrokerAI

Multi-bot trading platform for Proxmox LXC. BrokerAI orchestrates sub-bots, caches analysis data in local MongoDB, exposes an auth-gated React dashboard, and is managed via the `brokerai` CLI.

**Alpha 0.0.1** — structural scaffold. See [`.prompts/BrokerAI-Memory.md`](.prompts/BrokerAI-Memory.md) for current project context.

## Overview

| Component | Description |
|-----------|-------------|
| **Orchestrator** | Manages sub-bot lifecycle, heartbeat, and control IPC |
| **Web UI** | React dashboard + REST API on port **1989** (auth required) |
| **CLI** | `brokerai` command for status, bot control, updates, and services |
| **MongoDB** | Local cache for market data, research, and analysis results |
| **Auto-update** | Systemd timer checks GitHub every 6 hours |

### Sub-bots (Alpha taxonomy)

| Bot | Role | Status |
|-----|------|--------|
| `brokers` | Routes actions to asset-class sub-brokers | stub |
| `researcher` | Daily research / news for model input | stub |
| `data_manager` | Caches forex OHLCV from OANDA into MongoDB; schedules incremental fetches on candle close | partial |
| `data_analyzer` | Analyzes cached data; parallel exit-signal monitors | stub |
| `executor` | Executes trades when requested by brokers | stub |

Sub-brokers under **Brokers**: crypto, forex, stocks, futures, options (stubs).

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

**Data flow:**

```
Researcher ──► research_cache ──┐
                                 ├──► Data Analyzer ──► analysis_results ──► Brokers ──► Executor
Data Manager ──► market_data ────┘
```

**Runtime paths (container):**

| Path | Purpose |
|------|---------|
| `/opt/brokerai` | Application code + Python venv |
| `/etc/brokerai/config.env` | Configuration |
| `/var/lib/brokerai/data/` | Heartbeat, control IPC, auth |
| `/var/log/brokerai/` | Update and application logs |
| `/var/lib/mongodb` | MongoDB data files |

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
4. SSH with the same username and password: `ssh youruser@<container-ip>`

## MongoDB

Local MongoDB binds to **127.0.0.1:27017** only. Browse data with [MongoDB Compass](https://www.mongodb.com/products/compass):

```bash
ssh -L 27017:127.0.0.1:27017 youruser@<container-ip>
```

Connect Compass to `mongodb://127.0.0.1:27017/brokerai`.

| Collection | Purpose |
|------------|---------|
| `market_data` | Cached OHLCV bars (symbol, timeframe, source, time) |
| `strategies` | Saved strategy definitions (params v1, instruments, enabled flag) |
| `research_cache` | Daily research summaries |
| `analysis_results` | Analyzer output for brokers |

### Forex candle cache (`data_manager`)

For enabled forex strategies with OANDA configured, the **data manager** bot:

1. **Bootstrap** — If MongoDB has fewer bars than the strategy’s `min_candles`, pulls history from OANDA once (closed bars only).
2. **Cache** — Upserts bars into `market_data` keyed by pair, timeframe, and open time.
3. **Schedule** — After bootstrap, waits until the next bar close for each timeframe (e.g. M15 → every 15 minutes), then fetches only the newly closed bar(s).

The orchestrator still ticks every ~5 seconds, but OANDA is **not** called on every tick—only on bootstrap or when a scheduled candle close is due. Bot status includes `next_candle_fetches` per timeframe (`brokerai bots list --json`).

Requirements: OANDA credentials in **Settings → Data Connections**, forex enabled in **Settings → Broker**, and at least one **enabled strategy** assigned to overlapping forex pairs.

Run the data manager alone in dev:

```bash
brokerai run data-manager          # loop (default 5s tick; fetches only when due)
brokerai run data-manager --once   # single tick
```

Strategy params schema: [`docs/strategies/params-schema.md`](docs/strategies/params-schema.md). Caching notes: [`docs/architecture/caching.md`](docs/architecture/caching.md).

### Strategies (Web UI)

**Trading → Strategies** supports template-based builders (EMA Crossover, Custom), parameterized sections (timeframe, signal, filters, risk, execution), and saving to MongoDB. The data manager reads enabled strategies to decide which pairs, timeframes, and bar counts to cache.

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKERAI_MONGODB_URI` | `mongodb://127.0.0.1:27017` | MongoDB connection |
| `BROKERAI_MONGODB_DB` | `brokerai` | Database name |

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
brokerai status
brokerai bots list
brokerai bots stop researcher
brokerai bots start researcher
brokerai run data-manager --once   # dev: one data_manager tick
brokerai update check
brokerai services restart   # root
brokerai version
```

Add `--json` to `status`, `bots`, and `version`.

## Configuration

Edit `/etc/brokerai/config.env` (or `.env` in repo root for dev).

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKERAI_SECRET_KEY` | _(generated on install)_ | Session signing secret |
| `BROKERAI_WEB_PORT` | `1989` | Web UI port |
| `BROKERAI_ENABLED_BOTS` | `brokers,researcher,data_manager,data_analyzer,executor` | Active bots |
| `BROKERAI_MONGODB_URI` | `mongodb://127.0.0.1:27017` | MongoDB URI |
| `BROKERAI_MONGODB_DB` | `brokerai` | MongoDB database |
| `BROKERAI_DATA_DIR` | `/var/lib/brokerai/data` | Runtime state |
| `BROKERAI_LOG_DIR` | `/var/log/brokerai` | Logs |

Template: [`config/config.env.example`](config/config.env.example)

### Migrating from pre-Alpha bot names

Update config:

```bash
BROKERAI_ENABLED_BOTS=brokers,researcher,data_manager,data_analyzer,executor
```

## Web API

| Endpoint | Auth | Description |
|----------|------|-------------|
| `/api/auth/setup/status` | No | Setup complete flag |
| `/api/auth/setup` | No | First-run account creation |
| `/api/auth/login` | No | Login |
| `/api/auth/logout` | Yes | Logout |
| `/api/auth/me` | Yes | Current user |
| `/api/health` | No | Health, version, MongoDB status |
| `/api/bots` | Yes | Sub-bot statuses |
| `/api/bots/{name}/start` | Yes | Start bot (IPC) |
| `/api/bots/{name}/stop` | Yes | Stop bot (IPC) |
| `/api/system/db` | Yes | MongoDB collection counts |
| `/api/update` | Yes | Trigger update |

## Development

```bash
git clone https://github.com/anomaddev/BrokerAI.git
cd BrokerAI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp config/config.env.example .env
mkdir -p data logs

# MongoDB (Docker)
docker run -d --name brokerai-mongo -p 27017:27017 mongo:7

# Frontend
cd frontend && npm install && npm run dev   # :5173, proxies /api → :1989

# Backend (two terminals)
brokerai run orchestrator
uvicorn brokerai.web.app:app --reload --port 1989
```

Build frontend for production:

```bash
./scripts/build-frontend.sh
```

## Project structure

```
BrokerAI/
├── frontend/                       React + Vite dashboard
├── src/brokerai/
│   ├── auth/                       Setup, login, sessions
│   ├── bots/                       Sub-bot modules (Alpha taxonomy)
│   │   └── data_manager/           OANDA forex candle cache + schedule
│   ├── strategies/                 Strategy presets, params v1, evaluators
│   ├── db/                         MongoDB client + repositories
│   ├── cli/                        brokerai command
│   ├── core/                       Orchestrator + control IPC
│   └── web/                        FastAPI + static SPA
├── scripts/
│   ├── install-lxc.sh
│   ├── build-frontend.sh
│   ├── provision-admin-user.sh
│   └── lib/install-mongodb.sh
├── config/
└── systemd/
```

## License

MIT

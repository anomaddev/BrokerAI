# BrokerAI

Multi-bot trading platform for Proxmox LXC. BrokerAI orchestrates sub-bots (Research, Execution, Analysis), exposes a web dashboard, and is managed via the `brokerai` CLI.

## Overview

| Component | Description |
|-----------|-------------|
| **Orchestrator** | Manages sub-bot lifecycle, heartbeat, and control IPC |
| **Web UI** | FastAPI dashboard + REST API on port **1989** |
| **CLI** | `brokerai` command for status, bot control, updates, and services |
| **Auto-update** | Systemd timer checks GitHub every 6 hours |

### Sub-bots

| Bot | Role |
|-----|------|
| `research` | Market research (stub) |
| `execution` | Trade execution (stub) |
| `analysis` | Post-trade analysis (stub) |

## Architecture

```
Proxmox Host
  └── ct/brokerai.sh  →  LXC Container (Debian 13)
                            ├── brokerai-orchestrator.service
                            ├── brokerai-web.service  (:1989)
                            ├── brokerai-update.timer
                            └── /usr/local/bin/brokerai
```

**Runtime paths (container):**

| Path | Purpose |
|------|---------|
| `/opt/brokerai` | Application code + Python venv |
| `/etc/brokerai/config.env` | Configuration |
| `/var/lib/brokerai/data/` | Heartbeat, control IPC |
| `/var/log/brokerai/` | Update and application logs |

Control flow:

```
brokerai bots start/stop  →  data/control/inbox/  →  orchestrator  →  data/control/outbox/
brokerai status           →  reads heartbeat.json
Web UI / API              →  reads heartbeat.json (bot start/stop via API are stubs)
```

## Installation

### Option 1: Proxmox (creates LXC + installs)

Run on the **Proxmox host**:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

Uses [community-scripts build.func](https://github.com/community-scripts/ProxmoxVE). Default resources: 4 CPU, 8 GB RAM, 32 GB disk.

### Option 2: Standalone (existing container or VM)

Run **inside** Debian/Ubuntu:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/scripts/install-lxc.sh)"
```

```bash
bash scripts/install-lxc.sh --branch develop
bash scripts/install-lxc.sh --repo https://github.com/you/BrokerAI
bash scripts/install-lxc.sh --skip-clone   # use files already in /opt/brokerai
```

### Post-install

1. Open **http://\<container-ip\>:1989**
2. Verify: `brokerai status`
3. Config lives at `/etc/brokerai/config.env` (created automatically on first install)

## CLI

The primary way to manage BrokerAI. Installed at `/usr/local/bin/brokerai`.

```bash
brokerai help                    # all commands
brokerai help bots               # help for a command group
brokerai status                  # orchestrator + bot status
brokerai bots list               # list sub-bot states
brokerai bots stop research      # stop a sub-bot
brokerai bots start research     # start a sub-bot
brokerai update check            # check for updates (exit 0=current, 1=available, 2=error)
brokerai update apply            # apply updates (requires root)
brokerai services status         # systemd service status
brokerai services restart        # restart orchestrator + web UI (requires root)
brokerai version                 # package + installed commit
```

Add `--json` to `status`, `bots`, and `version` for scripting.

Bot control uses **direct file IPC** — the orchestrator must be running. The web UI is not required.

**Legacy shortcuts** (still available):

```bash
brokerai-check-update            # same as brokerai update check
sudo /opt/brokerai/scripts/update-now.sh
```

## Configuration

On the container, edit `/etc/brokerai/config.env`. For local development, use `.env` in the repo root.

```bash
nano /etc/brokerai/config.env
brokerai services restart
```

| Variable | Default | Description |
|----------|---------|-------------|
| `BROKERAI_SECRET_KEY` | _(generated on install)_ | Application secret |
| `BROKERAI_WEB_PORT` | `1989` | Web UI port |
| `BROKERAI_LOG_LEVEL` | `INFO` | Log verbosity (`DEBUG`, `INFO`, `WARNING`) |
| `BROKERAI_ENABLED_BOTS` | `research,execution,analysis` | Comma-separated active bots |
| `BROKERAI_AUTO_UPDATE` | `true` | Enable automatic updates |
| `BROKERAI_REPO` | `https://github.com/anomaddev/BrokerAI` | Git repository URL |
| `BROKERAI_UPDATE_TRACK` | `branch` | `branch`, `release`, or `latest-release` |
| `BROKERAI_BRANCH` | `main` | Branch to track (when `UPDATE_TRACK=branch`) |
| `BROKERAI_RELEASE` | _(empty)_ | Tag to pin (when `UPDATE_TRACK=release`) |
| `BROKERAI_DATA_DIR` | `/var/lib/brokerai/data` | Runtime state directory |
| `BROKERAI_LOG_DIR` | `/var/log/brokerai` | Log directory |

### Update tracks (SPM-style)

| Mode | Config | Behavior |
|------|--------|----------|
| `branch` | `BROKERAI_BRANCH=main` | Latest commit on branch |
| `release` | `BROKERAI_RELEASE=0.1.0` | Pinned to tag |
| `latest-release` | _(none)_ | Newest GitHub release |

Template: [`config/config.env.example`](config/config.env.example)

## Updating

Auto-update runs **15 minutes after boot**, then every **6 hours**.

```bash
brokerai update check            # check only
sudo brokerai update apply       # apply now
tail -f /var/log/brokerai/update.log
systemctl status brokerai-update.timer
```

**Web UI:** click **Update Now** in the dashboard header.

**API:**

```bash
curl -X POST http://localhost:1989/api/update
curl http://localhost:1989/api/update/status
```

**Proxmox update mode** (re-run ct script on existing container):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

Set `BROKERAI_AUTO_UPDATE=false` to disable the timer.

## Web API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard |
| `/api/health` | GET | Health, version, update pin |
| `/api/bots` | GET | Sub-bot statuses |
| `/api/bots/{name}/start` | POST | Start sub-bot (stub) |
| `/api/bots/{name}/stop` | POST | Stop sub-bot (stub) |
| `/api/update` | POST | Trigger update |
| `/api/update/status` | GET | Installed version + update log |

Use `brokerai bots start/stop` for direct bot control until the API is wired to IPC.

## Development

```bash
git clone https://github.com/anomaddev/BrokerAI.git
cd BrokerAI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .

cp config/config.env.example .env   # or create .env manually
mkdir -p data logs
```

Run in two terminals:

```bash
# Terminal 1 — orchestrator
brokerai run orchestrator

# Terminal 2 — web UI
uvicorn brokerai.web.app:app --reload --port 1989
```

```bash
brokerai status
brokerai bots list
brokerai bots stop research
```

Local `.env` overrides container paths (`BROKERAI_DATA_DIR=data`, `BROKERAI_LOG_DIR=logs`).

**Dev update** (no systemd):

```bash
./scripts/update-now.sh
```

## Project structure

```
BrokerAI/
├── ct/brokerai.sh                  Proxmox host script
├── install/brokerai-install.sh     In-container install
├── scripts/
│   ├── install-lxc.sh              Standalone installer
│   ├── auto-update.sh              Update logic
│   ├── check-update.sh             Read-only update check
│   ├── update-now.sh               Manual update trigger
│   └── lib/update-track.sh         Branch/release track helpers
├── src/brokerai/
│   ├── bots/                       Sub-bot modules
│   ├── cli/                        brokerai command
│   ├── core/                       Orchestrator + control IPC
│   └── web/                        FastAPI app + dashboard
├── config/
│   ├── config.env.example          Config template
│   └── sudoers/brokerai-update     Web UI update permissions
└── systemd/                        Service unit files
```

## Upgrade an existing install

If your container was installed before CLI or auto-update support:

```bash
pct enter 108                        # your container ID
cd /opt/brokerai && git pull
pip install -e .
chmod +x scripts/{auto-update,update-now,check-update}.sh
cp systemd/*.service systemd/*.timer /etc/systemd/system/
cp config/sudoers/brokerai-update /etc/sudoers.d/brokerai-update
chmod 440 /etc/sudoers.d/brokerai-update
ln -sf /opt/brokerai/venv/bin/brokerai /usr/local/bin/brokerai
ln -sf /opt/brokerai/scripts/check-update.sh /usr/local/bin/brokerai-check-update
systemctl daemon-reload
systemctl enable --now brokerai-update.timer
systemctl restart brokerai-orchestrator brokerai-web
brokerai status
```

## License

MIT

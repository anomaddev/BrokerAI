# BrokerAI

Multi-bot trading platform designed to run in an LXC container on Proxmox VE. BrokerAI orchestrates sub-bots (Research, Execution, Analysis) and exposes a web UI for monitoring and control.

## Architecture

```
/opt/brokerai/          Application code + Python venv
/etc/brokerai/          Configuration (config.env)
/var/lib/brokerai/data/ Runtime state (heartbeat.json)
/var/log/brokerai/      Application logs
```

Two systemd services run inside the container:

- **brokerai-orchestrator** — manages sub-bot lifecycle and writes heartbeat state
- **brokerai-web** — FastAPI web UI and REST API on port 1989

A systemd timer (**brokerai-update.timer**) checks GitHub every 6 hours and applies updates automatically.

## Installation

### Option 1: Proxmox community-scripts format (full LXC creation)

Run on your Proxmox host to create a new Debian 13 LXC and install BrokerAI:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

This script uses [community-scripts build.func](https://github.com/community-scripts/ProxmoxVE) for container creation and fetches the install script from this repository.

Default container resources: 2 CPU, 2 GB RAM, 8 GB disk.

### Option 2: Standalone installer (existing container or VM)

Run inside an existing Debian/Ubuntu system:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/scripts/install-lxc.sh)"
```

Options:

```bash
# Install a specific branch
bash scripts/install-lxc.sh --branch develop

# Use a fork or private mirror
bash scripts/install-lxc.sh --repo https://github.com/you/BrokerAI

# Dev: install from files already copied to /opt/brokerai
bash scripts/install-lxc.sh --skip-clone
```

## Post-Install

1. Open the web UI at `http://<container-ip>:1989`
2. Edit configuration at `/etc/brokerai/config.env`
3. Restart services after config changes:

```bash
systemctl restart brokerai-orchestrator brokerai-web
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Service health and version |
| `/api/bots` | GET | Status of all sub-bots |
| `/api/bots/{name}/start` | POST | Start a sub-bot (stub) |
| `/api/bots/{name}/stop` | POST | Stop a sub-bot (stub) |
| `/api/update` | POST | Trigger manual update |
| `/api/update/status` | GET | Installed version + recent update log |

## Project Structure

```
BrokerAI/
├── ct/brokerai.sh              Proxmox host script
├── install/brokerai-install.sh In-container install (community-scripts format)
├── scripts/install-lxc.sh      Standalone installer
├── src/brokerai/
│   ├── bots/                   Sub-bot modules (research, execution, analysis)
│   ├── core/orchestrator.py    Bot lifecycle manager
│   └── web/                    FastAPI app + dashboard
├── config/config.env.example   Configuration template
└── systemd/                    Service unit files
```

## Development

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"  # or: pip install -r requirements.txt && pip install -e .

# Run orchestrator locally
python -m brokerai.orchestrator

# Run web UI locally
uvicorn brokerai.web.app:app --reload --port 1989
```

Set `BROKERAI_DATA_DIR` and `BROKERAI_LOG_DIR` in a local `.env` or export overrides if not running on a container path.

## Updating

### Automatic (default)

Auto-update is enabled by default. A timer runs **15 minutes after boot**, then every **6 hours**:

```bash
# Timer status
systemctl status brokerai-update.timer

# View update log
tail -f /var/log/brokerai/update.log

# Trigger an update check now
systemctl start brokerai-update.service

# Or use the convenience script
sudo /opt/brokerai/scripts/update-now.sh
```

**From the web UI:** click **Update Now** in the dashboard header.

**From the API:**
```bash
curl -X POST http://localhost:1989/api/update
curl http://localhost:1989/api/update/status
```

**Local development** (no systemd):
```bash
./scripts/update-now.sh   # git pull + pip install -e .
```

Configure in `/etc/brokerai/config.env`:

```env
BROKERAI_AUTO_UPDATE=true
BROKERAI_REPO=https://github.com/anomaddev/BrokerAI

# Update track (Swift Package Manager-style)
BROKERAI_UPDATE_TRACK=branch          # branch | release | latest-release
BROKERAI_BRANCH=main                  # used when track=branch
BROKERAI_RELEASE=0.1.0                # used when track=release
```

**Track modes:**

| Mode | Config | Behavior |
|------|--------|----------|
| `branch` | `BROKERAI_BRANCH=main` | Latest commit on branch (like SPM `.branch("main")`) |
| `release` | `BROKERAI_RELEASE=0.1.0` | Pinned to tag (like SPM `.exact("0.1.0")`) |
| `latest-release` | _(no extra vars)_ | Newest GitHub release (like SPM floating releases) |

After changing track settings:

```bash
systemctl restart brokerai-orchestrator brokerai-web
/opt/brokerai/scripts/update-now.sh
```

Set `BROKERAI_AUTO_UPDATE=false` to disable automatic updates.

### Manual

Re-run the ct script on an existing container (update mode):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

Or inside the container:

```bash
/opt/brokerai/scripts/auto-update.sh --force
```

### Enable auto-update on an existing install

If your container was installed before auto-update was added:

```bash
pct enter 108   # your container ID
cd /opt/brokerai && git pull
cp systemd/brokerai-update.{service,timer} /etc/systemd/system/
chmod +x scripts/auto-update.sh scripts/update-now.sh
cp config/sudoers/brokerai-update /etc/sudoers.d/brokerai-update
chmod 440 /etc/sudoers.d/brokerai-update
systemctl daemon-reload
systemctl enable --now brokerai-update.timer
```

## License

MIT

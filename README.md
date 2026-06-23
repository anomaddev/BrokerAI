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
- **brokerai-web** — FastAPI web UI and REST API on port 8080

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

1. Open the web UI at `http://<container-ip>:8080`
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
uvicorn brokerai.web.app:app --reload --port 8080
```

Set `BROKERAI_DATA_DIR` and `BROKERAI_LOG_DIR` in a local `.env` or export overrides if not running on a container path.

## Updating

Re-run the ct script on an existing container (update mode):

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/anomaddev/BrokerAI/main/ct/brokerai.sh)"
```

Or manually inside the container:

```bash
cd /opt/brokerai && git pull
venv/bin/pip install -r requirements.txt && venv/bin/pip install -e .
systemctl restart brokerai-orchestrator brokerai-web
```

## License

MIT

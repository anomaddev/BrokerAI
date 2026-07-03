# BrokerAI

Multi-bot trading platform: FastAPI backend + MongoDB cache + React/Vite dashboard, managed via the `brokerai` CLI. See `README.md` for the product overview and `scripts/dev.sh` for the canonical local dev bootstrap.

## Cursor Cloud specific instructions

Dependencies (Python venv at `./venv`, `frontend/node_modules`) and system packages (MongoDB 8.0, `python3-venv`) are provisioned by the update script / VM snapshot. The notes below are the non-obvious caveats for starting and testing services.

### Services

| Service | Run command | Notes |
|---------|-------------|-------|
| MongoDB | `mongod --dbpath ~/mongo-data --logpath ~/mongo-log/mongod.log --bind_ip 127.0.0.1 --port 27017` | Must be running first. `systemctl`/Docker are NOT available here, so run `mongod` directly (the README/`scripts/dev.sh` Docker path does not apply). Create `~/mongo-data` and `~/mongo-log` once if missing. |
| Backend API | `set -a && . ./.env && set +a && ./venv/bin/uvicorn brokerai.web.app:app --reload --reload-exclude '.env' --host 127.0.0.1 --port 1989` | Core product (auth-gated dashboard + REST API). Requires `.env` (see below) and MongoDB. |
| Frontend (Vite) | `cd frontend && npm run dev -- --host 127.0.0.1` | Serves UI on `:5173`, proxies `/api` → `127.0.0.1:1989`. Open `http://localhost:5173`. |

### `.env` is required

The backend reads `.env` from the repo root (gitignored). If absent, create it the way `scripts/dev.sh` does: copy `config/config.env.example` to `.env`, then append `BROKERAI_DATA_DIR=data`, `BROKERAI_LOG_DIR=logs`, `BROKERAI_AUTO_UPDATE=false`, and `BROKERAI_SECRET_KEY=$(openssl rand -hex 16)`. Create `data/` and `logs/` dirs.

### First-run / hello-world

Fresh install shows a Setup wizard at `http://localhost:5173`. Create an admin (password rules: ≥12 chars, upper+lower+digit+special, e.g. `BrokerAI!2026`); it auto-logs-in. Auth state lives in `BROKERAI_DATA_DIR` (`data/`), strategies/market data in MongoDB.

### Tests

Run pytest **as a module** so the repo root is importable (tests do `from tests.fixtures...` and there is no root `conftest.py`/`__init__.py`): `./venv/bin/python -m pytest`. Plain `pytest` fails collection with `ModuleNotFoundError: No module named 'tests'`.

### Test suite state (NOT an environment problem)

The full suite (`./venv/bin/python -m pytest`) collects 181 tests: 180 pass and 1 fails. The single failure — `tests/test_data_analyzer_startup.py::test_first_tick_analyzes_when_no_prior_revision` — is a **test-isolation flake**: it passes when run alone or with only its own file (`... -m pytest tests/test_data_analyzer_startup.py`), and only fails when the whole suite runs before it (state pollution / ordering, not the environment). Do not try to "fix the environment" for this.

(The `brokerai.trading.data.candle_cache` module referenced by older notes now exists; the `brokerai` CLI imports and runs fine.)

### Build / typecheck

`cd frontend && npm run build` (Vite) succeeds and writes to `src/brokerai/web/static/` (tracked, content-hashed filenames). `tsc --noEmit` reports pre-existing type errors and is NOT part of the build pipeline.

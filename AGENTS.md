# BrokerAI

Multi-bot trading platform: FastAPI backend + self-hosted Supabase (Postgres/Auth) + React/Vite dashboard, managed via the `brokerai` CLI. See `README.md` for the product overview and `scripts/dev.sh` for the canonical local dev bootstrap.

## Cursor Cloud specific instructions

Dependencies (Python venv at `./venv`, `frontend/node_modules`) and system packages are provisioned by the update script / VM snapshot. The notes below are the non-obvious caveats for starting and testing services.

### Services

| Service | Run command | Notes |
|---------|-------------|-------|
| Supabase | `./scripts/setup-supabase.sh --start` | Docker required. Postgres `:5432`, Kong `:8000`, Studio `:3000`. See `deploy/supabase/BROKERAI.md`. |
| Schema | Auto via `ensure_indexes()` on API/orchestrator start | Creates `brokerai` schema tables (`SQLAlchemy create_all`). |
| Backend API | `set -a && . ./.env && set +a && ./venv/bin/uvicorn brokerai.web.app:app --reload --reload-exclude '.env' --host 127.0.0.1 --port 1989` | Requires `.env` and Postgres. |
| Frontend (Vite) | `cd frontend && npm run dev -- --host 127.0.0.1` | Serves UI on `:5173`, proxies `/api` → `127.0.0.1:1989`. Open `http://localhost:5173`. |

If Docker is unavailable in the environment, run a local Postgres 16+, set `BROKERAI_DATABASE_URL=postgresql+asyncpg://…`, then start the API (schema is created on startup). Auth Admin APIs need the full Supabase stack (or leave `BROKERAI_SUPABASE_*` empty to use local password hashes).

### `.env` is required

The backend reads `.env` from the repo root (gitignored). If absent, create it the way `scripts/dev.sh` does: copy `config/config.env.example` to `.env`, then append `BROKERAI_DATA_DIR=data`, `BROKERAI_LOG_DIR=logs`, `BROKERAI_AUTO_UPDATE=false`, and `BROKERAI_SECRET_KEY=$(openssl rand -hex 16)`. Create `data/` and `logs/` dirs. `./scripts/setup-supabase.sh` appends `BROKERAI_DATABASE_URL` and Supabase keys when missing.

### First-run / hello-world

**Built-in auth (default):** Fresh install shows a Setup wizard at `http://localhost:5173`. Create an admin (password rules: 8–32 chars, upper+lower+digit+special, e.g. `BrokerAI!2026`); it auto-logs-in. When Supabase Auth is configured, setup also creates the Auth user and bridges a signed BrokerAI session cookie.

**OIDC auth (matches production):** Run `./scripts/dev.sh --oidc` (requires Docker). Starts local Authelia on `:9091` and configures `.env` for OIDC. Sign in with `dev` / `BrokerAI!2026`. See `docs/auth/self-hosted-oidc.md`.

Auth profile prefs live in Postgres `brokerai.user_profiles` (with file fallback under `BROKERAI_DATA_DIR`); market/trading data in Postgres schema `brokerai`.

### Tests

Run pytest **as a module** so the repo root is importable (tests do `from tests.fixtures...` and there is no root `conftest.py`/`__init__.py`): `./venv/bin/python -m pytest`. Plain `pytest` fails collection with `ModuleNotFoundError: No module named 'tests'`.

The full suite (`./venv/bin/python -m pytest`) collects ~230 tests; all should pass. Persistent bots are `secretary`, `broker`, and `researcher` only.

### Build / typecheck

`cd frontend && npm run build` (Vite) succeeds and writes to `src/brokerai/web/static/` (tracked, content-hashed filenames). `tsc --noEmit` reports pre-existing type errors and is NOT part of the build pipeline.

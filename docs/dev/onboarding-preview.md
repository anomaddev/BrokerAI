# Onboarding wizard — local design preview

Use this flow to iterate on first-run onboarding without a Proxmox install.

## Quick start

```bash
./scripts/dev-onboarding.sh
```

This starts against a **clean Postgres from scratch**:

1. Wipe the local Supabase DB volume (`deploy/supabase/volumes/db/data`) and storage dir
2. Start self-hosted Supabase (`./scripts/setup-supabase.sh --start`) and wait for Postgres init
3. Ensure the empty `brokerai` schema (`SQLAlchemy create_all`)
4. Wipe local `data/auth/` (file fallback)
5. Force `BROKERAI_AUTH_MODE=builtin` for the preview session
6. Start orchestrator, API, and Vite
7. Open `http://localhost:5173/setup`

Walk the path: **Welcome → Admin → Profile photo → optional MFA** (when Supabase MFA is available) **→ Exchange → Instruments → Data sources → Models → Finish**.

Supabase JWT/API keys in `deploy/supabase/.env` are **kept** (only data volumes are removed).

## Reset only

```bash
./scripts/dev-onboarding.sh --reset-only
```

Same clean-DB wipe + schema ensure + auth reset, then exits without API/Vite.

## Jump to a step (DEV preview)

```bash
./scripts/dev-onboarding.sh --step exchange
./scripts/dev-onboarding.sh --step instruments
./scripts/dev-onboarding.sh --step models
```

Non-admin steps seed `preview` / `BrokerAI!2026Preview` and auto-login in Vite DEV.

Production builds ignore `?previewStep=`.

## Notes

- Docker is required for the default path. `--no-supabase` skips the volume wipe/start — bring your own **empty** Postgres and `BROKERAI_DATABASE_URL`.
- First Postgres init after a wipe can take ~30–90s before schema ensure succeeds.
- OANDA practice credentials are required to complete the exchange step against live APIs.
- Bot auto-start after Finish is **deferred** — the finish screen documents that.
- Exchange picker is modular: only OANDA is available today; other catalog entries show as Coming soon.
- Normal local development (reuse existing DB): `./scripts/dev.sh`.
- OIDC against an external IdP is documented in [`docs/auth/self-hosted-oidc.md`](../auth/self-hosted-oidc.md); onboarding preview always uses built-in auth.

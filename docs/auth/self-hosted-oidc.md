# Self-hosted OIDC authentication

BrokerAI supports two top-level authentication modes:

| Mode | Best for |
|------|----------|
| `builtin` (default) | Local dev and single-admin installs with built-in username/password |
| `oidc` | Private servers using Authentik, Keycloak, or another OIDC provider |

Local profile and preferences live in Postgres `brokerai.user_profiles` when Postgres is enabled (default). File fallback: `data/auth/users.json`. In OIDC mode the identity provider owns login, password resets, and optional IdP 2FA; BrokerAI still stores the local profile.

### Builtin + optional Supabase MFA

When `BROKERAI_SUPABASE_URL` and related keys are set, builtin setup/login also creates/uses a Supabase GoTrue user and can enable **TOTP MFA**. That is not a third auth mode: the browser session remains BrokerAI’s signed `brokerai_session` cookie.

## Architecture

```text
Browser -> Caddy (TLS) -> BrokerAI :1989
                \
                 -> OIDC provider (Authentik, Keycloak, …)
```

After a successful OIDC login, BrokerAI issues the same signed `brokerai_session` cookie used in built-in mode. Protected API routes continue to use `require_auth`.

## Enable OIDC

Add these variables to `.env` (dev) or `/etc/brokerai/config.env` (production):

```env
BROKERAI_AUTH_MODE=oidc
BROKERAI_OIDC_ISSUER=https://auth.example.com
BROKERAI_OIDC_CLIENT_ID=brokerai
BROKERAI_OIDC_CLIENT_SECRET=your-client-secret
# Optional overrides:
# BROKERAI_OIDC_REDIRECT_URI=https://brokerai.example.com/api/auth/oidc/callback
# BROKERAI_OIDC_POST_LOGOUT_REDIRECT_URI=https://brokerai.example.com/
# BROKERAI_OIDC_ALLOWED_SUB=lock-to-one-oidc-subject
# BROKERAI_SESSION_COOKIE_SECURE=true
```

Startup validation fails in OIDC mode when issuer, client ID, or client secret are missing.

## Provider setup

1. Register an OIDC client with your IdP.
2. Set the redirect URI to:
   `https://<host>/api/auth/oidc/callback`
3. Terminate TLS with host Caddy: set `BROKERAI_DOMAIN` at install time (Proxmox/standalone), or copy [`deploy/caddy/Caddyfile.example`](../../deploy/caddy/Caddyfile.example) manually. Optional `BROKERAI_SUPABASE_DOMAIN` exposes Kong/Studio on a second hostname (see [`deploy/supabase/BROKERAI.md`](../../deploy/supabase/BROKERAI.md)).
4. Bind BrokerAI to localhost once the reverse proxy is in place (`BROKERAI_WEB_BIND=127.0.0.1` is set automatically when install enables Caddy):
   `uvicorn ... --host 127.0.0.1 --port 1989`
5. Set `BROKERAI_AUTH_MODE=oidc` and restart `brokerai-web`.

## First login / migration

### New install

1. Open the dashboard.
2. Click **Continue with SSO**.
3. Sign in at your identity provider.
4. BrokerAI creates the local profile record automatically (Postgres `user_profiles`, or file fallback).

### Existing built-in install

1. Configure OIDC on your IdP while still on `BROKERAI_AUTH_MODE=builtin`.
2. Switch to `BROKERAI_AUTH_MODE=oidc`.
3. Sign in via OIDC.
4. BrokerAI links the OIDC subject to the existing local profile, preserving settings and backups.

Optional hardening for a single-user private server:

```env
BROKERAI_OIDC_ALLOWED_SUB=<subject-from-id-token>
```

## Disabled in OIDC mode

These built-in endpoints return `409`:

- `POST /api/auth/setup`
- `POST /api/auth/login`
- `PUT /api/auth/account/username`
- `PUT /api/auth/account/password`

SSH user provisioning tied to password changes is also skipped in OIDC mode.

## API endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/auth/config` | Public auth mode discovery for the frontend |
| `GET /api/auth/oidc/login` | Start OIDC authorization (PKCE) |
| `GET /api/auth/oidc/callback` | Complete login and set session cookie |
| `POST /api/auth/oidc/logout` | Clear session and return optional provider logout URL |

## Rollback

Set `BROKERAI_AUTH_MODE=builtin` and restore the admin profile from a Postgres backup (or `data/auth/` file fallback) if needed.

## Local development

Local preview defaults to built-in auth (`./scripts/dev.sh`). Bundled Authelia / `dev.sh --oidc` was removed — use an external IdP.

To exercise OIDC against an external IdP, set the OIDC variables in `.env` and point `BROKERAI_OIDC_ISSUER` at that provider. For local HTTP IdPs you may need `BROKERAI_OIDC_TLS_VERIFY=false`.

Reset local OIDC profile: clear the relevant `user_profiles` row (or delete `data/auth/` when using the file fallback) and sign in again.

To return to built-in username/password auth, set `BROKERAI_AUTH_MODE=builtin` in `.env` and restart.

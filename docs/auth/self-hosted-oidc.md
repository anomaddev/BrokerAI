# Self-hosted OIDC authentication

BrokerAI supports two authentication modes:

| Mode | Best for |
|------|----------|
| `builtin` (default) | Local dev and single-admin installs with built-in username/password |
| `oidc` | Private servers using Authelia, Authentik, or another self-hosted OIDC provider |

In OIDC mode BrokerAI still stores **local profile and preferences** in `data/auth/users.json`. The identity provider owns login, password resets, and optional 2FA.

## Architecture

```text
Browser -> Caddy (TLS) -> BrokerAI :1989
                \
                 -> Authelia (OIDC)
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

## Authelia quick start

1. Copy `deploy/authelia/configuration.yml.example` and customize domains/secrets.
2. Register the BrokerAI redirect URI:
   `https://<host>/api/auth/oidc/callback`
3. Terminate TLS with `deploy/caddy/Caddyfile.example` (or nginx equivalent).
4. Bind BrokerAI to localhost once the reverse proxy is in place:
   `uvicorn ... --host 127.0.0.1 --port 1989`
5. Set `BROKERAI_AUTH_MODE=oidc` and restart `brokerai-web`.

## First login / migration

### New install

1. Open the dashboard.
2. Click **Continue with SSO**.
3. Sign in at Authelia.
4. BrokerAI creates the local profile record automatically.

### Existing built-in install

1. Deploy Authelia and configure OIDC while still on `BROKERAI_AUTH_MODE=builtin`.
2. Switch to `BROKERAI_AUTH_MODE=oidc`.
3. Sign in via OIDC.
4. BrokerAI links the OIDC subject to the existing `users.json` profile, preserving settings and backups.

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

Set `BROKERAI_AUTH_MODE=builtin` and restore `users.json` from a config backup if needed.

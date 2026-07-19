# Caching strategy

BrokerAI runs as a single-node deployment (orchestrator + web + self-hosted Supabase Postgres). **Redis is not used today** and is not required at current scale.

## What we use instead

| Need | Implementation |
|------|----------------|
| Cross-process task coordination | File lock on `background-task-state.lock` + JSON state |
| Market status (Massive API) | In-process TTL cache (`integrations/massive_cache.py`, 60s) |
| Research signals | Precomputed snapshot in Postgres `research_cache` on report write |
| Settings | Postgres singleton docs + `@lru_cache` on `get_settings()` |
| Sessions | Stateless signed `brokerai_session` cookies (no server-side session store). When Supabase is configured, builtin login can also create GoTrue users and enable TOTP MFA; the browser session remains the BrokerAI cookie |
| Auth profiles | Postgres `brokerai.user_profiles` when `BROKERAI_USE_POSTGRES=true` (default); file fallback under `data/auth/` |

## When to add Redis

Revisit Redis when:

1. Web and orchestrator run on **different hosts** and file-based locks/heartbeat break down
2. You need **distributed rate limiting** across multiple workers for NewsAPI/LLM/OANDA
3. You run **multiple web instances** and need shared cache for Massive market status
4. You want **pub/sub** to replace 1s task polling with SSE without coupling to the web process

## When Redis does not help

- Single-admin auth (Postgres profiles + signed cookies; file fallback)
- Research report bodies (Supabase Storage bucket `research-reports` when configured; filesystem fallback otherwise; per-user read state in Postgres)
- Low-frequency settings CRUD
- `research_cache` until read paths are wired (fix application logic first)

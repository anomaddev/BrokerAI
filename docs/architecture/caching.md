# Caching strategy

BrokerAI runs as a single-node deployment (orchestrator + web + local MongoDB). **Redis is not used today** and is not required at current scale.

## What we use instead

| Need | Implementation |
|------|----------------|
| Cross-process task coordination | File lock on `background-task-state.lock` + JSON state |
| Market status (Massive API) | In-process TTL cache (`integrations/massive_cache.py`, 60s) |
| Research signals | Precomputed snapshot in MongoDB `research_cache` on report write |
| Settings | MongoDB singleton docs + `@lru_cache` on `get_settings()` |
| Sessions | Stateless signed cookies (no server-side session store) |

## When to add Redis

Revisit Redis when:

1. Web and orchestrator run on **different hosts** and file-based locks/heartbeat break down
2. You need **distributed rate limiting** across multiple workers for NewsAPI/LLM/OANDA
3. You run **multiple web instances** and need shared cache for Massive market status
4. You want **pub/sub** to replace 1s task polling with SSE without coupling to the web process

## When Redis does not help

- Single-user auth (file + cookies)
- Research report storage (filesystem is canonical)
- Low-frequency settings CRUD
- `research_cache` until read paths are wired (fix application logic first)

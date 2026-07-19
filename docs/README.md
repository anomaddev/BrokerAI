# BrokerAI documentation

Current stack: **Secretary-coordinated trading loop**, three persistent bots (`secretary`, `broker`, `researcher`), Postgres via self-hosted Supabase (`brokerai` schema), and auth modes `builtin` (default) or external `oidc`. Optional Supabase GoTrue + TOTP MFA when Supabase keys are configured.

Product overview and install: [`README.md`](../README.md). Local Cloud/agent notes: [`AGENTS.md`](../AGENTS.md).

## Architecture

| Doc | Topic |
|-----|-------|
| [architecture/the-loop.md](architecture/the-loop.md) | Secretary pipeline, persistent vs ephemeral workers |
| [architecture/orchestrator-and-bot-loops.md](architecture/orchestrator-and-bot-loops.md) | Orchestrator lifecycle and tick loops |
| [architecture/data-manager.md](architecture/data-manager.md) | Candle fetch/cache worker + `DataManagerService` |
| [architecture/data-analyzer.md](architecture/data-analyzer.md) | Forex strategy analysis worker |
| [architecture/oanda-entity-linkages.md](architecture/oanda-entity-linkages.md) | OANDA sync, broker ledger, entity mapping |
| [architecture/caching.md](architecture/caching.md) | Single-node caching (no Redis today) |

## Auth, strategies, and local preview

| Doc | Topic |
|-----|-------|
| [auth/self-hosted-oidc.md](auth/self-hosted-oidc.md) | Builtin vs OIDC; profiles and MFA |
| [strategies/params-schema.md](strategies/params-schema.md) | StrategyParams v1 |
| [dev/onboarding-preview.md](dev/onboarding-preview.md) | Clean-DB onboarding wizard preview |

## Releases

[`releases/`](releases/) holds **point-in-time** alpha notes (older files describe pre-Postgres storage). For current bots and Postgres tables, use this index and the architecture docs above — not the release bodies as living reference.

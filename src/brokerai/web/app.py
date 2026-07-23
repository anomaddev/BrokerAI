import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from brokerai import __version__
from brokerai.config.settings import get_settings, validate_startup_settings
from brokerai.core.control import ControlClient, ControlTimeout
from brokerai.db import ping_db
from brokerai.db.client import close_db, init_pg
from brokerai.db.pg.client import session_scope
from brokerai.db.pg.models import (
    AiModelRow,
    AnalysisResultRow,
    AssetSettingsRow,
    BacktestRunRow,
    BotActivityRow,
    BrokerLotRow,
    CostLedgerRow,
    DataConnectionRow,
    ExchangeConnectionRow,
    MarketCandle,
    ResearchCacheRow,
    ResearchSettingsRow,
    StrategyAnalysisRunRow,
    StrategyRow,
)
from sqlalchemy import func, select
from brokerai.web.routes.bot_activity import router as bot_activity_router
from brokerai.web.routes.cost_ledger import router as cost_ledger_router
from brokerai.web.routes.llm_budget_settings import router as llm_budget_settings_router
from brokerai.web.routes.assets_settings import router as assets_settings_router
from brokerai.web.routes.auth import require_auth, router as auth_router
from brokerai.web.routes.backups_settings import router as backups_settings_router
from brokerai.web.routes.data_connections_settings import router as data_connections_router
from brokerai.web.routes.exchange_connections_settings import router as exchange_connections_router
from brokerai.web.routes.market_data import router as market_data_router
from brokerai.web.routes.market_status import router as market_status_router
from brokerai.web.routes.models_settings import router as models_settings_router
from brokerai.web.routes.onboarding import router as onboarding_router
from brokerai.web.routes.research import router as research_router
from brokerai.web.routes.research_settings_route import router as research_settings_router
from brokerai.web.routes.rss_feeds_settings import router as rss_feeds_router
from brokerai.web.routes.settings import router as settings_router
from brokerai.web.routes.backtest_runs import router as backtest_runs_router
from brokerai.web.routes.backtest_settings import router as backtest_settings_router
from brokerai.web.routes.ai_strategy_settings import router as ai_strategy_settings_router
from brokerai.web.routes.strategies import router as strategies_router
from brokerai.web.routes.strategy_analysis_runs import router as strategy_analysis_runs_router
from brokerai.web.routes.trades import router as trades_router
from brokerai.web.routes.system import router as system_router
from brokerai.web.routes.tasks import router as tasks_router
from brokerai.web.update_runner import (
    check_for_updates,
    installed_version_short,
    read_version_lock,
    resolve_update_status,
    trigger_update,
)

logger = logging.getLogger(__name__)


def _configure_app_logging() -> None:
    """Emit ``brokerai.*`` INFO logs to stderr alongside uvicorn access lines."""
    app_logger = logging.getLogger("brokerai")
    if app_logger.handlers:
        return
    app_logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    app_logger.addHandler(handler)
    app_logger.propagate = False


async def _trade_sync_loop() -> None:
    """Sync broker state on a fixed interval."""
    from brokerai.trading.broker.sync import run_broker_sync

    while True:
        interval = max(60, get_settings().trade_sync_interval_seconds)
        try:
            result = await run_broker_sync(
                exchange_id="oanda",
                mode="incremental",
                include_account_summary=True,
            )
            if result.configured and (
                result.lots_upserted
                or result.enriched
                or result.lots_closed
                or result.summary_synced
            ):
                logger.info(
                    "Web broker sync — lots=%s enriched=%s closed=%s summary=%s",
                    result.lots_upserted,
                    result.enriched,
                    result.lots_closed,
                    result.summary_synced,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("OANDA trade sync loop failed", exc_info=True)
        await asyncio.sleep(interval)


async def _ai_strategy_startup_drain_loop() -> None:
    """Advance create-time AI Strategy startup jobs even if the orchestrator is stale.

    Secretary also drains these on its tick; this loop covers the common case where
    the API was reloaded (uvicorn --reload) but ``brokerai run orchestrator`` was not.
    """
    while True:
        try:
            from brokerai.ai_strategy.startup import drain_queued_startup_jobs

            summary = await drain_queued_startup_jobs(limit=2)
            if summary.get("advanced"):
                logger.info(
                    "API — AI startup drain advanced=%s completed=%s failed=%s",
                    summary.get("advanced"),
                    summary.get("completed"),
                    summary.get("failed"),
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("AI Strategy startup drain loop failed", exc_info=True)
        await asyncio.sleep(15)


async def _backup_schedule_loop() -> None:
    """Create scheduled full backups when due."""
    from brokerai.config_backup.service import ConfigBackupService

    while True:
        try:
            service = ConfigBackupService()
            await service.run_scheduled_backup_if_due()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Backup schedule loop failed", exc_info=True)
        await asyncio.sleep(60)


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    _configure_app_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    validate_startup_settings()
    try:
        await init_pg()
        from brokerai.db.indexes import ensure_indexes

        await ensure_indexes()
    except Exception:
        logger.warning("Postgres unavailable — startup DB init failed", exc_info=True)
    try:
        from brokerai.auth.supabase_auth import supabase_configured
        from brokerai.auth.profile_photo import (
            get_profile_photo_backend,
            migrate_local_profile_photo_to_storage,
        )
        from brokerai.bots.researcher.report_store import (
            get_report_store,
            migrate_local_reports_to_storage,
        )

        if supabase_configured():
            await get_report_store().ensure()
            await migrate_local_reports_to_storage()
            await get_profile_photo_backend().ensure()
            await migrate_local_profile_photo_to_storage()
    except Exception:
        logger.warning("Supabase Storage ensure/migrate failed", exc_info=True)
    try:
        from brokerai.tasks.runner import reconcile_stale_active_task

        reconcile_stale_active_task()
    except Exception:
        logger.warning("Background task reconciliation failed", exc_info=True)
    trade_sync_task = asyncio.create_task(_trade_sync_loop())
    backup_schedule_task = asyncio.create_task(_backup_schedule_loop())
    ai_startup_drain_task = asyncio.create_task(_ai_strategy_startup_drain_loop())
    backtest_coordinator = None
    try:
        from brokerai.backtesting.coordinator import get_backtest_coordinator

        backtest_coordinator = get_backtest_coordinator()
        await backtest_coordinator.start()
    except Exception:
        logger.warning("Backtest coordinator failed to start", exc_info=True)
    yield
    trade_sync_task.cancel()
    backup_schedule_task.cancel()
    ai_startup_drain_task.cancel()
    if backtest_coordinator is not None:
        try:
            await backtest_coordinator.stop()
        except Exception:
            logger.warning("Backtest coordinator stop failed", exc_info=True)
    await asyncio.gather(
        trade_sync_task,
        backup_schedule_task,
        ai_startup_drain_task,
        return_exceptions=True,
    )
    from brokerai.integrations.oanda_client import close_oanda_client

    await close_oanda_client()
    await close_db()


app = FastAPI(title="BrokerAI", version=__version__, lifespan=_app_lifespan)
settings = get_settings()

STATIC_DIR = Path(__file__).parent / "static"
VERSION_FILE = Path("/opt/BrokerAI_version.txt")

app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(settings_router)
app.include_router(models_settings_router)
app.include_router(data_connections_router)
app.include_router(market_status_router)
app.include_router(market_data_router)
app.include_router(exchange_connections_router)
app.include_router(research_settings_router)
app.include_router(rss_feeds_router)
app.include_router(assets_settings_router)
app.include_router(backups_settings_router)
app.include_router(research_router)
app.include_router(strategies_router)
app.include_router(backtest_runs_router)
app.include_router(backtest_settings_router)
app.include_router(ai_strategy_settings_router)
app.include_router(strategy_analysis_runs_router)
app.include_router(trades_router)
app.include_router(system_router)
app.include_router(bot_activity_router)
app.include_router(cost_ledger_router)
app.include_router(llm_budget_settings_router)
app.include_router(tasks_router)

if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")


def _read_heartbeat() -> dict:
    heartbeat_path = settings.data_dir / "heartbeat.json"
    if heartbeat_path.exists():
        try:
            return json.loads(heartbeat_path.read_text())
        except json.JSONDecodeError:
            pass
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "running": False,
        "bots": [],
    }


def _read_version_lock() -> dict:
    return read_version_lock()


def _read_installed_version() -> str | None:
    return installed_version_short()


def _spa_index() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=503, detail="Frontend not built")
    return FileResponse(index)


@app.get("/")
async def index() -> FileResponse:
    return _spa_index()


@app.get("/login")
async def login_page() -> FileResponse:
    return _spa_index()


@app.get("/setup")
async def setup_page() -> FileResponse:
    return _spa_index()


@app.get("/settings/{path:path}")
async def settings_page(path: str) -> FileResponse:
    _ = path
    return _spa_index()


@app.get("/research")
async def research_page() -> FileResponse:
    return _spa_index()


@app.get("/research/{path:path}")
async def research_subpage(path: str) -> FileResponse:
    _ = path
    return _spa_index()


@app.get("/trading/{path:path}")
async def trading_page(path: str) -> FileResponse:
    _ = path
    return _spa_index()


@app.get("/api/health")
async def health() -> JSONResponse:
    heartbeat = _read_heartbeat()
    lock = _read_version_lock()
    postgres_ok = await ping_db()
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "installed_version": _read_installed_version(),
            "installed_pin": (
                f"{lock.get('track', '?')}:{lock.get('ref', '?')}"
                if lock.get("track")
                else None
            ),
            "configured_pin": settings.update_pin_display,
            "orchestrator_running": heartbeat.get("running", False),
            "orchestrator_started_at": heartbeat.get("started_at"),
            "postgres": {"status": "ok" if postgres_ok else "unavailable"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


_DB_TABLE_COUNTS: tuple[tuple[str, type], ...] = (
    ("market_data", MarketCandle),
    ("research_cache", ResearchCacheRow),
    ("analysis_results", AnalysisResultRow),
    ("ai_models", AiModelRow),
    ("data_connections", DataConnectionRow),
    ("exchange_connections", ExchangeConnectionRow),
    ("research_settings", ResearchSettingsRow),
    ("asset_settings", AssetSettingsRow),
    ("strategies", StrategyRow),
    ("backtest_runs", BacktestRunRow),
    ("strategy_analysis_runs", StrategyAnalysisRunRow),
    ("trades", BrokerLotRow),
    ("bot_activity", BotActivityRow),
    ("cost_ledger", CostLedgerRow),
)


@app.get("/api/system/db")
async def db_stats(_username: str = Depends(require_auth)) -> JSONResponse:
    try:
        counts: dict[str, int] = {}
        async with session_scope() as session:
            for name, model in _DB_TABLE_COUNTS:
                result = await session.execute(select(func.count()).select_from(model))
                counts[name] = int(result.scalar_one())
        db_url = (settings.database_url or "").strip()
        display_url = db_url.split("@")[-1] if "@" in db_url else db_url
        return JSONResponse(
            {
                "database": "postgres",
                "uri": display_url,
                "tables": counts,
            }
        )
    except Exception as exc:
        return JSONResponse(
            {"database": "postgres", "error": str(exc), "tables": {}},
            status_code=503,
        )


@app.get("/api/bots")
async def list_bots(_username: str = Depends(require_auth)) -> JSONResponse:
    heartbeat = _read_heartbeat()
    bots = heartbeat.get("bots", [])
    if not bots:
        bots = [
            {"name": name, "state": "unknown"}
            for name in settings.enabled_bot_names
        ]
    return JSONResponse({"bots": bots})


@app.get("/api/bots/next-candle-preview")
async def next_candle_preview(_username: str = Depends(require_auth)) -> JSONResponse:
    from brokerai.bots.secretary.candle_preview import preview_next_candle_watch

    heartbeat = _read_heartbeat()
    next_candle_fetches: dict[str, str] | None = None
    for bot in heartbeat.get("bots", []):
        if bot.get("name") == "secretary":
            raw = bot.get("next_candle_fetches")
            if isinstance(raw, dict):
                next_candle_fetches = {str(k): str(v) for k, v in raw.items()}
            break

    payload = await preview_next_candle_watch(next_candle_fetches=next_candle_fetches)
    return JSONResponse(payload)


@app.get("/api/pipeline/status")
async def pipeline_status(_username: str = Depends(require_auth)) -> JSONResponse:
    heartbeat = _read_heartbeat()
    pipeline = heartbeat.get("pipeline")
    if pipeline is not None:
        return JSONResponse(pipeline)
    return JSONResponse(
        {
            "enabled": True,
            "queued_jobs": 0,
            "active_pipelines": 0,
        }
    )


@app.get("/api/update/status")
async def update_status(_username: str = Depends(require_auth)) -> JSONResponse:
    payload = await resolve_update_status()
    return JSONResponse(payload)


@app.post("/api/update/check")
async def update_check(_username: str = Depends(require_auth)) -> JSONResponse:
    payload = await check_for_updates()
    return JSONResponse(payload)


@app.post("/api/update")
async def trigger_update_route(_username: str = Depends(require_auth)) -> JSONResponse:
    ok, message = await trigger_update()
    if not ok:
        raise HTTPException(status_code=503, detail=message)
    logger.info("Manual update triggered via API")
    return JSONResponse({"action": "update", "status": "accepted", "message": message}, status_code=202)


@app.post("/api/bots/{name}/start")
async def start_bot(name: str, _username: str = Depends(require_auth)) -> JSONResponse:
    if name not in settings.enabled_bot_names:
        raise HTTPException(status_code=404, detail=f"Bot '{name}' not found")
    client = ControlClient()
    try:
        result = await asyncio.to_thread(client.submit, "start", name)
    except ControlTimeout as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.message)
    return JSONResponse({"action": "start", "bot": name, "status": "accepted"}, status_code=202)


@app.post("/api/bots/{name}/stop")
async def stop_bot(name: str, _username: str = Depends(require_auth)) -> JSONResponse:
    if name not in settings.enabled_bot_names:
        raise HTTPException(status_code=404, detail=f"Bot '{name}' not found")
    client = ControlClient()
    try:
        result = await asyncio.to_thread(client.submit, "stop", name)
    except ControlTimeout as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result.ok:
        raise HTTPException(status_code=500, detail=result.message)
    return JSONResponse({"action": "stop", "bot": name, "status": "accepted"}, status_code=202)


@app.post("/api/bots/{name}/restart")
async def restart_bot(name: str, _username: str = Depends(require_auth)) -> JSONResponse:
    """Restart one orchestrator module without restarting the API or host."""
    bot_name = name.strip()
    if not bot_name:
        raise HTTPException(status_code=404, detail="Bot not found")
    client = ControlClient()
    try:
        # Allow any loaded module (including auto-injected secretary/broker), not
        # only names listed in enabled_bots.
        result = await asyncio.to_thread(client.submit, "restart", bot_name, timeout=15.0)
    except ControlTimeout as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not result.ok:
        status = 404 if "not found" in result.message.lower() else 500
        raise HTTPException(status_code=status, detail=result.message)
    return JSONResponse(
        {
            "action": "restart",
            "bot": bot_name,
            "status": "accepted",
            "bot_status": result.bot_status,
        },
        status_code=202,
    )

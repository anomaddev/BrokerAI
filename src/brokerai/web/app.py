import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from brokerai import __version__
from brokerai.config.settings import get_settings

logger = logging.getLogger(__name__)

app = FastAPI(title="BrokerAI", version=__version__)
settings = get_settings()

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> JSONResponse:
    heartbeat = _read_heartbeat()
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "orchestrator_running": heartbeat.get("running", False),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


@app.get("/api/bots")
async def list_bots() -> JSONResponse:
    heartbeat = _read_heartbeat()
    bots = heartbeat.get("bots", [])
    if not bots:
        bots = [
            {"name": name, "state": "unknown"}
            for name in settings.enabled_bot_names
        ]
    return JSONResponse({"bots": bots})


@app.post("/api/bots/{name}/start")
async def start_bot(name: str) -> JSONResponse:
    if name not in settings.enabled_bot_names:
        raise HTTPException(status_code=404, detail=f"Bot '{name}' not found")
    logger.info("Start requested for bot '%s' (stub — orchestrator IPC pending)", name)
    return JSONResponse({"action": "start", "bot": name, "status": "accepted"}, status_code=202)


@app.post("/api/bots/{name}/stop")
async def stop_bot(name: str) -> JSONResponse:
    if name not in settings.enabled_bot_names:
        raise HTTPException(status_code=404, detail=f"Bot '{name}' not found")
    logger.info("Stop requested for bot '%s' (stub — orchestrator IPC pending)", name)
    return JSONResponse({"action": "stop", "bot": name, "status": "accepted"}, status_code=202)

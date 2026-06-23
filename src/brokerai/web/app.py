import asyncio
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
VERSION_FILE = Path("/opt/BrokerAI_version.txt")
UPDATE_LOG = Path("/var/log/brokerai/update.log")

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


def _read_version_lock() -> dict:
    if not VERSION_FILE.exists():
        return {}
    raw = VERSION_FILE.read_text().strip()
    if not raw:
        return {}
    if "=" in raw:
        lock: dict[str, str] = {}
        for line in raw.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                lock[key.strip()] = value.strip()
        return lock
    return {"commit": raw}


def _read_installed_version() -> str | None:
    lock = _read_version_lock()
    commit = lock.get("commit")
    if commit:
        return commit[:7]
    return None


def _read_update_log_tail(lines: int = 10) -> list[str]:
    if not UPDATE_LOG.exists():
        return []
    try:
        all_lines = UPDATE_LOG.read_text().splitlines()
        return all_lines[-lines:]
    except OSError:
        return []


async def _run_update_trigger() -> tuple[bool, str]:
    commands = [
        ["sudo", "-n", "systemctl", "start", "brokerai-update.service"],
        ["sudo", "-n", "/opt/brokerai/scripts/auto-update.sh", "--force"],
    ]
    for cmd in commands:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode == 0:
                return True, "Update started"
            logger.warning("Update trigger failed (%s): %s", cmd, stderr.decode().strip())
        except FileNotFoundError:
            continue
    return False, "Update trigger unavailable"


def _update_info() -> dict:
    lock = _read_version_lock()
    return {
        "configured_pin": settings.update_pin_display,
        "update_track": settings.update_track,
        "auto_update": settings.auto_update,
        "installed_track": lock.get("track"),
        "installed_ref": lock.get("ref"),
        "installed_commit": lock.get("commit"),
    }


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> JSONResponse:
    heartbeat = _read_heartbeat()
    lock = _read_version_lock()
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


@app.get("/api/update/status")
async def update_status() -> JSONResponse:
    return JSONResponse(
        {
            "installed_version": _read_installed_version(),
            "log_tail": _read_update_log_tail(),
            **_update_info(),
        }
    )


@app.post("/api/update")
async def trigger_update() -> JSONResponse:
    ok, message = await _run_update_trigger()
    if not ok:
        raise HTTPException(status_code=503, detail=message)
    logger.info("Manual update triggered via API")
    return JSONResponse({"action": "update", "status": "accepted", "message": message}, status_code=202)


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

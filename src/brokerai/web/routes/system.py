from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from brokerai.config.settings import get_settings
from brokerai.web.routes.auth import require_auth
from brokerai.web.system_power import power_control_available, trigger_reboot, trigger_shutdown
from brokerai.web.update_runner import is_dev_install

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/power")
async def power_status(_username: str = Depends(require_auth)) -> JSONResponse:
    settings = get_settings()
    dev_mode = is_dev_install(settings)
    return JSONResponse(
        {
            "available": power_control_available(settings),
            "dev_mode": dev_mode,
        }
    )


@router.post("/reboot")
async def reboot_system(_username: str = Depends(require_auth)) -> JSONResponse:
    ok, message = await trigger_reboot()
    if not ok:
        raise HTTPException(status_code=503, detail=message)
    return JSONResponse({"action": "reboot", "status": "accepted", "message": message}, status_code=202)


@router.post("/shutdown")
async def shutdown_system(_username: str = Depends(require_auth)) -> JSONResponse:
    ok, message = await trigger_shutdown()
    if not ok:
        raise HTTPException(status_code=503, detail=message)
    return JSONResponse({"action": "shutdown", "status": "accepted", "message": message}, status_code=202)

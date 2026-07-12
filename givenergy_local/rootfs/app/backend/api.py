import asyncio
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

import battery
import commissioning
import device_store
import discovery
import faults
import plant
import schedules

logger = logging.getLogger("api")
router = APIRouter(prefix="/api")


# ---------------------------------------------------------------------------
# Devices / discovery
# ---------------------------------------------------------------------------


@router.get("/devices")
def list_devices():
    return device_store.list_devices()


@router.post("/devices/scan")
async def start_scan(subnet_prefix: str | None = None):
    discovery.scan_state.start(subnet_prefix)
    return discovery.scan_state.status()


@router.get("/devices/scan")
def scan_status():
    return discovery.scan_state.status()


class ManualConnect(BaseModel):
    host: str
    port: int = 8899


@router.post("/devices/manual")
def add_manual_device(body: ManualConnect):
    return device_store.upsert_device(host=body.host, port=body.port)


@router.delete("/devices/{device_id}")
def remove_device(device_id: str):
    if not device_store.delete_device(device_id):
        raise HTTPException(404, "device not found")
    return {"ok": True}


class RenameBody(BaseModel):
    custom_name: str | None = None
    host: str | None = None


@router.patch("/devices/{device_id}")
def rename_device(device_id: str, body: RenameBody):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    device = device_store.update_device(device_id, **fields)
    if device is None:
        raise HTTPException(404, "device not found")
    return device


@router.post("/devices/{device_id}/favourite")
def favourite_device(device_id: str):
    device = device_store.set_favourite(device_id)
    if device is None:
        raise HTTPException(404, "device not found")
    return device


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


@router.post("/connect/{device_id}")
async def connect_device(device_id: str):
    device = device_store.get_device(device_id)
    if device is None:
        raise HTTPException(404, "device not found")
    try:
        await plant.manager.connect(host=device["host"], port=device["port"], device_id=device_id)
    except Exception as e:
        raise HTTPException(502, f"could not connect: {e}") from e
    return {"ok": True}


@router.post("/connect/manual")
async def connect_manual(body: ManualConnect):
    try:
        await plant.manager.connect(host=body.host, port=body.port, device_id=None)
    except Exception as e:
        raise HTTPException(502, f"could not connect: {e}") from e
    return {"ok": True}


@router.post("/disconnect")
async def disconnect():
    await plant.manager.disconnect()
    return {"ok": True}


def _require_session() -> plant.PlantSession:
    try:
        return plant.manager.require_session()
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e


@router.get("/status")
def status():
    session = plant.manager.session
    if session is None:
        return {"connected": False}
    snap = session.snapshot()
    faults.record(f"{session.host}:{session.port}", snap["faults"])
    return snap


# ---------------------------------------------------------------------------
# Battery control
# ---------------------------------------------------------------------------


class ToggleBody(BaseModel):
    enabled: bool


class PercentBody(BaseModel):
    value: int


class PauseSlotBody(BaseModel):
    start: str | None = None
    end: str | None = None


@router.post("/battery/discharge-mode")
async def api_set_discharge_mode(body: ToggleBody):
    await battery.set_discharge_mode(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/battery/charge-enabled")
async def api_set_charge_enabled(body: ToggleBody):
    await battery.set_charge_enabled(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/battery/discharge-enabled")
async def api_set_discharge_enabled(body: ToggleBody):
    await battery.set_discharge_enabled(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/battery/reserve")
async def api_set_reserve(body: PercentBody):
    await battery.set_reserve(_require_session(), body.value)
    return {"ok": True}


@router.post("/battery/charge-limit")
async def api_set_charge_limit(body: PercentBody):
    await battery.set_charge_limit(_require_session(), body.value)
    return {"ok": True}


@router.post("/battery/discharge-limit")
async def api_set_discharge_limit(body: PercentBody):
    await battery.set_discharge_limit(_require_session(), body.value)
    return {"ok": True}


@router.post("/battery/active-power-rate")
async def api_set_active_power_rate(body: PercentBody):
    await battery.set_active_power_rate(_require_session(), body.value)
    return {"ok": True}


@router.post("/battery/export-priority")
async def api_set_export_priority(body: PercentBody):
    await battery.set_export_priority(_require_session(), body.value)
    return {"ok": True}


@router.post("/battery/eps")
async def api_set_eps(body: ToggleBody):
    await battery.set_eps(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/battery/rtc")
async def api_set_rtc(body: ToggleBody):
    await battery.set_rtc(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/battery/calibration")
async def api_set_calibration(body: PercentBody):
    await battery.calibrate_battery_soc(_require_session(), body.value)
    return {"ok": True}


@router.post("/battery/pause-slot")
async def api_set_pause_slot(body: PauseSlotBody):
    await battery.set_pause_slot(_require_session(), body.start, body.end)
    return {"ok": True}


@router.post("/battery/pause-mode")
async def api_set_pause_mode(body: PercentBody):
    await battery.set_pause_mode(_require_session(), body.value)
    return {"ok": True}


@router.post("/battery/quick/charge-now")
async def api_charge_now():
    await battery.charge_now(_require_session())
    return {"ok": True}


@router.post("/battery/quick/discharge-now")
async def api_discharge_now():
    await battery.discharge_now(_require_session())
    return {"ok": True}


@router.post("/battery/quick/pause")
async def api_pause_now():
    await battery.pause_now(_require_session())
    return {"ok": True}


@router.post("/battery/quick/resume")
async def api_resume_normal():
    await battery.resume_normal(_require_session())
    return {"ok": True}


@router.post("/inverter/restart")
async def api_restart_inverter():
    await battery.restart_inverter(_require_session())
    return {"ok": True}


@router.post("/inverter/sync-clock")
async def api_sync_clock():
    await battery.sync_clock(_require_session())
    return {"ok": True}


# ---------------------------------------------------------------------------
# Commissioning (installer tier)
# ---------------------------------------------------------------------------


@router.post("/commissioning/meter-type")
async def api_set_meter_type(body: PercentBody):
    await commissioning.set_meter_type(_require_session(), body.value)
    return {"ok": True}


@router.post("/commissioning/ct-direction-em115")
async def api_set_ct_em115(body: ToggleBody):
    await commissioning.set_ct_direction_em115(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/commissioning/ct-direction-em418")
async def api_set_ct_em418(body: ToggleBody):
    await commissioning.set_ct_direction_em418(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/commissioning/battery-type")
async def api_set_battery_type(body: PercentBody):
    await commissioning.set_battery_type(_require_session(), body.value)
    return {"ok": True}


@router.post("/commissioning/battery-capacity")
async def api_set_battery_capacity(body: PercentBody):
    await commissioning.set_battery_capacity_ah(_require_session(), body.value)
    return {"ok": True}


@router.post("/commissioning/pv-startup-voltage")
async def api_set_pv_startup_voltage(body: PercentBody):
    await commissioning.set_pv_startup_voltage(_require_session(), body.value)
    return {"ok": True}


@router.post("/commissioning/grid-export-limit")
async def api_set_grid_export_limit(body: PercentBody):
    await commissioning.set_grid_export_limit_w(_require_session(), body.value)
    return {"ok": True}


@router.post("/commissioning/grid-import-limit")
async def api_set_grid_import_limit(body: PercentBody):
    await commissioning.set_grid_import_limit_a(_require_session(), body.value)
    return {"ok": True}


@router.post("/commissioning/grid-import-limit-enabled")
async def api_set_grid_import_limit_enabled(body: ToggleBody):
    await commissioning.set_grid_import_limit_enabled(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/commissioning/pv-input-mode")
async def api_set_pv_input_mode(body: PercentBody):
    await commissioning.set_pv_input_mode(_require_session(), body.value)
    return {"ok": True}


@router.post("/commissioning/force-off-grid")
async def api_set_force_off_grid(body: ToggleBody):
    await commissioning.set_force_off_grid(_require_session(), body.enabled)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


@router.get("/schedules")
def get_schedules():
    return schedules.read_slots(_require_session())


class SlotBody(BaseModel):
    start: str | None = None
    end: str | None = None


@router.put("/schedules/charge/{idx}")
async def api_set_charge_slot(idx: int, body: SlotBody):
    await schedules.set_charge_slot(_require_session(), idx, body.start, body.end)
    return {"ok": True}


@router.put("/schedules/discharge/{idx}")
async def api_set_discharge_slot(idx: int, body: SlotBody):
    await schedules.set_discharge_slot(_require_session(), idx, body.start, body.end)
    return {"ok": True}


@router.post("/schedules/charge-enabled")
async def api_schedules_charge_enabled(body: ToggleBody):
    await schedules.set_charge_enabled(_require_session(), body.enabled)
    return {"ok": True}


@router.post("/schedules/discharge-enabled")
async def api_schedules_discharge_enabled(body: ToggleBody):
    await schedules.set_discharge_enabled(_require_session(), body.enabled)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Fault log
# ---------------------------------------------------------------------------


@router.get("/faults")
def get_faults():
    session = plant.manager.session
    if session is None:
        return []
    return faults.get_log(f"{session.host}:{session.port}")


@router.delete("/faults/{index}")
def clear_fault(index: int):
    session = plant.manager.session
    if session is None:
        raise HTTPException(409, "no active device connection")
    faults.clear_entry(f"{session.host}:{session.port}", index)
    return {"ok": True}


# ---------------------------------------------------------------------------
# WebSocket live feed
# ---------------------------------------------------------------------------


@router.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            session = plant.manager.session
            if session is None:
                await websocket.send_json({"connected": False})
            else:
                snap = session.snapshot()
                faults.record(f"{session.host}:{session.port}", snap["faults"])
                await websocket.send_json(snap)
            await asyncio.sleep(plant.LIVE_REFRESH_SECONDS)
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_live error")

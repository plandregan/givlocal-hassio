"""Wraps a single givenergy-modbus Client connection: connect/detect, a background
poll loop (live + full telemetry refresh, mirroring GivLocal's two refresh intervals),
and a snapshot dict consumed by the REST API / WebSocket.

v1 supports one active connection at a time (matching the log evidence of the real
app: "Method 3 connect" tears down the previous connection before establishing a new
one) — multi-device quick-switch is a later addition.
"""

import asyncio
import logging
import os
import time

from givenergy_modbus.client.client import Client
from givenergy_modbus.exceptions import CommunicationError, RefreshFailed, RefreshPartiallySucceeded

import device_store

logger = logging.getLogger("plant")

LIVE_REFRESH_SECONDS = float(os.environ.get("GIVLOCAL_LIVE_REFRESH_SECONDS", "30"))
FULL_REFRESH_SECONDS = float(os.environ.get("GIVLOCAL_FULL_REFRESH_SECONDS", "120"))


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


class PlantSession:
    def __init__(self, host: str, port: int, device_id: str | None):
        self.host = host
        self.port = port
        self.device_id = device_id
        self.client = Client(host=host, port=port, connect_timeout=5.0)
        self.connected_at: float | None = None
        self.last_live_refresh: float | None = None
        self.last_full_refresh: float | None = None
        self.last_error: str | None = None
        self._poll_task: asyncio.Task | None = None
        self._stopping = False

    async def connect(self) -> None:
        await self.client.connect()
        await self.client.detect(timeout=5.0, retries=2)
        await self.client.load_config(timeout=5.0, retries=2)
        self.connected_at = time.time()
        self.last_full_refresh = self.connected_at
        if self.device_id:
            device_store.mark_connected(self.device_id)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def close(self) -> None:
        self._stopping = True
        if self._poll_task:
            self._poll_task.cancel()
        await self.client.close()

    async def _poll_loop(self) -> None:
        next_full = time.time() + FULL_REFRESH_SECONDS
        while not self._stopping:
            try:
                await self.client.refresh(timeout=3.0, retries=1)
                self.last_live_refresh = time.time()
                self.last_error = None
                if time.time() >= next_full:
                    await self.client.load_config(timeout=5.0, retries=1)
                    self.last_full_refresh = time.time()
                    next_full = time.time() + FULL_REFRESH_SECONDS
            except RefreshPartiallySucceeded as e:
                self.last_live_refresh = time.time()
                self.last_error = f"partial refresh failure: {e}"
                logger.warning("poll: %s", e)
            except (RefreshFailed, CommunicationError, TimeoutError) as e:
                self.last_error = str(e)
                logger.warning("poll: refresh failed: %s", e)
                try:
                    await self.client.connect()
                except Exception:
                    logger.debug("poll: reconnect attempt failed", exc_info=True)
                    await asyncio.sleep(LIVE_REFRESH_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.last_error = str(e)
                logger.exception("poll: unexpected error")
            await asyncio.sleep(LIVE_REFRESH_SECONDS)

    def snapshot(self) -> dict:
        plant = self.client.plant
        caps = plant.capabilities
        inverter = _safe(lambda: plant.inverter)
        batteries = _safe(lambda: plant.batteries, []) or []

        battery_socs = [b.soc for b in batteries if _safe(lambda: b.soc) is not None]
        avg_soc = round(sum(battery_socs) / len(battery_socs), 1) if battery_socs else None

        fault_messages = _safe(lambda: inverter.inverter_fault_messages) if inverter else None

        return {
            "connected": self.client.connected,
            "host": self.host,
            "port": self.port,
            "last_live_refresh": self.last_live_refresh,
            "last_full_refresh": self.last_full_refresh,
            "last_error": self.last_error,
            "identity": {
                "model": _safe(lambda: caps.device_type.name) if caps else None,
                "serial": _safe(lambda: plant.inverter_serial),
                "dsp_firmware_version": _safe(lambda: inverter.dsp_firmware_version) if inverter else None,
                "arm_firmware_version": _safe(lambda: inverter.arm_firmware_version) if inverter else None,
                "system_time": _safe(lambda: str(inverter.system_time)) if inverter else None,
                "meters_detected": _safe(lambda: len(plant.meters), 0),
                "battery_max_power_w": _safe(lambda: inverter.battery_max_power) if inverter else None,
                "inverter_max_power_w": _safe(lambda: inverter.inverter_max_power) if inverter else None,
            },
            "power_flow": {
                "solar_w": _safe(lambda: inverter.p_pv()) if inverter else None,
                "grid_import_w": _safe(lambda: inverter.grid_import_power) if inverter else None,
                "grid_export_w": _safe(lambda: inverter.grid_export_power) if inverter else None,
                "battery_charge_w": _safe(lambda: inverter.battery_charge_power) if inverter else None,
                "battery_discharge_w": _safe(lambda: inverter.battery_discharge_power) if inverter else None,
            },
            "totals_today": {
                "solar_kwh": _safe(lambda: inverter.e_pv_day()) if inverter else None,
                "consumption_kwh": _safe(lambda: inverter.e_consumption_today) if inverter else None,
                "battery_charge_kwh": _safe(lambda: inverter.e_battery_charge_today) if inverter else None,
                "battery_discharge_kwh": _safe(lambda: inverter.e_battery_discharge_today) if inverter else None,
                "import_kwh": _safe(lambda: inverter.e_grid_in_day) if inverter else None,
                "export_kwh": _safe(lambda: inverter.e_grid_out_day) if inverter else None,
            },
            "battery": {
                "average_soc": avg_soc,
                "count": len(batteries),
                "packs": [
                    {"soc": _safe(lambda b=b: b.soc), "serial": _safe(lambda b=b: b.serial_number)}
                    for b in batteries
                ],
                "enable_charge": _safe(lambda: inverter.enable_charge) if inverter else None,
                "enable_discharge": _safe(lambda: inverter.enable_discharge) if inverter else None,
                "battery_soc_reserve": _safe(lambda: inverter.battery_soc_reserve) if inverter else None,
                "battery_charge_limit": _safe(lambda: inverter.battery_charge_limit) if inverter else None,
                "battery_discharge_limit": _safe(lambda: inverter.battery_discharge_limit) if inverter else None,
                "battery_pause_mode": _safe(lambda: inverter.battery_pause_mode) if inverter else None,
                "discharge_mode": _safe(lambda: inverter.battery_power_mode) if inverter else None,
                "pause_slot_start": _safe(lambda: str(inverter.battery_pause_slot_1.start)[:5]) if inverter else None,
                "pause_slot_end": _safe(lambda: str(inverter.battery_pause_slot_1.end)[:5]) if inverter else None,
                "calibration_stage": _safe(lambda: inverter.battery_calibration_stage) if inverter else None,
            },
            "settings": {
                "active_power_rate": _safe(lambda: inverter.active_power_rate) if inverter else None,
                "export_priority": _safe(lambda: inverter.export_priority) if inverter else None,
                "enable_eps": _safe(lambda: inverter.enable_eps) if inverter else None,
                "enable_rtc": _safe(lambda: inverter.enable_rtc) if inverter else None,
            },
            "telemetry": {
                "string_1_voltage": _safe(lambda: inverter.v_pv1) if inverter else None,
                "string_2_voltage": _safe(lambda: inverter.v_pv2) if inverter else None,
                "string_1_energy_today": _safe(lambda: inverter.e_pv1_day) if inverter else None,
                "string_2_energy_today": _safe(lambda: inverter.e_pv2_day) if inverter else None,
                "grid_voltage": _safe(lambda: inverter.v_ac1) if inverter else None,
                "grid_frequency": _safe(lambda: inverter.f_ac1) if inverter else None,
                "temp_inverter": _safe(lambda: inverter.t_inverter_heatsink) if inverter else None,
                "temp_battery": _safe(lambda: inverter.t_battery) if inverter else None,
                "temp_charger": _safe(lambda: inverter.t_charger) if inverter else None,
            },
            "faults": fault_messages or [],
        }


class PlantManager:
    """Owns the single currently-active PlantSession."""

    def __init__(self) -> None:
        self.session: PlantSession | None = None
        self._connect_lock = asyncio.Lock()

    async def connect(self, host: str, port: int = 8899, device_id: str | None = None) -> PlantSession:
        async with self._connect_lock:
            if self.session is not None:
                await self.session.close()
                self.session = None
            session = PlantSession(host=host, port=port, device_id=device_id)
            await session.connect()
            self.session = session
            return session

    async def disconnect(self) -> None:
        async with self._connect_lock:
            if self.session is not None:
                await self.session.close()
                self.session = None

    def require_session(self) -> PlantSession:
        if self.session is None:
            raise RuntimeError("no active device connection")
        return self.session


manager = PlantManager()

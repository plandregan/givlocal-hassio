"""Battery control: discharge mode, reserve, power limits, pause mode, and quick
actions (Charge Now / Discharge Now / Pause / Resume), mirroring the GivLocal
manual's Battery Control and Quick Actions sections.

Quick Actions are implemented from the documented primitives rather than a single
dedicated register (GivEnergy inverters don't expose one): Charge Now/Discharge Now
temporarily push the relevant power limit to 100% while enabling that direction;
Resume restores whatever limits were in effect beforehand. Pause uses the inverter's
own immediate battery_pause_mode register (HR318) — the same field the Inverter tab's
Pause Slot exposes, just written without a time window so it takes effect now.
"""

from givenergy_modbus.client import commands
from givenergy_modbus.model.battery import BatteryPauseMode

from plant import PlantSession

# Remembers the charge/discharge limits that were active before a quick action
# overrode them, so "Resume" can restore them. Keyed by host — process-lifetime only.
_pre_quick_action_limits: dict[str, dict] = {}


async def _apply(session: PlantSession, requests) -> None:
    await session.client.one_shot_command(requests)


async def set_discharge_mode(session: PlantSession, match_demand: bool) -> None:
    reqs = (
        commands.set_discharge_mode_to_match_demand()
        if match_demand
        else commands.set_discharge_mode_max_power()
    )
    await _apply(session, reqs)


async def set_charge_enabled(session: PlantSession, enabled: bool) -> None:
    await _apply(session, commands.set_enable_charge(enabled))


async def set_discharge_enabled(session: PlantSession, enabled: bool) -> None:
    await _apply(session, commands.set_enable_discharge(enabled))


async def set_reserve(session: PlantSession, percent: int) -> None:
    await _apply(session, commands.set_battery_soc_reserve(percent))


async def set_charge_limit(session: PlantSession, percent: int) -> None:
    await _apply(session, commands.set_battery_charge_limit(percent))


async def set_discharge_limit(session: PlantSession, percent: int) -> None:
    await _apply(session, commands.set_battery_discharge_limit(percent))


async def set_active_power_rate(session: PlantSession, percent: int) -> None:
    await _apply(session, commands.set_active_power_rate(percent))


async def set_export_priority(session: PlantSession, priority: int) -> None:
    from givenergy_modbus.model.battery import ExportPriority

    await _apply(session, commands.set_export_priority(ExportPriority(priority)))


async def set_eps(session: PlantSession, enabled: bool) -> None:
    await _apply(session, commands.set_enable_eps(enabled))


async def set_pause_mode(session: PlantSession, mode: int) -> None:
    """Immediate pause override (0=Not Paused, 1=Pause Charge, 2=Pause Discharge, 3=Pause Both)."""
    await _apply(session, commands.set_battery_pause_mode(BatteryPauseMode(mode)))


async def set_pause_slot(session: PlantSession, start_hhmm: str | None, end_hhmm: str | None) -> None:
    from datetime import time as dt_time

    from givenergy_modbus.model import TimeSlot

    if start_hhmm is None or end_hhmm is None:
        await _apply(session, commands.set_pause_slot(None))
        return
    sh, sm = (int(x) for x in start_hhmm.split(":"))
    eh, em = (int(x) for x in end_hhmm.split(":"))
    await _apply(session, commands.set_pause_slot(TimeSlot(dt_time(sh, sm), dt_time(eh, em))))


async def calibrate_battery_soc(session: PlantSession, stage: int) -> None:
    await _apply(session, commands.set_calibrate_battery_soc(stage))


async def restart_inverter(session: PlantSession) -> None:
    await _apply(session, commands.set_inverter_reboot())


async def sync_clock(session: PlantSession) -> None:
    from datetime import datetime

    await _apply(session, commands.set_system_date_time(datetime.now()))


async def charge_now(session: PlantSession) -> None:
    inv = session.client.plant.inverter
    _pre_quick_action_limits[session.host] = {
        "charge_limit": getattr(inv, "battery_charge_limit", None),
        "enable_charge": getattr(inv, "enable_charge", None),
    }
    await _apply(session, commands.set_enable_charge(True) + commands.set_battery_charge_limit(100))


async def discharge_now(session: PlantSession) -> None:
    inv = session.client.plant.inverter
    _pre_quick_action_limits[session.host] = {
        "discharge_limit": getattr(inv, "battery_discharge_limit", None),
        "enable_discharge": getattr(inv, "enable_discharge", None),
    }
    await _apply(session, commands.set_enable_discharge(True) + commands.set_battery_discharge_limit(100))


async def pause_now(session: PlantSession) -> None:
    await set_pause_mode(session, BatteryPauseMode.PAUSE_BOTH.value)


async def resume_normal(session: PlantSession) -> None:
    await set_pause_mode(session, BatteryPauseMode.DISABLED.value)
    prev = _pre_quick_action_limits.pop(session.host, None)
    if prev:
        reqs = []
        if prev.get("charge_limit") is not None:
            reqs += commands.set_battery_charge_limit(prev["charge_limit"])
        if prev.get("discharge_limit") is not None:
            reqs += commands.set_battery_discharge_limit(prev["discharge_limit"])
        if reqs:
            await _apply(session, reqs)

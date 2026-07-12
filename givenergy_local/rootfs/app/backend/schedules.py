"""Charge/discharge schedule slot CRUD, mirroring GivLocal's Schedules tab.

Slot count varies by inverter generation; the library's detected SlotMap for the
connected model governs how many of the 10 possible slot registers are actually
wired up, so we read/write against whatever the model exposes and let the frontend
only show slots that came back non-None.
"""

from datetime import time as dt_time

from givenergy_modbus.client import commands
from givenergy_modbus.model import TimeSlot

from plant import PlantSession

MAX_SLOTS = 10


def _slot_map(session: PlantSession):
    return session.client.plant.inverter.slot_map


def _timeslot_to_dict(slot) -> dict | None:
    if slot is None:
        return None
    start = getattr(slot, "start", None)
    end = getattr(slot, "end", None)
    if start is None or end is None:
        return None
    return {"start": start.strftime("%H:%M"), "end": end.strftime("%H:%M")}


def read_slots(session: PlantSession) -> dict:
    inverter = session.client.plant.inverter
    charge = []
    discharge = []
    for i in range(1, MAX_SLOTS + 1):
        charge.append(_timeslot_to_dict(getattr(inverter, f"charge_slot_{i}", None)))
        discharge.append(_timeslot_to_dict(getattr(inverter, f"discharge_slot_{i}", None)))
    return {
        "charge_slots": charge,
        "discharge_slots": discharge,
        "enable_charge": getattr(inverter, "enable_charge", None),
        "enable_discharge": getattr(inverter, "enable_discharge", None),
    }


def _parse_hhmm(value: str) -> dt_time:
    h, m = (int(x) for x in value.split(":"))
    return dt_time(h, m)


async def set_charge_slot(session: PlantSession, idx: int, start: str | None, end: str | None) -> None:
    if not 1 <= idx <= MAX_SLOTS:
        raise ValueError(f"slot index {idx} out of range 1-{MAX_SLOTS}")
    slot_map = _slot_map(session)
    if start is None or end is None:
        reqs = commands.reset_charge_slot(idx, slot_map)
    else:
        reqs = commands.set_charge_slot(idx, TimeSlot(_parse_hhmm(start), _parse_hhmm(end)), slot_map)
    await session.client.one_shot_command(reqs)


async def set_discharge_slot(session: PlantSession, idx: int, start: str | None, end: str | None) -> None:
    if not 1 <= idx <= MAX_SLOTS:
        raise ValueError(f"slot index {idx} out of range 1-{MAX_SLOTS}")
    slot_map = _slot_map(session)
    if start is None or end is None:
        reqs = commands.reset_discharge_slot(idx, slot_map)
    else:
        reqs = commands.set_discharge_slot(idx, TimeSlot(_parse_hhmm(start), _parse_hhmm(end)), slot_map)
    await session.client.one_shot_command(reqs)


async def set_charge_enabled(session: PlantSession, enabled: bool) -> None:
    await session.client.one_shot_command(commands.set_enable_charge(enabled))


async def set_discharge_enabled(session: PlantSession, enabled: bool) -> None:
    await session.client.one_shot_command(commands.set_enable_discharge(enabled))

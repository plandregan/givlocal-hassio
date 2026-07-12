"""Installer-tier "Commissioning" settings, matching the GivLocal manual's
Commissioning section: grid/meter configuration, battery type/capacity,
PV input mode, grid import/export limits, and force off-grid.

Register numbers cross-referenced against the GivEnergy Hybrid Modbus RTU
protocol doc (v4.4.1) supplied by the user, and verified against
givenergy-modbus's own field definitions (model/inverter.py) — same
addresses, confirming this is the same register map the TCP client already
uses. Grid Code is not implemented: it isn't present as a single register in
either the RTU doc or the library's model, and guessing at an unverified
register for a grid-compliance setting isn't worth the risk.

All writes go through Client.installer_command() rather than
one_shot_command(): HR101/102 (grid import limit) and HR305 (PV input mode)
are genuinely installer-gated by the library; the rest aren't, but grouping
everything here under the same higher-friction path matches the real app's
"Commissioning" risk tier and its confirm-before-write UX.
"""

from givenergy_modbus.model.battery import ExportPriority  # noqa: F401  (re-exported for callers)
from givenergy_modbus.model.inverter import BatteryType, MeterType
from givenergy_modbus.pdu.write_registers import WriteHoldingRegisterRequest

from plant import PlantSession

# Holding-register addresses (see module docstring for provenance).
HR_GRID_EXPORT_LIMIT_W = 26
HR_METER_TYPE = 47
HR_CT_DIRECTION_EM115 = 48
HR_CT_DIRECTION_EM418 = 49
HR_BATTERY_TYPE = 54
HR_BATTERY_CAPACITY_AH = 55
HR_PV_STARTUP_VOLTAGE = 60
HR_GRID_IMPORT_LIMIT_A = 101
HR_GRID_IMPORT_LIMIT_ENABLED = 102
HR_PV_INPUT_MODE = 305
HR_FORCE_OFF_GRID = 331


async def _installer_write(session: PlantSession, register: int, value: int, installer_tier: bool) -> None:
    req = WriteHoldingRegisterRequest(register, value, installer=installer_tier)
    await session.client.installer_command([req])


async def set_meter_type(session: PlantSession, meter_type: int) -> None:
    MeterType(meter_type)  # validates the value is a known enum member
    await _installer_write(session, HR_METER_TYPE, meter_type, installer_tier=False)


async def set_ct_direction_em115(session: PlantSession, reversed_: bool) -> None:
    await _installer_write(session, HR_CT_DIRECTION_EM115, 1 if reversed_ else 0, installer_tier=False)


async def set_ct_direction_em418(session: PlantSession, reversed_: bool) -> None:
    await _installer_write(session, HR_CT_DIRECTION_EM418, 1 if reversed_ else 0, installer_tier=False)


async def set_battery_type(session: PlantSession, battery_type: int) -> None:
    BatteryType(battery_type)
    await _installer_write(session, HR_BATTERY_TYPE, battery_type, installer_tier=False)


async def set_battery_capacity_ah(session: PlantSession, amp_hours: int) -> None:
    await _installer_write(session, HR_BATTERY_CAPACITY_AH, amp_hours, installer_tier=False)


async def set_pv_startup_voltage(session: PlantSession, volts_x10: int) -> None:
    """volts_x10 is volts * 10 (register is 0.1V units, range 0-2000 = 0-200.0V)."""
    await _installer_write(session, HR_PV_STARTUP_VOLTAGE, volts_x10, installer_tier=False)


async def set_grid_export_limit_w(session: PlantSession, watts: int) -> None:
    await _installer_write(session, HR_GRID_EXPORT_LIMIT_W, watts, installer_tier=False)


async def set_grid_import_limit_a(session: PlantSession, amps: int) -> None:
    await _installer_write(session, HR_GRID_IMPORT_LIMIT_A, amps, installer_tier=True)


async def set_grid_import_limit_enabled(session: PlantSession, enabled: bool) -> None:
    await _installer_write(session, HR_GRID_IMPORT_LIMIT_ENABLED, 1 if enabled else 0, installer_tier=True)


async def set_pv_input_mode(session: PlantSession, mode: int) -> None:
    """0 = Independent Strings, 1 = Combined (per RTU doc PVModelSelect)."""
    await _installer_write(session, HR_PV_INPUT_MODE, mode, installer_tier=True)


async def set_force_off_grid(session: PlantSession, enabled: bool) -> None:
    await _installer_write(session, HR_FORCE_OFF_GRID, 1 if enabled else 0, installer_tier=False)

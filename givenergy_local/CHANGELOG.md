# Changelog

## 0.1.3

- Changed default poll intervals: `live_refresh_seconds` 5 → 30,
  `full_refresh_seconds` 30 → 120 (still configurable in the add-on's
  Configuration tab). Existing installs keep whatever value they've already
  set; this only changes the default for fresh installs.

## 0.1.2

- Fix: manual connect form did nothing on failure (unhandled fetch rejection,
  same root cause pattern as the scan hang). Now shows connecting state and
  surfaces errors.

## 0.1.1

- Fix: LAN scan on the Devices screen hung indefinitely (sync route calling
  `asyncio.create_task` from a thread with no event loop). Scan now runs
  correctly and completes in a few seconds.

## 0.1.0

Initial release.

- LAN discovery (port 8899 scan) and manual connection
- Live dashboard: power flow, battery SOC, today's totals, fault log
- Battery control: discharge mode, reserve, charge/discharge power limits, pause mode, quick actions
- Schedules tab: charge/discharge slot management
- Inverter tab: identity, clock sync, restart, active power rate, export priority, EPS

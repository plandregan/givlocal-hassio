# Changelog

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

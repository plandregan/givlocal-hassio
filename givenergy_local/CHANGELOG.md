# Changelog

## 0.2.1

- Fix: add-on stuck in a restart crash loop ("address already in use" on
  8099, repeating every few seconds). Root cause: the custom s6 `finish`
  script used an execlineb/`s6-test` invocation that doesn't exist in this
  base image ("unable to spawn s6-test: No such file or directory"), so it
  errored out on every service exit instead of cleanly tearing the process
  down — the next restart attempt then fought the previous run for the port.
  Removed the broken `finish` script entirely; a longrun service doesn't
  need one for normal operation, s6-overlay's default exit handling covers
  it. If you're seeing this crash loop, fully **stop** the add-on (not just
  update) before starting the new version, so the orphaned process is
  cleared by the container stop rather than another failed internal restart.

## 0.2.0

Frontend redesign to closely match the real GivLocal app's layout, based on a
screen recording of the actual app:

- Dashboard rebuilt as a circular power-flow diagram (Solar/Home/Battery/Grid
  nodes with a percentage-ring battery node and animated flow indicators),
  matching the real app instead of the previous generic grid layout.
- Devices screen restyled to the real app's compact card format (name + star,
  IP/firmware/serial/last-seen rows, chevron).
- Inverter tab rebuilt as a collapsible accordion (Overview, Fault Log, Live
  Telemetry, Battery Control, Power Limits, Clock, Advanced, Service,
  Commissioning placeholder) instead of one long flat page.
- New controls: RTC Enable toggle, Battery SOC Calibration status/start,
  dedicated immediate Pause Mode control, DC Charge/Discharge Limit now shown
  in kW (computed from the detected battery's rated power) to match the real
  app, not just the raw register percentage.
- New Overview section: plant identity card, Energy Stats (Solar/Home/Import/
  Export today), Connection info block.
- New Live Telemetry section: string voltages/energy, grid voltage/frequency,
  inverter/battery/charger temperatures.

## 0.1.4

- Fix: all API/WebSocket calls failed with "404: Not Found" when accessed
  through Home Assistant Ingress ("192.168.x.x:8123 says Could not add
  device: 404"). The frontend used absolute `/api/...` paths, which under
  Ingress's per-session URL prefix escape to Home Assistant's own core API
  instead of the add-on. Now uses relative paths that resolve correctly
  against the Ingress-prefixed page URL. Confirmed working end-to-end
  against a real inverter.

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

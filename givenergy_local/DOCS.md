# GivEnergy Local

Local Modbus TCP monitoring and control for GivEnergy inverters and batteries —
no GivEnergy Cloud account needed. Talks directly to your inverter over your LAN,
the same way the vendor's own local-first mobile app does.

## Requirements

- A GivEnergy inverter reachable on your LAN with Modbus TCP enabled on port 8899
  (this is on by default on most GivEnergy hybrid/AC-coupled inverters and gateways).
- This add-on must run with host networking (already configured) so it can scan
  your actual LAN subnet, not an isolated Docker network.

## Getting started

1. Start the add-on and open it from the sidebar (Ingress).
2. On the **Devices** screen, tap **Scan LAN** to discover inverters on your subnet,
   or use **Manual Connection** if you already know the IP address.
3. Tap a discovered device to connect. You'll land on the **Dashboard** tab.

## Tabs

- **Dashboard** — live power flow (solar/battery/home/grid), battery state of charge,
  today's totals, quick actions (Charge Now / Discharge Now / Pause / Resume), and a
  fault log.
- **Schedules** — charge and discharge time slots, plus the AC-charge / discharge
  schedule master switches.
- **Inverter** — identity, battery control (discharge mode, reserve, power limits,
  pause slot), and advanced settings (active power rate, export priority, EPS).

## Options

- `live_refresh_seconds` — how often live telemetry (power flow, SOC) is polled. Default 5.
- `full_refresh_seconds` — how often the full register set (temperatures, faults, etc.)
  is re-read. Default 30.

## Notes

- v1 supports one actively-connected device at a time.
- EV charger control, Tailscale/port-forward remote access, and the
  installer/commissioning section are planned for a later release.
- This add-on is an independent, from-spec reimplementation of local GivEnergy
  monitoring/control functionality, built on the open-source
  [`givenergy-modbus`](https://github.com/dewet22/givenergy-modbus) protocol library.
  It is not affiliated with GivEnergy.

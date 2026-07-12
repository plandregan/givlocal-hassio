# GivEnergy Local — Home Assistant Add-on Repository

A Home Assistant add-on for locally monitoring and controlling GivEnergy inverters,
batteries, and (later) EV chargers over Modbus TCP on your LAN — no GivEnergy Cloud
account needed.

This is an independent, from-spec reimplementation of the functionality found in the
closed-source "GivLocal" mobile app, built on top of the open-source
[`givenergy-modbus`](https://github.com/dewet22/givenergy-modbus) protocol library
(the same one used by projects like GivTCP). It is not affiliated with GivEnergy or
Thomserve, and does not reuse any of their code, artwork, or branding.

## Installing

1. In Home Assistant: **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add: `https://github.com/plandregan/givlocal-hassio`
3. Install **GivEnergy Local** from the store, start it, then open it from the sidebar.

## What's in v1

- Device discovery (LAN scan on port 8899) and manual connection
- Live dashboard: power flow (solar/battery/home/grid), battery SOC, today's totals, fault log
- Battery control: Eco mode, reserve %, charge/discharge power limits, pause slot, quick actions
- Schedules: charge/discharge slot management
- Basic inverter tab: identity, clock sync, restart

EV charger control, Tailscale/remote access, and the installer/commissioning section are
planned for a later release.

## Status

Early / actively developed. See [CHANGELOG.md](givenergy_local/CHANGELOG.md).

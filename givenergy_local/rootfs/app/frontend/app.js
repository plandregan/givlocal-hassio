// Relative (no leading slash) so requests resolve against the current document
// URL. Required under Home Assistant Ingress, which serves this app at a
// per-session prefix (e.g. /api/hassio_ingress/<token>/) — an absolute "/api/..."
// path would escape that prefix and hit Home Assistant's own core API instead.
const API = "api";
let ws = null;
let currentDevice = null;
let userEditingInverter = false;

function $(id) { return document.getElementById(id); }

async function apiGet(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiPost(path, body) {
  const res = await fetch(API + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiPut(path, body) {
  const res = await fetch(API + path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
async function apiDelete(path) {
  const res = await fetch(API + path, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// ---------------------------------------------------------------------------
// Tabs / views
// ---------------------------------------------------------------------------

function showView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-" + name).classList.remove("hidden");
  document.querySelectorAll(".tab-btn[data-tab]").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
}

document.querySelectorAll(".tab-btn[data-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    showView(btn.dataset.tab);
    if (btn.dataset.tab === "schedules") loadSchedules();
  });
});

$("btn-devices").addEventListener("click", () => {
  $("tabs").classList.add("hidden");
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-devices").classList.remove("hidden");
  loadDevices();
});

$("btn-settings").addEventListener("click", async () => {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-settings").classList.remove("hidden");
  try {
    const cfg = await apiGet("/config");
    $("cfg-live-refresh").textContent = cfg.live_refresh_seconds + "s";
    $("cfg-full-refresh").textContent = cfg.full_refresh_seconds + "s";
  } catch (e) { /* ignore */ }
});

$("btn-disconnect").addEventListener("click", async () => {
  if (!confirm("Disconnect from the current device?")) return;
  await apiPost("/disconnect");
  currentDevice = null;
  if (ws) { ws.close(); ws = null; }
  $("tabs").classList.add("hidden");
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  $("view-devices").classList.remove("hidden");
  loadDevices();
});

// ---------------------------------------------------------------------------
// Devices / discovery
// ---------------------------------------------------------------------------

function timeAgo(ts) {
  if (!ts) return "never";
  const s = Math.floor(Date.now() / 1000 - ts);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

async function loadDevices() {
  const devices = await apiGet("/devices");
  const list = $("device-list");
  list.innerHTML = "";
  if (devices.length === 0) {
    list.innerHTML = '<p class="muted small">No devices yet — scan your network or connect manually below.</p>';
    return;
  }
  devices.forEach((d) => {
    const name = d.custom_name || d.model || "Inverter";
    const card = document.createElement("div");
    card.className = "device-card";
    card.innerHTML = `
      <div class="device-card__info">
        <div class="device-card__name">${name}${d.favourite ? ' <span class="star">&#9733;</span>' : ""}</div>
        <div class="device-card__meta">
          IP Address: ${d.host}<br>
          ${d.firmware ? `Firmware Version: ${d.firmware}<br>` : ""}
          ${d.serial ? `Serial Number: ${d.serial}<br>` : ""}
          Last Seen: ${timeAgo(d.last_seen)}
        </div>
      </div>
      <span class="device-card__chevron">&#8250;</span>
    `;
    card.addEventListener("click", () => connectDevice(d.id));
    list.appendChild(card);
  });
}

async function startScan() {
  $("scan-progress").classList.remove("hidden");
  $("scan-progress-label").textContent = "Starting scan…";
  try {
    await apiPost("/devices/scan");
    pollScan();
  } catch (e) {
    $("scan-progress-label").textContent = "Scan failed: " + e.message;
  }
}

async function pollScan() {
  const status = await apiGet("/devices/scan");
  $("scan-progress-label").textContent = `Scanning ${status.subnet_prefix}.x… ${status.total ? Math.round((status.scanned / status.total) * 100) : 0}%`;
  await loadDevices();
  if (status.running) {
    setTimeout(pollScan, 800);
  } else {
    $("scan-progress").classList.add("hidden");
  }
}

$("btn-scan").addEventListener("click", startScan);
$("btn-stop-scan").addEventListener("click", () => { $("scan-progress").classList.add("hidden"); });

$("manual-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const host = $("manual-host").value.trim();
  const port = parseInt($("manual-port").value, 10) || 8899;
  const submitBtn = $("manual-form").querySelector("button[type=submit]");
  const originalLabel = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = "Connecting…";
  try {
    const device = await apiPost("/devices/manual", { host, port });
    await connectDevice(device.id);
  } catch (e) {
    alert("Could not add device: " + e.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = originalLabel;
  }
});

async function connectDevice(deviceId) {
  const clickable = document.querySelectorAll(".device-card, #manual-form button");
  clickable.forEach((b) => { b.style.pointerEvents = "none"; b.style.opacity = "0.6"; });
  try {
    await apiPost(`/connect/${deviceId}`);
    currentDevice = deviceId;
    enterConnectedView();
  } catch (e) {
    alert("Could not connect: " + e.message);
  } finally {
    clickable.forEach((b) => { b.style.pointerEvents = ""; b.style.opacity = ""; });
  }
}

function enterConnectedView() {
  $("tabs").classList.remove("hidden");
  showView("dashboard");
  connectWebSocket();
}

// ---------------------------------------------------------------------------
// Live status via WebSocket
// ---------------------------------------------------------------------------

function connectWebSocket() {
  if (ws) ws.close();
  // Resolve relative to the current document URL (preserves the Ingress prefix),
  // then swap the scheme to ws:/wss: — same reasoning as the API constant above.
  const wsUrl = new URL(`${API}/ws/live`, location.href);
  wsUrl.protocol = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(wsUrl.href);
  ws.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    renderStatus(data);
  };
  ws.onclose = () => {
    setTimeout(() => { if (currentDevice) connectWebSocket(); }, 2000);
  };
}

function fmtW(v) { return v === null || v === undefined ? "-- W" : `${Math.round(v)} W`; }
function fmtKwh(v) { return v === null || v === undefined ? "-- kWh" : `${v.toFixed(2)} kWh`; }

function setDotVisible(id, visible) {
  const dot = $(id);
  dot.classList.toggle("hidden", !visible);
}

function renderStatus(data) {
  const dots = [$("status-dot"), $("status-dot-2")];
  const texts = [$("status-text"), $("status-text-2")];
  if (!data.connected) {
    dots.forEach((d) => { d.className = "status-dot offline"; });
    texts.forEach((t) => { t.textContent = "Not connected"; });
    return;
  }
  const age = data.last_live_refresh ? (Date.now() / 1000 - data.last_live_refresh) : null;
  // No refresh yet right after connecting isn't a fault — treat as "settling", not offline.
  const cls = age === null ? "stale" : age < 60 ? "online" : age < 300 ? "stale" : "offline";
  dots.forEach((d) => { d.className = "status-dot " + cls; });
  texts.forEach((t) => { t.textContent = `Connected — ${data.host}`; });

  const pf = data.power_flow || {};
  const battery = data.battery || {};
  const totals = data.totals_today || {};

  $("val-solar").textContent = fmtW(pf.solar_w);
  const gridW = (pf.grid_import_w || 0) - (pf.grid_export_w || 0);
  $("val-grid").textContent = fmtW(Math.abs(gridW));
  $("grid-state-label").textContent = gridW > 5 ? "Importing" : gridW < -5 ? "Exporting" : "Idle";

  const battW = (pf.battery_charge_w || 0) - (pf.battery_discharge_w || 0);
  $("val-battery-power").textContent = fmtW(Math.abs(battW));
  $("battery-state-label").textContent = battW > 5 ? "Charging" : battW < -5 ? "Discharging" : "Idle";

  const homeW = (pf.solar_w || 0) + (pf.battery_discharge_w || 0) + (pf.grid_import_w || 0)
    - (pf.battery_charge_w || 0) - (pf.grid_export_w || 0);
  $("val-home").textContent = fmtW(Math.max(0, homeW));

  const soc = battery.average_soc;
  $("val-battery-soc").textContent = soc != null ? `${soc}%` : "--%";
  $("battery-ring").style.setProperty("--soc", soc != null ? soc : 0);
  $("battery-bar-fill").style.width = soc != null ? `${soc}%` : "0%";
  $("battery-bar-text").textContent = soc != null ? `${soc}%` : "--%";

  setDotVisible("dot-solar", (pf.solar_w || 0) > 5);
  setDotVisible("dot-battery", Math.abs(battW) > 5);
  setDotVisible("dot-grid", Math.abs(gridW) > 5);

  $("tot-solar").textContent = fmtKwh(totals.solar_kwh);
  $("tot-home").textContent = fmtKwh(totals.consumption_kwh);
  $("tot-import").textContent = fmtKwh(totals.import_kwh);
  $("tot-export").textContent = fmtKwh(totals.export_kwh);
  $("ov-tot-solar").textContent = fmtKwh(totals.solar_kwh);
  $("ov-tot-home").textContent = fmtKwh(totals.consumption_kwh);
  $("ov-tot-import").textContent = fmtKwh(totals.import_kwh);
  $("ov-tot-export").textContent = fmtKwh(totals.export_kwh);

  const faultsList = data.faults || [];
  const banner = $("fault-banner");
  if (faultsList.length > 0) {
    banner.textContent = `Active fault: ${faultsList.join(", ")}`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
  renderFaultLog();
  renderInverterTab(data);
}

async function renderFaultLog() {
  try {
    const log = await apiGet("/faults");
    const html = !log.length
      ? '<p class="muted">No faults recorded.</p>'
      : log.slice().reverse().map((entry, i) => {
          const detected = new Date(entry.detected_at * 1000).toLocaleString();
          const cleared = entry.cleared_at
            ? new Date(entry.cleared_at * 1000).toLocaleString()
            : '<span class="fault-active">Active</span>';
          return `<div class="fault-entry"><span>${entry.name}<br><span class="muted">Detected: ${detected}</span></span><span>${cleared}</span></div>`;
        }).join("");
    $("fault-log").innerHTML = html;
    $("inv-fault-log").innerHTML = html;
  } catch (e) { /* no active device */ }
}

// ---------------------------------------------------------------------------
// Quick actions
// ---------------------------------------------------------------------------

$("qa-charge").addEventListener("click", () => apiPost("/battery/quick/charge-now"));
$("qa-discharge").addEventListener("click", () => apiPost("/battery/quick/discharge-now"));
$("qa-pause").addEventListener("click", () => apiPost("/battery/quick/pause"));
$("qa-resume").addEventListener("click", () => apiPost("/battery/quick/resume"));

// ---------------------------------------------------------------------------
// Schedules
// ---------------------------------------------------------------------------

function slotRow(kind, idx, slot) {
  const row = document.createElement("div");
  row.className = "slot-row";
  row.innerHTML = `
    <span class="slot-idx">${idx}</span>
    <input type="time" class="slot-start" value="${slot ? slot.start : ""}">
    <input type="time" class="slot-end" value="${slot ? slot.end : ""}">
    <button class="btn btn-secondary btn-save">Save</button>
    <button class="btn btn-secondary btn-clear">Clear</button>
  `;
  row.querySelector(".btn-save").addEventListener("click", async () => {
    const start = row.querySelector(".slot-start").value;
    const end = row.querySelector(".slot-end").value;
    if (!start || !end) { alert("Set both start and end time"); return; }
    await apiPut(`/schedules/${kind}/${idx}`, { start, end });
  });
  row.querySelector(".btn-clear").addEventListener("click", async () => {
    row.querySelector(".slot-start").value = "";
    row.querySelector(".slot-end").value = "";
    await apiPut(`/schedules/${kind}/${idx}`, { start: null, end: null });
  });
  return row;
}

async function loadSchedules() {
  const data = await apiGet("/schedules");
  const chargeEl = $("charge-slots");
  const dischargeEl = $("discharge-slots");
  chargeEl.innerHTML = "";
  dischargeEl.innerHTML = "";
  data.charge_slots.forEach((slot, i) => {
    if (slot === null && i > 1) return;
    chargeEl.appendChild(slotRow("charge", i + 1, slot));
  });
  data.discharge_slots.forEach((slot, i) => {
    if (slot === null && i > 1) return;
    dischargeEl.appendChild(slotRow("discharge", i + 1, slot));
  });
  $("charge-enabled").checked = !!data.enable_charge;
  $("discharge-enabled").checked = !!data.enable_discharge;
}

$("charge-enabled").addEventListener("change", (e) => apiPost("/schedules/charge-enabled", { enabled: e.target.checked }));
$("discharge-enabled").addEventListener("change", (e) => apiPost("/schedules/discharge-enabled", { enabled: e.target.checked }));

// ---------------------------------------------------------------------------
// Inverter tab (accordion)
// ---------------------------------------------------------------------------

document.querySelectorAll(".acc-header").forEach((header) => {
  header.addEventListener("click", () => {
    header.closest(".acc-item").classList.toggle("open");
  });
});

const CALIBRATION_LABELS = { 0: "Off", 1: "Discharging", 2: "Set Lower Limit", 3: "Charging", 4: "Set Upper Limit", 5: "Balancing", 6: "Set Full Capacity", 7: "Finishing" };
const PAUSE_MODE_VALUES = [0, 1, 2, 3];

function renderInverterTab(data) {
  if (userEditingInverter) return;
  const id = data.identity || {};
  const battery = data.battery || {};
  const settings = data.settings || {};
  const telemetry = data.telemetry || {};

  $("ov-model").textContent = id.model || "--";
  $("ov-serial").textContent = id.serial || "--";
  $("ov-connection").innerHTML = `
    <div class="kv-row"><span>Product</span><span>${id.model || "--"}</span></div>
    <div class="kv-row"><span>Host</span><span>${data.host || "--"}</span></div>
    <div class="kv-row"><span>Inverter Serial</span><span>${id.serial || "--"}</span></div>
    <div class="kv-row"><span>Firmware Version</span><span>D${id.dsp_firmware_version ?? "--"}-A${id.arm_firmware_version ?? "--"}</span></div>
    <div class="kv-row"><span>Detected Meters</span><span>${id.meters_detected ?? "--"}</span></div>
    <div class="kv-row"><span>Status</span><span>${data.connected ? "Connected" : "Disconnected"}</span></div>
  `;

  $("telemetry-list").innerHTML = `
    <div class="kv-row"><span>String 1 Voltage</span><span>${telemetry.string_1_voltage ?? "--"} V</span></div>
    <div class="kv-row"><span>String 2 Voltage</span><span>${telemetry.string_2_voltage ?? "--"} V</span></div>
    <div class="kv-row"><span>String 1 Energy Today</span><span>${(telemetry.string_1_energy_today ?? 0).toFixed ? telemetry.string_1_energy_today.toFixed(2) : "--"} kWh</span></div>
    <div class="kv-row"><span>String 2 Energy Today</span><span>${(telemetry.string_2_energy_today ?? 0).toFixed ? telemetry.string_2_energy_today.toFixed(2) : "--"} kWh</span></div>
    <div class="kv-row"><span>Grid Voltage</span><span>${telemetry.grid_voltage ?? "--"} V</span></div>
    <div class="kv-row"><span>Grid Frequency</span><span>${telemetry.grid_frequency ?? "--"} Hz</span></div>
    <div class="kv-row"><span>Inverter Temp</span><span>${telemetry.temp_inverter ?? "--"} &#8451;</span></div>
    <div class="kv-row"><span>Battery Temp</span><span>${telemetry.temp_battery ?? "--"} &#8451;</span></div>
    <div class="kv-row"><span>Charger Temp</span><span>${telemetry.temp_charger ?? "--"} &#8451;</span></div>
  `;

  $("eco-mode").checked = battery.discharge_mode === 1;
  $("pause-start").value = battery.pause_slot_start || "";
  $("pause-end").value = battery.pause_slot_end || "";
  if (battery.battery_pause_mode != null && PAUSE_MODE_VALUES.includes(battery.battery_pause_mode)) {
    $("pause-mode").value = String(battery.battery_pause_mode);
  }
  if (battery.battery_soc_reserve != null) {
    $("reserve-slider").value = battery.battery_soc_reserve;
    $("reserve-value").textContent = battery.battery_soc_reserve + "%";
  }

  if (settings.active_power_rate != null) {
    $("apr-slider").value = settings.active_power_rate;
    $("apr-value").textContent = settings.active_power_rate + "%";
  }
  const battMaxKw = (id.battery_max_power_w || 0) / 1000;
  if (battery.battery_charge_limit != null) {
    $("charge-limit-slider").value = battery.battery_charge_limit;
    $("charge-limit-value").textContent = battMaxKw ? `${(battMaxKw * battery.battery_charge_limit / 100).toFixed(1)} kW` : `${battery.battery_charge_limit}%`;
  }
  if (battery.battery_discharge_limit != null) {
    $("discharge-limit-slider").value = battery.battery_discharge_limit;
    $("discharge-limit-value").textContent = battMaxKw ? `${(battMaxKw * battery.battery_discharge_limit / 100).toFixed(1)} kW` : `${battery.battery_discharge_limit}%`;
  }

  $("clock-inverter-time").textContent = id.system_time || "--";

  $("rtc-enable").checked = !!settings.enable_rtc;
  $("calibration-status").textContent = CALIBRATION_LABELS[battery.calibration_stage] || "Off";
  if (settings.export_priority != null) $("export-priority").value = settings.export_priority;
  $("eps-enabled").checked = !!settings.enable_eps;

  const c = data.commissioning || {};
  if (c.meter_type != null) $("c-meter-type").value = String(c.meter_type);
  $("c-ct-em115").checked = !!c.ct_direction_em115_reversed;
  $("c-ct-em418").checked = !!c.ct_direction_em418_reversed;
  if (c.battery_type != null) $("c-battery-type").value = String(c.battery_type);
  if (c.battery_capacity_ah != null) $("c-battery-capacity").value = c.battery_capacity_ah;
  if (c.pv_startup_voltage != null) $("c-pv-startup").value = c.pv_startup_voltage;
  if (c.pv_input_mode != null) $("c-pv-input-mode").value = String(c.pv_input_mode);
  if (c.grid_export_limit_w != null) $("c-export-limit").value = c.grid_export_limit_w;
  if (c.grid_import_limit_a != null) $("c-import-limit").value = c.grid_import_limit_a;
  $("c-import-limit-enabled").checked = !!c.grid_import_limit_enabled;
  $("c-force-off-grid").checked = !!c.force_off_grid;
}

function debounceCommit(el, fn) {
  let timer = null;
  el.addEventListener("input", () => { userEditingInverter = true; });
  el.addEventListener("change", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => { await fn(el.value); userEditingInverter = false; }, 150);
  });
}

debounceCommit($("reserve-slider"), async (v) => {
  $("reserve-value").textContent = v + "%";
  await apiPost("/battery/reserve", { value: parseInt(v, 10) });
});
debounceCommit($("charge-limit-slider"), async (v) => {
  await apiPost("/battery/charge-limit", { value: parseInt(v, 10) });
});
debounceCommit($("discharge-limit-slider"), async (v) => {
  await apiPost("/battery/discharge-limit", { value: parseInt(v, 10) });
});
debounceCommit($("apr-slider"), async (v) => {
  $("apr-value").textContent = v + "%";
  await apiPost("/battery/active-power-rate", { value: parseInt(v, 10) });
});

$("eco-mode").addEventListener("change", (e) => apiPost("/battery/discharge-mode", { enabled: e.target.checked }));
$("export-priority").addEventListener("change", (e) => apiPost("/battery/export-priority", { value: parseInt(e.target.value, 10) }));
$("eps-enabled").addEventListener("change", (e) => apiPost("/battery/eps", { enabled: e.target.checked }));
$("rtc-enable").addEventListener("change", (e) => apiPost("/battery/rtc", { enabled: e.target.checked }));
$("calibration-select").addEventListener("change", (e) => apiPost("/battery/calibration", { value: parseInt(e.target.value, 10) }));

$("btn-apply-pause").addEventListener("click", () => {
  apiPost("/battery/pause-slot", { start: $("pause-start").value || null, end: $("pause-end").value || null });
});
$("pause-mode").addEventListener("change", (e) => {
  apiPost("/battery/pause-mode", { value: parseInt(e.target.value, 10) });
});

$("btn-sync-clock").addEventListener("click", () => apiPost("/inverter/sync-clock"));
$("btn-restart").addEventListener("click", () => {
  if (confirm("Restart the inverter now? It will briefly go offline.")) {
    apiPost("/inverter/restart");
  }
});

// ---------------------------------------------------------------------------
// Commissioning (installer tier) — every write is confirmed first, matching
// the real app's "Confirm Commissioning Writes" behaviour.
// ---------------------------------------------------------------------------

function confirmedPost(path, body, message) {
  if (!confirm(message)) return;
  apiPost(path, body).catch((e) => alert("Write failed: " + e.message));
}

$("c-meter-type").addEventListener("change", (e) => {
  confirmedPost("/commissioning/meter-type", { value: parseInt(e.target.value, 10) }, "Change Meter Type?");
});
$("c-ct-em115").addEventListener("change", (e) => {
  confirmedPost("/commissioning/ct-direction-em115", { enabled: e.target.checked }, "Flip CT direction for EM115?");
});
$("c-ct-em418").addEventListener("change", (e) => {
  confirmedPost("/commissioning/ct-direction-em418", { enabled: e.target.checked }, "Flip CT direction for EM418?");
});
$("c-battery-type").addEventListener("change", (e) => {
  confirmedPost("/commissioning/battery-type", { value: parseInt(e.target.value, 10) }, "Change Battery Type?");
});
$("c-battery-capacity").addEventListener("change", (e) => {
  confirmedPost("/commissioning/battery-capacity", { value: parseInt(e.target.value, 10) }, "Set Battery Capacity?");
});
$("c-pv-startup").addEventListener("change", (e) => {
  const volts = parseFloat(e.target.value);
  confirmedPost("/commissioning/pv-startup-voltage", { value: Math.round(volts * 10) }, "Set PV Startup Voltage?");
});
$("c-pv-input-mode").addEventListener("change", (e) => {
  confirmedPost("/commissioning/pv-input-mode", { value: parseInt(e.target.value, 10) }, "Change PV Input Mode?");
});
$("c-export-limit").addEventListener("change", (e) => {
  confirmedPost("/commissioning/grid-export-limit", { value: parseInt(e.target.value, 10) }, "Set Grid Export Limit?");
});
$("c-import-limit").addEventListener("change", (e) => {
  confirmedPost("/commissioning/grid-import-limit", { value: parseInt(e.target.value, 10) }, "Set Grid Import Current Limit?");
});
$("c-import-limit-enabled").addEventListener("change", (e) => {
  confirmedPost("/commissioning/grid-import-limit-enabled", { enabled: e.target.checked }, "Toggle Grid Import Limit Enabled?");
});
$("c-force-off-grid").addEventListener("change", (e) => {
  confirmedPost("/commissioning/force-off-grid", { enabled: e.target.checked },
    e.target.checked ? "Force the inverter OFF GRID now? This isolates it from the grid." : "Restore normal grid connection?");
});

// ---------------------------------------------------------------------------
// Debug tools
// ---------------------------------------------------------------------------

function parseSlave(value) {
  if (value === "" || value === null || value === undefined) return null;
  const s = value.trim();
  if (s.toLowerCase().startsWith("0x")) return parseInt(s, 16);
  return parseInt(s, 10);
}

$("btn-dbg-read").addEventListener("click", async () => {
  const out = $("dbg-read-result");
  out.textContent = "Reading…";
  try {
    const result = await apiPost("/debug/read", {
      reg_type: $("dbg-read-type").value,
      address: parseInt($("dbg-read-addr").value, 10),
      count: parseInt($("dbg-read-count").value, 10) || 1,
      slave: parseSlave($("dbg-read-slave").value),
    });
    out.textContent = result.values.join(", ");
  } catch (e) {
    out.textContent = "Error: " + e.message;
  }
});

$("btn-dbg-write").addEventListener("click", async () => {
  const addr = $("dbg-write-addr").value;
  const val = $("dbg-write-value").value;
  if (addr === "" || val === "") { alert("Address and value are required"); return; }
  if (!confirm(`Write ${val} to HR(${addr})? This goes directly to the inverter.`)) return;
  const out = $("dbg-write-result");
  out.textContent = "Writing…";
  try {
    await apiPost("/debug/write", {
      address: parseInt(addr, 10),
      value: parseInt(val, 10),
      slave: parseSlave($("dbg-write-slave").value),
    });
    out.textContent = "Write OK";
  } catch (e) {
    out.textContent = "Error: " + e.message;
  }
});

$("btn-dbg-raw").addEventListener("click", async () => {
  const hex = $("dbg-raw-hex").value.trim();
  if (!hex) return;
  if (!confirm(`Send raw bytes "${hex}" directly to the device socket? No safety checks apply.`)) return;
  try {
    const result = await apiPost("/debug/raw-hex", { hex });
    alert(`Sent ${result.bytes_sent} bytes. Check the Raw Frame Log for any response.`);
  } catch (e) {
    alert("Send failed: " + e.message);
  }
});

let debugLogPollTimer = null;

function renderDebugLog(entries) {
  const el = $("dbg-log");
  el.innerHTML = entries
    .map((e) => {
      const ts = new Date(e.ts * 1000).toLocaleTimeString();
      const cls = e.direction === "tx" ? "log-tx" : "log-rx";
      return `<div class="${cls}">[${ts}] ${e.direction.toUpperCase()} ${e.hex}</div>`;
    })
    .join("");
  el.scrollTop = el.scrollHeight;
}

async function pollDebugLog() {
  try {
    const data = await apiGet("/debug/log");
    renderDebugLog(data.entries);
  } catch (e) { /* ignore */ }
}

$("btn-dbg-log-start").addEventListener("click", async () => {
  await apiPost("/debug/capture/start");
  if (debugLogPollTimer) clearInterval(debugLogPollTimer);
  debugLogPollTimer = setInterval(pollDebugLog, 1000);
  pollDebugLog();
});
$("btn-dbg-log-stop").addEventListener("click", async () => {
  await apiPost("/debug/capture/stop");
  if (debugLogPollTimer) { clearInterval(debugLogPollTimer); debugLogPollTimer = null; }
});
$("btn-dbg-log-clear").addEventListener("click", async () => {
  await apiDelete("/debug/log");
  $("dbg-log").innerHTML = "";
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

(async function init() {
  try {
    const status = await apiGet("/status");
    if (status.connected) {
      currentDevice = "existing";
      enterConnectedView();
      return;
    }
  } catch (e) { /* ignore */ }
  loadDevices();
})();

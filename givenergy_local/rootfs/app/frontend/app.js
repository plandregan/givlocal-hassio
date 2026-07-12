const API = "/api";
let ws = null;
let currentDevice = null;
let latestStatus = null;

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

// ---------------------------------------------------------------------------
// Devices / discovery
// ---------------------------------------------------------------------------

async function loadDevices() {
  const devices = await apiGet("/devices");
  const list = $("device-list");
  list.innerHTML = "";
  if (devices.length === 0) {
    list.innerHTML = '<p class="muted">No devices yet — scan your network or connect manually.</p>';
    return;
  }
  devices.forEach((d) => {
    const card = document.createElement("div");
    card.className = "device-card";
    const name = d.custom_name || d.model || d.host;
    card.innerHTML = `
      <div class="device-card__info">
        <span class="device-card__name">${name} ${d.favourite ? "&#9733;" : ""}</span>
        <span class="device-card__meta">${d.host}:${d.port} ${d.serial ? "&middot; " + d.serial : ""}</span>
      </div>
      <button class="btn btn-primary">Connect</button>
    `;
    card.querySelector("button").addEventListener("click", () => connectDevice(d.id));
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
  const pct = status.total ? Math.round((status.scanned / status.total) * 100) : 0;
  $("scan-progress-fill").style.width = pct + "%";
  $("scan-progress-label").textContent = `Scanning ${status.subnet_prefix}.0/24 — ${status.scanned}/${status.total}`;
  await loadDevices();
  if (status.running) {
    setTimeout(pollScan, 800);
  } else {
    $("scan-progress").classList.add("hidden");
  }
}

$("btn-scan").addEventListener("click", startScan);

$("manual-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const host = $("manual-host").value.trim();
  const port = parseInt($("manual-port").value, 10) || 8899;
  const device = await apiPost("/devices/manual", { host, port });
  await connectDevice(device.id);
});

async function connectDevice(deviceId) {
  try {
    await apiPost(`/connect/${deviceId}`);
    currentDevice = deviceId;
    enterConnectedView();
  } catch (e) {
    alert("Could not connect: " + e.message);
  }
}

function enterConnectedView() {
  $("tabs").classList.remove("hidden");
  showView("dashboard");
  connectWebSocket();
  loadIdentityAndSettings();
}

// ---------------------------------------------------------------------------
// Live status via WebSocket
// ---------------------------------------------------------------------------

function connectWebSocket() {
  if (ws) ws.close();
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}${API}/ws/live`);
  ws.onmessage = (evt) => {
    const data = JSON.parse(evt.data);
    latestStatus = data;
    renderStatus(data);
  };
  ws.onclose = () => {
    setTimeout(() => { if (currentDevice) connectWebSocket(); }, 2000);
  };
}

function fmtW(v) { return v === null || v === undefined ? "-- W" : `${v} W`; }
function fmtKwh(v) { return v === null || v === undefined ? "-- kWh" : `${v.toFixed(2)} kWh`; }

function renderStatus(data) {
  const pill = $("status-pill");
  if (data.connected) {
    pill.textContent = "Connected — " + data.host;
    pill.className = "status-pill status-pill--online";
  } else {
    pill.textContent = "Not connected";
    pill.className = "status-pill status-pill--offline";
    return;
  }

  const pf = data.power_flow || {};
  $("val-solar").textContent = fmtW(pf.solar_w);
  const gridW = (pf.grid_import_w || 0) - (pf.grid_export_w || 0);
  $("val-grid").textContent = fmtW(gridW);
  const battW = (pf.battery_charge_w || 0) - (pf.battery_discharge_w || 0);
  $("val-battery-power").textContent = fmtW(battW);
  // Home load = solar + battery discharge + grid import - battery charge - grid export.
  const homeW = (pf.solar_w || 0) + (pf.battery_discharge_w || 0) + (pf.grid_import_w || 0)
    - (pf.battery_charge_w || 0) - (pf.grid_export_w || 0);
  $("val-home").textContent = fmtW(Math.round(homeW));

  const battery = data.battery || {};
  $("val-battery-soc").textContent = battery.average_soc != null ? `${battery.average_soc}%` : "--%";

  const totals = data.totals_today || {};
  $("tot-solar").textContent = fmtKwh(totals.solar_kwh);
  $("tot-consumption").textContent = fmtKwh(totals.consumption_kwh);
  $("tot-charge").textContent = fmtKwh(totals.battery_charge_kwh);
  $("tot-discharge").textContent = fmtKwh(totals.battery_discharge_kwh);

  const faultsList = data.faults || [];
  const banner = $("fault-banner");
  if (faultsList.length > 0) {
    banner.textContent = `Active fault: ${faultsList.join(", ")}`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
  renderFaultLog();

  // Keep inverter-tab sliders in sync only if the user isn't actively dragging them.
  syncInverterFields(data);
}

async function renderFaultLog() {
  try {
    const log = await apiGet("/faults");
    const el = $("fault-log");
    if (!log.length) {
      el.innerHTML = '<p class="muted">No faults recorded.</p>';
      return;
    }
    el.innerHTML = log
      .slice()
      .reverse()
      .map((entry, i) => {
        const idx = log.length - 1 - i;
        const detected = new Date(entry.detected_at * 1000).toLocaleString();
        const cleared = entry.cleared_at
          ? new Date(entry.cleared_at * 1000).toLocaleString()
          : '<span class="fault-active">Active</span>';
        return `<div class="fault-entry"><span>${entry.name}<br><span class="muted">Detected: ${detected}</span></span><span>${cleared}</span></div>`;
      })
      .join("");
  } catch (e) {
    // no active device
  }
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
    if (slot === null && i > 1) return; // only show supported slots + first two
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
// Inverter tab
// ---------------------------------------------------------------------------

let userEditing = false;

async function loadIdentityAndSettings() {
  const data = await apiGet("/status");
  syncInverterFields(data);
}

function syncInverterFields(data) {
  if (userEditing) return;
  const id = data.identity || {};
  $("identity-block").innerHTML = `
    <div><span>Model</span>${id.model || "--"}</div>
    <div><span>Serial</span>${id.serial || "--"}</div>
    <div><span>DSP FW</span>${id.dsp_firmware_version ?? "--"}</div>
    <div><span>ARM FW</span>${id.arm_firmware_version ?? "--"}</div>
    <div><span>Inverter Time</span>${id.system_time || "--"}</div>
  `;

  const battery = data.battery || {};
  $("discharge-mode").checked = battery.discharge_mode === 1;
  if (battery.battery_soc_reserve != null) {
    $("reserve-slider").value = battery.battery_soc_reserve;
    $("reserve-value").textContent = battery.battery_soc_reserve + "%";
  }
  if (battery.battery_charge_limit != null) {
    $("charge-limit-slider").value = battery.battery_charge_limit;
    $("charge-limit-value").textContent = battery.battery_charge_limit + "%";
  }
  if (battery.battery_discharge_limit != null) {
    $("discharge-limit-slider").value = battery.battery_discharge_limit;
    $("discharge-limit-value").textContent = battery.battery_discharge_limit + "%";
  }

  const settings = data.settings || {};
  if (settings.active_power_rate != null) {
    $("apr-slider").value = settings.active_power_rate;
    $("apr-value").textContent = settings.active_power_rate + "%";
  }
  if (settings.export_priority != null) $("export-priority").value = settings.export_priority;
  $("eps-enabled").checked = !!settings.enable_eps;
}

function debounceCommit(el, fn) {
  let timer = null;
  el.addEventListener("input", () => { userEditing = true; });
  el.addEventListener("change", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => { await fn(el.value); userEditing = false; }, 150);
  });
}

debounceCommit($("reserve-slider"), async (v) => {
  $("reserve-value").textContent = v + "%";
  await apiPost("/battery/reserve", { value: parseInt(v, 10) });
});
debounceCommit($("charge-limit-slider"), async (v) => {
  $("charge-limit-value").textContent = v + "%";
  await apiPost("/battery/charge-limit", { value: parseInt(v, 10) });
});
debounceCommit($("discharge-limit-slider"), async (v) => {
  $("discharge-limit-value").textContent = v + "%";
  await apiPost("/battery/discharge-limit", { value: parseInt(v, 10) });
});
debounceCommit($("apr-slider"), async (v) => {
  $("apr-value").textContent = v + "%";
  await apiPost("/battery/active-power-rate", { value: parseInt(v, 10) });
});

$("discharge-mode").addEventListener("change", (e) => apiPost("/battery/discharge-mode", { enabled: e.target.checked }));
$("export-priority").addEventListener("change", (e) => apiPost("/battery/export-priority", { value: parseInt(e.target.value, 10) }));
$("eps-enabled").addEventListener("change", (e) => apiPost("/battery/eps", { enabled: e.target.checked }));

$("btn-set-pause-slot").addEventListener("click", () => {
  apiPost("/battery/pause-slot", { start: $("pause-start").value, end: $("pause-end").value });
});
$("btn-clear-pause-slot").addEventListener("click", () => {
  $("pause-start").value = "";
  $("pause-end").value = "";
  apiPost("/battery/pause-slot", { start: null, end: null });
});

$("btn-sync-clock").addEventListener("click", () => apiPost("/inverter/sync-clock"));
$("btn-restart").addEventListener("click", () => {
  if (confirm("Restart the inverter now? It will briefly go offline.")) {
    apiPost("/inverter/restart");
  }
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

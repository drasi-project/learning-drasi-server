// Copyright 2025 The Drasi Authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Curbside Pickup operations console (browser).
//
// Renders the two database tables and a live SQL log, and drives real UPDATEs
// through the Express API in server.js. The page polls /api/state so it always
// reflects the databases even when they change from elsewhere; toggling a row
// POSTs to the server, which runs the UPDATE and returns the refreshed state.

const POLL_MS = 1000;

const ordersBody = document.getElementById("orders-body");
const vehiclesBody = document.getElementById("vehicles-body");
const logEl = document.getElementById("log");
const statusEl = document.getElementById("status");
const statusText = document.getElementById("status-text");

// Plates currently mid-toggle, so we can disable their button and skip the
// poll-driven re-render that would otherwise clobber the "…" pending label.
const pending = new Set();

function esc(value) {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
}

function setStatus(kind, text) {
  statusEl.className = `status status-${kind}`;
  statusText.textContent = text;
}

function orderRow(o) {
  const ready = o.status === "ready";
  const badge = ready
    ? '<span class="badge badge-ready">✅ ready</span>'
    : '<span class="badge badge-preparing">🍕 preparing</span>';
  const label = ready ? "↩ preparing" : "mark ready →";
  const busy = pending.has(`o:${o.id}`);
  return `
    <tr>
      <td>${esc(o.id)}</td>
      <td>${esc(o.customer_name)}</td>
      <td><span class="plate">${esc(o.plate)}</span></td>
      <td>${badge}</td>
      <td class="col-action">
        <button class="toggle" data-kind="order" data-id="${esc(o.id)}" ${
          busy ? "disabled" : ""
        }>${busy ? "…" : label}</button>
      </td>
    </tr>`;
}

function vehicleRow(v) {
  const curbside = v.location === "Curbside";
  const badge = curbside
    ? '<span class="badge badge-curbside">🚙 Curbside</span>'
    : '<span class="badge badge-parking">🅿 Parking</span>';
  const label = curbside ? "↩ Parking" : "to Curbside →";
  const busy = pending.has(`v:${v.plate}`);
  return `
    <tr>
      <td><span class="plate">${esc(v.plate)}</span></td>
      <td>${esc(v.make)} ${esc(v.model)}</td>
      <td>${esc(v.color)}</td>
      <td>${badge}</td>
      <td class="col-action">
        <button class="toggle" data-kind="vehicle" data-plate="${esc(
          v.plate,
        )}" ${busy ? "disabled" : ""}>${busy ? "…" : label}</button>
      </td>
    </tr>`;
}

function renderLog(log) {
  if (!log || log.length === 0) {
    logEl.innerHTML =
      '<div class="log-empty">No statements yet — toggle a row above to run one.</div>';
    return;
  }
  const atBottom =
    logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 40;
  logEl.innerHTML = log
    .map((entry) => {
      const tag = String(entry.db || "").toLowerCase();
      return `<div class="log-line"><span class="log-tag tag-${esc(
        tag,
      )}">[${esc(entry.db)}]</span> ${esc(entry.text)}</div>`;
    })
    .join("");
  if (atBottom) logEl.scrollTop = logEl.scrollHeight;
}

function render(state) {
  const orders = state.orders || [];
  const vehicles = state.vehicles || [];

  ordersBody.innerHTML = orders.length
    ? orders.map(orderRow).join("")
    : '<tr><td colspan="5" class="empty">No orders.</td></tr>';

  vehiclesBody.innerHTML = vehicles.length
    ? vehicles.map(vehicleRow).join("")
    : '<tr><td colspan="5" class="empty">No vehicles.</td></tr>';

  renderLog(state.log);
}

async function refresh() {
  try {
    const res = await fetch("/api/state");
    const state = await res.json();
    if (state.connecting) {
      setStatus("connecting", "connecting to databases…");
      renderLog(state.log);
      return;
    }
    setStatus("connected", "connected");
    // Don't overwrite rows the user is actively toggling.
    if (pending.size === 0) render(state);
    else renderLog(state.log);
  } catch (e) {
    setStatus("error", "server unreachable");
  }
}

async function toggle(url, key) {
  pending.add(key);
  // Reflect the pending state immediately on the clicked button.
  document
    .querySelectorAll(".toggle")
    .forEach((b) => refreshButton(b));
  try {
    const res = await fetch(url, { method: "POST" });
    const state = await res.json();
    if (res.ok && !state.error) {
      pending.delete(key);
      render(state);
    } else {
      pending.delete(key);
      setStatus("error", state.error || "update failed");
    }
  } catch (e) {
    pending.delete(key);
    setStatus("error", "update failed");
  } finally {
    pending.delete(key);
  }
}

function refreshButton(btn) {
  const kind = btn.dataset.kind;
  const key =
    kind === "order" ? `o:${btn.dataset.id}` : `v:${btn.dataset.plate}`;
  if (pending.has(key)) {
    btn.disabled = true;
    btn.textContent = "…";
  }
}

document.addEventListener("click", (ev) => {
  const btn = ev.target.closest("button.toggle");
  if (!btn) return;
  if (btn.dataset.kind === "order") {
    toggle(`/api/orders/${encodeURIComponent(btn.dataset.id)}/toggle`, `o:${btn.dataset.id}`);
  } else {
    toggle(
      `/api/vehicles/${encodeURIComponent(btn.dataset.plate)}/toggle`,
      `v:${btn.dataset.plate}`,
    );
  }
});

refresh();
setInterval(refresh, POLL_MS);

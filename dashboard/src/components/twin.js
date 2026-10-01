// Digital twin: configured known-good state versus what the device itself reports.
// Wording is deliberate: a MATCH means the self-reported state matches, it is evidence, not attestation.
import { html } from "../lib/html.js";
import { ago, clock } from "../lib/format.js";
import { st } from "./status.js";
import { icon } from "./icons.js";

const FIELD = {
  fw_version: "Firmware version",
  cfg_hash: "Configuration hash",
  capabilities: "Capabilities",
  tamper: "Enclosure tamper switch",
};
const SENSOR = { temperature_c: ["Temperature", "°C"], humidity_pct: ["Humidity", "%"], pressure_hpa: ["Pressure", "hPa"], vibration_g: ["Vibration", "g"] };

function fieldName(k) {
  if (FIELD[k]) return FIELD[k];
  if (k.startsWith("sensor:")) return `${(SENSOR[k.slice(7)] || [k.slice(7)])[0]} range`;
  return k;
}
function fmt(k, v, side) {
  if (v === null || v === undefined) return side === "obs" ? "Not reported" : "Not set";
  if (Array.isArray(v) && k.startsWith("sensor:")) {
    const unit = (SENSOR[k.slice(7)] || [])[1] || "";
    return `${v[0] ?? "−∞"} to ${v[1] ?? "+∞"} ${unit}`.trim();
  }
  if (k.startsWith("sensor:") && Number.isFinite(v)) return `${v} ${(SENSOR[k.slice(7)] || [])[1] || ""}`.trim();
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}
function statusOf(s, k = "") {
  const sensor = k.startsWith("sensor:");
  if (k === "tamper") return s === "MATCH" ? st("ok", "Closed") : st("crit", "Open");
  if (s === "MATCH") return st("ok", sensor ? "In range" : "Match");
  if (s === "MISMATCH") return st("crit", sensor ? "Out of range" : "Mismatch");
  return st("na", "Not reported");
}

// The enclosure tamper switch is not part of the configured known-good state, but "closed" is required by policy:
// recovery health checks need tamper=false. Shown beside the comparison so a physical attack is visible here too.
const tamperOpen = (twin) => !!(twin && twin.observed && twin.observed.tamper === true);

export function twinVerdict(twin) {
  const c = twin && twin.comparison;
  if (tamperOpen(twin)) {
    return html`<div class="twin-verdict is-mismatch">${icon("xCircle")}<div><div class="h-panel">Enclosure tamper switch open</div><div class="meta">The device reports its tamper switch open. Health checks require it closed${c && c.overall === "MISMATCH" ? "; the configuration also differs from the known-good state" : ""}.</div></div></div>`;
  }
  if (!c || !Object.keys(c.fields || {}).length) {
    return html`<div class="twin-verdict is-unknown">${icon("info")}<div><div class="h-panel">No known-good state configured</div><div class="meta">Set the expected firmware and configuration so the device can be checked against it.</div></div></div>`;
  }
  const bad = Object.entries(c.fields || {}).filter(([, v]) => v.status === "MISMATCH");
  if (c.overall === "MATCH") {
    return html`<div class="twin-verdict is-match">${icon("checkCircle")}<div><div class="h-panel">Digital state match</div><div class="meta">Observed state matches the configured known-good state.</div></div></div>`;
  }
  if (bad.length) {
    return html`<div class="twin-verdict is-mismatch">${icon("xCircle")}<div><div class="h-panel">Digital state mismatch</div><div class="meta">${bad.map(([k]) => fieldName(k)).join(", ")} ${bad.length > 1 ? "differ" : "differs"} from the known-good state.</div></div></div>`;
  }
  return html`<div class="twin-verdict is-unknown">${icon("info")}<div><div class="h-panel">Not enough evidence yet</div><div class="meta">The device has not reported every expected field, so no match is claimed.</div></div></div>`;
}

/** A value the latest report did not carry is still shown, but marked with when it was last reported. */
function reported(k, v, obs) {
  const at = v.reported_at, latest = obs.observed_at;
  if (!Number.isFinite(at) || !Number.isFinite(latest) || latest - at < 1) return "";
  if (k === "capabilities") return html`<div class="caption">Reported at registration, ${clock(at)}</div>`;
  return html`<div class="caption twin-stale" title="The device's latest report did not include this field">Not in the latest report; last reported ${clock(at)}</div>`;
}

export function twinTable(twin, { serverNow = null } = {}) {
  const c = twin && twin.comparison;
  const obs = (twin && twin.observed) || {};
  const rows = c ? Object.entries(c.fields || {}) : [];
  if (typeof obs.tamper === "boolean") {
    rows.push(["tamper", { expected: "Closed (required by health checks)", observed: obs.tamper ? "OPEN" : "Closed",
      status: obs.tamper ? "MISMATCH" : "MATCH", reported_at: obs.reported_at && obs.reported_at.tamper }]);
  }
  if (!rows.length) return "";
  return html`<div class="table-wrap"><table class="table twin-table">
    <caption class="sr-only">Expected known-good state compared with the state the device reports</caption>
    <thead><tr><th scope="col">Field</th><th scope="col">Expected (known-good)</th><th scope="col">Observed (self-reported)</th><th scope="col">Status</th></tr></thead>
    <tbody>${rows.map(([k, v]) => html`<tr class="${v.status === "MISMATCH" ? "is-mismatch" : ""}" data-key="tw-${k}">
      <th scope="row" style="font-weight:600;text-align:left">${fieldName(k)}</th>
      <td class="exp">${fmt(k, v.expected, "exp")}</td>
      <td class="obs">${fmt(k, v.observed, "obs")}${reported(k, v, obs)}</td>
      <td>${statusOf(v.status, k)}</td></tr>`)}</tbody>
  </table></div>
  <p class="caption" style="margin-top:10px">${icon("info", 'style="display:inline;width:13px;height:13px;vertical-align:-2px"')} Observed values are reported by the device itself over its authenticated channel. A match is evidence, not cryptographic attestation.${Number.isFinite(obs.observed_at) ? ` Last report ${clock(obs.observed_at)}${Number.isFinite(serverNow) ? ` (${ago(serverNow - obs.observed_at)})` : ""}.` : ""}</p>`;
}

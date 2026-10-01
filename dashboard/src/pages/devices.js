// Devices: every enrolled device with its trust, connectivity and authentication at a glance.
import { html } from "../lib/html.js";
import { AUTH_PROFILES } from "../lib/copy.js";
import { clock, isoToTs } from "../lib/format.js";
import { S } from "../store.js";
import { fleet } from "../model.js";
import { icon } from "../components/icons.js";
import { empty, loadingPanel } from "../components/states.js";
import { simTag, stateBadge } from "../components/status.js";

export function render() {
  const head = html`<div class="page-head"><div><h1 class="h-page">Devices</h1><p class="lead">Every enrolled device, its trust and how it authenticates.</p></div></div>`;
  if (!S.loaded) return html`${head}${loadingPanel(6)}`;
  if (!S.devices.length) return html`${head}<section class="panel">${empty({ title: "No devices enrolled", text: "Enrol a device with python scripts/enroll_device.py. It appears here once it authenticates.", iconName: "devices" })}</section>`;
  const f = fleet();
  return html`${head}
  <section class="panel"><div class="panel-body table-wrap">
    <table class="table">
      <caption class="sr-only">Enrolled devices</caption>
      <thead><tr><th scope="col">Device</th><th scope="col">State</th><th scope="col">Trust</th><th scope="col">Connection</th><th scope="col">Hardware</th><th scope="col">Authentication</th><th scope="col">Firmware</th><th scope="col">Last seen</th><th scope="col">Incident</th></tr></thead>
      <tbody>${f.models.map((m) => {
        const d = m.device || {};
        const inc = m.incidents.find((i) => i.status !== "resolved");
        return html`<tr class="is-link" data-href="#/devices/${encodeURIComponent(m.id)}" data-key="dev-${m.id}">
          <td><a class="strong" href="#/devices/${encodeURIComponent(m.id)}">${m.id}</a>${d.revoked ? html` <span class="tag crit">Revoked</span>` : ""}</td>
          <td>${stateBadge(m.snapshot && m.snapshot.state)}</td>
          <td class="num strong">${m.snapshot && Number.isFinite(m.snapshot.score) ? m.snapshot.score : "—"}</td>
          <td><span class="chip ${m.connection.tone}" style="height:24px" title="${m.connection.caption}"><span class="dot"></span>${m.connection.label}</span></td>
          <td>${d.hw || "—"} ${d.hw === "software-agent" ? simTag() : ""}</td>
          <td>${AUTH_PROFILES[d.auth_profile] || d.auth_profile || "—"}</td>
          <td class="mono">${d.fw_version || "—"}</td>
          <td class="num">${d.last_seen ? clock(isoToTs(d.last_seen)) : "Never"}</td>
          <td>${inc ? html`<a href="#/incidents" class="st crit">${icon("alert")}${inc.id}</a>` : html`<span class="caption">None</span>`}</td>
        </tr>`;
      })}</tbody>
    </table>
  </div></section>`;
}

// Digital twin: configured known-good state against the device's self-reported state.
import { html } from "../lib/html.js";
import { clock } from "../lib/format.js";
import { S, focusId, gatewayNow } from "../store.js";
import { deviceModel } from "../model.js";
import { availability } from "../actions.js";
import { icon } from "../components/icons.js";
import { twinTable, twinVerdict } from "../components/twin.js";
import { empty, loadingPanel } from "../components/states.js";
import { st } from "../components/status.js";
import { devicePicker } from "./overview.js";

const SENSORS = [["temperature_c", "Temperature", "°C"], ["humidity_pct", "Humidity", "%"], ["pressure_hpa", "Pressure", "hPa"], ["vibration_g", "Vibration", "g"]];

export function render() {
  const head = (id) => html`<div class="page-head"><div><h1 class="h-page">Digital twin</h1>
    <p class="lead">What the device should be, set by an operator, next to what the device says it is. Recovery restores the expected state and health checks compare against it.</p></div>
    ${id ? devicePicker(id) : ""}</div>`;
  if (!S.loaded) return html`${head(null)}${loadingPanel(6)}`;
  const id = focusId();
  if (!id) return html`${head(null)}<section class="panel">${empty({ title: "No devices enrolled", iconName: "devices" })}</section>`;
  const m = deviceModel(id);
  if (m.recoveryUnavailable && !m.twin) return html`${head(id)}<section class="panel">${empty({ title: "Digital twin not enabled on this gateway", iconName: "twin" })}</section>`;
  const a = availability(id);
  const obs = (m.twin && m.twin.observed) || {};
  const sensors = obs.sensors || {};
  return html`${head(id)}
  <div class="grid split-7-5">
    <section class="panel" aria-labelledby="tw-title">
      <div class="panel-head"><h2 class="panel-title" id="tw-title">${icon("twin")}${id}: expected and observed</h2>
        <span class="act-wrap" title="${a.expected.ok ? "" : a.expected.why}"><button class="btn sm" type="button" data-action="op-expected" data-id="${id}" ${a.expected.ok ? "" : "disabled"}>${icon("edit")}Edit known-good state</button></span></div>
      <div class="panel-body stack">
        ${twinVerdict(m.twin)}
        ${!a.expected.ok ? html`<p class="caption">${a.expected.why}</p>` : ""}
        ${m.twin ? twinTable(m.twin, { serverNow: gatewayNow() }) : loadingPanel(4)}
      </div>
    </section>
    <div class="stack">
      <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("cpu")}Latest self-reported state</h2></div>
        <div class="panel-body">
          ${Object.keys(obs).length ? html`<dl class="kv">
            <dt>Firmware</dt><dd class="mono">${obs.fw_version || "Not reported"}</dd>
            <dt>Configuration</dt><dd class="mono">${obs.cfg_hash || "Not reported"}</dd>
            <dt>Capabilities</dt><dd>${(obs.capabilities || []).join(", ") || "Not reported"}</dd>
            <dt>Tamper switch</dt><dd>${obs.tamper === false ? st("ok", "Closed") : obs.tamper === true ? st("crit", "Open") : st("na", "Not reported")}</dd>
            ${SENSORS.map(([k, label, unit]) => html`<dt>${label}</dt><dd class="num">${Number.isFinite(sensors[k]) ? `${sensors[k]} ${unit}` : html`<span class="caption">No sensor</span>`}</dd>`)}
            <dt>Reported at</dt><dd>${Number.isFinite(obs.observed_at) ? clock(obs.observed_at) : "—"}</dd>
          </dl>` : empty({ title: "Nothing reported yet", text: "Observed state comes only from HMAC-authenticated device messages.", iconName: "cpu" })}
        </div></section>
      <section class="panel is-inset"><div class="panel-body stack-sm">
        <div class="strong row" style="gap:8px">${icon("info", 'style="width:16px;height:16px"')}What a match does and does not prove</div>
        <p class="meta">The device reports its own firmware and configuration over its authenticated channel. A match shows the report agrees with the known-good state. Without secure boot and remote attestation, a compromised device could report false values, so the twin is one piece of evidence among six, never proof on its own.</p>
      </div></section>
    </div>
  </div>`;
}

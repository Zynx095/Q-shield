// Device security profile: identity, trust, factors, enforcement, recovery, digital twin, incidents, timeline, evidence.
import { html } from "../lib/html.js";
import { AUTH_PROFILES, stateMeta } from "../lib/copy.js";
import { clock, isoToTs, ago } from "../lib/format.js";
import { S } from "../store.js";
import { UI, deviceModel, evidenceBlocks, limitOf, thresholds } from "../model.js";
import { availability } from "../actions.js";
import { icon } from "../components/icons.js";
import { trustLattice } from "../components/lattice.js";
import { factorList, scoreExplain } from "../components/factors.js";
import { channels, stateRail } from "../components/rail.js";
import { timeline } from "../components/timeline.js";
import { incidentCard } from "../components/incident.js";
import { stepper } from "../components/recovery.js";
import { twinTable, twinVerdict } from "../components/twin.js";
import { ledger } from "../components/ledger.js";
import { empty, loadingPanel } from "../components/states.js";
import { simTag, stateBadge } from "../components/status.js";
import { trustHistoryPanel } from "./overview.js";

export function actionButtons(id) {
  const a = availability(id);
  const btn = (kind, cls, ic, label) => html`<span class="act-wrap" title="${a[kind].ok ? "" : a[kind].why}">
    <button class="btn ${cls}" type="button" data-action="op-${kind}" data-id="${id}" ${a[kind].ok ? "" : html`disabled aria-describedby="why-${kind}-${id}"`}>${icon(ic)}${label}</button>
    ${a[kind].ok ? "" : html`<span class="sr-only" id="why-${kind}-${id}">${a[kind].why}</span>`}</span>`;
  const hint = !a.start.ok && !a.abort.ok ? a.start.why : "";      // nothing can be done right now: say why
  return html`<div class="stack-sm" style="align-items:flex-end;gap:6px">
    <div class="row">${btn("start", "accent", "refresh", "Start recovery")}${btn("abort", "danger", "stop", "Abort recovery")}${btn("expected", "", "edit", "Set known-good state")}</div>
    ${hint ? html`<p class="caption" style="text-align:right">${hint}</p>` : ""}</div>`;
}

export function render({ params }) {
  const id = params.id;
  const back = html`<a class="meta row" style="gap:4px;margin-bottom:8px" href="#/devices">${icon("chevronLeft", 'style="width:14px;height:14px"')}Devices</a>`;
  if (!S.loaded) return html`${back}${loadingPanel(8)}`;
  if (!S.devices.some((d) => d.device_id === id)) {
    return html`${back}<section class="panel">${empty({ title: "Unknown device", text: `The gateway has no device called ${id}.`, iconName: "devices" })}</section>`;
  }
  const m = deviceModel(id);
  const d = m.device || {};
  const snap = m.snapshot;
  const signers = ((S.system && S.system.pqc && S.system.pqc.signers) || []).filter((s) => (s.allowed_devices || []).includes(id));
  const blocks = evidenceBlocks().filter((b) => b.device_id === id);
  return html`${back}
  <div class="page-head">
    <div>
      <div class="row" style="gap:12px"><h1 class="h-page">${id}</h1>${stateBadge(snap && snap.state, { large: true })}${d.hw === "software-agent" ? simTag() : ""}</div>
      <p class="lead">${stateMeta(snap && snap.state).line}</p>
    </div>
    ${actionButtons(id)}
  </div>
  <div class="facts">
    <div class="fact"><div class="fact-label">Hardware</div><div class="fact-value">${d.hw || "—"}</div></div>
    <div class="fact"><div class="fact-label">Authentication</div><div class="fact-value">${AUTH_PROFILES[d.auth_profile] || d.auth_profile || "—"}</div></div>
    <div class="fact"><div class="fact-label">Firmware</div><div class="fact-value mono">${d.fw_version || "—"}</div></div>
    <div class="fact"><div class="fact-label">Connection</div><div class="fact-value">${m.connection.label}${d.revoked ? html` <span class="tag crit">Revoked</span>` : ""}${m.connection.caption ? html`<div class="caption">${m.connection.caption}</div>` : ""}</div></div>
    <div class="fact"><div class="fact-label">Last seen</div><div class="fact-value">${d.last_seen ? clock(isoToTs(d.last_seen)) : "Never"}${snap && Number.isFinite(snap.last_device_evidence_age_s) ? html` <span class="caption">${ago(snap.last_device_evidence_age_s)}</span>` : ""}</div></div>
    <div class="fact"><div class="fact-label">Vision signer</div><div class="fact-value">${signers.length ? signers.map((s) => `${s.signer_id} (${s.algorithm}, ${s.status})`).join(", ") : "None authorised"}</div></div>
  </div>

  <div class="grid split-5-7 section">
    <section class="panel" aria-label="Trust lattice">
      <div class="panel-body">
        ${snap && snap.status === "TRACKED" ? trustLattice({ snapshot: snap, factors: m.factors, thresholds: thresholds() }) : empty({ title: "No trust evidence yet", iconName: "shield" })}
        ${m.breakdown ? html`<div style="margin-top:12px"><button class="link-btn" type="button" data-action="toggle-math" aria-expanded="${UI.showMath}" aria-controls="dev-math">${UI.showMath ? "Hide the calculation" : "How is this score calculated?"}</button>
          <div id="dev-math" style="margin-top:10px" ${UI.showMath ? "" : "hidden"}>${UI.showMath ? scoreExplain(m.breakdown) : ""}</div></div>` : ""}
      </div>
    </section>
    <div class="stack">
      <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("shield")}Trust factors</h2></div><div class="panel-body">${factorList(m.factors)}</div></section>
      <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("lock")}Enforcement</h2></div><div class="panel-body stack-sm">${stateRail(m.path, snap && snap.state)}${channels(m.access)}</div></section>
    </div>
  </div>

  <div class="section">${trustHistoryPanel(m, "dev")}</div>

  <div class="grid grid-2 section">
    <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("refresh")}Recovery</h2><a class="meta" href="#/recovery">Open recovery</a></div>
      <div class="panel-body">${m.recoveryUnavailable ? empty({ title: "Recovery is not enabled on this gateway", iconName: "refresh" }) : stepper(m.steps, { compact: true })}</div></section>
    <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("twin")}Digital twin</h2><a class="meta" href="#/twin">Open twin</a></div>
      <div class="panel-body stack-sm">${twinVerdict(m.twin)}${twinTable(m.twin)}</div></section>
  </div>

  <div class="section stack">
    <h2 class="h-section">Incidents</h2>
    ${m.incidents.length ? m.incidents.map((i) => incidentCard(i)) : html`<section class="panel">${empty({ title: "No incidents", text: "No correlated incident has been recorded for this device.", iconName: "shieldCheck", ok: true })}</section>`}
  </div>

  <div class="grid split-7-5 section">
    <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("signal")}Security timeline</h2></div>
      <div class="panel-body">${m.timeline.length ? timeline(m.timeline, { expanded: UI.expanded, limit: limitOf("dev-tl", 20), deviceId: id, moreAction: "more:dev-tl", scope: "dev" }) : empty({ title: "No events yet", iconName: "signal" })}</div></section>
    <section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("ledger")}Evidence</h2><a class="meta" href="#/evidence">Full ledger</a></div>
      <div class="panel-body">${blocks.length ? ledger(blocks, { expanded: UI.expanded, limit: 6 }) : empty({ title: "No forensic events recorded yet", iconName: "ledger" })}</div></section>
  </div>`;
}

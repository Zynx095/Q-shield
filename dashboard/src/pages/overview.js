// Overview: "Is my system secure right now?" Posture, the focused device's trust lattice, its story, what the
// gateway is enforcing, the trust history and the live timeline. Every number is from the gateway.
import { html } from "../lib/html.js";
import { AUTH_PROFILES, stateMeta } from "../lib/copy.js";
import { ago, short } from "../lib/format.js";
import { S, focusId } from "../store.js";
import { UI, deviceModel, evidenceBlocks, flashTo, fleet, limitOf, thresholds } from "../model.js";
import { icon } from "../components/icons.js";
import { trustLattice } from "../components/lattice.js";
import { channels, stateRail } from "../components/rail.js";
import { trustChart } from "../components/chart.js";
import { timeline } from "../components/timeline.js";
import { incidentCard } from "../components/incident.js";
import { chainMini } from "../components/ledger.js";
import { scoreExplain } from "../components/factors.js";
import { empty, loadingPanel } from "../components/states.js";
import { simTag, stateBadge } from "../components/status.js";

export function devicePicker(id, label = "Device") {
  if (S.devices.length < 2) return "";
  return html`<label class="row" style="gap:8px"><span class="caption">${label}</span>
    <select class="select" data-action="focus" aria-label="${label}">${S.devices.map((d) => html`<option value="${d.device_id}" ${d.device_id === id ? "selected" : ""}>${d.device_id}</option>`)}</select></label>`;
}

export function trustHistoryPanel(m, id = "ov") {
  const pts = m.series;
  return html`<section class="panel" aria-labelledby="th-${id}">
    <div class="panel-head">
      <h2 class="panel-title" id="th-${id}">Trust over time</h2>
      <div class="seg" role="group" aria-label="Horizontal scale">
        <button type="button" data-action="chart-mode" data-mode="sequence" aria-pressed="${UI.chartMode === "sequence"}">Each change</button>
        <button type="button" data-action="chart-mode" data-mode="time" aria-pressed="${UI.chartMode === "time"}">Real time</button>
      </div>
    </div>
    <div class="panel-body">
      ${pts.length > 1
        ? html`${trustChart({ points: pts, thresholds: thresholds(), mode: UI.chartMode, width: UI.chartWidth[id] || 900, id })}
          <p class="caption" style="margin-top:6px">${UI.chartMode === "sequence" ? "Every recorded trust change, evenly spaced so a seconds-long attack stays readable beside a long recovery." : "Spaced by gateway time."} Dots mark state changes.</p>`
        : empty({ title: "Not enough history yet", text: "The chart appears after the trust engine records its first changes.", iconName: "signal" })}
    </div>
  </section>`;
}

function hero(f, m) {
  const p = f.posture;
  const snap = m && m.snapshot;
  const meta = stateMeta(snap && snap.state);
  const v = S.evidence.verify;
  const sys = S.system || {};
  const age = snap && Number.isFinite(snap.last_device_evidence_age_s) ? snap.last_device_evidence_age_s : null;
  const firstOpen = f.open.find((i) => i.deviceId === (m && m.id));
  return html`<section class="hero panel tone-${p.tone} ${m && flashTo(m.id) === "SUSPICIOUS" ? "is-sweep" : ""}" aria-labelledby="posture-title" data-reveal>
    <div class="hero-main">
      <div class="posture">
        <span class="posture-icon">${icon(p.icon)}</span>
        <div>
          <h1 class="h-page" id="posture-title">${p.title}</h1>
          <p class="lead">${p.line}</p>
        </div>
      </div>
      ${m ? html`
        <div class="hero-device">
          <div class="row" style="gap:10px">
            <a class="h-section" href="#/devices/${encodeURIComponent(m.id)}">${m.id}</a>
            ${stateBadge(snap && snap.state, { large: true })}
            ${m.device && m.device.hw === "software-agent" ? simTag() : ""}
          </div>
          ${devicePicker(m.id, "Focus")}
        </div>
        <p class="meta hero-stateline">${meta.line}</p>
        ${stateRail(m.path, snap && snap.state)}
        ${channels(m.access, { change: flashTo(m.id) })}
        <div class="facts">
          <div class="fact"><div class="fact-label">Last authenticated message</div><div class="fact-value">${age === null ? "—" : ago(age)}</div></div>
          <div class="fact"><div class="fact-label">Device authentication</div><div class="fact-value">${m.device ? (AUTH_PROFILES[m.device.auth_profile] || m.device.auth_profile).replace(" (pre-shared key)", "") : "—"}</div></div>
          <div class="fact"><div class="fact-label">Vision evidence</div><div class="fact-value">${sys.pqc && sys.pqc.enabled ? `${sys.pqc.sig_algorithm} signed` : "Not post-quantum"}</div></div>
          <div class="fact"><div class="fact-label">Evidence chain</div><div class="fact-value">${v ? (v.ok ? `${v.count} entries verified` : html`<span style="color:var(--crit)">Broken at #${v.first_bad_seq}</span>`) : "—"}</div></div>
        </div>
        ${firstOpen ? html`<div class="row"><a class="btn ${firstOpen.status === "open" ? "danger" : ""}" href="#/incidents">${icon("incident")}View ${firstOpen.id}</a>
          <a class="btn" href="#/recovery">${icon("refresh")}${firstOpen.status === "recovering" ? "Follow recovery" : "Go to recovery"}</a></div>` : ""}
      ` : ""}
    </div>
    <div class="hero-lattice">
      ${m && snap ? html`
        ${trustLattice({ snapshot: snap, factors: m.factors, thresholds: thresholds(), flash: UI.flash && UI.flash.deviceId === m.id && UI.flash.until > Date.now() })}
        <div class="lattice-caption">
          <p class="caption">Six evidence factors converge on the trust score. A factor's value is the points its adverse evidence removes.</p>
          <button class="link-btn" type="button" data-action="toggle-math" aria-expanded="${UI.showMath}" aria-controls="score-math">${UI.showMath ? "Hide" : "How is"} ${UI.showMath ? "the calculation" : "this score calculated?"}</button>
        </div>
        <div id="score-math" ${UI.showMath ? "" : "hidden"}>${UI.showMath ? scoreExplain(m.breakdown) : ""}</div>`
      : loadingPanel(6)}
    </div>
  </section>`;
}

export function render() {
  if (!S.loaded) return html`<div class="stack">${loadingPanel(8)}</div>`;
  const f = fleet();
  const id = focusId();
  const m = id ? deviceModel(id) : null;
  if (!m) {
    return html`${hero(f, null)}<div class="section">${empty({ title: "No devices enrolled", text: "Enrol a device (python scripts/enroll_device.py) and start it. It appears here as soon as it authenticates.", iconName: "devices" })}</div>`;
  }
  const blocks = evidenceBlocks();
  const v = S.evidence.verify;
  const openForDevice = f.open.filter((i) => i.deviceId === m.id);
  return html`
    ${hero(f, m)}
    <div class="section" data-reveal>${trustHistoryPanel(m, "ov")}</div>
    <div class="grid split-7-5 section">
      <section class="panel" aria-labelledby="tl-title" data-reveal>
        <div class="panel-head"><h2 class="panel-title" id="tl-title">${icon("signal")}Live security timeline</h2><span class="meta">${m.id}, newest first</span></div>
        <div class="panel-body">${m.timeline.length ? timeline(m.timeline, { expanded: UI.expanded, limit: limitOf("ov-tl", 14), deviceId: m.id, moreAction: "more:ov-tl", scope: "ov" })
          : empty({ title: "No security events yet", text: "Events appear here as the device reports and the gateway decides.", iconName: "signal" })}</div>
      </section>
      <div class="stack" data-reveal>
        ${openForDevice.length ? incidentCard(openForDevice[0], { compact: true })
          : html`<section class="panel">${empty({ title: "All clear", text: f.incidents.length ? "No active security incidents. Past incidents are resolved." : "No active security incidents.", iconName: "shieldCheck", ok: true })}</section>`}
        <section class="panel" aria-labelledby="ch-title">
          <div class="panel-head"><h2 class="panel-title" id="ch-title">${icon("ledger")}Evidence chain</h2><a class="meta" href="#/evidence">Open ledger</a></div>
          <div class="panel-body stack-sm">
            ${v ? html`<div class="row">${v.ok ? html`<span class="badge tone-ok">${icon("checkCircle")}Chain verified</span>` : html`<span class="badge tone-crit">${icon("xCircle")}Broken at #${v.first_bad_seq}</span>`}
              <span class="meta">${v.count} entries, SHA-256 linked${v.signed ? `, ${(S.system && S.system.evidence && S.system.evidence.algorithm) || "ML-DSA"} signed` : ", unsigned"}</span></div>
              <div class="caption">Head <span class="mono">${short(v.head_hash, 24)}</span></div>
              ${chainMini(blocks, 4)}`
            : S.evidence.unavailable ? empty({ title: "Evidence chain not configured", iconName: "ledger" }) : loadingPanel(2)}
          </div>
        </section>
        ${S.devices.length > 1 ? html`<section class="panel"><div class="panel-head"><h2 class="panel-title">${icon("devices")}Fleet</h2><a class="meta" href="#/devices">All devices</a></div>
          <div class="panel-body"><ul class="stack-sm">${f.models.map((x) => html`<li class="row-between"><a href="#/devices/${encodeURIComponent(x.id)}">${x.id}</a><span class="row" style="gap:8px"><span class="num strong">${x.snapshot && x.snapshot.score !== undefined ? x.snapshot.score : "—"}</span>${stateBadge(x.snapshot && x.snapshot.state)}</span></li>`)}</ul></div></section>` : ""}
      </div>
    </div>`;
}

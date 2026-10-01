// Camera & vision: what this browser's camera sees (a local preview; nothing leaves the page) beside what the Python
// vision service actually reported to the gateway (signed observations). They are kept apart on purpose: the preview
// is never analysed, and no signed observation ever came from this browser.
import { html } from "../lib/html.js";
import { observationView, visionStatus } from "../lib/derive.js";
import { ago, clock, duration, fixed } from "../lib/format.js";
import { S, gatewayNow } from "../store.js";
import { icon } from "../components/icons.js";
import { banner, empty, loadingPanel } from "../components/states.js";
import { simTag } from "../components/status.js";
import { CameraMonitor } from "../components/camera.js";

const SHOW = 8;

let monitor = null;

/** After each render (main.js): give the preview its mount. The mount is data-morph-skip, so refreshes leave it be. */
export function mount() {
  const host = document.getElementById("cam-mount");
  if (!host) return;
  if (!monitor) monitor = new CameraMonitor();
  monitor.attach(host);
}

/** Leaving the page or signing out: turn the camera off. */
export function release() {
  if (!monitor) return;
  monitor.release();
  monitor = null;
}

function previewPanel() {
  return html`<section class="panel" aria-labelledby="cam-title" data-reveal>
    <div class="panel-head"><h2 class="panel-title" id="cam-title">${icon("camera")}Live camera preview (this browser)</h2></div>
    <div class="panel-body stack-sm">
      ${banner("info", "info", "Local preview only.", "Not analysed, not signed, not sent to the gateway. The video stays on this page.")}
      <div id="cam-mount" data-morph-skip></div>
      <p class="caption">The vision service opens its own camera: the one set by <span class="mono">camera.source</span> in
        <span class="mono">config/vision.json</span>. Most webcams serve one program at a time, so preview the other camera, for example
        the integrated one while the USB camera feeds the vision service.</p>
    </div>
  </section>`;
}

// The path the LATEST observation actually took (recorded by the gateway), not the path the service could take.
function pipeline(p, latestModel, transport) {
  const head = [["Python vision service", ""], [latestModel || "Object detector", ""]];
  const steps = transport === "token" || (!transport && !p.enabled)
    ? [...head, ["Ingest token, unsigned", "warn"], ["Gateway stores", ""]]
    : transport === "signed"
      ? [...head, [`${p.sig_algorithm || "ML-DSA"} signature`, "pq"], ["Direct POST, no session", ""], ["Gateway verifies", ""]]
      : transport === "secure"
        ? [...head, [`${p.sig_algorithm} signature`, "pq"], [`${p.kem_algorithm} session (AES-256-GCM)`, "pq"], ["Gateway verifies", ""]]
        : [...head, [`${p.sig_algorithm} signature`, "pq"], [`optional ${p.kem_algorithm} session`, ""], ["Gateway verifies", ""]];
  return html`<ol class="pipe" aria-label="Path of the latest observation">${steps.map(([t, tone], i) => html`${i ? html`<li class="pipe-arrow" aria-hidden="true">${icon("chevronRight")}</li>` : ""}<li class="pipe-step ${tone}">${t}</li>`)}</ol>`;
}

const CAMERA = {
  ok: ["ok", "Reporting clear frames"], obstructed: ["crit", "Obstructed: lens covered or too dark"],
  source_lost: ["crit", "Source lost: no frames"],
};
const TRANSPORT = { secure: "inside the ML-KEM session", signed: "direct signed POST", token: "ingest token" };

function statusFacts(vs, now) {
  const cam = vs.camera ? CAMERA[vs.camera.state] || ["warn", vs.camera.state] : null;
  const last = vs.last;
  return html`<div class="facts vision-facts">
    <div class="fact"><div class="fact-label">Last observation received</div>
      <div class="fact-value">${last ? `${duration(vs.lastAgeS)} ago` : "None yet"}${last ? html`<div class="caption">${clock(last.ts)}${last.transport ? `, ${TRANSPORT[last.transport] || last.transport}` : ""}</div>` : ""}</div></div>
    <div class="fact"><div class="fact-label">Camera health (from the service)</div>
      <div class="fact-value">${cam ? html`<span class="st ${cam[0]}">${icon(cam[0] === "ok" ? "checkCircle" : "xCircle")}${cam[1]}</span><div class="caption">since ${clock(vs.camera.since)}</div>`
        : html`<span class="st na">${icon("minus")}No fault reported</span><div class="caption">the service reports changes only</div>`}</div></div>
    <div class="fact"><div class="fact-label">Rule matches stored</div>
      <div class="fact-value num">${vs.rules}<span class="caption"> of ${vs.total} observations, ${vs.signed} signed</span></div></div>
  </div>`;
}

function observationsPanel() {
  const p = (S.system && S.system.pqc) || {};
  const signers = p.signers || [];
  const all = S.observations.map(observationView);
  const real = all.find((o) => !o.synthetic && o.model);
  const many = new Set(all.map((o) => o.deviceId)).size > 1;
  const now = gatewayNow();
  const vs = visionStatus(S.observations, now);
  return html`<section class="panel" aria-labelledby="obs-title" data-reveal>
    <div class="panel-head"><h2 class="panel-title" id="obs-title">${icon("signature")}Vision service observations${p.enabled ? " (signed)" : ""}</h2></div>
    <div class="panel-body stack-sm">
      ${pipeline(p, real ? real.model.split(" ")[0] : null, vs.last && vs.last.transport)}
      <p class="caption">What the Python vision service reported, as stored by the gateway after it verified each signature. None of it came from the preview on this page.</p>
      ${S.loaded ? statusFacts(vs, now) : ""}
      ${signers.length ? html`<dl class="kv">${signers.map((sg) => html`<dt>Signer</dt><dd><span class="mono">${sg.signer_id}</span> ${sg.algorithm}, ${sg.status}<span class="caption">, source ${sg.source}${(sg.allowed_devices || []).length ? `, for ${sg.allowed_devices.join(", ")}` : ""}</span></dd>`)}</dl>` : ""}
      ${!S.loaded ? loadingPanel(4)
        : !all.length ? empty({ title: "No observations yet", text: "Start the vision service (python -m ai.vision, or scripts/demo_full.py --webcam). Its signed observations appear here.", iconName: "camera" })
        : html`<ol class="obs-list">${all.slice(0, SHOW).map((o) => html`<li class="obs-item ${o.rule ? "is-rule" : ""} ${o.health ? "is-health" : ""}" data-key="ob-${o.key}">
            <span class="obs-time num" title="Received ${ago(now - o.ts)}">${clock(o.ts)}</span>
            <div class="obs-body">
              <div class="obs-title">${o.title}${o.confidence !== null ? html` <span class="caption num">confidence ${fixed(o.confidence, 2)}</span>` : ""}${many ? html` <span class="caption">${o.deviceId}</span>` : ""}</div>
              <div class="obs-sub">${[o.zone, o.rule ? `rule matched: ${o.rule}` : null, o.model].filter(Boolean).join("; ")}</div>
            </div>
            <span class="obs-tags">${o.signed ? html`<span class="tag pqc" title="Verified ${o.alg} signature by ${o.signer}">${o.alg}</span>` : html`<span class="tag" title="Posted with the ingest token, not signed">Unsigned</span>`}${o.transport === "secure" ? html` <span class="tag pqc" title="Arrived inside an ML-KEM-768 session, AES-256-GCM encrypted">ML-KEM session</span>` : ""}${o.synthetic ? html` ${simTag("A synthetic detection from the attack simulation, signed with the real vision key; not camera output")}` : ""}</span>
          </li>`)}</ol>
          <p class="caption">Latest ${Math.min(SHOW, all.length)} of the ${all.length} most recent stored observations, newest first.</p>`}
    </div>
  </section>`;
}

export function render() {
  return html`<div class="page-head"><div><h1 class="h-page">Camera &amp; vision</h1>
    <p class="lead">A live preview from this browser's camera, beside the signed observations the vision service sent the gateway. The two are separate: the preview is never analysed or sent anywhere.</p></div></div>
  <div class="grid split-7-5">${previewPanel()}${observationsPanel()}</div>`;
}

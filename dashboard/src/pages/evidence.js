// Evidence chain: the forensic ledger of every security decision, hash-linked and ML-DSA signed by the gateway.
import { html } from "../lib/html.js";
import { ago, clock, short } from "../lib/format.js";
import { EVIDENCE_GROUPS, forensicCase, observationView } from "../lib/derive.js";
import { S, focusId } from "../store.js";
import { UI, evidenceBlocks } from "../model.js";
import { icon } from "../components/icons.js";
import { ledger } from "../components/ledger.js";
import { banner, empty, loadingPanel } from "../components/states.js";
import { rejectedTag, simTag } from "../components/status.js";

const FILTERS = [["all", "All"], ["trust", "Trust"], ["enforcement", "Enforcement"], ["recovery", "Recovery"], ["operator", "Operator"]];

function seal(v, ev) {
  if (ev.verifyError) return html`<div class="chain-seal na">${icon("info")}</div><div><h2 class="h-section">Verification unavailable</h2><p class="meta">The gateway did not answer the verification request.</p></div>`;
  if (!v) return html`<div class="chain-seal na">${icon("ledger")}</div><div><h2 class="h-section">Verifying…</h2></div>`;
  if (!v.ok) return html`<div class="chain-seal crit">${icon("unlink")}</div><div><h2 class="h-section" style="color:var(--crit)">Chain broken at entry #${v.first_bad_seq}</h2><p class="meta">${v.reason}. Entries after this point cannot be trusted.</p></div>`;
  return html`<div class="chain-seal ok">${icon("shieldCheck")}</div><div><h2 class="h-section">${v.signed ? "Chain verified" : "Chain intact, unsigned"}</h2>
    <p class="meta">${v.count} entries. Every hash recomputed${v.signed ? " and every signature checked" : ""} by the gateway.</p></div>`;
}

// What a cited record was, with the honesty labels it needs (simulated device data, synthetic detections).
function refLabel(ref, deviceId) {
  const [kind, id] = String(ref || "").split(/:(.*)/s);
  const dev = S.devices.find((d) => d.device_id === deviceId);
  if (kind === "device_message") {
    return html`Device message ${id}, HMAC-SHA256 authenticated${dev && dev.hw === "software-agent" ? html` ${simTag()}` : ""}`;
  }
  if (kind === "observation") {
    const o = S.observations.find((x) => x.observation_id === id);
    const v = o ? observationView(o) : null;
    return html`Observation <span class="mono">${short(id, 8)}</span>${v && v.signed ? `, ${v.alg} signed by ${v.signer}` : ""}${v && v.synthetic ? html` ${simTag("A synthetic detection from the attack simulation, signed with the real vision key; not camera output")}` : ""}`;
  }
  return ref;
}

/** The latest quarantine as a case: what happened, why, the proof, the gateway's action and the recovery. */
function caseFile(deviceId) {
  const c = deviceId ? forensicCase(S.evidence.entries, deviceId) : null;
  if (!c) return "";
  return html`<section class="panel section case" aria-labelledby="case-title" data-reveal>
    <div class="panel-head"><h2 class="panel-title" id="case-title">${icon("fileCheck")}Case file: ${c.incidentId || "quarantine"} on ${deviceId}</h2>
      <span class="badge tone-${c.resolved ? "ok" : "crit"}">${icon(c.resolved ? "checkCircle" : "alert")}${c.resolved ? "Resolved" : "Open"}</span></div>
    <div class="panel-body">
      <ol class="case-steps">${c.stages.map((s, n) => html`<li class="case-step ${s.pending ? "is-pending" : ""}" data-key="case-${s.key}">
        <span class="case-num" aria-hidden="true">${n + 1}</span>
        <div class="case-body"><h3 class="case-title">${s.title}</h3>
          ${s.pending || !s.items.length ? html`<p class="caption">${s.key === "recovered" ? "No recovery recorded yet. Start one from the Recovery page." : "Nothing recorded for this stage."}</p>`
            : html`<ul class="case-items">${s.items.map((it) => html`<li class="tone-${it.tone}">
              <a class="case-seq num" href="#/evidence/${it.seq}" title="Open evidence entry ${it.seq}">#${it.seq}</a>
              <span class="case-text">${s.key === "proof" ? refLabel(it.ref, deviceId) : it.text}${it.rejected ? html` ${rejectedTag()}` : ""}</span>
              <span class="case-when num">${it.score || clock(it.ts)}</span></li>`)}</ul>`}
        </div></li>`)}</ol>
      <p class="caption" style="margin-top:8px">Read only from the evidence chain below: every line cites the entry it comes from (SHA-256 linked, signed by the gateway). Select a number to open that entry.</p>
    </div>
  </section>`;
}

export function render({ params }) {
  const ev = S.evidence;
  const v = ev.verify;
  const sys = (S.system && S.system.evidence) || {};
  const head = html`<div class="page-head"><div><h1 class="h-page">Evidence chain</h1>
    <p class="lead">Every security decision is appended to a SHA-256 hash chain and signed by the gateway. Changing any entry breaks every link after it.</p></div></div>`;
  if (!S.loaded || !ev.loaded) return html`${head}${loadingPanel(8)}`;
  if (ev.unavailable) return html`${head}<section class="panel">${empty({ title: "Evidence chain not configured", text: "This gateway runs without the evidence chain.", iconName: "ledger" })}</section>`;
  const highlight = params.seq ? Number(params.seq) : null;
  const groups = EVIDENCE_GROUPS[UI.evidenceFilter];
  let blocks = evidenceBlocks();
  if (groups) blocks = blocks.filter((b) => groups.includes(b.event_type));
  if (UI.evidenceDevice !== "all") blocks = blocks.filter((b) => b.device_id === UI.evidenceDevice);
  const limit = highlight ? Math.max(UI.evidenceLimit, blocks.filter((b) => b.seq >= highlight).length + 2) : UI.evidenceLimit;

  return html`${head}
  <section class="panel" data-reveal>
    <div class="chain-head">
      ${seal(v, ev)}
      <div class="stack-sm" style="align-items:flex-end">
        <button class="btn sm" type="button" data-action="reverify">${icon("refresh")}Verify again</button>
        <span class="caption">${ev.verifyAt ? `Checked ${ago((Date.now() - ev.verifyAt) / 1000)}` : ""}</span>
      </div>
    </div>
    <div class="facts" style="margin:0 20px 20px">
      <div class="fact"><div class="fact-label">Linking</div><div class="fact-value">${sys.hash || "SHA-256"} hash chain</div></div>
      <div class="fact"><div class="fact-label">Signature</div><div class="fact-value">${v && v.signed ? `${sys.algorithm || "ML-DSA"}` : "Unsigned"}</div></div>
      <div class="fact"><div class="fact-label">Signing key</div><div class="fact-value mono">${sys.key_id || "—"}</div></div>
      <div class="fact"><div class="fact-label">Head</div><div class="fact-value"><span class="mono">#${v && v.head ? v.head.seq : "—"} ${v ? short(v.head_hash, 14) : ""}</span></div></div>
    </div>
  </section>
  ${caseFile(UI.evidenceDevice !== "all" ? UI.evidenceDevice : focusId())}
  <div class="section" data-reveal>${banner("info", "info", "Scope of this guarantee.", "The gateway recomputes every hash and checks every signature; the browser re-checks only that each entry points at the hash before it. The chain is not anchored externally, so someone holding both the database and the signing key could rewrite it.")}</div>
  <div class="row-between section" data-reveal>
    <div class="seg" role="group" aria-label="Filter entries">${FILTERS.map(([k, label]) => html`<button type="button" data-action="ev-filter" data-filter="${k}" aria-pressed="${UI.evidenceFilter === k}">${label}</button>`)}</div>
    ${S.devices.length ? html`<label class="row" style="gap:8px"><span class="caption">Device</span><select class="select" data-action="ev-device" aria-label="Filter by device">
      <option value="all" ${UI.evidenceDevice === "all" ? "selected" : ""}>All devices</option>
      ${S.devices.map((d) => html`<option value="${d.device_id}" ${UI.evidenceDevice === d.device_id ? "selected" : ""}>${d.device_id}</option>`)}</select></label>` : ""}
  </div>
  <section class="section">
    ${blocks.length ? html`${ledger(blocks, { expanded: UI.expanded, limit, highlight })}
      ${blocks.length > limit ? html`<button class="btn sm" type="button" data-action="ev-more" style="margin-left:64px">${icon("chevronDown")}Show ${Math.min(40, blocks.length - limit)} older entries</button>` : ""}`
      : html`<section class="panel">${empty({ title: "No forensic events recorded yet", text: ev.entries.length ? "No entries match this filter." : "Entries appear as soon as the gateway makes a security decision.", iconName: "ledger" })}</section>`}
  </section>`;
}

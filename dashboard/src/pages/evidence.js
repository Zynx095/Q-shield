// Evidence chain: the forensic ledger of every security decision, hash-linked and ML-DSA signed by the gateway.
import { html } from "../lib/html.js";
import { ago, short } from "../lib/format.js";
import { EVIDENCE_GROUPS } from "../lib/derive.js";
import { S } from "../store.js";
import { UI, evidenceBlocks } from "../model.js";
import { icon } from "../components/icons.js";
import { ledger } from "../components/ledger.js";
import { banner, empty, loadingPanel } from "../components/states.js";

const FILTERS = [["all", "All"], ["trust", "Trust"], ["enforcement", "Enforcement"], ["recovery", "Recovery"], ["operator", "Operator"]];

function seal(v, ev) {
  if (ev.verifyError) return html`<div class="chain-seal na">${icon("info")}</div><div><h2 class="h-section">Verification unavailable</h2><p class="meta">The gateway did not answer the verification request.</p></div>`;
  if (!v) return html`<div class="chain-seal na">${icon("ledger")}</div><div><h2 class="h-section">Verifying…</h2></div>`;
  if (!v.ok) return html`<div class="chain-seal crit">${icon("unlink")}</div><div><h2 class="h-section" style="color:var(--crit)">Chain broken at entry #${v.first_bad_seq}</h2><p class="meta">${v.reason}. Entries after this point cannot be trusted.</p></div>`;
  return html`<div class="chain-seal ok">${icon("shieldCheck")}</div><div><h2 class="h-section">${v.signed ? "Chain verified" : "Chain intact, unsigned"}</h2>
    <p class="meta">${v.count} entries. Every hash recomputed${v.signed ? " and every signature checked" : ""} by the gateway.</p></div>`;
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

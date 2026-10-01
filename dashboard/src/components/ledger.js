// Forensic evidence ledger. Every block shows its SHA-256 hash, the previous block's hash it commits to, and its
// ML-DSA signature. Link continuity is re-checked in the browser; signatures are verified by the gateway.
import { html } from "../lib/html.js";
import { OPERATOR_ACTIONS, evidenceLabel, failureLabel } from "../lib/copy.js";
import { bytes, clock, dateTime, short } from "../lib/format.js";
import { stateBadge } from "./status.js";
import { icon } from "./icons.js";

/** What this entry says, in one line, from its signed payload. */
export function blockTitle(b) {
  const p = b.payload || {};
  switch (b.event_type) {
    case "trust_state_transition":
      return p.previous_state ? `${p.previous_state} → ${p.new_state}` : `Trust record created: ${p.new_state}`;
    case "trust_score_change":
      return `Trust ${p.previous_score} → ${p.new_score}`;
    case "operator_action":
      return `${p.operator_id || "Operator"} ${OPERATOR_ACTIONS[p.action] || p.action}${p.result && p.result !== "success" ? " (refused)" : ""}`;
    case "recovery_failed":
      return `Recovery failed: ${failureLabel(p.reason)}`;
    default:
      return evidenceLabel(b.event_type);
  }
}

function blockDetail(b) {
  const sigBytes = b.signature ? b.signature.length / 2 : 0;
  return html`<dl class="kv">
    <dt>Event type</dt><dd class="mono">${b.event_type}</dd>
    <dt>Gateway time</dt><dd>${dateTime(b.ts)}</dd>
    <dt>Device</dt><dd>${b.device_id || "Gateway-wide"}</dd>
    <dt>Recorded by</dt><dd>${b.source}</dd>
    ${b.trust_state ? html`<dt>Trust at the time</dt><dd>${stateBadge(b.trust_state)} <span class="num strong">${b.trust_score}</span></dd>` : ""}
    <dt>Event hash</dt><dd class="hash-full">${b.event_hash}</dd>
    <dt>Previous hash</dt><dd class="hash-full">${b.prev_hash}</dd>
    <dt>Signature</dt><dd>${b.signature ? html`ML-DSA, ${bytes(sigBytes)}, key <span class="mono">${b.key_id}</span><div class="hash-full">${short(b.signature, 96)}</div>` : "Unsigned (PQC disabled on this gateway)"}</dd>
    <dt>Event id</dt><dd class="mono">${b.event_id}</dd>
    <dt>Payload</dt><dd><pre class="hash-full" style="white-space:pre-wrap;margin:0">${JSON.stringify(b.payload, null, 2)}</pre></dd>
  </dl>`;
}

export function ledger(blocks, { expanded = new Set(), limit = 40, highlight = null } = {}) {
  const desc = [...blocks].reverse().slice(0, limit);
  return html`<ol class="ledger" aria-label="Evidence chain, newest first">${desc.map((b, i) => {
    const id = `blk-${b.seq}`;
    const open = expanded.has(id) || highlight === b.seq;
    const older = desc[i + 1];
    const broken = b.linked === false || !!b.problem;
    return html`<li class="block ${broken ? "is-bad" : ""}" data-key="${id}" id="evidence-${b.seq}">
      <div class="block-rail">
        <span class="block-seq" aria-label="Entry ${b.seq}">#${b.seq}</span>
        ${older ? html`<span class="block-link ${b.linked === false ? "is-broken" : ""}"></span>` : ""}
      </div>
      <div style="min-width:0">
        <div class="block-card" ${highlight === b.seq ? html`style="border-color:var(--cobalt);box-shadow:0 0 0 3px var(--cobalt-tint)"` : ""}>
          <button class="block-head" type="button" aria-expanded="${open}" aria-controls="${id}-d" data-action="toggle" data-id="${id}">
            <span class="block-title">${blockTitle(b)} <span class="caption">${evidenceLabel(b.event_type)}, ${b.device_id || "gateway"}, ${clock(b.ts)}</span></span>
            <span class="block-ver">${b.problem ? html`<span class="st crit">${icon("xCircle")}${b.problem}</span>` : html`<span class="st ok">${icon("checkCircle")}Verified</span>`}</span>
            <span class="block-hashes"><span>hash <b>${short(b.event_hash, 12)}</b></span><span>prev <b>${short(b.prev_hash, 12)}</b></span><span>${b.signature ? "ML-DSA signed" : "unsigned"}</span></span>
          </button>
          <div class="block-body" id="${id}-d" ${open ? "" : "hidden"}>${open ? blockDetail(b) : ""}</div>
        </div>
        ${b.seq > 1 ? html`<div class="prevlink">${icon(b.linked === false ? "unlink" : "link")}${b.linked === false
          ? html`<span style="color:var(--crit)">Link broken: prev_hash does not match entry #${b.seq - 1}</span>`
          : html`<span>commits to #${b.seq - 1} (${short(b.prev_hash, 8)})${b.linked === true ? ", link checked" : ""}</span>`}</div>` : html`<div class="prevlink">${icon("link")}<span>genesis entry (prev_hash is all zeros)</span></div>`}
      </div>
    </li>`;
  })}</ol>`;
}

/** Compact horizontal chain of the last few blocks (overview). */
export function chainMini(blocks, n = 4) {
  const last = blocks.slice(-n);
  if (!last.length) return "";
  return html`<div class="chain-mini" aria-hidden="true">${last.map((b, i) => html`${i ? html`<span class="cm-link"></span>` : ""}<a class="cm-block" href="#/evidence/${b.seq}" tabindex="-1"><b>#${b.seq}</b><span class="mono">${short(b.event_hash, 6)}</span></a>`)}</div>`;
}

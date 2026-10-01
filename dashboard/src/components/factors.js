// The six trust factors as a readable list, plus the plain-language score breakdown (the "advanced" view).
import { html } from "../lib/html.js";
import { capLabel, factorLabel, signalLabel } from "../lib/copy.js";
import { clock, fixed, pct } from "../lib/format.js";
import { icon } from "./icons.js";

export function factorList(factors, { compact = false } = {}) {
  return html`<ul class="factors">${factors.map((f) => {
    const status = !f.available ? "No data" : f.level === "clear" ? "Clear" : `−${fixed(f.loss, 1)} pts`;
    const health = f.available ? Math.round(f.health) : 0;
    const desc = !f.available
      ? "No evidence yet. Excluded from the score until it reports."
      : f.last
        ? `Last: ${signalLabel(f.last.signal)} at ${clock(f.last.ts)}${Number.isFinite(f.last.confidence) ? `, confidence ${fixed(f.last.confidence, 2)}` : ""}`
        : compact ? "" : f.desc;
    return html`<li class="factor is-${f.level === "na" ? "na" : f.level}" data-key="fac-${f.key}">
      <span class="factor-icon">${icon(f.icon)}</span>
      <span class="factor-name">${f.label}${f.available ? html`<span class="caption">${pct(f.weight)} of score</span>` : ""}</span>
      <span class="factor-status">${status}</span>
      ${desc ? html`<span class="factor-desc">${desc}</span>` : ""}
      <span class="meter" role="meter" aria-label="${f.label} health" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${health}">
        ${f.available ? html`<i style="width:${health}%"></i>${f.level !== "clear" ? html`<i class="loss" style="width:${100 - health}%"></i>` : ""}` : ""}
      </span>
    </li>`;
  })}</ul>`;
}

export function scoreExplain(b) {
  if (!b) return "";
  return html`<div class="stack-sm">
    <dl class="kv">
      <dt>Weighted factor health</dt><dd class="num">${fixed(b.raw, 1)} <span class="caption">sum of each available factor's weight × (100 − penalty)</span></dd>
      <dt>Attack pressure</dt><dd class="num">−${fixed(b.pressure, 1)} <span class="caption">unauthenticated attack traffic, bounded; cannot quarantine on its own</span></dd>
      <dt>Before ceilings</dt><dd class="num">${fixed(b.uncapped, 1)}</dd>
      <dt>Ceilings</dt><dd>${b.caps.length ? b.caps.map((c) => html`<div>${capLabel(c.name)} ceiling <span class="num strong">${c.ceiling}</span></div>`) : "None active"}</dd>
      <dt>Trust score</dt><dd class="num strong">${b.final} <span class="caption">${b.capped ? "held down by a ceiling" : "rounded"}</span></dd>
      <dt>Coverage</dt><dd>${pct(b.coverage)} of factor weight has evidence${b.unavailable.length ? html` <span class="caption">(no data: ${b.unavailable.map(factorLabel).join(", ")})</span>` : ""}</dd>
    </dl>
  </div>`;
}

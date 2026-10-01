// Status primitives: a state is always icon + word + tone, never colour alone.
import { html } from "../lib/html.js";
import { stateMeta } from "../lib/copy.js";
import { icon } from "./icons.js";

export function stateBadge(state, { large = false } = {}) {
  const m = stateMeta(state);
  return html`<span class="badge ${large ? "is-lg" : ""} tone-${m.tone}">${icon(m.icon)}${state || "NO DATA"}</span>`;
}

export function toneBadge(tone, iconName, text) {
  return html`<span class="badge tone-${tone}">${icon(iconName)}${text}</span>`;
}

/** Inline status word with icon (tables). kind: ok | crit | warn | na */
export function st(kind, text) {
  const ic = { ok: "checkCircle", crit: "xCircle", warn: "alert", na: "minus" }[kind] || "dot";
  return html`<span class="st ${kind}">${icon(ic)}${text}</span>`;
}

export function chip(tone, text, { key = false, title = "" } = {}) {
  return html`<span class="chip ${tone} ${key ? "chip-key" : ""}" title="${title}"><span class="dot" aria-hidden="true"></span>${text}</span>`;
}

export function deltaText(d) {
  if (!Number.isFinite(d)) return "";
  const cls = d < 0 ? "neg" : d > 0 ? "pos" : "zero";
  const txt = d > 0 ? `+${d}` : d < 0 ? `−${Math.abs(d)}` : "±0";
  return html`<span class="delta ${cls}">${txt}</span>`;
}

export function authTag(auth) {
  if (!auth) return "";
  if (auth === "DEVICE_HMAC" || /hmac/i.test(auth)) return html`<span class="tag hmac">HMAC-SHA256</span>`;
  if (auth === "SIGNER_MLDSA" || /ML-DSA/i.test(auth)) return html`<span class="tag pqc">ML-DSA-65</span>`;
  if (auth === "UNAUTHENTICATED") return html`<span class="tag crit">Unauthenticated</span>`;
  if (auth === "TOKEN_ONLY") return html`<span class="tag">Token only</span>`;
  return html`<span class="tag">${auth}</span>`;
}

export const simTag = (title = "Data from the software agent, not physical hardware") =>
  html`<span class="tag sim" title="${title}">Simulated</span>`;

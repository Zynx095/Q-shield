// Safe HTML templating. Every interpolated value is escaped unless it is already Safe (built by `html` or `raw`).
// Security events carry attacker-chosen strings (claimed device ids, observation ids...), so nothing from the
// API is ever concatenated into markup without passing through here.

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" };

export class Safe {
  constructor(s) { this.s = s; }
  toString() { return this.s; }
}

export const esc = (v) => String(v ?? "").replace(/[&<>"'`]/g, (c) => ESC[c]);

/** Trusted markup only: static strings and SVG built in this codebase. Never pass API data to raw(). */
export const raw = (s) => new Safe(String(s));

function part(v) {
  if (v === null || v === undefined || v === false) return "";
  if (v instanceof Safe) return v.s;
  if (Array.isArray(v)) return v.map(part).join("");
  return esc(v);
}

export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) out += part(values[i]) + strings[i + 1];
  return new Safe(out);
}

/** Join a list of Safe fragments. */
export const join = (items, sep = "") => new Safe(items.map(part).join(part(sep)));

/** class list helper: cls("a", cond && "b") */
export const cls = (...xs) => xs.filter(Boolean).join(" ");

// Formatting. All timestamps from the gateway are seconds on the GATEWAY clock (which the demo can run ahead in an
// announced TIME-LAPSE); relative ages are computed against the gateway clock estimate, never the browser clock alone.

const pad = (n) => String(n).padStart(2, "0");

export function clock(ts) {
  if (ts === null || ts === undefined || !Number.isFinite(ts)) return "—";
  const d = new Date(ts * 1000);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

export function dateTime(ts) {
  if (!Number.isFinite(ts)) return "—";
  const d = new Date(ts * 1000);
  return `${d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}, ${clock(ts)}`;
}

export function dayKey(ts) {
  const d = new Date(ts * 1000);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

export function dayLabel(ts) {
  return new Date(ts * 1000).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

export function duration(s) {
  if (!Number.isFinite(s)) return "—";
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min${s % 60 && m < 10 ? ` ${s % 60} s` : ""}`;
  const h = Math.floor(m / 60);
  return `${h} h${m % 60 ? ` ${m % 60} min` : ""}`;
}

export function ago(s) {
  if (!Number.isFinite(s)) return "—";
  if (s < 2) return "just now";
  return `${duration(s)} ago`;
}

export function countdown(s) {
  if (!Number.isFinite(s)) return "—";
  const neg = s < 0;
  s = Math.abs(Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  return `${neg ? "-" : ""}${h ? `${h}:${pad(m)}` : m}:${pad(r)}`;
}

export const int = (n) => (Number.isFinite(n) ? String(Math.round(n)) : "—");
export const fixed = (n, d = 1) => (Number.isFinite(n) ? n.toFixed(d) : "—");
export const pct = (x) => (Number.isFinite(x) ? `${Math.round(x * 100)}%` : "—");
export function signed(n, d = 0) {
  if (!Number.isFinite(n)) return "—";
  const v = d ? n.toFixed(d) : String(Math.round(n));
  return n > 0 ? `+${v}` : n < 0 ? v.replace("-", "−") : v;
}

export const short = (h, n = 10) => (h ? `${String(h).slice(0, n)}…` : "—");
export const isoToTs = (iso) => (iso ? Date.parse(iso) / 1000 : null);

export function bytes(n) {
  if (!Number.isFinite(n)) return "—";
  return n >= 1024 ? `${(n / 1024).toFixed(n % 1024 ? 1 : 0)} KiB` : `${n} B`;
}

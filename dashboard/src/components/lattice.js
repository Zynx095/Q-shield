// The Trust Lattice: six evidence factors converge on the trust core. Each spoke's weight is its share of the
// score; a factor's colour and value show how many points its adverse evidence currently removes. The hexagonal
// ring around the core is the score itself (0 at the top, clockwise), with the 50 / 80 decision thresholds marked.
import { html, raw } from "../lib/html.js";
import { stateMeta } from "../lib/copy.js";
import { iconPaths } from "./icons.js";

const C = 240;            // centre of the 480 x 480 view box
const R_NODE = 158;       // spoke length to factor nodes
const R_CORE = 86;        // core hexagon
const R_RING = 100;       // score ring
const R_N = 27;           // factor node hexagon

const rad = (deg) => (deg * Math.PI) / 180;
const pt = (r, deg, cx = C, cy = C) => [cx + r * Math.cos(rad(deg)), cy + r * Math.sin(rad(deg))];
const f1 = (n) => n.toFixed(1);

function hexPath(r, cx = C, cy = C) {
  const ps = [-90, -30, 30, 90, 150, 210].map((a) => pt(r, a, cx, cy));
  return `M${ps.map(([x, y]) => `${f1(x)} ${f1(y)}`).join("L")}Z`;
}

/** Point at fraction f (0..1) along the hexagon perimeter, starting at the top vertex, clockwise. */
function along(r, f) {
  const verts = [-90, -30, 30, 90, 150, 210, 270].map((a) => pt(r, a));
  const seg = Math.min(5, Math.floor(f * 6));
  const t = f * 6 - seg;
  const [x0, y0] = verts[seg], [x1, y1] = verts[seg + 1];
  return [x0 + (x1 - x0) * t, y0 + (y1 - y0) * t];
}

let gridCache = null;
function honeycomb() {
  if (gridCache) return gridCache;
  const r = 19, w = Math.sqrt(3) * r;
  let d = "";
  for (let q = -7; q <= 7; q++) {
    for (let s = -7; s <= 7; s++) {
      const x = C + w * (q + s / 2), y = C + 1.5 * r * s;
      if (Math.hypot(x - C, y - C) > 236) continue;
      d += hexPath(r, x, y);
    }
  }
  gridCache = d;
  return d;
}

const ANGLES = [-90, -30, 30, 90, 150, 210];

export function trustLattice({ snapshot, factors, thresholds = null, flash = false }) {
  const tracked = snapshot && snapshot.status === "TRACKED";
  const score = tracked ? snapshot.score : null;
  const meta = stateMeta(tracked ? snapshot.state : null);
  const caps = (tracked && snapshot.caps) || [];
  const ceiling = caps.length ? Math.min(...caps.map((c) => c.ceiling)) : null;
  const ringLen = 100;
  const offset = ringLen - (score ?? 0);

  const spokes = factors.map((f, i) => {
    const a = ANGLES[i];
    const [nx, ny] = pt(R_NODE, a);
    const [cx, cy] = pt(R_RING + 10, a);
    const w = f.available ? 1.6 + (f.weight || 0) * 15 : 1.5;
    const cls = f.level === "na" ? "is-na" : f.level === "severe" ? "is-severe" : f.level === "hit" ? "is-hit" : "";
    return html`<line class="lat-link ${cls}" x1="${f1(cx)}" y1="${f1(cy)}" x2="${f1(nx)}" y2="${f1(ny)}" stroke-width="${f1(w)}"/>`;
  });

  const nodes = factors.map((f, i) => {
    const a = ANGLES[i];
    const [nx, ny] = pt(R_NODE, a);
    const upper = Math.sin(rad(a)) < 0;
    const ly = upper ? ny - R_N - 22 : ny + R_N + 20;
    const lvl = f.level === "na" ? "is-na" : `is-${f.level}`;
    const value = !f.available ? "No data" : f.level === "clear" ? "Clear" : `−${f.loss.toFixed(1)} pts`;
    return html`<g class="lat-factor" data-key="lf-${f.key}">
      <title>${f.label}: ${f.available ? `${Math.round(f.health)} / 100 health, ${Math.round((f.weight || 0) * 100)}% of the score` : "no evidence yet, excluded from the score"}</title>
      <path class="lat-node ${lvl}" d="${hexPath(R_N, nx, ny)}"/>
      <g class="lat-node-icon ${lvl}" transform="translate(${f1(nx - 10)} ${f1(ny - 10)}) scale(0.8333)">
        <g fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${raw(iconPaths(f.icon))}</g>
      </g>
      <text class="lat-label" x="${f1(nx)}" y="${f1(ly)}" text-anchor="middle">${f.label}</text>
      <text class="lat-value ${lvl}" x="${f1(nx)}" y="${f1(ly + 15)}" text-anchor="middle">${value}</text>
    </g>`;
  });

  const ticks = [];
  const tq = thresholds && thresholds.quarantine_below, tt = thresholds && thresholds.trusted_min;
  for (const [v, label] of [[tq, "Quarantine below"], [tt, "Trusted from"]]) {
    if (!Number.isFinite(v)) continue;
    const [x, y] = along(R_RING, v / 100);
    const [x2, y2] = along(R_RING + 13, v / 100);
    ticks.push(html`<line class="lat-tick" x1="${f1(x)}" y1="${f1(y)}" x2="${f1(x2)}" y2="${f1(y2)}"><title>${label} ${v}</title></line>`);
  }
  if (Number.isFinite(ceiling) && ceiling < 100) {
    const [x, y] = along(R_RING - 9, ceiling / 100);
    const [x2, y2] = along(R_RING + 9, ceiling / 100);
    ticks.push(html`<line class="lat-cap" x1="${f1(x)}" y1="${f1(y)}" x2="${f1(x2)}" y2="${f1(y2)}"><title>Ceiling ${ceiling}: an active cap limits the score</title></line>`);
  }

  const label = tracked
    ? `Trust score ${score} of 100, state ${snapshot.state}. ` + factors.map((f) => `${f.label}: ${!f.available ? "no data" : f.level === "clear" ? "clear" : `minus ${f.loss.toFixed(1)} points`}`).join(", ")
    : "No trust evidence yet";

  return html`<div class="lattice ${flash ? "is-flash" : ""}" data-tone="${meta.tone}">
    <svg viewBox="0 0 480 480" role="img" aria-label="${label}">
      <defs>
        <radialGradient id="lat-fade" cx="50%" cy="50%" r="50%"><stop offset="35%" stop-color="#fff" stop-opacity="1"/><stop offset="100%" stop-color="#fff" stop-opacity="0"/></radialGradient>
        <mask id="lat-mask"><rect width="480" height="480" fill="url(#lat-fade)"/></mask>
      </defs>
      <path class="lat-grid" d="${honeycomb()}" mask="url(#lat-mask)"/>
      ${spokes}
      <path class="lat-core" d="${hexPath(R_RING + 10)}"/>
      <path class="lat-track" d="${hexPath(R_RING)}"/>
      <path class="lat-progress" d="${hexPath(R_RING)}" pathLength="${ringLen}" stroke-dasharray="${ringLen}" style="stroke-dashoffset:${f1(offset)}"/>
      ${ticks}
      <text class="lat-of" x="${C}" y="${C - 46}" text-anchor="middle">Trust score</text>
      <text class="lat-score" x="${C}" y="${C + 24}" text-anchor="middle" data-tween="score">${tracked ? score : "—"}</text>
      <text class="lat-state" x="${C}" y="${C + 52}" text-anchor="middle">${tracked ? snapshot.state : "NO DATA"}</text>
      ${nodes}
    </svg>
  </div>`;
}

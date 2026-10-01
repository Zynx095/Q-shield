// Trust over time. One series (the score) as a step line: the score holds between recorded changes.
// Two x-scales: "Sequence" spaces every recorded change evenly so a one-second attack stays readable next to a
// forty-minute recovery; "Time" is true gateway time. The decision thresholds are drawn as bands, from config.
import { html } from "../lib/html.js";
import { stateMeta } from "../lib/copy.js";
import { clock } from "../lib/format.js";

const f1 = (n) => n.toFixed(1);

export function trustChart({ points, thresholds, mode = "sequence", width = 900, id = "trust" }) {
  const W = Math.max(320, Math.round(width));
  const H = W < 600 ? 220 : 248;
  const m = { l: 34, r: W < 600 ? 12 : 128, t: 12, b: 30 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  if (!points.length) return html``;

  const y = (v) => m.t + ih - (Math.max(0, Math.min(100, v)) / 100) * ih;
  let x;
  if (mode === "time" && points.length > 1) {
    const t0 = points[0].ts, t1 = points[points.length - 1].ts || t0 + 1;
    x = (p) => m.l + ((p.ts - t0) / Math.max(1e-6, t1 - t0)) * iw;
  } else {
    const n = Math.max(1, points.length - 1);
    x = (_p, i) => m.l + (i / n) * iw;
  }
  const xs = points.map((p, i) => x(p, i));

  // step-after path
  let d = "";
  points.forEach((p, i) => {
    const px = xs[i], py = y(p.score);
    if (i === 0) d += `M${f1(px)} ${f1(py)}`;
    else d += `H${f1(px)}V${f1(py)}`;
  });
  const area = `${d}V${f1(m.t + ih)}H${f1(xs[0])}Z`;

  const qb = thresholds?.quarantine_below, tm = thresholds?.trusted_min;
  const bands = [];
  if (Number.isFinite(qb) && Number.isFinite(tm)) {
    bands.push(html`<rect class="ch-band z-q" x="${m.l}" y="${f1(y(qb))}" width="${f1(iw)}" height="${f1(y(0) - y(qb))}"/>`);
    bands.push(html`<rect class="ch-band z-s" x="${m.l}" y="${f1(y(tm))}" width="${f1(iw)}" height="${f1(y(qb) - y(tm))}"/>`);
    bands.push(html`<rect class="ch-band z-t" x="${m.l}" y="${f1(y(100))}" width="${f1(iw)}" height="${f1(y(tm) - y(100))}"/>`);
  }
  const grid = [0, 25, 50, 75, 100].map((v) => html`
    <line class="ch-grid" x1="${m.l}" x2="${m.l + iw}" y1="${f1(y(v))}" y2="${f1(y(v))}"/>
    <text class="ch-axis" x="${m.l - 8}" y="${f1(y(v) + 4)}" text-anchor="end">${v}</text>`);
  const zoneLabels = W >= 600 && Number.isFinite(qb) && Number.isFinite(tm) ? html`
    <text class="ch-zone z-t" x="${m.l + iw + 12}" y="${f1((y(100) + y(tm)) / 2 + 4)}">Trusted ≥ ${tm}</text>
    <text class="ch-zone z-s" x="${m.l + iw + 12}" y="${f1((y(tm) + y(qb)) / 2 + 4)}">Suspicious</text>
    <text class="ch-zone z-q" x="${m.l + iw + 12}" y="${f1((y(qb) + y(0)) / 2 + 4)}">Quarantine &lt; ${qb}</text>` : "";

  // x ticks: first, last, and up to 5 evenly chosen points in between (never overlapping)
  const tickIdx = new Set([0, points.length - 1]);
  const want = Math.min(5, Math.floor(iw / 130));
  for (let k = 1; k < want; k++) tickIdx.add(Math.round((k * (points.length - 1)) / want));
  const ticks = [...tickIdx].sort((a, b) => a - b).map((i) => html`<text class="ch-axis" x="${f1(xs[i])}" y="${H - 8}" text-anchor="${i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}">${points[i].now ? "now" : clock(points[i].ts)}</text>`);

  const marks = points.map((p, i) => (p.transition || p.now)
    ? html`<circle class="ch-mark t-${stateMeta(p.state).tone}" cx="${f1(xs[i])}" cy="${f1(y(p.score))}" r="${p.now ? 4.5 : 5.5}"/>` : "");

  // hit columns for the hover layer (wider than the marks)
  const hits = points.map((p, i) => {
    const left = i === 0 ? m.l : (xs[i - 1] + xs[i]) / 2;
    const right = i === points.length - 1 ? m.l + iw : (xs[i] + xs[i + 1]) / 2;
    const tip = `${p.now ? "Now" : clock(p.ts)}|${p.score}|${p.state}|${p.label || ""}|${Number.isFinite(p.delta) && p.delta ? (p.delta > 0 ? `+${p.delta}` : `${p.delta}`) : ""}`;
    return html`<rect class="ch-hit" x="${f1(left)}" y="${m.t}" width="${f1(Math.max(1, right - left))}" height="${ih}" data-tip="${tip}" data-cx="${f1(xs[i])}" data-cy="${f1(y(p.score))}"/>`;
  });

  const last = points[points.length - 1];
  const summary = `Trust score over ${points.length} recorded changes, from ${points[0].score} to ${last.score}, now ${last.state}.`;
  return html`<div class="chart" data-chart="${id}" data-w="${W}" data-h="${H}">
    <svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="${summary}">
      <defs><linearGradient id="ch-fade-${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0f1b2d" stop-opacity="0.06"/><stop offset="1" stop-color="#0f1b2d" stop-opacity="0"/></linearGradient></defs>
      ${bands}${grid}${zoneLabels}
      <path d="${area}" fill="url(#ch-fade-${id})"/>
      <path class="ch-line" d="${d}"/>
      ${marks}
      <line class="ch-cross" data-cross x1="0" x2="0" y1="${m.t}" y2="${m.t + ih}" visibility="hidden"/>
      ${ticks}
      <g class="ch-hits">${hits}</g>
    </svg>
  </div>`;
}

/** Hover layer: one floating tooltip for every chart, wired once with event delegation. */
export function installChartHover(root) {
  const tip = document.createElement("div");
  tip.className = "tooltip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.appendChild(tip);
  const hide = () => {
    tip.hidden = true;
    root.querySelectorAll("[data-cross]").forEach((c) => c.setAttribute("visibility", "hidden"));
  };
  root.addEventListener("pointerover", (e) => {
    const hit = e.target.closest && e.target.closest(".ch-hit");
    if (!hit) return;
    const svg = hit.ownerSVGElement;
    const [time, score, state, label, delta] = hit.dataset.tip.split("|");
    tip.replaceChildren();
    const b = document.createElement("b");
    b.textContent = `${score}  ${state}`;
    const l = document.createElement("div"); l.textContent = label;
    const t = document.createElement("div"); t.className = "tt-muted"; t.textContent = `${time}${delta ? `  (${delta.replace("-", "−")})` : ""}`;
    tip.append(b, l, t);
    const cross = svg.querySelector("[data-cross]");
    cross.setAttribute("x1", hit.dataset.cx); cross.setAttribute("x2", hit.dataset.cx); cross.setAttribute("visibility", "visible");
    const box = svg.getBoundingClientRect();
    const sx = box.width / Number(svg.viewBox.baseVal.width), sy = box.height / Number(svg.viewBox.baseVal.height);
    tip.style.position = "fixed";
    tip.style.left = `${Math.min(window.innerWidth - 140, Math.max(140, box.left + Number(hit.dataset.cx) * sx))}px`;
    tip.style.top = `${box.top + Number(hit.dataset.cy) * sy}px`;
    tip.hidden = false;
  });
  root.addEventListener("pointerout", (e) => {
    if (e.target.closest && e.target.closest(".ch-hit") && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".ch-hit"))) hide();
  });
  window.addEventListener("scroll", hide, { passive: true });
}

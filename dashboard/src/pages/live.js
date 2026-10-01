// Presentation mode: the security story at a distance. Big state, big score, the path so far, what the gateway is
// enforcing and the latest decisions. Same live data as everywhere else; nothing is staged.
import { html } from "../lib/html.js";
import { STORY, stateMeta } from "../lib/copy.js";
import { clock } from "../lib/format.js";
import { S, focusId, gatewayNow } from "../store.js";
import { UI, deviceModel } from "../model.js";
import { storyProgress } from "../components/rail.js";
import { brandMark, icon } from "../components/icons.js";
import { loadingPanel } from "../components/states.js";
import { deltaText } from "../components/status.js";

export function render() {
  const id = S.loaded ? focusId() : null;
  const m = id ? deviceModel(id) : null;
  const snap = m && m.snapshot;
  const state = snap && snap.state;
  const meta = stateMeta(state);
  const { marks, pos } = m ? storyProgress(m.path, state) : { marks: [], pos: -1 };
  const latest = m ? m.timeline.slice(0, 5) : [];
  const n = m && m.access ? m.access.normal : null, r = m && m.access ? m.access.recovery : null;
  const recent = UI.flash && UI.flash.until > Date.now() && UI.flash.deviceId === id ? UI.flash : null;
  const v = S.evidence.verify;
  return html`<div class="live tone-${meta.tone}">
    <header class="live-top">
      <div class="row" style="gap:12px">${brandMark}<span class="live-brand">Q-SHIELD</span><span class="live-tag">Live</span></div>
      <div class="live-device">${id || "No device"}${m && m.device && m.device.hw === "software-agent" ? html` <span class="tag sim">Simulated device</span>` : ""}</div>
      <div class="row" style="gap:12px">
        ${S.connected === false ? html`<span class="chip crit"><span class="dot"></span>Gateway offline</span>` : ""}
        ${Math.abs(S.clockOffset) > 120 ? html`<span class="chip warn">Time-lapse</span>` : ""}
        <span class="live-clock num" data-gateway-clock>${clock(gatewayNow())}</span>
        <a class="btn ghost" href="#/overview" data-action="exit-live">${icon("x")}Exit</a>
      </div>
    </header>
    ${!m ? html`<div style="padding:48px">${loadingPanel(6)}</div>` : html`
    <ol class="live-rail" aria-label="Security story">${STORY.map((s, i) => {
      const sm = stateMeta(s);
      const now = i === pos, past = !now && marks[i] !== null && i < pos;
      return html`<li class="lr-step ${now ? "is-now" : past ? "is-past" : ""}" data-tone="${sm.tone}" ${now ? html`aria-current="step"` : ""}>
        <span class="lr-node">${icon(now || past ? sm.icon : "dot")}</span><span class="lr-label">${s}</span></li>`;
    })}</ol>
    <div class="live-main">
      <section class="live-state" aria-live="polite">
        ${recent ? html`<div class="live-change">${recent.from} → ${recent.to}</div>` : html`<div class="live-change is-quiet">Current state</div>`}
        <div class="live-word">${icon(meta.icon)}${state || "NO DATA"}</div>
        <div class="live-score"><span class="num" data-tween="score">${snap && Number.isFinite(snap.score) ? snap.score : "—"}</span><span class="live-of">trust score</span></div>
        <p class="live-line">${meta.line}</p>
        <div class="live-channels">
          <div class="lc ${n ? (n.allowed ? "ok" : "crit") : ""}">${icon(n && !n.allowed ? "x" : "check")}<span>Normal channel</span><b>${n ? (n.allowed ? "Open" : "Blocked") : "—"}</b></div>
          <div class="lc ${r ? (r.allowed ? "ok" : "") : ""}">${icon(r && r.allowed ? "refresh" : "minus")}<span>Recovery channel</span><b>${r ? (r.allowed ? "Available" : "Closed") : "—"}</b></div>
        </div>
      </section>
      <section class="live-feed" aria-label="Latest decisions">
        <h2 class="live-h">Latest decisions</h2>
        <ol>${latest.map((it, i) => html`<li class="lf-item ${i === 0 ? "is-first" : ""}" data-tone="${it.tone}" data-key="lf-${it.key}">
          <span class="lf-time num">${clock(it.ts)}</span>
          <div><div class="lf-title">${it.title}</div>${it.sub ? html`<div class="lf-sub">${it.sub}</div>` : ""}</div>
          ${Number.isFinite(it.scoreTo) ? html`<span class="lf-score num">${it.scoreTo} ${deltaText(it.delta)}</span>` : html`<span></span>`}
        </li>`)}</ol>
        <div class="live-foot">
          ${v ? html`<span class="row" style="gap:8px">${icon(v.ok ? "shieldCheck" : "unlink")}${v.ok ? `Evidence chain verified: ${v.count} entries${v.signed ? ", ML-DSA signed" : ""}` : `Evidence chain broken at #${v.first_bad_seq}`}</span>` : ""}
        </div>
      </section>
    </div>`}
  </div>`;
}

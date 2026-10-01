// Presentation mode: the security story at a distance. Big state, big score, the path so far, why the device is where
// it is, what the gateway is enforcing and the latest decisions. Same live data as everywhere else; nothing is staged.
import { html } from "../lib/html.js";
import { STORY, failureLabel, stateMeta } from "../lib/copy.js";
import { clock, duration } from "../lib/format.js";
import { S, focusId, gatewayNow } from "../store.js";
import { UI, deviceModel, thresholds } from "../model.js";
import { storyProgress } from "../components/rail.js";
import { brandMark, icon } from "../components/icons.js";
import { loadingPanel } from "../components/states.js";
import { deltaText, rejectedTag, simTag } from "../components/status.js";

const FEED_SIZE = 5;
const MODALITY = { PHYSICAL: "Physical tamper", VISUAL: "signed camera evidence", SENSOR: "sensor anomaly" };
const SHORT_STEP = { remediation: "Remediation", health: "Health checks", verified: "Verified", ramp: "Trust ramp", recovered: "Access restored", trusted: "Trusted" };

/** Entries worth a slot on the big screen: state changes, gateway events, and anything that moved the score. */
export const meaningful = (it) => it.isState || it.type === "event" || (Number.isFinite(it.delta) && it.delta !== 0);

function authShort(auth, sigAlg) {
  if (auth === "DEVICE_HMAC") return "HMAC-SHA256";
  if (auth === "SIGNER_MLDSA") return sigAlg;
  return null;
}

/** Did the device's latest state change come out of a completed recovery (RECOVERED -> TRUSTED)? */
function afterRecovery(m) {
  const p = m.path;
  return p.length >= 2 && p[p.length - 1].state === "TRUSTED" && p[p.length - 2].state === "RECOVERED" ? p[p.length - 1].ts : null;
}

function whenState(m, state) {
  for (let i = m.path.length - 1; i >= 0; i--) if (m.path[i].state === state) return m.path[i].ts;
  return null;
}

// ---------------------------------------------------------------------------------------------- context block
function quarantineReason(m) {
  const inc = m.incidents.find((i) => i.status !== "resolved");
  const failed = m.recovery && m.recovery.status === "failed" ? m.recovery : null;
  if (inc) {
    const parts = inc.members.map((x) => {
      const a = authShort(x.auth, m.sigAlg);
      return `${MODALITY[x.modality] || x.modality}${a ? ` (${a})` : ""}`;
    });
    const parts0 = parts.length ? parts.join(" + ") : inc.title;
    const simulated = inc.members.some((x) => x.provenance && /simulat|synthetic/i.test(x.provenance));
    const span = Number.isFinite(inc.spanS) ? (inc.spanS < 1 ? "Both signals less than a second apart" : `Both signals within ${duration(inc.spanS)}`) : null;
    return html`<div class="lv-ctx lv-reason">
      <div class="lv-ctx-label">${icon("alert")}${inc.cls === "confirmed_incident" ? "Confirmed incident" : "Correlated incident"}</div>
      <div class="lv-ctx-main">${parts0[0].toUpperCase() + parts0.slice(1)}</div>
      <div class="lv-ctx-sub">${[span, `correlation window ${duration(inc.windowS)}`].filter(Boolean).join(", ")}${simulated ? html` ${simTag("Includes simulated device data or a synthetic detection signed with the real vision key")}` : ""}</div>
      ${failed ? html`<div class="lv-ctx-sub">Last recovery attempt failed. ${failureLabel(failed.failure_reason)}</div>` : ""}
    </div>`;
  }
  // No open incident (e.g. operator quarantine): show the recorded reason of the latest transition into quarantine.
  const q = m.timeline.find((it) => it.isState && it.stateTo === "QUARANTINED");
  return html`<div class="lv-ctx lv-reason">
    <div class="lv-ctx-label">${icon("lock")}Why quarantined</div>
    <div class="lv-ctx-main">${q ? q.sub || q.title : "Quarantined by the trust engine"}</div>
  </div>`;
}

function recoveryProgress(m) {
  const steps = m.steps.slice(2);                        // remediation .. trusted
  const active = steps.find((s) => s.status === "active" || s.status === "failed");
  let detail = "";
  if (active && active.key === "health" && active.pips) {
    detail = html`<span class="pips lv-pips" aria-hidden="true">${Array.from({ length: active.pips.of }, (_, i) => html`<i class="${i < active.pips.on ? "on" : ""}"></i>`)}</span>
      <span><b class="num">${active.pips.on} / ${active.pips.of}</b> consecutive clean health checks</span>`;
  } else if (active && (active.key === "ramp" || active.key === "trusted") && active.progress) {
    const { value, target } = active.progress;
    detail = html`<span class="progress lv-progress" role="progressbar" aria-valuemin="0" aria-valuemax="${target}" aria-valuenow="${Math.min(value, target)}" aria-label="Trust ${value} of ${target}">
        <i style="width:${Math.min(100, (value / target) * 100).toFixed(1)}%"></i></span>
      <span>Trust rebuilding: <b class="num">${value} / ${target}</b> ${active.key === "ramp" ? "required for restored access" : "to fully trusted"}</span>`;
  } else if (active) {
    detail = html`<span>${active.sub}</span>`;
  }
  return html`<div class="lv-ctx lv-progress-block">
    <ol class="lv-steps" aria-label="Recovery progress">${steps.map((s) => html`<li class="is-${s.status}" ${s.status === "active" ? html`aria-current="step"` : ""}>
      <span class="lv-step-node" aria-hidden="true">${s.status === "done" ? icon("check") : s.status === "failed" ? icon("x") : ""}</span>
      <span class="lv-step-label">${SHORT_STEP[s.key] || s.title}<span class="sr-only"> (${s.status})</span></span></li>`)}</ol>
    ${detail ? html`<div class="lv-ctx-detail">${detail}</div>` : ""}
  </div>`;
}

function restored(m, state) {
  const snap = m.snapshot;
  const t = thresholds();
  const reentry = t ? t.trusted_reentry_min : null;
  const at = whenState(m, "RECOVERED");
  if (state === "RECOVERED") {
    return html`<div class="lv-ctx lv-restored">
      <div class="lv-ctx-label">${icon("unlock")}Normal channel restored</div>
      <div class="lv-ctx-main">Access returned${at ? ` at ${clock(at)}` : ""}; the recovery channel is closed.</div>
      ${Number.isFinite(reentry) && Number.isFinite(snap.score) ? html`<div class="lv-ctx-detail">
        <span class="progress lv-progress is-ok" role="progressbar" aria-valuemin="0" aria-valuemax="${reentry}" aria-valuenow="${Math.min(snap.score, reentry)}" aria-label="Trust ${snap.score} of ${reentry}"><i style="width:${Math.min(100, (snap.score / reentry) * 100).toFixed(1)}%"></i></span>
        <span>Trust rebuilding: <b class="num">${snap.score} / ${reentry}</b> to fully trusted</span></div>` : ""}
    </div>`;
  }
  return html`<div class="lv-ctx lv-restored">
    <div class="lv-ctx-label">${icon("checkCircle")}Normal channel restored</div>
    <div class="lv-ctx-main">Recovery complete: trust rebuilt to ${snap.score}.</div>
    <div class="lv-ctx-sub">${at ? `Access returned at ${clock(at)}, fully trusted at ${clock(afterRecovery(m))}.` : ""}</div>
  </div>`;
}

function context(m, state, meta) {
  if (state === "QUARANTINED") return quarantineReason(m);
  if ((state === "RECOVERING" || state === "VERIFIED") && m.recovery) return recoveryProgress(m);
  const normalOpen = m.access && m.access.normal && m.access.normal.allowed;
  if (normalOpen && state === "RECOVERED") return restored(m, state);
  if (normalOpen && state === "TRUSTED" && afterRecovery(m)) return restored(m, state);
  return html`<p class="live-line">${meta.line}</p>`;
}

// ---------------------------------------------------------------------------------------------- page
export function render() {
  const id = S.loaded ? focusId() : null;
  const m = id ? deviceModel(id) : null;
  const snap = m && m.snapshot;
  const state = snap && snap.state;
  const meta = stateMeta(state);
  const { marks, pos } = m ? storyProgress(m.path, state) : { marks: [], pos: -1 };
  const latest = m ? m.timeline.filter(meaningful).slice(0, FEED_SIZE) : [];
  const n = m && m.access ? m.access.normal : null, r = m && m.access ? m.access.recovery : null;
  const recent = UI.flash && UI.flash.until > Date.now() && UI.flash.deviceId === id ? UI.flash : null;
  const restoredNow = !!(n && n.allowed && (state === "RECOVERED" || (state === "TRUSTED" && m && afterRecovery(m))));
  const justRestored = restoredNow && recent && recent.to === "RECOVERED";
  const sealing = !!(recent && recent.to === "QUARANTINED");
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
        ${snap && snap.status === "TRACKED" ? context(m, state, meta) : ""}
        <div class="live-channels">
          <div class="lc ${n ? (n.allowed ? "ok" : "crit") : ""} ${restoredNow ? "is-restored" : ""} ${justRestored ? "is-new" : ""} ${sealing && n && !n.allowed ? "is-sealing" : ""}">${icon(n && !n.allowed ? "x" : "check")}<span>Normal channel</span><b>${n ? (n.allowed ? (restoredNow ? "Restored" : "Open") : "Blocked") : "—"}</b></div>
          <div class="lc ${r ? (r.allowed ? "ok" : "") : ""} ${sealing && r && r.allowed ? "is-opening" : ""}">${icon(r && r.allowed ? "refresh" : "minus")}<span>Recovery channel</span><b>${r ? (r.allowed ? "Available" : "Closed") : "—"}</b></div>
        </div>
      </section>
      <section class="live-feed" aria-label="Latest decisions">
        <h2 class="live-h">Latest decisions</h2>
        <ol>${latest.map((it, i) => html`<li class="lf-item ${i === 0 ? "is-first" : ""}" data-tone="${it.tone}" data-key="lf-${it.key}">
          <span class="lf-time num">${clock(it.ts)}</span>
          <div><div class="lf-title">${it.title}${it.rejected ? html` ${rejectedTag()}` : ""}</div>${it.sub ? html`<div class="lf-sub">${it.sub}</div>` : ""}</div>
          ${Number.isFinite(it.scoreTo) ? html`<span class="lf-score num">${it.scoreTo}${it.delta ? html` ${deltaText(it.delta)}` : ""}</span>` : html`<span></span>`}
        </li>`)}</ol>
        <div class="live-foot">
          ${v ? html`<span class="row" style="gap:8px">${icon(v.ok ? "shieldCheck" : "unlink")}${v.ok ? `Evidence chain verified: ${v.count} entries${v.signed ? ", ML-DSA signed" : ""}` : `Evidence chain broken at #${v.first_bad_seq}`}</span>` : ""}
        </div>
      </section>
    </div>`}
  </div>`;
}
